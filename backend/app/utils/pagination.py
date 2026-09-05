import base64
import json
from typing import Generic, TypeVar, List, Optional, Any, Tuple
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from fastapi import Query
from sqlalchemy import select, func, desc, asc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")

class PaginationParams:
    """Dependency for parsing offset pagination and sorting query parameters."""
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page (capped at 100)"),
        sort_by: Optional[str] = Query(None, description="Field name to sort by"),
        sort_order: str = Query("asc", description="Sort order ('asc' or 'desc')")
    ):
        raw_page = page.default if hasattr(page, "default") else page
        self.page = int(raw_page or 1)
        raw_page_size = page_size.default if hasattr(page_size, "default") else page_size
        self.page_size = min(int(raw_page_size or 20), 100)
        raw_sort_by = sort_by.default if hasattr(sort_by, "default") else sort_by
        self.sort_by = str(raw_sort_by) if raw_sort_by is not None else None
        raw_order = sort_order.default if hasattr(sort_order, "default") else sort_order
        self.sort_order = str(raw_order or "asc").lower()

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized envelope for offset-paginated collections."""
    items: List[T]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool

    model_config = ConfigDict(from_attributes=True)


async def paginate_query(
    query,
    model,
    params: PaginationParams,
    db: AsyncSession
) -> dict:
    """
    Executes an offset-paginated SQLAlchemy select query and returns envelope metadata.
    """
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    if params.sort_by and hasattr(model, params.sort_by):
        col = getattr(model, params.sort_by)
        order_fn = desc if params.sort_order == "desc" else asc
        query = query.order_by(order_fn(col))

    query = query.offset(params.offset).limit(params.page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    total_pages = max(1, (total_count + params.page_size - 1) // params.page_size)

    return {
        "items": items,
        "total_count": total_count,
        "page": params.page,
        "page_size": params.page_size,
        "total_pages": total_pages,
        "has_next": params.page < total_pages,
        "has_prev": params.page > 1,
    }


# ─── Cursor-Based Pagination (for 100K+ High-Throughput Tables) ──────────────

def encode_cursor(val: Any, item_id: str) -> str:
    """Encodes sorting key and item ID into an opaque cursor token."""
    if isinstance(val, datetime):
        val_str = val.isoformat()
    else:
        val_str = str(val) if val is not None else ""
    raw = json.dumps({"v": val_str, "id": str(item_id)})
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor_str: str) -> Optional[Tuple[str, str]]:
    """Decodes an opaque cursor token into (sort_value_str, item_id)."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
        data = json.loads(raw)
        return data.get("v"), data.get("id")
    except Exception:
        return None


class CursorPaginationParams:
    """Dependency for parsing cursor pagination query parameters."""
    def __init__(
        self,
        cursor: Optional[str] = Query(None, description="Opaque cursor token for keyset pagination"),
        limit: int = Query(20, ge=1, le=100, description="Max items per page (capped at 100)"),
        sort_order: str = Query("desc", description="Sort order: 'desc' (default) or 'asc'")
    ):
        raw_cursor = cursor.default if hasattr(cursor, "default") else cursor
        self.cursor = str(raw_cursor) if raw_cursor else None
        raw_limit = limit.default if hasattr(limit, "default") else limit
        self.limit = min(int(raw_limit or 20), 100)
        raw_order = sort_order.default if hasattr(sort_order, "default") else sort_order
        self.sort_order = str(raw_order or "desc").lower()


class CursorPaginatedResponse(BaseModel, Generic[T]):
    """Standardized envelope for cursor-paginated collections."""
    items: List[T]
    limit: int
    next_cursor: Optional[str] = None
    has_more: bool = False

    model_config = ConfigDict(from_attributes=True)


async def cursor_paginate_query(
    query,
    model,
    sort_column_name: str,
    params: CursorPaginationParams,
    db: AsyncSession
) -> dict:
    """
    Executes a high-efficiency Keyset/Cursor-paginated query ($O(1)$ index lookup).
    Fetches limit + 1 items to determine if a subsequent page exists without a COUNT scan.
    """
    sort_col = getattr(model, sort_column_name)
    id_col = getattr(model, "id")
    is_desc = params.sort_order == "desc"

    if params.cursor:
        decoded = decode_cursor(params.cursor)
        if decoded:
            val_str, cursor_id = decoded
            # Parse datetime if needed
            val = val_str
            if isinstance(sort_col.type.python_type, type) and issubclass(sort_col.type.python_type, datetime):
                try:
                    val = datetime.fromisoformat(val_str)
                except Exception:
                    pass

            if is_desc:
                # WHERE (col < val) OR (col == val AND id < cursor_id)
                condition = or_(
                    sort_col < val,
                    and_(sort_col == val, id_col < cursor_id)
                )
            else:
                condition = or_(
                    sort_col > val,
                    and_(sort_col == val, id_col > cursor_id)
                )
            query = query.where(condition)

    # Apply deterministic ordering
    if is_desc:
        query = query.order_by(desc(sort_col), desc(id_col))
    else:
        query = query.order_by(asc(sort_col), asc(id_col))

    # Fetch limit + 1
    query = query.limit(params.limit + 1)
    result = await db.execute(query)
    all_items = result.scalars().all()

    has_more = len(all_items) > params.limit
    items = all_items[:params.limit]

    next_cursor = None
    if has_more and items:
        last_item = items[-1]
        sort_val = getattr(last_item, sort_column_name)
        item_id = getattr(last_item, "id")
        next_cursor = encode_cursor(sort_val, item_id)

    return {
        "items": items,
        "limit": params.limit,
        "next_cursor": next_cursor,
        "has_more": has_more
    }
