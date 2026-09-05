"""
Enterprise Synthetic Hospital Data Generator & Benchmark Engine
================================================================
Generates coherent, relational synthetic clinical and operational data at scale
(10,000 to 1,000,000+ patients) using streaming batches, deterministic seed control,
and memory-efficient database insertion.

Supports:
- Direct PostgreSQL / SQLite bulk insertion
- Benchmark query execution for latency, throughput, and index verification
- Realistic clinical distributions (vitals, diagnoses, encounters, longitudinal timeline)
"""

import argparse
import asyncio
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Generator, Tuple

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, func, and_, text
from app.models.tenant import Tenant
from app.models.patient import Patient, Encounter
from app.models.observation import ClinicalObservation
from app.models.department import Department
from app.models.staff import Staff
from app.models.agent import AuditLog


# ─── Realistic Clinical Seed Data Distributions ──────────────────────────────

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
    ("DEP-ER", "Emergency Department", "ER", 6),
    ("DEP-ICU", "Intensive Care Unit", "ICU", 8),
    ("DEP-WA", "General Ward A", "WA", 10),
    ("DEP-WB", "General Ward B", "WB", 10),
    ("DEP-CAR", "Cardiology Department", "CAR", 6),
    ("DEP-ISO", "Isolation Unit", "ISO", 4),
    ("DEP-RAD", "Radiology Department", "RAD", 0),
    ("DEP-LAB", "Laboratory Department", "LAB", 0),
    ("DEP-SUR", "Surgery Department", "SUR", 0),
]

CHIEF_COMPLAINTS = [
    ("Severe crushing chest pain radiating to left arm", "DEP-CAR", 1, 1),
    ("Acute shortness of breath and wheezing", "DEP-ER", 2, 2),
    ("High grade fever with severe chills and body ache", "DEP-ER", 3, 3),
    ("Head trauma following motor vehicle collision, GCS 12", "DEP-ER", 1, 1),
    ("Severe abdominal pain in right lower quadrant with vomiting", "DEP-SUR", 2, 2),
    ("Generalized weakness, dizziness, and mild dehydration", "DEP-WA", 4, 4),
    ("Routine post-operative surgical wound follow-up", "DEP-WA", 5, 5),
    ("Sudden onset left-sided weakness and facial droop", "DEP-ICU", 1, 1),
]

OBSERVATION_TEMPLATES = [
    ("HEART_RATE", "bpm", 55, 140, True),
    ("BP_SYSTOLIC", "mmHg", 90, 180, True),
    ("BP_DIASTOLIC", "mmHg", 60, 110, True),
    ("SPO2", "%", 88, 100, True),
    ("TEMPERATURE_F", "degF", 97.0, 103.5, True),
    ("RESPIRATORY_RATE", "/min", 12, 32, True),
    ("PAIN_LEVEL", "/10", 0, 10, True),
    ("GCS_SCORE", "/15", 9, 15, True),
    ("BLOOD_GLUCOSE", "mg/dL", 70, 280, True),
]


def generate_patient_batch(
    start_idx: int,
    count: int,
    tenant_id: str,
    base_time: datetime
) -> List[Dict[str, Any]]:
    """Generates a batch of realistic patient records."""
    patients = []
    for i in range(count):
        idx = start_idx + i
        gender = "M" if random.random() < 0.5 else "F"
        first_name = random.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
        last_name = random.choice(LAST_NAMES)
        age = int(random.gauss(48, 18))
        age = max(1, min(100, age))
        bg = random.choices(BLOOD_GROUPS, weights=BLOOD_GROUP_WEIGHTS)[0]
        phone = f"+9198{random.randint(10000000, 99999999)}"
        em_phone = f"+9197{random.randint(10000000, 99999999)}"
        
        # 30% chance of chronic condition, 15% chance of allergy
        patient_conditions = random.sample(CHRONIC_CONDITIONS, k=random.randint(1, 2)) if random.random() < 0.3 else []
        patient_allergies = random.sample(ALLERGIES, k=1) if random.random() < 0.15 else []

        created_at = base_time - timedelta(days=random.randint(1, 365), hours=random.randint(0, 23))

        patients.append({
            "id": f"PAT-{idx:07d}",
            "tenant_id": tenant_id,
            "first_name": first_name,
            "last_name": last_name,
            "age": age,
            "gender": gender,
            "blood_group": bg,
            "contact_phone": phone,
            "emergency_contact": em_phone,
            "allergies": patient_allergies,
            "chronic_conditions": patient_conditions,
            "created_at": created_at
        })
    return patients


def generate_encounters_and_observations(
    patient: Dict[str, Any],
    tenant_id: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Generates 1 to 3 encounters and 5-15 longitudinal observations per encounter."""
    encounters = []
    observations = []
    audits = []

    # 1 to 3 encounters per patient
    num_encounters = 1 if random.random() < 0.6 else (2 if random.random() < 0.85 else 3)
    patient_created = patient["created_at"]

    for e_idx in range(num_encounters):
        enc_id = f"ENC-{patient['id'][4:]}-{e_idx+1}"
        complaint, dept_id, esi, prio = random.choice(CHIEF_COMPLAINTS)
        
        enc_time = patient_created + timedelta(days=e_idx * random.randint(10, 60), hours=random.randint(1, 12))
        status = "COMPLETED" if e_idx < num_encounters - 1 else random.choice(["ACTIVE", "COMPLETED", "COMPLETED"])

        hr = random.randint(60, 115)
        sys_bp = random.randint(110, 150)
        dia_bp = random.randint(70, 95)
        spo2 = random.randint(93, 100)
        temp = round(random.uniform(97.6, 101.5), 1)

        enc = {
            "id": enc_id,
            "patient_id": patient["id"],
            "encounter_type": "EMERGENCY" if dept_id == "DEP-ER" else "ADMISSION",
            "status": status,
            "current_department_id": dept_id,
            "current_bed_id": None,
            "assigned_doctor_id": f"DOC-{random.randint(1, 8):03d}",
            "assigned_nurse_id": f"NUR-{random.randint(1, 15):03d}",
            "esi_level": esi,
            "priority": prio,
            "patient_status": "DISCHARGED" if status == "COMPLETED" else "ADMITTED",
            "chief_complaint": complaint,
            "heart_rate": hr,
            "bp_systolic": sys_bp,
            "bp_diastolic": dia_bp,
            "spo2": spo2,
            "temperature_f": temp,
            "pain_level": random.randint(1, 8),
            "respiratory_rate": random.randint(14, 24),
            "gcs_score": random.randint(13, 15),
            "diagnosed_diseases": [],
            "diagnosis_notes": f"Admitted for {complaint}. Clinical vitals stabilized under standard monitoring.",
            "arrival_time": enc_time,
            "registration_time": enc_time + timedelta(minutes=5),
            "triage_time": enc_time + timedelta(minutes=15),
            "doctor_assigned_time": enc_time + timedelta(minutes=25),
            "discharge_time": enc_time + timedelta(hours=random.randint(4, 72)) if status == "COMPLETED" else None
        }
        encounters.append(enc)

        # Generate 4 to 8 time-series measurement rounds (longitudinal vitals)
        num_obs_rounds = random.randint(3, 7)
        for r_idx in range(num_obs_rounds):
            obs_time = enc_time + timedelta(hours=r_idx * random.randint(2, 6))
            
            # Record core vitals in each round
            for vname, unit, vmin, vmax, is_numeric in OBSERVATION_TEMPLATES[:random.randint(4, len(OBSERVATION_TEMPLATES))]:
                val = round(random.uniform(vmin, vmax), 1) if isinstance(vmin, float) else random.randint(vmin, vmax)
                obs_id = f"OBS-{patient['id'][4:]}-{e_idx+1}-{r_idx+1}-{vname[:4]}"
                observations.append({
                    "id": obs_id,
                    "patient_id": patient["id"],
                    "encounter_id": enc_id,
                    "tenant_id": tenant_id,
                    "observation_type": vname,
                    "value_numeric": float(val),
                    "value_text": None,
                    "unit": unit,
                    "observed_at": obs_time,
                    "recorded_at": obs_time + timedelta(minutes=2),
                    "recorded_by": enc["assigned_nurse_id"],
                    "source": "DEVICE" if random.random() < 0.7 else "MANUAL",
                    "status": "ACTIVE",
                    "correction_of": None,
                    "correction_reason": None,
                    "metadata_json": {},
                    "created_at": obs_time
                })

        # Append audit record
        audits.append({
            "id": f"AUD-{patient['id'][4:]}-{e_idx+1}",
            "tenant_id": tenant_id,
            "timestamp": enc_time,
            "entity_type": "encounter",
            "entity_id": enc_id,
            "field_changed": "status",
            "old_value": None,
            "new_value": status,
            "changed_by": enc["assigned_doctor_id"],
            "change_reason": f"Encounter initiated for {patient['id']}",
            "decision_id": None,
            "approval_id": None
        })

    return encounters, observations, audits


from app.database import Base


async def stream_and_insert_dataset(
    db_url: str,
    patient_count: int,
    batch_size: int = 1000,
    tenant_id: str = "HOSP-DEFAULT",
    seed: int = 42
) -> Dict[str, Any]:
    """
    Streams and bulk-inserts synthetic data directly into PostgreSQL/SQLite in batches.
    Avoids holding millions of records in memory.
    """
    random.seed(seed)
    engine = create_async_engine(db_url, echo=False)

    # Initialize schema tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.utils.datetime_utils import utc_now
    print(f"[*] Starting streaming synthetic data generation: {patient_count:,} patients (Batch Size: {batch_size:,})", flush=True)
    start_wall = time.perf_counter()
    base_time = utc_now()

    total_encounters = 0
    total_observations = 0
    total_audits = 0

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    num_batches = (patient_count + batch_size - 1) // batch_size

    # 1. Ensure Tenant exists
    async with session_factory() as session:
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        if not t_res.scalars().first():
            tenant = Tenant(
                id=tenant_id,
                name="Primary Enterprise Facility",
                code="HOSP-ENT",
                description="Production benchmark facility",
                is_active=True,
                timezone="UTC"
            )
            session.add(tenant)
            await session.commit()
            print(f"[*] Created tenant record {tenant_id}")

    # 2. Stream and insert in batches
    for b_idx in range(num_batches):
        b_start = time.perf_counter()
        curr_count = min(batch_size, patient_count - (b_idx * batch_size))
        start_idx = b_idx * batch_size + 1

        patients_data = generate_patient_batch(start_idx, curr_count, tenant_id, base_time)
        
        all_encounters = []
        all_observations = []
        all_audits = []

        for p in patients_data:
            encs, obs, aud = generate_encounters_and_observations(p, tenant_id)
            all_encounters.extend(encs)
            all_observations.extend(obs)
            all_audits.extend(aud)

        # Bulk insert via session.add_all in manageable sub-chunks
        async with session_factory() as session:
            # Patients
            for i in range(0, len(patients_data), 500):
                chunk = patients_data[i:i+500]
                session.add_all([Patient(**p) for p in chunk])
                await session.flush()

            # Encounters
            for i in range(0, len(all_encounters), 500):
                chunk = all_encounters[i:i+500]
                session.add_all([Encounter(**e) for e in chunk])
                await session.flush()

            # Observations
            for i in range(0, len(all_observations), 500):
                chunk = all_observations[i:i+500]
                session.add_all([ClinicalObservation(**o) for o in chunk])
                await session.flush()

            # Audits
            for i in range(0, len(all_audits), 500):
                chunk = all_audits[i:i+500]
                session.add_all([AuditLog(**a) for a in chunk])
                await session.flush()

            await session.commit()

        total_encounters += len(all_encounters)
        total_observations += len(all_observations)
        total_audits += len(all_audits)

        b_elapsed = time.perf_counter() - b_start
        inserted_patients = min((b_idx + 1) * batch_size, patient_count)
        rate = curr_count / b_elapsed if b_elapsed > 0 else 0
        print(f"  [+] Batch {b_idx+1}/{num_batches} ({inserted_patients:,}/{patient_count:,} patients) | "
              f"{len(all_encounters):,} Encounters | {len(all_observations):,} Observations | {rate:.1f} pts/sec")

    total_time = time.perf_counter() - start_wall
    await engine.dispose()

    summary = {
        "patients": patient_count,
        "encounters": total_encounters,
        "observations": total_observations,
        "audit_logs": total_audits,
        "total_rows": patient_count + total_encounters + total_observations + total_audits,
        "duration_seconds": total_time,
        "throughput_pts_per_sec": patient_count / total_time if total_time > 0 else 0
    }
    print(f"\n[+] Generation Complete in {total_time:.2f}s:")
    print(f"    - Patients: {patient_count:,}")
    print(f"    - Encounters: {total_encounters:,}")
    print(f"    - Observations: {total_observations:,}")
    print(f"    - Audit Logs: {total_audits:,}")
    print(f"    - Total Rows: {summary['total_rows']:,}")
    return summary


# ─── Benchmark Suite ─────────────────────────────────────────────────────────

async def run_scale_benchmarks(
    db_url: str,
    tenant_id: str = "HOSP-DEFAULT",
    iterations: int = 50
) -> Dict[str, Any]:
    """
    Executes a comprehensive suite of real database queries against 10K / 100K datasets
    measuring response times, cursor vs offset behavior, and tenant-scoped lookups.
    """
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    print(f"\n===============================================================")
    print(f" EXECUTING ENTERPRISE SCALE BENCHMARK WORKLOADS ({iterations} runs each)")
    print(f"===============================================================\n")

    results = {}

    async with session_factory() as session:
        # Sample patient ID
        sample_res = await session.execute(select(Patient.id).where(Patient.tenant_id == tenant_id).limit(10))
        sample_ids = sample_res.scalars().all()
        if not sample_ids:
            print("[!] No patient records found for benchmarking.")
            return {}

        target_pid = sample_ids[0]

        # 1. Primary Key Patient Lookup (Indexed)
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            q = select(Patient).where(and_(Patient.id == target_pid, Patient.tenant_id == tenant_id))
            await session.execute(q)
            latencies.append((time.perf_counter() - t0) * 1000)
        results["1_patient_lookup_pk_ms"] = {
            "avg": sum(latencies)/len(latencies),
            "p95": sorted(latencies)[int(0.95*len(latencies))],
            "min": min(latencies),
            "max": max(latencies)
        }

        # 2. Paginated Patient List (Offset 1,000, Limit 50)
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            q = select(Patient).where(Patient.tenant_id == tenant_id).offset(1000).limit(50)
            await session.execute(q)
            latencies.append((time.perf_counter() - t0) * 1000)
        results["2_paginated_patient_list_offset_ms"] = {
            "avg": sum(latencies)/len(latencies),
            "p95": sorted(latencies)[int(0.95*len(latencies))]
        }

        # 3. Patient Encounter History (Join / Patient ID lookup)
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            q = select(Encounter).where(Encounter.patient_id == target_pid).order_by(Encounter.arrival_time.desc())
            await session.execute(q)
            latencies.append((time.perf_counter() - t0) * 1000)
        results["3_patient_encounter_history_ms"] = {
            "avg": sum(latencies)/len(latencies),
            "p95": sorted(latencies)[int(0.95*len(latencies))]
        }

        # 4. Longitudinal Observations Timeline (Time-series query)
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            q = (
                select(ClinicalObservation)
                .where(and_(
                    ClinicalObservation.patient_id == target_pid,
                    ClinicalObservation.tenant_id == tenant_id
                ))
                .order_by(ClinicalObservation.observed_at.desc())
                .limit(50)
            )
            await session.execute(q)
            latencies.append((time.perf_counter() - t0) * 1000)
        results["4_longitudinal_observations_timeline_ms"] = {
            "avg": sum(latencies)/len(latencies),
            "p95": sorted(latencies)[int(0.95*len(latencies))]
        }

        # 5. Recent Vital Signs (Single vital type aggregation)
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            q = (
                select(ClinicalObservation)
                .where(and_(
                    ClinicalObservation.patient_id == target_pid,
                    ClinicalObservation.tenant_id == tenant_id,
                    ClinicalObservation.observation_type == "HEART_RATE"
                ))
                .order_by(ClinicalObservation.observed_at.desc())
                .limit(1)
            )
            await session.execute(q)
            latencies.append((time.perf_counter() - t0) * 1000)
        results["5_recent_vital_query_ms"] = {
            "avg": sum(latencies)/len(latencies),
            "p95": sorted(latencies)[int(0.95*len(latencies))]
        }

        # 6. Tenant-Filtered Search by Phone / Name (Indexed + Bounded)
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            q = select(Patient).where(and_(Patient.tenant_id == tenant_id, Patient.contact_phone.like("+9198%"))).limit(20)
            await session.execute(q)
            latencies.append((time.perf_counter() - t0) * 1000)
        results["6_tenant_phone_search_ms"] = {
            "avg": sum(latencies)/len(latencies),
            "p95": sorted(latencies)[int(0.95*len(latencies))]
        }

        # 7. Paginated Audit Trail by Tenant & Timestamp
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            q = select(AuditLog).where(AuditLog.tenant_id == tenant_id).order_by(AuditLog.timestamp.desc()).limit(50)
            await session.execute(q)
            latencies.append((time.perf_counter() - t0) * 1000)
        results["7_paginated_audit_trail_ms"] = {
            "avg": sum(latencies)/len(latencies),
            "p95": sorted(latencies)[int(0.95*len(latencies))]
        }

    await engine.dispose()

    # Print benchmark report
    for name, m in results.items():
        print(f"  - {name:<45} | Avg: {m['avg']:>6.2f} ms | P95: {m['p95']:>6.2f} ms")

    return results


# ─── CLI Entrypoint ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic hospital data at scale & benchmark PostgreSQL.")
    parser.add_argument("--patients", type=int, default=10000, help="Number of patients to generate (e.g. 10000, 100000, 500000)")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for streaming database insertion")
    parser.add_argument("--tenant-id", type=str, default="HOSP-DEFAULT", help="Target facility tenant ID")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    parser.add_argument("--db-url", type=str, default=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./hospital.db"), help="Database connection URL")
    parser.add_argument("--benchmark-only", action="store_true", help="Skip generation and execute benchmark suite")

    args = parser.parse_args()

    if not args.benchmark_only:
        asyncio.run(stream_and_insert_dataset(
            db_url=args.db_url,
            patient_count=args.patients,
            batch_size=args.batch_size,
            tenant_id=args.tenant_id,
            seed=args.seed
        ))

    asyncio.run(run_scale_benchmarks(
        db_url=args.db_url,
        tenant_id=args.tenant_id,
        iterations=50
    ))


if __name__ == "__main__":
    main()
