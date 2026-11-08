"""Agent 4: validate scenario and invoke Stage 3 in a killable bounded worker."""

import multiprocessing
from multiprocessing.connection import Connection

from bottleneck_analyzer.agents.contracts import SimulationInput, SimulationOutput
from bottleneck_analyzer.core.config import AppSettings
from bottleneck_analyzer.simulation.config import Intervention, updated
from bottleneck_analyzer.simulation.scenarios import assess_comparison, compare


def execute(request: SimulationInput) -> SimulationOutput:
    """Pure worker: no engine, database writes, provider keys or generated code."""
    scenario = request.scenario
    intervention = Intervention(
        station=scenario.request.target_station,
        category=scenario.request.fault_category,
        method=scenario.request.method,
        reduction_percentage=scenario.request.reduction_percentage,
    )
    config = updated(
        request.config, days=scenario.days or request.config.days, record_history=False
    )
    # Validation resolves category/equipment against the seven-station configuration.
    updated(config, intervention=intervention)
    seeds = list(range(scenario.seed_start, scenario.seed_start + scenario.replications))
    comparison = compare(config, intervention, seeds)
    sensitivity_seeds = list(
        range(
            scenario.sensitivity_seed_start,
            scenario.sensitivity_seed_start + scenario.sensitivity_replications,
        )
    )
    assessment = assess_comparison(
        comparison, sensitivity_seeds, days=min(scenario.sensitivity_days, config.days)
    )
    return SimulationOutput(
        baseline=comparison["baseline"],
        scenario=comparison["scenario"],
        paired_gain=comparison["paired_gain"],
        comparison=comparison,
        constraint_assessment=assessment,
        seeds=seeds,
        configuration_version=config.version,
        days=config.days,
        limitations=[
            "Synthetic model predictions; not measured plant outcomes or approved changes.",
            "Intervals cover seed variation, not structural model error.",
            assessment["qualification"],
            "Realized downtime reduction need not equal the requested parameter reduction.",
        ],
    )


def worker(send: Connection, request: SimulationInput) -> None:
    try:
        send.send((True, execute(request).model_dump(mode="json")))
    except Exception:
        send.send((False, "Simulation execution failed"))
    finally:
        send.close()


class SimulationAgent:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    def run(self, request: SimulationInput) -> SimulationOutput:
        request = SimulationInput.model_validate(request.model_dump())
        scenario = request.scenario
        if scenario.request.fault_category != "robot_fault":
            raise ValueError("Stage 6 interventions target robot faults only")
        days = scenario.days or request.config.days
        if (
            days > self.settings.simulation_max_days
            or scenario.replications > self.settings.simulation_max_replications
            or scenario.sensitivity_replications > self.settings.simulation_max_replications
            or scenario.sensitivity_days > self.settings.simulation_max_days
        ):
            raise ValueError("Simulation exceeds configured scope or replication limits")
        if scenario.request.baseline_version not in (None, request.config.version):
            raise ValueError("Scenario baseline version does not match")
        target = Intervention(
            station=scenario.request.target_station,
            category=scenario.request.fault_category,
            method=scenario.request.method,
            reduction_percentage=scenario.request.reduction_percentage,
        )
        if request.config.intervention is not None:
            raise ValueError("Baseline already contains an intervention")
        updated(request.config, intervention=target)
        ctx = multiprocessing.get_context("spawn")
        receive, send = ctx.Pipe(duplex=False)
        process = ctx.Process(target=worker, args=(send, request), daemon=True)
        try:
            process.start()
            send.close()
            if not receive.poll(self.settings.simulation_timeout_seconds):
                raise TimeoutError("Simulation exceeded its runtime limit")
            try:
                success, payload = receive.recv()
            except EOFError:
                raise RuntimeError("Simulation worker stopped without a result") from None
            if not success:
                raise RuntimeError("Simulation execution failed")
            return SimulationOutput.model_validate(payload)
        finally:
            receive.close()
            send.close()
            if process.pid:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
                process.close()
