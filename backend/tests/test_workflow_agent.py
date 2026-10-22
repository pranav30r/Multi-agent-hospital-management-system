"""
Comprehensive Unit and Regression Test Suite for ClinicalWorkflowAgent.

Verifies:
1. BaseAgent inheritance and module exports in app.agents and app.services.agent_orchestrator.
2. Deterministic protocol selection across Cardiac, Resuscitation, Respiratory, Sepsis, and Outpatient scenarios.
3. Strict non-destructive contract: guarantees ZERO mutation to database records, beds, tasks, and encounters.
4. Edge cases: Missing vitals, high-risk overrides, multi-protocol deduplication, tenant isolation, and input validation.
5. Integration with MultiAgentOrchestratorService.
"""

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.workflow_agent import (
    ClinicalWorkflowAgent,
    PROTOCOL_RESUSCITATION,
    PROTOCOL_CARDIAC,
    PROTOCOL_RESPIRATORY,
    PROTOCOL_SEPSIS,
    PROTOCOL_OUTPATIENT,
    PROTOCOL_GENERAL,
)
import app.agents as agents_pkg
import app.services.agent_orchestrator as orchestrator_pkg
from app.models.patient import Patient, Encounter
from app.models.department import Department
from app.models.bed import Bed
from app.models.workflow import Task


# ─── 1. Package Exports and Base Inheritance ─────────────────────────────────

def test_workflow_agent_exports_and_base_inheritance():
    """Verify ClinicalWorkflowAgent inherits from BaseAgent and is properly exported."""
    assert issubclass(ClinicalWorkflowAgent, BaseAgent), "ClinicalWorkflowAgent must inherit from BaseAgent"
    assert agents_pkg.ClinicalWorkflowAgent is ClinicalWorkflowAgent
    assert orchestrator_pkg.ClinicalWorkflowAgent is ClinicalWorkflowAgent
    assert "ClinicalWorkflowAgent" in agents_pkg.__all__
    assert "ClinicalWorkflowAgent" in orchestrator_pkg.__all__


@pytest.mark.asyncio
async def test_workflow_agent_initialization(test_db):
    """Verify agent attributes and database session binding."""
    async with test_db() as session:
        agent = ClinicalWorkflowAgent(session)
        assert agent.agent_id == "clinical_workflow_agent"
        assert "Clinical Workflow" in agent.name
        assert agent.db is session


# ─── 2. Cardiac / Acute Chest Pain Protocol ──────────────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_cardiac_protocol_generation(test_db):
    """Verify ECG < 10 mins and troponin recommendations for acute chest pain with ESI 2."""
    async with test_db() as session:
        dept = await session.get(Department, "DEP-ER")
        if not dept:
            dept = Department(id="DEP-ER", tenant_id="HOSP-DEFAULT", name="Emergency Department", code="ER", total_beds=6)
            session.add(dept)
            await session.flush()

        patient = Patient(
            id="PAT-CARD-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Ramesh",
            last_name="Gupta",
            age=58,
            gender="M",
            blood_group="B+",
            contact_phone="9876543100",
            emergency_contact="9876543101",
            allergies=["Penicillin"]
        )
        session.add(patient)

        encounter = Encounter(
            id="ENC-CARD-01",
            patient_id="PAT-CARD-01",
            current_department_id=dept.id,
            encounter_type="EMERGENCY",
            chief_complaint="Severe crushing substernal chest pain radiating to left jaw",
            bp_systolic=160,
            bp_diastolic=98,
            heart_rate=105,
            spo2=96,
            temperature_f=98.6,
            respiratory_rate=22,
            pain_level=8,
            esi_level=2
        )
        session.add(encounter)
        await session.commit()

        triage_output = {
            "esi_level": 2,
            "severity": "HIGH",
            "score": 8.0,
            "red_flags": [{"code": "RF-CHEST-PAIN", "description": "High-risk acute coronary syndrome presentation"}],
            "recommended_care_level": "EMERGENCY"
        }

        agent = ClinicalWorkflowAgent(session)
        result = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)

        assert result["status"] == "PENDING"
        assert result["agent"] == "clinical_workflow_agent"
        assert PROTOCOL_CARDIAC in result["selected_protocols"]
        assert result["requires_human_review"] is True

        task_chain = result["task_chain"]
        assert len(task_chain) >= 4

        # Verify 12-lead ECG recommendation
        ecg_tasks = [t for t in task_chain if "ECG" in t["title"] or "Electrocardiogram" in t["title"]]
        assert len(ecg_tasks) == 1
        ecg_task = ecg_tasks[0]
        assert ecg_task["urgency"] == "STAT"
        assert "< 10 minutes" in ecg_task["time_window"]
        assert ecg_task["suggested_role"] == "NURSE"
        assert any("10 minutes" in step for step in ecg_task["verification_checklist"])

        # Verify Troponin cardiac biomarker lab
        troponin_tasks = [t for t in task_chain if "Troponin" in t["title"] or "Biomarker" in t["title"]]
        assert len(troponin_tasks) == 1
        trop_task = troponin_tasks[0]
        assert trop_task["urgency"] == "STAT"
        assert trop_task["task_type"] == "DIAGNOSTIC"
        assert trop_task["suggested_role"] == "LAB_TECH"

        # Verify task ordering: STAT assessment and ECG precede monitoring
        first_task = task_chain[0]
        assert first_task["urgency"] == "STAT"


# ─── 3. Resuscitation / ESI 1 / Shock Protocol ───────────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_resuscitation_protocol_generation(test_db):
    """Verify immediate resuscitation recommendations for ESI 1 / shock presentation."""
    async with test_db() as session:
        dept = await session.get(Department, "DEP-ER")
        if not dept:
            dept = Department(id="DEP-ER", tenant_id="HOSP-DEFAULT", name="Emergency Department", code="ER", total_beds=6)
            session.add(dept)
            await session.flush()

        patient = Patient(
            id="PAT-RESUS-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Sanjay",
            last_name="Verma",
            age=64,
            gender="M",
            blood_group="AB+",
            contact_phone="9876543102",
            emergency_contact="9876543103"
        )
        session.add(patient)

        encounter = Encounter(
            id="ENC-RESUS-01",
            patient_id="PAT-RESUS-01",
            current_department_id=dept.id,
            encounter_type="EMERGENCY",
            chief_complaint="Unresponsive, profound shock, cardiac arrest resuscitation in progress",
            bp_systolic=65,
            bp_diastolic=35,
            heart_rate=145,
            spo2=78,
            temperature_f=95.8,
            respiratory_rate=8,
            gcs_score=4,
            esi_level=1
        )
        session.add(encounter)
        await session.commit()

        triage_output = {
            "esi_level": 1,
            "severity": "CRITICAL",
            "score": 10.0,
            "red_flags": [
                {"code": "RF-SHOCK", "description": "Decompensated shock"},
                {"code": "RF-GCS", "description": "GCS <= 8 critical"}
            ],
            "recommended_care_level": "ICU"
        }

        agent = ClinicalWorkflowAgent(session)
        result = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)

        assert result["status"] == "PENDING"
        assert PROTOCOL_RESUSCITATION in result["selected_protocols"]
        assert result["requires_human_review"] is True

        titles = [t["title"] for t in result["task_chain"]]
        assert any("Immediate Resuscitation" in title for title in titles)
        assert any("Airway" in title for title in titles)
        assert any("Vascular Access" in title for title in titles)
        assert any("Code Team" in title or "Resuscitation" in title for title in titles)
        assert any("Critical Care Escalation" in title for title in titles)

        # All primary resuscitation tasks must have STAT urgency
        for task in result["task_chain"]:
            assert task["urgency"] == "STAT"


# ─── 4. Routine Outpatient / Lower-Acuity Workflow ───────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_outpatient_protocol_generation(test_db):
    """Verify routine outpatient documentation and prescription checks for ESI 5 without red flags."""
    async with test_db() as session:
        dept = await session.get(Department, "DEP-ER")
        if not dept:
            dept = Department(id="DEP-ER", tenant_id="HOSP-DEFAULT", name="Emergency Department", code="ER", total_beds=6)
            session.add(dept)
            await session.flush()

        patient = Patient(
            id="PAT-OPD-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Pooja",
            last_name="Sharma",
            age=26,
            gender="F",
            blood_group="O+",
            contact_phone="9876543104",
            emergency_contact="9876543105",
            allergies=["Sulfa drugs"]
        )
        session.add(patient)

        encounter = Encounter(
            id="ENC-OPD-01",
            patient_id="PAT-OPD-01",
            current_department_id=dept.id,
            encounter_type="OPD",
            chief_complaint="Superficial finger papercut, suture removal follow-up",
            bp_systolic=118,
            bp_diastolic=76,
            heart_rate=72,
            spo2=99,
            temperature_f=98.4,
            respiratory_rate=14,
            pain_level=1,
            esi_level=5
        )
        session.add(encounter)
        await session.commit()

        triage_output = {
            "esi_level": 5,
            "severity": "LOW",
            "score": 1.0,
            "red_flags": [],
            "recommended_care_level": "OUTPATIENT"
        }

        agent = ClinicalWorkflowAgent(session)
        result = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)

        assert result["status"] == "PENDING"
        assert PROTOCOL_OUTPATIENT in result["selected_protocols"]
        assert result["requires_human_review"] is False

        task_chain = result["task_chain"]
        assert len(task_chain) == 3
        for task in task_chain:
            assert task["urgency"] == "ROUTINE"

        titles = [t["title"] for t in task_chain]
        assert any("Clinical Documentation" in title for title in titles)
        assert any("Prescription Reconciliation" in title for title in titles)
        assert any("Discharge Instructions" in title for title in titles)


# ─── 5. Non-Destructive Contract Test ────────────────────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_non_destructive_contract(test_db):
    """
    CRITICAL SAFETY INVARIANT TEST:
    Snapshot database state before evaluation; verify zero live task creations,
    zero bed changes, zero encounter/patient state mutations during evaluation.
    """
    async with test_db() as session:
        dept = await session.get(Department, "DEP-ER")
        if not dept:
            dept = Department(id="DEP-ER", tenant_id="HOSP-DEFAULT", name="Emergency Department", code="ER", total_beds=6)
            session.add(dept)
            await session.flush()

        patient = Patient(
            id="PAT-SAFE-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Karan",
            last_name="Mehta",
            age=50,
            gender="M",
            blood_group="A+",
            contact_phone="9876543106",
            emergency_contact="9876543107"
        )
        session.add(patient)

        encounter = Encounter(
            id="ENC-SAFE-01",
            patient_id="PAT-SAFE-01",
            current_department_id=dept.id,
            encounter_type="EMERGENCY",
            status="ACTIVE",
            patient_status="ARRIVED",
            chief_complaint="Acute severe chest pressure radiating to back",
            bp_systolic=150,
            bp_diastolic=95,
            heart_rate=110,
            spo2=95,
            esi_level=2
        )
        session.add(encounter)
        await session.commit()

        # 1. Snapshot database record counts and states before evaluation
        task_count_before = (await session.execute(select(func.count(Task.id)))).scalar_one()
        bed_count_before = (await session.execute(select(func.count(Bed.id)))).scalar_one()

        enc_snapshot = await session.get(Encounter, "ENC-SAFE-01")
        initial_enc_status = enc_snapshot.status
        initial_patient_status = enc_snapshot.patient_status
        initial_bed_id = enc_snapshot.current_bed_id

        # 2. Run agent evaluation
        agent = ClinicalWorkflowAgent(session)
        triage_output = {
            "esi_level": 2,
            "severity": "HIGH",
            "score": 7.5,
            "red_flags": [{"code": "RF-CHEST-PAIN", "description": "Acute chest pain"}],
            "recommended_care_level": "EMERGENCY"
        }
        rec_output = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)

        # 3. Assert recommendations were produced
        assert rec_output["status"] == "PENDING"
        assert len(rec_output["task_chain"]) > 0

        # 4. Snapshot database after evaluation and verify absolute zero mutation
        task_count_after = (await session.execute(select(func.count(Task.id)))).scalar_one()
        bed_count_after = (await session.execute(select(func.count(Bed.id)))).scalar_one()

        assert task_count_after == task_count_before, "Evaluation must NOT insert tasks into tasks table"
        assert bed_count_after == bed_count_before, "Evaluation must NOT create or delete beds"

        enc_after = await session.get(Encounter, "ENC-SAFE-01")
        assert enc_after.status == initial_enc_status, "Encounter status must remain untouched"
        assert enc_after.patient_status == initial_patient_status, "Patient status must remain untouched"
        assert enc_after.current_bed_id == initial_bed_id, "Current bed must remain untouched"


# ─── 6. Respiratory Distress / Hypoxia Protocol ──────────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_respiratory_distress_protocol(test_db):
    """Verify oxygen titration, ABG, and chest X-ray for documented hypoxia and respiratory distress."""
    async with test_db() as session:
        dept = await session.get(Department, "DEP-ER")
        if not dept:
            dept = Department(id="DEP-ER", tenant_id="HOSP-DEFAULT", name="Emergency Department", code="ER", total_beds=6)
            session.add(dept)
            await session.flush()

        patient = Patient(
            id="PAT-RESP-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Amina",
            last_name="Begum",
            age=68,
            gender="F",
            blood_group="B-",
            contact_phone="9876543108",
            emergency_contact="9876543109"
        )
        session.add(patient)

        encounter = Encounter(
            id="ENC-RESP-01",
            patient_id="PAT-RESP-01",
            current_department_id=dept.id,
            chief_complaint="Severe shortness of breath, acute asthma exacerbation, audible wheezing",
            bp_systolic=135,
            bp_diastolic=85,
            heart_rate=115,
            spo2=86,  # Documented severe hypoxia
            respiratory_rate=32,  # Tachypnea
            esi_level=2
        )
        session.add(encounter)
        await session.commit()

        triage_output = {
            "esi_level": 2,
            "severity": "HIGH",
            "score": 8.0,
            "red_flags": [{"code": "RF-HYPOXIA", "description": "Severe arterial hypoxia SpO2 86%"}],
            "recommended_care_level": "EMERGENCY"
        }

        agent = ClinicalWorkflowAgent(session)
        result = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)

        assert PROTOCOL_RESPIRATORY in result["selected_protocols"]
        task_chain = result["task_chain"]

        # Check oxygen titration
        o2_tasks = [t for t in task_chain if "Oxygen" in t["title"]]
        assert len(o2_tasks) == 1
        assert o2_tasks[0]["urgency"] == "STAT"
        assert "< 10 minutes" in o2_tasks[0]["time_window"]

        # Check bronchodilator review, ABG, and portable chest X-ray
        titles = [t["title"] for t in task_chain]
        assert any("Bronchodilator" in title for title in titles)
        assert any("Arterial Blood Gas" in title for title in titles)
        assert any("Chest Radiograph" in title for title in titles)


# ─── 7. Suspected Sepsis Protocol ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_sepsis_protocol_with_sufficient_evidence(test_db):
    """Verify blood cultures, lactate, and antimicrobial evaluation when infection + 2 vitals present."""
    async with test_db() as session:
        dept = await session.get(Department, "DEP-ER")
        if not dept:
            dept = Department(id="DEP-ER", tenant_id="HOSP-DEFAULT", name="Emergency Department", code="ER", total_beds=6)
            session.add(dept)
            await session.flush()

        patient = Patient(
            id="PAT-SEP-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Gopal",
            last_name="Nair",
            age=71,
            gender="M",
            blood_group="O+",
            contact_phone="9876543110",
            emergency_contact="9876543111"
        )
        session.add(patient)

        # Fever (102.4F) + Tachycardia (112) + Hypotension (88/50) + Tachypnea (24) -> Sepsis criteria met
        encounter = Encounter(
            id="ENC-SEP-01",
            patient_id="PAT-SEP-01",
            current_department_id=dept.id,
            chief_complaint="High grade fever, chills, productive cough with purulent sputum, suspected pneumonia",
            temperature_f=102.4,
            heart_rate=112,
            bp_systolic=88,
            bp_diastolic=50,
            respiratory_rate=24,
            spo2=93,
            esi_level=2
        )
        session.add(encounter)
        await session.commit()

        triage_output = {
            "esi_level": 2,
            "severity": "HIGH",
            "score": 8.5,
            "red_flags": [{"code": "RF-SEPSIS", "description": "Septic syndrome presentation"}],
            "recommended_care_level": "EMERGENCY"
        }

        agent = ClinicalWorkflowAgent(session)
        result = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)

        assert PROTOCOL_SEPSIS in result["selected_protocols"]
        task_chain = result["task_chain"]

        titles = [t["title"] for t in task_chain]
        assert any("Sepsis Screening" in title for title in titles)
        assert any("Blood Cultures" in title for title in titles)
        assert any("Antimicrobial Evaluation" in title for title in titles)
        assert any("Fluid Resuscitation" in title for title in titles)

        # Blood cultures must be STAT
        bc_task = [t for t in task_chain if "Blood Cultures" in t["title"]][0]
        assert bc_task["urgency"] == "STAT"
        assert "< 30 minutes" in bc_task["time_window"]


# ─── 8. Missing Data and Non-Fabrication Rules ────────────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_sepsis_rule_missing_vitals_not_positive(test_db):
    """
    CRITICAL RULE: Fever alone without at least 2 recorded associated findings must NOT trigger sepsis.
    Missing measurements must never be inferred as positive findings.
    """
    async with test_db() as session:
        patient = Patient(
            id="PAT-SEP-02",
            tenant_id="HOSP-DEFAULT",
            first_name="Deepak",
            last_name="Joshi",
            age=35,
            gender="M",
            blood_group="A-",
            contact_phone="9876543112",
            emergency_contact="9876543113"
        )
        session.add(patient)

        # Fever is present, but HR, BP, RR, GCS are completely missing (None)
        encounter = Encounter(
            id="ENC-SEP-02",
            patient_id="PAT-SEP-02",
            current_department_id="DEP-ER",
            chief_complaint="Low grade fever for 2 days",
            temperature_f=100.8,
            heart_rate=None,
            bp_systolic=None,
            respiratory_rate=None,
            spo2=None,
            gcs_score=None,
            esi_level=4
        )
        session.add(encounter)
        await session.commit()

        triage_output = {
            "esi_level": 4,
            "severity": "LOW",
            "score": 2.0,
            "red_flags": [],
            "recommended_care_level": "GENERAL"
        }

        agent = ClinicalWorkflowAgent(session)
        result = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)

        # Sepsis protocol MUST NOT trigger because associated findings are missing, not positive
        assert PROTOCOL_SEPSIS not in result["selected_protocols"]

        # Missing vitals MUST be surfaced as safety flags
        flags = result["safety_flags"]
        assert any("MISSING_VITAL: Heart rate" in f for f in flags)
        assert any("MISSING_VITAL: Systolic blood pressure" in f for f in flags)
        assert any("MISSING_VITAL: Respiratory rate" in f for f in flags)


# ─── 9. High-Risk Findings Override Low Acuity Pathway ───────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_high_risk_overrides_low_acuity_baseline(test_db):
    """Verify red flags or acute symptoms prevent routine outpatient protocol even if ESI is 5."""
    async with test_db() as session:
        patient = Patient(
            id="PAT-OVR-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Sunita",
            last_name="Rao",
            age=55,
            gender="F",
            blood_group="B+",
            contact_phone="9876543114",
            emergency_contact="9876543115"
        )
        session.add(patient)

        # Labeled ESI 5, but complaint is acute substernal chest pain
        encounter = Encounter(
            id="ENC-OVR-01",
            patient_id="PAT-OVR-01",
            current_department_id="DEP-ER",
            chief_complaint="Substernal chest pain with nausea",
            bp_systolic=140,
            bp_diastolic=90,
            heart_rate=92,
            spo2=97,
            esi_level=5
        )
        session.add(encounter)
        await session.commit()

        triage_output = {
            "esi_level": 5,
            "severity": "LOW",
            "score": 2.0,
            "red_flags": [{"code": "RF-CHEST", "description": "Chest pain"}],
            "recommended_care_level": "OUTPATIENT"
        }

        agent = ClinicalWorkflowAgent(session)
        result = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)

        # Routine Outpatient MUST NOT be selected; Cardiac protocol MUST take precedence
        assert PROTOCOL_OUTPATIENT not in result["selected_protocols"]
        assert PROTOCOL_CARDIAC in result["selected_protocols"]
        assert result["requires_human_review"] is True


# ─── 10. Multi-Protocol Trigger & Task Deduplication ─────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_overlapping_protocols_deduplication(test_db):
    """Verify patient with both cardiac chest pain and hypoxia triggers both protocols without duplicate tasks."""
    async with test_db() as session:
        patient = Patient(
            id="PAT-MULTI-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Anil",
            last_name="Kapoor",
            age=62,
            gender="M",
            blood_group="O-",
            contact_phone="9876543116",
            emergency_contact="9876543117"
        )
        session.add(patient)

        encounter = Encounter(
            id="ENC-MULTI-01",
            patient_id="PAT-MULTI-01",
            current_department_id="DEP-ER",
            chief_complaint="Acute chest pain and severe shortness of breath",
            bp_systolic=155,
            bp_diastolic=95,
            heart_rate=118,
            spo2=88,  # Hypoxia trigger
            respiratory_rate=28,  # Respiratory trigger
            pain_level=8,
            esi_level=2
        )
        session.add(encounter)
        await session.commit()

        triage_output = {
            "esi_level": 2,
            "severity": "HIGH",
            "score": 8.5,
            "red_flags": [
                {"code": "RF-CHEST-PAIN", "description": "Chest pain"},
                {"code": "RF-HYPOXIA", "description": "Hypoxia"}
            ],
            "recommended_care_level": "EMERGENCY"
        }

        agent = ClinicalWorkflowAgent(session)
        result = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)

        # Both protocols must be selected
        assert PROTOCOL_CARDIAC in result["selected_protocols"]
        assert PROTOCOL_RESPIRATORY in result["selected_protocols"]

        task_chain = result["task_chain"]
        titles = [t["title"] for t in task_chain]

        # Verify cardiac and respiratory tasks coexist
        assert any("ECG" in title for title in titles)
        assert any("Oxygen" in title for title in titles)

        # Verify no duplicate task titles exist in task_chain
        assert len(titles) == len(set(titles)), "All tasks in recommendation chain must be uniquely deduplicated"


# ─── 11. Tenant Isolation Context Propagation ───────────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_tenant_isolation_propagation(test_db):
    """Verify tenant_id propagates cleanly through recommendations and provenance metadata."""
    async with test_db() as session:
        patient = Patient(
            id="PAT-TEN-01",
            tenant_id="HOSP-METRO-SOUTH",
            first_name="Maya",
            last_name="Menon",
            age=40,
            gender="F",
            blood_group="A+",
            contact_phone="9876543118",
            emergency_contact="9876543119"
        )
        session.add(patient)

        encounter = Encounter(
            id="ENC-TEN-01",
            patient_id="PAT-TEN-01",
            current_department_id="DEP-ER",
            chief_complaint="Mild ankle sprain",
            bp_systolic=120,
            bp_diastolic=80,
            heart_rate=70,
            spo2=99,
            temperature_f=98.6,
            respiratory_rate=16,
            esi_level=5
        )
        session.add(encounter)
        await session.commit()

        agent = ClinicalWorkflowAgent(session)
        result = await agent.evaluate(
            triage_output={"esi_level": 5, "severity": "LOW"},
            encounter=encounter,
            patient=patient,
            tenant_id="HOSP-METRO-SOUTH"
        )

        assert result["tenant_id"] == "HOSP-METRO-SOUTH"
        assert result["provenance"]["tenant_id"] == "HOSP-METRO-SOUTH"
        assert result["provenance"]["encounter_id"] == "ENC-TEN-01"


# ─── 12. Deterministic Reproducibility ────────────────────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_deterministic_reproducibility(test_db):
    """Verify identical normalized inputs yield exact identical recommendations and ordering."""
    async with test_db() as session:
        patient = Patient(
            id="PAT-DET-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Vikram",
            last_name="Seth",
            age=49,
            gender="M",
            blood_group="B+",
            contact_phone="9876543120",
            emergency_contact="9876543121"
        )
        session.add(patient)

        encounter = Encounter(
            id="ENC-DET-01",
            patient_id="PAT-DET-01",
            current_department_id="DEP-ER",
            chief_complaint="Chest tightness radiating to left arm",
            bp_systolic=148,
            bp_diastolic=92,
            heart_rate=98,
            spo2=95,
            pain_level=7,
            esi_level=2
        )
        session.add(encounter)
        await session.commit()

        agent = ClinicalWorkflowAgent(session)
        triage_output = {"esi_level": 2, "severity": "HIGH", "red_flags": ["cardiac chest pain"]}

        run1 = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)
        run2 = await agent.evaluate(triage_output=triage_output, encounter=encounter, patient=patient)

        assert run1["protocol"] == run2["protocol"]
        assert run1["selected_protocols"] == run2["selected_protocols"]
        assert run1["requires_human_review"] == run2["requires_human_review"]
        assert len(run1["task_chain"]) == len(run2["task_chain"])

        for t1, t2 in zip(run1["task_chain"], run2["task_chain"]):
            assert t1["title"] == t2["title"]
            assert t1["urgency"] == t2["urgency"]
            assert t1["time_window"] == t2["time_window"]
            assert t1["suggested_role"] == t2["suggested_role"]


# ─── 13. Input Validation and Exception Handling ─────────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_input_validation(test_db):
    """Verify agent raises clear ValueErrors when required encounter or patient is None."""
    async with test_db() as session:
        agent = ClinicalWorkflowAgent(session)

        with pytest.raises(ValueError, match="Encounter object is required"):
            await agent.evaluate(triage_output={}, encounter=None, patient=Patient())

        with pytest.raises(ValueError, match="Patient object is required"):
            await agent.evaluate(triage_output={}, encounter=Encounter(), patient=None)

        with pytest.raises(ValueError, match="triage_output must be a dictionary"):
            await agent.evaluate(triage_output="invalid_string", encounter=Encounter(), patient=Patient())


# ─── 14. MultiAgentOrchestratorService Integration ───────────────────────────

@pytest.mark.asyncio
async def test_workflow_agent_orchestrator_integration(test_db):
    """Verify MultiAgentOrchestratorService initializes ClinicalWorkflowAgent and provides recommendation pipeline."""
    async with test_db() as session:
        orchestrator = orchestrator_pkg.MultiAgentOrchestratorService(session)
        assert hasattr(orchestrator, "workflow_agent")
        assert isinstance(orchestrator.workflow_agent, ClinicalWorkflowAgent)

        dept = await session.get(Department, "DEP-ER")
        if not dept:
            dept = Department(id="DEP-ER", tenant_id="HOSP-DEFAULT", name="Emergency Department", code="ER", total_beds=6)
            session.add(dept)
            await session.flush()

        patient = Patient(
            id="PAT-ORCH-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Tara",
            last_name="Roy",
            age=33,
            gender="F",
            blood_group="O+",
            contact_phone="9876543122",
            emergency_contact="9876543123"
        )
        session.add(patient)

        encounter = Encounter(
            id="ENC-ORCH-01",
            patient_id="PAT-ORCH-01",
            current_department_id=dept.id,
            chief_complaint="Minor headache after studying",
            bp_systolic=115,
            bp_diastolic=75,
            heart_rate=68,
            spo2=99,
            temperature_f=98.4,
            respiratory_rate=14,
            esi_level=5
        )
        session.add(encounter)
        await session.commit()

        # Execute recommendation via orchestrator service facade
        rec = await orchestrator.recommend_clinical_workflow(encounter_id="ENC-ORCH-01")
        assert rec["status"] == "PENDING"
        assert rec["agent"] == "clinical_workflow_agent"
        assert PROTOCOL_OUTPATIENT in rec["selected_protocols"]
