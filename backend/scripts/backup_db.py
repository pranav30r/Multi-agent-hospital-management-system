import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.utils.datetime_utils import utc_now, utc_now_iso
from app.models import (
    Department, Bed, Staff, Equipment, Disease,
    Patient, Encounter, EmergencyEvent, AuditLog, WorkflowDefinition
)

async def export_hospital_snapshot(output_file: str = None, session_factory=None):
    """Exports all core hospital relational tables into a portable JSON snapshot."""
    if not output_file:
        timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
        output_file = f"hospital_snapshot_{timestamp}.json"

    factory = session_factory or AsyncSessionLocal
    async with factory() as session:
        snapshot = {
            "exported_at": utc_now_iso(),
            "version": "1.0.0",
            "departments": [d.__dict__ for d in (await session.execute(select(Department))).scalars().all()],
            "beds": [b.__dict__ for b in (await session.execute(select(Bed))).scalars().all()],
            "staff": [s.__dict__ for s in (await session.execute(select(Staff))).scalars().all()],
            "equipment": [e.__dict__ for e in (await session.execute(select(Equipment))).scalars().all()],
            "diseases": [dis.__dict__ for dis in (await session.execute(select(Disease))).scalars().all()],
            "patients": [p.__dict__ for p in (await session.execute(select(Patient))).scalars().all()],
            "encounters": [enc.__dict__ for enc in (await session.execute(select(Encounter))).scalars().all()],
            "emergencies": [emg.__dict__ for emg in (await session.execute(select(EmergencyEvent))).scalars().all()],
            "audit_logs": [log.__dict__ for log in (await session.execute(select(AuditLog))).scalars().all()],
        }

        # Clean non-serializable SQLAlchemy state keys
        for category, items in snapshot.items():
            if isinstance(items, list):
                for item in items:
                    item.pop("_sa_instance_state", None)
                    for k, v in item.items():
                        if isinstance(v, datetime):
                            item[k] = v.isoformat()

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)

        print(f"Hospital snapshot exported successfully to: {output_file}")
        return output_file

if __name__ == "__main__":
    asyncio.run(export_hospital_snapshot())
