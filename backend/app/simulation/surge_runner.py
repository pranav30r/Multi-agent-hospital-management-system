"""
Surge Simulation Runner for Hospital Capacity Stress-Testing and Multi-Agent Benchmarking.

Models simulated patient arrival spikes (e.g. Mass Casualty, Pandemic Surge, ED Overload),
evaluates deterministic clinical protocol recommendations via ClinicalWorkflowAgent,
tracks virtual bed and staff capacity contention, and reports measurable system outcomes.

CRITICAL SAFETY INVARIANT:
This runner is purely in-memory and non-destructive. It NEVER persists simulated encounters,
mutates production bed states, creates live database tasks, or triggers external clinical orders.
"""

import logging
import random
import time
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.agents.workflow_agent import (
    ClinicalWorkflowAgent,
    PROTOCOL_RESUSCITATION,
    PROTOCOL_CARDIAC,
    PROTOCOL_RESPIRATORY,
    PROTOCOL_SEPSIS,
    PROTOCOL_OUTPATIENT,
    PROTOCOL_GENERAL,
)
from app.utils.datetime_utils import utc_now_iso

logger = logging.getLogger(__name__)

VALID_ARRIVAL_PATTERNS = {"UNIFORM", "BATCH_BURST", "RAMP_UP"}
VALID_ACUITY_PROFILES = {"STANDARD", "MASS_CASUALTY", "HIGH_ACUITY", "LOW_ACUITY"}


class SurgeScenarioConfig(BaseModel):
    """Configuration schema for a surge simulation benchmark scenario."""
    scenario_name: str = "DEFAULT_SURGE"
    arrival_count: int = Field(default=20, ge=1, le=500)
    arrival_pattern: str = "BATCH_BURST"
    acuity_profile: str = "MASS_CASUALTY"
    
    # Virtual Resource Capacities
    initial_er_capacity: int = Field(default=6, ge=0)
    initial_icu_capacity: int = Field(default=2, ge=0)
    initial_ward_capacity: int = Field(default=12, ge=0)
    
    # Virtual Staffing Limits
    doctor_staffing_count: int = Field(default=2, ge=1)
    nurse_staffing_count: int = Field(default=4, ge=1)
    doctor_patient_limit: int = Field(default=4, ge=1)
    nurse_patient_limit: int = Field(default=3, ge=1)
    
    # Simulation Control
    random_seed: Optional[int] = 42
    tenant_id: str = "HOSP-DEFAULT"

    @field_validator("arrival_pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in VALID_ARRIVAL_PATTERNS:
            raise ValueError(f"Invalid arrival_pattern '{v}'. Must be one of {VALID_ARRIVAL_PATTERNS}")
        return v_upper

    @field_validator("acuity_profile")
    @classmethod
    def validate_profile(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in VALID_ACUITY_PROFILES:
            raise ValueError(f"Invalid acuity_profile '{v}'. Must be one of {VALID_ACUITY_PROFILES}")
        return v_upper


class SimulationResult(BaseModel):
    """Structured, measurable output metrics produced by the surge simulation runner."""
    scenario_name: str
    total_arrivals: int
    acuity_distribution: Dict[int, int]
    protocols_triggered: Dict[str, int]
    bed_shortage_events: int
    staff_overload_events: int
    conflicts_detected: Dict[str, int]
    peak_utilization: Dict[str, float]
    human_approval_required_count: int
    average_simulated_wait_time_minutes: float
    duration_seconds: float
    is_simulation: bool = True
    provenance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class SurgeSimulationRunner:
    """
    Executes in-memory discrete-event surge simulations with deterministic clinical workflow evaluation.
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        # ClinicalWorkflowAgent takes db session in BaseAgent constructor, but evaluate is non-destructive
        self.workflow_agent = ClinicalWorkflowAgent(db=db)

    async def run_simulation(self, config: SurgeScenarioConfig) -> SimulationResult:
        """
        Executes a deterministic surge simulation based on the scenario configuration.
        Tracks virtual resource contention and protocol evaluations with zero production mutations.
        """
        start_time = time.perf_counter()
        rng = random.Random(config.random_seed)

        # 1. Initialize Virtual Resource Pools
        er_occupied = 0
        icu_occupied = 0
        ward_occupied = 0
        
        peak_er = 0
        peak_icu = 0
        peak_ward = 0

        active_patient_load = 0
        max_doctor_capacity = config.doctor_staffing_count * config.doctor_patient_limit
        max_nurse_capacity = config.nurse_staffing_count * config.nurse_patient_limit

        # 2. Initialize Telemetry Metric Counters
        acuity_distribution: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        protocols_triggered: Dict[str, int] = {
            PROTOCOL_RESUSCITATION: 0,
            PROTOCOL_CARDIAC: 0,
            PROTOCOL_RESPIRATORY: 0,
            PROTOCOL_SEPSIS: 0,
            PROTOCOL_OUTPATIENT: 0,
            PROTOCOL_GENERAL: 0,
        }
        conflicts_detected: Dict[str, int] = {
            "BED_CAPACITY_CONFLICT": 0,
            "STAFF_SHORTAGE_CONFLICT": 0,
            "EMERGENCY_RESOURCE_MISMATCH": 0,
        }
        bed_shortage_events = 0
        staff_overload_events = 0
        human_approval_required_count = 0
        total_simulated_wait_minutes = 0.0

        # 3. Generate and Process Simulated Arrivals
        arrivals = self._generate_simulated_arrivals(config, rng)

        for arrival_idx, (patient, encounter, triage_out) in enumerate(arrivals):
            esi = encounter.esi_level or 3
            acuity_distribution[esi] = acuity_distribution.get(esi, 0) + 1

            # A. Evaluate deterministic clinical protocol recommendation
            rec = await self.workflow_agent.evaluate(
                triage_output=triage_out,
                encounter=encounter,
                patient=patient,
                tenant_id=config.tenant_id
            )

            primary_protocol = rec.get("protocol", PROTOCOL_GENERAL)
            protocols_triggered[primary_protocol] = protocols_triggered.get(primary_protocol, 0) + 1
            for p in rec.get("selected_protocols", []):
                if p != primary_protocol and p in protocols_triggered:
                    protocols_triggered[p] += 1

            if rec.get("requires_human_review", True):
                human_approval_required_count += 1

            # B. Simulate Virtual Bed Allocation and Contention
            care_level = triage_out.get("recommended_care_level", "GENERAL")
            if esi == 1 or care_level == "ICU":
                if icu_occupied < config.initial_icu_capacity:
                    icu_occupied += 1
                else:
                    bed_shortage_events += 1
                    conflicts_detected["BED_CAPACITY_CONFLICT"] += 1
                    # Attempt ER overflow if available
                    if er_occupied < config.initial_er_capacity:
                        er_occupied += 1
                        conflicts_detected["EMERGENCY_RESOURCE_MISMATCH"] += 1
            elif esi == 2 or care_level == "EMERGENCY":
                if er_occupied < config.initial_er_capacity:
                    er_occupied += 1
                else:
                    bed_shortage_events += 1
                    conflicts_detected["BED_CAPACITY_CONFLICT"] += 1
            else:
                if ward_occupied < config.initial_ward_capacity:
                    ward_occupied += 1
                else:
                    # Ward full; minor queue backlog
                    bed_shortage_events += 1

            # Update peak occupancies
            peak_er = max(peak_er, er_occupied)
            peak_icu = max(peak_icu, icu_occupied)
            peak_ward = max(peak_ward, ward_occupied)

            # C. Simulate Virtual Staffing Load & Shortages
            active_patient_load += 1
            if active_patient_load > max_doctor_capacity or active_patient_load > max_nurse_capacity:
                staff_overload_events += 1
                conflicts_detected["STAFF_SHORTAGE_CONFLICT"] += 1

            # D. Estimate Simulated Wait Time (based on clinical priority and resource bottlenecks)
            base_wait = {1: 0.0, 2: 10.0, 3: 45.0, 4: 90.0, 5: 120.0}.get(esi, 30.0)
            if er_occupied >= config.initial_er_capacity and config.initial_er_capacity > 0:
                base_wait += 25.0
            if icu_occupied >= config.initial_icu_capacity and config.initial_icu_capacity > 0 and esi in [1, 2]:
                base_wait += 40.0
            if active_patient_load > max_doctor_capacity:
                base_wait += 20.0
            total_simulated_wait_minutes += base_wait

            # Simulate occasional discharge/transfer every few patients to model dynamic patient flow
            if arrival_idx % 3 == 0:
                if ward_occupied > 0:
                    ward_occupied -= 1
                if er_occupied > 0 and arrival_idx % 2 == 0:
                    er_occupied -= 1
                if active_patient_load > 1:
                    active_patient_load -= 1

        # 4. Compute Final Derived Metrics
        avg_wait = round(total_simulated_wait_minutes / max(1, config.arrival_count), 1)
        peak_utilization = {
            "ER": round((peak_er / max(1, config.initial_er_capacity)) * 100, 1),
            "ICU": round((peak_icu / max(1, config.initial_icu_capacity)) * 100, 1),
            "WARD": round((peak_ward / max(1, config.initial_ward_capacity)) * 100, 1),
        }

        elapsed_sec = round(time.perf_counter() - start_time, 4)

        provenance = {
            "runner": "SurgeSimulationRunner_v1",
            "scenario_name": config.scenario_name,
            "arrival_pattern": config.arrival_pattern,
            "acuity_profile": config.acuity_profile,
            "random_seed": config.random_seed,
            "timestamp": utc_now_iso(),
            "disclaimer": "Simulated operational workload — Zero live database or physical clinical side effects."
        }

        return SimulationResult(
            scenario_name=config.scenario_name,
            total_arrivals=config.arrival_count,
            acuity_distribution=acuity_distribution,
            protocols_triggered=protocols_triggered,
            bed_shortage_events=bed_shortage_events,
            staff_overload_events=staff_overload_events,
            conflicts_detected=conflicts_detected,
            peak_utilization=peak_utilization,
            human_approval_required_count=human_approval_required_count,
            average_simulated_wait_time_minutes=avg_wait,
            duration_seconds=elapsed_sec,
            is_simulation=True,
            provenance=provenance
        )

    # ─── Synthetic Patient Arrival Generation ─────────────────────────────────

    def _generate_simulated_arrivals(
        self,
        config: SurgeScenarioConfig,
        rng: random.Random
    ) -> List[tuple[Patient, Encounter, Dict[str, Any]]]:
        """
        Deterministically constructs in-memory synthetic Patient and Encounter objects
        matching the configured acuity profile and arrival distribution weights.
        """
        arrivals: List[tuple[Patient, Encounter, Dict[str, Any]]] = []

        # Acuity Profile Weights: [ESI-1, ESI-2, ESI-3, ESI-4, ESI-5]
        profile_weights = {
            "STANDARD": [5, 20, 45, 20, 10],
            "MASS_CASUALTY": [30, 45, 20, 5, 0],
            "HIGH_ACUITY": [15, 45, 30, 10, 0],
            "LOW_ACUITY": [0, 5, 15, 45, 35],
        }.get(config.acuity_profile, [5, 20, 45, 20, 10])

        esi_choices = [1, 2, 3, 4, 5]

        for i in range(config.arrival_count):
            esi = rng.choices(esi_choices, weights=profile_weights, k=1)[0]
            patient, encounter, triage_out = self._create_synthetic_case(i + 1, esi, config.tenant_id, rng)
            arrivals.append((patient, encounter, triage_out))

        return arrivals

    def _create_synthetic_case(
        self,
        case_id: int,
        esi: int,
        tenant_id: str,
        rng: random.Random
    ) -> tuple[Patient, Encounter, Dict[str, Any]]:
        """Constructs clinically coherent synthetic case based on ESI tier."""
        pat_id = f"SIM-PAT-{case_id:04d}"
        enc_id = f"SIM-ENC-{case_id:04d}"
        age = rng.randint(18, 85)
        gender = rng.choice(["M", "F"])

        if esi == 1:
            chief_complaint = rng.choice([
                "Unresponsive, profound shock, cardiac arrest resuscitation in progress",
                "Severe respiratory arrest, cyanosis, gasping respirations",
                "Massive trauma, hemorrhagic shock, hypotension"
            ])
            hr = rng.randint(130, 160)
            bp_sys = rng.randint(55, 75)
            bp_dia = rng.randint(30, 45)
            spo2 = rng.randint(72, 82)
            rr = rng.randint(6, 10)
            temp = 96.2
            pain = None
            gcs = rng.randint(3, 7)
            severity = "CRITICAL"
            care_level = "ICU"
            red_flags = [{"code": "RF-SHOCK", "description": "Severe shock / arrest"}]

        elif esi == 2:
            case_type = rng.choice(["CARDIAC", "RESPIRATORY", "SEPSIS"])
            if case_type == "CARDIAC":
                chief_complaint = "Severe substernal crushing chest pain radiating to left arm and jaw"
                hr = rng.randint(100, 125)
                bp_sys = rng.randint(150, 180)
                bp_dia = rng.randint(95, 110)
                spo2 = rng.randint(94, 97)
                rr = rng.randint(20, 24)
                temp = 98.6
                pain = rng.randint(8, 10)
                gcs = 15
                red_flags = [{"code": "RF-CHEST-PAIN", "description": "Acute chest pain"}]
            elif case_type == "RESPIRATORY":
                chief_complaint = "Severe shortness of breath, acute asthma exacerbation with wheezing"
                hr = rng.randint(110, 130)
                bp_sys = rng.randint(130, 155)
                bp_dia = rng.randint(80, 95)
                spo2 = rng.randint(85, 90)
                rr = rng.randint(28, 34)
                temp = 98.4
                pain = 4
                gcs = 15
                red_flags = [{"code": "RF-HYPOXIA", "description": "Arterial hypoxia"}]
            else:
                chief_complaint = "High fever, chills, purulent productive cough, suspected sepsis"
                hr = rng.randint(110, 125)
                bp_sys = rng.randint(85, 95)
                bp_dia = rng.randint(50, 60)
                spo2 = rng.randint(92, 95)
                rr = rng.randint(22, 26)
                temp = round(rng.uniform(101.5, 103.5), 1)
                pain = 5
                gcs = 14
                red_flags = [{"code": "RF-SEPSIS", "description": "Suspected systemic sepsis"}]

            severity = "HIGH"
            care_level = "EMERGENCY"

        elif esi == 3:
            chief_complaint = rng.choice([
                "Moderate abdominal pain and nausea for 2 days",
                "High fever and urinary tract infection symptoms",
                "Deep laceration to forearm requiring surgical repair"
            ])
            hr = rng.randint(85, 105)
            bp_sys = rng.randint(120, 145)
            bp_dia = rng.randint(75, 90)
            spo2 = rng.randint(96, 99)
            rr = rng.randint(16, 20)
            temp = round(rng.uniform(99.0, 101.0), 1)
            pain = rng.randint(4, 7)
            gcs = 15
            severity = "MODERATE"
            care_level = "GENERAL"
            red_flags = []

        elif esi == 4:
            chief_complaint = rng.choice([
                "Ankle inversion sprain, able to bear weight with pain",
                "Superficial hand laceration with controlled bleeding",
                "Mild pharyngitis and sore throat for 24 hours"
            ])
            hr = rng.randint(70, 85)
            bp_sys = rng.randint(115, 130)
            bp_dia = rng.randint(70, 82)
            spo2 = 98
            rr = 16
            temp = 98.6
            pain = rng.randint(2, 4)
            gcs = 15
            severity = "LOW"
            care_level = "GENERAL"
            red_flags = []

        else:  # ESI 5
            chief_complaint = rng.choice([
                "Suture removal and surgical wound check",
                "Routine chronic medication refill consultation",
                "Minor superficial abrasion after minor fall"
            ])
            hr = rng.randint(65, 80)
            bp_sys = rng.randint(110, 125)
            bp_dia = rng.randint(70, 80)
            spo2 = 99
            rr = 14
            temp = 98.4
            pain = rng.randint(0, 1)
            gcs = 15
            severity = "LOW"
            care_level = "OUTPATIENT"
            red_flags = []

        patient = Patient(
            id=pat_id,
            tenant_id=tenant_id,
            first_name=f"SimulatedPat{case_id}",
            last_name="SurgeCase",
            age=age,
            gender=gender,
            blood_group="O+",
            contact_phone="555-0100",
            emergency_contact="555-0101",
            allergies=["Penicillin"] if esi in [1, 2] else []
        )

        encounter = Encounter(
            id=enc_id,
            patient_id=pat_id,
            current_department_id="DEP-ER",
            encounter_type="EMERGENCY",
            status="ACTIVE",
            patient_status="ARRIVED",
            chief_complaint=chief_complaint,
            heart_rate=hr,
            bp_systolic=bp_sys,
            bp_diastolic=bp_dia,
            spo2=spo2,
            temperature_f=temp,
            respiratory_rate=rr,
            pain_level=pain,
            gcs_score=gcs,
            esi_level=esi
        )

        triage_out = {
            "esi_level": esi,
            "severity": severity,
            "recommended_care_level": care_level,
            "red_flags": red_flags,
            "requires_telemetry": esi in [1, 2],
            "requires_isolation": False
        }

        return patient, encounter, triage_out
