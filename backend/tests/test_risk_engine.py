"""
Focused Unit & Integration Tests for Standalone RiskEngine.
Verifies risk tiers (HIGH, MEDIUM, LOW), boundary conditions, clinical red flags,
hemodynamic instability escalation, human approval invariants, missing input resilience,
and backward compatibility with CoordinatorAgent.
"""

import pytest
from app.services.risk_engine import (
    RiskEngine,
    RiskPolicyConfig,
    RiskEvaluationResult,
    RiskTier,
    GovernanceActionType,
)
from app.models.patient import Patient, Encounter
from app.models.bed import Bed
from app.models.department import Department
from app.agents.coordinator_agent import CoordinatorAgent


# =====================================================================
# 1. High-Risk Tier & Boundary Conditions
# =====================================================================

def test_high_risk_tier_triggers():
    engine = RiskEngine()

    # Trigger A: Priority CRITICAL
    res = engine.evaluate(
        triage_output={"priority_level": "CRITICAL", "severity": "MODERATE", "red_flags": []},
        emergency_output={"escalation_required": False}
    )
    assert res.risk_level == RiskTier.HIGH
    assert res.action_type == GovernanceActionType.ICU_BED_ALLOCATION
    assert res.requires_human_approval is True
    assert res.confidence == 0.94
    assert res.proposed_action["priority"] == "CRITICAL"

    # Trigger B: Severity CRITICAL or HIGH
    for sev in ["CRITICAL", "HIGH"]:
        res = engine.evaluate(
            triage_output={"priority_level": "ROUTINE", "severity": sev, "red_flags": []},
            emergency_output={"escalation_required": False}
        )
        assert res.risk_level == RiskTier.HIGH
        assert res.requires_human_approval is True

    # Trigger C: Care Level ICU
    res = engine.evaluate(
        triage_output={"recommended_care_level": "ICU", "severity": "LOW", "red_flags": []},
        emergency_output={"escalation_required": False}
    )
    assert res.risk_level == RiskTier.HIGH
    assert res.requires_human_approval is True

    # Trigger D: 2 or more red flags
    res = engine.evaluate(
        triage_output={
            "priority_level": "ROUTINE",
            "severity": "LOW",
            "red_flags": [{"code": "RF_1"}, {"code": "RF_2"}]
        },
        emergency_output={"escalation_required": False}
    )
    assert res.risk_level == RiskTier.HIGH
    assert res.requires_human_approval is True

    # Trigger E: ESI Level 1
    res = engine.evaluate(
        triage_output={"esi_level": 1, "severity": "LOW", "red_flags": []},
        emergency_output={"escalation_required": False}
    )
    assert res.risk_level == RiskTier.HIGH
    assert res.requires_human_approval is True

    # Trigger F: Emergency Escalation Required
    res = engine.evaluate(
        triage_output={"priority_level": "ROUTINE", "severity": "LOW", "red_flags": []},
        emergency_output={"escalation_required": True, "emergency_level": "RAPID_RESPONSE_STAT"}
    )
    assert res.risk_level == RiskTier.HIGH
    assert res.requires_human_approval is True

    # Trigger G: Negotiation Status UNRESOLVED_ESCALATED
    res = engine.evaluate(
        triage_output={"priority_level": "ROUTINE", "severity": "LOW", "red_flags": []},
        emergency_output={"escalation_required": False},
        negotiation_status="UNRESOLVED_ESCALATED"
    )
    assert res.risk_level == RiskTier.HIGH
    assert res.requires_human_approval is True


# =====================================================================
# 2. Medium-Risk Tier & Boundary Conditions
# =====================================================================

def test_medium_risk_tier_triggers():
    engine = RiskEngine()

    # Trigger A: Priority HIGH (without other high triggers)
    res = engine.evaluate(
        triage_output={"priority_level": "HIGH", "severity": "MODERATE", "red_flags": []},
        emergency_output={"escalation_required": False}
    )
    assert res.risk_level == RiskTier.MEDIUM
    assert res.action_type == GovernanceActionType.SPECIALIST_CONSULT
    assert res.requires_human_approval is True
    assert res.confidence == 0.88
    assert res.proposed_action["specialty"] == "EMERGENCY_MEDICINE"
    assert res.proposed_action["priority"] == "HIGH"

    # Trigger B: Exactly 1 Red Flag
    res = engine.evaluate(
        triage_output={"priority_level": "ROUTINE", "severity": "LOW", "red_flags": [{"code": "RF_FEVER"}]},
        emergency_output={"escalation_required": False}
    )
    assert res.risk_level == RiskTier.MEDIUM
    assert res.requires_human_approval is True

    # Trigger C: Care Level EMERGENCY
    res = engine.evaluate(
        triage_output={"recommended_care_level": "EMERGENCY", "severity": "LOW", "red_flags": []},
        emergency_output={"escalation_required": False}
    )
    assert res.risk_level == RiskTier.MEDIUM
    assert res.requires_human_approval is True

    # Trigger D: ESI Level 2
    res = engine.evaluate(
        triage_output={"esi_level": 2, "severity": "LOW", "red_flags": []},
        emergency_output={"escalation_required": False}
    )
    assert res.risk_level == RiskTier.MEDIUM
    assert res.requires_human_approval is True


# =====================================================================
# 3. Low-Risk Tier: Observation Admission vs Standard OPD
# =====================================================================

def test_low_risk_observation_admission():
    engine = RiskEngine()

    # Priority MODERATE with stable vitals
    res = engine.evaluate(
        triage_output={"priority_level": "MODERATE", "severity": "LOW", "red_flags": []},
        emergency_output={"escalation_required": False},
        selected_plan={"target_department_id": "DEP-MED"}
    )
    assert res.risk_level == RiskTier.LOW
    assert res.action_type == GovernanceActionType.OBSERVATION_ADMISSION
    assert res.requires_human_approval is True
    assert res.confidence == 0.82
    assert res.proposed_action["action"] == "OBSERVE"
    assert res.proposed_action["department_code"] == "DEP-MED"

    # Care Level GENERAL with non-routine priority
    res2 = engine.evaluate(
        triage_output={"recommended_care_level": "GENERAL", "priority_level": "STANDARD", "severity": "LOW", "red_flags": []},
        emergency_output={"escalation_required": False}
    )
    assert res2.risk_level == RiskTier.LOW
    assert res2.action_type == GovernanceActionType.OBSERVATION_ADMISSION
    assert res2.requires_human_approval is True


def test_low_risk_standard_opd_routing():
    engine = RiskEngine()

    # Routine outpatient case
    res = engine.evaluate(
        triage_output={
            "priority_level": "ROUTINE",
            "severity": "LOW",
            "recommended_care_level": "OUTPATIENT",
            "red_flags": []
        },
        emergency_output={"escalation_required": False}
    )
    assert res.risk_level == RiskTier.LOW
    assert res.action_type == GovernanceActionType.STANDARD_OPD
    assert res.requires_human_approval is False
    assert res.confidence == 0.90
    assert res.proposed_action["action"] == "QUEUE_OPD"
    assert res.proposed_action["priority"] == "ROUTINE"


# =====================================================================
# 4. Hemodynamic Instability Escalation
# =====================================================================

def test_hemodynamic_instability_escalation():
    engine = RiskEngine()

    # Case A: Hypotension / Shock (SBP <= 85)
    res_sbp = engine.evaluate(
        triage_output={"priority_level": "ROUTINE", "severity": "LOW", "red_flags": []},
        encounter={"id": "ENC-01", "bp_systolic": 80, "spo2": 98, "gcs_score": 15}
    )
    assert res_sbp.risk_level == RiskTier.HIGH
    assert res_sbp.action_type == GovernanceActionType.ICU_BED_ALLOCATION
    assert res_sbp.requires_human_approval is True
    assert any("Hypotension/Shock" in rf for rf in res_sbp.risk_factors)

    # Case B: Severe Hypoxia (SpO2 <= 88)
    res_spo2 = engine.evaluate(
        triage_output={"priority_level": "ROUTINE", "severity": "LOW", "red_flags": []},
        encounter={"id": "ENC-02", "bp_systolic": 120, "spo2": 84, "gcs_score": 15}
    )
    assert res_spo2.risk_level == RiskTier.HIGH
    assert res_spo2.requires_human_approval is True
    assert any("Severe Hypoxia" in rf for rf in res_spo2.risk_factors)

    # Case C: Altered Sensorium / Coma (GCS <= 10)
    res_gcs = engine.evaluate(
        triage_output={"priority_level": "ROUTINE", "severity": "LOW", "red_flags": []},
        encounter={"id": "ENC-03", "bp_systolic": 120, "spo2": 99, "gcs_score": 7}
    )
    assert res_gcs.risk_level == RiskTier.HIGH
    assert res_gcs.requires_human_approval is True
    assert any("Altered Consciousness/Coma" in rf for rf in res_gcs.risk_factors)


# =====================================================================
# 5. Human Approval Invariants
# =====================================================================

def test_human_approval_governance_invariants():
    """
    Verifies the core governance invariant:
    - HIGH risk -> MUST require human approval.
    - MEDIUM risk -> MUST require human approval.
    - LOW risk (Observation Admission) -> MUST require human approval.
    - LOW risk (Standard OPD) -> Autonomous routing without human approval.
    """
    engine = RiskEngine()

    # High
    r_high = engine.evaluate(triage_output={"priority_level": "CRITICAL"})
    assert r_high.requires_human_approval is True

    # Medium
    r_med = engine.evaluate(triage_output={"priority_level": "HIGH", "severity": "MODERATE"})
    assert r_med.requires_human_approval is True

    # Low Obs
    r_obs = engine.evaluate(triage_output={"priority_level": "MODERATE", "severity": "LOW"})
    assert r_obs.requires_human_approval is True

    # Low OPD
    r_opd = engine.evaluate(triage_output={"priority_level": "ROUTINE", "severity": "LOW"})
    assert r_opd.requires_human_approval is False


# =====================================================================
# 6. Missing and Incomplete Input Resilience
# =====================================================================

def test_missing_and_incomplete_inputs():
    engine = RiskEngine()

    # Empty invocation
    r_none = engine.evaluate()
    assert r_none.risk_level == RiskTier.LOW
    assert r_none.action_type == GovernanceActionType.STANDARD_OPD
    assert r_none.requires_human_approval is False

    # Malformed red_flags (not a list)
    r_malformed_rf = engine.evaluate(triage_output={"red_flags": "none", "severity": None})
    assert r_malformed_rf.risk_level == RiskTier.LOW

    # Encounter with string / non-numeric vitals
    r_str_vitals = engine.evaluate(
        triage_output={"priority_level": "ROUTINE"},
        encounter={"bp_systolic": "invalid", "spo2": None, "gcs_score": "unknown"}
    )
    assert r_str_vitals.risk_level == RiskTier.LOW

    # All None explicit parameters
    r_all_none = engine.evaluate(
        triage_output=None,
        emergency_output=None,
        selected_plan=None,
        encounter=None,
        patient=None,
        negotiation_status=None,
        active_conflicts=None,
        bed_output=None,
        staff_output=None
    )
    assert r_all_none.risk_level == RiskTier.LOW
    assert r_all_none.action_type == GovernanceActionType.STANDARD_OPD


# =====================================================================
# 7. Deterministic Results
# =====================================================================

def test_deterministic_evaluation():
    engine = RiskEngine()
    triage_input = {
        "priority_level": "HIGH",
        "severity": "MODERATE",
        "red_flags": [{"code": "RF_TACHYCARDIA"}],
        "recommended_care_level": "EMERGENCY"
    }
    plan_input = {"target_bed_id": "BED-ER-01", "assigned_doctor_id": "DOC-01"}

    first_res = engine.evaluate(triage_output=triage_input, selected_plan=plan_input)

    for _ in range(50):
        next_res = engine.evaluate(triage_output=triage_input, selected_plan=plan_input)
        assert next_res.risk_level == first_res.risk_level
        assert next_res.action_type == first_res.action_type
        assert next_res.requires_human_approval == first_res.requires_human_approval
        assert next_res.confidence == first_res.confidence
        assert next_res.reasoning == first_res.reasoning
        assert next_res.proposed_action == first_res.proposed_action
        assert next_res.risk_score == first_res.risk_score
        assert next_res.risk_factors == first_res.risk_factors


# =====================================================================
# 8. Result Access Patterns (Object, Dict, Subscript)
# =====================================================================

def test_result_access_patterns():
    engine = RiskEngine()
    res = engine.evaluate(triage_output={"priority_level": "CRITICAL"})

    # Attribute access
    assert res.risk_level == "HIGH"
    assert res.action_type == "ICU_BED_ALLOCATION_RECOMMENDATION"

    # Subscript access
    assert res["risk_level"] == "HIGH"
    assert res["action_type"] == "ICU_BED_ALLOCATION_RECOMMENDATION"

    # get() method
    assert res.get("risk_level") == "HIGH"
    assert res.get("non_existent", "default_val") == "default_val"

    # to_dict()
    d = res.to_dict()
    assert isinstance(d, dict)
    assert d["risk_level"] == "HIGH"
    assert "risk_factors" in d


# =====================================================================
# 9. Custom Policy Configuration
# =====================================================================

def test_custom_policy_configuration():
    # Configure custom thresholds: ESI 3 triggers high risk, red flag threshold = 3
    custom_policy = RiskPolicyConfig(
        high_risk_esi_levels=(1, 3),
        high_risk_min_red_flags=3,
        confidence_high=0.99
    )
    custom_engine = RiskEngine(policy=custom_policy)

    # Acuity ESI 3 now triggers HIGH risk
    res_esi3 = custom_engine.evaluate(triage_output={"esi_level": 3, "red_flags": []})
    assert res_esi3.risk_level == RiskTier.HIGH
    assert res_esi3.confidence == 0.99

    # 2 Red flags now triggers MEDIUM risk (since min for high is 3)
    res_2rf = custom_engine.evaluate(
        triage_output={"priority_level": "ROUTINE", "severity": "LOW", "red_flags": [{"code": "A"}, {"code": "B"}]}
    )
    assert res_2rf.risk_level == RiskTier.MEDIUM


# =====================================================================
# 10. CoordinatorAgent Integration & Backward Compatibility
# =====================================================================

@pytest.mark.asyncio
async def test_coordinator_agent_integration_with_risk_engine(test_db):
    async with test_db() as session:
        dept = Department(
            id="DEP-ER-TEST",
            tenant_id="HOSP-DEFAULT",
            name="Emergency Department",
            code="ER-TEST",
            total_beds=4
        )
        bed = Bed(
            id="BED-ICU-TEST-01",
            department_id="DEP-ER-TEST",
            bed_type="ICU",
            status="AVAILABLE"
        )
        patient = Patient(
            id="PAT-RISK-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Vikram",
            last_name="Singh",
            age=55,
            gender="M",
            blood_group="O+",
            contact_phone="9876543210",
            emergency_contact="9876543211"
        )
        encounter = Encounter(
            id="ENC-RISK-01",
            patient_id="PAT-RISK-01",
            current_department_id="DEP-ER-TEST",
            chief_complaint="Severe chest pain and dyspnea",
            bp_systolic=80,
            spo2=86,
            heart_rate=130,
            gcs_score=13
        )
        session.add_all([dept, bed, patient, encounter])
        await session.commit()

        coordinator = CoordinatorAgent(session)
        assert isinstance(coordinator.risk_engine, RiskEngine)

        triage_output = {
            "recommended_care_level": "ICU",
            "severity": "CRITICAL",
            "priority_level": "CRITICAL",
            "red_flags": [{"code": "RF_HYPOXIA", "severity": "HIGH"}, {"code": "RF_SHOCK", "severity": "HIGH"}],
            "esi_level": 1
        }
        bed_output = {
            "feasibility": "FEASIBLE",
            "recommended_bed_id": "BED-ICU-TEST-01",
            "recommended_department_id": "DEP-ER-TEST",
            "bed_type": "ICU"
        }
        staff_output = {
            "feasibility": "FEASIBLE",
            "assigned_doctor_id": "DOC-TEST-01",
            "assigned_nurse_id": "NUR-TEST-01"
        }
        emergency_output = {
            "escalation_required": True,
            "emergency_level": "CRITICAL_CODE_BLUE",
            "recommended_emergency_actions": ["ACTIVATE_RAPID_RESPONSE_TEAM"]
        }
        coordinator_output = {
            "discharge_readiness": "NOT_READY"
        }

        result = await coordinator.coordinate(
            triage_output=triage_output,
            bed_output=bed_output,
            staff_output=staff_output,
            emergency_output=emergency_output,
            coordinator_output=coordinator_output,
            encounter=encounter,
            patient=patient,
            tenant_id="HOSP-DEFAULT"
        )

        assert result["action_type"] == "ICU_BED_ALLOCATION_RECOMMENDATION"
        assert result["risk_level"] == "HIGH"
        assert result["requires_human_approval"] is True
        assert result["approval_item_id"] is not None
        assert result["status"] == "PROPOSED"
        assert "risk_evaluation" in result
        assert result["risk_evaluation"]["risk_level"] == "HIGH"
        assert result["risk_evaluation"]["policy_tier"] == "HIGH_ACUITY_CRITICAL"
