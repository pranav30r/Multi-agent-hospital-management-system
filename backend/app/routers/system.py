import sys
import os
import platform
import psutil
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, engine
from app.config import settings
from app.utils.datetime_utils import utc_now

router = APIRouter(prefix="/system", tags=["System Telemetry & Metrics"])
START_TIME = utc_now()

@router.get("/metrics")
async def get_system_metrics(db: AsyncSession = Depends(get_db)):
    """
    Returns deep system performance metrics:
    - Python environment & OS stats
    - Memory and CPU utilization
    - Database connectivity and pool stats
    - Service uptime
    """
    uptime_seconds = (utc_now() - START_TIME).total_seconds()
    
    # Process memory
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()

    # DB connection check
    db_status = "HEALTHY"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"UNHEALTHY: {str(e)}"

    return {
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "status": "ONLINE",
        "uptime_seconds": round(uptime_seconds, 1),
        "uptime_human": f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m {int(uptime_seconds % 60)}s",
        "environment": {
            "python_version": sys.version.split()[0],
            "os_platform": platform.platform(),
            "processor": platform.processor(),
        },
        "resources": {
            "memory_used_mb": round(mem_info.rss / (1024 * 1024), 2),
            "cpu_percent": process.cpu_percent(interval=None),
        },
        "database": {
            "status": db_status,
            "dialect": engine.dialect.name,
            "pool_size": getattr(engine.pool, "size", lambda: "static")(),
        },
        "features": {
            "jwt_auth": True,
            "websocket_events": True,
            "audit_trail": True,
            "role_based_access": True,
            "prediction_logging": True,
        }
    }
