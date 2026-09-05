import pytest
from httpx import AsyncClient
from app.auth.security import create_access_token
from app.utils.pagination import encode_cursor, decode_cursor


def test_cursor_encode_and_decode_cycle():
    """Verify that cursor encoding and decoding preserves values and types."""
    from datetime import datetime
    now = datetime(2026, 9, 5, 12, 30, 45)
    token = encode_cursor(now, "OBS-123456")
    val, item_id = decode_cursor(token)
    assert item_id == "OBS-123456"
    assert val == now.isoformat()


@pytest.mark.asyncio
async def test_paginated_patient_query_max_limit_enforcement(client: AsyncClient):
    """Verify that page_size is strictly capped at 100 to prevent unbounded memory scans."""
    token = create_access_token({
        "sub": "DOC-001",
        "role": "DOCTOR",
        "name": "Dr. Rajesh Sharma",
        "department_id": "DEP-ER",
        "tenant_id": "HOSP-DEFAULT"
    })
    headers = {"Authorization": f"Bearer {token}"}

    # Request limit=5000 -> must be rejected or capped to 100
    res = await client.get("/api/v1/patients?limit=5000", headers=headers)
    # FastAPI Query(le=100) returns 422 Unprocessable Entity
    assert res.status_code == 422
