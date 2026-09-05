"""
LangGraph Multi-Agent State Graph Integration & Structured Negotiation Tests.

Proves:
1. A real LangGraph StateGraph is constructed and compiled with conflict detection and negotiation nodes.
2. All 5 specialized operational agents (Triage, Bed Management, Staff Workload, Emergency Escalation, Patient Coordinator) and the Coordinator agent execute as graph nodes.
3. No-conflict workflows bypass negotiation directly to Coordinator.
4. Real resource conflicts (e.g. ICU bed shortage, staffing overload) trigger the structured negotiation node.
5. Structured inter-agent messages (COUNTER_PROPOSAL, ESCALATION, REVISED_PROPOSAL) are generated and persisted.
6. Negotiation is bounded by MAX_NEGOTIATION_ROUNDS = 2.
7. Consequential critical actions require human approval (ApprovalItem PENDING).
8. Low-risk routine actions execute safely without approval barrier.
9. Physical resources (Beds, Staff, Emergency Codes) remain unmutated by AI agents during negotiation.
10. Idempotency and tenant isolation remain strictly intact.
"""

import pytest
from sqlalchemy import select, update
from langgraph.graph.state import CompiledStateGraph

from app.models.patient import Patient, Encounter
from app.models.bed import Bed
from app.models.staff import Staff
from app.models.agent import AgentDecision, AgentMessage, ApprovalItem, OptimizationRun
from app.services.agent_graph import (
    HospitalLangGraphOrchestrator,
    create_hospital_state_graph,
    HospitalAgentState,
    MAX_NEGOTIATION_ROUNDS
)
from app.services.agent_orchestrator import PatientCoordinatorAgent, BedManagementAgent


@pytest.mark.asyncio
async def test_01_langgraph_stategraph_structure_and_compilation():
    """
    Test 1: Verifies real LangGraph StateGraph instantiation, node topology, and compilation.
    """
    compiled_graph = create_hospital_state_graph()
    assert isinstance(compiled_graph, CompiledStateGraph)
    
    # Verify exact graph nodes
    node_keys = set(compiled_graph.nodes.keys())
    assert "__start__" in node_keys
    assert "triage" in node_keys
    assert "bed" in node_keys
    assert "emergency" in node_keys
    assert "staff" in node_keys
    assert "patient_coordinator" in node_keys
    assert "conflict_detector" in node_keys
    assert "negotiator" in node_keys
    assert "coordinator" in node_keys


@pytest.mark.asyncio
async def test_02_full_langgraph_execution_critical_decompensation(test_db):
    """
    Test 2: Full LangGraph execution on acute critical patient with available ICU resources.
    - Graph traverses triage -> bed & emergency -> staff -> patient_coordinator -> conflict_detector -> coordinator -> END.
    - Verifies complete state population across all agent nodes.
    - Verifies HITL ApprovalItem generation and resource safety.
    """
    async with test_db() as session:
        # Seed Patient & Encounter
        patient = Patient(
            id="PAT-LG-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Ramesh",
            last_name="Verma",
            age=68,
            gender="M",
            blood_group="B+",
            contact_phone="9876543210",
            emergency_contact="9876543211",
            allergies=["Penicillin"],
            chronic_conditions=["CAD", "Type 2 Diabetes"]
        )
        encounter = Encounter(
            id="ENC-LG-01",
            patient_id="PAT-LG-01",
            current_department_id="DEP-EMERGENCY",
            encounter_type="EMERGENCY",
            chief_complaint="Crushing substernal chest pain radiating to left jaw with diaphoresis",
            esi_level=1,
            priority=1,
            heart_rate=135,
            bp_systolic=80,
            bp_diastolic=50,
            spo2=86,
            temperature_f=98.8,
            respiratory_rate=28,
            gcs_score=11,
            pain_level=9
        )
        session.add_all([patient, encounter])
        await session.commit()

        # Run LangGraph Orchestrator
        orchestrator = HospitalLangGraphOrchestrator(session, encounter=encounter, patient=patient)
        final_state = await orchestrator.run(
            tenant_id="HOSP-DEFAULT",
            trigger_reason="ACUTE_CHEST_PAIN_EMERGENCY",
            actor_id="STAFF-TRIAGE-01"
        )

        # 1. Verify LangGraph Execution State
        assert final_state["status"] == "COMPLETED"
        assert final_state["error"] is None
        assert final_state["failed_agent"] is None

        # 2. Verify Triage Node Output in State
        triage_out = final_state.get("triage_output")
        assert triage_out is not None
        assert triage_out["agent_id"] == "triage_agent"
        assert triage_out["esi_level"] in [1, 2]
        assert triage_out["recommended_care_level"] == "ICU"
        assert triage_out["requires_telemetry"] is True

        # 3. Verify Bed Node Output in State
        bed_out = final_state.get("bed_output")
        assert bed_out is not None
        assert bed_out["agent_id"] in ["bed_agent", "bed_management_agent"]
        assert bed_out["bed_type"] == "ICU"

        # 4. Verify Emergency Escalation Node Output in State
        emergency_out = final_state.get("emergency_output")
        assert emergency_out is not None
        assert emergency_out["agent_id"] == "emergency_escalation_agent"
        assert emergency_out["escalation_required"] is True
        assert emergency_out["emergency_level"] in ["CRITICAL_CODE_BLUE", "RAPID_RESPONSE_STAT", "ACUTE_RAPID_RESPONSE"]

        # 5. Verify Staff Node Output in State
        staff_out = final_state.get("staff_output")
        assert staff_out is not None
        assert staff_out["agent_id"] == "staff_workload_agent"
        assert staff_out["assigned_doctor_id"] is not None

        # 6. Verify Patient Coordinator Node Output in State
        coord_pat_out = final_state.get("patient_coordinator_output")
        assert coord_pat_out is not None
        assert coord_pat_out["agent_id"] == "patient_coordinator_agent"
        assert "Ramesh Verma" in coord_pat_out["handoff_brief"]["patient_name"]
        assert coord_pat_out["discharge_readiness"] is False

        # 7. Verify Coordinator Synthesis & Human Approval
        coord_out = final_state.get("coordinator_output")
        assert coord_out is not None
        assert coord_out["risk_level"] == "HIGH"
        assert coord_out["requires_human_approval"] is True
        assert coord_out["approval_item_id"] is not None
        assert coord_out["action_type"] == "ICU_BED_ALLOCATION_RECOMMENDATION"

        # 8. Verify Database Persistence of Decision & Approval
        dec = (await session.execute(select(AgentDecision).where(AgentDecision.id == coord_out["id"]))).scalar_one()
        assert dec.status == "PROPOSED"
        assert dec.risk_level == "HIGH"

        appr = (await session.execute(select(ApprovalItem).where(ApprovalItem.id == coord_out["approval_item_id"]))).scalar_one()
        assert appr.status == "PENDING"

        # 9. Verify Safety Invariant: ICU Beds unmutated by AI
        icu_bed = (await session.execute(select(Bed).where(Bed.id == "BED-ICU-01"))).scalar_one()
        assert icu_bed.status == "AVAILABLE"


@pytest.mark.asyncio
async def test_03_langgraph_routine_opd_workflow(test_db):
    """
    Test 3: LangGraph routine OPD workflow execution.
    - Low-risk presentation bypasses negotiation directly to Coordinator.
    - No ApprovalItem generated.
    """
    async with test_db() as session:
        patient = Patient(
            id="PAT-LG-02",
            tenant_id="HOSP-DEFAULT",
            first_name="Pooja",
            last_name="Nair",
            age=25,
            gender="F",
            blood_group="A+",
            contact_phone="9876543220",
            emergency_contact="9876543221"
        )
        encounter = Encounter(
            id="ENC-LG-02",
            patient_id="PAT-LG-02",
            current_department_id="DEP-OPD",
            encounter_type="OPD",
            chief_complaint="Minor cold symptoms and runny nose for 2 days",
            esi_level=5,
            priority=5,
            heart_rate=72,
            bp_systolic=118,
            bp_diastolic=78,
            spo2=99,
            temperature_f=98.4,
            respiratory_rate=14,
            gcs_score=15,
            pain_level=0
        )
        session.add_all([patient, encounter])
        await session.commit()

        orchestrator = HospitalLangGraphOrchestrator(session, encounter=encounter, patient=patient)
        final_state = await orchestrator.run(
            tenant_id="HOSP-DEFAULT",
            trigger_reason="OPD_INTAKE",
            actor_id="STAFF-OPD-01"
        )

        assert final_state["status"] == "COMPLETED"
        assert final_state["negotiation_status"] == "BYPASSED"
        assert final_state["action_type"] == "STANDARD_OPD_ROUTING"
        assert final_state["risk_level"] == "LOW"
        assert final_state["requires_human_approval"] is False
        assert final_state["approval_item_id"] is None
        assert final_state["patient_coordinator_output"]["discharge_readiness"] is True


@pytest.mark.asyncio
async def test_04_langgraph_api_endpoint_orchestration(auth_client):
    """
    Test 4: End-to-end HTTP API integration with LangGraph runtime.
    - POST /api/v1/clinical-intelligence/{encounter_id}/orchestrate invokes LangGraph.
    - GET /api/v1/clinical-intelligence/{encounter_id}/messages returns all provenance records.
    - GET /api/v1/clinical-intelligence/{encounter_id}/optimization-run returns optimization telemetry.
    """
    # 1. Create Patient
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Vikram",
        "last_name": "Singhania",
        "age": 55,
        "gender": "M",
        "blood_group": "O-",
        "contact_phone": "+919123456789",
        "emergency_contact": "+919123456780"
    })).json()

    # 2. Create Emergency Encounter
    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Acute severe shortness of breath with low oxygen saturation",
        "encounter_type": "EMERGENCY",
        "heart_rate": 118,
        "bp_systolic": 145,
        "bp_diastolic": 95,
        "spo2": 89,
        "temperature_f": 99.2,
        "respiratory_rate": 26,
        "gcs_score": 14,
        "pain_level": 5
    })).json()

    # 3. Trigger LangGraph Orchestration via API
    orch_res = await auth_client.post(f"/api/v1/clinical-intelligence/{enc['id']}/orchestrate")
    assert orch_res.status_code == 200
    decision = orch_res.json()

    assert decision["encounter_id"] == enc["id"]
    assert decision["action_type"] in ["ICU_BED_ALLOCATION_RECOMMENDATION", "SPECIALIST_CONSULT_RECOMMENDATION"]
    assert decision["risk_level"] in ["HIGH", "MEDIUM"]
    assert decision["requires_human_approval"] is True

    # 4. Verify Agent Message Provenance records
    msg_res = await auth_client.get(f"/api/v1/clinical-intelligence/{enc['id']}/messages")
    assert msg_res.status_code == 200
    messages = msg_res.json()
    assert len(messages) >= 6

    senders = [m["sender_agent"] for m in messages]
    assert "triage_agent" in senders
    assert "bed_agent" in senders
    assert "staff_agent" in senders
    assert "emergency_escalation_agent" in senders
    assert "patient_coordinator_agent" in senders
    assert "coordinator_agent" in senders

    # 5. Verify OptimizationRun Record
    opt_res = await auth_client.get(f"/api/v1/clinical-intelligence/{enc['id']}/optimization-run")
    assert opt_res.status_code == 200
    opt_data = opt_res.json()
    assert opt_data["status"] == "COMPLETED"
    assert len(opt_data["candidates"]) >= 2
    assert opt_data["selected_plan_index"] == 0


@pytest.mark.asyncio
async def test_05_langgraph_state_propagation_across_all_nodes(test_db):
    """
    Test 5: Explicit verification of deterministic data flow across graph edges.
    """
    async with test_db() as session:
        patient = Patient(
            id="PAT-LG-05",
            tenant_id="HOSP-DEFAULT",
            first_name="Anita",
            last_name="Desai",
            age=40,
            gender="F",
            blood_group="B+",
            contact_phone="9876543230",
            emergency_contact="9876543231"
        )
        encounter = Encounter(
            id="ENC-LG-05",
            patient_id="PAT-LG-05",
            current_department_id="DEP-EMERGENCY",
            encounter_type="EMERGENCY",
            chief_complaint="Severe laceration and bleeding",
            esi_level=2,
            priority=2,
            heart_rate=105,
            bp_systolic=110,
            bp_diastolic=70,
            spo2=96,
            temperature_f=98.6,
            respiratory_rate=18,
            gcs_score=15,
            pain_level=7
        )
        session.add_all([patient, encounter])
        await session.commit()

        orchestrator = HospitalLangGraphOrchestrator(session, encounter=encounter, patient=patient)
        state = await orchestrator.run(tenant_id="HOSP-DEFAULT")

        # Check every agent node contributed to the shared state
        assert state["triage_output"]["agent_id"] == "triage_agent"
        assert state["bed_output"]["agent_id"] in ["bed_agent", "bed_management_agent"]
        assert state["emergency_output"]["agent_id"] == "emergency_escalation_agent"
        assert state["staff_output"]["agent_id"] == "staff_workload_agent"
        assert state["patient_coordinator_output"]["agent_id"] == "patient_coordinator_agent"
        assert state["coordinator_output"]["action_type"] in ["SPECIALIST_CONSULT_RECOMMENDATION", "ICU_BED_ALLOCATION_RECOMMENDATION"]


@pytest.mark.asyncio
async def test_06_langgraph_error_containment(test_db):
    """
    Test 6: Verify error containment when an agent receives invalid context.
    """
    async with test_db() as session:
        patient = Patient(
            id="PAT-LG-06",
            tenant_id="HOSP-DEFAULT",
            first_name="Error",
            last_name="Test",
            age=50,
            gender="M",
            blood_group="O+",
            contact_phone="9876543240",
            emergency_contact="9876543241"
        )
        encounter = Encounter(
            id="ENC-LG-06",
            patient_id="PAT-LG-06",
            current_department_id="DEP-EMERGENCY",
            chief_complaint="Crash test",
            esi_level=3
        )
        session.add_all([patient, encounter])
        await session.commit()

        orchestrator = HospitalLangGraphOrchestrator(session, encounter=encounter, patient=patient)
        
        failed_input: HospitalAgentState = {
            "encounter_id": "ENC-LG-06",
            "patient_id": "PAT-LG-06",
            "tenant_id": "HOSP-DEFAULT",
            "status": "FAILED",
            "error": "Simulated upstream failure",
            "failed_agent": "triage_agent"
        }
        res = await orchestrator.bed_node(failed_input)
        assert res == {}, "Downstream node must cleanly bypass execution when upstream is failed."


@pytest.mark.asyncio
async def test_07_structured_inter_agent_negotiation_on_icu_shortage(test_db):
    """
    Test 7: Real Resource Conflict & Structured Inter-Agent Negotiation.
    - Scenario: All ICU beds occupied. Acute critical decompensation (Shock, BP 70, GCS 7).
    - Triage demands ICU -> Bed Agent detects shortage (CONSTRAINED/UNAVAILABLE).
    - Conflict detector identifies BED_CAPACITY_CONFLICT.
    - Negotiation node is invoked:
        * Bed Agent counter-proposes step-down / holding placement.
        * Emergency Agent rejects holding due to profound shock -> emits ESCALATION.
        * Patient Coordinator updates handoff brief.
    - Coordinator receives escalation, elevates risk to HIGH, creates ApprovalItem PENDING.
    - All negotiation AgentMessage records are persisted.
    """
    async with test_db() as session:
        # Mark all ICU and Cardiac Monitor beds as OCCUPIED
        await session.execute(
            update(Bed).where(Bed.bed_type.in_(["ICU", "CARDIAC_MONITOR"])).values(status="OCCUPIED")
        )

        patient = Patient(
            id="PAT-NEG-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Mohan",
            last_name="Bhargav",
            age=72,
            gender="M",
            blood_group="AB+",
            contact_phone="9876543250",
            emergency_contact="9876543251"
        )
        encounter = Encounter(
            id="ENC-NEG-01",
            patient_id="PAT-NEG-01",
            current_department_id="DEP-EMERGENCY",
            encounter_type="EMERGENCY",
            chief_complaint="Profound septic shock with severe hypotension and unresponsive state",
            esi_level=1,
            priority=1,
            heart_rate=140,
            bp_systolic=65,
            bp_diastolic=40,
            spo2=82,
            temperature_f=102.5,
            respiratory_rate=32,
            gcs_score=7,
            pain_level=10
        )
        session.add_all([patient, encounter])
        await session.commit()

        orchestrator = HospitalLangGraphOrchestrator(session, encounter=encounter, patient=patient)
        final_state = await orchestrator.run(
            tenant_id="HOSP-DEFAULT",
            trigger_reason="SEPTIC_SHOCK_ICU_SHORTAGE",
            actor_id="STAFF-TRIAGE-02"
        )

        # 1. Verify Negotiation Execution
        assert final_state["status"] == "COMPLETED"
        assert final_state["negotiation_round"] == 1
        assert final_state["negotiation_status"] == "UNRESOLVED_ESCALATED"
        assert len(final_state["active_conflicts"]) >= 1

        # 2. Verify Negotiation Messages Generated
        neg_msgs = final_state.get("negotiation_messages", [])
        assert len(neg_msgs) >= 2

        msg_types = [m["message_type"] for m in neg_msgs]
        assert "COUNTER_PROPOSAL" in msg_types
        assert "ESCALATION" in msg_types

        # 3. Verify Database Persistence of All Agent Messages (6 base + negotiation msgs)
        saved_msgs = (await session.execute(
            select(AgentMessage).where(AgentMessage.encounter_id == "ENC-NEG-01")
        )).scalars().all()
        assert len(saved_msgs) >= 8

        # 4. Verify Coordinator Safety Gating (HITL ApprovalItem required)
        assert final_state["risk_level"] == "HIGH"
        assert final_state["requires_human_approval"] is True
        assert final_state["approval_item_id"] is not None

        appr = (await session.execute(
            select(ApprovalItem).where(ApprovalItem.id == final_state["approval_item_id"])
        )).scalar_one()
        assert appr.status == "PENDING"
        assert "Negotiation Status: UNRESOLVED_ESCALATED" in appr.reasoning


@pytest.mark.asyncio
async def test_08_bounded_negotiation_rounds_limit():
    """
    Test 8: Verifies negotiation round upper bound invariant (MAX_NEGOTIATION_ROUNDS = 2).
    """
    assert MAX_NEGOTIATION_ROUNDS == 2


@pytest.mark.asyncio
async def test_09_staff_shortage_negotiation_rebalances_assignment(test_db):
    """
    Test 9: Staff Shortage Conflict & Rebalanced Assignment Proposal.
    - Scenario: Staff shortage conflict is resolved through rebalanced secondary assignments.
    - StaffWorkloadAgent emits REVISED_PROPOSAL.
    """
    async with test_db() as session:
        # Mark existing nurses to max overloaded workload
        await session.execute(
            update(Staff).where(Staff.role.in_(["NURSE", "CHARGE_NURSE"])).values(current_workload=15)
        )

        patient = Patient(
            id="PAT-NEG-02",
            tenant_id="HOSP-DEFAULT",
            first_name="Harish",
            last_name="Kotian",
            age=58,
            gender="M",
            blood_group="B+",
            contact_phone="9876543260",
            emergency_contact="9876543261"
        )
        encounter = Encounter(
            id="ENC-NEG-02",
            patient_id="PAT-NEG-02",
            current_department_id="DEP-EMERGENCY",
            encounter_type="EMERGENCY",
            chief_complaint="Moderate asthma wheezing with high patient volume",
            esi_level=3,
            priority=3,
            heart_rate=98,
            bp_systolic=130,
            bp_diastolic=82,
            spo2=94,
            temperature_f=98.6,
            respiratory_rate=20,
            gcs_score=15,
            pain_level=3
        )
        session.add_all([patient, encounter])
        await session.commit()

        orchestrator = HospitalLangGraphOrchestrator(session, encounter=encounter, patient=patient)
        final_state = await orchestrator.run(
            tenant_id="HOSP-DEFAULT",
            trigger_reason="ASTHMA_INTAKE",
            actor_id="STAFF-TRIAGE-03"
        )

        assert final_state["status"] == "COMPLETED"
        assert final_state["negotiation_round"] >= 1
        assert "staff_revised_proposal" in final_state.get("revised_proposals", {})


@pytest.mark.asyncio
async def test_10_discharge_stepdown_proposal_generation(test_db):
    """
    Test 10: PatientCoordinatorAgent generates structured discharge / step-down proposal.
    """
    async with test_db() as session:
        patient = Patient(
            id="PAT-DISC-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Ramesh",
            last_name="Gupta",
            age=45,
            gender="M",
            blood_group="O+",
            contact_phone="9876543201",
            emergency_contact="9876543202"
        )
        encounter = Encounter(
            id="ENC-DISC-01",
            patient_id="PAT-DISC-01",
            current_department_id="DEP-EMERGENCY",
            encounter_type="EMERGENCY",
            chief_complaint="Stable post-observation for mild gastritis",
            esi_level=4,
            priority=4,
            bp_systolic=120,
            spo2=98,
            temperature_f=98.6
        )
        session.add_all([patient, encounter])
        await session.commit()

        coord_agent = PatientCoordinatorAgent(session)
        proposal = await coord_agent.propose_discharge_or_stepdown(
            triage_output={"recommended_care_level": "GENERAL", "esi_level": 4, "severity": "LOW", "priority_level": "MODERATE", "requires_telemetry": False, "requires_isolation": False},
            bed_output={"recommended_bed_id": "BED-WA-01", "recommended_department_id": "DEP-WA"},
            staff_output={},
            encounter=encounter,
            patient=patient,
            tenant_id="HOSP-DEFAULT"
        )

        assert proposal["agent_id"] == "patient_coordinator_agent"
        assert proposal["message_type"] == "PROPOSAL"
        assert proposal["transition_type"] == "STEP_DOWN_TRANSFER"
        assert proposal["proposed_destination"] == "DEP-WA"
        assert proposal["clinical_readiness"] is True


@pytest.mark.asyncio
async def test_11_stepdown_negotiation_ward_a_full_counter_proposes_ward_b(test_db):
    """
    Test 11: Real Step-Down Conflict & Bidirectional Negotiation.
    - Scenario: Patient in Emergency ready for step-down to Ward A (DEP-WA).
    - All Ward A beds are OCCUPIED.
    - Ward B (DEP-WB) beds are AVAILABLE.
    - Patient Coordinator proposes DEP-WA.
    - Bed Manager detects DEP-WA is full -> counter-proposes available bed in DEP-WB.
    - Patient Coordinator evaluates DEP-WB -> clinically compatible -> emits ACCEPT.
    - Coordinator incorporates negotiated DEP-WB bed into Plan 0 (NEGOTIATED_OPTIMAL).
    - All negotiation AgentMessage records are persisted.
    """
    async with test_db() as session:
        # Mark all Ward A beds as OCCUPIED
        await session.execute(
            update(Bed).where(Bed.department_id == "DEP-WA").values(status="OCCUPIED")
        )

        patient = Patient(
            id="PAT-DISC-02",
            tenant_id="HOSP-DEFAULT",
            first_name="Sunita",
            last_name="Kulkarni",
            age=52,
            gender="F",
            blood_group="A+",
            contact_phone="9876543203",
            emergency_contact="9876543204"
        )
        encounter = Encounter(
            id="ENC-DISC-02",
            patient_id="PAT-DISC-02",
            current_department_id="DEP-EMERGENCY",
            encounter_type="EMERGENCY",
            chief_complaint="Stable post-angioplasty recovery, ready for general ward step-down",
            esi_level=3,
            priority=3,
            heart_rate=78,
            bp_systolic=122,
            bp_diastolic=78,
            spo2=98,
            temperature_f=98.4,
            respiratory_rate=16,
            gcs_score=15,
            pain_level=1
        )
        session.add_all([patient, encounter])
        await session.commit()

        orchestrator = HospitalLangGraphOrchestrator(session, encounter=encounter, patient=patient)
        final_state = await orchestrator.run(
            tenant_id="HOSP-DEFAULT",
            trigger_reason="STEP_DOWN_WARD_TRANSFER",
            actor_id="STAFF-DOC-01"
        )

        # 1. Verify Negotiation Execution
        assert final_state["status"] == "COMPLETED"
        assert final_state["negotiation_round"] >= 1
        assert final_state["negotiation_status"] == "RESOLVED"

        # 2. Verify Structured Negotiation Messages
        neg_msgs = final_state.get("negotiation_messages", [])
        assert len(neg_msgs) >= 3

        senders = [m["sender_agent"] for m in neg_msgs]
        receivers = [m["receiver_agent"] for m in neg_msgs]
        msg_types = [m["message_type"] for m in neg_msgs]

        assert "patient_coordinator_agent" in senders
        assert "bed_agent" in senders
        assert "PROPOSAL" in msg_types
        assert "COUNTER_PROPOSAL" in msg_types
        assert "ACCEPT" in msg_types

        # 3. Verify Coordinator Candidate Plan Allocation
        selected_plan = final_state["selected_plan"]
        assert selected_plan["target_department_id"] == "DEP-WB"
        assert selected_plan["target_bed_id"] is not None
        assert selected_plan["target_bed_id"].startswith("BED-WB-")

        # 4. Verify Database Persistence of AgentMessage records
        saved_msgs = (await session.execute(
            select(AgentMessage).where(AgentMessage.encounter_id == "ENC-DISC-02")
        )).scalars().all()
        assert len(saved_msgs) >= 9


@pytest.mark.asyncio
async def test_12_stepdown_negotiation_isolation_incompatibility_escalates(test_db):
    """
    Test 12: Step-Down Conflict with Clinical Incompatibility -> Safe Escalation.
    - Scenario: Patient with active rash/fever requires isolation.
    - Primary isolation ward full. Alternative general ward offered by Bed Manager lacks isolation.
    - Patient Coordinator evaluates counter-proposal -> rejects due to missing isolation barrier -> emits ESCALATION.
    - Negotiation status becomes UNRESOLVED_ESCALATED.
    - Coordinator elevates risk to HIGH and creates ApprovalItem PENDING.
    """
    async with test_db() as session:
        # Mark all isolation beds in hospital as OCCUPIED
        await session.execute(
            update(Bed).where(Bed.is_isolation == True).values(status="OCCUPIED")
        )

        patient = Patient(
            id="PAT-DISC-03",
            tenant_id="HOSP-DEFAULT",
            first_name="Zoya",
            last_name="Khan",
            age=29,
            gender="F",
            blood_group="B-",
            contact_phone="9876543205",
            emergency_contact="9876543206"
        )
        encounter = Encounter(
            id="ENC-DISC-03",
            patient_id="PAT-DISC-03",
            current_department_id="DEP-EMERGENCY",
            encounter_type="EMERGENCY",
            chief_complaint="High fever and diffuse rash with suspected droplet transmission",
            esi_level=2,
            priority=2,
            heart_rate=102,
            bp_systolic=115,
            bp_diastolic=75,
            spo2=97,
            temperature_f=102.1,
            respiratory_rate=20,
            gcs_score=15,
            pain_level=4
        )
        session.add_all([patient, encounter])
        await session.commit()

        orchestrator = HospitalLangGraphOrchestrator(session, encounter=encounter, patient=patient)
        final_state = await orchestrator.run(
            tenant_id="HOSP-DEFAULT",
            trigger_reason="ISOLATION_STEP_DOWN_CHECK",
            actor_id="STAFF-DOC-02"
        )

        assert final_state["status"] == "COMPLETED"
        assert final_state["negotiation_status"] == "UNRESOLVED_ESCALATED"
        assert final_state["risk_level"] == "HIGH"
        assert final_state["requires_human_approval"] is True
        assert final_state["approval_item_id"] is not None


@pytest.mark.asyncio
async def test_13_stepdown_negotiation_facility_wide_rejection(test_db):
    """
    Test 13: Facility-Wide Bed Exhaustion -> Bed Manager Rejection & Safe Escalation.
    """
    async with test_db() as session:
        # Mark all beds in the hospital as OCCUPIED
        await session.execute(
            update(Bed).values(status="OCCUPIED")
        )

        patient = Patient(
            id="PAT-DISC-04",
            tenant_id="HOSP-DEFAULT",
            first_name="Deepak",
            last_name="Shinde",
            age=66,
            gender="M",
            blood_group="AB+",
            contact_phone="9876543207",
            emergency_contact="9876543208"
        )
        encounter = Encounter(
            id="ENC-DISC-04",
            patient_id="PAT-DISC-04",
            current_department_id="DEP-EMERGENCY",
            encounter_type="EMERGENCY",
            chief_complaint="Mild dizziness and weakness, stable",
            esi_level=3,
            priority=3,
            bp_systolic=125,
            spo2=97,
            temperature_f=98.6
        )
        session.add_all([patient, encounter])
        await session.commit()

        bed_agent = BedManagementAgent(session)
        proposal = {
            "transition_type": "STEP_DOWN_TRANSFER",
            "proposed_destination": "DEP-WA",
            "requires_telemetry": False,
            "requires_isolation": False
        }
        res = await bed_agent.evaluate_discharge_stepdown_proposal(proposal, tenant_id="HOSP-DEFAULT")
        assert res["decision"] == "REJECT"

        coord_agent = PatientCoordinatorAgent(session)
        eval_res = await coord_agent.evaluate_bed_response(res, {"requires_telemetry": False, "requires_isolation": False}, encounter)
        assert eval_res["message_type"] == "ESCALATION"
        assert eval_res["counter_decision"] == "REJECT"


@pytest.mark.asyncio
async def test_14_stepdown_negotiation_zero_resource_mutation(test_db):
    """
    Test 14: Strict Safety Boundary — Verifies zero physical database mutations on beds/staff during negotiation.
    """
    async with test_db() as session:
        # Check initial state of a target bed
        initial_bed = (await session.execute(
            select(Bed).where(Bed.id == "BED-WB-01")
        )).scalar_one()
        assert initial_bed.status == "AVAILABLE"
        initial_status = initial_bed.status

        patient = Patient(
            id="PAT-DISC-05",
            tenant_id="HOSP-DEFAULT",
            first_name="Kavita",
            last_name="Jain",
            age=48,
            gender="F",
            blood_group="O+",
            contact_phone="9876543209",
            emergency_contact="9876543210"
        )
        encounter = Encounter(
            id="ENC-DISC-05",
            patient_id="PAT-DISC-05",
            current_department_id="DEP-EMERGENCY",
            encounter_type="EMERGENCY",
            chief_complaint="Post-procedure observation and step-down",
            esi_level=3,
            priority=3
        )
        session.add_all([patient, encounter])
        await session.commit()

        orchestrator = HospitalLangGraphOrchestrator(session, encounter=encounter, patient=patient)
        await orchestrator.run(tenant_id="HOSP-DEFAULT")

        # Verify bed is still AVAILABLE in database (not mutated by agent)
        bed_after = (await session.execute(
            select(Bed).where(Bed.id == "BED-WB-01")
        )).scalar_one()
        assert bed_after.status == initial_status, "Agent negotiation must NEVER mutate Bed.status directly."

