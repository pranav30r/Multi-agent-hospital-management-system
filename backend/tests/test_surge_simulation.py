"""
Comprehensive Unit and Regression Test Suite for Surge Simulation Runner.

Verifies:
1. Module exports and configuration schema validation (SurgeScenarioConfig, SurgeSimulationRunner, SimulationResult).
2. Baseline normal load scenario execution and metric collection.
3. High-acuity / Mass Casualty surge load execution with protocol escalation.
4. Virtual capacity bottlenecks: bed shortages, staff overloads, and conflict detection.
5. Deterministic reproducibility across identical seeds.
6. Strict side-effect isolation: zero database mutations to patients, encounters, beds, or tasks.
7. CLI interface execution and JSON metric export.
"""

import json
import pytest
import subprocess
import sys
from pathlib import Path
from sqlalchemy import select, func

from app.simulation import (
    SurgeSimulationRunner,
    SurgeScenarioConfig,
    SimulationResult,
)
from app.simulation.surge_runner import (
    VALID_ARRIVAL_PATTERNS,
    VALID_ACUITY_PROFILES,
)
from app.agents.workflow_agent import (
    PROTOCOL_RESUSCITATION,
    PROTOCOL_CARDIAC,
    PROTOCOL_RESPIRATORY,
    PROTOCOL_SEPSIS,
    PROTOCOL_OUTPATIENT,
    PROTOCOL_GENERAL,
)
from app.models.patient import Patient, Encounter
from app.models.bed import Bed
from app.models.workflow import Task


# ─── 1. Package Exports and Configuration Validation ─────────────────────────

def test_simulation_package_exports():
    """Verify primary simulation classes are cleanly exported."""
    import app.simulation as sim_pkg
    assert hasattr(sim_pkg, "SurgeSimulationRunner")
    assert hasattr(sim_pkg, "SurgeScenarioConfig")
    assert hasattr(sim_pkg, "SimulationResult")
    assert "SurgeSimulationRunner" in sim_pkg.__all__
    assert "SurgeScenarioConfig" in sim_pkg.__all__
    assert "SimulationResult" in sim_pkg.__all__


def test_scenario_config_defaults_and_validation():
    """Verify default values and bounds validation for scenario configuration."""
    cfg = SurgeScenarioConfig()
    assert cfg.arrival_count == 20
    assert cfg.arrival_pattern == "BATCH_BURST"
    assert cfg.acuity_profile == "MASS_CASUALTY"
    assert cfg.initial_er_capacity == 6
    assert cfg.initial_icu_capacity == 2
    assert cfg.initial_ward_capacity == 12
    assert cfg.random_seed == 42


def test_scenario_config_invalid_inputs():
    """Verify that invalid inputs raise descriptive validation errors."""
    # Invalid arrival count: 0
    with pytest.raises(ValueError):
        SurgeScenarioConfig(arrival_count=0)

    # Invalid arrival count: > 500
    with pytest.raises(ValueError):
        SurgeScenarioConfig(arrival_count=501)

    # Invalid pattern
    with pytest.raises(ValueError, match="Invalid arrival_pattern"):
        SurgeScenarioConfig(arrival_pattern="EXPONENTIAL_CHAOS")

    # Invalid acuity profile
    with pytest.raises(ValueError, match="Invalid acuity_profile"):
        SurgeScenarioConfig(acuity_profile="SUPER_CRITICAL")


# ─── 2. Normal Load Baseline Scenario ────────────────────────────────────────

@pytest.mark.asyncio
async def test_normal_load_simulation():
    """Verify normal load scenario produces consistent metrics and complete protocol mappings."""
    runner = SurgeSimulationRunner(db=None)
    config = SurgeScenarioConfig(
        scenario_name="TEST_NORMAL_LOAD",
        arrival_count=15,
        arrival_pattern="UNIFORM",
        acuity_profile="STANDARD",
        initial_er_capacity=10,
        initial_icu_capacity=5,
        initial_ward_capacity=20,
        doctor_staffing_count=4,
        nurse_staffing_count=8,
        random_seed=101
    )

    result = await runner.run_simulation(config)

    assert isinstance(result, SimulationResult)
    assert result.scenario_name == "TEST_NORMAL_LOAD"
    assert result.total_arrivals == 15
    assert sum(result.acuity_distribution.values()) == 15

    # Check that all ESI tiers 1 to 5 are represented in distribution map
    for esi in [1, 2, 3, 4, 5]:
        assert esi in result.acuity_distribution

    # Telemetry and provenance checks
    assert result.is_simulation is True
    assert result.provenance["runner"] == "SurgeSimulationRunner_v1"
    assert result.provenance["scenario_name"] == "TEST_NORMAL_LOAD"
    assert result.provenance["random_seed"] == 101
    assert result.duration_seconds >= 0.0
    assert result.average_simulated_wait_time_minutes > 0.0


# ─── 3. Mass Casualty Surge Load & Protocol Escalation ───────────────────────

@pytest.mark.asyncio
async def test_mass_casualty_surge_scenario():
    """Verify Mass Casualty profile generates high-acuity caseload and triggers critical protocols."""
    runner = SurgeSimulationRunner(db=None)
    config = SurgeScenarioConfig(
        scenario_name="TEST_MASS_CASUALTY",
        arrival_count=30,
        arrival_pattern="BATCH_BURST",
        acuity_profile="MASS_CASUALTY",
        initial_er_capacity=8,
        initial_icu_capacity=3,
        initial_ward_capacity=15,
        doctor_staffing_count=2,
        nurse_staffing_count=4,
        random_seed=42
    )

    result = await runner.run_simulation(config)

    # In mass casualty, ESI 1 and 2 should dominate
    high_acuity_count = result.acuity_distribution[1] + result.acuity_distribution[2]
    assert high_acuity_count > (result.total_arrivals * 0.5), "Mass casualty should yield >50% high-acuity cases"

    # Critical protocols must have been triggered
    assert (
        result.protocols_triggered[PROTOCOL_RESUSCITATION] > 0
        or result.protocols_triggered[PROTOCOL_CARDIAC] > 0
    )

    # High acuity requires physician review
    assert result.human_approval_required_count >= high_acuity_count


# ─── 4. Virtual Capacity Constraints & Contention ────────────────────────────

@pytest.mark.asyncio
async def test_capacity_bottleneck_and_resource_contention():
    """Verify that constrained virtual beds and staff yield measurable contention events."""
    runner = SurgeSimulationRunner(db=None)
    
    # Highly constrained environment
    choked_config = SurgeScenarioConfig(
        scenario_name="TEST_CHOKED_CAPACITY",
        arrival_count=25,
        arrival_pattern="BATCH_BURST",
        acuity_profile="MASS_CASUALTY",
        initial_er_capacity=2,
        initial_icu_capacity=1,
        initial_ward_capacity=3,
        doctor_staffing_count=1,
        nurse_staffing_count=1,
        doctor_patient_limit=2,
        nurse_patient_limit=2,
        random_seed=42
    )

    result = await runner.run_simulation(choked_config)

    # Under 25 arrivals with 1 ICU bed and 2 ER beds, bed shortages MUST occur
    assert result.bed_shortage_events > 0, "Constrained scenario should log bed shortage events"
    assert result.conflicts_detected["BED_CAPACITY_CONFLICT"] > 0
    assert result.conflicts_detected["STAFF_SHORTAGE_CONFLICT"] > 0
    assert result.peak_utilization["ICU"] >= 100.0
    assert result.peak_utilization["ER"] >= 100.0


@pytest.mark.asyncio
async def test_unconstrained_vs_constrained_wait_times():
    """Verify average wait time is strictly longer under constrained capacity than unconstrained."""
    runner = SurgeSimulationRunner(db=None)

    # 1. Unconstrained
    unconstrained_cfg = SurgeScenarioConfig(
        arrival_count=20,
        acuity_profile="STANDARD",
        initial_er_capacity=50,
        initial_icu_capacity=20,
        initial_ward_capacity=50,
        doctor_staffing_count=10,
        nurse_staffing_count=20,
        random_seed=77
    )
    unconstrained_res = await runner.run_simulation(unconstrained_cfg)

    # 2. Severely Constrained
    constrained_cfg = SurgeScenarioConfig(
        arrival_count=20,
        acuity_profile="STANDARD",
        initial_er_capacity=1,
        initial_icu_capacity=1,
        initial_ward_capacity=2,
        doctor_staffing_count=1,
        nurse_staffing_count=1,
        random_seed=77
    )
    constrained_res = await runner.run_simulation(constrained_cfg)

    assert constrained_res.average_simulated_wait_time_minutes > unconstrained_res.average_simulated_wait_time_minutes
    assert constrained_res.bed_shortage_events > unconstrained_res.bed_shortage_events


# ─── 5. Acuity Profile Comparison ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_low_acuity_vs_high_acuity_profiles():
    """Verify LOW_ACUITY profile shifts cases away from ICU/Resuscitation toward Outpatient/General."""
    runner = SurgeSimulationRunner(db=None)

    low_cfg = SurgeScenarioConfig(
        arrival_count=25,
        acuity_profile="LOW_ACUITY",
        random_seed=55
    )
    low_res = await runner.run_simulation(low_cfg)

    high_cfg = SurgeScenarioConfig(
        arrival_count=25,
        acuity_profile="HIGH_ACUITY",
        random_seed=55
    )
    high_res = await runner.run_simulation(high_cfg)

    # Low acuity should have 0 or near 0 ESI 1
    assert low_res.acuity_distribution[1] == 0
    assert low_res.acuity_distribution[4] + low_res.acuity_distribution[5] > 15

    # High acuity should have significant ESI 1 and 2
    assert high_res.acuity_distribution[1] + high_res.acuity_distribution[2] > 10

    # Low acuity outpatient / general protocols should exceed resuscitation
    assert low_res.protocols_triggered[PROTOCOL_RESUSCITATION] == 0
    assert (
        low_res.protocols_triggered[PROTOCOL_OUTPATIENT]
        + low_res.protocols_triggered[PROTOCOL_GENERAL]
        > high_res.protocols_triggered[PROTOCOL_OUTPATIENT]
    )


# ─── 6. Deterministic Reproducibility ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_deterministic_reproducibility():
    """Verify two runs with identical seeds produce bit-identical simulation results."""
    runner = SurgeSimulationRunner(db=None)
    config = SurgeScenarioConfig(
        scenario_name="TEST_REPRODUCIBILITY",
        arrival_count=35,
        arrival_pattern="RAMP_UP",
        acuity_profile="MASS_CASUALTY",
        random_seed=2024
    )

    run_1 = await runner.run_simulation(config)
    run_2 = await runner.run_simulation(config)

    assert run_1.total_arrivals == run_2.total_arrivals
    assert run_1.acuity_distribution == run_2.acuity_distribution
    assert run_1.protocols_triggered == run_2.protocols_triggered
    assert run_1.bed_shortage_events == run_2.bed_shortage_events
    assert run_1.staff_overload_events == run_2.staff_overload_events
    assert run_1.conflicts_detected == run_2.conflicts_detected
    assert run_1.peak_utilization == run_2.peak_utilization
    assert run_1.human_approval_required_count == run_2.human_approval_required_count
    assert run_1.average_simulated_wait_time_minutes == run_2.average_simulated_wait_time_minutes


# ─── 7. Side-Effect Isolation (Zero Database Mutations) ──────────────────────

@pytest.mark.asyncio
async def test_side_effect_isolation_zero_db_mutations(test_db):
    """
    MANDATORY SAFETY INVARIANT TEST:
    Verifies that running a simulation with an active database session NEVER persists
    simulated encounters, mutates beds, creates tasks, or modifies real patients.
    """
    async with test_db() as session:
        # Snapshot record counts before simulation
        pats_before = (await session.execute(select(func.count(Patient.id)))).scalar_one()
        encs_before = (await session.execute(select(func.count(Encounter.id)))).scalar_one()
        beds_before = (await session.execute(select(func.count(Bed.id)))).scalar_one()
        tasks_before = (await session.execute(select(func.count(Task.id)))).scalar_one()

        # Execute heavy surge simulation passing the session
        runner = SurgeSimulationRunner(db=session)
        config = SurgeScenarioConfig(
            scenario_name="SAFETY_ISOLATION_TEST",
            arrival_count=40,
            arrival_pattern="BATCH_BURST",
            acuity_profile="MASS_CASUALTY",
            initial_er_capacity=2,
            initial_icu_capacity=1,
            initial_ward_capacity=5,
            random_seed=999
        )
        result = await runner.run_simulation(config)

        assert result.total_arrivals == 40
        assert result.bed_shortage_events > 0

        # Snapshot record counts after simulation
        pats_after = (await session.execute(select(func.count(Patient.id)))).scalar_one()
        encs_after = (await session.execute(select(func.count(Encounter.id)))).scalar_one()
        beds_after = (await session.execute(select(func.count(Bed.id)))).scalar_one()
        tasks_after = (await session.execute(select(func.count(Task.id)))).scalar_one()

        # Strict equality assertion: ZERO database state mutations
        assert pats_after == pats_before, f"Patients mutated: before={pats_before}, after={pats_after}"
        assert encs_after == encs_before, f"Encounters mutated: before={encs_before}, after={encs_after}"
        assert beds_after == beds_before, f"Beds mutated: before={beds_before}, after={beds_after}"
        assert tasks_after == tasks_before, f"Tasks mutated: before={tasks_before}, after={tasks_after}"


# ─── 8. CLI Interface Execution & Output Verification ─────────────────────────

def test_cli_runner_script_execution(tmp_path):
    """Verify that backend/scripts/simulate_surge.py runs cleanly via subprocess."""
    cli_path = Path(__file__).resolve().parent.parent / "scripts" / "simulate_surge.py"
    assert cli_path.exists(), f"CLI runner script missing at {cli_path}"

    json_out = tmp_path / "surge_metrics.json"

    cmd = [
        sys.executable,
        str(cli_path),
        "--arrivals", "8",
        "--pattern", "UNIFORM",
        "--profile", "MASS_CASUALTY",
        "--seed", "42",
        "--output-json", str(json_out)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "HOSPITAL MULTI-AGENT INTELLIGENCE — SURGE SIMULATION RUNNER" in result.stdout
    assert "Simulation Complete" in result.stdout
    assert json_out.exists(), "Output JSON file was not generated"

    with open(json_out, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["total_arrivals"] == 8
    assert data["is_simulation"] is True
    assert data["provenance"]["random_seed"] == 42
    assert "conflicts_detected" in data
