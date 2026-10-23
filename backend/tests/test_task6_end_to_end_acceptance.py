from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketState

from app.models.bed import Bed
from app.models.patient import Encounter, Patient
from app.routers.events import TenantWebSocketManager
from app.services.approval_service import ApprovalService
from app.services.clinical_intake_service import ClinicalIntakeService
from app.services.dashboard_service import DashboardService
from app.services.events import event_bus
from app.services.hospital_workflow_coordinator import HospitalWorkflowCoordinator


class RecordingWebSocket:
    def __init__(self):
        self.client_state = WebSocketState.CONNECTED
        self.events = []

    async def accept(self):
        return None

    async def send_json(self, event):
        self.events.append(event)

    async def close(self, code=None):
        self.client_state = WebSocketState.DISCONNECTED


@pytest.mark.asyncio
async def test_high_risk_intake_through_approval_and_dashboard(test_db, monkeypatch):
    """Exercise intake, coordinated recommendation, approval, event delivery, and dashboard state."""
    monkeypatch.setattr(event_bus.manager, "get_client", AsyncMock(return_value=None))
    websocket_manager = TenantWebSocketManager()
    socket = RecordingWebSocket()
    event_bus.register_local_subscriber(websocket_manager._broadcast_to_tenant_local)
    await websocket_manager.connect(socket, "HOSP-DEFAULT")

    try:
        async with test_db() as session:
            patient = Patient(
                id="PAT-TASK6-001",
                tenant_id="HOSP-DEFAULT",
                first_name="Mira",
                last_name="Shah",
                age=58,
                gender="F",
                blood_group="O+",
                contact_phone="9000000601",
                emergency_contact="9000000602",
                allergies=["Penicillin"],
                chronic_conditions=["Hypertension"]
            )
            session.add(patient)
            await session.flush()

            encounter = Encounter(
                id="ENC-TASK6-001",
                patient_id=patient.id,
                encounter_type="EMERGENCY",
                status="ACTIVE",
                current_department_id="DEP-ER",
                esi_level=1,
                priority=1,
                patient_status="ARRIVED",
                chief_complaint="Severe chest pain, diaphoresis, and difficulty breathing",
                heart_rate=132,
                bp_systolic=78,
                bp_diastolic=48,
                spo2=85,
                pain_level=9
            )
            session.add(encounter)

            available_icu_bed = (await session.execute(
                select(Bed).where(Bed.department_id == "DEP-ICU").limit(1)
            )).scalars().first()
            assert available_icu_bed is not None, "Acceptance scenario requires an ICU bed in seeded infrastructure"
            available_icu_bed.status = "AVAILABLE"
            available_icu_bed.current_patient_id = None
            available_icu_bed.current_encounter_id = None
            await session.commit()

            intake_service = ClinicalIntakeService(session)
            intake = await intake_service.start_intake_session(
                patient_id=patient.id,
                encounter_id=encounter.id,
                chief_complaint_raw=encounter.chief_complaint,
                actor_id="PATIENT"
            )

            question = await intake_service.get_current_question(intake.id)
            while question:
                response_type = (question.response_type or "TEXT").upper()
                if response_type == "BOOLEAN":
                    raw_value, structured_value = "Yes", {"value": True}
                elif response_type == "SCALE":
                    raw_value, structured_value = "9", {"value": 9}
                elif response_type == "NUMBER":
                    raw_value, structured_value = "2", {"value": 2}
                elif response_type == "SINGLE_CHOICE":
                    raw_value = question.allowed_options[0] if question.allowed_options else "Option 1"
                    structured_value = {"value": raw_value}
                else:
                    raw_value = "Severe chest pain with sweating and shortness of breath"
                    structured_value = {"value": raw_value}
                await intake_service.submit_response(
                    session_id=intake.id,
                    question_id=question.id,
                    raw_response=raw_value,
                    structured_value=structured_value
                )
                question = await intake_service.get_current_question(intake.id)

            completed_intake = await intake_service.complete_intake_session(intake.id, actor_id="PATIENT")
            assert completed_intake.status == "COMPLETED"

            workflow = await HospitalWorkflowCoordinator(session).coordinate_workflow(
                encounter_id=encounter.id,
                tenant_id="HOSP-DEFAULT",
                actor_id="DOC-001",
                trigger_reason="FRONTEND_REQUEST"
            )
            assert workflow.triage_result is not None
            assert workflow.resource_match_result is not None
            assert workflow.workflow_status == "APPROVAL_PENDING"
            assert workflow.approval_status == "PENDING"
            approval_id = workflow.recommendation.approval_item_id
            assert approval_id

            state_before_review = await DashboardService(session).get_hospital_state("HOSP-DEFAULT")
            assert state_before_review["approvals"]["pending"] >= 1

            reviewed = await ApprovalService(session).review_approval(
                approval_id=approval_id,
                action="APPROVE",
                actor_id="DOC-001",
                actor_role="DOCTOR",
                tenant_id="HOSP-DEFAULT"
            )
            assert reviewed.status in {"APPROVE", "APPROVED"}

            updated_dashboard = await DashboardService(session).get_hospital_state("HOSP-DEFAULT")
            assert updated_dashboard["beds"]["RESERVED"] == state_before_review["beds"]["RESERVED"] + 1
            assert updated_dashboard["approvals"]["pending"] == state_before_review["approvals"]["pending"] - 1
            assert updated_dashboard["patients"]["active_encounters"] >= 1

            saved_encounter = await session.get(Encounter, encounter.id)
            assert saved_encounter.current_bed_id is not None
            saved_bed = await session.get(Bed, saved_encounter.current_bed_id)
            assert saved_bed.status in {"RESERVED", "OCCUPIED"}
            assert saved_bed.current_encounter_id == encounter.id

        delivered_types = {event.get("event_type") for event in socket.events}
        assert "PATIENT_INTAKE_COMPLETED" in delivered_types
        assert "APPROVAL_REQUIRED" in delivered_types
        assert "BED_RESERVED" in delivered_types
        assert "APPROVAL_DECIDED" in delivered_types
    finally:
        event_bus.unregister_local_subscriber(websocket_manager._broadcast_to_tenant_local)
        websocket_manager.disconnect(socket, "HOSP-DEFAULT")
        await websocket_manager.close_all()
