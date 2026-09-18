"""
Unit and integration tests verifying tenant isolation for operational resources:
- Bed Management (Beds, Departments)
- Equipment
- Staff
- Emergency Events
- BedManagementAgent (ICU & Bidirectional Discharge Step-down proposals)
- Hospital Dashboard
"""

import pytest
from sqlalchemy import select
from app.models.tenant import Tenant
from app.models.department import Department
from app.models.bed import Bed
from app.models.staff import Staff
from app.models.equipment import Equipment
from app.models.emergency import EmergencyEvent
from app.models.patient import Patient, Encounter
from app.services.agent_orchestrator import BedManagerAgent, BedManagementAgent
from app.services.bed_service import BedService
from app.services.equipment_service import EquipmentService
from app.services.staff_service import StaffService
from app.services.emergency_service import EmergencyService
from app.services.dashboard_service import DashboardService


async def setup_multi_tenant_resources(session):
    """
    Creates two distinct tenants with isolated operational resources:
    - TENANT-A:
        - Department: ICU-A (0 beds available, 2 total), ED-A (1 bed available, 2 total), GENERAL-A (0 beds available, 2 total)
        - Equipment: EQ-A1 (IN_USE)
        - Staff: STAFF-A1 (ON_DUTY, ICU)
        - Emergency: EM-A1 (FIRE_HAZARD, ACTIVE)
    - TENANT-B:
        - Department: ICU-B (2 beds available, 2 total), GENERAL-B (3 beds available, 5 total)
        - Equipment: EQ-B1 (AVAILABLE)
        - Staff: STAFF-B1 (ON_DUTY, ICU)
        - Emergency: EM-B1 (INFRASTRUCTURE_FAILURE, ACTIVE)
    """
    # 1. Create Tenants with mandatory code field
    tenant_a = Tenant(id="TENANT-A", name="Hospital A", code="HOSP-A", is_active=True)
    tenant_b = Tenant(id="TENANT-B", name="Hospital B", code="HOSP-B", is_active=True)
    session.add_all([tenant_a, tenant_b])
    await session.flush()

    # 2. Departments with unique codes per department
    dept_icu_a = Department(id="DEPT-ICU-A", tenant_id="TENANT-A", name="ICU A", code="ICU-A", total_beds=2)
    dept_ed_a = Department(id="DEPT-ED-A", tenant_id="TENANT-A", name="ED A", code="ED-A", total_beds=2)
    dept_gen_a = Department(id="DEPT-GEN-A", tenant_id="TENANT-A", name="General A", code="GEN-A", total_beds=2)
    
    dept_icu_b = Department(id="DEPT-ICU-B", tenant_id="TENANT-B", name="ICU B", code="ICU-B", total_beds=2)
    dept_gen_b = Department(id="DEPT-GEN-B", tenant_id="TENANT-B", name="General B", code="GEN-B", total_beds=5)
    
    session.add_all([dept_icu_a, dept_ed_a, dept_gen_a, dept_icu_b, dept_gen_b])
    await session.flush()

    # 3. Beds for Tenant A
    bed_icu_a1 = Bed(id="BED-ICU-A1", department_id="DEPT-ICU-A", bed_type="ICU", status="OCCUPIED")
    bed_icu_a2 = Bed(id="BED-ICU-A2", department_id="DEPT-ICU-A", bed_type="ICU", status="OCCUPIED")
    bed_ed_a1 = Bed(id="BED-ED-A1", department_id="DEPT-ED-A", bed_type="EMERGENCY", status="AVAILABLE")
    bed_ed_a2 = Bed(id="BED-ED-A2", department_id="DEPT-ED-A", bed_type="EMERGENCY", status="OCCUPIED")
    bed_gen_a1 = Bed(id="BED-GEN-A1", department_id="DEPT-GEN-A", bed_type="GENERAL", status="OCCUPIED")
    bed_gen_a2 = Bed(id="BED-GEN-A2", department_id="DEPT-GEN-A", bed_type="GENERAL", status="OCCUPIED")

    # 4. Beds for Tenant B
    bed_icu_b1 = Bed(id="BED-ICU-B1", department_id="DEPT-ICU-B", bed_type="ICU", status="AVAILABLE")
    bed_icu_b2 = Bed(id="BED-ICU-B2", department_id="DEPT-ICU-B", bed_type="ICU", status="AVAILABLE")
    bed_gen_b1 = Bed(id="BED-GEN-B1", department_id="DEPT-GEN-B", bed_type="GENERAL", status="AVAILABLE")
    bed_gen_b2 = Bed(id="BED-GEN-B2", department_id="DEPT-GEN-B", bed_type="GENERAL", status="AVAILABLE")
    bed_gen_b3 = Bed(id="BED-GEN-B3", department_id="DEPT-GEN-B", bed_type="GENERAL", status="AVAILABLE")

    session.add_all([
        bed_icu_a1, bed_icu_a2, bed_ed_a1, bed_ed_a2, bed_gen_a1, bed_gen_a2,
        bed_icu_b1, bed_icu_b2, bed_gen_b1, bed_gen_b2, bed_gen_b3
    ])

    # 5. Staff
    staff_a = Staff(id="STAFF-A1", tenant_id="TENANT-A", first_name="Alice", last_name="Doc", role="DOCTOR", department_id="DEPT-ICU-A", status="AVAILABLE", current_workload=2, max_workload=5)
    staff_b = Staff(id="STAFF-B1", tenant_id="TENANT-B", first_name="Bob", last_name="Doc", role="DOCTOR", department_id="DEPT-ICU-B", status="AVAILABLE", current_workload=1, max_workload=5)
    session.add_all([staff_a, staff_b])

    # 6. Equipment
    eq_a = Equipment(id="EQ-A1", name="Ventilator A", resource_type="VENTILATOR", department_id="DEPT-ICU-A", status="IN_USE")
    eq_b = Equipment(id="EQ-B1", name="Ventilator B", resource_type="VENTILATOR", department_id="DEPT-ICU-B", status="AVAILABLE")
    session.add_all([eq_a, eq_b])

    # 7. Emergency Events
    em_a = EmergencyEvent(id="EM-A1", tenant_id="TENANT-A", event_type="FIRE_HAZARD", severity="HIGH", description="Fire alarm in Wing A", affected_departments=["DEPT-ICU-A"], expected_patient_surge=4, declared_by="STAFF-A1", status="ACTIVE")
    em_b = EmergencyEvent(id="EM-B1", tenant_id="TENANT-B", event_type="INFRASTRUCTURE_FAILURE", severity="HIGH", description="Power backup failure in Wing B", affected_departments=["DEPT-ICU-B"], expected_patient_surge=6, declared_by="STAFF-B1", status="ACTIVE")
    session.add_all([em_a, em_b])

    await session.commit()


@pytest.mark.asyncio
async def test_bed_management_agent_tenant_isolation(test_db):
    """
    Ensure BedManagementAgent.evaluate() only counts and returns beds from the requested tenant.
    """
    async with test_db() as session:
        await setup_multi_tenant_resources(session)

        # Create test patient and encounter for Tenant A
        pat_a = Patient(
            id="PAT-ISO-A",
            tenant_id="TENANT-A",
            first_name="John",
            last_name="Doe",
            age=45,
            gender="M",
            blood_group="O+",
            contact_phone="1234567890",
            emergency_contact="1234567890"
        )
        enc_a = Encounter(
            id="ENC-ISO-A",
            patient_id="PAT-ISO-A",
            current_department_id="DEPT-ICU-A",
            esi_level=1,
            encounter_type="EMERGENCY",
            chief_complaint="Severe acute chest pain radiating to left arm"
        )
        # Create test patient and encounter for Tenant B
        pat_b = Patient(
            id="PAT-ISO-B",
            tenant_id="TENANT-B",
            first_name="Jane",
            last_name="Smith",
            age=50,
            gender="F",
            blood_group="A+",
            contact_phone="9876543210",
            emergency_contact="9876543210"
        )
        enc_b = Encounter(
            id="ENC-ISO-B",
            patient_id="PAT-ISO-B",
            current_department_id="DEPT-ICU-B",
            esi_level=1,
            encounter_type="EMERGENCY",
            chief_complaint="Acute severe respiratory distress"
        )
        session.add_all([pat_a, enc_a, pat_b, enc_b])
        await session.commit()

        bed_agent = BedManagerAgent(session)
        
        # Evaluate for Tenant A in ICU (where Tenant A has 0 available beds, but Tenant B has 2)
        triage_out_icu = {
            "esi_level": 1,
            "recommended_care_level": "ICU",
            "requires_isolation": False,
            "requires_telemetry": True,
            "priority_level": "CRITICAL"
        }

        dec_a = await bed_agent.evaluate(
            triage_output=triage_out_icu,
            encounter=enc_a,
            tenant_id="TENANT-A"
        )
        assert dec_a["status"] == "COMPLETED"
        assert dec_a["recommended_bed_id"] not in ["BED-ICU-B1", "BED-ICU-B2"]
        assert dec_a["recommended_department_id"] != "DEPT-ICU-B"
        assert dec_a["feasibility"] in ["CONSTRAINED", "UNAVAILABLE"]

        # Evaluate for Tenant B in ICU (where Tenant B has 2 available beds)
        dec_b = await bed_agent.evaluate(
            triage_output=triage_out_icu,
            encounter=enc_b,
            tenant_id="TENANT-B"
        )
        assert dec_b["status"] == "COMPLETED"
        assert dec_b["recommended_bed_id"] in ["BED-ICU-B1", "BED-ICU-B2"]
        assert dec_b["recommended_department_id"] == "DEPT-ICU-B"
        assert dec_b["feasibility"] == "FEASIBLE"


@pytest.mark.asyncio
async def test_bed_management_agent_discharge_stepdown_cross_tenant_isolation(test_db):
    """
    Ensure BedManagerAgent.evaluate_discharge_stepdown_proposal() never counter-proposes or allocates
    a bed from Tenant B when evaluating for Tenant A, even if Tenant A target and alternative wards are full.
    """
    async with test_db() as session:
        await setup_multi_tenant_resources(session)

        bed_agent = BedManagerAgent(session)

        # Step-down proposal for Tenant A into General Ward (General Ward A is full; General Ward B has 3 available beds)
        result_a = await bed_agent.evaluate_discharge_stepdown_proposal(
            proposal={
                "transition_type": "STEP_DOWN_TRANSFER",
                "proposed_destination": "DEPT-GEN-A",
                "requires_isolation": False,
                "requires_telemetry": False
            },
            tenant_id="TENANT-A"
        )
        # Since General Ward A has 0 available beds and ICU A is full, it must NOT pick General Ward B beds
        if result_a.get("decision") == "COUNTER_PROPOSAL":
            assert not str(result_a.get("counter_bed_id", "")).startswith("BED-GEN-B")
            assert not str(result_a.get("counter_bed_id", "")).startswith("BED-ICU-B")
            assert result_a.get("counter_department_id") != "DEPT-GEN-B"
        else:
            assert result_a["decision"] in ["REJECT", "ESCALATION"]


@pytest.mark.asyncio
async def test_bed_service_and_equipment_service_isolation(test_db):
    """
    Test BedService and EquipmentService tenant isolation.
    """
    async with test_db() as session:
        await setup_multi_tenant_resources(session)

        bed_service = BedService(session)
        equipment_service = EquipmentService(session)

        # BedService list_departments
        depts_a = await bed_service.list_departments(tenant_id="TENANT-A")
        assert len(depts_a) == 3
        assert all(d.tenant_id == "TENANT-A" for d in depts_a)

        depts_b = await bed_service.list_departments(tenant_id="TENANT-B")
        assert len(depts_b) == 2
        assert all(d.tenant_id == "TENANT-B" for d in depts_b)

        # BedService list_beds
        beds_a = await bed_service.list_beds(tenant_id="TENANT-A")
        assert len(beds_a) == 6
        for b in beds_a:
            assert b.id.startswith("BED-ICU-A") or b.id.startswith("BED-ED-A") or b.id.startswith("BED-GEN-A")

        beds_b = await bed_service.list_beds(tenant_id="TENANT-B")
        assert len(beds_b) == 5
        for b in beds_b:
            assert b.id.startswith("BED-ICU-B") or b.id.startswith("BED-GEN-B")

        # EquipmentService list_equipment
        eqs_a = await equipment_service.list_equipment(tenant_id="TENANT-A")
        assert len(eqs_a) == 1
        assert eqs_a[0].id == "EQ-A1"

        eqs_b = await equipment_service.list_equipment(tenant_id="TENANT-B")
        assert len(eqs_b) == 1
        assert eqs_b[0].id == "EQ-B1"


@pytest.mark.asyncio
async def test_staff_and_emergency_service_isolation(test_db):
    """
    Test StaffService and EmergencyService tenant isolation.
    """
    async with test_db() as session:
        await setup_multi_tenant_resources(session)

        staff_service = StaffService(session)
        emergency_service = EmergencyService(session)

        staff_a = await staff_service.list_staff(tenant_id="TENANT-A")
        assert len(staff_a) == 1
        assert staff_a[0].id == "STAFF-A1"

        staff_b = await staff_service.list_staff(tenant_id="TENANT-B")
        assert len(staff_b) == 1
        assert staff_b[0].id == "STAFF-B1"

        emergencies_a = await emergency_service.list_active_emergencies(tenant_id="TENANT-A")
        assert len(emergencies_a) == 1
        assert emergencies_a[0].id == "EM-A1"

        emergencies_b = await emergency_service.list_active_emergencies(tenant_id="TENANT-B")
        assert len(emergencies_b) == 1
        assert emergencies_b[0].id == "EM-B1"


@pytest.mark.asyncio
async def test_dashboard_service_isolation(test_db):
    """
    Test DashboardService isolation across tenants.
    """
    async with test_db() as session:
        await setup_multi_tenant_resources(session)

        dashboard_service = DashboardService(session)

        state_a = await dashboard_service.get_hospital_state(tenant_id="TENANT-A")
        assert state_a["beds"]["total"] == 6
        assert state_a["beds"]["AVAILABLE"] == 1  # only BED-ED-A1 is AVAILABLE
        assert state_a["active_emergencies"] == 1

        state_b = await dashboard_service.get_hospital_state(tenant_id="TENANT-B")
        assert state_b["beds"]["total"] == 5  # 2 ICU + 3 General
        assert state_b["beds"]["AVAILABLE"] == 5  # 2 ICU + 3 General
        assert state_b["active_emergencies"] == 1
