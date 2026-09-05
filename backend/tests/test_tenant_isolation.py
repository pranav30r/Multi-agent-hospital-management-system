import pytest
from httpx import AsyncClient
from app.auth.security import create_access_token


@pytest.mark.asyncio
async def test_same_tenant_patient_access(client: AsyncClient):
    """Verify that staff can access patient master records within their own tenant."""
    token_hosp_a = create_access_token({
        "sub": "DOC-001",
        "role": "DOCTOR",
        "name": "Dr. Hospital A",
        "department_id": "DEP-ER",
        "tenant_id": "HOSP-DEFAULT"
    })
    headers_a = {"Authorization": f"Bearer {token_hosp_a}"}

    # Register patient in HOSP-DEFAULT
    res = await client.post(
        "/api/v1/patients",
        headers=headers_a,
        json={
            "first_name": "TenantA",
            "last_name": "Patient",
            "age": 45,
            "gender": "M",
            "blood_group": "B+",
            "contact_phone": "+919811122233",
            "emergency_contact": "+919811122234"
        }
    )
    assert res.status_code == 201
    patient_id = res.json()["id"]

    # Same-tenant staff can retrieve patient
    get_res = await client.get(f"/api/v1/patients/{patient_id}", headers=headers_a)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == patient_id
    assert get_res.json()["tenant_id"] == "HOSP-DEFAULT"


@pytest.mark.asyncio
async def test_cross_tenant_patient_isolation(client: AsyncClient):
    """Verify that staff in Tenant B CANNOT read or query patients belonging to Tenant A."""
    token_hosp_a = create_access_token({
        "sub": "DOC-001",
        "role": "DOCTOR",
        "name": "Dr. Hospital A",
        "department_id": "DEP-ER",
        "tenant_id": "HOSP-DEFAULT"
    })
    headers_a = {"Authorization": f"Bearer {token_hosp_a}"}

    # Register patient in HOSP-DEFAULT
    res = await client.post(
        "/api/v1/patients",
        headers=headers_a,
        json={
            "first_name": "Confidential",
            "last_name": "Patient",
            "age": 50,
            "gender": "F",
            "blood_group": "O+",
            "contact_phone": "+919855566677",
            "emergency_contact": "+919855566678"
        }
    )
    assert res.status_code == 201
    patient_id = res.json()["id"]

    # Token for Staff in Tenant B (HOSP-RIVAL)
    token_hosp_b = create_access_token({
        "sub": "DOC-002",
        "role": "DOCTOR",
        "name": "Dr. Rival Facility",
        "department_id": "DEP-ER",
        "tenant_id": "HOSP-RIVAL"
    })
    headers_b = {"Authorization": f"Bearer {token_hosp_b}"}

    # Cross-tenant access must return 404 Not Found (zero information leakage)
    get_res = await client.get(f"/api/v1/patients/{patient_id}", headers=headers_b)
    assert get_res.status_code == 404

    # Cross-tenant search must NOT return patient from other tenant
    search_res = await client.get("/api/v1/patients?search=Confidential", headers=headers_b)
    assert search_res.status_code == 200
    patient_ids = [p["id"] for p in search_res.json()]
    assert patient_id not in patient_ids


@pytest.mark.asyncio
async def test_tenant_context_cannot_be_spoofed_in_request(client: AsyncClient):
    """Verify that client cannot spoof tenant ownership by providing arbitrary tenant headers/payloads."""
    token_hosp_a = create_access_token({
        "sub": "DOC-001",
        "role": "DOCTOR",
        "name": "Dr. Hospital A",
        "department_id": "DEP-ER",
        "tenant_id": "HOSP-DEFAULT"
    })
    headers_a = {"Authorization": f"Bearer {token_hosp_a}"}

    # Client tries to force tenant_id: "HOSP-FOREIGN" in request payload
    res = await client.post(
        "/api/v1/patients",
        headers=headers_a,
        json={
            "first_name": "Spoof",
            "last_name": "Attempt",
            "age": 30,
            "gender": "M",
            "blood_group": "A+",
            "contact_phone": "+919899988877",
            "emergency_contact": "+919899988878",
            "tenant_id": "HOSP-FOREIGN"
        }
    )
    assert res.status_code == 201
    # Server must bind it strictly to the authenticated JWT tenant ("HOSP-DEFAULT")
    assert res.json()["tenant_id"] == "HOSP-DEFAULT"
