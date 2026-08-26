import pytest

@pytest.mark.asyncio
async def test_staff_login_success(client):
    """Test successful staff authentication and JWT generation."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"staff_id": "DOC-001", "password": "hospital@123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["staff_id"] == "DOC-001"
    assert data["role"] == "DOCTOR"


@pytest.mark.asyncio
async def test_staff_login_invalid_password(client):
    """Test failed login with incorrect password."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"staff_id": "DOC-001", "password": "wrong_password"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_staff_login_unknown_id(client):
    """Test login with non-existent staff ID."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"staff_id": "DOC-999", "password": "hospital@123"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_staff_get_me(client):
    """Test querying authenticated profile via Bearer token."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"staff_id": "DOC-001", "password": "hospital@123"}
    )
    token = login_res.json()["access_token"]

    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert me_res.status_code == 200
    data = me_res.json()
    assert data["id"] == "DOC-001"
    assert data["role"] == "DOCTOR"
    assert data["department_id"] == "DEP-ER"


@pytest.mark.asyncio
async def test_staff_register(client):
    """Test registering a new staff member account."""
    reg_payload = {
        "id": "DOC-099",
        "first_name": "Siddharth",
        "last_name": "Rao",
        "role": "DOCTOR",
        "department_id": "DEP-ICU",
        "specialization": "Critical Care Medicine",
        "max_workload": 6
    }
    response = await client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["staff_id"] == "DOC-099"
    assert "access_token" in data
