# pyrefly: ignore [missing-import]
import pytest
# pyrefly: ignore [missing-import]
from sqlalchemy import select
from app.models.patient import Patient, Encounter
from app.models.intake import ClinicalIntakeSession, ClinicalAssessment
from app.models.priority import ClinicalPriorityRecommendation
from app.models.agent import ApprovalItem, AgentDecision, AuditLog
from app.models.bed import Bed
from app.models.workflow import WorkflowInstance


@pytest.mark.asyncio
async def test_complete_synthetic_patient_journey(auth_client, admin_client, test_db):
    """
    End-to-End Synthetic Patient Care Workflow Verification:
    1. Authenticate Staff (Doctor auth_client + Administrator admin_client)
    2. Register Patient (PAT-...)
    3. Create Clinical Encounter (ENC-...)
    4. Start Clinical Intake Session
    5. Ingest Adaptive Questionnaire Responses
    6. Complete Clinical Intake Session
    7. Generate Clinical Intelligence & Severity Assessment
    8. Evaluate Priority & Clinical Routing Recommendation
    9. Record Operational Forecasting Prediction
    10. Create Agent Decision & Human-in-the-Loop Approval Item
    11. Human Reviewer Action (Approve Decision)
    12. Reserve Bed (SELECT ... FOR UPDATE verification)
    13. Confirm Patient Arrival in Bed (OCCUPIED transition)
    14. Initialize and Advance Clinical Workflow Instance
    15. Verify Database State Machine and Immutable Audit Logs
    """
    # ─── 1. Register Patient ──────────────────────────────────────────────────
    pat_payload = {
        "first_name": "Vikram",
        "last_name": "Malhotra",
        "age": 62,
        "gender": "MALE",
        "blood_group": "B+",
        "contact_phone": "+91-9876543210",
        "emergency_contact": "+91-9876543211",
        "allergies": ["Penicillin"],
        "chronic_conditions": ["Hypertension", "Type 2 Diabetes"]
    }
    pat_resp = await auth_client.post("/api/v1/patients", json=pat_payload)
    assert pat_resp.status_code == 201, f"Patient registration failed: {pat_resp.text}"
    patient_id = pat_resp.json()["id"]
    assert patient_id.startswith("PAT-")

    # ─── 2. Create Clinical Encounter ─────────────────────────────────────────
    enc_payload = {
        "patient_id": patient_id,
        "chief_complaint": "Acute crushing substernal chest pain radiating to left arm with diaphoresis",
        "encounter_type": "EMERGENCY",
        "heart_rate": 118,
        "bp_systolic": 85,
        "bp_diastolic": 55,
        "spo2": 88,
        "temperature_f": 99.1,
        "respiratory_rate": 26,
        "gcs_score": 14,
        "pain_score": 9
    }
    enc_resp = await auth_client.post("/api/v1/patients/encounters", json=enc_payload)
    assert enc_resp.status_code == 201, f"Encounter creation failed: {enc_resp.text}"
    encounter_id = enc_resp.json()["id"]
    assert encounter_id.startswith("ENC-")

    # ─── 3. Start Clinical Intake Session ─────────────────────────────────────
    intake_start = await auth_client.post("/api/v1/clinical-intakes", json={
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "language": "en",
        "interaction_mode": "TEXT",
        "chief_complaint_raw": enc_payload["chief_complaint"]
    })
    assert intake_start.status_code == 201, f"Intake start failed: {intake_start.text}"
    session_id = intake_start.json()["id"]

    # ─── 4. Ingest Adaptive Questionnaire Responses ───────────────────────────
    for _ in range(12):
        cq_res = await auth_client.get(f"/api/v1/clinical-intakes/{session_id}/current-question")
        if cq_res.status_code != 200 or not cq_res.json():
            break
        q = cq_res.json()
        resp_val = "Severe crushing substernal chest pain radiating to left arm"
        struct_val = {"value": resp_val}
        if q.get("response_type") == "BOOLEAN":
            resp_val = "true"
            struct_val = {"value": True}
        elif q.get("response_type") == "SCALE":
            resp_val = "9"
            struct_val = {"value": 9}

        ans_post = await auth_client.post(f"/api/v1/clinical-intakes/{session_id}/responses", json={
            "question_id": q["id"],
            "raw_response": resp_val,
            "structured_value": struct_val
        })
        assert ans_post.status_code == 201

    # ─── 5. Complete Clinical Intake Session ──────────────────────────────────
    complete_resp = await auth_client.post(
        f"/api/v1/clinical-intakes/{session_id}/complete",
        json={"notes": "Intake completed by attending emergency clinician"}
    )
    assert complete_resp.status_code == 200, f"Intake completion failed: {complete_resp.text}"
    assert complete_resp.json()["status"] == "COMPLETED"

    # ─── 6. Generate Clinical Intelligence & Severity Assessment ───────────────
    intel_resp = await auth_client.get(f"/api/v1/clinical-intelligence/{encounter_id}")
    assert intel_resp.status_code == 200, f"Clinical intelligence failed: {intel_resp.text}"
    intel_data = intel_resp.json()
    assert intel_data["severity"] in ["HIGH", "CRITICAL"]
    assert len(intel_data["red_flags"]) >= 1
    assert intel_data["requires_priority_attention"] is True

    # ─── 7. Evaluate Priority & Clinical Routing Recommendation ───────────────
    priority_resp = await auth_client.post(f"/api/v1/clinical-priority/{encounter_id}/evaluate")
    assert priority_resp.status_code == 200, f"Priority evaluation failed: {priority_resp.text}"
    priority_data = priority_resp.json()
    assert priority_data["priority_level"] in ["CRITICAL", "HIGH"]
    assert priority_data["route"] in ["EMERGENCY_TRIAGE", "IMMEDIATE_DOCTOR_REVIEW"]

    # ─── 8. Record Operational Forecasting Prediction ─────────────────────────
    pred_resp = await auth_client.post("/api/v1/predictions/record", json={
        "prediction_type": "ICU_DEMAND",
        "predicted_value": 4.5,
        "prediction_unit": "beds",
        "confidence_score": 0.92,
        "inference_time_ms": 12.5,
        "model_name": "ICUDemandForecaster_v1",
        "actionable_recommendation": "Prepare ICU bed allocation for incoming cardiac emergency",
        "forecast_horizon_hours": 6
    })
    assert pred_resp.status_code == 201, f"Prediction record failed: {pred_resp.text}"

    # ─── 9. Create Agent Decision & Human Approval Item ───────────────────────
    async with test_db() as session:
        decision = AgentDecision(
            agent_id="ClinicalResourceOrchestratorAgent",
            encounter_id=encounter_id,
            action_type="ICU_BED_ALLOCATION",
            proposed_action={
                "action": "ALLOCATE_BED",
                "bed_id": "BED-ICU-01",
                "encounter_id": encounter_id,
                "patient_id": patient_id
            },
            reasoning="Patient exhibits critical hemodynamic instability and requires urgent ICU telemetry monitoring.",
            confidence=0.95,
            risk_level="HIGH",
            status="PROPOSED"
        )
        session.add(decision)
        await session.commit()
        await session.refresh(decision)

        approval = ApprovalItem(
            decision_id=decision.id,
            agent_id="ClinicalResourceOrchestratorAgent",
            action_type="ICU_BED_ALLOCATION",
            risk_level="HIGH",
            proposed_action=decision.proposed_action,
            reasoning=decision.reasoning,
            status="PENDING"
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)
        approval_id = approval.id

    # ─── 10. Human Reviewer Action (Approve Decision) ─────────────────────────
    review_resp = await auth_client.post(f"/api/v1/approvals/{approval_id}/review", json={
        "action": "APPROVE",
        "notes": "Approved for immediate transfer to ICU-01"
    })
    assert review_resp.status_code == 200, f"Approval review failed: {review_resp.text}"
    assert review_resp.json()["status"] in ["APPROVE", "APPROVED"]

    # Verify duplicate review is rejected (Idempotency Guard)
    dup_review = await auth_client.post(f"/api/v1/approvals/{approval_id}/review", json={
        "action": "APPROVE"
    })
    assert dup_review.status_code == 400, "Duplicate approval review must be rejected"

    # ─── 11. Verify Bed is Reserved via Approval Execution Pipeline ───────────
    async with test_db() as session:
        bed_db = await session.get(Bed, "BED-ICU-01")
        assert bed_db is not None
        assert bed_db.status == "RESERVED"
        assert bed_db.current_patient_id == patient_id
        assert bed_db.current_encounter_id == encounter_id

    # Verify duplicate bed booking is rejected (Bed is already reserved)
    dup_bed = await auth_client.post("/api/v1/beds/book-manual", json={
        "bed_id": "BED-ICU-01",
        "encounter_id": encounter_id,
        "patient_id": patient_id
    })
    assert dup_bed.status_code == 400, "Double bed booking must be rejected"  

    # ─── 12. Confirm Patient Arrival in Bed ────────────────────────────────────
    arrival_resp = await auth_client.post("/api/v1/beds/BED-ICU-01/confirm-patient-in-bed")
    assert arrival_resp.status_code == 200, f"Bed arrival confirmation failed: {arrival_resp.text}"
    assert arrival_resp.json()["status"] == "OCCUPIED"

    # ─── 13. Initialize and Advance Clinical Workflow Instance ────────────────
    wf_inst_resp = await auth_client.post("/api/v1/workflows/instances", json={
        "workflow_definition_id": "WFD-EMERGENCY-ADMISSION",
        "encounter_id": encounter_id,
        "patient_id": patient_id
    })
    assert wf_inst_resp.status_code == 201, f"Workflow instance creation failed: {wf_inst_resp.text}"
    wf_instance_id = wf_inst_resp.json()["id"]
    assert wf_inst_resp.json()["current_step_number"] == 1

    advance_resp = await auth_client.post(
        f"/api/v1/workflows/instances/{wf_instance_id}/advance",
        json={"notes": "Step 1 triage completed"}
    )
    assert advance_resp.status_code == 200, f"Workflow advance failed: {advance_resp.text}"
    assert advance_resp.json()["current_step_number"] == 2

    # ─── 14. Verify Database State Machine & Immutable Audit Trail ────────────
    async with test_db() as session:
        # Verify Patient State
        p_db = (await session.execute(select(Patient).where(Patient.id == patient_id))).scalar_one()
        assert p_db.first_name == "Vikram"
        assert p_db.age == 62

        # Verify Encounter State
        enc_db = (await session.execute(select(Encounter).where(Encounter.id == encounter_id))).scalar_one()
        assert enc_db.status == "ACTIVE"
        assert enc_db.heart_rate == 118

        # Verify Intake Session State
        intk_db = (await session.execute(select(ClinicalIntakeSession).where(ClinicalIntakeSession.id == session_id))).scalar_one()
        assert intk_db.status == "COMPLETED"

        # Verify Clinical Assessment State
        assess_db = (await session.execute(select(ClinicalAssessment).where(ClinicalAssessment.encounter_id == encounter_id))).scalars().first()
        assert assess_db is not None
        assert assess_db.severity in ["HIGH", "CRITICAL"]

        # Verify Priority Recommendation State
        prio_db = (await session.execute(select(ClinicalPriorityRecommendation).where(ClinicalPriorityRecommendation.encounter_id == encounter_id))).scalars().first()
        assert prio_db is not None
        assert prio_db.priority_level in ["CRITICAL", "HIGH"]

        # Verify Bed State
        bed_db = (await session.execute(select(Bed).where(Bed.id == "BED-ICU-01"))).scalar_one()
        assert bed_db.status == "OCCUPIED"
        assert bed_db.current_patient_id == patient_id
        assert bed_db.current_encounter_id == encounter_id

        # Verify Approval Item State
        appr_db = (await session.execute(select(ApprovalItem).where(ApprovalItem.id == approval_id))).scalar_one()
        assert appr_db.status in ["APPROVE", "APPROVED"]

        # Verify Workflow Instance State
        wf_db = (await session.execute(select(WorkflowInstance).where(WorkflowInstance.id == wf_instance_id))).scalar_one()
        assert wf_db.current_step_number == 2
        assert wf_db.status in ["ACTIVE", "IN_PROGRESS"]

    # Query Audit Log endpoint as Administrator
    audit_resp = await admin_client.get("/api/v1/audit")
    assert audit_resp.status_code == 200, f"Admin audit retrieval failed: {audit_resp.text}"
    audit_list = audit_resp.json()
    assert len(audit_list) >= 3
