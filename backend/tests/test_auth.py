import pytest
from app.auth.security import decode_access_token


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
    assert data["tenant_id"] == "HOSP-DEFAULT"


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
    assert data["tenant_id"] == "HOSP-DEFAULT"


@pytest.mark.asyncio
async def test_staff_register(admin_client):
    """Test registering a new staff member account by an authorized administrator."""
    reg_payload = {
        "id": "DOC-099",
        "first_name": "Siddharth",
        "last_name": "Rao",
        "role": "DOCTOR",
        "department_id": "DEP-ICU",
        "specialization": "Critical Care Medicine",
        "max_workload": 6
    }
    response = await admin_client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["staff_id"] == "DOC-099"
    assert data["tenant_id"] == "HOSP-DEFAULT"
    assert "access_token" in data

    token_payload = decode_access_token(data["access_token"])
    assert token_payload is not None
    assert token_payload.get("tenant_id") == "HOSP-DEFAULT"
    assert token_payload.get("sub") == "DOC-099"


@pytest.mark.asyncio
async def test_unauthenticated_staff_register_rejected(client):
    """Test that registration is rejected with 401 when caller is unauthenticated."""
    reg_payload = {
        "id": "DOC-UNAUTH-01",
        "first_name": "Hacker",
        "last_name": "User",
        "role": "DOCTOR",
        "department_id": "DEP-ER"
    }
    response = await client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_staff_register_rejected(auth_client):
    """Test that registration is rejected with 403 when caller is non-admin (e.g. DOCTOR)."""
    reg_payload = {
        "id": "DOC-FORBIDDEN-01",
        "first_name": "Unauthorized",
        "last_name": "Doctor",
        "role": "DOCTOR",
        "department_id": "DEP-ER"
    }
    response = await auth_client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_register_staff_in_foreign_tenant(admin_client):
    """Test that admin cannot specify a different tenant_id than their own (reject 403)."""
    reg_payload = {
        "id": "DOC-CROSS-01",
        "first_name": "Cross",
        "last_name": "Tenant",
        "role": "DOCTOR",
        "department_id": "DEP-ER",
        "tenant_id": "HOSP-RIVAL"
    }
    response = await admin_client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 403
    assert "another tenant" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_cannot_register_staff_in_foreign_department(admin_client):
    """Test that admin cannot assign staff to a non-existent or foreign tenant department (reject 400)."""
    reg_payload = {
        "id": "DOC-DEPT-INV",
        "first_name": "Invalid",
        "last_name": "Dept",
        "role": "DOCTOR",
        "department_id": "DEP-NON-EXISTENT"
    }
    response = await admin_client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


@pytest.mark.asyncio
async def test_jwt_missing_tenant_claim_is_rejected(client):
    """
    Fix 1 Regression Test: Prove that a valid staff ID with a JWT missing
    the tenant_id claim is rejected with 401 Unauthorized.
    """
    from jose import jwt
    from app.config import settings

    # Create a JWT token without tenant_id claim
    token_payload = {
        "sub": "DOC-001",
        "role": "DOCTOR",
        "name": "Dr. Test No Tenant"
    }
    raw_token = jwt.encode(token_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    headers = {"Authorization": f"Bearer {raw_token}"}

    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Token tenant does not match authoritative staff tenant"
