"""Public controlled simulation tool interface."""

from dataclasses import dataclass

from bottleneck_analyzer.simulation.config import SimulationConfig
from bottleneck_analyzer.simulation.environment import Line
from bottleneck_analyzer.simulation.events import Fault, StateInterval
from bottleneck_analyzer.simulation.metrics import candidates, summarize
from bottleneck_analyzer.simulation.vehicle import Vehicle


@dataclass
class SimulationResult:
    config: SimulationConfig
    metrics: dict
    vehicles: list[Vehicle]
    faults: list[Fault]
    states: list[StateInterval]


def run_simulation(config: SimulationConfig) -> SimulationResult:
    line = Line(config)
    line.run()
    metrics = summarize(line)
    metrics["constraints"] = candidates(metrics)
    return SimulationResult(config, metrics, line.vehicles, line.faults, line.states.intervals)
