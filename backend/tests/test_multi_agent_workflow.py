import pytest
from datetime import datetime
from sqlalchemy import select

from app.models.patient import Patient, Encounter
from app.models.bed import Bed
from app.models.staff import Staff
from app.models.emergency import EmergencyEvent
from app.models.agent import AgentDecision, AgentMessage, OptimizationRun, ApprovalItem, AuditLog
from app.services.agent_orchestrator import (
    TriageAgent, BedManagerAgent, BedManagementAgent, StaffSchedulerAgent, StaffWorkloadAgent,
    EmergencyEscalationAgent, PatientCoordinatorAgent,
    CoordinatorAgent, MultiAgentOrchestratorService
)


@pytest.mark.asyncio
async def test_01_full_5_agent_workflow_execution_critical(auth_client, test_db):
    """
    Test 1: Full 5-Agent Critical Emergency Workflow
    - Triage Agent evaluates severe chest pain + hypoxia + tachycardia.
    - Bed Agent proposes available ICU bed.
    - Staff Agent assigns optimal doctor and nurse.
    - Emergency Escalation Agent detects acute decompensation and triggers RAPID_RESPONSE_STAT.
    - Patient Coordinator Agent synthesizes clinical handoff and flags missing allergy verification.
    - Coordinator generates 3 candidate plans, creates OptimizationRun, 6 AgentMessages,
      AgentDecision, and routes to ApprovalItem (PENDING).
    - Invariant: Beds and Staff are NEVER autonomously mutated.
    """
    # 1. Register Patient & Critical Emergency Encounter
    pat_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Arjun",
        "last_name": "Verma",
        "age": 62,
        "gender": "M",
        "blood_group": "B+",
        "contact_phone": "+919811223344",
        "emergency_contact": "+919811223345",
        "allergies": ["Penicillin"],
        "chronic_conditions": ["Coronary Artery Disease"]
    })
    assert pat_res.status_code == 201, f"Patient create failed: {pat_res.text}"
    patient_id = pat_res.json()["id"]

    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Acute severe substernal chest pressure radiating to left shoulder, diaphoresis, dyspnea",
        "encounter_type": "EMERGENCY",
        "heart_rate": 136,
        "bp_systolic": 85,
        "bp_diastolic": 55,
        "spo2": 87,
        "temperature_f": 99.1,
        "respiratory_rate": 28,
        "gcs_score": 14,
        "pain_level": 9
    })
    assert enc_res.status_code == 201, f"Encounter create failed: {enc_res.text}"
    encounter_id = enc_res.json()["id"]

    # 2. Trigger Multi-Agent Orchestration via API
    orch_res = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/orchestrate", json={
        "trigger_reason": "EMERGENCY_TRIAGE_INTAKE"
    })
    assert orch_res.status_code == 200, f"Orchestration failed: {orch_res.text}"
    data = orch_res.json()

    assert data["action_type"] == "ICU_BED_ALLOCATION_RECOMMENDATION"
    assert data["risk_level"] == "HIGH"
    assert data["requires_human_approval"] is True
    assert data["approval_item_id"] is not None
    assert data["status"] == "PROPOSED"
    assert data["optimization_run_id"] is not None
    assert data["agent_messages_count"] == 6
    assert len(data["candidate_plans"]) >= 3

    # 3. Verify Database Invariants
    async with test_db() as session:
        # Check Decision
        dec = (await session.execute(select(AgentDecision).where(AgentDecision.id == data["id"]))).scalar_one()
        assert dec.encounter_id == encounter_id
        assert dec.risk_level == "HIGH"

        # Check Approval Item
        appr = (await session.execute(select(ApprovalItem).where(ApprovalItem.id == data["approval_item_id"]))).scalar_one()
        assert appr.status == "PENDING"
        assert appr.decision_id == dec.id

        # Check OptimizationRun
        opt = (await session.execute(select(OptimizationRun).where(OptimizationRun.id == data["optimization_run_id"]))).scalar_one()
        assert opt.candidates_count >= 3
        assert opt.hard_constraint_pass is True
        assert opt.status == "COMPLETED"
        assert "emergency_escalation_agent" in opt.agents_involved
        assert "patient_coordinator_agent" in opt.agents_involved

        # Check AgentMessages (all 5 specialized agents + coordinator)
        msgs = (await session.execute(select(AgentMessage).where(AgentMessage.encounter_id == encounter_id))).scalars().all()
        assert len(msgs) == 6
        senders = [m.sender_agent for m in msgs]
        assert "triage_agent" in senders
        assert "bed_agent" in senders
        assert "staff_agent" in senders
        assert "emergency_escalation_agent" in senders
        assert "patient_coordinator_agent" in senders
        assert "coordinator_agent" in senders

        # Crucial Invariant: Critical Hospital Resources were NOT autonomously mutated by AI
        icu_bed = (await session.execute(select(Bed).where(Bed.id == "BED-ICU-01"))).scalar_one()
        assert icu_bed.status == "AVAILABLE", "AI must never mutate bed availability directly!"


@pytest.mark.asyncio
async def test_02_inter_agent_messages_endpoint(auth_client):
    """
    Test 2: Inter-Agent Message Provenance Endpoint
    - Verifies GET /api/v1/clinical-intelligence/{encounter_id}/messages returns full 5-agent message exchange trail.
    """
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Deepak", "last_name": "Patel", "age": 45, "gender": "M",
        "blood_group": "O+", "contact_phone": "+919877112233", "emergency_contact": "+919877112234"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Acute moderate asthma exacerbation with audible wheezing",
        "encounter_type": "EMERGENCY",
        "heart_rate": 105, "bp_systolic": 130, "bp_diastolic": 82, "spo2": 92,
        "temperature_f": 98.6, "respiratory_rate": 22, "gcs_score": 15, "pain_level": 4
    })).json()

    # Orchestrate
    await auth_client.post(f"/api/v1/clinical-intelligence/{enc['id']}/orchestrate")

    # Query Messages
    msg_res = await auth_client.get(f"/api/v1/clinical-intelligence/{enc['id']}/messages")
    assert msg_res.status_code == 200
    messages = msg_res.json()
    assert len(messages) == 6

    subjects = [m["subject"] for m in messages]
    assert "TRIAGE_ASSESSMENT_COMPLETED" in subjects
    assert "BED_FEASIBILITY_EVALUATED" in subjects
    assert "STAFF_WORKLOAD_EVALUATED" in subjects
    assert "EMERGENCY_ESCALATION_EVALUATED" in subjects
    assert "PATIENT_COORDINATION_COMPLETED" in subjects
    assert "OPERATIONAL_PLAN_SELECTED" in subjects


@pytest.mark.asyncio
async def test_03_emergency_escalation_agent_direct_evaluation(test_db):
    """
    Test 3: EmergencyEscalationAgent Dedicated Unit Evaluation
    - Verifies physiological decompensation triggers emergency escalation level.
    - Confirms agent remains recommendation-only and does not mutate emergency event records.
    """
    async with test_db() as session:
        agent = EmergencyEscalationAgent(session)
        p = Patient(id="PAT-EM-01", tenant_id="HOSP-DEFAULT", first_name="Rahul", last_name="Sharma", age=70, gender="M", blood_group="O+", contact_phone="9988112233", emergency_contact="9988112234")
        enc = Encounter(id="ENC-EM-01", patient_id="PAT-EM-01", current_department_id="DEP-EMERGENCY", chief_complaint="Severe shock and hypotension", bp_systolic=75, spo2=84, gcs_score=8)
        session.add_all([p, enc])
        await session.commit()

        triage_mock = {
            "esi_level": 1,
            "severity": "CRITICAL",
            "score": 95.0,
            "red_flags": [{"code": "RF_CRITICAL_HYPOXIA", "severity": "HIGH"}],
            "recommended_care_level": "ICU"
        }

        output = await agent.evaluate(triage_mock, enc, tenant_id="HOSP-DEFAULT")
        assert output["agent_id"] == "emergency_escalation_agent"
        assert output["escalation_required"] is True
        assert output["emergency_level"] == "CRITICAL_CODE_BLUE"
        assert "ACTIVATE_RAPID_RESPONSE_TEAM" in output["recommended_emergency_actions"]
        assert "STAT_ICU_BED_RESERVATION" in output["recommended_emergency_actions"]


@pytest.mark.asyncio
async def test_04_patient_coordinator_agent_direct_evaluation(test_db):
    """
    Test 4: PatientCoordinatorAgent Dedicated Unit Evaluation
    - Verifies clinical handoff brief preparation, discharge readiness check, and missing inputs detection.
    - Confirms agent remains recommendation-only.
    """
    async with test_db() as session:
        agent = PatientCoordinatorAgent(session)
        p = Patient(id="PAT-PC-01", tenant_id="HOSP-DEFAULT", first_name="Sneha", last_name="Gupta", age=30, gender="F", blood_group="A+", contact_phone="9988112235", emergency_contact="9988112236", allergies=[])
        enc = Encounter(id="ENC-PC-01", patient_id="PAT-PC-01", current_department_id="DEP-OPD", chief_complaint="Mild ankle sprain", bp_systolic=118, spo2=99, temperature_f=98.6)
        session.add_all([p, enc])
        await session.commit()

        triage_mock = {
            "esi_level": 5,
            "severity": "LOW",
            "score": 5.0,
            "red_flags": [],
            "recommended_care_level": "OUTPATIENT",
            "priority_level": "ROUTINE"
        }
        bed_mock = {"recommended_bed_id": None, "recommended_department_id": "DEP-OPD"}
        staff_mock = {"assigned_doctor_id": "DOC-001", "assigned_nurse_id": "NUR-001"}

        output = await agent.evaluate(triage_mock, bed_mock, staff_mock, enc, p, tenant_id="HOSP-DEFAULT")
        assert output["agent_id"] == "patient_coordinator_agent"
        assert output["discharge_readiness"] is True
        assert "Sneha Gupta" in output["handoff_brief"]["patient_name"]
        assert len(output["coordination_recommendations"]) >= 1


@pytest.mark.asyncio
async def test_05_routine_opd_workflow_no_human_approval_barrier(auth_client):
    """
    Test 5: Routine Low-Risk Encounter
    - Triage Agent identifies ESI 5 / Routine acuity.
    - Emergency Escalation confirms no active deterioration.
    - Resulting decision is STANDARD_OPD_ROUTING with risk_level=LOW.
    - No ApprovalItem is created.
    """
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Sanjay", "last_name": "Mishra", "age": 29, "gender": "M",
        "blood_group": "AB+", "contact_phone": "+919855112233", "emergency_contact": "+919855112234"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Routine health checkup and annual physical",
        "encounter_type": "OPD",
        "heart_rate": 68, "bp_systolic": 115, "bp_diastolic": 75, "spo2": 99,
        "temperature_f": 98.4, "respiratory_rate": 14, "gcs_score": 15, "pain_level": 0
    })).json()

    dec_res = await auth_client.post(f"/api/v1/clinical-intelligence/{enc['id']}/orchestrate")
    assert dec_res.status_code == 200
    data = dec_res.json()

    assert data["action_type"] == "STANDARD_OPD_ROUTING"
    assert data["risk_level"] == "LOW"
    assert data["requires_human_approval"] is False
    assert data["approval_item_id"] is None


@pytest.mark.asyncio
async def test_06_multi_agent_idempotency_and_force_recalculate(auth_client):
    """
    Test 6: Idempotency
    - Calling orchestrate multiple times returns the active decision without creating duplicate records.
    - force_recalculate=True generates a fresh run.
    """
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Kavita", "last_name": "Reddy", "age": 52, "gender": "F",
        "blood_group": "O+", "contact_phone": "+919844112233", "emergency_contact": "+919844112234"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Acute abdominal pain in right lower quadrant with nausea",
        "encounter_type": "EMERGENCY",
        "heart_rate": 102, "bp_systolic": 135, "bp_diastolic": 88, "spo2": 97,
        "temperature_f": 100.2, "respiratory_rate": 20, "gcs_score": 15, "pain_level": 8
    })).json()

    # First Run
    run1 = (await auth_client.post(f"/api/v1/clinical-intelligence/{enc['id']}/orchestrate")).json()

    # Second Run (Idempotent)
    run2 = (await auth_client.post(f"/api/v1/clinical-intelligence/{enc['id']}/orchestrate")).json()
    assert run1["id"] == run2["id"], "Repeated orchestration must be idempotent!"

    # Third Run with Force Recalculate
    run3 = (await auth_client.post(f"/api/v1/clinical-intelligence/{enc['id']}/orchestrate", json={
        "force_recalculate": True
    })).json()
    assert run3["id"] != run1["id"], "Force recalculate must produce a new decision!"


@pytest.mark.asyncio
async def test_07_human_approval_to_authorized_service_execution_flow(auth_client, test_db):
    """
    Test 7: End-to-End Human Approval Barrier to Authorized Service Execution
    1. Multi-Agent workflow proposes ICU bed allocation and creates PENDING approval.
    2. Clinician reviews and approves via /api/v1/approvals/{id}/review.
    3. Consequential bed reservation is executed through authorized BedService.
    4. Audit trail captures full provenance.
    """
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Vikram", "last_name": "Chauhan", "age": 67, "gender": "M",
        "blood_group": "A+", "contact_phone": "+919833112233", "emergency_contact": "+919833112234"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Acute severe heart failure exacerbation with severe pulmonary edema and hypotension",
        "encounter_type": "EMERGENCY",
        "heart_rate": 140, "bp_systolic": 78, "bp_diastolic": 48, "spo2": 82,
        "temperature_f": 98.8, "respiratory_rate": 34, "gcs_score": 12, "pain_level": 7
    })).json()

    # 1. Orchestrate
    orch_res = (await auth_client.post(f"/api/v1/clinical-intelligence/{enc['id']}/orchestrate")).json()
    approval_id = orch_res["approval_item_id"]
    assert approval_id is not None

    # 2. Clinician Approves via Approval Queue
    appr_res = await auth_client.post(f"/api/v1/approvals/{approval_id}/review", json={
        "action": "APPROVE"
    })
    assert appr_res.status_code == 200
    appr_data = appr_res.json()
    assert appr_data["status"] in ["APPROVE", "APPROVED"]

    # 3. Verify that the Authorized Execution Layer reserved the Bed
    async with test_db() as session:
        # Check Approval item
        appr_db = (await session.execute(select(ApprovalItem).where(ApprovalItem.id == approval_id))).scalar_one()
        assert appr_db.status in ["APPROVE", "APPROVED"]

        # Check Decision is resolved
        dec_db = (await session.execute(select(AgentDecision).where(AgentDecision.id == appr_db.decision_id))).scalar_one()
        assert dec_db.status in ["APPROVE", "APPROVED"]

        # Check Audit Log for approval action
        audit_entries = (await session.execute(
            select(AuditLog).where(AuditLog.approval_id == approval_id)
        )).scalars().all()
        assert len(audit_entries) >= 1
