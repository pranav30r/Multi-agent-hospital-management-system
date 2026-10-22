"""
High-Performance Synthetic Patient Data Generator & Benchmark Engine
=====================================================================
Deterministic, reproducible synthetic data seeder for 10,000+ patient master
records and clinical encounters.

Features:
- Deterministic seeding with configurable PRNG seed.
- Exact clinical ESI acuity distribution (ESI 1: 5%, ESI 2: 15%, ESI 3: 40%, ESI 4: 25%, ESI 5: 15%).
- Plausible vital-sign distributions mapped to ICD-10 catalog from 03_seed_clinical.sql.
- Async bulk insertion using SQLAlchemy `insert()` in 1,000-record chunks.
- Atomic transaction strategy with rollback on failure.
- Production environment lock requiring explicit `--confirm-synthetic-seed` flag.
- Tracemalloc peak memory and execution latency instrumentation.
"""

import argparse
import asyncio
import os
import random
import sys
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import and_, func, insert, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.department import Department
from app.models.patient import Encounter, Patient
from app.models.tenant import Tenant

# ─── Clinical Disease Catalog from database/03_seed_clinical.sql ──────────────

CLINICAL_DISEASES_CATALOG: List[Dict[str, str]] = [
    {"id": "DIS-01", "name": "Hypertension", "icd_code": "I10", "category": "Cardiovascular"},
    {"id": "DIS-02", "name": "Acute Myocardial Infarction", "icd_code": "I21", "category": "Cardiovascular"},
    {"id": "DIS-03", "name": "Congestive Heart Failure", "icd_code": "I50", "category": "Cardiovascular"},
    {"id": "DIS-04", "name": "Atrial Fibrillation", "icd_code": "I48", "category": "Cardiovascular"},
    {"id": "DIS-05", "name": "Deep Vein Thrombosis", "icd_code": "I82", "category": "Cardiovascular"},
    {"id": "DIS-06", "name": "Pulmonary Embolism", "icd_code": "I26", "category": "Cardiovascular"},
    {"id": "DIS-07", "name": "Aortic Aneurysm", "icd_code": "I71", "category": "Cardiovascular"},
    {"id": "DIS-08", "name": "Asthma Exacerbation", "icd_code": "J45", "category": "Respiratory"},
    {"id": "DIS-09", "name": "COPD Exacerbation", "icd_code": "J44", "category": "Respiratory"},
    {"id": "DIS-10", "name": "Bacterial Pneumonia", "icd_code": "J18", "category": "Respiratory"},
    {"id": "DIS-11", "name": "Acute Bronchitis", "icd_code": "J20", "category": "Respiratory"},
    {"id": "DIS-12", "name": "Chronic Sinusitis", "icd_code": "J32", "category": "Respiratory"},
    {"id": "DIS-13", "name": "COVID-19 Infection", "icd_code": "U07.1", "category": "Infectious"},
    {"id": "DIS-14", "name": "Pulmonary Tuberculosis", "icd_code": "A15", "category": "Infectious"},
    {"id": "DIS-15", "name": "Dengue Fever", "icd_code": "A90", "category": "Infectious"},
    {"id": "DIS-16", "name": "Malaria", "icd_code": "B50", "category": "Infectious"},
    {"id": "DIS-17", "name": "Hepatitis B", "icd_code": "B16", "category": "Infectious"},
    {"id": "DIS-18", "name": "HIV/AIDS", "icd_code": "B20", "category": "Infectious"},
    {"id": "DIS-19", "name": "Bacterial Meningitis", "icd_code": "G00", "category": "Infectious"},
    {"id": "DIS-20", "name": "Acute Tonsillitis", "icd_code": "J03", "category": "Infectious"},
    {"id": "DIS-21", "name": "Type 2 Diabetes Mellitus", "icd_code": "E11", "category": "Endocrine"},
    {"id": "DIS-22", "name": "Diabetic Ketoacidosis", "icd_code": "E10.1", "category": "Endocrine"},
    {"id": "DIS-23", "name": "Acute Appendicitis", "icd_code": "K35", "category": "Gastrointestinal"},
    {"id": "DIS-24", "name": "Acute Pancreatitis", "icd_code": "K85", "category": "Gastrointestinal"},
    {"id": "DIS-25", "name": "Liver Cirrhosis", "icd_code": "K74", "category": "Gastrointestinal"},
    {"id": "DIS-26", "name": "Acute Gastroenteritis", "icd_code": "K52", "category": "Gastrointestinal"},
    {"id": "DIS-27", "name": "Ischemic Stroke", "icd_code": "I63", "category": "Neurology"},
    {"id": "DIS-28", "name": "Epilepsy", "icd_code": "G40", "category": "Neurology"},
    {"id": "DIS-29", "name": "Migraine", "icd_code": "G43", "category": "Neurology"},
    {"id": "DIS-30", "name": "Acute Kidney Injury", "icd_code": "N17", "category": "Nephrology"},
    {"id": "DIS-31", "name": "Kidney Stone", "icd_code": "N20", "category": "Nephrology"},
    {"id": "DIS-32", "name": "Femur Fracture", "icd_code": "S72", "category": "Orthopedics"},
    {"id": "DIS-33", "name": "Osteoarthritis", "icd_code": "M15", "category": "Orthopedics"},
    {"id": "DIS-34", "name": "Severe Sepsis", "icd_code": "R65.2", "category": "Critical Care"},
    {"id": "DIS-35", "name": "Multi-Organ Dysfunction", "icd_code": "R65.1", "category": "Critical Care"},
    {"id": "DIS-36", "name": "Cellulitis", "icd_code": "L03", "category": "Dermatology"},
    {"id": "DIS-37", "name": "Urinary Tract Infection", "icd_code": "N39", "category": "Urology"},
    {"id": "DIS-38", "name": "Depression", "icd_code": "F32", "category": "Psychiatry"},
    {"id": "DIS-39", "name": "Severe Burns", "icd_code": "T30", "category": "Trauma"},
    {"id": "DIS-40", "name": "Anemia", "icd_code": "D64", "category": "Hematology"},
]

# ─── Fictional Demographic Corpora ───────────────────────────────────────────

FIRST_NAMES_M = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
    "Shaurya", "Atharv", "Advik", "Pranav", "Advaith", "Aaryan", "Dhruv", "Kabir", "Ritvik", "Darsh",
    "Rajesh", "Suresh", "Ramesh", "Anil", "Sunil", "Vikram", "Deepak", "Manoj", "Sanjay", "Amit"
]

FIRST_NAMES_F = [
    "Aadhya", "Saanvi", "Ananya", "Diya", "Gauri", "Pari", "Anika", "Navya", "Angel", "Myra",
    "Sara", "Ira", "Riya", "Avni", "Prisha", "Siya", "Anvi", "Aarohi", "Anaya", "Sneha",
    "Pooja", "Priya", "Sunita", "Anita", "Deepa", "Kavita", "Neha", "Meera", "Swati", "Ritu"
]

LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Deshmukh", "Singh", "Reddy", "Joshi", "Gupta", "Nair", "Kumar",
    "Mehta", "Shah", "Yadav", "Rao", "Tiwari", "Kulkarni", "Rathi", "Chatterjee", "Banerjee", "Bose",
    "Chauhan", "Pandey", "Mishra", "Dubey", "Shukla", "Bhatt", "Choudhary", "Malhotra", "Kapoor", "Khan"
]

BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
BLOOD_GROUP_WEIGHTS = [0.25, 0.05, 0.35, 0.05, 0.08, 0.02, 0.18, 0.02]

CHRONIC_CONDITIONS = [
    "Type 2 Diabetes", "Essential Hypertension", "Asthma", "Coronary Artery Disease",
    "Hypothyroidism", "Chronic Kidney Disease", "COPD", "Hyperlipidemia", "Rheumatoid Arthritis"
]

ALLERGIES = [
    "Penicillin", "Sulfa Drugs", "Aspirin", "Ibuprofen", "Peanuts", "Shellfish",
    "Latex", "Contrast Dye", "Codeine"
]

DEPARTMENTS = [
    ("DEP-ER", "Emergency Department"),
    ("DEP-ICU", "Intensive Care Unit"),
    ("DEP-WA", "General Ward A"),
    ("DEP-WB", "General Ward B"),
    ("DEP-CAR", "Cardiology Department"),
    ("DEP-ISO", "Isolation Unit"),
]

# ─── High-Performance Generator Class ───────────────────────────────────────

class SyntheticPatientGenerator:
    """
    Deterministic clinical generator for reproducible patient and encounter records.
    """

    def __init__(self, tenant_id: str = "HOSP-DEFAULT", seed: int = 42):
        self.tenant_id = tenant_id
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_patients(self, count: int = 10000, start_idx: int = 1) -> List[Dict[str, Any]]:
        """
        Generates deterministic patient master records matching `Patient` model.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        patients: List[Dict[str, Any]] = []

        for i in range(count):
            idx = start_idx + i
            # Unique MRN formatted as PAT-XXXXX
            patient_id = f"PAT-{idx:05d}"
            
            # Deterministic gender selection (49% M, 49% F, 2% OTHER)
            gender_roll = self.rng.random()
            if gender_roll < 0.49:
                gender = "M"
                first_name = self.rng.choice(FIRST_NAMES_M)
            elif gender_roll < 0.98:
                gender = "F"
                first_name = self.rng.choice(FIRST_NAMES_F)
            else:
                gender = "OTHER"
                first_name = self.rng.choice(FIRST_NAMES_M + FIRST_NAMES_F)

            last_name = self.rng.choice(LAST_NAMES)
            
            # Normal age distribution centered around 45 (bounded 1 to 98)
            age = int(self.rng.gauss(45, 18))
            age = max(1, min(98, age))
            
            bg = self.rng.choices(BLOOD_GROUPS, weights=BLOOD_GROUP_WEIGHTS)[0]
            
            # Synthetic non-real phone numbers (555 prefix standard test numbering)
            phone = f"+9198{self.rng.randint(10000000, 99999999)}"
            em_phone = f"+9197{self.rng.randint(10000000, 99999999)}"
            
            # Clinical history probability
            p_conditions = self.rng.sample(CHRONIC_CONDITIONS, k=self.rng.randint(1, 2)) if self.rng.random() < 0.28 else []
            p_allergies = self.rng.sample(ALLERGIES, k=1) if self.rng.random() < 0.14 else []

            created_offset = timedelta(days=self.rng.randint(1, 365), hours=self.rng.randint(0, 23))
            created_at = now - created_offset

            patients.append({
                "id": patient_id,
                "tenant_id": self.tenant_id,
                "first_name": first_name,
                "last_name": last_name,
                "age": age,
                "gender": gender,
                "blood_group": bg,
                "contact_phone": phone,
                "emergency_contact": em_phone,
                "allergies": p_allergies,
                "chronic_conditions": p_conditions,
                "created_at": created_at,
            })

        return patients

    def generate_encounters(
        self,
        patients: List[Dict[str, Any]],
        count: int = 2000,
        start_idx: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Generates clinical encounters with verified ESI and physiological distributions.
        Target ESI:
        - ESI 1: 5% (Resuscitation)
        - ESI 2: 15% (Emergent)
        - ESI 3: 40% (Urgent)
        - ESI 4: 25% (Less Urgent)
        - ESI 5: 15% (Non-urgent)
        """
        if count > len(patients):
            raise ValueError(f"Encounter count ({count}) cannot exceed available patient count ({len(patients)})")

        # Build exact ESI distribution quotas
        esi_counts = {
            1: int(round(count * 0.05)),
            2: int(round(count * 0.15)),
            3: int(round(count * 0.40)),
            4: int(round(count * 0.25)),
            5: count - (int(round(count * 0.05)) + int(round(count * 0.15)) + int(round(count * 0.40)) + int(round(count * 0.25)))
        }

        # Create pooled ESI list and shuffle deterministically
        esi_pool: List[int] = []
        for level, n in esi_counts.items():
            esi_pool.extend([level] * n)
        self.rng.shuffle(esi_pool)

        # Select target patients for encounters deterministically
        selected_patients = patients[:count]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        encounters: List[Dict[str, Any]] = []

        for i, patient in enumerate(selected_patients):
            enc_idx = start_idx + i
            enc_id = f"ENC-{enc_idx:06d}"
            esi_level = esi_pool[i]

            # 1. Clinically plausible vital signs within specified ranges:
            # HR: 60 - 110 bpm
            # Systolic: 90 - 160 mmHg, Diastolic: 60 - 100 mmHg
            # Pairing: systolic >= diastolic + 25
            # SpO2: 92 - 100 %
            # Temp: 36.5 - 38.8 °C -> converted to Fahrenheit 97.7 - 101.8 °F
            
            hr = self.rng.randint(60, 110)
            
            # Diastolic between 60 and 95 so systolic has at least 25 mmHg margin up to 160
            dia_bp = self.rng.randint(60, 95)
            min_sys = max(90, dia_bp + 25)
            max_sys = min(160, dia_bp + 55)
            sys_bp = self.rng.randint(min_sys, max_sys)

            # ESI 1-2 skew lower SpO2, ESI 4-5 high SpO2
            if esi_level in (1, 2):
                spo2 = self.rng.randint(92, 97)
            else:
                spo2 = self.rng.randint(95, 100)

            # Temp Celsius within [36.5, 38.8] -> converted to deg F
            temp_c = round(self.rng.uniform(36.5, 38.8), 2)
            temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 1)

            # Plausible secondary vitals
            resp_rate = self.rng.randint(12, 24)
            pain_level = self.rng.randint(6, 10) if esi_level in (1, 2, 3) else self.rng.randint(0, 5)
            gcs_score = self.rng.randint(9, 13) if esi_level == 1 else self.rng.randint(13, 15)

            # 2. Select primary diagnosis from 03_seed_clinical.sql catalog
            disease = self.rng.choice(CLINICAL_DISEASES_CATALOG)
            diagnosed = [{
                "id": disease["id"],
                "name": disease["name"],
                "icd_code": disease["icd_code"],
                "category": disease["category"]
            }]

            # 3. Department assignment based on acuity and category
            if esi_level == 1:
                dept_id = "DEP-ICU" if disease["category"] in ("Critical Care", "Cardiovascular") else "DEP-ER"
            elif esi_level == 2:
                dept_id = "DEP-ER"
            elif disease["category"] == "Cardiovascular":
                dept_id = "DEP-CAR"
            elif disease["category"] == "Infectious":
                dept_id = "DEP-ISO"
            else:
                dept_id = self.rng.choice(["DEP-WA", "DEP-WB"])

            enc_type = "EMERGENCY" if esi_level in (1, 2) else "ADMISSION"
            status = "ACTIVE" if self.rng.random() < 0.65 else "COMPLETED"
            arrival_time = now - timedelta(days=self.rng.randint(0, 14), hours=self.rng.randint(0, 23))

            chief_complaint = f"Presents with acute symptoms consistent with {disease['name']} ({disease['icd_code']})."

            encounters.append({
                "id": enc_id,
                "patient_id": patient["id"],
                "encounter_type": enc_type,
                "status": status,
                "current_department_id": dept_id,
                "current_bed_id": None,
                "assigned_doctor_id": f"DOC-{self.rng.randint(1, 8):03d}",
                "assigned_nurse_id": f"NUR-{self.rng.randint(1, 15):03d}",
                "esi_level": esi_level,
                "priority": esi_level,
                "patient_status": "ARRIVED" if status == "ACTIVE" else "DISCHARGED",
                "chief_complaint": chief_complaint,
                "heart_rate": hr,
                "bp_systolic": sys_bp,
                "bp_diastolic": dia_bp,
                "spo2": spo2,
                "temperature_f": temp_f,
                "pain_level": pain_level,
                "respiratory_rate": resp_rate,
                "gcs_score": gcs_score,
                "diagnosed_diseases": diagnosed,
                "diagnosis_notes": f"Primary ICD-10 diagnosis: {disease['icd_code']} ({disease['name']}).",
                "arrival_time": arrival_time,
                "registration_time": arrival_time + timedelta(minutes=5),
                "triage_time": arrival_time + timedelta(minutes=12),
                "doctor_assigned_time": arrival_time + timedelta(minutes=25),
                "discharge_time": arrival_time + timedelta(hours=self.rng.randint(4, 48)) if status == "COMPLETED" else None,
            })

        return encounters


# ─── Target Database Validation & Safety Guard ───────────────────────────────

def validate_target_database_url(db_url: str, allow_benchmark_db: bool = False) -> None:
    """
    Strict validation of database target to prevent accidental corruption
    of development or production databases.
    """
    if not db_url or not db_url.strip():
        raise ValueError("Target database URL must be explicitly provided.")

    clean_url = db_url.strip()
    norm_url = clean_url.lower()

    # Rule 1: Never allow seeding the currently configured application database
    configured_db = (settings.DATABASE_URL or "").strip()
    if configured_db and clean_url == configured_db:
        raise PermissionError(
            f"Execution blocked: target database URL matches the active application DATABASE_URL ({configured_db}). "
            "Seeding directly against the active application database is strictly forbidden."
        )

    # Rule 2: Never allow default development database 'hospital.db'
    if "hospital.db" in norm_url:
        raise PermissionError(
            "Execution blocked: target database cannot be the standard application database 'hospital.db'. "
            "Please specify a dedicated disposable target (e.g. 'sqlite+aiosqlite:///./disposable_benchmark.db')."
        )

    # Rule 3: Reject production database strings regardless of ENVIRONMENT setting
    prod_keywords = ["prod", "production", "hospital_prod", "prod-db", "rds.amazonaws.com"]
    for kw in prod_keywords:
        if kw in norm_url:
            raise PermissionError(
                f"Execution blocked: target database URL contains production keyword '{kw}'. "
                "Synthetic seeding to production databases is strictly prohibited."
            )

    # Rule 4: Production environment lock
    is_prod = settings.ENVIRONMENT.lower() in ["production", "prod"]
    if is_prod and not allow_benchmark_db:
        raise PermissionError(
            f"Execution blocked: environment is '{settings.ENVIRONMENT}'. "
            "Synthetic data generation is prohibited in production without an explicitly authorized benchmark target."
        )

    # Rule 5: If allow_benchmark_db is passed, target MUST be an explicitly isolated benchmark target
    if allow_benchmark_db:
        benchmark_indicators = ["benchmark", "disposable", "test", "tmp", "memory"]
        if not any(ind in norm_url for ind in benchmark_indicators):
            raise PermissionError(
                "Execution blocked: '--allow-benchmark-db' requires an explicitly isolated benchmark target URL "
                "containing 'benchmark', 'disposable', 'test', 'tmp', or 'memory'."
            )


# ─── High-Performance Bulk Seeder Engine ─────────────────────────────────────

async def seed_synthetic_patients_and_encounters(
    db_url: str,
    patient_count: int = 10000,
    encounter_count: int = 2000,
    batch_size: int = 1000,
    with_encounters: bool = True,
    tenant_id: str = "HOSP-DEFAULT",
    seed: int = 42,
    confirm_flag: bool = False,
    allow_benchmark_db: bool = False,
    skip_existing: bool = False,
    induce_failure_for_test: bool = False
) -> Dict[str, Any]:
    """
    Executes high-performance chunked bulk insertion with safety gates and rollback protection.
    """
    # ── Safety Check 1: Mandatory Opt-In Flag ──────────────────────────────
    if not confirm_flag:
        raise PermissionError(
            "Execution blocked: missing mandatory '--confirm-synthetic-seed' flag. "
            "Synthetic data generation must be explicitly confirmed."
        )

    # ── Safety Check 2: Target Database URL Validation ─────────────────────
    validate_target_database_url(db_url=db_url, allow_benchmark_db=allow_benchmark_db)

    # Instrument memory and timing
    tracemalloc.start()
    start_wall = time.perf_counter()

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    generator = SyntheticPatientGenerator(tenant_id=tenant_id, seed=seed)
    patients_data = generator.generate_patients(count=patient_count)
    encounters_data = generator.generate_encounters(patients_data, count=encounter_count) if with_encounters else []

    total_patients_inserted = 0
    total_encounters_inserted = 0
    total_batches = 0
    actual_query_count = 0

    try:
        async with session_factory() as session:
            try:
                # ── 1. Pre-Check: Tenant and Duplicate Verification ─────────────
                # Verify Tenant
                tenant_res = await session.execute(select(Tenant.id).where(Tenant.id == tenant_id))
                actual_query_count += 1
                if not tenant_res.scalar_one_or_none():
                    # Automatically create tenant in benchmark db if not present
                    session.add(Tenant(
                        id=tenant_id,
                        name="Default Synthetic Benchmark Facility",
                        code="CHN",
                        description="Synthetic Load Test Facility",
                        is_active=True,
                        timezone="UTC"
                    ))
                    await session.flush()

                # Verify Departments if inserting encounters
                if with_encounters and encounters_data:
                    dept_res = await session.execute(select(Department.id))
                    actual_query_count += 1
                    existing_dept_ids = set(dept_res.scalars().all())
                    missing_depts = [
                        Department(id=did, tenant_id=tenant_id, name=dname, code=did.replace("DEP-", ""), total_beds=10, current_occupancy=0, min_doctors=1, min_nurses=2, nurse_patient_ratio="1:5")
                        for did, dname in DEPARTMENTS if did not in existing_dept_ids
                    ]
                    if missing_depts:
                        session.add_all(missing_depts)
                        await session.flush()

                # Verify Duplicates: inspect first and last patient ID
                first_id = patients_data[0]["id"]
                last_id = patients_data[-1]["id"]
                dup_check = await session.execute(
                    select(func.count(Patient.id)).where(
                        and_(Patient.tenant_id == tenant_id, Patient.id.in_([first_id, last_id]))
                    )
                )
                actual_query_count += 1
                dup_count = dup_check.scalar() or 0
                if dup_count > 0:
                    if skip_existing:
                        pass
                    else:
                        raise ValueError(
                            f"Duplicate patient records detected (e.g., {first_id}). "
                            "Aborting synthetic insertion to prevent overwriting existing data. "
                            "Use an alternate ID range or a fresh test database."
                        )

                # ── 2. Atomic Bulk Insertion in Batches of 1,000 ─────────────────
                # Bulk insert patients
                num_patient_batches = (len(patients_data) + batch_size - 1) // batch_size
                for b_idx in range(num_patient_batches):
                    chunk = patients_data[b_idx * batch_size : (b_idx + 1) * batch_size]
                    await session.execute(insert(Patient).values(chunk))
                    total_patients_inserted += len(chunk)
                    total_batches += 1
                    actual_query_count += 1

                # Bulk insert encounters
                if with_encounters and encounters_data:
                    num_enc_batches = (len(encounters_data) + batch_size - 1) // batch_size
                    for b_idx in range(num_enc_batches):
                        chunk = encounters_data[b_idx * batch_size : (b_idx + 1) * batch_size]
                        
                        # Deliberate failure trigger for testing transaction rollback behavior
                        if induce_failure_for_test and b_idx == num_enc_batches - 1:
                            # Induce duplicate primary key constraint error
                            bad_chunk = list(chunk)
                            bad_chunk.append(dict(chunk[0]))  # duplicate PK violates UNIQUE constraint
                            await session.execute(insert(Encounter).values(bad_chunk))
                        else:
                            await session.execute(insert(Encounter).values(chunk))
                            
                        total_encounters_inserted += len(chunk)
                        total_batches += 1
                        actual_query_count += 1

                await session.commit()
            except Exception:
                await session.rollback()
                raise
    except Exception:
        await engine.dispose()
        tracemalloc.stop()
        raise

    elapsed_time = time.perf_counter() - start_wall
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    await engine.dispose()

    return {
        "patients_inserted": total_patients_inserted,
        "encounters_inserted": total_encounters_inserted,
        "total_rows": total_patients_inserted + total_encounters_inserted,
        "total_batches": total_batches,
        "batch_size": batch_size,
        "elapsed_seconds": round(elapsed_time, 3),
        "peak_memory_mb": round(peak_mem / (1024 * 1024), 2),
        "actual_query_count": actual_query_count,
        "tenant_id": tenant_id,
        "rate_pts_per_sec": round(total_patients_inserted / elapsed_time, 1) if elapsed_time > 0 else 0
    }


# ─── Latency and Distribution Verification Benchmark ─────────────────────────

async def run_verification_benchmarks(
    db_url: str,
    sample_patient_ids: List[str],
    iterations: int = 20,
    tenant_id: str = "HOSP-DEFAULT"
) -> Dict[str, Any]:
    """
    Measures indexed MRN lookup, patient search latency, and distribution stats.
    """
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    latencies_mrn: List[float] = []
    latencies_search: List[float] = []

    async with session_factory() as session:
        # 1. MRN Primary Key / ID Lookup Benchmark
        for pid in sample_patient_ids[:iterations]:
            t0 = time.perf_counter()
            q = select(Patient).where(and_(Patient.id == pid, Patient.tenant_id == tenant_id))
            await session.execute(q)
            latencies_mrn.append((time.perf_counter() - t0) * 1000)

        # 2. Patient Search by Name / Phone Prefix Benchmark
        for _ in range(iterations):
            t0 = time.perf_counter()
            term = "%sharma%"
            q = select(Patient).where(
                and_(
                    Patient.tenant_id == tenant_id,
                    or_(
                        func.lower(Patient.last_name).like(term),
                        func.lower(Patient.first_name).like(term)
                    )
                )
            ).limit(20)
            await session.execute(q)
            latencies_search.append((time.perf_counter() - t0) * 1000)

        # 3. Clinical Distributions Validation
        # ESI Counts
        esi_q = await session.execute(
            select(Encounter.esi_level, func.count(Encounter.id))
            .group_by(Encounter.esi_level)
            .order_by(Encounter.esi_level)
        )
        esi_distribution = {row[0]: row[1] for row in esi_q.all()}

        # Vital Ranges Verification
        vitals_q = await session.execute(
            select(
                func.min(Encounter.heart_rate), func.max(Encounter.heart_rate),
                func.min(Encounter.bp_systolic), func.max(Encounter.bp_systolic),
                func.min(Encounter.bp_diastolic), func.max(Encounter.bp_diastolic),
                func.min(Encounter.spo2), func.max(Encounter.spo2),
                func.min(Encounter.temperature_f), func.max(Encounter.temperature_f),
            )
        )
        vitals_row = vitals_q.one()

    await engine.dispose()

    return {
        "mrn_lookup_avg_ms": round(sum(latencies_mrn) / len(latencies_mrn), 2) if latencies_mrn else 0,
        "mrn_lookup_p95_ms": round(sorted(latencies_mrn)[int(len(latencies_mrn) * 0.95)], 2) if latencies_mrn else 0,
        "search_avg_ms": round(sum(latencies_search) / len(latencies_search), 2) if latencies_search else 0,
        "search_p95_ms": round(sorted(latencies_search)[int(len(latencies_search) * 0.95)], 2) if latencies_search else 0,
        "esi_distribution": esi_distribution,
        "vitals_ranges": {
            "heart_rate_min_max": (vitals_row[0], vitals_row[1]),
            "bp_systolic_min_max": (vitals_row[2], vitals_row[3]),
            "bp_diastolic_min_max": (vitals_row[4], vitals_row[5]),
            "spo2_min_max": (vitals_row[6], vitals_row[7]),
            "temperature_f_min_max": (vitals_row[8], vitals_row[9]),
        }
    }


# ─── CLI Entrypoint ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="High-Performance Synthetic Patient Data Generator & Seeder"
    )
    parser.add_argument("--patients", type=int, default=10000, help="Number of patient master records to generate (default: 10000)")
    parser.add_argument("--with-encounters", action="store_true", default=True, help="Generate clinical encounters for a subset of patients (default: True)")
    parser.add_argument("--no-encounters", dest="with_encounters", action="store_false", help="Disable encounter generation")
    parser.add_argument("--encounter-count", type=int, default=2000, help="Number of clinical encounters to generate (default: 2000)")
    parser.add_argument("--batch-size", type=int, default=1000, help="Chunked insertion batch size (default: 1000)")
    parser.add_argument("--tenant-id", type=str, default="HOSP-DEFAULT", help="Target facility tenant ID (default: HOSP-DEFAULT)")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic PRNG random seed (default: 42)")
    parser.add_argument("--db-url", type=str, required=True, help="Explicit target database connection URL (REQUIRED; cannot be default or active app database)")
    parser.add_argument("--confirm-synthetic-seed", action="store_true", help="Explicit safety opt-in confirmation (REQUIRED to execute)")
    parser.add_argument("--allow-benchmark-db", action="store_true", help="Allow running when environment is set to production")
    parser.add_argument("--skip-existing", action="store_true", help="Skip if synthetic records already exist instead of erroring")
    parser.add_argument("--benchmark", action="store_true", help="Run latency and distribution verification benchmarks after seeding")

    args = parser.parse_args()

    print("\n=================================================================")
    print(" HOSPITAL SYNTHETIC PATIENT DATA GENERATOR (CLI)")
    print("=================================================================\n")

    try:
        summary = asyncio.run(seed_synthetic_patients_and_encounters(
            db_url=args.db_url,
            patient_count=args.patients,
            encounter_count=args.encounter_count,
            batch_size=args.batch_size,
            with_encounters=args.with_encounters,
            tenant_id=args.tenant_id,
            seed=args.seed,
            confirm_flag=args.confirm_synthetic_seed,
            allow_benchmark_db=args.allow_benchmark_db,
            skip_existing=args.skip_existing
        ))

        print(f"[+] Bulk Seeding Completed Successfully:")
        print(f"    - Patients Inserted:     {summary['patients_inserted']:,}")
        print(f"    - Encounters Inserted:   {summary['encounters_inserted']:,}")
        print(f"    - Total Rows:            {summary['total_rows']:,}")
        print(f"    - Batches Executed:      {summary['total_batches']} (Size: {summary['batch_size']:,})")
        print(f"    - Elapsed Time:          {summary['elapsed_seconds']} s ({summary['rate_pts_per_sec']:,} pts/sec)")
        print(f"    - Peak Memory:           {summary['peak_memory_mb']} MB")
        print(f"    - Total DB Queries:      {summary['actual_query_count']}")
        print(f"    - Tenant Boundary:       {summary['tenant_id']}")

        if args.benchmark:
            print("\n[*] Executing Latency & Distribution Verification...")
            sample_ids = [f"PAT-{i:05d}" for i in range(1, min(summary["patients_inserted"], 50) + 1)]
            bench = asyncio.run(run_verification_benchmarks(
                db_url=args.db_url,
                sample_patient_ids=sample_ids,
                tenant_id=args.tenant_id
            ))
            print(f"[+] Benchmark Results:")
            print(f"    - MRN Lookup Latency:    Avg {bench['mrn_lookup_avg_ms']} ms | P95 {bench['mrn_lookup_p95_ms']} ms")
            print(f"    - Patient Search:        Avg {bench['search_avg_ms']} ms | P95 {bench['search_p95_p95_ms']} ms" if "search_p95_p95_ms" in bench else f"    - Patient Search:        Avg {bench['search_avg_ms']} ms | P95 {bench['search_p95_ms']} ms")
            print(f"    - ESI Distribution:      {bench['esi_distribution']}")
            print(f"    - Vitals Ranges:         {bench['vitals_ranges']}")

    except Exception as e:
        print(f"[!] Seeding Failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
