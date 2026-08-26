from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    staff_id: str
    name: str
    role: str
    department_id: str

class LoginRequest(BaseModel):
    staff_id: str
    password: str

class StaffRegisterRequest(BaseModel):
    id: str
    first_name: str
    last_name: str
    role: str
    department_id: str
    specialization: Optional[str] = None
    max_workload: int = 5
