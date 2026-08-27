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


@pytest.mark.asyncio
async def test_health_check_active_db_returns_200(client):
    """Verify that /health actively executes a DB ping and returns 200 when healthy."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_api_v1_health_check_returns_200(client):
    """Verify that /api/v1/health returns 200 with connected DB."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_root_endpoint_metadata(client):
    """Verify root endpoint responds with system metadata."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "system" in data
    assert "docs" in data


def test_production_secret_guard_blocks_insecure_secrets():
    """Verify that Settings raises an error if production is booted with insecure/short secrets."""
    from app.config import Settings
    with pytest.raises(ValueError, match="CRITICAL SECURITY CONFIGURATION ERROR"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="hospital-super-secret-key-change-in-production-2026",
            JWT_SECRET="hospital-super-secret-key-change-in-production-2026"
        )
