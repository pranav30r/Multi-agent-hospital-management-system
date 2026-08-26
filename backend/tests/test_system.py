import pytest

@pytest.mark.asyncio
async def test_request_context_middleware_headers(client):
    """Verify that every response receives X-Request-ID and X-Process-Time-Ms headers."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert "x-process-time-ms" in response.headers
    assert float(response.headers["x-process-time-ms"]) >= 0.0


@pytest.mark.asyncio
async def test_system_metrics_endpoint(client):
    """Verify system telemetry metrics (memory, CPU, DB status, uptime)."""
    response = await client.get("/api/v1/system/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ONLINE"
    assert "uptime_seconds" in data
    assert "resources" in data
    assert "memory_used_mb" in data["resources"]
    assert "database" in data
    assert data["database"]["status"] == "HEALTHY"
