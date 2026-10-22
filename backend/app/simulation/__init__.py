"""
Surge Simulation Package.

Exports the SurgeSimulationRunner and SurgeScenarioConfig for hospital load stress-testing,
capacity bottleneck identification, and multi-agent coordination benchmarking.
"""

from app.simulation.surge_runner import (
    SurgeSimulationRunner,
    SurgeScenarioConfig,
    SimulationResult,
)

__all__ = [
    "SurgeSimulationRunner",
    "SurgeScenarioConfig",
    "SimulationResult",
]
