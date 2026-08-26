import pytest

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
