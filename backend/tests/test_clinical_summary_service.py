import pytest
from app.services.clinical_summary_service import ClinicalSummaryService


def test_clinical_summary_generation_structure():
    """Test structured summary generation distinguishing patient-reported, observed, and derived sections."""
    service = ClinicalSummaryService()

    patient_data = {
        "id": "PAT-101",
        "name": "Ananya Roy",
        "allergies": ["Sulfa"],
        "chronic_conditions": ["Hypertension"]
    }
    encounter_data = {
        "id": "ENC-201",
        "chief_complaint": "Acute headache",
        "patient_status": "ACTIVE",
        "current_department_id": "DEP-ER",
        "esi_level": 3,
        "vitals": {
            "heart_rate": 86,
            "bp_systolic": 142,
            "bp_diastolic": 90,
            "spo2": 98,
            "temperature_f": 98.6,
            "pain_level": 5
        }
    }
    intake_summary = {
        "chief_complaint": "Throbbing frontal headache with mild nausea",
        "symptoms": ["Frontal headache", "Photophobia"],
        "duration": "12 hours",
        "pain": {"score": 5, "location": "Forehead", "present": True},
        "medications": "Amlodipine 5mg",
        "allergies": ["Sulfa"],
        "past_medical_history": "Hypertension"
    }
    severity_assessment = {
        "severity": "MEDIUM",
        "score": 25.0,
        "requires_priority_attention": False,
        "reasons": ["Moderate reported pain level (5/10)"],
        "supporting_factors": ["Heart Rate: 86", "Systolic Blood Pressure: 142"],
        "missing_information": ["Respiratory Rate (respiratory_rate)"]
    }
    red_flags = []
    prior_encounters = [
        {"id": "ENC-099", "chief_complaint": "Routine health checkup", "status": "DISCHARGED"}
    ]

    summary = service.generate_summary(
        patient_data=patient_data,
        encounter_data=encounter_data,
        intake_summary=intake_summary,
        severity_assessment=severity_assessment,
        red_flags=red_flags,
        prior_encounters=prior_encounters
    )

    assert "meta" in summary
    assert "patient_reported" in summary
    assert "observed" in summary
    assert "derived" in summary
    assert "longitudinal" in summary

    # Patient Reported
    assert summary["patient_reported"]["chief_complaint"] == "Throbbing frontal headache with mild nausea"
    assert summary["patient_reported"]["pain"]["score"] == 5
    assert summary["patient_reported"]["medications"] == "Amlodipine 5mg"

    # Observed
    assert summary["observed"]["vitals"]["heart_rate"] == 86
    assert summary["observed"]["vitals"]["blood_pressure"] == "142/90"

    # Derived
    assert summary["derived"]["severity"] == "MEDIUM"
    assert summary["derived"]["requires_priority_attention"] is False
    assert len(summary["derived"]["missing_information"]) == 1

    # Longitudinal
    assert summary["longitudinal"]["total_prior_visits"] == 1
