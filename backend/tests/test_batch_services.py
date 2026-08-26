import pytest
from fastapi import HTTPException
from app.services.approval_service import ApprovalService
from app.services.emergency_service import EmergencyService
from app.services.workflow_service import WorkflowService
from app.models.agent import ApprovalItem, AgentDecision
from app.models.patient import Patient, Encounter

@pytest.mark.asyncio
async def test_approval_service_lifecycle(test_db):
    """Direct unit test for ApprovalService operations."""
    async with test_db() as session:
        service = ApprovalService(session)

        # 1. Create a pending decision & approval item
        dec = AgentDecision(
            id="DEC-SVC-TEST-01",
            agent_id="AGENT-TRIAGE",
            action_type="BED_TRANSFER",
            proposed_action={"bed_id": "BED-ICU-02"},
            reasoning="Patient unstable",
            status="PROPOSED"
        )
        item = ApprovalItem(
            id="APP-SVC-TEST-01",
            decision_id="DEC-SVC-TEST-01",
            agent_id="AGENT-TRIAGE",
            action_type="BED_TRANSFER",
            risk_level="HIGH",
            proposed_action={"bed_id": "BED-ICU-02"},
            reasoning="Patient unstable",
            status="PENDING"
        )
        session.add_all([dec, item])
        await session.commit()

        # 2. Test list_pending_approvals
        pending = await service.list_pending_approvals()
        assert any(i.id == "APP-SVC-TEST-01" for i in pending)

        # 3. Test review_approval (APPROVE)
        resolved = await service.review_approval(
            approval_id="APP-SVC-TEST-01",
            action="APPROVE",
            actor_id="DOC-001",
            actor_role="DOCTOR"
        )
        assert resolved.status == "APPROVE"
        assert resolved.reviewed_by == "DOC-001"

        # 4. Test double review rejection
        with pytest.raises(HTTPException) as exc_info:
            await service.review_approval(
                approval_id="APP-SVC-TEST-01",
                action="REJECT",
                actor_id="DOC-002",
                actor_role="DOCTOR"
            )
        assert exc_info.value.status_code == 400
        assert "already in 'APPROVE' state" in exc_info.value.detail


@pytest.mark.asyncio
async def test_emergency_service_lifecycle(test_db):
    """Direct unit test for EmergencyService operations."""
    async with test_db() as session:
        service = EmergencyService(session)

        # 1. Declare Emergency
        emr = await service.declare_emergency(
            event_type="MASS_CASUALTY",
            severity="CRITICAL",
            description="Highway pileup surge",
            affected_departments=["DEP-ER", "DEP-ICU"],
            expected_patient_surge=10,
            actor_id="DOC-001"
        )
        assert emr.status == "ACTIVE"
        assert emr.event_type == "MASS_CASUALTY"

        # 2. List Active Emergencies
        active = await service.list_active_emergencies()
        assert any(e.id == emr.id for e in active)

        # 3. Resolve Emergency
        resolved = await service.resolve_emergency(
            emergency_id=emr.id,
            actor_id="DOC-001"
        )
        assert resolved.status == "RESOLVED"
        assert resolved.resolved_at is not None

        # 4. Double resolve rejection
        with pytest.raises(HTTPException) as exc_info:
            await service.resolve_emergency(
                emergency_id=emr.id,
                actor_id="DOC-002"
            )
        assert exc_info.value.status_code == 400
        assert "already resolved" in exc_info.value.detail


@pytest.mark.asyncio
async def test_workflow_service_lifecycle(test_db):
    """Direct unit test for WorkflowService operations."""
    async with test_db() as session:
        service = WorkflowService(session)

        # 1. Test list_definitions
        defs = await service.list_definitions()
        assert len(defs) >= 3

        # 2. Seed patient and encounter
        p = Patient(
            id="PAT-WF-SVC-01",
            first_name="Anita",
            last_name="Rao",
            age=29,
            gender="F",
            blood_group="A+",
            contact_phone="+919876543230",
            emergency_contact="+919876543231"
        )
        enc = Encounter(
            id="ENC-WF-SVC-01",
            patient_id="PAT-WF-SVC-01",
            chief_complaint="Acute appendicitis",
            current_department_id="DEP-ER"
        )
        session.add_all([p, enc])
        await session.commit()

        # 3. Start Workflow Instance
        wf_inst = await service.start_workflow(
            workflow_definition_id="WFD-EMERGENCY-ADMISSION",
            encounter_id="ENC-WF-SVC-01",
            patient_id="PAT-WF-SVC-01",
            actor_id="DOC-001"
        )
        assert wf_inst["status"] == "ACTIVE"
        assert wf_inst["current_step_number"] == 1
        instance_id = wf_inst["id"]

        # 4. Advance Step
        step_2 = await service.advance_step(
            instance_id=instance_id,
            notes="Triage vitals verified",
            actor_id="NUR-001"
        )
        assert step_2["current_step_number"] >= 2

        # 5. List Queues & Tasks
        queues = await service.list_queues()
        assert isinstance(queues, list)

        tasks = await service.list_tasks()
        assert isinstance(tasks, list)
