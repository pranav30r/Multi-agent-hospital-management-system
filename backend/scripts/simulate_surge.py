"""
CLI Surge Simulation Runner Script.

Executes automated hospital surge stress-testing, capacity bottleneck evaluation,
and multi-agent intelligence performance benchmarking.

Usage:
    python backend/scripts/simulate_surge.py --arrivals 25 --profile MASS_CASUALTY --seed 42
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.simulation import SurgeSimulationRunner, SurgeScenarioConfig


async def main():
    parser = argparse.ArgumentParser(description="Hospital Intelligence Multi-Agent Surge Simulation Runner")
    parser.add_argument("--arrivals", type=int, default=20, help="Number of simulated patient arrivals (1-500)")
    parser.add_argument("--pattern", type=str, default="BATCH_BURST", choices=["UNIFORM", "BATCH_BURST", "RAMP_UP"], help="Arrival pattern")
    parser.add_argument("--profile", type=str, default="MASS_CASUALTY", choices=["STANDARD", "MASS_CASUALTY", "HIGH_ACUITY", "LOW_ACUITY"], help="Acuity profile")
    parser.add_argument("--er-capacity", type=int, default=6, help="Virtual initial ER bed capacity")
    parser.add_argument("--icu-capacity", type=int, default=2, help="Virtual initial ICU bed capacity")
    parser.add_argument("--ward-capacity", type=int, default=12, help="Virtual initial Ward bed capacity")
    parser.add_argument("--doctors", type=int, default=2, help="Virtual doctors on duty")
    parser.add_argument("--nurses", type=int, default=4, help="Virtual nurses on duty")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic reproducibility")
    parser.add_argument("--tenant-id", type=str, default="HOSP-DEFAULT", help="Target tenant identifier")
    parser.add_argument("--output-json", type=str, default=None, help="Optional file path to export JSON metrics")

    args = parser.parse_args()

    config = SurgeScenarioConfig(
        scenario_name=f"SURGE_{args.profile}_{args.pattern}",
        arrival_count=args.arrivals,
        arrival_pattern=args.pattern,
        acuity_profile=args.profile,
        initial_er_capacity=args.er_capacity,
        initial_icu_capacity=args.icu_capacity,
        initial_ward_capacity=args.ward_capacity,
        doctor_staffing_count=args.doctors,
        nurse_staffing_count=args.nurses,
        random_seed=args.seed,
        tenant_id=args.tenant_id
    )

    print("=" * 70)
    print(" HOSPITAL MULTI-AGENT INTELLIGENCE — SURGE SIMULATION RUNNER")
    print("=" * 70)
    print(f"Scenario Name:     {config.scenario_name}")
    print(f"Arrivals:          {config.arrival_count} ({config.arrival_pattern})")
    print(f"Acuity Profile:    {config.acuity_profile}")
    print(f"Virtual Beds:      ER={config.initial_er_capacity}, ICU={config.initial_icu_capacity}, Ward={config.initial_ward_capacity}")
    print(f"Virtual Staff:     Doctors={config.doctor_staffing_count}, Nurses={config.nurse_staffing_count}")
    print(f"Deterministic Seed:{config.random_seed}")
    print("-" * 70)

    runner = SurgeSimulationRunner(db=None)
    result = await runner.run_simulation(config)

    print(f"\n[Simulation Complete in {result.duration_seconds}s]")
    print(f"Acuity Distribution:  {result.acuity_distribution}")
    print(f"Bed Shortage Events:  {result.bed_shortage_events}")
    print(f"Staff Overload Events:{result.staff_overload_events}")
    print(f"Conflicts Detected:   {result.conflicts_detected}")
    print(f"Peak Bed Utilization: {result.peak_utilization}")
    print(f"Human Reviews Needed: {result.human_approval_required_count} / {result.total_arrivals}")
    print(f"Average Wait Time:    {result.average_simulated_wait_time_minutes} minutes")
    print("\nClinical Protocols Triggered:")
    for proto, count in result.protocols_triggered.items():
        if count > 0:
            print(f"  - {proto}: {count}")

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"\nSaved JSON metrics to: {out_path}")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
