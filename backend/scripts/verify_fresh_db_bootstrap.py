import os
import sys
import tempfile
import sqlite3
from pathlib import Path
from alembic.config import Config
from alembic import command

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
DATABASE_DIR = PROJECT_ROOT / "database"

SEED_FILES = [
    "02_seed_infrastructure.sql",
    "03_seed_clinical.sql",
    "04_seed_workflows.sql",
    "05_seed_operational.sql"
]


def test_fresh_db_bootstrap():
    print("=" * 80)
    print("FRESH-DB REPRODUCIBILITY & BOOTSTRAP VERIFICATION")
    print("=" * 80)

    # 1. Create temporary SQLite database
    temp_db_file = PROJECT_ROOT / "scratch" / "fresh_bootstrap_test.db"
    if temp_db_file.exists():
        temp_db_file.unlink()

    temp_db_file.parent.mkdir(parents=True, exist_ok=True)
    temp_db_url = f"sqlite:///{temp_db_file.as_posix()}"
    print(f"\n[1/4] Created fresh temporary database target: {temp_db_url}")

    # 2. Run Alembic Migration
    print("\n[2/4] Executing authoritative Alembic migration (upgrade head)...")
    alembic_ini_path = BACKEND_DIR / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", temp_db_url)
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(alembic_cfg, "head")
    print("  -> Alembic migration executed successfully.")

    # 3. Verify Table Count in Fresh DB
    conn = sqlite3.connect(temp_db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\n[3/4] Discovered {len(tables)} tables in freshly migrated database:")
    assert "alembic_version" in tables
    assert len(tables) >= 36  # 35 domain tables + alembic_version
    print(f"  -> Found all 35 domain tables + alembic_version.")

    # 4. Load Seed SQL files
    print("\n[4/4] Applying seed datasets from database/*.sql...")
    for seed_file in SEED_FILES:
        seed_path = DATABASE_DIR / seed_file
        if seed_path.exists():
            with open(seed_path, "r", encoding="utf-8") as f:
                sql = f.read().replace("::jsonb", "")
            cursor.executescript(sql)
            print(f"  -> Seeded {seed_file}")
        else:
            print(f"  -> Warning: {seed_file} not found")

    conn.commit()

    # Query key seeded counts
    cursor.execute("SELECT count(*) FROM departments;")
    dept_count = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM beds;")
    bed_count = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM staff;")
    staff_count = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM equipment;")
    eq_count = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM diseases;")
    disease_count = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM workflow_definitions;")
    wf_count = cursor.fetchone()[0]

    print("\nSeed Verification Summary:")
    print(f"  - Departments:          {dept_count}")
    print(f"  - Beds:                 {bed_count}")
    print(f"  - Staff:                {staff_count}")
    print(f"  - Equipment:            {eq_count}")
    print(f"  - Diseases:             {disease_count}")
    print(f"  - Workflow Definitions: {wf_count}")

    assert dept_count >= 9
    assert bed_count >= 44
    assert staff_count >= 33
    assert eq_count >= 15
    assert disease_count >= 10
    assert wf_count >= 3

    conn.close()

    # Cleanup temp file
    if temp_db_file.exists():
        temp_db_file.unlink()

    print("\n" + "=" * 80)
    print("FRESH-DB BOOTSTRAP REPRODUCIBILITY 100% VERIFIED!")
    print("=" * 80)


if __name__ == "__main__":
    test_fresh_db_bootstrap()
