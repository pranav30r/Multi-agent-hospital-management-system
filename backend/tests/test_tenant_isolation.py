import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.auth.security import create_access_token
from app.models.tenant import Tenant
from app.models.department import Department
from app.models.staff import Staff
from app.models.patient import Encounter
from app.models.agent import AuditLog


async def seed_tenant_b(session_factory):
    """Seed a genuine second tenant with its department and staff in the test DB."""
    async with session_factory() as session:
        t = await session.get(Tenant, "HOSP-RIVAL")
        if not t:
            t = Tenant(id="HOSP-RIVAL", name="Rival Hospital", code="RIV", is_active=True)
            session.add(t)

        d = await session.get(Department, "DEP-RIVAL")
        if not d:
            d = Department(id="DEP-RIVAL", tenant_id="HOSP-RIVAL", name="Rival Emergency", code="ER")
            session.add(d)

        s = await session.get(Staff, "DOC-RIVAL-01")
        if not s:
            s = Staff(
                id="DOC-RIVAL-01",
                tenant_id="HOSP-RIVAL",
                first_name="Rival",
                last_name="Doctor",
                role="DOCTOR",
                department_id="DEP-RIVAL",
                status="AVAILABLE",
                current_workload=0,
                max_workload=5
            )
            session.add(s)

        admin_b = await session.get(Staff, "ADM-RIVAL-01")
        if not admin_b:
            admin_b = Staff(
                id="ADM-RIVAL-01",
                tenant_id="HOSP-RIVAL",
                first_name="Rival",
                last_name="Admin",
                role="ADMINISTRATOR",
                department_id="DEP-RIVAL",
                status="AVAILABLE",
                current_workload=0,
                max_workload=50
            )
            session.add(admin_b)

        await session.commit()


@pytest.mark.asyncio
async def test_jwt_tenant_mismatch_with_staff_record_is_rejected(client: AsyncClient):
    """
    Phase 2: If the JWT tenant_id does not match the database Staff.tenant_id,
    return 401 Unauthorized with the exact detail message, performing no mutation.
    """
    # DOC-001 belongs to HOSP-DEFAULT in the database, but token specifies HOSP-FORGED
    forged_token = create_access_token({
        "sub": "DOC-001",
        "role": "DOCTOR",
        "name": "Dr. Forged",
        "department_id": "DEP-ER",
        "tenant_id": "HOSP-FORGED"
    })
    forged_headers = {"Authorization": f"Bearer {forged_token}"}

    # Query endpoint
    res_get = await client.get("/api/v1/patients", headers=forged_headers)
    assert res_get.status_code == 401
    assert res_get.json()["detail"] == "Token tenant does not match authoritative staff tenant"

    # Mutation endpoint
    res_patch = await client.patch(
        "/api/v1/staff/DOC-001/status",
        headers=forged_headers,
        json={"status": "BUSY", "reason": "Attempting forged update"}
    )
    assert res_patch.status_code == 401
    assert res_patch.json()["detail"] == "Token tenant does not match authoritative staff tenant"


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
async def test_cross_tenant_patient_isolation(client: AsyncClient, test_db):
    """Verify that staff in Tenant B CANNOT read or query patients belonging to Tenant A."""
    await seed_tenant_b(test_db)

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

    # Genuine Token for Staff in Tenant B (HOSP-RIVAL)
    token_hosp_b = create_access_token({
        "sub": "DOC-RIVAL-01",
        "role": "DOCTOR",
        "name": "Dr. Rival Facility",
        "department_id": "DEP-RIVAL",
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
async def test_cross_tenant_active_encounters_isolation(client: AsyncClient, test_db):
    """
    Phase 6: Create genuine two-tenant active encounters and verify strict isolation.
    Tenant A: Patient A -> Encounter A
    Tenant B: Patient B -> Encounter B
    Tenant A query must return Encounter A and NOT Encounter B.
    Tenant B query must return Encounter B and NOT Encounter A.
    """
    await seed_tenant_b(test_db)

    headers_a = {"Authorization": f"Bearer {create_access_token({'sub': 'DOC-001', 'role': 'DOCTOR', 'tenant_id': 'HOSP-DEFAULT'})}"}
    headers_b = {"Authorization": f"Bearer {create_access_token({'sub': 'DOC-RIVAL-01', 'role': 'DOCTOR', 'tenant_id': 'HOSP-RIVAL'})}"}

    # 1. Create Patient A and Encounter A in Tenant A
    p_a_res = await client.post(
        "/api/v1/patients",
        headers=headers_a,
        json={
            "first_name": "Patient",
            "last_name": "Alpha",
            "age": 32,
            "gender": "M",
            "blood_group": "A+",
            "contact_phone": "+919811111111",
            "emergency_contact": "+919811111112"
        }
    )
    assert p_a_res.status_code == 201
    pat_a_id = p_a_res.json()["id"]

    enc_a_res = await client.post(
        "/api/v1/patients/encounters",
        headers=headers_a,
        json={
            "patient_id": pat_a_id,
            "chief_complaint": "Severe chest pain in Tenant A",
            "encounter_type": "EMERGENCY",
            "current_department_id": "DEP-ER"
        }
    )
    assert enc_a_res.status_code == 201
    enc_a_id = enc_a_res.json()["id"]

    # 2. Create Patient B and Encounter B in Tenant B
    p_b_res = await client.post(
        "/api/v1/patients",
        headers=headers_b,
        json={
            "first_name": "Patient",
            "last_name": "Beta",
            "age": 45,
            "gender": "F",
            "blood_group": "B+",
            "contact_phone": "+919822222221",
            "emergency_contact": "+919822222222"
        }
    )
    assert p_b_res.status_code == 201
    pat_b_id = p_b_res.json()["id"]

    enc_b_res = await client.post(
        "/api/v1/patients/encounters",
        headers=headers_b,
        json={
            "patient_id": pat_b_id,
            "chief_complaint": "Acute appendicitis in Tenant B",
            "encounter_type": "EMERGENCY",
            "current_department_id": "DEP-RIVAL"
        }
    )
    assert enc_b_res.status_code == 201
    enc_b_id = enc_b_res.json()["id"]

    # 3. Query active encounters as Tenant A
    active_a_res = await client.get("/api/v1/patients/encounters/active", headers=headers_a)
    assert active_a_res.status_code == 200
    encs_a = active_a_res.json()
    ids_a = [e["id"] for e in encs_a]
    assert enc_a_id in ids_a
    assert enc_b_id not in ids_a

    # 4. Query active encounters as Tenant B
    active_b_res = await client.get("/api/v1/patients/encounters/active", headers=headers_b)
    assert active_b_res.status_code == 200
    encs_b = active_b_res.json()
    ids_b = [e["id"] for e in encs_b]
    assert enc_b_id in ids_b
    assert enc_a_id not in ids_b


@pytest.mark.asyncio
async def test_cross_tenant_staff_status_mutation_rejected(client: AsyncClient, test_db):
    """
    Phase 4: Verify that attempting to mutate the status of a staff member belonging to another tenant
    returns 404 Not Found, produces NO database modification, and creates NO successful audit entry.
    """
    await seed_tenant_b(test_db)

    # DOC-001 belongs to HOSP-DEFAULT with status AVAILABLE
    async with test_db() as session:
        orig_doc = await session.get(Staff, "DOC-001")
        assert orig_doc.status == "AVAILABLE"
        orig_status = orig_doc.status

    # Caller is administrator in HOSP-RIVAL (Tenant B)
    headers_rival_admin = {"Authorization": f"Bearer {create_access_token({'sub': 'ADM-RIVAL-01', 'role': 'ADMINISTRATOR', 'tenant_id': 'HOSP-RIVAL'})}"}

    # Attempt to change DOC-001 status
    res = await client.patch(
        "/api/v1/staff/DOC-001/status",
        headers=headers_rival_admin,
        json={"status": "ON_LEAVE", "reason": "Hostile takeover attempt"}
    )
    assert res.status_code == 404

    # Verify no database mutation occurred
    async with test_db() as session:
        check_doc = await session.get(Staff, "DOC-001")
        assert check_doc.status == orig_status

        # Verify no audit log entry was created for this change
        audit_res = await session.execute(
            select(AuditLog).where(
                AuditLog.entity_id == "DOC-001",
                AuditLog.change_reason == "Hostile takeover attempt"
            )
        )
        assert audit_res.scalars().first() is None


@pytest.mark.asyncio
async def test_tenant_context_cannot_be_spoofed_in_request(client: AsyncClient):
    """Verify that client cannot spoof tenant ownership by providing arbitrary tenant payloads."""
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


@pytest.mark.asyncio
async def test_multi_tenant_department_code_uniqueness(test_db):
    """
    Fix 2 & 3: Test that two different tenants can create departments with the same code,
    but a single tenant cannot create duplicate department codes.
    Tenant A (HOSP-DEFAULT) + 'ER' -> allowed (seeded)
    Tenant B (HOSP-RIVAL) + 'ER' -> allowed
    Tenant A (HOSP-DEFAULT) + 'ER' duplicate -> rejected by composite uniqueness constraint
    """
    from sqlalchemy.exc import IntegrityError

    async with test_db() as session:
        # Tenant B creates department with code 'ER' -> must succeed
        t_b = await session.get(Tenant, "HOSP-RIVAL")
        if not t_b:
            t_b = Tenant(id="HOSP-RIVAL", name="Rival Facility", code="RIV", is_active=True)
            session.add(t_b)
            await session.commit()

        dept_b = Department(
            id="DEP-RIV-ER",
            tenant_id="HOSP-RIVAL",
            name="Rival Emergency Unit",
            code="ER"
        )
        session.add(dept_b)
        await session.commit()
        await session.refresh(dept_b)
        assert dept_b.code == "ER"
        assert dept_b.tenant_id == "HOSP-RIVAL"

        # Tenant A attempts to create a duplicate department with code 'ER' -> must be rejected
        dept_a_dup = Department(
            id="DEP-DUP-ER",
            tenant_id="HOSP-DEFAULT",
            name="Duplicate Emergency Room",
            code="ER"
        )
        session.add(dept_a_dup)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
