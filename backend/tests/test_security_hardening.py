import pytest
from httpx import AsyncClient, ASGITransport
from app.config import Settings, DEFAULT_INSECURE_DEV_SECRET
from app.auth.security import create_access_token
from app.main import app

@pytest.mark.asyncio
async def test_input_sanitization_blocks_xss(client):
    """Verify that malicious XSS query parameters are intercepted and blocked with HTTP 400."""
    response = await client.get("/api/v1/diseases?search=<script>alert('hack')</script>")
    assert response.status_code == 400
    assert "Malicious characters or injection detected" in response.json()["detail"]


@pytest.mark.asyncio
async def test_brute_force_lockout_trigger(client):
    """Verify that 5 consecutive failed login attempts trigger an automated account lockout (HTTP 423)."""
    staff_id = "DOC-002"

    # 4 failed attempts
    for i in range(4):
        res = await client.post("/api/v1/auth/login", json={"staff_id": staff_id, "password": "bad_password"})
        assert res.status_code == 401
        assert "attempts remaining before lockout" in res.json()["detail"]

    # 5th failed attempt triggers lockout
    res5 = await client.post("/api/v1/auth/login", json={"staff_id": staff_id, "password": "bad_password"})
    assert res5.status_code == 401

    # 6th attempt is blocked with 423 Locked
    res6 = await client.post("/api/v1/auth/login", json={"staff_id": staff_id, "password": "hospital@123"})
    assert res6.status_code == 423
    assert "Account temporarily locked" in res6.json()["detail"]


@pytest.mark.asyncio
async def test_successful_login_resets_counter(client):
    """Verify that a successful login resets any previously recorded failed attempts."""
    staff_id = "DOC-003"
    # 2 failed attempts
    await client.post("/api/v1/auth/login", json={"staff_id": staff_id, "password": "wrong"})
    await client.post("/api/v1/auth/login", json={"staff_id": staff_id, "password": "wrong"})

    # Valid login
    res_ok = await client.post("/api/v1/auth/login", json={"staff_id": staff_id, "password": "hospital@123"})
    assert res_ok.status_code == 200
    assert "access_token" in res_ok.json()


def test_production_fails_on_default_secret():
    """Confirms production fails closed if default development secret is used."""
    with pytest.raises(ValueError, match="CRITICAL SECURITY CONFIGURATION ERROR"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY=DEFAULT_INSECURE_DEV_SECRET,
            JWT_SECRET="valid-strong-production-jwt-secret-key-32chars!",
            DATABASE_URL="postgresql+asyncpg://postgres:pass@localhost:5432/db"
        )


def test_production_fails_on_short_secret():
    """Confirms production fails closed if secret is under 32 characters."""
    with pytest.raises(ValueError, match="under 32 characters"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="short-secret-under-32-chars",
            JWT_SECRET="valid-strong-production-jwt-secret-key-32chars!",
            DATABASE_URL="postgresql+asyncpg://postgres:pass@localhost:5432/db"
        )


def test_production_fails_on_sqlite():
    """Confirms production fails closed if SQLite is used instead of PostgreSQL."""
    with pytest.raises(ValueError, match="CRITICAL DATABASE CONFIGURATION ERROR"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="valid-strong-production-secret-key-32chars!",
            JWT_SECRET="valid-strong-production-jwt-secret-key-32chars!",
            DATABASE_URL="sqlite+aiosqlite:///./hospital.db"
        )


def test_production_fails_on_wildcard_cors():
    """Confirms production fails closed if wildcard '*' is in ALLOWED_ORIGINS."""
    with pytest.raises(ValueError, match="CRITICAL CORS CONFIGURATION ERROR"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="valid-strong-production-secret-key-32chars!",
            JWT_SECRET="valid-strong-production-jwt-secret-key-32chars!",
            DATABASE_URL="postgresql+asyncpg://postgres:pass@localhost:5432/db",
            ALLOWED_ORIGINS="*"
        )


def test_production_valid_configuration_passes():
    """Confirms valid production configuration passes validation."""
    s = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="valid-strong-production-secret-key-32chars!",
        JWT_SECRET="valid-strong-production-jwt-secret-key-32chars!",
        DATABASE_URL="postgresql+asyncpg://postgres:pass@localhost:5432/db",
        ALLOWED_ORIGINS="https://hospital.example.com,https://admin.hospital.example.com"
    )
    assert s.ENVIRONMENT == "production"
    assert "https://hospital.example.com" in s.get_allowed_origins()


@pytest.mark.asyncio
async def test_invalid_token_type_rejected():
    """Confirms tokens with non-access type are rejected with 401."""
    token = create_access_token({"sub": "DOC-001", "role": "DOCTOR", "tenant_id": "HOSP-DEFAULT", "type": "refresh_token"})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/api/v1/dashboard/state", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401
        assert "Invalid token type" in res.json().get("detail", "")


@pytest.mark.asyncio
async def test_mismatched_tenant_rejected():
    """Confirms token with forged/mismatched tenant is rejected with 401."""
    token = create_access_token({"sub": "DOC-001", "role": "DOCTOR", "tenant_id": "HOSP-FORGED"})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/api/v1/dashboard/state", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401
        assert "Token tenant does not match" in res.json().get("detail", "")
