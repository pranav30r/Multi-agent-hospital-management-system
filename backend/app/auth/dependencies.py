import logging
from typing import List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.security import decode_access_token
from app.models.staff import Staff

logger = logging.getLogger(__name__)

# OAuth2 scheme for Swagger UI & Authorization header parsing
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False
)

async def get_current_user_token(token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    """Decodes the JWT token from authorization header and validates claims."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

async def get_current_staff(
    payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db)
) -> Staff:
    """Resolves authenticated Staff record from database using token subject claim."""
    staff_id = payload.get("sub")
    result = await db.execute(select(Staff).where(Staff.id == staff_id))
    staff = result.scalars().first()
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User/Staff {staff_id} not found"
        )
    return staff

def require_roles(allowed_roles: List[str]):
    """
    Role-Based Access Control (RBAC) Dependency Factory.
    Enforces that the current authenticated user possesses one of the allowed roles.
    Example: Depends(require_roles(["ADMINISTRATOR", "DOCTOR"]))
    """
    async def role_checker(
        staff: Staff = Depends(get_current_staff)
    ) -> Staff:
        if staff.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {allowed_roles}, your role: {staff.role}"
            )
        return staff
    return role_checker

async def get_optional_staff(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Optional[Staff]:
    """Retrieves staff if a valid token is provided, otherwise returns None without error."""
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    result = await db.execute(select(Staff).where(Staff.id == payload.get("sub")))
    return result.scalars().first()
