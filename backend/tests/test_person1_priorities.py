import pytest
from httpx import AsyncClient

from app.auth.security import decode_access_token
from app.models.tenant import Tenant
from app.models.department import Department
from app.models.staff import Staff
from app.models.bed import Bed
from app.models.patient import Encounter
from app.models.workflow import Transfer, Discharge


async def seed_secondary_tenant(session_factory):
    """Seed secondary tenant and genuine staff members for tenant-isolation testing."""
    async with session_factory() as session:
        t = await session.get(Tenant, "HOSP-SECONDARY")
        if not t:
            t = Tenant(id="HOSP-SECONDARY", name="Secondary Hospital", code="SEC", is_active=True)
            session.add(t)

        d = await session.get(Department, "DEP-ER-SEC")
        if not d:
            d = Department(id="DEP-ER-SEC", tenant_id="HOSP-SECONDARY", name="Secondary Emergency", code="ER")
            session.add(d)

        s1 = await session.get(Staff, "DOC-TENANT-SEC")
        if not s1:
            s1 = Staff(
                id="DOC-TENANT-SEC",
                tenant_id="HOSP-SECONDARY",
                first_name="Kavita",
                last_name="Patel",
                role="DOCTOR",
                department_id="DEP-ER-SEC",
                specialization="Emergency",
                password_hash="$2b$12$OFGNkctqGDUtRAacUe4HBur2X0O74MrDkNJdQH8OqfANlyI5b0t.C",
                status="AVAILABLE"
            )
            session.add(s1)

        s2 = await session.get(Staff, "DOC-TENANT-B")
        if not s2:
            s2 = Staff(
                id="DOC-TENANT-B",
                tenant_id="HOSP-SECONDARY",
                first_name="Arun",
                last_name="Verma",
                role="DOCTOR",
                department_id="DEP-ER-SEC",
                specialization="Emergency",
                status="AVAILABLE"
            )
            session.add(s2)

        s3 = await session.get(Staff, "NUR-TENANT-SEC")
        if not s3:
            s3 = Staff(
                id="NUR-TENANT-SEC",
                tenant_id="HOSP-SECONDARY",
                first_name="Rohan",
                last_name="Gupta",
                role="NURSE",
                department_id="DEP-ER-SEC",
                specialization="Triage",
                status="AVAILABLE",
                current_workload=0,
                max_workload=5
            )
            session.add(s3)

        s4 = await session.get(Staff, "ADM-TENANT-SEC")
        if not s4:
            s4 = Staff(
                id="ADM-TENANT-SEC",
                tenant_id="HOSP-SECONDARY",
                first_name="Meera",
                last_name="Nair",
                role="ADMINISTRATOR",
                department_id="DEP-ER-SEC",
                specialization="Administration",
                status="AVAILABLE",
                current_workload=0,
                max_workload=50
            )
            session.add(s4)

        s5 = await session.get(Staff, "ADM-SEC-APPR")
        if not s5:
            s5 = Staff(
                id="ADM-SEC-APPR",
                tenant_id="HOSP-SECONDARY",
                first_name="Suresh",
                last_name="Menon",
                role="ADMINISTRATOR",
                department_id="DEP-ER-SEC",
                specialization="Administration",
                status="AVAILABLE",
                current_workload=0,
                max_workload=50
            )
            session.add(s5)

        await session.commit()


@pytest.mark.asyncio
async def test_jwt_embeds_actual_tenant_id(client: AsyncClient, test_db):
    """P0: Ensure JWT access token contains the staff member's actual tenant_id, not hardcoded HOSP-DEFAULT."""
    await seed_secondary_tenant(test_db)

    # Login and verify returned tenant_id and decoded token payload
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"staff_id": "DOC-TENANT-SEC", "password": "hospital@123"}
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["tenant_id"] == "HOSP-SECONDARY"

    token = login_data["access_token"]
    payload = decode_access_token(token)
    assert payload is not None
    assert payload.get("tenant_id") == "HOSP-SECONDARY"


@pytest.mark.asyncio
async def test_active_encounters_tenant_scoped(client: AsyncClient, make_auth_headers, test_db):
    """P0: Ensure /patients/encounters/active is isolated per tenant and does not leak cross-tenant encounters."""
    await seed_secondary_tenant(test_db)

    headers_tenant_a = make_auth_headers(staff_id="DOC-001", role="DOCTOR", tenant_id="HOSP-DEFAULT")
    headers_tenant_b = make_auth_headers(staff_id="DOC-TENANT-B", role="DOCTOR", tenant_id="HOSP-SECONDARY")

    # 1. Register patient in Tenant A and Tenant B
    p_a_res = await client.post(
        "/api/v1/patients",
        headers=headers_tenant_a,
        json={
            "first_name": "Alpha",
            "last_name": "Patient",
            "age": 30,
            "gender": "M",
            "blood_group": "A+",
            "contact_phone": "+919100000001",
            "emergency_contact": "+919100000002"
        }
    )
    assert p_a_res.status_code == 201
    pat_a_id = p_a_res.json()["id"]

    p_b_res = await client.post(
        "/api/v1/patients",
        headers=headers_tenant_b,
        json={
            "first_name": "Beta",
            "last_name": "Patient",
            "age": 40,
            "gender": "F",
            "blood_group": "B+",
            "contact_phone": "+919200000001",
            "emergency_contact": "+919200000002"
        }
    )
    assert p_b_res.status_code == 201
    pat_b_id = p_b_res.json()["id"]

    # 2. Start encounter for each
    enc_a_res = await client.post(
        "/api/v1/patients/encounters",
        headers=headers_tenant_a,
        json={
            "patient_id": pat_a_id,
            "current_department_id": "DEP-ER",
            "chief_complaint": "Chest discomfort",
            "encounter_type": "EMERGENCY"
        }
    )
    assert enc_a_res.status_code == 201
    enc_a_id = enc_a_res.json()["id"]

    enc_b_res = await client.post(
        "/api/v1/patients/encounters",
        headers=headers_tenant_b,
        json={
            "patient_id": pat_b_id,
            "current_department_id": "DEP-ER-SEC",
            "chief_complaint": "Acute abdominal pain",
            "encounter_type": "EMERGENCY"
        }
    )
    assert enc_b_res.status_code == 201
    enc_b_id = enc_b_res.json()["id"]

    # 3. Tenant A queries active encounters
    active_a = await client.get("/api/v1/patients/encounters/active", headers=headers_tenant_a)
    assert active_a.status_code == 200
    ids_a = [e["id"] for e in active_a.json()]
    assert enc_a_id in ids_a
    assert enc_b_id not in ids_a

    # 4. Tenant B queries active encounters
    active_b = await client.get("/api/v1/patients/encounters/active", headers=headers_tenant_b)
    assert active_b.status_code == 200
    ids_b = [e["id"] for e in active_b.json()]
    assert enc_b_id in ids_b
    assert enc_a_id not in ids_b

    # 5. Cross-tenant encounter access returns 404
    cross_res = await client.get(f"/api/v1/patients/encounters/{enc_b_id}", headers=headers_tenant_a)
    assert cross_res.status_code == 404


@pytest.mark.asyncio
async def test_staff_workload_tenant_scoped(client: AsyncClient, make_auth_headers, test_db):
    """P0: Ensure adjusting staff workload is scoped to tenant and rejects cross-tenant modification."""
    await seed_secondary_tenant(test_db)

    admin_a = make_auth_headers(staff_id="ADM-001", role="ADMINISTRATOR", tenant_id="HOSP-DEFAULT")
    admin_b = make_auth_headers(staff_id="ADM-TENANT-SEC", role="ADMINISTRATOR", tenant_id="HOSP-SECONDARY")

    # Admin from HOSP-DEFAULT tries to adjust staff in HOSP-SECONDARY -> 404 Not Found
    cross_adj = await client.patch(
        "/api/v1/staff/NUR-TENANT-SEC/workload?delta=1",
        headers=admin_a
    )
    assert cross_adj.status_code == 404

    # Admin from HOSP-SECONDARY adjusts staff in HOSP-SECONDARY -> 200 OK
    same_adj = await client.patch(
        "/api/v1/staff/NUR-TENANT-SEC/workload?delta=1",
        headers=admin_b
    )
    assert same_adj.status_code == 200
    assert same_adj.json()["current_workload"] == 1


@pytest.mark.asyncio
async def test_predictions_run_endpoint(auth_client: AsyncClient):
    """P1: Test POST /predictions/run triggers inference contract and records output."""
    payload = {
        "prediction_type": "ICU_DEMAND",
        "forecast_horizon_hours": 4,
        "department_id": "DEP-ICU"
    }
    res = await auth_client.post("/api/v1/predictions/run", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["prediction_type"] == "ICU_DEMAND"
    assert "prediction_output" in data
    assert data["confidence_score"] > 0
    assert "id" in data


@pytest.mark.asyncio
async def test_emergency_crew_run_and_listing(admin_client: AsyncClient):
    """P1: Test POST /emergencies/{id}/run-crew and GET /emergencies/crew-runs."""
    # 1. Declare emergency
    dec_res = await admin_client.post(
        "/api/v1/emergencies/declare",
        json={
            "event_type": "MASS_CASUALTY",
            "severity": "CRITICAL",
            "description": "Explosion incident",
            "affected_departments": ["DEP-ER", "DEP-ICU"],
            "expected_patient_surge": 15
        }
    )
    assert dec_res.status_code == 201
    emg_id = dec_res.json()["id"]

    # 2. Trigger crew run
    crew_res = await admin_client.post(f"/api/v1/emergencies/{emg_id}/run-crew")
    assert crew_res.status_code == 200
    crew_data = crew_res.json()
    assert crew_data["crew_name"] == "EmergencySurgeCrew"
    assert crew_data["status"] == "COMPLETED"
    assert crew_data["trigger_event"] == emg_id
    assert "Triage Lead" in crew_data["output_summary"]

    # 3. List crew runs
    list_res = await admin_client.get("/api/v1/emergencies/crew-runs")
    assert list_res.status_code == 200
    runs = list_res.json()
    assert len(runs) >= 1
    run_ids = [r["id"] for r in runs]
    assert crew_data["id"] in run_ids


@pytest.mark.asyncio
async def test_approvals_tenant_isolation(client: AsyncClient, make_auth_headers, test_db):
    """P1: Ensure pending approvals are filtered by tenant_id."""
    await seed_secondary_tenant(test_db)

    headers_a = make_auth_headers(staff_id="ADM-001", role="ADMINISTRATOR", tenant_id="HOSP-DEFAULT")
    headers_b = make_auth_headers(staff_id="ADM-SEC-APPR", role="ADMINISTRATOR", tenant_id="HOSP-SECONDARY")

    # In HOSP-DEFAULT, list pending approvals
    res_a = await client.get("/api/v1/approvals/pending", headers=headers_a)
    assert res_a.status_code == 200
    assert isinstance(res_a.json(), list)

    # In HOSP-SECONDARY (no items created yet for it), list pending approvals returns empty list
    res_b = await client.get("/api/v1/approvals/pending", headers=headers_b)
    assert res_b.status_code == 200
    assert len(res_b.json()) == 0


@pytest.mark.asyncio
async def test_workflows_and_tasks_pagination(auth_client: AsyncClient):
    """P2: Ensure pagination query parameters (skip, limit) work on workflows/instances and workflows/tasks."""
    # List instances with limit=1
    inst_res = await auth_client.get("/api/v1/workflows/instances?skip=0&limit=1")
    assert inst_res.status_code == 200
    assert len(inst_res.json()) <= 1

    # List tasks with limit=1
    task_res = await auth_client.get("/api/v1/workflows/tasks?skip=0&limit=1")
    assert task_res.status_code == 200
    assert len(task_res.json()) <= 1


def test_composite_indexes_and_foreign_keys():
    """P2: Verify composite indexes and foreign keys exist in ORM schema."""
    # 1. Bed composite index
    bed_indexes = {idx.name for idx in Bed.__table__.indexes}
    assert "ix_beds_dept_status" in bed_indexes

    # 2. Encounter composite index
    encounter_indexes = {idx.name for idx in Encounter.__table__.indexes}
    assert "ix_encounters_status_arrival" in encounter_indexes

    # 3. Foreign keys on Encounter, Transfer, Discharge
    encounter_fks = {fk.target_fullname for fk in Encounter.__table__.foreign_keys}
    assert "departments.id" in encounter_fks

    transfer_fks = {fk.target_fullname for fk in Transfer.__table__.foreign_keys}
    assert "departments.id" in transfer_fks
    assert "beds.id" in transfer_fks

    discharge_fks = {fk.target_fullname for fk in Discharge.__table__.foreign_keys}
    assert "staff.id" in discharge_fks


@pytest.mark.asyncio
async def test_approvals_get_by_id_and_tenant(client: AsyncClient, make_auth_headers, test_db):
    """P1: Verify GET /approvals/{id} fetches approval details within tenant boundary and rejects cross-tenant access."""
    await seed_secondary_tenant(test_db)
    admin_a = make_auth_headers(staff_id="ADM-001", role="ADMINISTRATOR", tenant_id="HOSP-DEFAULT")
    admin_b = make_auth_headers(staff_id="ADM-SEC-APPR", role="ADMINISTRATOR", tenant_id="HOSP-SECONDARY")

    # List pending in default tenant to get an approval id if any exists
    res_list = await client.get("/api/v1/approvals/pending", headers=admin_a)
    assert res_list.status_code == 200
    items = res_list.json()
    if items:
        target_id = items[0]["id"]
        # Same tenant can fetch it
        res_get = await client.get(f"/api/v1/approvals/{target_id}", headers=admin_a)
        assert res_get.status_code == 200
        assert res_get.json()["id"] == target_id

        # Cross tenant receives 404
        cross_res = await client.get(f"/api/v1/approvals/{target_id}", headers=admin_b)
        assert cross_res.status_code == 404


@pytest.mark.asyncio
async def test_clinical_task_lifecycle_endpoints(auth_client: AsyncClient, client: AsyncClient, make_auth_headers):
    """P1: Verify creating and updating clinical workflow tasks via REST endpoints."""
    headers = make_auth_headers(staff_id="DOC-001", role="DOCTOR")

    # 1. Create Patient & Encounter
    p_res = await client.post("/api/v1/patients", headers=headers, json={
        "first_name": "Task", "last_name": "Patient", "age": 35, "gender": "F",
        "blood_group": "A+", "contact_phone": "+919811111111", "emergency_contact": "+919811111112"
    })
    assert p_res.status_code == 201
    pat_id = p_res.json()["id"]

    e_res = await client.post("/api/v1/patients/encounters", headers=headers, json={
        "patient_id": pat_id, "current_department_id": "DEP-ER", "chief_complaint": "Acute migraine", "encounter_type": "EMERGENCY"
    })
    assert e_res.status_code == 201
    enc_id = e_res.json()["id"]

    # 2. Create Task
    task_res = await client.post("/api/v1/workflows/tasks", headers=headers, json={
        "encounter_id": enc_id, "patient_id": pat_id, "title": "Administer IV Analgesic",
        "task_type": "TRIAGE", "priority": 1, "description": "10mg Metoclopramide + 500mg Paracetamol"
    })
    assert task_res.status_code == 201
    task_data = task_res.json()
    task_id = task_data["id"]
    assert task_data["status"] == "PENDING"
    assert task_data["title"] == "Administer IV Analgesic"

    # 3. Advance task to IN_PROGRESS
    up1 = await client.patch(f"/api/v1/workflows/tasks/{task_id}", headers=headers, json={"status": "IN_PROGRESS"})
    assert up1.status_code == 200
    assert up1.json()["status"] == "IN_PROGRESS"

    # 4. Complete task
    up2 = await client.patch(f"/api/v1/workflows/tasks/{task_id}", headers=headers, json={"status": "COMPLETED"})
    assert up2.status_code == 200
    assert up2.json()["status"] == "COMPLETED"
    assert up2.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_staff_search_endpoint_and_tenant_isolation(client: AsyncClient, make_auth_headers, test_db):
    """P1: Verify GET /staff?search= query operates within tenant boundaries."""
    await seed_secondary_tenant(test_db)
    admin_a = make_auth_headers(staff_id="ADM-001", role="ADMINISTRATOR", tenant_id="HOSP-DEFAULT")
    admin_b = make_auth_headers(staff_id="ADM-TENANT-SEC", role="ADMINISTRATOR", tenant_id="HOSP-SECONDARY")

    # Search for Kavita in HOSP-SECONDARY (should be found)
    search_b = await client.get("/api/v1/staff?search=Kavita", headers=admin_b)
    assert search_b.status_code == 200
    b_ids = [s["id"] for s in search_b.json()]
    assert "DOC-TENANT-SEC" in b_ids

    # Search for Kavita in HOSP-DEFAULT (should NOT be found due to tenant isolation)
    search_a = await client.get("/api/v1/staff?search=Kavita", headers=admin_a)
    assert search_a.status_code == 200
    a_ids = [s["id"] for s in search_a.json()]
    assert "DOC-TENANT-SEC" not in a_ids
