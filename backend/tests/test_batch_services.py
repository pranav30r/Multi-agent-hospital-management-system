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

        # 1. Create a decision
        dec = AgentDecision(
            id="DEC-SVC-TEST-01",
            agent_id="AGENT-TRIAGE",
            action_type="BED_TRANSFER",
            proposed_action={"bed_id": "BED-ICU-02"},
            reasoning="Patient unstable",
            status="PROPOSED"
        )
        session.add(dec)
        await session.commit()

        # 2. Test create_approval_request
        item = await service.create_approval_request(
            decision_id="DEC-SVC-TEST-01",
            agent_id="AGENT-TRIAGE",
            action_type="BED_TRANSFER",
            proposed_action={"bed_id": "BED-ICU-02"},
            reasoning="Patient unstable",
            risk_level="HIGH"
        )
        assert item.status == "PENDING"
        assert item.id.startswith("APR-")

        # 3. Test list_pending_approvals
        pending = await service.list_pending_approvals()
        assert any(i.id == item.id for i in pending)

        # 4. Test review_approval (APPROVE)
        resolved = await service.review_approval(
            approval_id=item.id,
            action="APPROVE",
            actor_id="DOC-001",
            actor_role="DOCTOR"
        )
        assert resolved.status == "APPROVE"
        assert resolved.reviewed_by == "DOC-001"

        # 5. Test double review rejection
        with pytest.raises(HTTPException) as exc_info:
            await service.review_approval(
                approval_id=item.id,
                action="REJECT",
                actor_id="DOC-002",
                actor_role="DOCTOR"
            )
        assert exc_info.value.status_code == 400
        assert "already in 'APPROVE' state" in exc_info.value.detail


@pytest.mark.asyncio
async def test_approval_service_expire_and_modify(test_db):
    """Test modify, reject, and expire flows in ApprovalService."""
    async with test_db() as session:
        service = ApprovalService(session)

        # 1. Decision & Approval for Modify
        dec2 = AgentDecision(
            id="DEC-SVC-TEST-02",
            agent_id="AGENT-BED",
            action_type="BED_ALLOCATION",
            proposed_action={"bed_id": "BED-ER-01"},
            reasoning="Need bed",
            status="PROPOSED"
        )
        session.add(dec2)
        await session.commit()

        item2 = await service.create_approval_request(
            decision_id="DEC-SVC-TEST-02",
            agent_id="AGENT-BED",
            action_type="BED_ALLOCATION",
            proposed_action={"bed_id": "BED-ER-01"},
            reasoning="Need bed"
        )

        mod_item = await service.modify_action(
            approval_id=item2.id,
            modification={"bed_id": "BED-ICU-01"},
            actor_id="DOC-001",
            actor_role="DOCTOR"
        )
        assert mod_item.status == "MODIFY"
        assert mod_item.modification == {"bed_id": "BED-ICU-01"}

        # 2. Decision & Approval for Expire
        dec3 = AgentDecision(
            id="DEC-SVC-TEST-03",
            agent_id="AGENT-BED",
            action_type="BED_ALLOCATION",
            proposed_action={"bed_id": "BED-ER-02"},
            reasoning="Need bed",
            status="PROPOSED"
        )
        session.add(dec3)
        await session.commit()

        item3 = await service.create_approval_request(
            decision_id="DEC-SVC-TEST-03",
            agent_id="AGENT-BED",
            action_type="BED_ALLOCATION",
            proposed_action={"bed_id": "BED-ER-02"},
            reasoning="Need bed"
        )

        exp_item = await service.expire_approval(approval_id=item3.id)
        assert exp_item.status == "EXPIRED"


@pytest.mark.asyncio
async def test_emergency_service_lifecycle(test_db):
    """Direct unit test for EmergencyService operations."""
    async with test_db() as session:
        service = EmergencyService(session)

        # 1. Declare Emergency with valid departments from DB
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

        # 3. Affected departments query
        aff_depts = await service.get_affected_departments()
        assert "DEP-ER" in aff_depts
        assert "DEP-ICU" in aff_depts

        # 4. Escalate emergency
        esc = await service.escalate_emergency(
            emergency_id=emr.id,
            additional_surge=5,
            additional_departments=["DEP-SUR"],
            reason="Secondary surge arrived",
            actor_id="ADM-001"
        )
        assert esc.status == "ESCALATED"
        assert esc.expected_patient_surge == 15

        # 5. Resolve Emergency
        resolved = await service.resolve_emergency(
            emergency_id=emr.id,
            actor_id="DOC-001"
        )
        assert resolved.status == "RESOLVED"
        assert resolved.resolved_at is not None

        # 6. Double resolve rejection
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

        # 5. Queue operations
        q_entry = await service.add_to_queue(
            patient_id="PAT-WF-SVC-01",
            encounter_id="ENC-WF-SVC-01",
            department_id="DEP-ER",
            queue_type="TRIAGE_QUEUE"
        )
        assert q_entry.status == "WAITING"
        assert q_entry.position >= 1

        updated_q = await service.update_queue_status(queue_id=q_entry.id, status="CALLED")
        assert updated_q.status == "CALLED"

        # 6. Task operations
        tsk = await service.create_task(
            encounter_id="ENC-WF-SVC-01",
            patient_id="PAT-WF-SVC-01",
            title="Perform Blood Gas Analysis",
            task_type="LAB_TEST"
        )
        assert tsk.status == "PENDING"

        upd_tsk = await service.update_task_status(task_id=tsk.id, status="COMPLETED")
        assert upd_tsk.status == "COMPLETED"
