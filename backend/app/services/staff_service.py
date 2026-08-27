import logging
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff import Staff, StaffShift, StaffSkill
from app.models.department import Department
from app.models.agent import AuditLog
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

VALID_STAFF_ROLES = {
    "DOCTOR",
    "NURSE",
    "CHARGE_NURSE",
    "TECHNICIAN",
    "RECEPTIONIST",
    "ADMINISTRATOR"
}

VALID_STAFF_STATUSES = {
    "AVAILABLE",
    "BUSY",
    "ON_BREAK",
    "ON_LEAVE",
    "OFF_SHIFT",
    "EMERGENCY_ASSIGNED"
}

VALID_SHIFT_TYPES = {"MORNING", "AFTERNOON", "NIGHT"}
VALID_SHIFT_STATUSES = {"SCHEDULED", "ACTIVE", "COMPLETED", "CANCELLED"}


class StaffService:
    """
    Application Service for Hospital Staff, Clinical Workforce, Shift Schedules, and Skills.
    Encapsulates staff CRUD, department verification, workload concurrency, shift lifecycles, and skills.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 1. Staff CRUD & Query Operations ───────────────────────────────────

    async def create_staff(
        self,
        id: str,
        first_name: str,
        last_name: str,
        role: str,
        department_id: str,
        actor_id: str,
        specialization: Optional[str] = None,
        max_workload: int = 5,
        skills: Optional[List[str]] = None,
        password_hash: Optional[str] = None
    ) -> Staff:
        """Create a new staff member with department validation and audit log."""
        role_clean = role.upper()
        if role_clean not in VALID_STAFF_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid staff role '{role}'. Valid roles: {sorted(list(VALID_STAFF_ROLES))}")

        # Validate department exists
        dept_res = await self.db.execute(select(Department.id).where(Department.id == department_id))
        if not dept_res.scalars().first():
            raise HTTPException(status_code=400, detail=f"Referenced department {department_id} does not exist")

        existing_res = await self.db.execute(select(Staff.id).where(Staff.id == id))
        if existing_res.scalars().first():
            raise HTTPException(status_code=400, detail=f"Staff member with ID {id} already exists")

        staff = Staff(
            id=id,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            role=role_clean,
            department_id=department_id,
            specialization=specialization,
            status="AVAILABLE",
            current_workload=0,
            max_workload=max_workload,
            skills=skills or [],
            password_hash=password_hash,
            created_at=utc_now()
        )
        self.db.add(staff)

        audit = AuditLog(
            entity_type="staff",
            entity_id=id,
            field_changed="creation",
            old_value=None,
            new_value=role_clean,
            changed_by=actor_id,
            change_reason=f"Created staff member {id} ({role_clean})"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(staff)
        logger.info(f"Created staff {id} ({first_name} {last_name}, {role_clean}) by {actor_id}")
        return staff

    async def get_staff_by_id(self, staff_id: str) -> Optional[Staff]:
        """Fetch staff member by primary key ID."""
        result = await self.db.execute(select(Staff).where(Staff.id == staff_id))
        return result.scalars().first()

    async def list_staff(
        self,
        role: Optional[str] = None,
        department_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Staff]:
        """List hospital staff with optional role, department, and status filters."""
        query = select(Staff)
        if role:
            query = query.where(Staff.role == role.upper())
        if department_id:
            query = query.where(Staff.department_id == department_id)
        if status:
            query = query.where(Staff.status == status.upper())
        result = await self.db.execute(query.order_by(Staff.role, Staff.id))
        return result.scalars().all()

    async def search_staff(self, query_str: str, limit: int = 20) -> List[Staff]:
        """Search staff by ID, first name, last name, or specialization."""
        term = f"%{query_str.strip().lower()}%"
        stmt = select(Staff).where(
            or_(
                func.lower(Staff.id).like(term),
                func.lower(Staff.first_name).like(term),
                func.lower(Staff.last_name).like(term),
                func.lower(Staff.specialization).like(term)
            )
        ).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_staff(
        self,
        staff_id: str,
        updates: Dict[str, Any],
        actor_id: str
    ) -> Staff:
        """Update staff attributes with row lock, department validation, and audit."""
        result = await self.db.execute(
            select(Staff).where(Staff.id == staff_id).with_for_update()
        )
        staff = result.scalars().first()
        if not staff:
            raise HTTPException(status_code=404, detail=f"Staff member {staff_id} not found")

        if "department_id" in updates and updates["department_id"]:
            dept_res = await self.db.execute(
                select(Department.id).where(Department.id == updates["department_id"])
            )
            if not dept_res.scalars().first():
                raise HTTPException(status_code=400, detail=f"Referenced department {updates['department_id']} does not exist")
            staff.department_id = updates["department_id"]

        if "role" in updates and updates["role"]:
            role_clean = updates["role"].upper()
            if role_clean not in VALID_STAFF_ROLES:
                raise HTTPException(status_code=400, detail=f"Invalid staff role '{updates['role']}'")
            staff.role = role_clean

        for attr in ["first_name", "last_name", "specialization", "max_workload", "skills"]:
            if attr in updates and updates[attr] is not None:
                setattr(staff, attr, updates[attr])

        audit = AuditLog(
            entity_type="staff",
            entity_id=staff_id,
            field_changed="profile_update",
            old_value=None,
            new_value="UPDATED",
            changed_by=actor_id,
            change_reason="Staff profile update"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(staff)
        return staff

    async def get_staff_by_department(self, department_id: str) -> List[Staff]:
        """Query staff assigned to a specific department."""
        return await self.list_staff(department_id=department_id)

    async def get_staff_by_role(self, role: str) -> List[Staff]:
        """Query staff by clinical or operational role."""
        return await self.list_staff(role=role)

    async def find_available_staff(
        self,
        department_id: Optional[str] = None,
        role: Optional[str] = None,
        required_skill: Optional[str] = None
    ) -> List[Staff]:
        """
        Find all staff members who are AVAILABLE and below maximum workload capacity.
        Optionally filter by department, role, and certified skill.
        """
        query = select(Staff).where(
            Staff.status == "AVAILABLE",
            Staff.current_workload < Staff.max_workload
        )
        if department_id:
            query = query.where(Staff.department_id == department_id)
        if role:
            query = query.where(Staff.role == role.upper())

        result = await self.db.execute(query.order_by(Staff.current_workload))
        staff_list = result.scalars().all()

        if required_skill:
            skill_clean = required_skill.upper()
            return [s for s in staff_list if s.skills and skill_clean in [str(sk).upper() for sk in s.skills]]
        return staff_list

    # ─── 2. Status & Workload Management ────────────────────────────────────

    async def update_staff_status(
        self,
        staff_id: str,
        new_status: str,
        actor_id: str,
        reason: str = "Manual status update"
    ) -> Staff:
        """Update operational status with pessimistic row lock and audit."""
        result = await self.db.execute(
            select(Staff).where(Staff.id == staff_id).with_for_update()
        )
        staff = result.scalars().first()
        if not staff:
            raise HTTPException(status_code=404, detail=f"Staff member {staff_id} not found")

        status_clean = new_status.upper()
        if status_clean not in VALID_STAFF_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid staff status '{new_status}'. Valid statuses: {sorted(list(VALID_STAFF_STATUSES))}"
            )

        old_status = staff.status
        staff.status = status_clean

        audit = AuditLog(
            entity_type="staff",
            entity_id=staff_id,
            field_changed="status",
            old_value=old_status,
            new_value=status_clean,
            changed_by=actor_id,
            change_reason=reason
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(staff)
        logger.info(f"Staff {staff_id} status: {old_status} → {status_clean} by {actor_id}")
        return staff

    async def adjust_workload(
        self,
        staff_id: str,
        delta: int,
        actor_id: str
    ) -> Dict[str, Any]:
        """
        Adjust staff patient workload count with pessimistic lock.
        Auto-sets status to BUSY when reaching max workload, or AVAILABLE when capacity frees up.
        """
        result = await self.db.execute(
            select(Staff).where(Staff.id == staff_id).with_for_update()
        )
        staff = result.scalars().first()
        if not staff:
            raise HTTPException(status_code=404, detail=f"Staff member {staff_id} not found")

        old_load = staff.current_workload
        new_load = max(0, staff.current_workload + delta)

        if delta > 0 and new_load > staff.max_workload:
            raise HTTPException(
                status_code=400,
                detail=f"Staff member {staff_id} has exceeded maximum workload capacity of {staff.max_workload}"
            )

        staff.current_workload = new_load

        # Auto-toggle status
        if staff.current_workload >= staff.max_workload:
            staff.status = "BUSY"
        elif staff.status == "BUSY" and staff.current_workload < staff.max_workload:
            staff.status = "AVAILABLE"

        audit = AuditLog(
            entity_type="staff",
            entity_id=staff_id,
            field_changed="workload",
            old_value=str(old_load),
            new_value=str(staff.current_workload),
            changed_by=actor_id,
            change_reason=f"Workload adjusted by delta={delta}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(staff)
        logger.info(f"Staff {staff_id} workload: {old_load} → {staff.current_workload} by {actor_id}")
        return {
            "id": staff.id,
            "current_workload": staff.current_workload,
            "max_workload": staff.max_workload,
            "status": staff.status
        }

    async def get_department_staffing_ratios(self, department_id: str) -> Dict[str, Any]:
        """Calculate current nurse:patient and doctor:patient staffing ratios for a department."""
        dept_res = await self.db.execute(select(Department.id).where(Department.id == department_id))
        if not dept_res.scalars().first():
            raise HTTPException(status_code=404, detail=f"Department {department_id} not found")

        doctors = await self.db.execute(
            select(Staff).where(
                Staff.department_id == department_id,
                Staff.role == "DOCTOR",
                Staff.status.in_(["AVAILABLE", "BUSY"])
            )
        )
        nurses = await self.db.execute(
            select(Staff).where(
                Staff.department_id == department_id,
                Staff.role.in_(["NURSE", "CHARGE_NURSE"]),
                Staff.status.in_(["AVAILABLE", "BUSY"])
            )
        )

        doc_list = doctors.scalars().all()
        nurse_list = nurses.scalars().all()
        total_patients = sum(s.current_workload for s in nurse_list)

        return {
            "department_id": department_id,
            "active_doctors": len(doc_list),
            "active_nurses": len(nurse_list),
            "total_active_patients": total_patients,
            "nurse_patient_ratio": f"1:{round(total_patients / max(len(nurse_list), 1))}",
            "doctor_patient_ratio": f"1:{round(total_patients / max(len(doc_list), 1))}"
        }

    # ─── 3. Shift Management Operations ─────────────────────────────────────

    async def create_shift(
        self,
        staff_id: str,
        department_id: str,
        shift_type: str,
        start_time: str,
        end_time: str,
        actor_id: str
    ) -> StaffShift:
        """Schedule a new shift for a verified staff member."""
        staff = await self.get_staff_by_id(staff_id)
        if not staff:
            raise HTTPException(status_code=404, detail=f"Staff member {staff_id} not found")

        dept_res = await self.db.execute(select(Department.id).where(Department.id == department_id))
        if not dept_res.scalars().first():
            raise HTTPException(status_code=400, detail=f"Referenced department {department_id} does not exist")

        shift_type_clean = shift_type.upper()
        if shift_type_clean not in VALID_SHIFT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid shift type '{shift_type}'. Valid types: {sorted(list(VALID_SHIFT_TYPES))}"
            )

        shift = StaffShift(
            staff_id=staff_id,
            department_id=department_id,
            shift_type=shift_type_clean,
            start_time=start_time,
            end_time=end_time,
            status="SCHEDULED"
        )
        self.db.add(shift)

        audit = AuditLog(
            entity_type="staff_shift",
            entity_id=staff_id,
            field_changed="shift_schedule",
            old_value=None,
            new_value=shift_type_clean,
            changed_by=actor_id,
            change_reason=f"Scheduled {shift_type_clean} shift in {department_id}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(shift)
        logger.info(f"Shift created {shift.id} for {staff_id} ({shift_type_clean}) by {actor_id}")
        return shift

    async def get_shift_by_id(self, shift_id: str) -> Optional[StaffShift]:
        """Fetch shift schedule by ID."""
        result = await self.db.execute(select(StaffShift).where(StaffShift.id == shift_id))
        return result.scalars().first()

    async def list_shifts(
        self,
        staff_id: Optional[str] = None,
        department_id: Optional[str] = None,
        shift_type: Optional[str] = None
    ) -> List[StaffShift]:
        """List staff shift schedules with optional filters."""
        query = select(StaffShift)
        if staff_id:
            query = query.where(StaffShift.staff_id == staff_id)
        if department_id:
            query = query.where(StaffShift.department_id == department_id)
        if shift_type:
            query = query.where(StaffShift.shift_type == shift_type.upper())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_shift_status(
        self,
        shift_id: str,
        new_status: str,
        actor_id: str
    ) -> StaffShift:
        """Update shift lifecycle status (SCHEDULED -> ACTIVE -> COMPLETED / CANCELLED)."""
        result = await self.db.execute(
            select(StaffShift).where(StaffShift.id == shift_id).with_for_update()
        )
        shift = result.scalars().first()
        if not shift:
            raise HTTPException(status_code=404, detail=f"Shift {shift_id} not found")

        status_clean = new_status.upper()
        if status_clean not in VALID_SHIFT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid shift status: {new_status}")

        if shift.status in ["COMPLETED", "CANCELLED"] and status_clean == "ACTIVE":
            raise HTTPException(status_code=400, detail=f"Cannot reactivate an already {shift.status} shift")

        old_status = shift.status
        shift.status = status_clean

        audit = AuditLog(
            entity_type="staff_shift",
            entity_id=shift_id,
            field_changed="status",
            old_value=old_status,
            new_value=status_clean,
            changed_by=actor_id,
            change_reason=f"Shift status updated to {status_clean}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(shift)
        return shift

    # ─── 4. Skills Operations ───────────────────────────────────────────────

    async def add_staff_skill(
        self,
        staff_id: str,
        skill_name: str,
        actor_id: str
    ) -> StaffSkill:
        """Register a new certified skill for a staff member and update skills list."""
        staff = await self.get_staff_by_id(staff_id)
        if not staff:
            raise HTTPException(status_code=404, detail=f"Staff member {staff_id} not found")

        skill_clean = skill_name.strip().upper()
        skill = StaffSkill(
            staff_id=staff_id,
            skill_name=skill_clean,
            certification_date=utc_now()
        )
        self.db.add(skill)

        # Synchronize staff skills json list
        current_skills = list(staff.skills or [])
        if skill_clean not in current_skills:
            current_skills.append(skill_clean)
            staff.skills = current_skills

        audit = AuditLog(
            entity_type="staff_skill",
            entity_id=staff_id,
            field_changed="skill_added",
            old_value=None,
            new_value=skill_clean,
            changed_by=actor_id,
            change_reason=f"Certified in {skill_clean}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(skill)
        logger.info(f"Skill added: {skill_clean} for {staff_id} by {actor_id}")
        return skill

    async def list_staff_skills(self, staff_id: str) -> List[StaffSkill]:
        """List all certified skills recorded for a staff member."""
        result = await self.db.execute(select(StaffSkill).where(StaffSkill.staff_id == staff_id))
        return result.scalars().all()

    async def remove_staff_skill(self, skill_id: str, actor_id: str) -> bool:
        """Remove a skill certification by ID."""
        result = await self.db.execute(
            select(StaffSkill).where(StaffSkill.id == skill_id).with_for_update()
        )
        skill = result.scalars().first()
        if not skill:
            raise HTTPException(status_code=404, detail=f"Staff skill {skill_id} not found")

        staff_id = skill.staff_id
        skill_name = skill.skill_name
        await self.db.delete(skill)

        # Update staff model list
        staff = await self.get_staff_by_id(staff_id)
        if staff and staff.skills and skill_name in staff.skills:
            updated_skills = [s for s in staff.skills if s != skill_name]
            staff.skills = updated_skills

        audit = AuditLog(
            entity_type="staff_skill",
            entity_id=staff_id,
            field_changed="skill_removed",
            old_value=skill_name,
            new_value=None,
            changed_by=actor_id,
            change_reason=f"Skill {skill_name} removed"
        )
        self.db.add(audit)

        await self.db.commit()
        return True

    async def has_skill(self, staff_id: str, skill_name: str) -> bool:
        """Check whether a staff member holds a specific certified skill."""
        staff = await self.get_staff_by_id(staff_id)
        if not staff or not staff.skills:
            return False
        return skill_name.strip().upper() in [str(s).upper() for s in staff.skills]
