from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class DiseaseResponse(BaseModel):
    id: str
    name: str
    icd_code: Optional[str] = None
    category: str
    is_communicable: bool = False
    requires_isolation: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class DiseaseCreate(BaseModel):
    name: str
    icd_code: Optional[str] = None
    category: str
    is_communicable: bool = False
    requires_isolation: bool = False
