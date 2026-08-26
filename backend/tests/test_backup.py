import pytest
import os
import json
from scripts.backup_db import export_hospital_snapshot

@pytest.mark.asyncio
async def test_export_hospital_snapshot_creates_json(test_db, tmp_path):
    """Verify that export_hospital_snapshot generates a valid populated JSON file."""
    output_file = str(tmp_path / "test_snapshot.json")
    await export_hospital_snapshot(output_file, session_factory=test_db)

    assert os.path.exists(output_file)
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "exported_at" in data
    assert "version" in data
    assert "departments" in data
    assert "beds" in data
    assert "staff" in data
    assert "equipment" in data
    assert "diseases" in data
