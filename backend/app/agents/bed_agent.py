"""
Autonomous Bed & Resource Inventory Agent (Bed Manager Agent).
Evaluates real-time bed capacity, ward type matching, telemetry/isolation requirements,
and step-down transitions to propose feasible candidate bed assignments without mutating resource state.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.bed import Bed
from app.models.department import Department
from app.models.equipment import Equipment
from app.utils.datetime_utils import utc_now_iso
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class BedManagerAgent(BaseAgent):
    """
    Autonomous Bed & Resource Inventory Agent (Bed Manager Agent).
    Evaluates real-time bed capacity, ward type matching, telemetry/isolation requirements,
    and step-down transitions to propose feasible candidate bed assignments without mutating resource state.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db=db, agent_id="bed_manager_agent", name="Bed & Resource Inventory Agent")

    async def evaluate(
        self,
        triage_output: Dict[str, Any],
        encounter: Encounter,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Queries live bed availability and evaluates suitability for triage recommendation.
        """
        care_level = triage_output.get("recommended_care_level", "GENERAL")
        requires_isolation = triage_output.get("requires_isolation", False)
        requires_telemetry = triage_output.get("requires_telemetry", False)

        # Map care level to bed types
        target_bed_types = {
            "ICU": ["ICU", "CARDIAC_MONITOR"],
            "EMERGENCY": ["EMERGENCY", "ICU", "GENERAL"],
            "GENERAL": ["GENERAL", "EMERGENCY"],
            "OUTPATIENT": []
        }.get(care_level, ["GENERAL"])

        if care_level == "OUTPATIENT":
            return {
                "agent_id": "bed_manager_agent",
                "status": "NOT_REQUIRED",
                "recommended_bed_id": None,
                "recommended_department_id": "DEP-OPD",
                "bed_type": None,
                "alternative_beds": [],
                "occupancy_rate": 0.0,
                "feasibility": "FEASIBLE",
                "rationale": "Outpatient encounter does not require inpatient bed reservation.",
                "timestamp": utc_now_iso()
            }

        # Query all available beds belonging to this tenant's departments
        query = (
            select(Bed)
            .join(Department, Bed.department_id == Department.id)
            .where(
                and_(
                    Department.tenant_id == tenant_id,
                    Bed.status == "AVAILABLE"
                )
            )
        )
        res = await self.db.execute(query)
        available_beds: List[Bed] = res.scalars().all()

        # Query total bed inventory for occupancy stats for this tenant
        total_res = await self.db.execute(
            select(func.count(Bed.id))
            .join(Department, Bed.department_id == Department.id)
            .where(Department.tenant_id == tenant_id)
        )
        total_beds = total_res.scalar() or 1
        occupied_res = await self.db.execute(
            select(func.count(Bed.id))
            .join(Department, Bed.department_id == Department.id)
            .where(
                and_(
                    Department.tenant_id == tenant_id,
                    Bed.status.in_(["OCCUPIED", "RESERVED"])
                )
            )
        )
        occupied_beds = occupied_res.scalar() or 0
        occupancy_rate = round(occupied_beds / total_beds, 2)
        department_counts = await self.db.execute(
            select(Bed.department_id, func.count(Bed.id))
            .join(Department, Bed.department_id == Department.id)
            .where(Department.tenant_id == tenant_id)
            .group_by(Bed.department_id)
        )
        capacity_by_department = dict(department_counts.all())
        department_occupancy_rows = await self.db.execute(
            select(Bed.department_id, func.count(Bed.id))
            .join(Department, Bed.department_id == Department.id)
            .where(Department.tenant_id == tenant_id, Bed.status.in_(["OCCUPIED", "RESERVED"]))
            .group_by(Bed.department_id)
        )
        occupied_by_department = dict(department_occupancy_rows.all())
        occupancy_by_department = {
            department_id: round(occupied_by_department.get(department_id, 0) / max(count, 1), 2)
            for department_id, count in capacity_by_department.items()
        }

        # Match optimal candidate beds
        matching_beds = [b for b in available_beds if b.bed_type in target_bed_types]
        if requires_isolation:
            matching_beds = [b for b in matching_beds if b.is_isolation]

        if requires_telemetry:
            matching_beds = [b for b in matching_beds if b.has_telemetry or b.bed_type == "ICU"]

        equipment_ready = True
        if triage_output.get("requires_ventilator"):
            equipment_result = await self.db.execute(
                select(func.count(Equipment.id))
                .join(Department, Equipment.department_id == Department.id)
                .where(Department.tenant_id == tenant_id, Equipment.resource_type == "VENTILATOR", Equipment.status == "AVAILABLE")
            )
            equipment_ready = (equipment_result.scalar() or 0) > 0
            if not equipment_ready:
                matching_beds = []

        if matching_beds:
            primary_bed = matching_beds[0]
            alt_beds = [b.id for b in matching_beds[1:4]]
            feasibility = "FEASIBLE"
            rationale = (
                f"Optimal bed {primary_bed.id} ({primary_bed.bed_type}) identified in department {primary_bed.department_id}. "
                f"{len(matching_beds)} compatible beds available (Facility Occupancy: {occupancy_rate*100:.0f}%)."
            )
            rec_bed_id = primary_bed.id
            rec_dept_id = primary_bed.department_id
            rec_bed_type = primary_bed.bed_type
        elif available_beds:
            alt_beds = []
            feasibility = "CONSTRAINED"
            rationale = "No bed satisfies all requested clinical constraints; no fallback bed is recommended. " + ("No available ventilator is present." if not equipment_ready else "Review capacity or clinical requirements.")
            rec_bed_id = None
            rec_dept_id = None
            rec_bed_type = None
        else:
            feasibility = "UNAVAILABLE"
            rationale = f"Critical bed shortage: zero available beds across all hospital units (Occupancy: 100%). Surge holding area required."
            rec_bed_id = None
            rec_dept_id = "DEP-ER"
            rec_bed_type = "SURGE_HOLDING"
            alt_beds = []

        return {
            "agent_id": "bed_manager_agent",
            "status": "COMPLETED",
            "recommended_bed_id": rec_bed_id,
            "recommended_department_id": rec_dept_id,
            "bed_type": rec_bed_type,
            "alternative_beds": alt_beds,
            "occupancy_rate": occupancy_rate,
            "feasibility": feasibility,
            "capacity_by_department": capacity_by_department,
            "occupancy_by_department": occupancy_by_department,
            "available_compatible_beds": len(matching_beds),
            "ventilator_required": bool(triage_output.get("requires_ventilator")),
            "ventilator_available": equipment_ready,
            "rationale": rationale,
            "timestamp": utc_now_iso()
        }

    async def propose_counter_proposal(
        self,
        triage_output: Dict[str, Any],
        initial_bed_output: Dict[str, Any],
        encounter: Encounter,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Formulates a structured counter-proposal when optimal bed tier is constrained or unavailable.
        Evaluates step-down telemetry units, observation surge beds, or emergency holding areas.
        """
        alt_beds = initial_bed_output.get("alternative_beds", [])
        if alt_beds:
            proposed_bed_id = alt_beds[0]
            bed_obj = (
                await self.db.execute(
                    select(Bed)
                    .join(Department, Bed.department_id == Department.id)
                    .where(
                        and_(
                            Department.tenant_id == tenant_id,
                            Bed.id == proposed_bed_id
                        )
                    )
                )
            ).scalar_one_or_none()
            dept_id = bed_obj.department_id if bed_obj else "DEP-WA"
            bed_type = bed_obj.bed_type if bed_obj else "STEP_DOWN"
            counter_rationale = f"Propose step-down bed {proposed_bed_id} ({bed_type}) in {dept_id} with continuous vital monitoring."
        else:
            proposed_bed_id = None
            dept_id = "DEP-ER"
            bed_type = "EMERGENCY_HOLDING"
            counter_rationale = "Propose emergency holding area placement with STAT clinical consultation and continuous telemetry."

        return {
            "agent_id": "bed_manager_agent",
            "message_type": "COUNTER_PROPOSAL",
            "proposed_bed_id": proposed_bed_id,
            "proposed_department_id": dept_id,
            "proposed_bed_type": bed_type,
            "rationale": counter_rationale,
            "timestamp": utc_now_iso()
        }

    async def evaluate_discharge_stepdown_proposal(
        self,
        proposal: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Evaluates a Patient Care Coordinator discharge or step-down transfer proposal.
        Checks real-time bed inventory in the requested target department belonging to this tenant.
        If unavailable, formulates a genuine alternative counter-proposal using available beds belonging to this tenant.
        """
        trans_type = proposal.get("transition_type")
        if trans_type == "OUTPATIENT_DISCHARGE":
            return {
                "agent_id": "bed_manager_agent",
                "decision": "ACCEPT",
                "department_id": "DEP-OPD",
                "allocated_bed_id": None,
                "rationale": "Outpatient discharge confirmed; inpatient bed de-allocated or not required.",
                "timestamp": utc_now_iso()
            }

        target_dept = proposal.get("proposed_destination", "DEP-WA")
        req_iso = proposal.get("requires_isolation", False)
        req_telem = proposal.get("requires_telemetry", False)

        # 1. Query available beds in target department belonging to this tenant
        stmt = (
            select(Bed)
            .join(Department, Bed.department_id == Department.id)
            .where(
                and_(
                    Department.tenant_id == tenant_id,
                    Bed.department_id == target_dept,
                    Bed.status == "AVAILABLE"
                )
            )
        )
        res = await self.db.execute(stmt)
        target_beds: List[Bed] = res.scalars().all()

        if req_iso:
            target_beds = [b for b in target_beds if b.is_isolation]
        if req_telem:
            target_beds = [b for b in target_beds if b.has_telemetry or b.bed_type == "ICU"]

        if target_beds:
            allocated = target_beds[0]
            return {
                "agent_id": "bed_manager_agent",
                "decision": "ACCEPT",
                "allocated_bed_id": allocated.id,
                "department_id": target_dept,
                "bed_type": allocated.bed_type,
                "has_telemetry": allocated.has_telemetry,
                "is_isolation": allocated.is_isolation,
                "rationale": f"Accepted step-down assignment to bed {allocated.id} ({allocated.bed_type}) in {target_dept}.",
                "timestamp": utc_now_iso()
            }

        # 2. If target department has no matching beds, find alternative general / step-down ward bed belonging to this tenant
        alt_stmt = (
            select(Bed)
            .join(Department, Bed.department_id == Department.id)
            .where(
                and_(
                    Department.tenant_id == tenant_id,
                    Bed.department_id != target_dept,
                    Department.code != "ER",
                    Bed.department_id != "DEP-ER",
                    Bed.bed_type.in_(["GENERAL", "STEP_DOWN", "CARDIAC_MONITOR"]),
                    Bed.status == "AVAILABLE"
                )
            )
        )
        alt_res = await self.db.execute(alt_stmt)
        alt_beds: List[Bed] = alt_res.scalars().all()

        if req_iso:
            alt_iso_beds = [b for b in alt_beds if b.is_isolation]
            if alt_iso_beds:
                alt_beds = alt_iso_beds
        if req_telem:
            alt_telem_beds = [b for b in alt_beds if b.has_telemetry or b.bed_type in ["ICU", "CARDIAC_MONITOR"]]
            if alt_telem_beds:
                alt_beds = alt_telem_beds

        if alt_beds:
            counter_bed = alt_beds[0]
            return {
                "agent_id": "bed_manager_agent",
                "decision": "COUNTER_PROPOSAL",
                "counter_bed_id": counter_bed.id,
                "counter_department_id": counter_bed.department_id,
                "counter_bed_type": counter_bed.bed_type,
                "has_telemetry": counter_bed.has_telemetry,
                "is_isolation": counter_bed.is_isolation,
                "rationale": f"Target department {target_dept} has no available matching beds. Counter-proposing bed {counter_bed.id} ({counter_bed.bed_type}) in {counter_bed.department_id}.",
                "timestamp": utc_now_iso()
            }

        # 3. No available beds facility-wide
        return {
            "agent_id": "bed_manager_agent",
            "decision": "REJECT",
            "rationale": f"Target department {target_dept} and all secondary hospital wards have zero available beds.",
            "timestamp": utc_now_iso()
        }


# Alias for backward compatibility
BedManagementAgent = BedManagerAgent
