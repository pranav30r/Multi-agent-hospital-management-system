from typing import Generic, TypeVar, List, Optional
from pydantic import BaseModel, Field
from fastapi import Query
from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")

class PaginationParams:
    """Dependency for parsing pagination and sorting query parameters."""
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
        sort_by: Optional[str] = Query(None, description="Field name to sort by"),
        sort_order: str = Query("asc", regex="^(asc|desc)$", description="Sort order ('asc' or 'desc')")
    ):
        self.page = page
        self.page_size = page_size
        self.sort_by = sort_by
        self.sort_order = sort_order.lower()

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized envelope for paginated collections."""
    items: List[T]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


async def paginate_query(
    query,
    model,
    params: PaginationParams,
    db: AsyncSession
) -> dict:
    """
    Executes a paginated SQLAlchemy select query and returns metadata.
    """
    # 1. Total count
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    # 2. Sorting
    if params.sort_by and hasattr(model, params.sort_by):
        col = getattr(model, params.sort_by)
        order_fn = desc if params.sort_order == "desc" else asc
        query = query.order_by(order_fn(col))

    # 3. Pagination slice
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
