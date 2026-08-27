import pytest

@pytest.mark.asyncio
async def test_security_headers_present(client):
    """Verify that OWASP security headers are present on all responses."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("x-xss-protection") == "1; mode=block"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_rate_limiter_middleware_triggers_429_on_excess_traffic():
    """Verify that InMemoryRateLimiter triggers HTTP 429 when threshold is exceeded."""
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from app.middleware.rate_limit import InMemoryRateLimiter

    test_app = FastAPI()
    test_app.add_middleware(InMemoryRateLimiter, max_requests=3, window_seconds=60)

    @test_app.get("/test-endpoint")
    async def sample_endpoint():
        return {"status": "ok"}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # First 3 requests succeed
        for _ in range(3):
            res = await ac.get("/test-endpoint")
            assert res.status_code == 200

        # 4th request exceeds rate limit and receives 429
        blocked_res = await ac.get("/test-endpoint")
        assert blocked_res.status_code == 429
        data = blocked_res.json()
        assert "Rate limit exceeded" in data["detail"]
        assert "Retry-After" in blocked_res.headers


@pytest.mark.asyncio
async def test_rate_limiter_whitelists_health_and_root():
    """Verify that health checks and root are not rate-limited."""
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from app.middleware.rate_limit import InMemoryRateLimiter

    test_app = FastAPI()
    test_app.add_middleware(InMemoryRateLimiter, max_requests=1, window_seconds=60)

    @test_app.get("/health")
    async def health():
        return {"status": "healthy"}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for _ in range(5):
            res = await ac.get("/health")
            assert res.status_code == 200
