import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.models.agent import AuditLog
from app.auth.security import create_access_token, verify_password, get_password_hash
from app.auth.dependencies import get_current_staff

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication & Security"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class LoginJSONRequest(BaseModel):
    staff_id: str = Field(..., example="DOC-001")
    password: str = Field(..., example="hospital@123")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    staff_id: str
    name: str
    role: str
    department_id: str


class StaffRegisterRequest(BaseModel):
    id: str = Field(..., example="DOC-009")
    first_name: str = Field(..., example="Aarav")
    last_name: str = Field(..., example="Mehta")
    role: str = Field(..., example="DOCTOR")
    department_id: str = Field(..., example="DEP-ER")
    specialization: Optional[str] = Field(None, example="Trauma Surgery")
    max_workload: int = Field(default=5)


class StaffMeResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    role: str
    department_id: str
    specialization: Optional[str]
    status: str
    current_workload: int
    max_workload: int

    class Config:
        from_attributes = True


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Optional[OAuth2PasswordRequestForm] = Depends(None),
    json_data: Optional[LoginJSONRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate hospital staff and generate a JWT bearer token.
    Supports both Swagger UI form-urlencoded login and frontend JSON POST login.
    Default password for all seeded staff accounts: 'hospital@123'.
    """
    staff_id = form_data.username if form_data else (json_data.staff_id if json_data else None)
    password = form_data.password if form_data else (json_data.password if json_data else None)

    if not staff_id or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Staff ID / username and password are required"
        )

    result = await db.execute(select(Staff).where(Staff.id == staff_id.upper()))
    staff = result.scalars().first()

    # Note: In our hospital simulation, if staff exists and password is the master default 'hospital@123',
    # authenticate immediately to facilitate frictionless role simulation.
    if not staff or password != "hospital@123":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid staff ID or credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_payload = {
        "sub": staff.id,
        "role": staff.role,
        "name": f"{staff.first_name} {staff.last_name}",
        "department_id": staff.department_id
    }
    access_token = create_access_token(data=token_payload)

    # Log successful login in audit trail
    audit = AuditLog(
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

    logger.info(f"Staff {staff.id} ({staff.role}) successfully logged in")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "staff_id": staff.id,
        "name": f"{staff.first_name} {staff.last_name}",
        "role": staff.role,
        "department_id": staff.department_id
    }


@router.get("/me", response_model=StaffMeResponse)
async def get_my_profile(current_staff: Staff = Depends(get_current_staff)):
    """Retrieve identity and permissions for the currently authenticated staff token."""
    return current_staff


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_staff(
    req: StaffRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """Register a new staff member and issue an authentication token."""
    existing = await db.execute(select(Staff).where(Staff.id == req.id.upper()))
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Staff with ID {req.id} already exists"
        )

    new_staff = Staff(
        id=req.id.upper(),
        first_name=req.first_name,
        last_name=req.last_name,
        role=req.role.upper(),
        department_id=req.department_id.upper(),
        specialization=req.specialization,
        status="AVAILABLE",
        current_workload=0,
        max_workload=req.max_workload
    )
    db.add(new_staff)

    audit = AuditLog(
        entity_type="staff",
        entity_id=new_staff.id,
        field_changed="registration",
        old_value=None,
        new_value="CREATED",
        changed_by="SYSTEM_ADMIN",
        change_reason=f"New staff account created: {new_staff.role}"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(new_staff)

    token_payload = {
        "sub": new_staff.id,
        "role": new_staff.role,
        "name": f"{new_staff.first_name} {new_staff.last_name}",
        "department_id": new_staff.department_id
    }
    access_token = create_access_token(data=token_payload)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "staff_id": new_staff.id,
        "name": f"{new_staff.first_name} {new_staff.last_name}",
        "role": new_staff.role,
        "department_id": new_staff.department_id
    }
