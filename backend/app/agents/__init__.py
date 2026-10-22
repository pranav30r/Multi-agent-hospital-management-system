"""
Hospital Multi-Agent Intelligence Package.

Exports the 5 specialized operational agents, the Coordinator agent, and the BaseAgent abstraction:
1. BaseAgent (app.agents.base)
2. TriageAgent (app.agents.triage_agent)
3. BedManagerAgent / BedManagementAgent (app.agents.bed_agent)
4. StaffSchedulerAgent / StaffWorkloadAgent (app.agents.staff_agent)
5. EmergencyEscalationAgent (app.agents.emergency_agent)
6. PatientCoordinatorAgent (app.agents.patient_coordinator_agent)
7. CoordinatorAgent (app.agents.coordinator_agent)
"""

from app.agents.base import BaseAgent
from app.agents.triage_agent import TriageAgent
from app.agents.bed_agent import BedManagerAgent, BedManagementAgent
from app.agents.staff_agent import StaffSchedulerAgent, StaffWorkloadAgent
from app.agents.emergency_agent import EmergencyEscalationAgent
from app.agents.patient_coordinator_agent import PatientCoordinatorAgent
from app.agents.coordinator_agent import CoordinatorAgent
from app.agents.workflow_agent import ClinicalWorkflowAgent

__all__ = [
    "BaseAgent",
    "TriageAgent",
    "BedManagerAgent",
    "BedManagementAgent",
    "StaffSchedulerAgent",
    "StaffWorkloadAgent",
    "EmergencyEscalationAgent",
    "PatientCoordinatorAgent",
    "CoordinatorAgent",
    "ClinicalWorkflowAgent",
]
