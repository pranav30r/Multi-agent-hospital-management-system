import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.models.department import Department
from app.models.agent import AuditLog
from app.auth.security import create_access_token, verify_password, get_password_hash
from app.auth.dependencies import get_current_staff, require_roles
from app.services.staff_service import VALID_STAFF_ROLES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication & Security"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class LoginJSONRequest(BaseModel):
    staff_id: str = Field(..., description="Staff ID e.g. DOC-001")
    password: str = Field(..., description="Staff password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    staff_id: str
    name: str
    role: str
    department_id: str
    tenant_id: str = "HOSP-DEFAULT"


class StaffRegisterRequest(BaseModel):
    id: str = Field(..., description="Staff unique identifier")
    tenant_id: str = Field(default="HOSP-DEFAULT", description="Hospital tenant identifier")
    first_name: str = Field(..., description="Staff first name")
    last_name: str = Field(..., description="Staff last name")
    role: str = Field(..., description="Hospital role")
    department_id: str = Field(..., description="Department assignment")
    specialization: Optional[str] = Field(None, description="Clinical specialization")
    password: str = Field(default="hospital@123", description="Account password")
    max_workload: int = Field(default=5)



class StaffMeResponse(BaseModel):
    id: str
    tenant_id: str = "HOSP-DEFAULT"
    first_name: str
    last_name: str
    role: str
    department_id: str
    specialization: Optional[str] = None
    status: str
    current_workload: int
    max_workload: int

    model_config = ConfigDict(from_attributes=True)


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginJSONRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate hospital staff and generate a JWT bearer token.
    Strictly verifies passwords against the stored cryptographic hash.
    """
    staff_id = req.staff_id
    password = req.password

    if not staff_id or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Staff ID and password are required"
        )

    from app.auth.lockout import is_account_locked, record_failed_login, reset_failed_login

    locked, remaining_sec = is_account_locked(staff_id.upper())
    if locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account temporarily locked due to multiple failed login attempts. Retry in {remaining_sec} seconds."
        )

    result = await db.execute(select(Staff).where(Staff.id == staff_id.upper()))
    staff = result.scalars().first()

    # Strict cryptographic hash verification (No hardcoded bypass)
    if not staff or not staff.password_hash or not verify_password(password, staff.password_hash):
        attempts_left = record_failed_login(staff_id.upper())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid staff ID or credentials. {attempts_left} attempts remaining before lockout.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Login successful: reset failed attempt counter
    reset_failed_login(staff.id)

    effective_tenant = getattr(staff, "tenant_id", "HOSP-DEFAULT") or "HOSP-DEFAULT"
    token_payload = {
        "sub": staff.id,
        "role": staff.role,
        "name": f"{staff.first_name} {staff.last_name}",
        "department_id": staff.department_id,
        "tenant_id": effective_tenant
    }
    access_token = create_access_token(data=token_payload)

    # Log successful login in audit trail
    audit = AuditLog(
        tenant_id=effective_tenant,
        entity_type="staff",
        entity_id=staff.id,
        field_changed="session",
        old_value="OFFLINE",
        new_value="AUTHENTICATED",
        changed_by=staff.id,
        change_reason="Staff successfully authenticated via JWT"
    )
    db.add(audit)
    await db.commit()

    logger.info(f"Staff {staff.id} ({staff.role}) successfully logged in for tenant {effective_tenant}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "staff_id": staff.id,
        "name": f"{staff.first_name} {staff.last_name}",
        "role": staff.role,
        "department_id": staff.department_id,
        "tenant_id": effective_tenant
    }


@router.get("/me", response_model=StaffMeResponse)
async def get_my_profile(current_staff: Staff = Depends(get_current_staff)):
    """Retrieve identity and permissions for the currently authenticated staff token."""
    return current_staff


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_staff(
    req: StaffRegisterRequest,
    current_admin: Staff = Depends(require_roles(["ADMINISTRATOR"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new staff member under the authenticated administrator's tenant.
    Enforces RBAC authorization, tenant ownership, role validity, and department isolation.
    """
    # 1. Enforce tenant boundary: new staff belongs to current_admin.tenant_id
    admin_tenant = current_admin.tenant_id
    if req.tenant_id and req.tenant_id != admin_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator cannot create staff in another tenant"
        )

    # 2. Validate role against recognized staff roles
    role_clean = req.role.strip().upper()
    if role_clean not in VALID_STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid staff role '{req.role}'. Valid roles: {sorted(list(VALID_STAFF_ROLES))}"
        )

    # 3. Validate department exists and belongs to current_admin.tenant_id
    dept_id_clean = req.department_id.strip().upper()
    dept_res = await db.execute(
        select(Department).where(
            and_(
                Department.id == dept_id_clean,
                Department.tenant_id == admin_tenant
            )
        )
    )
    dept = dept_res.scalars().first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Referenced department {req.department_id} does not exist for tenant {admin_tenant}"
        )

    # 4. Check uniqueness of staff ID
    existing = await db.execute(select(Staff).where(Staff.id == req.id.strip().upper()))
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Staff with ID {req.id} already exists"
        )

    new_staff = Staff(
        id=req.id.strip().upper(),
        tenant_id=admin_tenant,
        first_name=req.first_name.strip(),
        last_name=req.last_name.strip(),
        role=role_clean,
        department_id=dept.id,
        specialization=req.specialization,
        status="AVAILABLE",
        current_workload=0,
        max_workload=req.max_workload,
        password_hash=get_password_hash(req.password)
    )
    db.add(new_staff)

    audit = AuditLog(
        tenant_id=admin_tenant,
        entity_type="staff",
        entity_id=new_staff.id,
        field_changed="registration",
        old_value=None,
        new_value="CREATED",
        changed_by=current_admin.id,
        change_reason=f"New staff account created: {new_staff.role} by admin {current_admin.id}"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(new_staff)

    token_payload = {
        "sub": new_staff.id,
        "role": new_staff.role,
        "name": f"{new_staff.first_name} {new_staff.last_name}",
        "department_id": new_staff.department_id,
        "tenant_id": new_staff.tenant_id
    }
    access_token = create_access_token(data=token_payload)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "staff_id": new_staff.id,
        "name": f"{new_staff.first_name} {new_staff.last_name}",
        "role": new_staff.role,
        "department_id": new_staff.department_id,
        "tenant_id": new_staff.tenant_id
    }
