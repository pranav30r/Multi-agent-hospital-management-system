import pytest
from app.services.clinical_severity_service import ClinicalSeverityService


def test_severity_computation_low():
    """Test LOW severity evaluation for stable vitals and mild symptoms."""
    service = ClinicalSeverityService()
    vitals = {
        "heart_rate": 74,
        "bp_systolic": 118,
        "bp_diastolic": 76,
        "spo2": 98,
        "temperature_f": 98.4,
        "pain_level": 2,
        "respiratory_rate": 16,
        "gcs_score": 15
    }
    intake_summary = {
        "chief_complaint": "Mild common cold and runny nose",
        "duration": "3 days",
        "pain": {"score": 2, "location": "Nose"}
    }
    res = service.compute_severity(encounter_vitals=vitals, intake_summary=intake_summary, red_flags=[])

    assert res["severity"] == "LOW"
    assert res["requires_priority_attention"] is False
    assert res["score"] < 20.0
    assert len(res["missing_information"]) == 0
    assert len(res["reasons"]) > 0


def test_severity_computation_medium():
    """Test MEDIUM severity evaluation for moderate pain and warnings."""
    service = ClinicalSeverityService()
    vitals = {
        "heart_rate": 110,
        "bp_systolic": 140,
        "bp_diastolic": 88,
        "spo2": 95,
        "temperature_f": 100.2,
        "pain_level": 6,
        "respiratory_rate": 20,
        "gcs_score": 15
    }
    intake_summary = {
        "chief_complaint": "Moderate ankle sprain with swelling",
        "duration": "1 day",
        "pain": {"score": 6, "location": "Right ankle"}
    }
    med_flag = [{
        "code": "RF_MODERATE_SEVERE_PAIN",
        "severity": "MEDIUM",
        "reason": "Moderate-severe reported pain score: 6/10"
    }]
    res = service.compute_severity(encounter_vitals=vitals, intake_summary=intake_summary, red_flags=med_flag)

    assert res["severity"] == "MEDIUM"
    assert res["requires_priority_attention"] is False
    assert res["score"] >= 20.0


def test_severity_computation_high_and_priority():
    """Test HIGH severity evaluation when high-risk red flags are detected."""
    service = ClinicalSeverityService()
    vitals = {
        "heart_rate": 136,
        "bp_systolic": 82,
        "bp_diastolic": 50,
        "spo2": 88,
        "temperature_f": 103.8,
        "pain_level": 9,
        "respiratory_rate": 28,
        "gcs_score": 12
    }
    high_flags = [
        {"code": "RF_CRITICAL_HYPOXIA", "severity": "HIGH", "reason": "Critical low oxygen saturation: 88%"},
        {"code": "RF_HYPOTENSION", "severity": "HIGH", "reason": "Severe hypotension: 82 mmHg"},
        {"code": "RF_SEVERE_PAIN", "severity": "HIGH", "reason": "Severe reported pain score: 9/10"}
    ]
    res = service.compute_severity(encounter_vitals=vitals, red_flags=high_flags, esi_level=2)

    assert res["severity"] == "HIGH"
    assert res["requires_priority_attention"] is True
    assert res["priority_reason"] is not None
    assert "88%" in res["priority_reason"] or "score" in res["priority_reason"]


def test_missing_information_tracking():
    """Test that missing vitals are explicitly recorded without inventing default values."""
    service = ClinicalSeverityService()
    vitals_empty = {}
    res = service.compute_severity(encounter_vitals=vitals_empty, intake_summary={})

    assert len(res["missing_information"]) >= 6
    missing_str = " ".join(res["missing_information"])
    assert "spo2" in missing_str
    assert "heart_rate" in missing_str
    assert "bp_systolic" in missing_str
