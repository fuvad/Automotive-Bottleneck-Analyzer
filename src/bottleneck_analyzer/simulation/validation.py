"""Conservation, routing, state and calendar validation for actual simulated output."""

import math
from collections import defaultdict

from bottleneck_analyzer.simulation.calendars import Calendar
from bottleneck_analyzer.simulation.engine import SimulationResult


def validate_result(result: SimulationResult) -> dict:
    if not result.config.record_history:
        raise ValueError("Business-history validation requires record_history=True")
    calendar = Calendar(result.config)
    metrics = result.metrics
    if len(result.vehicles) != metrics["released"]:
        raise ValueError("Released vehicles do not match the retained history")
    completed = 0
    for vehicle in result.vehicles:
        if not 0 <= vehicle.release < calendar.horizon:
            raise ValueError("Invalid vehicle release time")
        if not calendar.position(vehicle.release)[0]:
            raise ValueError("Vehicle released during a planned closure")
        expected = list(range(len(vehicle.operations)))
        if [o.station for o in vehicle.operations] != expected:
            raise ValueError("Vehicle route is out of order or duplicates a station")
        previous = vehicle.release
        for operation in vehicle.operations:
            if not previous - 1e-6 <= operation.arrival <= operation.start:
                raise ValueError("Vehicle arrival/start violates flow order")
            if operation.processing_seconds <= 0:
                raise ValueError("Processing durations must be positive")
            if operation.end is not None:
                if operation.end <= operation.start:
                    raise ValueError("Processing end must follow start")
                if operation.departure is not None and operation.departure < operation.end:
                    raise ValueError("Departure precedes processing end")
                previous = operation.departure or operation.end
        if vehicle.completion is not None:
            if len(vehicle.operations) != 7 or vehicle.operations[-1].end != vehicle.completion:
                raise ValueError("Only Final Inspection completes a vehicle")
            completed += 1
    if completed != metrics["completed"] or metrics["released"] != completed + metrics["final_wip"]:
        raise ValueError("Vehicle conservation failed")
    if (
        metrics["maximum_wip"]
        > result.config.input_capacity + sum(result.config.buffer_capacities) + 7
    ):
        raise ValueError("WIP exceeds bounded storage plus station positions")
    state_groups = defaultdict(list)
    for state in result.states:
        if state.end <= state.start:
            raise ValueError("Invalid state interval")
        state_groups[state.station].append(state)
    for station in range(7):
        states = sorted(state_groups[station], key=lambda s: s.start)
        if not states or states[0].start != 0 or states[-1].end != calendar.horizon:
            raise ValueError("State history does not cover the observation period")
        if any(abs(a.end - b.start) > 1e-6 for a, b in zip(states, states[1:])):
            raise ValueError("Station state intervals overlap or leave gaps")
        for state in states:
            active = calendar.scheduled_between(state.start, state.end)
            if state.state == "planned_downtime":
                if active > 1e-5:
                    raise ValueError("Planned downtime overlaps scheduled operating time")
            elif abs(active - (state.end - state.start)) > 1e-5:
                raise ValueError("Active station state overlaps a planned closure")
        queue = metrics["stations"][station]["maximum_input_queue"]
        capacity = (
            result.config.input_capacity
            if station == 0
            else result.config.buffer_capacities[station - 1]
        )
        if queue > capacity:
            raise ValueError("Finite buffer capacity exceeded")
        faults = sorted([f for f in result.faults if f.station == station], key=lambda f: f.start)
        if any(a.end > b.start + 1e-6 for a, b in zip(faults, faults[1:])):
            raise ValueError("Machine failures overlap")
    if not math.isclose(metrics["jph"], completed / (calendar.scheduled_seconds / 3600)):
        raise ValueError("Invalid JPH denominator")
    return {
        "valid": True,
        "completed": completed,
        "final_wip": metrics["final_wip"],
        "released": metrics["released"],
        "provenance": "simulation",
    }
