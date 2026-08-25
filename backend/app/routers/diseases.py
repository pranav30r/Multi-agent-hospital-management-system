import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Disease

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/diseases", tags=["Disease Registry"])

class DiseaseCreate(BaseModel):
    name: str = Field(..., example="Acute Viral Myocarditis")
    icd_code: Optional[str] = Field(None, example="I40.9")
    category: str = Field(default="Cardiovascular", example="Cardiovascular")
    is_communicable: bool = Field(default=False)
    requires_isolation: bool = Field(default=False)
    added_by: str = Field(default="REC-001")

class DiseaseResponse(DiseaseCreate):
    id: str

    class Config:
        from_attributes = True

@router.get("", response_model=List[DiseaseResponse])
async def list_diseases(db: AsyncSession = Depends(get_db)):
    """List all registered diseases from the ICD-10 reference registry."""
    res = await db.execute(select(Disease).where(Disease.is_active == True).order_by(Disease.name))
    return res.scalars().all()

@router.post("", response_model=DiseaseResponse, status_code=status.HTTP_201_CREATED)
async def add_disease(disease_in: DiseaseCreate, db: AsyncSession = Depends(get_db)):
    """
    Add a new disease to the system registry (Receptionist feature).
    Immediately updates all disease selection dropdowns across the application.
    """
    # Check for duplicate name
    existing = await db.execute(select(Disease).where(Disease.name.ilike(disease_in.name)))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"Disease '{disease_in.name}' already exists in registry")

    disease = Disease(
        name=disease_in.name,
        icd_code=disease_in.icd_code,
        category=disease_in.category,
        is_communicable=disease_in.is_communicable,
        requires_isolation=disease_in.requires_isolation,
        added_by=disease_in.added_by
    )
    db.add(disease)
    await db.commit()
    await db.refresh(disease)
    logger.info(f"Added new disease to registry: {disease.name} (ICD: {disease.icd_code}) by {disease.added_by}")
    return disease
