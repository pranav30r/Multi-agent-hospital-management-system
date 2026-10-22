"""
Focused Unit & Integration Tests for Dedicated ConstraintOptimizer.
Verifies dynamic input response, deterministic calculations, weight normalization,
hard constraint enforcement, missing data resilience, penalty calculations,
candidate ranking, and integration with CoordinatorAgent and OptimizationRun.
"""

import pytest
from app.services.constraint_optimizer import (
    ConstraintOptimizer,
    ConstraintOptimizerConfig,
    OptimizerResult,
)
from app.models.patient import Patient, Encounter
from app.models.bed import Bed
from app.models.department import Department
from app.models.agent import OptimizationRun
from app.agents.coordinator_agent import CoordinatorAgent
from sqlalchemy import select


def _sample_candidates():
    return [
        {
            "plan_index": 0,
            "plan_type": "PRIMARY_RECOMMENDED",
            "care_level": "ICU",
            "target_bed_id": "BED-ICU-01",
            "target_department_id": "DEP-ICU",
            "assigned_doctor_id": "DOC-01",
            "assigned_nurse_id": "NUR-01",
            "description": "Direct ICU admission"
        },
        {
            "plan_index": 1,
            "plan_type": "ALTERNATIVE_STEP_DOWN",
            "care_level": "EMERGENCY",
            "target_bed_id": "BED-ER-02",
            "target_department_id": "DEP-ER",
            "assigned_doctor_id": "DOC-01",
            "assigned_nurse_id": "NUR-01",
            "description": "Step-down emergency bay placement"
        },
        {
            "plan_index": 2,
            "plan_type": "CONTINGENCY_SURGE",
            "care_level": "EMERGENCY_HOLDING",
            "target_bed_id": None,
            "target_department_id": "DEP-ER",
            "assigned_doctor_id": "DOC-01",
            "assigned_nurse_id": "NUR-01",
            "description": "ED holding stabilization"
        }
    ]


# =====================================================================
# 1. Objective Scores Respond to Candidate Inputs
# =====================================================================

def test_objective_scores_respond_to_candidate_inputs():
    optimizer = ConstraintOptimizer()
    candidates = _sample_candidates()

    # Base run: zero wait time, low occupancy, optimal nurse load
    base_res = optimizer.optimize(
        candidates=candidates,
        triage_output={"recommended_care_level": "ICU"},
        bed_output={"feasibility": "FEASIBLE", "occupancy_rate": 0.65},
        staff_output={"feasibility": "FEASIBLE", "avg_nurse_load": 1.5}
    )
    base_p0 = base_res.scored_candidates[0]

    # Run with delayed wait time (e.g. 60 mins wait)
    cand_delayed = [dict(c) for c in candidates]
    cand_delayed[0]["wait_time_minutes"] = 60.0
    res_delayed = optimizer.optimize(
        candidates=cand_delayed,
        triage_output={"recommended_care_level": "ICU"},
        bed_output={"feasibility": "FEASIBLE", "occupancy_rate": 0.65},
        staff_output={"feasibility": "FEASIBLE", "avg_nurse_load": 1.5}
    )
    p0_delayed = res_delayed.scored_candidates[0]

    assert p0_delayed["waiting_time_score"] < base_p0["waiting_time_score"]
    assert p0_delayed["objective_score"] < base_p0["objective_score"]

    # Run with saturated bed occupancy (98%)
    res_occupied = optimizer.optimize(
        candidates=candidates,
        triage_output={"recommended_care_level": "ICU"},
        bed_output={"feasibility": "CONSTRAINED", "occupancy_rate": 0.98},
        staff_output={"feasibility": "FEASIBLE", "avg_nurse_load": 1.5}
    )
    p0_occupied = res_occupied.scored_candidates[0]
    assert p0_occupied["resource_util_score"] < base_p0["resource_util_score"]

    # Run with overloaded nurse staffing (load 7.0)
    res_staff_overload = optimizer.optimize(
        candidates=candidates,
        triage_output={"recommended_care_level": "ICU"},
        bed_output={"feasibility": "FEASIBLE", "occupancy_rate": 0.65},
        staff_output={"feasibility": "WARNING_OVERLOAD", "avg_nurse_load": 7.0}
    )
    p0_staff = res_staff_overload.scored_candidates[0]
    assert p0_staff["staff_balance_score"] < base_p0["staff_balance_score"]


# =====================================================================
# 2. Deterministic Scoring
# =====================================================================

def test_deterministic_scoring():
    optimizer = ConstraintOptimizer()
    candidates = _sample_candidates()
    context = {
        "triage_output": {"recommended_care_level": "ICU"},
        "bed_output": {"feasibility": "FEASIBLE", "occupancy_rate": 0.70},
        "staff_output": {"feasibility": "FEASIBLE", "avg_nurse_load": 2.0},
        "negotiation_status": "NONE"
    }

    first_res = optimizer.optimize(candidates=candidates, **context)

    for _ in range(50):
        next_res = optimizer.optimize(candidates=candidates, **context)
        assert next_res.selected_plan_index == first_res.selected_plan_index
        assert next_res.objective_score == first_res.objective_score
        assert next_res.waiting_time_score == first_res.waiting_time_score
        assert next_res.resource_util_score == first_res.resource_util_score
        assert next_res.staff_balance_score == first_res.staff_balance_score
        for i in range(len(candidates)):
            assert next_res.scored_candidates[i]["objective_score"] == first_res.scored_candidates[i]["objective_score"]


# =====================================================================
# 3. Objective Weight Configuration and Normalization
# =====================================================================

def test_objective_weight_configuration_and_normalization():
    # 1. Non-normalized weights (e.g. 50, 30, 20) are properly normalized to (0.5, 0.3, 0.2)
    cfg = ConstraintOptimizerConfig(
        weight_waiting_time=50.0,
        weight_resource_util=30.0,
        weight_staff_balance=20.0
    )
    w_w, w_u, w_s = cfg.get_normalized_weights()
    assert round(w_w, 2) == 0.50
    assert round(w_u, 2) == 0.30
    assert round(w_s, 2) == 0.20
    assert round(w_w + w_u + w_s, 4) == 1.0

    # 2. Extreme weight configuration shifts preference
    wait_heavy_cfg = ConstraintOptimizerConfig(
        weight_waiting_time=0.90,
        weight_resource_util=0.05,
        weight_staff_balance=0.05
    )
    optimizer_wait = ConstraintOptimizer(config=wait_heavy_cfg)

    cands = [
        {
            "plan_index": 0,
            "plan_type": "FAST_WAIT_POOR_STAFF",
            "wait_time_minutes": 0.0,
            "avg_nurse_load": 8.0,
            "occupancy_rate": 0.95
        },
        {
            "plan_index": 1,
            "plan_type": "SLOW_WAIT_IDEAL_STAFF",
            "wait_time_minutes": 90.0,
            "avg_nurse_load": 1.0,
            "occupancy_rate": 0.50
        }
    ]

    res_wait_heavy = optimizer_wait.optimize(candidates=cands)
    # The fast wait candidate wins under wait-heavy weights
    assert res_wait_heavy.selected_plan_index == 0


# =====================================================================
# 4. Hard Constraint Violations & Infeasible Candidates
# =====================================================================

def test_hard_constraint_violations_and_infeasible_candidates():
    optimizer = ConstraintOptimizer()
    candidates = _sample_candidates()

    # Scenario: Bed capacity conflict active, negotiation UNRESOLVED
    conflicts = [{
        "type": "BED_CAPACITY_CONFLICT",
        "severity": "CRITICAL",
        "description": "Zero ICU beds available"
    }]

    res_unresolved = optimizer.optimize(
        candidates=candidates,
        triage_output={"recommended_care_level": "ICU"},
        bed_output={"feasibility": "UNAVAILABLE"},
        staff_output={"feasibility": "FEASIBLE"},
        negotiation_status="NONE",
        active_conflicts=conflicts
    )

    p0 = res_unresolved.scored_candidates[0]
    p1 = res_unresolved.scored_candidates[1]

    # Plan 0 fails hard constraint
    assert p0["hard_constraint_pass"] is False
    assert any("Bed capacity unavailable" in r for r in p0["penalty_reasons"])

    # Plan 1 passes hard constraint
    assert p1["hard_constraint_pass"] is True

    # Critical invariant: Infeasible candidate cannot be selected over feasible candidate!
    assert res_unresolved.selected_plan_index == 1
    assert res_unresolved.selected_plan["plan_type"] == "ALTERNATIVE_STEP_DOWN"

    # Now resolve negotiation -> Plan 0 becomes feasible
    res_resolved = optimizer.optimize(
        candidates=candidates,
        triage_output={"recommended_care_level": "ICU"},
        bed_output={"feasibility": "FEASIBLE"},
        staff_output={"feasibility": "FEASIBLE"},
        negotiation_status="RESOLVED",
        active_conflicts=conflicts
    )
    assert res_resolved.scored_candidates[0]["hard_constraint_pass"] is True
    assert res_resolved.selected_plan_index == 0


# =====================================================================
# 5. Missing & Incomplete Data Resilience
# =====================================================================

def test_missing_and_incomplete_data_resilience():
    optimizer = ConstraintOptimizer()

    # Minimal candidates with empty/None context
    minimal_cands = [{"plan_index": 0, "plan_type": "PRIMARY"}]
    res = optimizer.optimize(
        candidates=minimal_cands,
        triage_output=None,
        bed_output=None,
        staff_output=None,
        emergency_output=None,
        negotiation_status=None,
        active_conflicts=None
    )

    assert res.selected_plan_index == 0
    assert 0.0 <= res.objective_score <= 1.0
    assert 0.0 <= res.waiting_time_score <= 1.0
    assert 0.0 <= res.resource_util_score <= 1.0
    assert 0.0 <= res.staff_balance_score <= 1.0
    assert res.hard_constraint_pass is True

    # Candidates with invalid non-numeric measurements
    cands_invalid = [{
        "plan_index": 0,
        "wait_time_minutes": "unknown",
        "occupancy_rate": "invalid",
        "avg_nurse_load": None
    }]
    res_invalid = optimizer.optimize(candidates=cands_invalid)
    assert 0.0 <= res_invalid.objective_score <= 1.0

    # Empty candidate list raises ValueError
    with pytest.raises(ValueError):
        optimizer.optimize(candidates=[])


# =====================================================================
# 6. Bed-Tier Mismatch & Transfer Delay Penalties
# =====================================================================

def test_bed_tier_mismatch_and_transfer_delay_penalties():
    optimizer = ConstraintOptimizer()

    candidates = [
        {
            "plan_index": 0,
            "care_level": "GENERAL",  # Mismatch: patient needs ICU
            "target_department_id": "DEP-WARD-B",
            "transfer_delay_minutes": 45.0
        }
    ]

    res = optimizer.optimize(
        candidates=candidates,
        triage_output={"recommended_care_level": "ICU"},
        bed_output={"recommended_department_id": "DEP-ICU"}
    )

    p0 = res.scored_candidates[0]
    assert p0["penalties_applied"] > 0.0
    reasons_str = " ".join(p0["penalty_reasons"])
    assert "Acuity mismatch" in reasons_str
    assert "Transfer delay" in reasons_str


# =====================================================================
# 7. Staffing Ratio & Workload Evaluation
# =====================================================================

def test_staffing_ratio_and_workload_evaluation():
    optimizer = ConstraintOptimizer()

    # Optimal staffing ratio (1.5:1)
    res_optimal = optimizer.optimize(
        candidates=[{"plan_index": 0, "assigned_doctor_id": "DOC-1", "assigned_nurse_id": "NUR-1"}],
        staff_output={"feasibility": "FEASIBLE", "avg_nurse_load": 1.5}
    )
    # Severe overload ratio (7.5:1)
    res_overload = optimizer.optimize(
        candidates=[{"plan_index": 0, "assigned_doctor_id": "DOC-1", "assigned_nurse_id": "NUR-1"}],
        staff_output={"feasibility": "WARNING_OVERLOAD", "avg_nurse_load": 7.5}
    )

    assert res_optimal.scored_candidates[0]["staff_balance_score"] > res_overload.scored_candidates[0]["staff_balance_score"]

    # Missing staff assignment penalizes staff balance score
    res_unassigned = optimizer.optimize(
        candidates=[{"plan_index": 0, "assigned_doctor_id": None, "assigned_nurse_id": None}],
        staff_output={"feasibility": "FEASIBLE"}
    )
    assert res_unassigned.scored_candidates[0]["staff_balance_score"] < res_optimal.scored_candidates[0]["staff_balance_score"]


# =====================================================================
# 8. Candidate Ranking & Tie-Breaking
# =====================================================================

def test_candidate_ranking_and_tie_breaking():
    optimizer = ConstraintOptimizer()

    # Two identical candidates: tie-breaking selects lower plan_index
    cands_tie = [
        {"plan_index": 0, "plan_type": "PLAN_A"},
        {"plan_index": 1, "plan_type": "PLAN_B"}
    ]
    res_tie = optimizer.optimize(candidates=cands_tie)
    assert res_tie.selected_plan_index == 0

    # Infeasible Plan 0 with higher raw terms vs Feasible Plan 1
    cands_feasibility = [
        {"plan_index": 0, "hard_constraint_pass": False, "plan_type": "INFEASIBLE_HIGH_RESOURCE"},
        {"plan_index": 1, "hard_constraint_pass": True, "plan_type": "FEASIBLE_MODERATE"}
    ]
    res_feasibility = optimizer.optimize(candidates=cands_feasibility)
    assert res_feasibility.selected_plan_index == 1


# =====================================================================
# 9. Compatibility with OptimizationRun Data Structures
# =====================================================================

def test_compatibility_with_optimization_run_structure():
    optimizer = ConstraintOptimizer()
    candidates = _sample_candidates()

    res = optimizer.optimize(candidates=candidates)
    d = res.to_dict()

    # Check that required OptimizationRun model fields are provided
    assert "selected_plan_index" in d
    assert "selected_plan" in d
    assert "objective_score" in d
    assert "waiting_time_score" in d
    assert "resource_util_score" in d
    assert "staff_balance_score" in d
    assert "hard_constraint_pass" in d
    assert "candidates_count" in d
    assert "candidates" in d
    assert len(d["candidates"]) == 3


# =====================================================================
# 10. CoordinatorAgent End-to-End Integration
# =====================================================================

@pytest.mark.asyncio
async def test_coordinator_agent_integration_with_constraint_optimizer(test_db):
    async with test_db() as session:
        dept = Department(
            id="DEP-OPT-01",
            tenant_id="HOSP-DEFAULT",
            name="Intensive Care Unit",
            code="ICU-OPT",
            total_beds=5
        )
        bed = Bed(
            id="BED-OPT-01",
            department_id="DEP-OPT-01",
            bed_type="ICU",
            status="AVAILABLE"
        )
        patient = Patient(
            id="PAT-OPT-01",
            tenant_id="HOSP-DEFAULT",
            first_name="Ramesh",
            last_name="Gupta",
            age=58,
            gender="M",
            blood_group="B+",
            contact_phone="9811223344",
            emergency_contact="9811223345"
        )
        encounter = Encounter(
            id="ENC-OPT-01",
            patient_id="PAT-OPT-01",
            current_department_id="DEP-OPT-01",
            chief_complaint="Severe respiratory distress and tachycardia",
            bp_systolic=90,
            spo2=87,
            heart_rate=125,
            gcs_score=14
        )
        session.add_all([dept, bed, patient, encounter])
        await session.commit()

        coordinator = CoordinatorAgent(session)
        assert isinstance(coordinator.constraint_optimizer, ConstraintOptimizer)

        triage_output = {
            "recommended_care_level": "ICU",
            "severity": "CRITICAL",
            "priority_level": "CRITICAL",
            "red_flags": [{"code": "RF_HYPOXIA", "severity": "HIGH"}],
            "esi_level": 1
        }
        bed_output = {
            "feasibility": "FEASIBLE",
            "recommended_bed_id": "BED-OPT-01",
            "recommended_department_id": "DEP-OPT-01",
            "bed_type": "ICU",
            "occupancy_rate": 0.72
        }
        staff_output = {
            "feasibility": "FEASIBLE",
            "assigned_doctor_id": "DOC-OPT-01",
            "assigned_nurse_id": "NUR-OPT-01",
            "avg_nurse_load": 1.8
        }
        emergency_output = {
            "escalation_required": True,
            "emergency_level": "RAPID_RESPONSE_STAT",
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

        assert result["selected_plan"] is not None
        assert result["selected_plan"]["objective_score"] > 0.0
        assert "optimization_result" in result
        assert result["optimization_result"]["selected_plan_index"] == 0
        assert len(result["candidate_plans"]) >= 3

        # Verify persisted OptimizationRun entity
        opt_run = (
            await session.execute(
                select(OptimizationRun).where(OptimizationRun.id == result["optimization_run_id"])
            )
        ).scalar_one()
        assert opt_run.objective_score > 0.0
        assert opt_run.waiting_time_score > 0.0
        assert opt_run.resource_util_score > 0.0
        assert opt_run.staff_balance_score > 0.0
        assert opt_run.hard_constraint_pass is True
        assert opt_run.selected_plan_index == 0
