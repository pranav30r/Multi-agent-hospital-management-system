import pytest
from app.services.red_flag_service import RedFlagService


def test_red_flag_detection_vitals():
    """Test red flag detection for critical physiological thresholds."""
    rf_service = RedFlagService()

    # 1. Critical Hypoxia & Severe Tachycardia
    critical_vitals = {
        "spo2": 88,
        "heart_rate": 135,
        "bp_systolic": 190,
        "bp_diastolic": 115,
        "respiratory_rate": 30,
        "temperature_f": 104.0,
        "gcs_score": 11
    }
    flags = rf_service.detect_red_flags(encounter_vitals=critical_vitals)
    codes = [f["code"] for f in flags]

    assert "RF_CRITICAL_HYPOXIA" in codes
    assert "RF_SEVERE_TACHYCARDIA" in codes
    assert "RF_HYPERTENSIVE_CRISIS" in codes
    assert "RF_SEVERE_TACHYPNEA" in codes
    assert "RF_HIGH_GRADE_FEVER" in codes
    assert "RF_ALTERED_GCS" in codes

    # All these should be HIGH severity
    for f in flags:
        assert f["severity"] == "HIGH"


def test_red_flag_detection_normal_and_moderate():
    """Test normal vitals produce zero high-risk red flags, while moderate values trigger warnings."""
    rf_service = RedFlagService()

    # Normal vitals
    normal_vitals = {
        "spo2": 99,
        "heart_rate": 72,
        "bp_systolic": 120,
        "bp_diastolic": 80,
        "respiratory_rate": 16,
        "temperature_f": 98.6,
        "gcs_score": 15
    }
    flags_normal = rf_service.detect_red_flags(encounter_vitals=normal_vitals)
    assert len(flags_normal) == 0

    # Mild/moderate deviations
    mod_vitals = {
        "spo2": 92,
        "heart_rate": 118,
        "bp_systolic": 155,
        "bp_diastolic": 96,
        "gcs_score": 14
    }
    flags_mod = rf_service.detect_red_flags(encounter_vitals=mod_vitals)
    codes_mod = [f["code"] for f in flags_mod]
    assert "RF_MILD_HYPOXIA" in codes_mod
    assert "RF_TACHYCARDIA" in codes_mod
    assert "RF_STAGE2_HYPERTENSION" in codes_mod
    assert "RF_MILD_GCS_DECREASE" in codes_mod


def test_red_flag_symptoms_and_pain():
    """Test detection of high-risk symptoms and high pain scores."""
    rf_service = RedFlagService()

    intake_data = {
        "chief_complaint": "Sudden severe chest pain radiating to left arm",
        "symptoms": ["Shortness of breath", "Sweating", "Difficulty breathing"],
        "pain": {"score": 9, "location": "Substernal chest"}
    }
    flags = rf_service.detect_red_flags(encounter_vitals={}, intake_summary=intake_data)
    codes = [f["code"] for f in flags]

    assert "RF_CHEST_COMPLAINT" in codes
    assert "RF_RESPIRATORY_DISTRESS" in codes
    assert "RF_SEVERE_PAIN" in codes
