import asyncio
import time
import statistics
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.auth.security import create_access_token
import app.models

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

DATABASE_DIR = Path(__file__).resolve().parent.parent.parent / "database"
SEED_SQL_FILES = [
    "02_seed_infrastructure.sql",
    "03_seed_clinical.sql",
    "04_seed_workflows.sql",
    "05_seed_operational.sql"
]


async def run_validation_suite():
    def seed_sync(sync_conn):
        for seed_file in SEED_SQL_FILES:
            file_path = DATABASE_DIR / seed_file
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().replace("::jsonb", "")
                try:
                    sync_conn.connection.dbapi_connection.executescript(content)
                except Exception:
                    for statement in content.split(";"):
                        stmt = statement.strip()
                        if stmt:
                            sync_conn.exec_driver_sql(stmt)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(seed_sync)

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Generate authenticated headers
        doc_token = create_access_token({"sub": "DOC-001", "role": "DOCTOR", "department_id": "DEP-ER"})
        nurse_token = create_access_token({"sub": "NUR-001", "role": "NURSE", "department_id": "DEP-ER"})
        admin_token = create_access_token({"sub": "ADM-001", "role": "ADMINISTRATOR", "department_id": "DEP-ADMIN"})

        doc_headers = {"Authorization": f"Bearer {doc_token}"}
        nurse_headers = {"Authorization": f"Bearer {nurse_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        print("=" * 80)
        print("PROCESS 4 — REAL-WORLD VALIDATION SUITE EXECUTION")
        print("=" * 80)

        # ------------------------------------------------------------
        # 1. WORKFLOW A: Intake -> Severity -> Priority -> Doctor View
        # ------------------------------------------------------------
        print("\n[Workflow A] Patient Intake & Clinical Decision Pipeline...")
        p_res = await client.post("/api/v1/patients", json={
            "first_name": "Suresh",
            "last_name": "Patel",
            "age": 62,
            "gender": "M",
            "blood_group": "B+",
            "contact_phone": "+919876543299",
            "emergency_contact": "+919876543298"
        }, headers=nurse_headers)
        assert p_res.status_code in [200, 201], f"Failed patient registration: {p_res.text}"
        patient_id = p_res.json()["id"]

        enc_res = await client.post("/api/v1/patients/encounters", json={
            "patient_id": patient_id,
            "chief_complaint": "Crushing chest pain radiating to left arm and severe shortness of breath",
            "heart_rate": 128,
            "bp_systolic": 85,
            "bp_diastolic": 55,
            "spo2": 88,
            "temperature_f": 99.1,
            "pain_level": 10,
            "respiratory_rate": 28,
            "gcs_score": 14
        }, headers=nurse_headers)
        assert enc_res.status_code in [200, 201], f"Failed encounter creation: {enc_res.text}"
        encounter_id = enc_res.json()["id"]

        session_res = await client.post("/api/v1/clinical-intakes", json={
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "language": "en",
            "interaction_mode": "TEXT"
        }, headers=nurse_headers)
        assert session_res.status_code in [200, 201], f"Failed intake session creation: {session_res.text}"
        session_id = session_res.json()["id"]

        # Adaptively answer all sequential questions
        for _ in range(12):
            cq_res = await client.get(f"/api/v1/clinical-intakes/{session_id}/current-question")
            if cq_res.status_code != 200 or not cq_res.json():
                break
            q = cq_res.json()
            resp_val = "Crushing chest pain radiating to left arm for 2 hours"
            struct_val: Dict[str, Any] = {"value": resp_val}
            if q["response_type"] == "BOOLEAN":
                resp_val = "true"
                struct_val = {"value": True}
            elif q["response_type"] == "SCALE":
                resp_val = "10"
                struct_val = {"value": 10}

            await client.post(f"/api/v1/clinical-intakes/{session_id}/responses", json={
                "question_id": q["id"],
                "raw_response": resp_val,
                "structured_value": struct_val
            }, headers=nurse_headers)

        complete_res = await client.post(f"/api/v1/clinical-intakes/{session_id}/complete", headers=nurse_headers)
        assert complete_res.status_code in [200, 201], f"Failed intake completion: {complete_res.text}"

        eval_res = await client.post(f"/api/v1/clinical-priority/{encounter_id}/evaluate", headers=doc_headers)
        assert eval_res.status_code in [200, 201], f"Failed priority evaluation: {eval_res.text}"
        priority_data = eval_res.json()
        assert priority_data["priority_level"] == "CRITICAL"
        assert priority_data["requires_priority_attention"] is True
        print(f"  -> Generated Priority: {priority_data['priority_level']} (Score: {priority_data['score']})")

        doc_view_res = await client.get(f"/api/v1/clinical-intakes/doctor-view/{encounter_id}", headers=doc_headers)
        assert doc_view_res.status_code in [200, 201], f"Failed doctor view: {doc_view_res.text}"
        doc_view = doc_view_res.json()
        assert "patient" in doc_view or "encounter" in doc_view
        print("  -> Doctor Clinical View: PASSED")

        intel_res = await client.get(f"/api/v1/clinical-intelligence/{encounter_id}", headers=doc_headers)
        assert intel_res.status_code in [200, 201], f"Failed clinical intelligence: {intel_res.text}"
        intel_data = intel_res.json()
        assert intel_data["severity"] in ["CRITICAL", "HIGH", "MODERATE", "ROUTINE"]
        print("  -> Workflow A: PASSED")

        # ------------------------------------------------------------
        # 2. WORKFLOW B: Bed Allocation & Row-Lock Conflict Check
        # ------------------------------------------------------------
        print("\n[Workflow B] Bed Allocation & Pessimistic Concurrency...")
        beds_res = await client.get("/api/v1/beds", headers=doc_headers)
        available_beds = [b for b in beds_res.json() if b["status"] == "AVAILABLE"]
        assert len(available_beds) > 0, "No available beds for test"
        target_bed = available_beds[0]["id"]

        book1_res = await client.post("/api/v1/beds/book-manual", json={
            "bed_id": target_bed,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "reason": "Immediate ICU Admission"
        }, headers=doc_headers)
        assert book1_res.status_code in [200, 201], f"Failed first bed booking: {book1_res.text}"

        # Second concurrent attempt MUST fail with 400 Bad Request
        book2_res = await client.post("/api/v1/beds/book-manual", json={
            "bed_id": target_bed,
            "patient_id": "PAT-9999",
            "encounter_id": "ENC-9999",
            "reason": "Conflicting attempt"
        }, headers=doc_headers)
        assert book2_res.status_code == 400, f"Expected 400 for double booking, got {book2_res.status_code}"
        print("  -> Double-booking row lock prevented conflicting allocation: PASSED")

        arrival_res = await client.post(f"/api/v1/beds/{target_bed}/confirm-patient-in-bed", headers=nurse_headers)
        assert arrival_res.status_code in [200, 201]
        assert arrival_res.json()["status"] == "OCCUPIED"
        print("  -> Bed state transitioned to OCCUPIED: PASSED")
        print("  -> Workflow B: PASSED")

        # ------------------------------------------------------------
        # 3. WORKFLOW C: Equipment Reservation & Release
        # ------------------------------------------------------------
        print("\n[Workflow C] Equipment Reservation & Release...")
        eq_res = await client.get("/api/v1/equipment", headers=doc_headers)
        avail_eq = [e for e in eq_res.json() if e["status"] == "AVAILABLE"]
        assert len(avail_eq) > 0, "No available equipment"
        eq_id = avail_eq[0]["id"]

        eq_book_res = await client.post("/api/v1/equipment/bookings", json={
            "equipment_id": eq_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "notes": "Urgent chest scan"
        }, headers=doc_headers)
        assert eq_book_res.status_code in [200, 201]
        booking_id = eq_book_res.json()["id"]

        eq_comp_res = await client.post(f"/api/v1/equipment/bookings/{booking_id}/complete", headers=doc_headers)
        assert eq_comp_res.status_code in [200, 201]
        assert eq_comp_res.json()["status"] == "COMPLETED"
        print("  -> Workflow C: PASSED")

        # ------------------------------------------------------------
        # 4. WORKFLOW D: Emergency Event Declaration & Resolution
        # ------------------------------------------------------------
        print("\n[Workflow D] Emergency Event Lifecycle...")
        emg_dec_res = await client.post("/api/v1/emergencies/declare", json={
            "event_type": "MASS_CASUALTY",
            "severity": "CRITICAL",
            "description": "Multi-vehicle collision on highway",
            "affected_departments": ["DEP-ER", "DEP-ICU"],
            "expected_patient_surge": 15
        }, headers=admin_headers)
        assert emg_dec_res.status_code in [200, 201]
        emg_id = emg_dec_res.json()["id"]

        active_emg_res = await client.get("/api/v1/emergencies/active", headers=doc_headers)
        assert any(e["id"] == emg_id for e in active_emg_res.json())

        resolve_emg_res = await client.post(f"/api/v1/emergencies/{emg_id}/resolve", headers=admin_headers)
        assert resolve_emg_res.status_code == 200
        assert resolve_emg_res.json()["status"] == "RESOLVED"
        print("  -> Workflow D: PASSED")

        # ------------------------------------------------------------
        # 5. WORKFLOW E: Human-in-the-Loop Approval Decision
        # ------------------------------------------------------------
        print("\n[Workflow E] Human-in-the-Loop Approval Resolution...")
        from app.models.agent import ApprovalItem, AgentDecision
        from app.utils.datetime_utils import utc_now

        app_id = f"APR-{int(time.time()*1000)%1000000}"
        dec_id = f"DEC-{int(time.time()*1000)%1000000}"
        async with TestingSessionLocal() as db_sess:
            dec = AgentDecision(
                id=dec_id,
                agent_id="bed_agent",
                action_type="BED_REASSIGNMENT",
                proposed_action={"bed_id": target_bed},
                reasoning="ICU surge optimization",
                status="PROPOSED",
                created_at=utc_now()
            )
            item = ApprovalItem(
                id=app_id,
                decision_id=dec_id,
                agent_id="bed_agent",
                action_type="BED_REASSIGNMENT",
                proposed_action={"bed_id": target_bed},
                reasoning="ICU surge optimization",
                status="PENDING",
                created_at=utc_now()
            )
            db_sess.add(dec)
            db_sess.add(item)
            await db_sess.commit()

        # Reviewer 1 Approves
        rev1_res = await client.post(f"/api/v1/approvals/{app_id}/review", json={
            "action": "APPROVE"
        }, headers=admin_headers)
        assert rev1_res.status_code == 200
        assert rev1_res.json()["status"] in ["APPROVE", "APPROVED"]

        # Conflicting second review attempt MUST fail with 400
        rev2_res = await client.post(f"/api/v1/approvals/{app_id}/review", json={
            "action": "REJECT",
            "rejection_reason": "Too late"
        }, headers=admin_headers)
        assert rev2_res.status_code == 400, f"Expected 400 for already-resolved approval, got {rev2_res.status_code}"
        print("  -> Conflicting second approval review rejected with 400: PASSED")
        print("  -> Workflow E: PASSED")

        # ------------------------------------------------------------
        # 6. WORKFLOW F: Clinical Workflow Step Sequencing
        # ------------------------------------------------------------
        print("\n[Workflow F] Workflow Step Sequencing...")
        wf_defs_res = await client.get("/api/v1/workflows/definitions", headers=doc_headers)
        defs = wf_defs_res.json()
        assert len(defs) > 0, "No workflow definitions found"
        def_id = defs[0]["id"]

        wf_start_res = await client.post("/api/v1/workflows/instances", json={
            "workflow_definition_id": def_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id
        }, headers=doc_headers)
        assert wf_start_res.status_code in [200, 201], f"Failed start workflow: {wf_start_res.text}"
        instance_id = wf_start_res.json()["id"]

        wf_adv_res = await client.post(f"/api/v1/workflows/instances/{instance_id}/advance", json={"notes": "Step completed"}, headers=doc_headers)
        assert wf_adv_res.status_code == 200, f"Failed advance workflow: {wf_adv_res.text}"
        assert wf_adv_res.json()["current_step_number"] >= 2
        print("  -> Workflow F: PASSED")

        # ------------------------------------------------------------
        # 7. PERFORMANCE BASELINE MEASUREMENT (Latency & Stats)
        # ------------------------------------------------------------
        print("\n" + "=" * 80)
        print("BENCHMARKING ENDPOINT LATENCIES (50 iterations each)")
        print("=" * 80)

        benchmarks = [
            ("GET /health", "/health", None),
            ("GET /api/v1/dashboard/state", "/api/v1/dashboard/state", doc_headers),
            ("GET /api/v1/patients", "/api/v1/patients", doc_headers),
            ("GET /api/v1/patients/encounters/active", "/api/v1/patients/encounters/active", doc_headers),
            ("GET /api/v1/system/metrics", "/api/v1/system/metrics", doc_headers),
            (f"GET /api/v1/clinical-priority/{encounter_id}", f"/api/v1/clinical-priority/{encounter_id}", doc_headers)
        ]

        for name, path, headers in benchmarks:
            latencies = []
            for _ in range(50):
                t0 = time.perf_counter()
                res = await client.get(path, headers=headers)
                t1 = time.perf_counter()
                assert res.status_code == 200
                latencies.append((t1 - t0) * 1000)

            latencies.sort()
            p50 = statistics.median(latencies)
            p95 = latencies[int(len(latencies) * 0.95)]
            p99 = latencies[int(len(latencies) * 0.99)]
            avg = statistics.mean(latencies)

            print(f"{name:<48} | p50: {p50:5.2f}ms | p95: {p95:5.2f}ms | p99: {p99:5.2f}ms | avg: {avg:5.2f}ms")

        print("=" * 80)
        print("ALL PROCESS 4 VALIDATION SUITES EXECUTED SUCCESSFULLY.")
        print("=" * 80)

    fastapi_app.dependency_overrides.clear()


if __name__ == "__main__":
    asyncio.run(run_validation_suite())
