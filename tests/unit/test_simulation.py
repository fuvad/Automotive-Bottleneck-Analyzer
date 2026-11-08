"""Small deterministic simulation checks without a database or model service."""

import math
from dataclasses import asdict
from statistics import mean

import pytest
from pydantic import ValidationError

from bottleneck_analyzer.domain.enums import InterventionMethod
from bottleneck_analyzer.domain.manufacturing import STATION_NAMES
from bottleneck_analyzer.simulation.calendars import Calendar
from bottleneck_analyzer.simulation.config import (
    Distribution,
    Failure,
    Intervention,
    ShiftPattern,
    SimulationConfig,
    StationParameters,
    updated,
)
from bottleneck_analyzer.simulation.engine import run_simulation
from bottleneck_analyzer.simulation.failures import sample, stream
from bottleneck_analyzer.simulation.metrics import candidates
from bottleneck_analyzer.simulation.persistence import project_result, validate_simulation_history
from bottleneck_analyzer.simulation.scenarios import compare, sensitivity, statistics
from bottleneck_analyzer.simulation.validation import validate_result


def small_config(**changes) -> SimulationConfig:
    base = SimulationConfig(
        name="simulation-test",
        days=1,
        shifts=(
            ShiftPattern(
                name="shift_1",
                start_seconds=0,
                duration_seconds=600,
                break_start_seconds=300,
                break_seconds=60,
            ),
            ShiftPattern(
                name="shift_2",
                start_seconds=600,
                duration_seconds=600,
                break_start_seconds=300,
                break_seconds=60,
            ),
        ),
        stations=tuple(
            StationParameters(
                name=n,
                processing=Distribution(mean=10, cv=0, minimum=1),
                suv_multiplier=1,
                sedan_multiplier=1,
                failures=(),
            )
            for n in STATION_NAMES
        ),
        release_rate_jph=300,
        buffer_capacities=(1, 1, 1, 1, 1, 1),
        input_capacity=1,
    )
    return updated(base, **changes)


def test_conservation_route_order_final_inspection_and_bounded_wip():
    result = run_simulation(small_config())
    assert validate_result(result)["valid"]
    done = [v for v in result.vehicles if v.completion is not None]
    assert len(done) == result.metrics["completed"]
    assert result.metrics["released"] == len(done) + result.metrics["final_wip"]
    for vehicle in done:
        assert [o.station for o in vehicle.operations] == list(range(7))
        assert vehicle.completion == vehicle.operations[-1].end
        assert all(o.departure >= o.end > o.start >= o.arrival for o in vehicle.operations)
    assert result.metrics["maximum_wip"] <= 14
    assert result.metrics["completed"] < result.metrics["released"]


def test_empty_buffers_starve_and_full_buffers_propagate_blocking():
    config = small_config()
    stations = list(config.stations)
    stations[6] = stations[6].model_copy(
        update={"processing": Distribution(mean=40, cv=0, minimum=1)}
    )
    result = run_simulation(updated(config, stations=tuple(stations)))
    assert validate_result(result)["valid"]
    assert all(s["maximum_input_queue"] <= 1 for s in result.metrics["stations"])
    assert result.metrics["stations"][0]["blocked_seconds"] > 0
    assert result.metrics["stations"][6]["starved_seconds"] > 0
    fast = run_simulation(config)
    assert fast.metrics["completed"] > result.metrics["completed"]


def test_distributions_positive_reproducible_and_model_adjustments():
    distribution = Distribution(mean=60, cv=0.2, minimum=25)
    left = [sample(distribution, stream(7, i)) for i in range(100)]
    right = [sample(distribution, stream(7, i)) for i in range(100)]
    assert left == right
    assert min(left) >= 25
    assert len(set(left)) > 1
    stations = tuple(s.model_copy(update={"suv_multiplier": 2}) for s in small_config().stations)
    suv = run_simulation(small_config(stations=stations, suv_fraction=1))
    sedan = run_simulation(small_config(stations=stations, suv_fraction=0))
    assert suv.metrics["completed"] < sedan.metrics["completed"]


def fault_config() -> SimulationConfig:
    config = small_config()
    stations = list(config.stations)
    stations[0] = stations[0].model_copy(
        update={
            "failures": (Failure(mtbf_seconds=1, repair=Distribution(mean=400, cv=0, minimum=1)),)
        }
    )
    return updated(config, stations=tuple(stations))


def test_failures_suspend_processing_and_repairs_cross_breaks():
    result = run_simulation(fault_config())
    calendar = Calendar(result.config)
    assert validate_result(result)["valid"]
    assert result.faults
    assert any(f.start < 300 < f.end for f in result.faults)
    assert all(math.isclose(f.end - f.start, 400) for f in result.faults if not f.truncated)
    # This deliberately severe failure rate prevents even the first operation
    # finishing; its remaining work must stay in WIP rather than count as output.
    assert result.vehicles[0].operations[0].end is None
    assert result.metrics["completed"] == 0
    faults = result.metrics["stations"][0]["fault_seconds"]
    assert math.isclose(
        faults, sum(calendar.scheduled_between(f.start, f.end) for f in result.faults), abs_tol=1e-5
    )
    assert faults < sum(f.end - f.start for f in result.faults)


def test_repairs_resume_remaining_work_and_do_not_restart_it():
    config = small_config()
    stations = list(config.stations)
    stations[0] = stations[0].model_copy(
        update={
            "failures": (Failure(mtbf_seconds=50, repair=Distribution(mean=25, cv=0, minimum=1)),)
        }
    )
    result = run_simulation(updated(config, stations=tuple(stations)))
    assert result.metrics["stations"][0]["fault_count"] > 0
    assert result.metrics["completed"] > 0
    for vehicle in result.vehicles:
        for operation in vehicle.operations:
            if operation.end is not None:
                processing = sum(
                    max(0, min(operation.end, s.end) - max(operation.start, s.start))
                    for s in result.states
                    if s.station == operation.station and s.state == "running"
                )
                assert processing == pytest.approx(operation.processing_seconds, abs=1e-5)


def test_calendar_denominators_state_times_and_queue_integrals():
    config = small_config()
    calendar = Calendar(config)
    assert calendar.scheduled_seconds == 1080
    assert not calendar.position(300)[0]
    assert calendar.position(360)[0]
    assert calendar.shift_at(600).name == "shift_2"
    result = run_simulation(config)
    assert result.metrics["scheduled_hours"] == 0.3
    assert result.metrics["jph"] == result.metrics["completed"] / 0.3
    assert result.metrics["planned_break_hours"] == 120 / 3600
    assert result.metrics["average_wip"] <= result.metrics["maximum_wip"]
    for i, station in enumerate(result.metrics["stations"]):
        times = {
            name: sum(s.end - s.start for s in result.states if s.station == i and s.state == name)
            for name in ("running", "faulted", "blocked", "starved")
        }
        assert sum(times.values()) == pytest.approx(1080)
        assert station["utilization"] == pytest.approx(times["running"] / 1080)
        assert 0 <= station["average_input_queue"] <= station["maximum_input_queue"] <= 1
    assert (
        sum(v["completed"] for v in result.metrics["by_shift"].values())
        == result.metrics["completed"]
    )
    assert (
        sum(v["completed"] for v in result.metrics["by_hour"].values())
        == result.metrics["completed"]
    )


def test_same_seed_same_events_different_seed_changes_events():
    config = updated(SimulationConfig(days=1), shifts=small_config().shifts)
    left, right = run_simulation(config), run_simulation(config)
    changed = run_simulation(updated(config, seed=config.seed + 1))
    assert left.metrics == right.metrics
    assert [asdict(f) for f in left.faults] == [asdict(f) for f in right.faults]
    assert [asdict(v) for v in left.vehicles] != [asdict(v) for v in changed.vehicles]


def test_repair_intervention_scales_only_targeted_repair_samples():
    config = fault_config()
    target = Intervention(station=STATION_NAMES[0], method=InterventionMethod.REPAIR_DURATION)
    base = run_simulation(config)
    scenario = run_simulation(updated(config, intervention=target))
    assert scenario.config.stations == base.config.stations
    for fault in scenario.faults:
        assert fault.sampled_repair == pytest.approx(280)
    assert all(f.sampled_repair == 400 for f in base.faults)
    assert (
        scenario.metrics["stations"][0]["operations"] >= base.metrics["stations"][0]["operations"]
    )
    failure_rate = run_simulation(
        updated(
            config,
            intervention=target.model_copy(update={"method": InterventionMethod.FAILURE_RATE}),
        )
    )
    assert all(f.sampled_repair == 400 for f in failure_rate.faults)
    assert failure_rate.faults[0].start == pytest.approx(base.faults[0].start / 0.7)


def test_pairing_statistics_and_explicit_method():
    result = compare(
        fault_config(), Intervention(station=STATION_NAMES[0], method="repair_duration"), [1, 2, 3]
    )
    assert result["paired_gain"]["mean"] == pytest.approx(
        mean(r["gain_jph"] for r in result["runs"])
    )
    assert result["seeds"] == [1, 2, 3]
    assert (
        result["paired_gain"]["ci95"][0]
        <= result["paired_gain"]["mean"]
        <= result["paired_gain"]["ci95"][1]
    )
    assert statistics([1, 2, 3])["mean"] == 2
    assert statistics([1])["ci95"] is None
    with pytest.raises(ValidationError):
        Intervention(station=STATION_NAMES[0])


def test_candidates_need_sensitivity_and_slow_station_is_detected():
    config = small_config()
    stations = list(config.stations)
    stations[1] = stations[1].model_copy(
        update={"processing": Distribution(mean=50, cv=0, minimum=1)}
    )
    slow = updated(config, stations=tuple(stations))
    result = run_simulation(slow)
    assert candidates(result.metrics)["primary"] is None
    measured = sensitivity(slow, [1, 2, 3])
    assert measured["primary"] == "Framing"
    assert measured["sensitivity"]["Framing"]["mean"] > 0


def test_simulation_projection_supports_wip_and_cross_shift_faults():
    result = run_simulation(fault_config())
    history = project_result(result)
    assert history.provenance == "simulation"
    assert validate_simulation_history(history)["valid"]
    assert history.rows["simulation_run"][0]["results"]["censored_vehicles"]
    assert all(r["embedding"] is None for r in history.rows["source_record"])
    assert "sop_document" not in history.rows
    assert history.config.sop_reference_dataset == "stage2-30day-v1"
    broken = project_result(result)
    broken.rows["vehicle"][0]["model_id"] = "invalid-reference"
    with pytest.raises(ValueError):
        validate_simulation_history(broken)


@pytest.mark.parametrize(
    "change",
    [
        {"buffer_capacities": (0, 1, 1, 1, 1, 1)},
        {"suv_fraction": 1.1},
        {"release_rate_jph": 0},
        {"days": 0},
        {"shifts": ()},
        {"stations": ()},
    ],
)
def test_invalid_config_rejected(change):
    with pytest.raises(ValidationError):
        updated(small_config(), **change)


def test_repair_censoring_and_pending_work_at_observation_end():
    config = small_config()
    stations = list(config.stations)
    stations[0] = stations[0].model_copy(
        update={
            "failures": (
                Failure(mtbf_seconds=1, repair=Distribution(mean=100000, cv=0, minimum=1)),
            )
        }
    )
    result = run_simulation(updated(config, stations=tuple(stations)))
    assert result.faults[0].truncated
    assert result.faults[0].end == 86400
    assert result.metrics["completed"] == 0
    assert validate_result(result)["valid"]
    history = project_result(result)
    assert validate_simulation_history(history)["valid"]
    assert history.rows["simulation_run"][0]["results"]["censored_vehicles"]


def test_operation_pauses_during_gap_between_shifts_and_persists_completion_shift():
    config = small_config(
        shifts=(
            ShiftPattern(
                name="shift_1",
                start_seconds=0,
                duration_seconds=300,
                break_start_seconds=150,
                break_seconds=30,
            ),
            ShiftPattern(
                name="shift_2",
                start_seconds=800,
                duration_seconds=300,
                break_start_seconds=150,
                break_seconds=30,
            ),
        )
    )
    stations = tuple(
        s.model_copy(update={"processing": Distribution(mean=120, cv=0, minimum=1)})
        for s in config.stations
    )
    result = run_simulation(updated(config, stations=stations))
    assert validate_result(result)["valid"]
    assert any(
        o.start < 300 and o.end is not None and o.end > 800
        for v in result.vehicles
        for o in v.operations
    )
    assert not any(s.state == "running" and s.start < 800 and s.end > 300 for s in result.states)
    history = project_result(result)
    assert validate_simulation_history(history)["valid"]
    shifts = {r["id"]: r for r in history.rows["shift"]}
    assert any(
        r["started_at"] < shifts[r["shift_id"]]["start_time"]
        for r in history.rows["production_record"]
    )


def test_targeted_repair_keeps_other_machine_repair_streams_unchanged():
    config = small_config()
    stations = tuple(
        s.model_copy(
            update={
                "failures": (
                    Failure(mtbf_seconds=50, repair=Distribution(mean=20, cv=0.2, minimum=1)),
                )
            }
        )
        for s in config.stations
    )
    config = updated(config, stations=stations)
    before = run_simulation(config)
    target = Intervention(station="Closures Fitting", method="repair_duration")
    after = run_simulation(updated(config, intervention=target))
    old = {(f.station, f.category, f.equipment_id, f.occurrence): f for f in before.faults}
    shared = 0
    for fault in after.faults:
        key = (fault.station, fault.category, fault.equipment_id, fault.occurrence)
        if key in old:
            scale = 0.7 if fault.station == 3 else 1
            assert fault.sampled_repair == pytest.approx(old[key].sampled_repair * scale)
            shared += fault.station != 3
    assert shared > 0


def test_duplicate_seeds_and_single_run_constraint_claims_are_rejected():
    with pytest.raises(ValueError, match="distinct"):
        compare(small_config(), Intervention(station="Hemming", method="repair_duration"), [1, 1])
    assert sensitivity(small_config(), [1])["primary"] is None


def test_cli_reports_disk_full_without_printing_connection_secrets(monkeypatch, capsys):
    from unittest.mock import MagicMock

    from psycopg.errors import DiskFull
    from sqlalchemy.exc import OperationalError

    from bottleneck_analyzer.simulation import cli

    engine = MagicMock()
    engine.begin.return_value.__enter__.side_effect = OperationalError(
        "INSERT", {}, DiskFull("connection details must not be printed")
    )
    monkeypatch.setattr(cli, "create_db_engine", lambda: engine)
    monkeypatch.setattr(cli, "SimulationConfig", lambda: small_config())
    monkeypatch.setattr("sys.argv", ["stage3", "baseline", "--persist"])
    assert cli.main() == 1
    output = capsys.readouterr().out
    assert '"status": "failed"' in output
    assert '"commit_confirmed": false' in output
    assert '"sqlstate": "53100"' in output
    assert "connection details must not be printed" not in output
    engine.dispose.assert_called_once()
