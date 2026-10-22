"""
Test Suite for High-Performance Synthetic Patient Data Generator
================================================================
Validates:
1. Deterministic generation & reproducibility
2. Clinical distributions (ESI 1-5 proportions, vital signs ranges)
3. Disease catalog mapping to 03_seed_clinical.sql
4. Tenant scoping and required constraints
5. Safety controls (mandatory confirmation flag, production guard)
6. Duplicate detection and collision prevention
7. Atomic transaction rollback behavior on induced failure
8. Batch sizing and bulk insertion integrity
"""

import pytest
import pytest_asyncio
import tempfile
import os
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

import sys
from app.config import settings
from app.database import Base
from app.models.patient import Patient, Encounter
from app.models.tenant import Tenant
from app.models.department import Department
from scripts.seed_patients_10k import (
    SyntheticPatientGenerator,
    seed_synthetic_patients_and_encounters,
    validate_target_database_url,
    CLINICAL_DISEASES_CATALOG,
    DEPARTMENTS,
)


@pytest.fixture
def generator():
    return SyntheticPatientGenerator(tenant_id="HOSP-DEFAULT", seed=42)


def test_clinical_diseases_catalog_matches_seed_sql():
    """Verify all 40 ICD-10 diseases are loaded from 03_seed_clinical.sql."""
    assert len(CLINICAL_DISEASES_CATALOG) == 40
    ids = [d["id"] for d in CLINICAL_DISEASES_CATALOG]
    assert "DIS-01" in ids
    assert "DIS-40" in ids
    # Verify codes
    icd_codes = [d["icd_code"] for d in CLINICAL_DISEASES_CATALOG]
    assert "I10" in icd_codes       # Hypertension
    assert "I21" in icd_codes       # AMI
    assert "U07.1" in icd_codes     # COVID-19
    assert "D64" in icd_codes       # Anemia


def test_deterministic_generation_reproducibility(generator):
    """Verify deterministic generator produces identical output for identical seed."""
    gen1 = SyntheticPatientGenerator(seed=12345)
    gen2 = SyntheticPatientGenerator(seed=12345)

    pts1 = gen1.generate_patients(count=100)
    pts2 = gen2.generate_patients(count=100)

    assert len(pts1) == 100
    assert len(pts2) == 100
    assert pts1[0]["id"] == pts2[0]["id"]
    assert pts1[0]["first_name"] == pts2[0]["first_name"]
    assert pts1[0]["contact_phone"] == pts2[0]["contact_phone"]
    assert pts1[-1]["id"] == pts2[-1]["id"]


def test_patient_demographics_and_tenant_scoping(generator):
    """Verify required fields, tenant scoping, and format of patient master records."""
    patients = generator.generate_patients(count=500)
    assert len(patients) == 500

    seen_ids = set()
    for p in patients:
        assert p["tenant_id"] == "HOSP-DEFAULT"
        assert p["id"].startswith("PAT-")
        assert p["id"] not in seen_ids
        seen_ids.add(p["id"])

        assert p["first_name"]
        assert p["last_name"]
        assert 1 <= p["age"] <= 120
        assert p["gender"] in ("M", "F", "OTHER")
        assert p["blood_group"] in ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
        assert p["contact_phone"].startswith("+9198")
        assert p["emergency_contact"].startswith("+9197")
        assert isinstance(p["allergies"], list)
        assert isinstance(p["chronic_conditions"], list)


def test_target_esi_acuity_distribution(generator):
    """Verify exact target proportions for generated encounters."""
    patients = generator.generate_patients(count=2000)
    encounters = generator.generate_encounters(patients, count=2000)

    assert len(encounters) == 2000

    esi_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for e in encounters:
        esi_counts[e["esi_level"]] += 1

    # Exact target proportions:
    # ESI 1: 5% (100)
    # ESI 2: 15% (300)
    # ESI 3: 40% (800)
    # ESI 4: 25% (500)
    # ESI 5: 15% (300)
    assert esi_counts[1] == 100, f"Expected 100 ESI 1, got {esi_counts[1]}"
    assert esi_counts[2] == 300, f"Expected 300 ESI 2, got {esi_counts[2]}"
    assert esi_counts[3] == 800, f"Expected 800 ESI 3, got {esi_counts[3]}"
    assert esi_counts[4] == 500, f"Expected 500 ESI 4, got {esi_counts[4]}"
    assert esi_counts[5] == 300, f"Expected 300 ESI 5, got {esi_counts[5]}"


def test_vital_signs_ranges_and_plausible_pairings(generator):
    """Verify vital signs fall strictly within clinical ranges and physiological pairings."""
    patients = generator.generate_patients(count=1000)
    encounters = generator.generate_encounters(patients, count=1000)

    catalog_codes = {d["icd_code"] for d in CLINICAL_DISEASES_CATALOG}

    for e in encounters:
        # HR: 60 - 110 bpm
        assert 60 <= e["heart_rate"] <= 110, f"HR {e['heart_rate']} out of bounds"

        # BP: Diastolic 60-100, Systolic 90-160, Systolic > Diastolic + 20
        assert 60 <= e["bp_diastolic"] <= 100, f"Diastolic {e['bp_diastolic']} out of bounds"
        assert 90 <= e["bp_systolic"] <= 160, f"Systolic {e['bp_systolic']} out of bounds"
        assert e["bp_systolic"] >= e["bp_diastolic"] + 20, (
            f"Implausible BP pairing: {e['bp_systolic']}/{e['bp_diastolic']}"
        )

        # SpO2: 92 - 100 %
        assert 92 <= e["spo2"] <= 100, f"SpO2 {e['spo2']} out of bounds"

        # Temp: 36.5 - 38.8 °C -> Fahrenheit 97.7 - 101.8 °F
        assert 97.0 <= e["temperature_f"] <= 102.5, f"Temp {e['temperature_f']} out of bounds"

        # Diagnosed disease must come from 03_seed_clinical.sql catalog
        assert len(e["diagnosed_diseases"]) == 1
        d = e["diagnosed_diseases"][0]
        assert d["icd_code"] in catalog_codes


@pytest.mark.asyncio
async def test_safety_check_blocks_without_confirm_flag():
    """Verify execution is refused without explicit --confirm-synthetic-seed."""
    with pytest.raises(PermissionError, match="--confirm-synthetic-seed"):
        await seed_synthetic_patients_and_encounters(
            db_url="sqlite+aiosqlite:///./disposable_benchmark_test.db",
            patient_count=10,
            confirm_flag=False
        )


def test_safety_check_omitting_db_url_fails():
    """Verify omitting or passing an empty database URL fails before any write."""
    with pytest.raises(ValueError, match="Target database URL must be explicitly provided"):
        validate_target_database_url(db_url="")


def test_safety_check_app_configured_database_rejected():
    """Verify target matching the active application DATABASE_URL is strictly rejected."""
    with pytest.raises(PermissionError, match="matches the active application DATABASE_URL"):
        validate_target_database_url(db_url=settings.DATABASE_URL)


def test_safety_check_hospital_db_target_rejected():
    """Verify target containing 'hospital.db' is strictly rejected."""
    with pytest.raises(PermissionError, match="cannot be the standard application database 'hospital.db'"):
        validate_target_database_url(db_url="sqlite+aiosqlite:///./backup/hospital.db")


def test_safety_check_production_keyword_target_rejected():
    """Verify production database target strings are rejected regardless of ENVIRONMENT."""
    with pytest.raises(PermissionError, match="contains production keyword 'prod'"):
        validate_target_database_url(db_url="postgresql+asyncpg://admin:pass@db.hospital.org/hospital_prod")

    with pytest.raises(PermissionError, match="contains production keyword 'rds.amazonaws.com'"):
        validate_target_database_url(db_url="postgresql+asyncpg://admin:pass@clinical-db.rds.amazonaws.com/clinical")


def test_safety_check_allow_benchmark_db_requires_isolated_target():
    """Verify --allow-benchmark-db cannot authorize an ordinary database without isolated marker."""
    with pytest.raises(PermissionError, match="requires an explicitly isolated benchmark target URL"):
        validate_target_database_url(
            db_url="postgresql+asyncpg://admin:pass@internal-cluster/live_records",
            allow_benchmark_db=True
        )


def test_cli_omitting_db_url_fails():
    """Verify invoking the CLI without --db-url fails with exit code != 0."""
    import subprocess
    res = subprocess.run(
        [sys.executable, "scripts/seed_patients_10k.py", "--confirm-synthetic-seed"],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        capture_output=True,
        text=True
    )
    assert res.returncode != 0
    assert "the following arguments are required: --db-url" in res.stderr


@pytest.mark.asyncio
async def test_atomic_bulk_insertion_and_batching():
    """Verify chunked bulk insertion on a disposable in-memory database."""
    # Use disposable temporary file database for clean schema test
    with tempfile.NamedTemporaryFile(prefix="disposable_benchmark_", suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    try:
        summary = await seed_synthetic_patients_and_encounters(
            db_url=db_url,
            patient_count=2000,
            encounter_count=500,
            batch_size=1000,
            with_encounters=True,
            confirm_flag=True,
            seed=999
        )

        assert summary["patients_inserted"] == 2000
        assert summary["encounters_inserted"] == 500
        assert summary["total_rows"] == 2500
        assert summary["total_batches"] == 3  # 2 patient batches + 1 encounter batch
        assert summary["elapsed_seconds"] > 0
        assert summary["peak_memory_mb"] > 0

        # Query database directly to confirm row counts
        engine = create_async_engine(db_url)
        session_factory = async_sessionmaker(bind=engine, class_=AsyncSession)
        async with session_factory() as s:
            p_count = (await s.execute(select(func.count(Patient.id)))).scalar()
            e_count = (await s.execute(select(func.count(Encounter.id)))).scalar()
            assert p_count == 2000
            assert e_count == 500
        await engine.dispose()

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_duplicate_detection_prevents_overwrite():
    """Verify reruns detect duplicate IDs/MRNs and abort to protect existing data."""
    with tempfile.NamedTemporaryFile(prefix="disposable_benchmark_", suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    try:
        # First run succeeds
        await seed_synthetic_patients_and_encounters(
            db_url=db_url,
            patient_count=100,
            with_encounters=False,
            confirm_flag=True,
            seed=42
        )

        # Second run with same seed must detect duplicate and fail
        with pytest.raises(ValueError, match="Duplicate patient records detected"):
            await seed_synthetic_patients_and_encounters(
                db_url=db_url,
                patient_count=100,
                with_encounters=False,
                confirm_flag=True,
                seed=42,
                skip_existing=False
            )

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_transaction_rollback_on_failure():
    """Verify atomic transaction rollback leaves database completely clean on induced failure."""
    with tempfile.NamedTemporaryFile(prefix="disposable_benchmark_", suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    try:
        # Induce a deliberate failure in encounter insertion
        with pytest.raises(Exception):
            await seed_synthetic_patients_and_encounters(
                db_url=db_url,
                patient_count=500,
                encounter_count=100,
                with_encounters=True,
                confirm_flag=True,
                seed=42,
                induce_failure_for_test=True
            )

        # Verify rollback: 0 patients and 0 encounters committed
        engine = create_async_engine(db_url)
        session_factory = async_sessionmaker(bind=engine, class_=AsyncSession)
        async with session_factory() as s:
            p_count = (await s.execute(select(func.count(Patient.id)))).scalar()
            e_count = (await s.execute(select(func.count(Encounter.id)))).scalar()
            assert p_count == 0, f"Expected 0 patients after rollback, found {p_count}"
            assert e_count == 0, f"Expected 0 encounters after rollback, found {e_count}"
        await engine.dispose()

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
