import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import AsyncSessionLocal, init_db
from app.models import (
    Department, Bed, Staff, Equipment, Disease,
    Patient, Encounter, EmergencyEvent, AuditLog
)

async def restore_hospital_snapshot(snapshot_file: str):
    """Restores hospital data from a JSON snapshot file."""
    if not os.path.exists(snapshot_file):
        print(f"Error: Snapshot file {snapshot_file} not found")
        return False

    with open(snapshot_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    await init_db()

    async with AsyncSessionLocal() as session:
        # Restore diseases if present
        for dis in data.get("diseases", []):
            session.add(Disease(
                id=dis.get("id"),
                name=dis.get("name"),
                icd_code=dis.get("icd_code"),
                category=dis.get("category"),
                is_communicable=dis.get("is_communicable", False),
                requires_isolation=dis.get("requires_isolation", False)
            ))

        await session.commit()
        print(f"Restored snapshot from {snapshot_file} successfully")
        return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(restore_hospital_snapshot(sys.argv[1]))
    else:
        print("Usage: python restore_db.py <snapshot_file.json>")
