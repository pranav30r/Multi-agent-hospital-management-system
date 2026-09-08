import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Hospital Dashboard State"])


@router.get("/state")
async def get_hospital_state(db: AsyncSession = Depends(get_db)):
    """
    Single unified endpoint returning the complete hospital operational state.
    This is the primary data source for the Command Center frontend.
    Designed to be polled every 2-3 seconds for near-real-time updates.
    """
    service = DashboardService(db)
    return await service.get_hospital_state()


@router.get("/departments/summary")
async def get_departments_summary(db: AsyncSession = Depends(get_db)):
    """Get per-department summary with bed utilization and staffing data."""
    service = DashboardService(db)
    return await service.get_departments_summary()


@router.get("/departments/{department_id}")
async def get_department_overview(department_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed telemetry overview for a specific department."""
    service = DashboardService(db)
    return await service.get_department_overview(department_id)


@router.get("/telemetry")
async def get_command_center_telemetry(db: AsyncSession = Depends(get_db)):
    """Get aggregated top-level telemetry including hospital overview, live queues, tasks, and latest predictions."""
    service = DashboardService(db)
    return await service.get_command_center_telemetry()
