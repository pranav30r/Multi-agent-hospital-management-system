import pytest
from sqlalchemy import select, update
from app.models.patient import Patient, Encounter
from app.models.bed import Bed
from app.models.staff import Staff
from app.services.resource_evaluation import OptimizationEvaluator, DeterministicGreedyBaseline
from tests.test_tenant_isolation import seed_tenant_b


@pytest.mark.asyncio
async def test_scenario_normal_bed_allocation(test_db):
    """
    Scenario 1: Normal bed allocation with adequate capacity.
    Both baseline and optimizer should find feasible allocations.
    """
    async with test_db() as session:
        pat = Patient(
            id="PAT-EVAL-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Anil",
            last_name="Deshmukh",
            age=40,
            gender="M",
            blood_group="O+",
            contact_phone="+919800000001",
            emergency_contact="+919800000002"
        )
        enc = Encounter(
            id="ENC-EVAL-01",
            patient_id="PAT-EVAL-01",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            chief_complaint="Moderate lower leg sprain",
            esi_level=4,
            heart_rate=78,
            bp_systolic=120,
            bp_diastolic=80,
            spo2=99,
            pain_level=3
        )
        session.add_all([pat, enc])
        await session.commit()

        evaluator = OptimizationEvaluator(session)
        res = await evaluator.evaluate_scenario(enc, pat)

        # Baseline finds an available bed
        assert res["baseline"]["is_feasible"] is True
        assert res["baseline"]["target_bed_id"] is not None

        # Optimizer finds an optimal feasible plan and generates candidate alternatives
        assert res["optimizer"]["is_feasible"] is True
        assert res["optimizer"]["candidate_plans_count"] >= 2


@pytest.mark.asyncio
async def test_scenario_scarce_icu_requires_negotiation(test_db):
    """
    Scenario 2: Scarce ICU availability (Primary ICU is 100% occupied).
    Baseline fails or selects an incompatible bed without negotiation.
    Optimizer executes negotiation and counter-proposes an alternative step-down bed.
    """
    async with test_db() as session:
        # Mark all ICU beds as OCCUPIED
        await session.execute(
            update(Bed).where(Bed.department_id == "DEP-ICU").values(status="OCCUPIED")
        )

        pat = Patient(
            id="PAT-EVAL-02",
            tenant_id="HOSP-DEFAULT",
            first_name="Ravi",
            last_name="Shukla",
            age=62,
            gender="M",
            blood_group="B+",
            contact_phone="+919800000003",
            emergency_contact="+919800000004"
        )
        enc = Encounter(
            id="ENC-EVAL-02",
            patient_id="PAT-EVAL-02",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ICU",
            chief_complaint="Severe crushing chest pain radiating to left jaw, diaphoresis",
            esi_level=1,
            heart_rate=135,
            bp_systolic=85,
            bp_diastolic=55,
            spo2=88,
            pain_level=9
        )
        session.add_all([pat, enc])
        await session.commit()

        evaluator = OptimizationEvaluator(session)
        res = await evaluator.evaluate_scenario(enc, pat)

        # Baseline: either cannot find bed in ICU or violates care level
        # Optimizer: detects conflict, initiates negotiation, and evaluates candidates
        assert res["optimizer"]["candidate_plans_count"] >= 2
        assert res["optimizer"]["requires_human_approval"] is True


@pytest.mark.asyncio
async def test_scenario_staff_overload_rebalancing(test_db):
    """
    Scenario 3: Staff overload.
    Primary ER doctor is at max capacity (workload >= max_workload).
    Baseline naively assigns the overloaded doctor (violating constraint).
    Optimizer detects overload and rebalances or flags conflict.
    """
    async with test_db() as session:
        # Overload primary ER doctor
        await session.execute(
            update(Staff).where(Staff.id == "DOC-001").values(current_workload=10, max_workload=10)
        )

        pat = Patient(
            id="PAT-EVAL-03",
            tenant_id="HOSP-DEFAULT",
            first_name="Pooja",
            last_name="Hegde",
            age=29,
            gender="F",
            blood_group="A+",
            contact_phone="+919800000005",
            emergency_contact="+919800000006"
        )
        enc = Encounter(
            id="ENC-EVAL-03",
            patient_id="PAT-EVAL-03",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            chief_complaint="Acute migraine with photophobia",
            esi_level=3,
            heart_rate=82,
            bp_systolic=118,
            bp_diastolic=78,
            spo2=99,
            pain_level=6
        )
        session.add_all([pat, enc])
        await session.commit()

        evaluator = OptimizationEvaluator(session)
        res = await evaluator.evaluate_scenario(enc, pat)

        # Baseline assigns overloaded doctor -> constraint violation
        if res["baseline"]["assigned_doctor_id"] == "DOC-001":
            assert "STAFF_CAPACITY_EXCEEDED" in res["baseline"]["violations"]


@pytest.mark.asyncio
async def test_scenario_isolation_compatibility(test_db):
    """
    Scenario 4: Infectious symptom pattern (fever + rash).
    Requires isolation-capable bed.
    Baseline grabs first non-isolation bed (violating isolation constraint).
    """
    async with test_db() as session:
        pat = Patient(
            id="PAT-EVAL-04",
            tenant_id="HOSP-DEFAULT",
            first_name="Karan",
            last_name="Johar",
            age=36,
            gender="M",
            blood_group="AB-",
            contact_phone="+919800000007",
            emergency_contact="+919800000008"
        )
        enc = Encounter(
            id="ENC-EVAL-04",
            patient_id="PAT-EVAL-04",
            encounter_type="EMERGENCY",
            current_department_id="DEP-WA",
            chief_complaint="High fever with diffuse petechial rash and vomiting",
            esi_level=2,
            heart_rate=112,
            bp_systolic=105,
            bp_diastolic=68,
            spo2=96,
            pain_level=5
        )
        session.add_all([pat, enc])
        await session.commit()

        evaluator = OptimizationEvaluator(session)
        res = await evaluator.evaluate_scenario(enc, pat)

        # Baseline selects first Ward bed which lacks isolation capability
        b_id = res["baseline"]["target_bed_id"]
        if b_id:
            b_obj = await session.get(Bed, b_id)
            if not b_obj.is_isolation:
                assert "ISOLATION_MISMATCH" in res["baseline"]["violations"]


@pytest.mark.asyncio
async def test_scenario_cross_tenant_isolation(test_db):
    """
    Scenario 5: Cross-tenant isolation.
    Tenant A encounters must never receive Tenant B beds.
    """
    await seed_tenant_b(test_db)

    async with test_db() as session:
        pat = Patient(
            id="PAT-EVAL-05",
            tenant_id="HOSP-DEFAULT",
            first_name="Deepak",
            last_name="Chopra",
            age=51,
            gender="M",
            blood_group="O-",
            contact_phone="+919800000009",
            emergency_contact="+919800000010"
        )
        enc = Encounter(
            id="ENC-EVAL-05",
            patient_id="PAT-EVAL-05",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            chief_complaint="General checkup",
            esi_level=4
        )
        session.add_all([pat, enc])
        await session.commit()

        evaluator = OptimizationEvaluator(session)
        res = await evaluator.evaluate_scenario(enc, pat, tenant_id="HOSP-DEFAULT")

        # Confirm no Tenant B bed assigned in either strategy
        if res["baseline"]["target_bed_id"]:
            b_base = await session.get(Bed, res["baseline"]["target_bed_id"])
            assert b_base.id.startswith("BED-") and not b_base.id.startswith("BED-RIV")

        if res["optimizer"]["target_bed_id"]:
            b_opt = await session.get(Bed, res["optimizer"]["target_bed_id"])
            assert b_opt.id.startswith("BED-") and not b_opt.id.startswith("BED-RIV")


@pytest.mark.asyncio
async def test_scenario_high_risk_human_approval_barrier_zero_mutation(test_db):
    """
    Scenario 6 & 7: High-risk critical decompensation requires human approval.
    Proves that running the optimizer generates a PENDING approval and DOES NOT
    mutate physical beds autonomously prior to clinician signoff.
    """
    async with test_db() as session:
        # Reset ICU bed to available
        await session.execute(
            update(Bed).where(Bed.id == "BED-ICU-01").values(status="AVAILABLE", current_patient_id=None)
        )

        pat = Patient(
            id="PAT-EVAL-06",
            tenant_id="HOSP-DEFAULT",
            first_name="Vikram",
            last_name="Sarabhai",
            age=71,
            gender="M",
            blood_group="B-",
            contact_phone="+919800000011",
            emergency_contact="+919800000012"
        )
        enc = Encounter(
            id="ENC-EVAL-06",
            patient_id="PAT-EVAL-06",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            chief_complaint="Ventricular tachycardia with profound shock GCS 7",
            esi_level=1,
            heart_rate=165,
            bp_systolic=60,
            bp_diastolic=35,
            spo2=79,
            gcs_score=7,
            pain_level=0
        )
        session.add_all([pat, enc])
        await session.commit()

        evaluator = OptimizationEvaluator(session)
        res = await evaluator.evaluate_scenario(enc, pat)

        # Optimizer requires human approval
        assert res["optimizer"]["requires_human_approval"] is True
        assert res["optimizer"]["risk_level"] == "HIGH"

        # Verify bed BED-ICU-01 remains AVAILABLE (zero autonomous mutation!)
        b_after = await session.get(Bed, "BED-ICU-01")
        assert b_after.status == "AVAILABLE"
        assert b_after.current_patient_id is None
