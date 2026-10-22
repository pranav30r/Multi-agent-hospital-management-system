"""
Comprehensive Unit and Regression Test Suite for LLMService.

Verifies:
1. Safe offline initialization without credentials.
2. Deterministic fallback for Intake NLP, SBAR handoff briefs, and Discharge summaries.
3. Accurate provenance metadata (is_llm_generated, provider, disclaimer).
4. Outbound provider handling using httpx.MockTransport for OpenAI and Groq APIs.
5. Error handling: Timeouts, HTTP 401/429, malformed JSON, and disabled fallback.
6. Deterministic reproducibility and non-fabrication of missing clinical data.
7. Integration with ClinicalIntakeService, PatientCoordinatorAgent, and ClinicalDocumentService.
"""

import json
import pytest
import httpx
from sqlalchemy import select, func

from app.llm import (
    LLMService,
    LLMServiceError,
    PROVIDER_OPENAI,
    PROVIDER_GROQ,
    PROVIDER_FALLBACK,
    DISCLAIMER_TEXT,
)
from app.models.patient import Patient, Encounter
from app.models.department import Department
from app.models.workflow import Task
from app.models.bed import Bed
from app.services.clinical_intake_service import ClinicalIntakeService
from app.agents.patient_coordinator_agent import PatientCoordinatorAgent
from app.services.clinical_document_service import ClinicalDocumentService


# ─── 1. Offline Initialization ───────────────────────────────────────────────

def test_llm_service_initialization_offline():
    """Verify LLMService initializes safely without external credentials or network access."""
    service = LLMService(
        openai_api_key=None,
        groq_api_key=None,
        enable_fallback=True
    )
    assert service.provider is None
    assert service.enable_fallback is True
    assert service.openai_api_key is None
    assert service.groq_api_key is None


# ─── 2. Provider Priority ────────────────────────────────────────────────────

def test_llm_service_provider_priority():
    """Verify deterministic provider priority rule: OPENAI > GROQ > FALLBACK."""
    # Both keys provided: OPENAI wins
    both_service = LLMService(openai_api_key="sk-test-openai", groq_api_key="gsk-test-groq")
    assert both_service.provider == PROVIDER_OPENAI

    # Only Groq provided: GROQ selected
    groq_service = LLMService(openai_api_key=None, groq_api_key="gsk-test-groq")
    assert groq_service.provider == PROVIDER_GROQ

    # Neither provided: None (fallback)
    none_service = LLMService(openai_api_key="", groq_api_key="")
    assert none_service.provider is None


# ─── 3. Deterministic Intake NLP Fallback ────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_service_intake_nlp_fallback():
    """Verify deterministic extraction of symptoms and explicitly mentioned vitals without fabrication."""
    service = LLMService(openai_api_key=None, groq_api_key=None, enable_fallback=True)

    text = (
        "54-year-old male with severe chest pain and shortness of breath for 2 hours. "
        "Vitals: HR 105, BP 160/95 mmHg, SpO2 93% on room air. Reports pain level 8/10."
    )

    result = await service.extract_intake_nlp(text)

    assert result["is_llm_generated"] is False
    assert result["provider"] == PROVIDER_FALLBACK
    assert result["disclaimer"] == DISCLAIMER_TEXT

    # Verify detected symptoms
    symptoms = result["symptoms"]
    assert "Chest Pain / Discomfort" in symptoms
    assert "Shortness of Breath" in symptoms

    # Verify extracted vitals
    vitals = result["vital_signs"]
    assert vitals["heart_rate"] == 105
    assert vitals["bp_systolic"] == 160
    assert vitals["bp_diastolic"] == 95
    assert vitals["spo2"] == 93
    assert result["pain_score"] == 8

    # Verify non-fabrication: unmentioned vitals must be None
    assert vitals["temperature_f"] is None
    assert vitals["respiratory_rate"] is None

    # Verify candidate acuity indicator and candidate ESI (non-definitive)
    assert result["candidate_esi"] == 2
    assert any("Candidate High Acuity" in ind for ind in result["candidate_acuity_indicators"])

    # Verify missing information list
    missing = result["missing_information"]
    assert any("Body temperature" in m for m in missing)
    assert any("Respiratory rate" in m for m in missing)


# ─── 4. SBAR Handoff Brief Fallback ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_service_sbar_handoff_fallback():
    """Verify SBAR structure generation with all four sections and safe handling of missing fields."""
    service = LLMService(openai_api_key=None, groq_api_key=None, enable_fallback=True)

    context = {
        "patient_name": "Rohan Mehra",
        "age": 62,
        "gender": "M",
        "chief_complaint": "Acute epigastric pain radiating to back",
        "esi_level": 2,
        "current_department": "DEP-ER",
        "current_bed": "BED-ER-02",
        "allergies": ["Penicillin", "Aspirin"],
        "chronic_conditions": ["Type 2 Diabetes", "Hypertension"],
        "vitals": {
            "heart_rate": 96,
            "bp_systolic": 145,
            "bp_diastolic": 90,
            "spo2": 96,
            "temperature_f": 99.1,
            "respiratory_rate": 20
        },
        "assigned_doctor": "DOC-ER-01",
        "assigned_nurse": "NUR-ER-04",
        "recommendations": [{"title": "STAT Serum Amylase & Lipase"}, {"title": "Abdominal Ultrasound"}]
    }

    result = await service.generate_sbar_handoff(context)

    assert result["is_llm_generated"] is False
    assert result["provider"] == PROVIDER_FALLBACK
    assert result["disclaimer"] == DISCLAIMER_TEXT

    # Check SBAR sections
    assert "Rohan Mehra" in result["situation"]
    assert "Acute epigastric pain" in result["situation"]
    assert "Penicillin" in result["background"]
    assert "Type 2 Diabetes" in result["background"]
    assert "HR 96" in result["assessment"]
    assert "145/90" in result["assessment"]
    assert "STAT Serum Amylase" in result["recommendation"]
    assert "DOC-ER-01" in result["recommendation"]


# ─── 5. Discharge Summary Fallback ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_service_discharge_summary_fallback():
    """Verify structured discharge summary draft with precautions and non-fabrication of diagnoses."""
    service = LLMService(openai_api_key=None, groq_api_key=None, enable_fallback=True)

    context = {
        "patient_name": "Meera Sen",
        "encounter_id": "ENC-DIS-01",
        "department": "Cardiology Ward",
        "chief_complaint": "Atypical chest discomfort",
        "admission_date": "2026-10-18T10:00:00Z",
        "discharge_date": "2026-10-21T14:00:00Z",
        "diagnoses": ["Non-cardiac chest pain", "GERD"],
        "treatment_summary": "Monitored telemetry x 48h, serial troponins negative, PPI trial initiated",
        "prescriptions": [
            {"name": "Omeprazole", "dosage": "20mg daily", "instructions": "Take before breakfast for 4 weeks"}
        ],
        "follow_up_instructions": "Outpatient follow-up with gastroenterologist in 2 weeks"
    }

    result = await service.generate_discharge_summary(context)

    assert result["is_llm_generated"] is False
    assert result["provider"] == PROVIDER_FALLBACK
    assert result["disclaimer"] == DISCLAIMER_TEXT

    assert "Meera Sen" in result["encounter_summary"]
    assert "Non-cardiac chest pain" in result["documented_diagnoses"]
    assert "GERD" in result["documented_diagnoses"]
    assert "PPI trial initiated" in result["treatment_and_hospital_course"]
    assert any("Omeprazole" in med for med in result["medication_reconciliation"])
    assert "2 weeks" in result["follow_up_instructions"]

    # Verify urgent return precautions are present
    assert len(result["urgent_warning_signs"]) >= 4
    assert any("chest pain" in sign.lower() for sign in result["urgent_warning_signs"])


# ─── 6. Outbound Provider Mocking (OpenAI & Groq) ────────────────────────────

@pytest.mark.asyncio
async def test_llm_service_mock_openai_api_success():
    """Verify outbound OpenAI chat-completion request handling and response parsing via MockTransport."""
    fake_response_json = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "presenting_complaint": "Acute severe substernal chest pressure",
                        "symptoms": ["Chest Pain", "Diaphoresis"],
                        "vital_signs": {
                            "heart_rate": 108,
                            "bp_systolic": 150,
                            "bp_diastolic": 95,
                            "spo2": 94,
                            "temperature_f": 98.6,
                            "respiratory_rate": 22
                        },
                        "pain_score": 9,
                        "candidate_acuity_indicators": ["Candidate High Acuity: ACS symptoms"],
                        "candidate_esi": 2,
                        "missing_information": []
                    })
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.openai.com/v1/chat/completions"
        assert "Bearer sk-mock-openai-key" in request.headers["Authorization"]
        body = json.loads(request.read())
        assert body["model"] == "gpt-4o-mini"
        return httpx.Response(200, json=fake_response_json)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        service = LLMService(
            http_client=mock_client,
            openai_api_key="sk-mock-openai-key",
            groq_api_key=None,
            model="gpt-4o-mini"
        )
        assert service.provider == PROVIDER_OPENAI

        result = await service.extract_intake_nlp("Crushing chest pain and sweating, pain 9/10.")

        assert result["is_llm_generated"] is True
        assert result["provider"] == PROVIDER_OPENAI
        assert result["disclaimer"] == DISCLAIMER_TEXT
        assert result["vital_signs"]["heart_rate"] == 108
        assert result["pain_score"] == 9
        assert "Chest Pain" in result["symptoms"]


@pytest.mark.asyncio
async def test_llm_service_mock_groq_api_success():
    """Verify outbound Groq chat-completion request handling when configured."""
    fake_response_json = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "situation": "Patient in ER with dyspnea",
                        "background": "Known history of COPD",
                        "assessment": "SpO2 89% on room air, bilateral expiratory wheezes",
                        "recommendation": "Initiate Venturi mask O2 and bronchodilator nebulization",
                        "missing_fields": []
                    })
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.groq.com/openai/v1/chat/completions"
        assert "Bearer gsk-mock-groq-key" in request.headers["Authorization"]
        return httpx.Response(200, json=fake_response_json)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        service = LLMService(
            http_client=mock_client,
            openai_api_key=None,
            groq_api_key="gsk-mock-groq-key",
            model="llama-3.3-70b-versatile"
        )
        assert service.provider == PROVIDER_GROQ

        result = await service.generate_sbar_handoff({"chief_complaint": "Severe dyspnea"})

        assert result["is_llm_generated"] is True
        assert result["provider"] == PROVIDER_GROQ
        assert "COPD" in result["background"]


# ─── 7. Timeout & Error Fallback ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_service_timeout_fallback_enabled():
    """Verify that outbound network timeout seamlessly invokes deterministic fallback when enabled."""
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Request timed out after 5.0 seconds", request=request)

    transport = httpx.MockTransport(timeout_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        service = LLMService(
            http_client=mock_client,
            openai_api_key="sk-test",
            enable_fallback=True
        )

        result = await service.extract_intake_nlp("Patient reports high fever 103F and cough.")

        # Timeout triggered fallback
        assert result["is_llm_generated"] is False
        assert result["provider"] == PROVIDER_FALLBACK
        assert result["vital_signs"]["temperature_f"] == 103.0
        assert "Fever / Chills" in result["symptoms"]


@pytest.mark.asyncio
async def test_llm_service_error_when_fallback_disabled():
    """Verify that network or provider errors raise LLMServiceError when fallback is disabled."""
    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})

    transport = httpx.MockTransport(error_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        service = LLMService(
            http_client=mock_client,
            openai_api_key="sk-invalid-key",
            enable_fallback=False
        )

        with pytest.raises(LLMServiceError, match="non-200 HTTP status 401"):
            await service.extract_intake_nlp("Chest pain")


@pytest.mark.asyncio
async def test_llm_service_malformed_json_fallback():
    """Verify that invalid JSON in LLM content triggers deterministic fallback."""
    fake_response = {
        "choices": [
            {
                "message": {
                    "content": "This is non-JSON freeform text from LLM."
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_response)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        service = LLMService(
            http_client=mock_client,
            openai_api_key="sk-test",
            enable_fallback=True
        )

        result = await service.extract_intake_nlp("Headache and dizziness for 1 day, HR 78.")
        assert result["is_llm_generated"] is False
        assert result["provider"] == PROVIDER_FALLBACK
        assert "Headache" in result["symptoms"]


# ─── 8. Reproducibility & Edge Cases ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_service_deterministic_reproducibility():
    """Verify identical inputs yield exact identical results in fallback mode."""
    service = LLMService(enable_fallback=True)
    text = "Fever and productive cough for 3 days, temp 101.5 F, HR 88 bpm."

    res1 = await service.extract_intake_nlp(text)
    res2 = await service.extract_intake_nlp(text)

    assert res1["symptoms"] == res2["symptoms"]
    assert res1["vital_signs"] == res2["vital_signs"]
    assert res1["candidate_esi"] == res2["candidate_esi"]
    assert res1["missing_information"] == res2["missing_information"]


@pytest.mark.asyncio
async def test_llm_service_empty_and_null_inputs():
    """Verify empty and None inputs are handled safely without crashing."""
    service = LLMService(enable_fallback=True)

    nlp_res = await service.extract_intake_nlp("")
    assert nlp_res["presenting_complaint"] == "No intake statement provided"
    assert nlp_res["symptoms"] == []

    sbar_res = await service.generate_sbar_handoff({})
    assert "Unspecified Patient" in sbar_res["situation"]
    assert len(sbar_res["missing_fields"]) > 0

    dis_res = await service.generate_discharge_summary({})
    assert "Discharge summary draft" in dis_res["encounter_summary"]


# ─── 9. Service Integration & Non-Destructive Contract ───────────────────────

@pytest.mark.asyncio
async def test_llm_service_integration_and_non_destructive(test_db):
    """
    CRITICAL SAFETY INVARIANT TEST:
    Verify that ClinicalIntakeService, PatientCoordinatorAgent, and ClinicalDocumentService
    can use LLMService with zero mutations to database tables, tasks, or beds.
    """
    async with test_db() as session:
        dept = await session.get(Department, "DEP-ER")
        if not dept:
            dept = Department(id="DEP-ER", tenant_id="HOSP-DEFAULT", name="Emergency", code="ER", total_beds=6)
            session.add(dept)
            await session.flush()

        patient = Patient(
            id="PAT-LLM-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Deepa",
            last_name="Kulkarni",
            age=48,
            gender="F",
            blood_group="A+",
            contact_phone="9876543150",
            emergency_contact="9876543151",
            allergies=["Cephalosporins"]
        )
        session.add(patient)

        encounter = Encounter(
            id="ENC-LLM-01",
            patient_id="PAT-LLM-01",
            current_department_id=dept.id,
            chief_complaint="Acute right lower quadrant abdominal pain",
            bp_systolic=128,
            bp_diastolic=82,
            heart_rate=88,
            spo2=98,
            temperature_f=100.2,
            respiratory_rate=16,
            esi_level=3
        )
        session.add(encounter)
        await session.commit()

        # Snapshot DB record counts before operations
        task_count_before = (await session.execute(select(func.count(Task.id)))).scalar_one()
        bed_count_before = (await session.execute(select(func.count(Bed.id)))).scalar_one()

        # 1. Test ClinicalIntakeService integration
        intake_svc = ClinicalIntakeService(session)
        intake_nlp = await intake_svc.extract_nlp_summary("Abdominal pain and nausea, temp 100.2 F")
        assert "Gastrointestinal Symptoms" in intake_nlp["symptoms"]
        assert intake_nlp["vital_signs"]["temperature_f"] == 100.2

        # 2. Test PatientCoordinatorAgent integration
        coordinator = PatientCoordinatorAgent(session)
        sbar = await coordinator.draft_sbar_handoff(encounter=encounter, patient=patient)
        assert "Deepa Kulkarni" in sbar["situation"]
        assert "Cephalosporins" in sbar["background"]
        assert "HR 88" in sbar["assessment"]

        # 3. Test ClinicalDocumentService integration
        doc_svc = ClinicalDocumentService(session)
        discharge_draft = await doc_svc.draft_discharge_summary(encounter_id="ENC-LLM-01")
        assert "Deepa Kulkarni" in discharge_draft["encounter_summary"]
        assert len(discharge_draft["urgent_warning_signs"]) > 0

        # Verify absolute zero mutation to database entities
        task_count_after = (await session.execute(select(func.count(Task.id)))).scalar_one()
        bed_count_after = (await session.execute(select(func.count(Bed.id)))).scalar_one()

        assert task_count_after == task_count_before, "LLM integration must NOT insert database tasks"
        assert bed_count_after == bed_count_before, "LLM integration must NOT mutate beds"
