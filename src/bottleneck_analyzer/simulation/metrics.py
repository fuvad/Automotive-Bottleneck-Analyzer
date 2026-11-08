"""Deterministic metrics from simulated events, separate from historical analytics."""


def summarize(line) -> dict:
    calendar = line.calendar
    scheduled = calendar.scheduled_seconds
    hours = scheduled / 3600
    station_metrics = []
    for index, station in enumerate(line.config.stations):
        times = line.states.durations[index]
        faults = [f for f in line.faults if f.station == index]
        operating = times.get("running", 0.0)
        operations = line.operation_counts[index]
        observed_mean = line.completed_work[index] / operations if operations else None
        station_metrics.append(
            {
                "station": station.name,
                "processing_seconds": operating,
                "fault_seconds": times.get("faulted", 0.0),
                "planned_closed_seconds": times.get("planned_downtime", 0.0),
                "blocked_seconds": times.get("blocked", 0.0),
                "starved_seconds": times.get("starved", 0.0),
                "utilization": operating / scheduled,
                "mean_completed_service_work_seconds": observed_mean,
                "processing_capacity_jph": 3600 / observed_mean if observed_mean else None,
                "availability": 1 - times.get("faulted", 0.0) / scheduled,
                "average_input_queue": line.queue_gauges[index].finish(),
                "maximum_input_queue": line.queue_gauges[index].maximum,
                "operations": line.operation_counts[index],
                "throughput_jph": line.operation_counts[index] / hours,
                "fault_count": len(faults),
                "observed_operating_mtbf_seconds": operating / len(faults) if faults else None,
                "mean_observed_repair_seconds": (
                    sum(f.end - f.start for f in faults) / len(faults) if faults else None
                ),
                "fault_calendar_seconds": sum(f.end - f.start for f in faults),
                "fault_by_category": {
                    category: {
                        "count": sum(f.category == category for f in faults),
                        "scheduled_seconds": sum(
                            calendar.scheduled_between(f.start, f.end)
                            for f in faults
                            if f.category == category
                        ),
                        "sampled_repair_seconds": sum(
                            f.sampled_repair for f in faults if f.category == category
                        ),
                    }
                    for category in sorted({f.category for f in faults})
                },
            }
        )
        total = sum(times.get(s, 0.0) for s in ("running", "blocked", "starved", "faulted"))
        if abs(total - scheduled) > 1e-3:
            raise ValueError(f"Station state accounting does not conserve time: {station.name}")
    if line.released - line.completed != line.wip.value:
        raise ValueError("Vehicle conservation failed")
    by_shift = {}
    for w in calendar.windows:
        key = f"{w.day}/{w.name}"
        denominator = calendar.scheduled_between(w.start, w.end) / 3600
        by_shift[key] = {
            "completed": line.shifts[key],
            "scheduled_hours": denominator,
            "jph": line.shifts[key] / denominator,
        }
    return {
        "released": line.released,
        "completed": line.completed,
        "final_wip": line.wip.value,
        "scheduled_hours": hours,
        "jph": line.completed / hours,
        "planned_break_hours": sum(w.break_end - w.break_start for w in calendar.windows) / 3600,
        "planned_closed_hours": (calendar.horizon - scheduled) / 3600,
        "unplanned_station_seconds": sum(s["fault_seconds"] for s in station_metrics),
        "average_cycle_seconds": line.cycle_sum / (line.completed - 1)
        if line.completed > 1
        else None,
        "average_flow_seconds": line.flow_sum / line.completed if line.completed else None,
        "average_wip": line.wip.finish(),
        "maximum_wip": line.wip.maximum,
        "by_model": {
            model: {"completed": line.models[model], "jph": line.models[model] / hours}
            for model in ("SUV", "Sedan")
        },
        "by_shift": by_shift,
        "by_hour": {
            str(hour): {
                "completed": line.hourly[str(hour)],
                "scheduled_hours": calendar.scheduled_between(hour * 3600, (hour + 1) * 3600)
                / 3600,
                "jph": (
                    line.hourly[str(hour)]
                    * 3600
                    / calendar.scheduled_between(hour * 3600, (hour + 1) * 3600)
                )
                if calendar.scheduled_between(hour * 3600, (hour + 1) * 3600)
                else None,
            }
            for hour in range(int(calendar.horizon // 3600))
        },
        "stations": station_metrics,
        "warmup_seconds": 0,
        "initial_wip": 0,
    }


def candidates(metrics: dict, sensitivity: dict[str, dict] | None = None) -> dict:
    """Rank multiple signals; only paired sensitivity can qualify a primary constraint."""
    hours = metrics["scheduled_hours"]
    signals = []
    for i, station in enumerate(metrics["stations"]):
        upstream_blocking = metrics["stations"][i - 1]["blocked_seconds"] if i else 0
        downstream_starvation = metrics["stations"][i + 1]["starved_seconds"] if i < 6 else 0
        signals.append(
            {
                "station": station["station"],
                "utilization": station["utilization"],
                "input_queue": station["average_input_queue"],
                "fault_seconds": station["fault_seconds"],
                "upstream_blocked_seconds": upstream_blocking,
                "downstream_starved_seconds": downstream_starvation,
                "operations": station["operations"],
                "processing_capacity_jph": station.get("processing_capacity_jph"),
                "observational_score": station["utilization"]
                + station["average_input_queue"] / 10
                + (upstream_blocking + downstream_starvation) / (hours * 3600),
            }
        )
    signals.sort(key=lambda s: s["observational_score"], reverse=True)
    primary = None
    if sensitivity:
        ranked = sorted(sensitivity, key=lambda s: sensitivity[s]["mean"], reverse=True)
        if ranked and sensitivity[ranked[0]]["ci95"] and sensitivity[ranked[0]]["ci95"][0] > 0:
            primary = ranked[0]
    return {
        "primary": primary,
        "observational_candidates": signals,
        "sensitivity": sensitivity or {},
        "qualification": (
            "Modeled constraint supported by paired station-capacity sensitivity."
            if primary
            else "Candidates only; sensitivity is absent or inconclusive."
        ),
    }
