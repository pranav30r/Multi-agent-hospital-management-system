"""
Unit tests for the modular hospital agents package (app.agents)
and the backward-compatible facade (app.services.agent_orchestrator).
"""

import pytest
from app.agents.base import BaseAgent
import app.agents as modular_agents
import app.services.agent_orchestrator as orchestrator_facade

from app.agents import (
    BaseAgent,
    TriageAgent,
    BedManagerAgent,
    BedManagementAgent,
    StaffSchedulerAgent,
    StaffWorkloadAgent,
    EmergencyEscalationAgent,
    PatientCoordinatorAgent,
    CoordinatorAgent,
)
from app.models.patient import Patient, Encounter
from app.models.department import Department


def test_01_modular_agent_imports():
    """Verify all 5 specialized agents, the coordinator, and compatibility aliases import from app.agents."""
    assert TriageAgent is not None
    assert BedManagerAgent is not None
    assert BedManagementAgent is not None
    assert StaffSchedulerAgent is not None
    assert StaffWorkloadAgent is not None
    assert EmergencyEscalationAgent is not None
    assert PatientCoordinatorAgent is not None
    assert CoordinatorAgent is not None


def test_02_backward_compatible_facade_imports():
    """Verify app.services.agent_orchestrator re-exports the exact identical agent classes."""
    assert orchestrator_facade.TriageAgent is TriageAgent
    assert orchestrator_facade.BedManagerAgent is BedManagerAgent
    assert orchestrator_facade.BedManagementAgent is BedManagementAgent
    assert orchestrator_facade.StaffSchedulerAgent is StaffSchedulerAgent
    assert orchestrator_facade.StaffWorkloadAgent is StaffWorkloadAgent
    assert orchestrator_facade.EmergencyEscalationAgent is EmergencyEscalationAgent
    assert orchestrator_facade.PatientCoordinatorAgent is PatientCoordinatorAgent
    assert orchestrator_facade.CoordinatorAgent is CoordinatorAgent
    assert orchestrator_facade.MultiAgentOrchestratorService is not None


def test_03_base_agent_inheritance():
    """Verify all 5 specialized agents and coordinator inherit from BaseAgent."""
    agent_classes = [
        TriageAgent,
        BedManagerAgent,
        BedManagementAgent,
        StaffSchedulerAgent,
        StaffWorkloadAgent,
        EmergencyEscalationAgent,
        PatientCoordinatorAgent,
        CoordinatorAgent,
    ]
    for cls in agent_classes:
        assert issubclass(cls, BaseAgent), f"{cls.__name__} must be a subclass of BaseAgent"


def test_04_compatibility_aliases():
    """Verify backward-compatible class aliases match original classes."""
    assert BedManagementAgent is BedManagerAgent
    assert StaffWorkloadAgent is StaffSchedulerAgent


@pytest.mark.asyncio
async def test_05_modular_agent_attributes(test_db):
    """Verify each modular agent assigns standard agent_id, name, and db session."""
    async with test_db() as session:
        triage = TriageAgent(session)
        assert triage.agent_id == "triage_agent"
        assert "Triage" in triage.name
        assert triage.db is session

        bed = BedManagerAgent(session)
        assert bed.agent_id == "bed_manager_agent"
        assert bed.db is session

        staff = StaffSchedulerAgent(session)
        assert staff.agent_id == "staff_scheduler_agent"
        assert staff.db is session

        emergency = EmergencyEscalationAgent(session)
        assert emergency.agent_id == "emergency_escalation_agent"
        assert emergency.db is session

        coord = PatientCoordinatorAgent(session)
        assert coord.agent_id == "patient_coordinator_agent"
        assert coord.db is session

        orchestrator = CoordinatorAgent(session)
        assert orchestrator.agent_id == "coordinator_agent"
        assert orchestrator.db is session


@pytest.mark.asyncio
async def test_06_direct_triage_agent_evaluation(test_db):
    """Verify TriageAgent evaluate method runs directly through the modular package."""
    async with test_db() as session:
        dept = await session.get(Department, "DEP-ER")
        if not dept:
            dept = Department(
                id="DEP-ER",
                tenant_id="HOSP-DEFAULT",
                name="Emergency Department",
                code="ER",
                total_beds=6
            )
            session.add(dept)
            await session.flush()

        patient = Patient(
            id="PAT-MOD-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Anita",
            last_name="Desai",
            age=45,
            gender="F",
            blood_group="A+",
            contact_phone="9876543200",
            emergency_contact="9876543201"
        )
        session.add(patient)
        encounter = Encounter(
            id="ENC-MOD-01",
            patient_id="PAT-MOD-01",
            current_department_id=dept.id,
            encounter_type="EMERGENCY",
            chief_complaint="Severe crushing chest pain radiating to left jaw",
            bp_systolic=165,
            bp_diastolic=105,
            heart_rate=120,
            spo2=91,
            esi_level=2
        )
        session.add(encounter)
        await session.commit()

        triage_agent = TriageAgent(session)
        res = await triage_agent.evaluate(encounter=encounter, patient=patient)

        assert res["agent_id"] == "triage_agent"
        assert res["esi_level"] == 2
        assert res["recommended_care_level"] in ["EMERGENCY", "ICU"]
        assert res["clinical_urgency"] in ["URGENT", "IMMEDIATE"]


@pytest.mark.asyncio
async def test_07_direct_emergency_agent_evaluation(test_db):
    """Verify EmergencyEscalationAgent evaluate method runs directly through the modular package."""
    async with test_db() as session:
        dept = await session.get(Department, "DEP-ER")
        if not dept:
            dept = Department(
                id="DEP-ER",
                tenant_id="HOSP-DEFAULT",
                name="Emergency Department",
                code="ER",
                total_beds=6
            )
            session.add(dept)
            await session.flush()

        patient = Patient(
            id="PAT-MOD-02",
            tenant_id="HOSP-DEFAULT",
            first_name="Vikram",
            last_name="Singh",
            age=72,
            gender="M",
            blood_group="O+",
            contact_phone="9876543202",
            emergency_contact="9876543203"
        )
        session.add(patient)
        encounter = Encounter(
            id="ENC-MOD-02",
            patient_id="PAT-MOD-02",
            current_department_id=dept.id,
            encounter_type="EMERGENCY",
            chief_complaint="Cardiac arrest, unresponsiveness",
            bp_systolic=70,
            bp_diastolic=40,
            heart_rate=145,
            spo2=82,
            gcs_score=7,
            esi_level=1
        )
        session.add(encounter)
        await session.commit()

        triage_output = {
            "esi_level": 1,
            "severity": "CRITICAL",
            "score": 9.5,
            "red_flags": [{"code": "RF-SHOCK", "severity": "HIGH", "source": "vitals.bp_systolic"}]
        }

        emergency_agent = EmergencyEscalationAgent(session)
        res = await emergency_agent.evaluate(triage_output=triage_output, encounter=encounter, tenant_id="HOSP-DEFAULT")

        assert res["agent_id"] == "emergency_escalation_agent"
        assert res["escalation_required"] is True
        assert res["emergency_level"] == "CRITICAL_CODE_BLUE"
        assert "ACTIVATE_RAPID_RESPONSE_TEAM" in res["recommended_emergency_actions"]


@pytest.mark.asyncio
async def test_08_multi_agent_orchestrator_service_facade_integrity(test_db):
    """Verify MultiAgentOrchestratorService binds all modular agents properly."""
    async with test_db() as session:
        orchestrator_service = orchestrator_facade.MultiAgentOrchestratorService(session)
        assert isinstance(orchestrator_service.triage_agent, TriageAgent)
        assert isinstance(orchestrator_service.bed_agent, BedManagerAgent)
        assert isinstance(orchestrator_service.staff_agent, StaffSchedulerAgent)
        assert isinstance(orchestrator_service.emergency_agent, EmergencyEscalationAgent)
        assert isinstance(orchestrator_service.patient_coordinator_agent, PatientCoordinatorAgent)
        assert isinstance(orchestrator_service.coordinator, CoordinatorAgent)
