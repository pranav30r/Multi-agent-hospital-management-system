import pytest
from app.utils.pagination import PaginationParams, paginate_query
from app.models.disease import Disease
from sqlalchemy import select

@pytest.mark.asyncio
async def test_pagination_disease_query(test_db):
    """Verify pagination math, total count, and has_next / has_prev flags."""
    async with test_db() as session:
        # Page 1 (20 items)
        params1 = PaginationParams(page=1, page_size=20)
        p1 = await paginate_query(select(Disease), Disease, params1, session)
        assert len(p1["items"]) == 20
        assert p1["total_count"] == 40
        assert p1["total_pages"] == 2
        assert p1["has_next"] is True
        assert p1["has_prev"] is False

        # Page 2 (20 items)
        params2 = PaginationParams(page=2, page_size=20)
        p2 = await paginate_query(select(Disease), Disease, params2, session)
        assert len(p2["items"]) == 20
        assert p2["total_pages"] == 2
        assert p2["has_next"] is False
        assert p2["has_prev"] is True
