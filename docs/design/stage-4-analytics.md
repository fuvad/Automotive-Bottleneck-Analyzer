# Stage 4 historical analytics

## Implementation and boundaries

The analytics layer reads persisted PostgreSQL history and returns validated
Pydantic results. It performs no simulation, LLM calculation, text retrieval,
agent routing, API presentation, or database writes. Stages 5–8 remain separate.
No dependency, migration, simulation assumption, or development dataset was added
or changed. The original implementation plan and two-day schedule are preserved:
Stage 4 belongs to Day 1 hours 3.5–4.5; calibration is already available from Stage 3.

The public Python interface is `analytics.service.analyze(engine, AnalyticsScope)`.
It owns a PostgreSQL repeatable-read, read-only transaction. The connection-level
function is SELECT-only and supports callers with an existing transaction,
including the isolated integration-test fixture. Analytics sets transaction-local
UTC and disables JIT for these calendar queries; neither changes server settings.

| Module under `src/bottleneck_analyzer/analytics/` | Responsibility |
| --- | --- |
| `contracts.py` | Dataset-explicit scope, metrics, aggregate evidence, candidates and results |
| `calendar.py` | Interval union, clipping, exclusion subtraction and segment calendars |
| `repository.py` | Parameterized PostgreSQL aggregations and bounded metadata reads |
| `candidates.py` | Observational indicators, documented score, evidence labels and abstention |
| `service.py` | Read-only snapshot, metric composition, provenance and report association |
| `cli.py` | Explicit local analysis and optional JSON report |

Existing manufacturing names, `AnalysisScope`, `EvidenceReference`, SQLAlchemy
tables, engine factory, configuration and test infrastructure are reused. No
parallel domain vocabulary or ORM result objects are exposed to callers.

## Dataset selection and scope

`dataset` is mandatory. Missing datasets raise an error, with no fallback.
The primary history is `sim-30day-baseline-v1`, provenance `simulation`; the original
`stage2-30day-v1` retains provenance `authored_fixture`. The existing
`sim-framing-validation-v1` supplies the independent Framing reference case.
Dataset UUID, content hash, provenance, selected period and filters accompany results.

Optional scope filters are aware start/end timestamps, station name, SUV/Sedan,
shift_1/shift_2, a dated shift UUID, and a list of UTC hours 0–23. Periods must be
inside the requested dataset. Unknown stations, foreign shift UUIDs, invalid hours
and naive timestamps are rejected. The free-text shared `time_of_day` filter is
deliberately unavailable here; a later planner must translate it into UTC hours.

All relevant tables and joins carry explicit dataset predicates. Source records,
models and neighboring stations cannot leak across datasets. A station filter
limits displayed station results after ranking with the full line context; it
does not redefine line output as that station's operations. Model filters do not
reduce the scheduled-hours denominator.

Periods are half-open `[start,end)`. Shift results retain dated UUIDs and labels.
Time-of-day results pool the same UTC hour across the selected dates into 24
groups; they are not a chronological hourly time series. Intersections handle
partial hours, partial shifts and planned breaks. The analytics transaction pins
UTC because PostgreSQL `date_trunc(timestamptz)` otherwise follows session timezone.

## Metric definitions

| Metric | Definition / measurement basis |
| --- | --- |
| Scheduled hours | Union of selected shift windows minus the union of explicit calendar exclusions, divided by 3,600 |
| Line JPH | Final Inspection completions in selected windows / scheduled hours; null when no scheduled hours |
| Design gap | Configured design JPH minus observed line JPH; also design rate × scheduled hours minus completions |
| Model JPH | That model's completions / the same scheduled hours: contribution to mixed-line output |
| Admissions | Vehicles whose persisted release timestamp falls in selected windows |
| Initial/final WIP | Admitted but not completed at the first/last selected period boundary |
| Average flow time | Calendar release-to-completion time for bodies completed in selected windows |
| Average/max WIP | Scheduled-time integral / scheduled seconds, and positive-duration maximum; includes machine-held vehicles |
| Station operations | Persisted processing completions at that station, selected by completion timestamp |
| Processing/utilization | Exclusive `running` seconds within scheduled windows; divided by scheduled seconds for utilization |
| Faulted/blocked/starved | Exclusive corresponding station-state seconds within scheduled windows |
| Planned closure | Selected wall seconds minus scheduled seconds, including breaks and off-shift closure |
| Active service mean | Retained MES `processing_seconds` averaged over completed visits |
| Processing capacity | 3,600 / mean service seconds; explanatory diagnostic, not actual throughput |
| Effective capacity diagnostic | Processing capacity × (1 − exclusive faulted seconds / scheduled seconds) |
| Operation elapsed | Completion minus processing start; can include repair and planned closure, so is not active work |
| Model waiting/blocking | Mean retained MES wall-clock wait/block durations for completed visits; may include closure |
| Average/max input queue | Reconstructed arrival-to-start intervals, weighted by scheduled time and swept for occupancy |

Unplanned downtime stays in scheduled hours. Physical repair duration is never
added to exclusive fault-state duration. Design gap is not loss attributable to
one station; recoverable output requires a defined counterfactual simulation.
Neither capacity diagnostic substitutes for Final Inspection throughput.

Model-specific machine-state utilization/fault/block/starve totals are null:
the persisted state table has no model/vehicle attribution. Model segments use
actual model service samples, queue contributions and wall-clock wait/block
observations, with warnings. Completed-visit means include the entire visit even
if it crosses the requested boundary; they are not interval-exposure totals.
Small model samples are flagged. No exclusive-model line capacity is inferred.

Queue reconstruction includes unfinished operations and waiting, not-yet-started
visits from the bounded `simulation_run.results.censored_vehicles` tail. It does
not load full raw exports or all vehicle traces into Python. Timestamp conversion
can create one-microsecond simultaneous-transition artifacts: integrals retain
their precision, while maxima exclude sweep spans of at most two microseconds.
Instantaneous queue spikes in the simulator need not be reconstructable.
Authored fixtures lack the necessary arrival/service traces; those metrics are
null, never fabricated from operation elapsed time.

For noncontiguous shift/hour filters, WIP stocks describe the outer boundaries;
admissions and completions describe only selected windows. Their difference must
not be interpreted as a conservation check across omitted time. State coverage
is interval-union coverage / scheduled time. Overlapping durations are reported
and state totals suppressed; missing coverage is warned rather than filled in.

## Query strategy and traceability

Small dataset/station/calendar/run metadata is read once. PostgreSQL handles
operation counts/means, clipped state totals and interval unions, line events,
queue endpoint sweeps and WIP integrals across all segments in batches. The
repository returns aggregates, bounded source-reference samples and the censored
WIP tail, rather than hundreds of thousands of source/state rows.

Calendar windows are split at UTC-hour boundaries. Materialized state/occupancy
slices permit hash joins on UTC hour before exact interval clipping. Inspection
of `EXPLAIN` caught an initial nested loop over the whole state table; explicit
materialization removed that repeated scan. Existing dataset, station/time,
vehicle and unique-operation indexes were inspected; no new index was necessary.
SQL uses bound parameters and fixed query templates, never agent-generated SQL.

Aggregate references include dataset UUID, scope signature, segment, station,
measurement, record count and bounded deterministic source UUID/system/source-ID
samples. They describe a selection of records, not a claim that one sample proves
the whole aggregate. Supporting/contradicting indicators and source references
remain inspectable without returning large raw histories.

## Candidate method

The score organizes observational candidates; it is neither a probability nor a
statistically validated constraint classifier. All seven stations receive ranks;
the leading candidate is separately nullable.

Each available component is bounded to 0–1. Missing components contribute zero
and remain explicitly null. The score is:

```text
0.30 × busy pressure
+ 0.25 × input queue / input capacity
+ 0.20 × immediate upstream blocking fraction
+ 0.20 × immediate downstream starvation fraction
+ 0.05 × service mean / largest station service mean
− 0.10 × (own blocking fraction + own starvation fraction)
```

For full-line segments, busy pressure is `(processing + faulted) / scheduled`.
This recognizes station occupancy while requiring independent flow propagation.
Own blocking/starvation remain conflicting evidence of downstream/upstream
restriction. Fault fraction and utilization are also exposed separately.

For model segments, busy pressure is relative service demand; upstream blocking
and downstream waiting use model visit wall-clock means divided by 3,600 and
clipped to 1. These are weaker proxies, not model-exclusive machine-state fractions.
Missing first/last neighbors are null rather than invented observations.

Supporting indicators use fixed thresholds: busy pressure ≥ 0.75, queue fraction
≥ 0.50, upstream blocking ≥ 0.05, downstream starvation ≥ 0.05. Own blocking or
starvation above 0.10 is explicitly conflicting. Missing queue/service information
is also retained as a limitation. Weights and thresholds are MVP heuristics,
declared before reference-case validation; no station name determines the result.

Evidence strength requires at least 30 completed operations and 1,800 scheduled
seconds. Non-model segments additionally require ≥95% state coverage and no
overlap beyond one millisecond. Given that minimum:

- `strong`: at least three supporting signals in a non-model segment.
- `moderate`: at least two supporting signals; model segments are capped here.
- `weak`: fewer supporting signals, despite adequate basic coverage/sample.
- `insufficient_evidence`: the minimum sample/coverage requirements fail.

Only a strong/moderate top candidate separated from second place by at least 0.01
is asserted as a leader. Otherwise the result abstains. Ties sort by station name
for deterministic output but never force a leader. Strength describes the
available indicators, not proof; conflicting indicators can coexist with support.

Rankings run overall, by dated shift, by model and by UTC-hour group. Results
report changed leaders and unresolved groups. Overall candidate persistence is
the fraction of resolved dated shifts led by that station; evaluated/resolved
shift counts are also exposed so sparse coverage cannot masquerade as persistence.

## Separate simulation evidence

Persisted run/configuration IDs, seed and full-run reference JPH are exposed as
simulation metadata, not substituted for historical calculations. Optional saved
Stage 3 assessment context requires both the paired-comparison and assessment
files. The baseline configuration must match the dataset except name, replication
seed and history-recording flag; the assessment must share the comparison summary.
File hashes and paths identify the supplied local artifacts. Mismatches raise errors.

The sensitivity evidence retains its own three-day horizon/seeds, while the paired
comparison uses 30 days. It is full-configuration context even for a filtered
request, never evidence that a particular segment has a proven constraint. It
does not change the historical score. Synthetic sensitivity is not real-plant proof.

## Commands

Run from the project root using the configured `.env`:

```powershell
poetry run python -m bottleneck_analyzer.analytics.cli --dataset sim-30day-baseline-v1
poetry run python -m bottleneck_analyzer.analytics.cli --dataset sim-framing-validation-v1
poetry run python -m bottleneck_analyzer.analytics.cli --dataset sim-30day-baseline-v1 --model SUV --shift shift_1 --utc-hour 4
poetry run python -m bottleneck_analyzer.analytics.cli --dataset sim-30day-baseline-v1 --comparison data/processed/stage3/paired-comparison.json --assessment data/processed/stage3/constraint-assessment.json --report data/processed/stage4/example.json
```

`--start`/`--end` accept timezone-aware ISO timestamps; `--shift-id` accepts a UUID.
Report creation refuses to overwrite an existing path. Reports are local, ignored
artifacts. SQL errors print only their class and a generic diagnostic, without
connection details. If Poetry is not on PATH, the existing
`.\.venv\Scripts\python.exe -m ...` provides equivalent module execution.

## Measured baseline and interpretation

The persisted seed-1001 baseline gives:

| Metric | Historical result |
| --- | ---: |
| Admitted / completed / final WIP | 21,126 / 21,096 / 30 |
| Scheduled hours / JPH | 450 / 46.88 |
| Design gap / design-gap bodies | 13.12 JPH / 5,904 |
| SUV / Sedan completions | 10,461 / 10,635 |
| SUV / Sedan JPH contribution | 23.246667 / 23.633333 |
| Mean flow time / average WIP | 3,771.414151 seconds / 30.922847 |
| Overall leader | Hemming |
| Dated shifts / model groups / UTC-hour groups | 60 / 2 / 24 |

All dated shifts identify Hemming. Model proxy rankings identify Framing for both
SUV and Sedan; those qualified demand/wait rankings differ from the shared-line
ranking and are not evidence that the physical constraint changed by model.
Closed UTC-hour groups have null JPH and no asserted leader.

The historical 46.88 JPH matches the retained single run, not the 46.255889 mean
of 20 independent Stage 3 replications. That difference is expected sampling
variation. Historical calculations and stored run metrics independently agree
on counts, scheduled hours, station state durations, flow, WIP and queue integrals.
The separate Framing dataset produces 1,716 completions at 38.133333 JPH and ranks
Framing first despite Hemming having the largest faulted-time total.

## Validation record

Focused unit tests cover manually checked JPH/design gap, calendar unions,
overlapping breaks, partial hours, shift/model segmentation, scope validation,
candidate conflicts, abstention, deterministic ranking and report mismatches.
PostgreSQL tests use the existing opt-in rollback-only schema fixture for temporary
test history; no new development dataset is generated. They cover state gaps and
overlap, real operation/state/queue aggregation, censoring, provenance, dataset
isolation, repeatability, partial/closed periods, and the two existing persisted
simulation references. A statement audit checks bounded read-only queries.

Final executed commands and their results are recorded in
[`../implementation-status.md`](../implementation-status.md). No separate static
type checker is configured. Early performance and timezone failures were fixed
before final acceptance; failed diagnostic reports are not acceptance artifacts.

A measured full baseline analysis, including all 86 segments and associated
Stage 3 reports, used **15 SQL statements in 33.326 seconds** while another test
run was active. Its JSON report was **3,451,105 bytes**. This is an observation on
the local machine, not a latency guarantee. No peak-memory benchmark is claimed.
No raw export was read. Local files from early diagnostic runs may contain failed
or superseded measurements; use the verified result or rerun the current CLI to
a fresh report path.

## Limits

The ranking is heuristic and observational. No root cause, station-attributable
recoverable loss or real-plant constraint is inferred. Shared states cannot be
assigned exclusively to SUV/Sedan. Completed-visit means can have censoring or
boundary selection bias. Queue maxima have timestamp-resolution limits.
Full segment reports are several MiB of structured aggregates; downstream tools
should select relevant scopes/fields rather than pass the entire report to an LLM.
The existing serial-line, synthetic calendar and no-scrap/rework assumptions still
apply. Real production deployment requires further validation and human review.
