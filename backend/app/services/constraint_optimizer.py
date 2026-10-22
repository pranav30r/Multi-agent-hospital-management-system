"""
Dedicated Multi-Objective Constraint Optimizer.
Evaluates candidate operational plans against capacity, transfer delay, staffing ratios,
and bed-tier compatibility. Replaces static scores with explicit, deterministic mathematical
objective calculations and hard constraint enforcement.

Formula:
    Objective Score = w_w * S_wait + w_u * S_util + w_s * S_staff - P_penalties
where:
    w_w + w_u + w_s = 1.0 (normalized weights)
    S_wait, S_util, S_staff in [0.0, 1.0] (higher is better)
    P_penalties = P_mismatch + P_transfer + P_hard_violation
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConstraintOptimizerConfig:
    """
    Configurable weights, penalties, and threshold coefficients for candidate operational plan scoring.
    """
    # Objective weights (normalized to sum to 1.0)
    weight_waiting_time: float = 0.35
    weight_resource_util: float = 0.35
    weight_staff_balance: float = 0.30

    # Constraint penalty coefficients
    penalty_tier_mismatch: float = 0.08
    penalty_transfer_delay: float = 0.05
    penalty_staff_overload: float = 0.08
    penalty_hard_constraint_violation: float = 0.22

    # Operational thresholds
    max_acceptable_wait_minutes: float = 120.0
    optimal_nurse_patient_ratio: float = 2.0
    max_acceptable_nurse_ratio: float = 6.0
    optimal_occupancy_rate: float = 0.85

    def get_normalized_weights(self) -> Tuple[float, float, float]:
        """Returns normalized (w_wait, w_util, w_staff) summing to 1.0."""
        total = self.weight_waiting_time + self.weight_resource_util + self.weight_staff_balance
        if total <= 0:
            return (0.35, 0.35, 0.30)
        return (
            self.weight_waiting_time / total,
            self.weight_resource_util / total,
            self.weight_staff_balance / total
        )


@dataclass
class OptimizerResult:
    """
    Authoritative result of candidate plan optimization and ranking.
    """
    scored_candidates: List[Dict[str, Any]]
    selected_plan: Dict[str, Any]
    selected_plan_index: int
    feasible_candidates_count: int
    hard_constraint_pass: bool
    objective_score: float
    waiting_time_score: float
    resource_util_score: float
    staff_balance_score: float
    optimization_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_plan_index": self.selected_plan_index,
            "selected_plan": self.selected_plan,
            "objective_score": self.objective_score,
            "waiting_time_score": self.waiting_time_score,
            "resource_util_score": self.resource_util_score,
            "staff_balance_score": self.staff_balance_score,
            "hard_constraint_pass": self.hard_constraint_pass,
            "feasible_candidates_count": self.feasible_candidates_count,
            "candidates_count": len(self.scored_candidates),
            "candidates": self.scored_candidates,
            "optimization_metadata": self.optimization_metadata
        }


class ConstraintOptimizer:
    """
    Deterministic Multi-Objective Plan Optimizer.
    Evaluates candidate plans across clinical waiting time, bed utilization,
    staffing ratios, and constraint penalties, enforcing hard constraint feasibility.
    """

    def __init__(self, config: Optional[ConstraintOptimizerConfig] = None):
        self.config = config or ConstraintOptimizerConfig()

    def optimize(
        self,
        candidates: List[Dict[str, Any]],
        triage_output: Optional[Dict[str, Any]] = None,
        bed_output: Optional[Dict[str, Any]] = None,
        staff_output: Optional[Dict[str, Any]] = None,
        emergency_output: Optional[Dict[str, Any]] = None,
        negotiation_status: str = "NONE",
        active_conflicts: Optional[List[Dict[str, Any]]] = None,
    ) -> OptimizerResult:
        """
        Evaluates, scores, and ranks candidate operational plans.
        Returns the scored candidate list and the optimal feasible plan.
        """
        if not candidates:
            raise ValueError("ConstraintOptimizer requires at least one candidate plan.")

        triage = triage_output or {}
        bed = bed_output or {}
        staff = staff_output or {}
        emergency = emergency_output or {}
        conflicts = active_conflicts or []
        w_wait, w_util, w_staff = self.config.get_normalized_weights()

        scored_candidates: List[Dict[str, Any]] = []

        for candidate in candidates:
            cand = dict(candidate)
            plan_index = cand.get("plan_index", 0)
            plan_type = cand.get("plan_type", "PRIMARY_RECOMMENDED")

            # 1. Compute Waiting Time Score S_wait in [0.0, 1.0]
            s_wait = self._compute_waiting_time_score(cand, triage, bed, emergency)

            # 2. Compute Resource Utilization Score S_util in [0.0, 1.0]
            s_util = self._compute_resource_util_score(cand, triage, bed, emergency, conflicts, negotiation_status)

            # 3. Compute Staff Balance Score S_staff in [0.0, 1.0]
            s_staff = self._compute_staff_balance_score(cand, triage, staff, emergency)

            # 4. Compute Penalties P_penalties and Hard Constraint Pass
            penalties, penalty_reasons, hard_pass = self._compute_penalties(
                cand, triage, bed, staff, emergency, conflicts, negotiation_status
            )

            # 5. Composite Objective Score
            raw_score = (w_wait * s_wait) + (w_util * s_util) + (w_staff * s_staff) - penalties
            composite_score = round(max(0.0, min(1.0, raw_score)), 2)

            # Populate scored candidate fields
            cand["waiting_time_score"] = round(s_wait, 2)
            cand["resource_util_score"] = round(s_util, 2)
            cand["staff_balance_score"] = round(s_staff, 2)
            cand["objective_score"] = composite_score
            cand["hard_constraint_pass"] = hard_pass
            cand["penalties_applied"] = round(penalties, 3)
            cand["penalty_reasons"] = penalty_reasons

            scored_candidates.append(cand)

        # 6. Rank Candidates: Feasible plans ALWAYS precede infeasible plans.
        # Ties among feasible plans are broken by objective_score descending, then plan_index ascending.
        def rank_key(c: Dict[str, Any]) -> Tuple[int, float, int]:
            # Feasible = 1, Infeasible = 0
            is_feasible = 1 if c["hard_constraint_pass"] else 0
            score = c["objective_score"]
            # Lower plan index preferred in exact ties
            inv_index = -c.get("plan_index", 0)
            return (is_feasible, score, inv_index)

        ranked = sorted(scored_candidates, key=rank_key, reverse=True)
        selected_plan = ranked[0]
        selected_plan_idx = selected_plan.get("plan_index", 0)
        feasible_count = sum(1 for c in scored_candidates if c["hard_constraint_pass"])

        metadata = {
            "weights": {
                "waiting_time": w_wait,
                "resource_util": w_util,
                "staff_balance": w_staff
            },
            "total_candidates": len(scored_candidates),
            "feasible_candidates": feasible_count,
            "negotiation_status": negotiation_status,
            "active_conflicts_count": len(conflicts),
            "selection_strategy": "FEASIBLE_MAX_OBJECTIVE"
        }

        return OptimizerResult(
            scored_candidates=scored_candidates,
            selected_plan=selected_plan,
            selected_plan_index=selected_plan_idx,
            feasible_candidates_count=feasible_count,
            hard_constraint_pass=selected_plan["hard_constraint_pass"],
            objective_score=selected_plan["objective_score"],
            waiting_time_score=selected_plan["waiting_time_score"],
            resource_util_score=selected_plan["resource_util_score"],
            staff_balance_score=selected_plan["staff_balance_score"],
            optimization_metadata=metadata
        )

    def _compute_waiting_time_score(
        self,
        candidate: Dict[str, Any],
        triage: Dict[str, Any],
        bed: Dict[str, Any],
        emergency: Dict[str, Any]
    ) -> float:
        """
        Computes clinical waiting time satisfaction S_wait in [0.0, 1.0].
        Direction: Higher is better (1.0 = immediate placement, 0.0 = excessive delay).
        """
        # If explicit wait time in minutes is specified on candidate or bed output
        wait_mins = candidate.get("wait_time_minutes")
        if wait_mins is None:
            wait_mins = candidate.get("estimated_wait_minutes")
        if wait_mins is None:
            wait_mins = bed.get("estimated_wait_minutes")

        if wait_mins is not None:
            try:
                mins = max(0.0, float(wait_mins))
                # Linear decay over max_acceptable_wait_minutes
                score = 1.0 - (mins / self.config.max_acceptable_wait_minutes)
                return max(0.0, min(1.0, score))
            except (ValueError, TypeError):
                pass

        # Fallback to structural plan type characteristics
        plan_type = candidate.get("plan_type", "PRIMARY_RECOMMENDED")
        bed_feasibility = bed.get("feasibility", "FEASIBLE")

        if plan_type in ["PRIMARY_RECOMMENDED", "NEGOTIATED_OPTIMAL"]:
            if bed_feasibility == "FEASIBLE":
                return 0.95
            elif bed_feasibility == "CONSTRAINED":
                return 0.80
            else:
                return 0.50
        elif plan_type == "ALTERNATIVE_STEP_DOWN":
            return 0.85
        elif plan_type == "CONTINGENCY_SURGE":
            return 0.70
        else:
            return 0.80

    def _compute_resource_util_score(
        self,
        candidate: Dict[str, Any],
        triage: Dict[str, Any],
        bed: Dict[str, Any],
        emergency: Dict[str, Any],
        conflicts: List[Dict[str, Any]],
        negotiation_status: str
    ) -> float:
        """
        Computes resource utilization score S_util in [0.0, 1.0].
        Direction: Higher is better (optimal utilization without bottleneck saturation).
        """
        # If explicit occupancy rate is available
        occupancy = candidate.get("occupancy_rate")
        if occupancy is None:
            occupancy = bed.get("occupancy_rate")

        if occupancy is not None:
            try:
                occ = max(0.0, min(1.0, float(occupancy)))
                if occ <= 0.75:
                    return 0.92
                elif occ <= self.config.optimal_occupancy_rate:  # <= 0.85
                    return 0.88
                elif occ <= 0.95:
                    return 0.75
                else:
                    return 0.55
            except (ValueError, TypeError):
                pass

        # Context-aware structural plan type scoring
        plan_type = candidate.get("plan_type", "PRIMARY_RECOMMENDED")
        bed_feasibility = bed.get("feasibility", "FEASIBLE")

        if plan_type in ["PRIMARY_RECOMMENDED", "NEGOTIATED_OPTIMAL"]:
            if negotiation_status == "RESOLVED":
                return 0.85
            if any(c.get("type") == "BED_CAPACITY_CONFLICT" for c in conflicts):
                return 0.60
            if bed_feasibility == "CONSTRAINED":
                return 0.75
            return 0.88
        elif plan_type == "ALTERNATIVE_STEP_DOWN":
            return 0.80
        elif plan_type == "CONTINGENCY_SURGE":
            return 0.75
        else:
            return 0.80

    def _compute_staff_balance_score(
        self,
        candidate: Dict[str, Any],
        triage: Dict[str, Any],
        staff: Dict[str, Any],
        emergency: Dict[str, Any]
    ) -> float:
        """
        Computes staff balance and workload ratio score S_staff in [0.0, 1.0].
        Direction: Higher is better (balanced nurse/physician workload, no burnout overload).
        """
        # If explicit nurse-patient ratio or nurse workload load is available
        nurse_load = candidate.get("avg_nurse_load")
        if nurse_load is None:
            nurse_load = staff.get("avg_nurse_load")

        if nurse_load is not None:
            try:
                load = max(0.0, float(nurse_load))
                if load <= self.config.optimal_nurse_patient_ratio:
                    return 0.92
                elif load <= 4.0:
                    return 0.88
                elif load <= self.config.max_acceptable_nurse_ratio:
                    return 0.75
                else:
                    return 0.60
            except (ValueError, TypeError):
                pass

        # Evaluate based on staff agent feasibility
        feasibility = staff.get("feasibility", "FEASIBLE")
        assigned_doc = candidate.get("assigned_doctor_id") or staff.get("assigned_doctor_id")
        assigned_nurse = candidate.get("assigned_nurse_id") or staff.get("assigned_nurse_id")

        base_score = 0.90
        if feasibility in ["FEASIBLE", "REBALANCED"]:
            base_score = 0.90
        elif feasibility == "WARNING_OVERLOAD":
            base_score = 0.75
        elif feasibility == "CRITICAL_SHORTAGE":
            base_score = 0.65
        else:
            base_score = 0.85

        # Penalize if assigned doctor or nurse is missing from the plan
        if not assigned_doc or not assigned_nurse:
            base_score = max(0.50, base_score - 0.10)

        return base_score

    def _compute_penalties(
        self,
        candidate: Dict[str, Any],
        triage: Dict[str, Any],
        bed: Dict[str, Any],
        staff: Dict[str, Any],
        emergency: Dict[str, Any],
        conflicts: List[Dict[str, Any]],
        negotiation_status: str
    ) -> Tuple[float, List[str], bool]:
        """
        Calculates penalty deductions and determines hard constraint satisfaction.
        Returns: (total_penalties, penalty_reasons, hard_constraint_pass)
        """
        total_penalties = 0.0
        reasons: List[str] = []
        hard_pass = True

        plan_type = candidate.get("plan_type", "PRIMARY_RECOMMENDED")
        care_level = candidate.get("care_level")
        rec_care_level = triage.get("recommended_care_level")

        # -------------------------------------------------------------
        # Hard Constraint Checks
        # -------------------------------------------------------------
        # 1. Unresolved Bed Shortage for Primary Plan
        if plan_type in ["PRIMARY_RECOMMENDED", "NEGOTIATED_OPTIMAL"]:
            has_bed_conflict = any(c.get("type") == "BED_CAPACITY_CONFLICT" for c in conflicts)
            if has_bed_conflict and negotiation_status != "RESOLVED":
                hard_pass = False
                total_penalties += self.config.penalty_hard_constraint_violation
                reasons.append("Hard constraint failure: Bed capacity unavailable without resolution")

        # 2. Critical Staff Shortage
        if staff.get("feasibility") == "CRITICAL_SHORTAGE":
            if any(c.get("type") == "STAFF_SHORTAGE_CONFLICT" for c in conflicts):
                if negotiation_status != "RESOLVED":
                    hard_pass = False
                    total_penalties += self.config.penalty_hard_constraint_violation
                    reasons.append("Hard constraint failure: Critical clinical staff shortage")

        # 3. Explicit candidate hard_constraint_pass override
        if candidate.get("hard_constraint_pass") is False:
            hard_pass = False
            total_penalties += self.config.penalty_hard_constraint_violation
            reasons.append("Hard constraint failure: Explicit plan infeasibility flag")

        # -------------------------------------------------------------
        # Soft Penalties: Bed-Tier Acuity Mismatch
        # -------------------------------------------------------------
        if rec_care_level and care_level:
            if rec_care_level == "ICU" and care_level in ["GENERAL", "EMERGENCY_HOLDING"]:
                total_penalties += self.config.penalty_tier_mismatch
                reasons.append(
                    f"Acuity mismatch: Triage demands {rec_care_level} but candidate allocates {care_level}"
                )
            elif rec_care_level != care_level and care_level == "EMERGENCY_HOLDING":
                mismatch_p = self.config.penalty_tier_mismatch * 0.5
                total_penalties += mismatch_p
                reasons.append(f"Contingency holding bay placement penalty ({mismatch_p:.3f})")

        # -------------------------------------------------------------
        # Soft Penalties: Transfer Delay
        # -------------------------------------------------------------
        transfer_delay = candidate.get("transfer_delay_minutes")
        if transfer_delay is not None:
            try:
                mins = max(0.0, float(transfer_delay))
                p_trans = min(
                    self.config.penalty_transfer_delay * 2,
                    (mins / 60.0) * self.config.penalty_transfer_delay
                )
                total_penalties += p_trans
                reasons.append(f"Transfer delay of {mins:.1f} mins penalty ({p_trans:.3f})")
            except (ValueError, TypeError):
                pass
        elif candidate.get("target_department_id") and bed.get("recommended_department_id"):
            # Department mismatch suggests inter-unit transfer delay
            if candidate["target_department_id"] != bed["recommended_department_id"]:
                p_inter = self.config.penalty_transfer_delay * 0.5
                total_penalties += p_inter
                reasons.append(f"Inter-departmental transfer delay penalty ({p_inter:.3f})")

        return (total_penalties, reasons, hard_pass)
