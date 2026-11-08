# Stage 3 — seven-station SimPy simulation

## Architecture and configuration

The public tool interface is `simulation.engine.run_simulation(SimulationConfig)`.
It returns metrics plus optional business history. `environment.py` owns the
SimPy environment; `station.py` owns machine workers; `buffer.py` owns bounded
stores; `calendars.py` controls availability; `events.py` records exclusive states
and time-weighted gauges. `metrics.py`, `scenarios.py`, and `calibration.py` contain
deterministic simulation calculations and experiments. These modules do not
query historical production, run agents, or serve business API endpoints.

Parameters are validated, frozen Pydantic models. Seven ordered station names
reuse the manufacturing vocabulary. `topology_from_dataset()` reads the existing
station order, six buffer capacities and the first dated shift patterns/breaks
from `stage2-30day-v1`; processing distributions remain explicit synthetic inputs.
The initial dataset's fixed vehicle volume is never used to limit simulation
output. The 60-second planned cycle remains a separate design reference.

## Station and finite-buffer semantics

Seven concurrent station workers follow the agreed order. Each worker retrieves
one body, processes its remaining work, then yields a `Store.put()` into the next
finite buffer. If that buffer is full, the worker retains the body and is blocked
after service. It cannot start another body until the put succeeds. This naturally
propagates congestion upstream. Empty input stores cause starvation. Six stores
have the reference capacity of five; the external admission store is also bounded
at five. Maximum admitted WIP is therefore bounded by input capacity + six buffer
capacities + seven machine positions (42 with the baseline configuration).

Releases occur periodically at 65 opportunities/hour of scheduled time. Source
backpressure waits for space rather than creating an unlimited queue or admitting
all bodies at once. An exponential arrival pattern is also available. Arrival
cadence pauses outside scheduled production. Actual admission is recorded when
the bounded input store accepts the vehicle. Output is determined by line events,
not by the illustrative 46 JPH reference or the authored fixture's volume.

Vehicles retain one sequence/model identity, release time, station arrival/start,
sampled processing work, processing end and departure, plus Final Inspection
completion. An operation may finish processing but remain blocked. Vehicles still
waiting/processing/blocked at the horizon remain WIP; they are never reported as
line completions. Production starts from an empty line; WIP carries across shifts
and days, with no artificial daily reset and no drain after the observation end.

## Synthetic processing, failure and repair assumptions

Initial mean processing seconds by station are 54, 59, 55, 56, 60, 55, 54. Each uses
a lognormal draw with CV 0.08, floored at 30 seconds before model adjustment.
SUV multiplies work by 1.04; Sedan by 0.96. The baseline mix is independently
sampled 50/50. These are authored modeling assumptions, not real factory values.
The floor ensures positive processing, and can slightly raise the distribution's
realized mean when strongly binding; all parameters are configurable.

Failures use independent exponential operating-work budgets by station, category
and equipment. Only actual processing depletes these budgets. They pause during
blocking, starvation, repair and planned closure. The first budget exhausted
suspends processing; a positive lognormal repair timeout runs on calendar time.
After repair the machine resumes the exact remaining processing work. The failed
clock resets; other equipment clocks retain their budgets. Repairs are serialized
at each station and cannot overlap, despite multiple configured categories.

Supported categories include robot, mechanical, electrical, sensor and other
equipment faults, plus the existing quality/material vocabulary. Additive Alembic
revision `0002` extends the category check constraint; it does not change existing
data or reinstall pgvector. The pre-existing migration test's hardcoded revision
was updated to the actual Alembic head with explicit user approval; its schema
comparison and other checks remain intact.

Robot operating MTBF is initially 2,400 seconds at Hemming and 30,000 elsewhere.
Initial robot mean repair is 360 seconds at Hemming and 120 elsewhere, CV 0.35,
minimum 10 seconds. Other equipment categories use operating MTBF 120,000 seconds,
mean repair 90 seconds and CV 0.3. The calibration search changes only the Hemming
robot mean repair within the declared 360/480/600/720-second grid.

## Calendar and state accounting

The baseline reuses the synthetic two eight-hour windows at 00:00 and 08:00 UTC,
with a 30-minute break four hours into each shift. Thirty days yield 450 scheduled
production hours, 30 break hours, and 240 hours outside shifts. Configuration can
change shift windows/breaks; the current model supports two non-overlapping shifts
and one contiguous break per shift.

Processing and new releases pause during planned closure. Repairs continue through
breaks and overnight. If repair ends while closed, processing waits until reopening.
Exclusive recorded machine states give planned closure priority over faulted,
running, blocked and starved states. Thus machine fault loss excludes repair time
that overlaps a planned break or off-shift period. Physical fault/repair elapsed
duration is retained separately. At the horizon, unfinished repairs are censored
and explicitly labeled; sampled repair duration and observed duration are distinct.

## Metric definitions

- JPH = Final Inspection completions / scheduled production hours. Unplanned
  failures remain in the denominator. Startup is included; warm-up is zero.
- Processing utilization = actual active processing seconds / scheduled seconds.
  State-duration conservation is checked for every station.
- Blocking/starvation/fault loss come from exclusive state intervals, never from
  a capacity formula or post-hoc subtraction.
- Queue and WIP averages integrate occupancy over scheduled time. Maxima come
  from real put/get/admission/completion transitions. WIP includes machine-held
  bodies, including bodies blocked after processing.
- Average flow time is calendar time from admission to Final Inspection,
  including closures. Average output cycle time uses scheduled time between
  consecutive completions. These denominators are intentionally different.
- Per-model JPH is each model's contribution to total scheduled-hours throughput,
  not an estimate of the capacity of a line making that model exclusively.
- Per-dated-shift and per-UTC-hour results retain completion counts and their own
  scheduled-hours denominators; a closed hour has no JPH rather than an invented zero rate.
- Operating MTBF is observed processing time / fault count; mean observed repair
  uses physical elapsed duration. Censored boundaries affect these diagnostics.
- `unplanned_station_seconds` sums machine loss time; it is not line-level output
  loss and must not be summed into recoverable JPH. Processing-capacity diagnostics
  are explanatory only; actual throughput always comes from SimPy completions.

## Constraint evidence and experiments

Observational candidates combine utilization, queues, upstream blocking,
downstream starvation and operations. Their score only organizes evidence. It
does not establish the constraint. `sensitivity()` separately reduces one
station's processing-time distribution by 10%, preserves other assumptions, and
compares paired seeds. A positive interval for the strongest measured response
qualifies a modeled primary candidate. Other stations and conflicting metrics
remain visible. A single replication cannot supply an uncertainty interval.

The baseline and post-intervention sensitivity assessments use explicitly
declared horizons and seeds. They are exploratory comparisons across seven
stations; intervals are not adjusted for multiple comparisons or model error.
The Framing stress fixture changes Framing processing assumptions and measures
the response. Its expected constraint is checked by simulation, not returned as
a hardcoded answer, and need not be the station with most raw downtime.

`calibrate()` evaluates a fixed grid, retaining every parameter change, seed,
configuration, line result and station diagnostic. Five three-day seeds 11–15
were used for selection. The mean JPH values were 51.2844 (360 s), 49.2444 (480 s),
47.1600 (600 s), and 45.3111 (720 s). The selected 720-second repair configuration
meets the initial 45–47 JPH calibration tolerance. It must also be evaluated on
separate seeds. This matches an illustrative synthetic target, not plant data.

Random streams use stable SHA-256 seed derivation. Processing is keyed by station
and vehicle sequence, vehicle mix has its own stream, and gaps/repairs have separate
station/category/equipment streams indexed by occurrence. Scenario seeds align
these random inputs; failures need not happen at identical calendar times because
operating-time exposure changes with flow. No global Python random state is used.

The primary intervention multiplies only targeted robot repair samples by 0.70.
The separate failure-rate intervention changes MTBF to MTBF / 0.70, preserving
repair samples. It does not multiply MTBF by 0.70. Target station/category/equipment
and method are mandatory in the validated tool configuration. Ambiguous language
must be clarified by the later planner; this stage does not implement language routing.

Paired experiments report baseline/scenario means, standard deviations, ranges,
95% Student-t intervals, paired differences, percent gain, and realized scheduled
target downtime change. The latter need not equal exactly 30% because exposure,
event counts and horizon censoring can change. Uncertainty covers random seeds,
not structural model error. Constraint movement is reported only after separately
checking baseline and scenario sensitivity; it is never guaranteed.

## Persistence and source projections

`project_result()` maps actual events into the existing business tables.
`SimulationHistory` reuses Stage 2 UUID namespaces, source identities, provenance
fields, fingerprinting, atomic loading, advisory locking and stored-value replay
checks. The loader accepts the explicit simulation validator; the authored
validator and generator retain their existing semantics. A new dataset stores
`provenance=simulation`, full version/configuration, seed, baseline/intervention
role, calibration status and a simulation-run record. No operational approval is
fabricated: model approval fields remain null.

MES rows represent operations whose processing has finished. Their raw records
retain arrival, service work, departure/blocking, release and completion context.
An operation can span shifts; its normalized shift FK identifies its completion
shift. End-of-horizon censored vehicles/operations are retained in simulation-run
results. SCADA states are clipped into dated shifts; outside-shift closure remains
available in simulation state totals.

A physical fault can cross several active/closed intervals. Its `fault_event`
stores physical elapsed repair duration and references the first active fault
fragment. Direct source links connect every active fragment of that incident.
Downstream consumers must use exclusive station-state intervals for scheduled
fault loss and must not add overlapping planned time from physical repair duration.

CMMS and Andon samples reference the same simulated incident. Some incidents have
no human record. Shift notes without incident IDs have null fault FKs and inferred
evidence links. Historian samples explicitly represent a simulated fault-active
indicator, not a physically causal sensor model; bad/missing quality is preserved.
Unrelated handover notes remain present for later retrieval validation.

SOP content is reused by reference to `stage2-30day-v1` in configuration and the
manifest. No SOP documents/sections are copied into the simulation dataset.
The reference dataset is verified before persistence. All generated source records
are synthetic. The authored dataset is never deleted, overwritten or relabeled.

## CLI and verification

Run from the project root. Poetry can prefix each command with `poetry run`.
In the current environment, `.\.venv\Scripts\python.exe -m` provides the same
module execution using the existing environment.

```powershell
poetry run alembic upgrade head
poetry run python -m bottleneck_analyzer.simulation.cli calibrate --days 3 --replications 5 --seed-start 11 --report data/processed/stage3/calibration.json --save-config data/processed/stage3/calibrated-config.json
poetry run python -m bottleneck_analyzer.simulation.cli scenario --config data/processed/stage3/calibrated-config.json --days 30 --replications 20 --seed-start 1001 --target Hemming --method repair_duration --report data/processed/stage3/paired-comparison.json
poetry run python -m bottleneck_analyzer.simulation.cli assess --comparison data/processed/stage3/paired-comparison.json --days 3 --replications 5 --seed-start 2001 --report data/processed/stage3/constraint-assessment.json
poetry run python -m bottleneck_analyzer.simulation.cli baseline --config data/processed/stage3/calibrated-config.json --days 30 --from-dataset --export --persist --report data/processed/stage3/persisted-baseline.json
```

`baseline` validates the retained output and optionally exports/persists it.
`replicate` runs baseline replications; `scenario` runs paired experiments;
`sensitivity` tests each station; `assess` combines a paired experiment with
baseline/post-intervention sensitivity. All report files are immutable: identical
replays are accepted; conflicting content needs a new path or dataset name. Without
`--config`, commands use the initial, uncalibrated assumptions. Nothing runs during
FastAPI startup.

Small deterministic tests cover conservation, correct routes, buffers, failures,
resumption, calendars, denominators, random streams, scenario targeting and
statistics. Database-write tests reuse the rollback-only isolated schema fixture;
`STAGE2_TEST_POSTGRES=1` explicitly opts in. No tests clear development tables.
Long 30-day/20-pair experiments are run explicitly and saved under the ignored
`data/processed/stage3/` directory.

Metrics-only runs retain bounded active vehicles, aggregate counts, and physical
faults. Full-history runs retain business events/vehicle traces for projection,
not every internal SimPy scheduling event. Processing and recording consume
memory proportional to retained business history when enabled.

## Remaining limits

This is a single synthetic serial line with one machine position per station,
finite buffers and no scrap, rework, labor contention, conveyor travel, batching,
planned overtime or shared repair crews. Repairs run through closures; failures
are operating-time equipment events. Those assumptions must be revisited before
any plant use. Calibration is not real-plant validation. Saved artifacts and the
execution record report the actual experiments and acceptance checks.

## Executed experiments — 2026-11-08

The independent 30-day paired experiment used seeds 1001–1020 after calibration
selection on seeds 11–15. No parameter was changed in response to the evaluation.

| Metric | Baseline | 30% shorter targeted robot repairs |
| --- | ---: | ---: |
| Replications | 20 | 20 |
| Mean JPH | 46.255889 | 49.609000 |
| Standard deviation | 0.429603 | 0.348899 |
| Minimum–maximum JPH | 45.306667–46.880000 | 48.748889–50.022222 |
| 95% interval for mean | 46.054831–46.456947 | 49.445712–49.772288 |

The mean paired gain was **3.353111 JPH**, 95% interval **3.275210–3.431012**,
or **7.249%**. Scheduled targeted robot-fault loss fell by **24.714%**; this is an
observed change, distinct from the exact 0.70 multiplier on repair samples.

Baseline and post-intervention sensitivity each used five independent three-day
seeds 2001–2005. Hemming remained the primary modeled candidate: its 10% processing
speed-up gave mean gains 4.826667 JPH (95% interval 4.689556–4.963777) before the
intervention and 4.973333 (4.616603–5.330064) afterward. The tested alternatives
had zero gain in those runs. The constraint did **not** move. All 20 full baseline
runs also ranked Hemming first observationally, which is supporting evidence rather
than a substitute for the separate sensitivity experiments.

The failure-rate mechanism was checked separately using 20 three-day pairs,
seeds 4001–4020. Baseline mean was 46.454444 JPH, scenario mean 49.637778, mean
paired gain 3.183333 (95% interval 2.751442–3.615225), with a 24.037% observed
scheduled downtime reduction. Its shorter horizon must be retained when comparing
it with the primary 30-day experiment.

The Framing case uses the checked-in `simulation-framing.json` inputs and seeds
3001–3005, three days each. Sensitivity identifies Framing, despite Hemming having
the greatest fault loss. The saved seed-3001 dataset completed 1,716 bodies at
38.133333 JPH and was committed before the later disk-space failure. The idealized
one-day no-loss case gave 59.6 JPH; startup explains the gap from 60. Raising source
opportunities from 65 to 90 JPH in the three-day release check left output at
45.8 JPH for both, supporting that admission rate is not imposing the target.

### Artifacts and persistence status

Reports are retained under `data/processed/stage3/`: `calibration.json`,
`calibrated-config.json`, `paired-comparison.json`, `baseline-sensitivity.json`,
`constraint-assessment.json`, `failure-rate-comparison.json`, `reference-cases.json`,
`exported-baseline.json`, and `persisted-baseline.json`. They are generated local
artifacts ignored by Git.

The validated 30-day export `data/raw/sim-30day-baseline-v1/` contains 21,126
admitted vehicles, 21,096 completions and 30 final WIP, with 147,736 completed
station operations, 222,115 state intervals, 1,017 faults, 373,589 source records,
and 4,698 evidence links. Source exports total approximately 188 MB. Its hash is
`23b496836dcc2d35a7922a5c6d2c75061212447ee7808f1964ba1019ab609394`.
An export-only replay independently passed result/history validation and reused
the existing manifest. The full-history process was observed at about 810 MB RAM.

**Initial storage incident (resolved).** The first 30-day load failed
with PostgreSQL `DiskFull` (SQLSTATE 53100) while inserting station-state records.
C: had only about 5 MB free; PostgreSQL then entered recovery and interrupted a
concurrent test. The loader uses one transaction. After the user freed space and
restarted the service, checks confirmed rollback and preserved datasets. The agent
did not delete project data or files to work around the failure. The CLI now reports
database errors without connection details, records commit as unconfirmed, and
returns a nonzero exit status.

Before that failure, the 13 integration tests passed. The later full-suite run
reported 61 passed, one failure and two errors during the storage/recovery event.
After the CLI diagnostic test was added, all 51 independent unit tests passed.
After recovery, the **full suite passed all 64 tests in 55.98 seconds**. Ruff,
compilation, Poetry and Alembic checks passed; the current revision is `0002`
with no schema differences.

The full baseline was then committed successfully and replayed: **`created: false`**,
identical hash, counts and stored values, with no duplicate records. A full replay
of the authored Stage 2 generator also returned `created: false`, confirming its
original values and hash unchanged. The Framing dataset retained its expected
hash; no temporary test schemas remained. All 373,589 exported source records
were independently parsed. At the final audit C: retained about 10.6 GB free.

These were the final database-test commands after recovery:

```powershell
$env:STAGE2_TEST_POSTGRES = '1'
poetry run pytest -q --tb=short
Remove-Item Env:STAGE2_TEST_POSTGRES
poetry run alembic check
```

If a report path contains an earlier failure record, choose a fresh report path;
report files are not silently replaced. The implementation plan and schedule are
unchanged. **Stage 3 and Stage 2 final acceptance are complete. Stage 4 is ready
to begin and remains Not Started.**

## File inventory

Created under `src/bottleneck_analyzer/simulation/`: `calendars.py`,
`calibration.py`, `cli.py`, `environment.py`, `events.py`, `failures.py`,
`metrics.py`, `persistence.py`, `reference_cases.py`, `scenarios.py`, and
`validation.py`. Implemented the existing `config.py`, `engine.py`, `station.py`,
`buffer.py`, and `vehicle.py` placeholders.

Created `alembic/versions/0002_equipment_fault_categories.py`,
`tests/unit/test_simulation.py`, `tests/integration/test_simulation_persistence.py`,
`tests/fixtures/simulation-framing.json`, and this technical document.

Modified shared files only where needed for simulation: `domain/manufacturing.py`
(equipment vocabulary), `db/models/production.py` (matching check constraint),
`data/generators/history.py` (shared history configuration/provenance interface),
`data/storage.py` (explicit validator/provenance support), and
`data/generators/cli.py` (export simulation provenance and referenced SOPs).
The one approved migration-test assertion now follows the actual Alembic head.
README, roadmap and status changes describe actual functionality and outcomes.
The Stage 2 data-model document now records closure of its cross-stage acceptance.

Dependency declarations and the original implementation plan are unchanged.
