from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

class DiseaseResponse(BaseModel):
    id: str
    name: str
    icd_code: str
    category: str
    is_communicable: bool
    requires_isolation: bool
    created_at: datetime

    class Config:
        from_attributes = True

class DiseaseCreate(BaseModel):
    name: str
    icd_code: str
    category: str
    is_communicable: bool = False
    requires_isolation: bool = False
