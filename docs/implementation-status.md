# Implementation Status

## Project information

- **Project name:** Automotive Bottleneck Analyzer
- **Overall status:** In Progress
- **Current stage:** Stage 6 — Four-Agent Implementation and LangGraph Orchestration (Not Started — ready to begin)
- **Stage 2:** Implementation and Final Acceptance Completed
- **Stage 3:** Completed
- **Last updated:** 2026-11-08
- **Source of truth:** [`implementation-plan.md`](implementation-plan.md) and [`implementation-roadmap.md`](implementation-roadmap.md)

## Stage status

| Stage | Implementation status | Final acceptance / notes |
| --- | --- | --- |
| Stage 1 — Project Foundation and Configuration | Completed | Foundation implementation, local checks, authenticated PostgreSQL connectivity, and pgvector operation verification completed. |
| Stage 2 — Domain Models, Database Schema, and Synthetic Data Generation | Completed | Final acceptance closed: 30-day simulation dataset loaded/replayed, Framing case verified, authored fixture unchanged. |
| Stage 3 — Seven-Station SimPy Discrete-Event Simulation | Completed | Simulation, calibration, uncertainty, both interventions, persistence/replay and final 64-test suite verified. |
| Stage 4 — Historical Analytics and Bottleneck Candidate Identification | Completed | Read-only metrics, segmentation, source references, candidates, persisted reference comparisons and final 89-test suite passed. |
| Stage 5 — Knowledge Retrieval and Evidence Linking | Completed | Live semantic acceptance closed: 2,544 vectors, 17/17 live checks, source-fact preservation and final 125-test suite passed. |
| Stage 6 — Four-Agent Implementation and LangGraph Orchestration | Not Started | Ready to begin; Stages 1–5 are verified. |
| Stage 7 — API and Local User Interface | Not Started | Waiting for Stage 6. |
| Stage 8 — Testing, Validation, Documentation, and Presentation | Not Started | Waiting for the implemented vertical workflow. |

## Completed tasks

- Read the project `AGENTS.md`, `docs/implementation-plan.md`, and `docs/implementation-roadmap.md` before implementation.
- Audited the existing package, dependency configuration, environment template, SQLAlchemy session, Alembic environment, and starter tests.
- Extended typed settings for application/runtime values, production-rate references, LLM/embedding providers, and LangSmith configuration.
- Added foundational contracts for analysis scope, evidence references, scenario requests, investigation state, question intent, status, and evidence relationships.
- Added PostgreSQL-only database health inspection, pgvector availability reporting, and a FastAPI database-session dependency.
- Added `/health` and `/health/database` endpoints with startup/shutdown logging and tracing-disabled operation.
- Added isolated foundation tests for settings, health endpoints, missing database configuration, and shared contract validation.

Stages 1–5 are complete. Stage 3's verified simulation datasets close Stage 2 final
acceptance. Stage 6 is ready but has not been started. The execution records below
retain the earlier pending state and the final verification evidence.

## Pending tasks

### Stage 1 — Project Foundation and Configuration

- [x] Inspect and preserve the existing foundation behavior before changes.
- [x] Define foundational typed contracts for scope, evidence, scenarios, investigation state, and question/status enums.
- [x] Configure PostgreSQL/pgvector, LLM, embeddings, LangSmith, logging, production-rate, and runtime settings.
- [x] Confirm local startup, application liveness, and clear database health reporting with tracing disabled.
- [x] Add and run focused tests for foundation contracts and health endpoints.
- [x] Run and record available dependency, pytest, Ruff, import, and startup checks.
- [x] Verify PostgreSQL authentication and pgvector availability with valid project database credentials.

### Later stages

- [x] Implement domain models, PostgreSQL schema, migrations, and fixed-seed authored-data generation/loading.
- [x] Verify Stage 3's new simulation-derived dataset and Framing constraint case to close Stage 2 final acceptance.
- [x] Implement the seven-station SimPy simulation, buffers, faults, repairs, calendars, scenarios, and uncertainty.
- [x] Implement deterministic historical analytics and candidate identification.
- [x] Implement evidence ingestion, exact/lexical/vector retrieval, linking, and qualified cause assessment.
- [ ] Implement exactly four agents and controlled LangGraph workflows.
- [ ] Implement the read-only API and local web interface.
- [ ] Complete validation, documentation, packaging, presentation, and rehearsal.

## Validation commands and actual results

Commands below record the earlier Stage 1 checks. Current Stage 2 checks and
results are recorded in the execution record below.

| Command | Actual result |
| --- | --- |
| `poetry check` | Shell command unavailable (`poetry` is not on PATH); equivalent `\.venv\Scripts\python.exe -m poetry check` passed: `All set!`. |
| `poetry run pytest` | Poetry shell command unavailable; equivalent `\.venv\Scripts\python.exe -m pytest` passed: 8 tests passed. |
| `poetry run ruff check .` | Poetry shell command unavailable; equivalent `\.venv\Scripts\ruff.exe check .` passed: `All checks passed!`. |
| `\.venv\Scripts\python.exe -m pytest tests/unit/test_foundation.py` | Passed: 7 tests passed. |
| `\.venv\Scripts\python.exe -m pytest` | Passed: 8 tests passed, including the live PostgreSQL/pgvector integration test. |
| `\.venv\Scripts\ruff.exe check .` | Passed: no lint errors. |
| `\.venv\Scripts\python.exe -c "... import ..."` | Passed: all required Python imports loaded; application title and contract state were printed. |
| `\.venv\Scripts\python.exe -c "... TestClient(app) ..."` | Passed: `/health` returned HTTP 200 and `/health/database` returned HTTP 200 with `misconfigured` when `DATABASE_URL` was absent. |
| Configured PostgreSQL health check using local `.env` | Passed: `status=healthy`, `database_connected=true`, `pgvector_available=true`, and `vector_operations_available=true`. |
| Live SQLAlchemy pgvector operation | Passed: `SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector` returned distance `1.0`. |
| `poetry run alembic upgrade head` | Not run; the planned business schema is not implemented yet. |

Repository inspection was completed before implementation. Those inspection commands are not implementation validation results.

## Blockers and decisions

### Blockers

- None for Stage 1.
- None remaining for Stage 3 or Stage 2 final acceptance.
- None remaining for Stage 4. Model-exclusive machine states remain an explicit
  schema limitation, not fabricated measurements or a blocker to qualified analytics.
- None for Stage 5. The configured provider, live embeddings and 17 synthetic
  semantic/hybrid acceptance cases are verified; general real-plant relevance
  remains outside the scope of these checks.
- Resolved incident: PostgreSQL reported `DiskFull` (53100). The user freed disk space and restarted the stopped service. Database recovery, full dataset load/replay, authored-data preservation and final tests all passed afterward. The agent did not delete data/files to resolve the incident.

### Decisions

- Preserve the four-agent architecture exactly: Orchestrator/Planner, Data and Analytics, Knowledge and Root-Cause, and Simulation.
- Preserve PostgreSQL with pgvector, SQLAlchemy 2.x, Alembic, SimPy, LangGraph, FastAPI, LangSmith, Poetry, pytest, and Ruff.
- Keep the project as a modular monolith with synthetic, read-only source connectors.
- Keep database connectivity lazy: application liveness must work without a database, while database readiness reports missing configuration, connection failure, or missing pgvector explicitly.
- Use the configured local PostgreSQL database and existing pgvector installation; do not recreate the database or reinstall the extension.
- Use this file as the implementation progress record; update task and stage statuses only after the corresponding work has actually been implemented and verified.
- Do not mark a task or stage complete based on planned work, code inspection alone, or an unexecuted validation command.

## Stage 2 execution record — 2026-11-07

**Implementation status: Completed. Final acceptance was initially pending Stage 3
output and is now closed; see the final Stage 3 verification below.**

Read all four project documents and the attached request before changes. The
Stage 1 baseline passed all 8 tests. Existing settings, engine/session creation,
declarative base, logging, health endpoints, and pgvector installation were reused.
No dependencies were added or changed. No Git commit was made.

### Implemented and verified

- [x] Manufacturing enums and validated date/seed/volume/dataset configuration.
- [x] 21 typed SQLAlchemy table mappings with UUIDs, required columns, FKs,
  positive intervals, allowed categories/states, uniqueness, and useful indexes.
- [x] Dated shifts and explicit planned-break exclusions; durations computed
  from timestamps in PostgreSQL.
- [x] Original source IDs/fields/text, file provenance, explicit incident links,
  and separately labeled inferred evidence links.
- [x] SOP metadata/content/sections; generated full-text column and GIN index;
  nullable pgvector/model columns, with no fabricated embeddings.
- [x] Initial business migration generated, manually reviewed, safely applied,
  and tested in isolated schemas.
- [x] Fixed-seed authored event fixtures and source projections for all seven
  source systems, including missing notes, irrelevant notes, delayed/open and
  unlinked maintenance, and invalid/missing sensor values.
- [x] Transactional loading, per-dataset UUID namespace, advisory lock,
  idempotent replay, conflict rejection, counts and stored-value verification.
- [x] CSV/JSONL exports, original SOP text files, manifest, read-only source
  connectors, and explicit generation CLI.
- [x] Initial 30-day fixture generated, validated, loaded and replayed without
  duplicates.
- [x] Framing-focused evidence fixture with checked authored fault durations.
- [x] Unit/integration tests, migration consistency check, imports/compilation,
  Poetry configuration check, and Ruff.
- [x] Final shared history produced by the seven-station SimPy model.
- [x] Confirmed Framing-stronger-constraint expected result using line sensitivity.

### Schema and migration

Migration revision: **0001**, `alembic/versions/0001_initial_business_schema.py`.

Before migration, the existing target `bottleneck_analyzer` had no tables or
migration revisions. The role was confirmed as `bottleneck_app`; vector 0.8.7 was
already enabled. Upgrade created 21 business tables plus `alembic_version`; it
did not drop or overwrite tables, change credentials, recreate the database, or
install/alter the extension. `alembic check` reports no model/schema differences.

Entities and relationships are documented in
[`design/stage-2-data-model.md`](design/stage-2-data-model.md). Future simulation
configuration/run and investigation-audit tables are schema only and contain no
generated results or agent behavior.

### Initial dataset and counts

- Name: `stage2-30day-v1`.
- Generator version/provenance: `authored-fixture-v1` / `authored_fixture`.
- Seed: **42**.
- Period: **2026-09-01 00:00 UTC through 2026-10-01 00:00 UTC**, end exclusive.
- Calendar: 30 days, two eight-hour shifts/day, 30-minute planned break per shift.
- Requested volume: 345 vehicles/shift, alternating SUV/Sedan. This yields the
  illustrative 46 JPH reference by construction; it is not calibrated simulation output.
- Content hash: `cdea3a7b8470b6e0e2779f8bea6e539cdf73789862dd2ee646ca48919c2d41f1`.
- Manifest: `data/raw/stage2-30day-v1/manifest.json`.

| Entity | Persisted records |
| --- | ---: |
| Dataset | 1 |
| Station | 7 |
| Buffer | 6 |
| Vehicle model | 2 |
| Shift | 60 |
| Calendar exclusion | 60 |
| Vehicle | 20,700 |
| Production record | 144,900 |
| Station-state event | 2,520 |
| Fault event | 420 |
| Maintenance work order | 375 |
| Andon event | 280 |
| Shift handover note | 144 |
| Historian observation | 420 |
| SOP document | 7 |
| SOP section | 14 |
| Source record | 149,080 |
| Evidence link | 1,533 |
| Model configuration | 0 |
| Simulation run | 0 |
| Investigation audit | 0 |

Source breakdown: MES 144,900; SCADA 2,940; historian 420; CMMS 375; Andon 280;
shift notes 144; SOP documents/sections 21. Sensor qualities: 140 good, 140 bad,
140 missing. Evidence links: 1,449 direct and 84 inferred.

### Actual Stage 2 validation results

Commands were executed from the project root using the installed `.venv` Python
3.12 environment. The Poetry executable is not on PATH, but its module is available.

| Executed command or check | Actual result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m alembic history` before migration | No existing revisions. |
| SQLAlchemy inspection before migration | Correct database/role, no tables, vector 0.8.7 present. |
| `.\.venv\Scripts\python.exe -m alembic upgrade head` | Passed; applied initial revision 0001. |
| `.\.venv\Scripts\python.exe -m alembic current` | `0001 (head)`. |
| `.\.venv\Scripts\python.exe -m bottleneck_analyzer.data.generators.cli` | Passed; first load `created: true`, integrity checks and stored-value comparison succeeded. |
| Same generation command repeated | Passed; `created: false`, identical hash/counts, no duplicates. |
| `$env:STAGE2_TEST_POSTGRES='1'` then `.\.venv\Scripts\python.exe -m pytest -q` | **40 passed**, including all Stage 1 tests, pure generator tests, and opt-in migration/constraint/load tests. |
| `.\.venv\Scripts\python.exe -m alembic check` | Passed; no new upgrade operations detected. |
| `.\.venv\Scripts\python.exe -m poetry check` | Passed; `All set!`. |
| `.\.venv\Scripts\python.exe -m compileall -q src tests alembic` | Passed; no compilation errors. |
| Mapper/import check with `configure_mappers()` | Passed; 21 mapped tables. |
| `.\.venv\Scripts\ruff.exe check .` | Passed; all checks passed. |
| Read-only database audit after live tests | All seven sources present; expected sensor/link counts; zero `stage2_test_%` schemas remain. |

During development, checks found a break-boundary error in authored booking slots
and an Alembic version-table comparison issue; both were corrected before the
passing run. Replay also tests rejection of changed stored values. The old Stage 1
test assumption that metadata must stay empty was updated to check that engine
creation remains lazy after business models are registered; the original engine,
driver and session assertions remain.

Live write tests require explicit `STAGE2_TEST_POSTGRES=1`. They create uniquely
named schemas inside rollback-only transactions, apply the real migration there,
verify all business tables are in that schema, and verify cleanup. They do not
modify public development data. The role lacks CREATEDB privilege, so no test
database was created and no role/credential changes were attempted.

No separate type checker is configured. Compilation/import checks and executed
tests passed; no unexecuted type-check result is claimed.

### Limitations and next stage

The primary plan requires simulation-derived history. This task excludes Stage 3
simulation implementation, so the initial dataset is explicitly an authored
fixture. It verifies data integrity and ingestion, not finite-buffer propagation,
calibration, line causation, or scenario gains. The Framing fixture verifies higher
authored fault duration only; line-level constraint sensitivity is unverified.

**At the Stage 2 handoff, implementation was complete and final acceptance was
pending Stage 3 output. That acceptance has since been closed.**
The implementation and its 40-test verification record stand as completed work.
The original schedule is unchanged: Stages 2 and 3 share Day 1 hours 1–3.5.

The handoff is sequential:

1. Stage 3 consumes the completed Stage 2 contracts, schema, migration, and
   authored-data/source-loading pipeline. Its entry dependencies are satisfied.
2. Stage 3 builds the SimPy model and generates a new simulation-derived dataset
   under a fresh identity, preserving the authored fixture.
3. Validate/load the new dataset through the Stage 2 pipeline and verify the
   remaining simulation-derived history and Framing constraint acceptance evidence.
4. Record the actual results in this file and close Stage 2 final acceptance once
   those checks pass. Do not repeat or reopen completed implementation solely
   because the acceptance evidence arrived later.

At that earlier tracking correction, Stage 3 remained Not Started. The subsequent
Stage 3 implementation and verification are recorded below.

## Stage 3 execution record — 2026-11-08

**Status: Completed. The storage incident described below was resolved, and all
final acceptance checks passed.**

### Implemented

- [x] Typed synthetic processing/failure/calendar/release/mix/scenario parameters.
- [x] Seven SimPy station workers, six finite buffers and bounded source admission.
- [x] Model-specific positive processing distributions, actual blocking and starvation.
- [x] Operating-time failures, calendar-time serialized repairs, and remaining-work resumption.
- [x] Two-shift calendars, break/overnight pauses, exclusive state accounting and censored WIP.
- [x] Line/station metrics, queue/WIP integrals, model/shift/hour throughput and state conservation.
- [x] Separate indexed random streams, paired experiments, uncertainty and capacity sensitivity.
- [x] Both targeted interventions: repair duration ×0.70 and failure rate ×0.70 (MTBF ÷0.70).
- [x] Transparent calibration grid with independent evaluation seeds.
- [x] Simulation provenance, source projections, actual MES/fault evidence links, configuration/run storage and referenced SOP reuse.
- [x] Explicit CLI commands for baseline, replication, calibration, scenario, sensitivity, assessment, export and persistence.
- [x] Framing stress-case generation and measurement; reference dataset saved before the storage failure.
- [x] Full 30-day result/history validation and reproducible source export.
- [x] Independent unit tests, Ruff, compilation and Poetry configuration checks.
- [x] Commit and replay the 30-day simulation dataset after disk recovery.
- [x] Verify the authored fixture and committed Framing dataset after recovery.
- [x] Complete a clean full-suite run and final Alembic comparison.
- [x] Close Stage 3 and Stage 2 final acceptance after those checks pass.

### Compatibility changes and migration

Revision **0002** extends the equipment-category check constraint for mechanical,
electrical, sensor and other equipment faults. It was reviewed and applied to the
existing database without changing original rows, credentials or extensions.
The user approved updating only the pre-existing migration test's revision
assertion from a hardcoded `0001` to the actual Alembic head. Other existing tests
were retained. Stage 2's loader now takes an explicit validator and history
provenance, defaulting to its original authored behavior; simulation supplies its
own validator for partial WIP, cross-shift operations and physical repair intervals.
No dependencies were added and no Git commit was made.

### Calibration, uncertainty and constraint evidence

Five three-day calibration seeds **11–15** evaluated only the declared Hemming
robot mean-repair grid: 360, 480, 600 and 720 seconds. Mean JPH was respectively
51.284444, 49.244444, 47.160000 and 45.311111. The selected **720 seconds** met the
45–47 JPH calibration tolerance. All other assumptions stayed fixed. Calibration
is against the exercise's illustrative reference, not real plant data.

The independent **20 paired 30-day experiments**, seeds **1001–1020**, produced:

| Metric | Actual result |
| --- | --- |
| Baseline mean JPH | 46.255889 |
| Baseline standard deviation | 0.429603 |
| Baseline minimum–maximum | 45.306667–46.880000 |
| Baseline 95% mean interval | 46.054831–46.456947 |
| Scenario mean JPH | 49.609000 |
| Scenario standard deviation | 0.348899 |
| Scenario minimum–maximum | 48.748889–50.022222 |
| Scenario 95% mean interval | 49.445712–49.772288 |
| Paired mean gain JPH | 3.353111 |
| Paired gain 95% interval | 3.275210–3.431012 |
| Mean throughput improvement | 7.249% |
| Observed scheduled robot-fault loss reduction | 24.714% |

The 0.70 repair multiplier is exact for matching sampled repairs. Realized loss
reduction differs because exposure/event counts and censoring change with flow.
The 95% intervals use Student-t statistics across seeds, not model-error bounds.

Separate five-seed, three-day sensitivity experiments (**2001–2005**) identify
**Hemming before and after intervention; no constraint move was observed**. Its
10% processing speed-up gained 4.826667 JPH before intervention (95% interval
4.689556–4.963777) and 4.973333 afterward (4.616603–5.330064). Other tested stations
had zero gain in these experiments. All 20 long baseline runs also ranked Hemming
first observationally; the ranking alone is not treated as proof.

The separate failure-rate method completed **20 three-day pairs**, seeds
**4001–4020**: baseline 46.454444 JPH, scenario 49.637778, paired gain 3.183333
(95% interval 2.751442–3.615225). This shorter mechanism-validation experiment
does not replace the primary 30-day comparison.

The Framing fixture uses a declared 90-second mean Framing processing assumption.
Five three-day sensitivity seeds **3001–3005** identify Framing even though Hemming
has the largest fault loss. The saved seed-3001 case completed 1,716 vehicles at
38.133333 JPH. An idealized one-day line achieved 59.6 JPH versus the 60 JPH design
reference (startup included). Raising source opportunities from 65 to 90 JPH left
the three-day reference output at 45.8 JPH in both cases; releases do not force 46.

### Dataset generation and persistence

The **validated export** is `sim-30day-baseline-v1`, seed **1001**, simulation
version `simpy-line-v1`, 2026-09-01 through 2026-10-01 UTC, 50/50 stochastic mix,
450 scheduled production hours. The single retained run completed **21,096**
vehicles at **46.88 JPH**, from **21,126** admissions with **30** final WIP. This
single run is distinct from the 20-replication mean above.

| Entity | Generated and persisted records (verified after recovery) |
| --- | ---: |
| Station | 7 |
| Buffer | 6 |
| Vehicle model | 2 |
| Shift / calendar exclusion | 60 / 60 |
| Vehicle | 21,126 |
| Completed station production record | 147,736 |
| Station-state interval | 222,115 |
| Physical fault / historian observation | 1,017 / 1,017 |
| Maintenance work order | 762 |
| Andon event | 678 |
| Handover note | 264 |
| Source record | 373,589 |
| Evidence link | 4,698 |
| Model configuration / simulation run | 1 / 1 |

SOP content is referenced from `stage2-30day-v1`, not copied. The baseline export
hash is `23b496836dcc2d35a7922a5c6d2c75061212447ee7808f1964ba1019ab609394`.
CSV/JSONL exports plus manifest are in `data/raw/sim-30day-baseline-v1/` and total
approximately 188 MB. A second export-only run passed validation and reused that
manifest. The full-history process was observed at approximately 810 MB RAM.

The initial database load failed with SQLSTATE 53100 during station-event
insertion. Post-recovery checks confirmed rollback; the subsequent full load and
replay passed, as detailed in the final recovery evidence below.
The separately committed `sim-framing-validation-v1` case has 1,733 vehicle rows,
12,038 station operations, 20,672 states, 91 faults, 33,045 source records, and 421
links. Its hash was reverified after recovery. The authored fixture's original
hash and every generated stored value were also reverified unchanged.

### Actual checks

| Executed check | Actual result |
| --- | --- |
| Initial focused simulation tests | 17 passed. |
| Isolated integration suite before storage failure | 13 passed. |
| Expanded simulation tests before CLI error handling | 21 passed. |
| Full suite during disk/recovery event | 61 passed; one failure and two errors in database operations. Not a passing full-suite result. |
| Final independent unit suite (`pytest tests/unit -q --tb=short`) | 51 passed, including safe disk-full CLI reporting. |
| Ruff | Passed after final code changes. |
| Compilation (`compileall -q src tests alembic`) | Passed, exit 0. |
| Poetry module check | Passed, `All set!`. |
| Full suite after recovery | 64 passed in 55.98 seconds, exit 0. |
| Final Alembic/database comparison | Passed after recovery: no new upgrade operations, head 0002. |
| Original plan checksum | Matches the unchanged reference copy. |

Detailed commands, assumptions, report filenames and remaining limitations are in
[`design/stage-3-simulation.md`](design/stage-3-simulation.md). Reports and generated
data are ignored by Git. There is no separate type checker configured.

### Acceptance and handoff

Stage 3 and Stage 2 final acceptance are **Completed**. Stage 4 can safely begin
using the verified database and simulation interfaces, and remains **Not Started**.
No simulation results or reduced datasets were substituted for the failed load.

### Final recovery and acceptance evidence

The user freed C: to approximately 10.8 GB and restarted `postgresql-x64-17` after
Windows denied service-control access from the agent session. Read-only checks
then confirmed healthy PostgreSQL/pgvector, no committed partial baseline, no
orphaned test schemas, and unchanged authored/Framing hashes. The failed load had
rolled back. No credentials, extensions, database identities or original records
were replaced.

The full 30-day load was retried and **committed successfully**. An identical
second run returned **`created: false`** after checking counts and every generated
stored value; its fingerprint remained
`23b496836dcc2d35a7922a5c6d2c75061212447ee7808f1964ba1019ab609394`.
The original Stage 2 generator was also replayed: it returned **`created: false`**
after full stored-value verification, retaining original hash
`cdea3a7b8470b6e0e2779f8bea6e539cdf73789862dd2ee646ca48919c2d41f1`.
All CSV/JSONL source exports were parsed successfully (373,589 source records;
SOP content remains referenced).

Final executed checks:

- **Full pytest suite: 64 passed in 55.98 seconds**, exit 0, with
  `STAGE2_TEST_POSTGRES=1` and `--tb=short`. This supersedes the interrupted run.
- **Ruff: passed. Compilation: passed (exit 0). Poetry check: passed.**
- **Alembic check: passed**, no new upgrade operations; **current revision: 0002**.
- **Database audit: passed** for all three dataset hashes and exact baseline
  persisted counts, including 21,126 vehicles, 147,736 operations, 222,115 states,
  1,017 faults and 373,589 source records.
- **Temporary test schemas: zero** after the final suite; original fixture and
  committed Framing dataset remain present with their expected hashes.
- C: retained approximately **10.6 GB free** at the final audit.

`data/processed/stage3/persisted-baseline.json` records the successful load.
The immutable report retains its initial `created: true`; the verified replay
reported `created: false` in the terminal without replacing the report. Technical
assumptions and limitations remain documented; calibration is not plant validation.

## Stage 4 execution record — 2026-11-08

**Status: Completed. Stage 5 is ready to begin and remains Not Started.**

Read the attached Stage 4 request, AGENTS, original plan, roadmap, this status
record, Stage 2/3 technical documents and README. Inspected actual schemas,
configuration/session creation, generator/storage, simulation projection and
source fields, existing tests, indexes, saved reports and all three persisted
datasets before implementation. The analytics package previously contained only
its initializer. No unrelated code was rewritten.

### Implemented and verified

- [x] Dataset-explicit typed scope/result contracts reusing shared scope/evidence types.
- [x] Repeatable-read, PostgreSQL-enforced read-only public analysis interface.
- [x] Bound, explicitly dataset-filtered aggregate queries; no raw-export loading or N+1 loop.
- [x] Unioned shift calendars, explicit break subtraction, aware periods and UTC-hour handling.
- [x] Admissions/completions, initial/final and average/max WIP, flow time, JPH and design gap.
- [x] Station operations, active service, elapsed duration, exclusive states, coverage and queue metrics.
- [x] Dated shifts, model JPH contributions, UTC-hour groups, partial/closed-period behavior.
- [x] Transparent candidate scoring, individual indicators, support/conflicts and evidence strength.
- [x] Sample/coverage thresholds, abstention, segment changes and dated-shift persistence counts.
- [x] Aggregate references and bounded real source UUID/system/source-ID samples.
- [x] Separately labeled persisted simulation reference and configuration-checked optional assessment.
- [x] CLI, opt-in PostgreSQL tests, baseline/Framing comparison and documentation.

### Actual results

`sim-30day-baseline-v1` remains simulation-derived with its original UUID/hash:
21,126 admissions, 21,096 completions, 30 final WIP and 450 scheduled hours give
**46.88 JPH**, **13.12 JPH design gap**, and **5,904 design-gap bodies**. This gap
is not station-specific recoverable output. SUV/Sedan completions are
10,461/10,635, contributing 23.246667/23.633333 JPH. Mean flow time is
3,771.414151 seconds and average WIP is 30.922847.

**Hemming** is the overall historical leader and leads all 60 dated shifts.
The two model proxy rankings lead with **Framing**, explicitly qualified because
the schema cannot assign shared machine states exclusively to SUV/Sedan. They
are not proof of model-specific line constraints. There are 24 pooled UTC-hour
groups, with null JPH and no asserted leader in closed hours.

Counts, scheduled hours, flow/WIP, station operations/state durations/queue
integrals, individual dated shifts and UTC-hour buckets match the independently
stored Stage 3 simulation metrics. The 46.88 retained single-run JPH is correctly
distinct from the 46.255889 mean of 20 independent replications. Matching saved
sensitivity evidence remains separate from observational scores.

The existing `sim-framing-validation-v1` gives **1,716 completions**, **38.133333 JPH**
and **Framing** first, although Hemming has the greatest faulted time. No simulation
assumptions were changed and no long simulation experiment was rerun.

### Validation commands and actual results

Commands used the existing Python 3.12 `.venv` from the project root.

| Executed command/check | Actual result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_analytics.py -q --tb=short` | **18 passed in 0.78 seconds**. |
| `STAGE2_TEST_POSTGRES=1`, then `python -m pytest tests/integration/test_analytics.py -q --tb=short -x` | **7 passed in 85.11 seconds**. |
| `STAGE2_TEST_POSTGRES=1`, then `python -m pytest -q --tb=short` | First full run **89 passed in 122.52 seconds**. |
| Same full suite after final numeric/order and per-shift/hour assertions | **89 passed in 121.90 seconds**, exit 0. |
| `.\.venv\Scripts\ruff.exe check .` | **Passed**, all checks passed. |
| `.\.venv\Scripts\python.exe -m compileall -q src tests alembic` | **Passed**, exit 0. |
| `.\.venv\Scripts\python.exe -m poetry check` | **Passed**, `All set!`. |
| `.\.venv\Scripts\python.exe -m alembic check` | **Passed**, no new upgrade operations detected. |
| `.\.venv\Scripts\python.exe -m alembic current` | **0002 (head)**, unchanged. |
| Full baseline CLI with matching comparison/assessment artifacts | Passed; 21,096 completions, 450 hours, 46.88 JPH, Hemming, 86 segments. |
| Query audit / measured full analysis | **15 statements**, SELECT/WITH/SET only; **33.326 seconds** while another test run was active. |
| Post-suite read-only dataset audit | All three provenance labels/hashes unchanged; baseline counts 21,126 vehicles, 147,736 operations, 222,115 states, 373,589 sources. |
| Post-suite temporary-schema audit | **Zero** `stage2_test_%` schemas remain. |
| Original implementation-plan checksum | Still `AA250999107FDBFDC56F88DD6E91AC3DBCAAD41E01B46BB634EF71A9B7A6AD1D`. |

The full-suite PowerShell sequence is:

```powershell
$env:STAGE2_TEST_POSTGRES = '1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:STAGE2_TEST_POSTGRES
```

Early development checks exposed a slow interval nested loop, session-timezone
dependence, and one-microsecond queue-max artifacts. These were corrected with
materialized UTC-hour slices, transaction-local UTC, and a declared two-microsecond
maximum-resolution threshold. Final passing results above supersede failed or
cancelled exploratory checks. No separate type checker or peak-memory benchmark
is claimed. The measured structured report was approximately 3.3 MiB; raw histories
remain in PostgreSQL.

### Files and decisions

Created six analytics modules: `contracts.py`, `calendar.py`, `repository.py`,
`candidates.py`, `service.py`, `cli.py`; two analytics test modules; and
`docs/design/stage-4-analytics.md`. Updated README, roadmap and this status file.
Local JSON reports under `data/processed/stage4/` are ignored by Git.

No dependencies, migration, existing tests, shared domain contracts, simulation
code, generators, database credentials, extension, or persisted datasets were
changed. Temporary test fixtures exist only in rollback-only isolated schemas.
No Git commit was created. No Stage 5–8 behavior was implemented.

### Limits and handoff

No blockers remain for Stage 4 acceptance. Scores are documented heuristics, not
probabilities or proof of real-plant constraints. Model-exclusive state attribution
is unsupported and null; model evidence is capped at moderate. Closed periods
have no JPH, missing/overlapping states are explicit, and completed-visit means can
have censoring/boundary bias. The design gap remains separate from simulated
recoverable gain. Stage 5 may use the structured candidate scopes and source IDs
for evidence retrieval; it has not been started.

## Stage 5 execution record — 2026-11-08

This initial implementation record preceded live semantic acceptance. The latter
was pending at this point and is closed in the follow-up record below.

**Status: Completed for implementation and local acceptance. Stage 6 remains
Not Started and is ready to begin.**

Inspected the attached request, AGENTS, original plan/roadmap/status, Stage 2–4
technical documents, actual mappings/indexes/source projections/links, typed
analytics contracts, settings, test fixtures and the three existing datasets.
The retrieval package previously had only an initializer. Official OpenAI
documentation was checked for the optional real embedding adapter.

### Implemented and verified

- [x] Explicit dataset/station/aware-period request, bounded results and validated exact UUIDs.
- [x] Read-only snapshot interface, fixed bound SQL, dataset/station/time/system/shift/hour filters.
- [x] Exact incident/work-order/source resolution before FTS/vector searches; FKs work without graph rows.
- [x] PostgreSQL English full-text search through the existing generated vector and GIN index.
- [x] Actual pgvector cosine search with model identity and dimension guards, verified with isolated numeric fixtures.
- [x] Missing vectors/configuration/provider failures preserve exact/lexical results and disclose unavailable semantics.
- [x] Exact-priority rank fusion and identity-based deduplication preserving every matching method and original link type.
- [x] Original source text/JSON/IDs/path/timestamp/station/incident/version metadata and explicit rendering basis.
- [x] Whole short records, existing SOP sections and stable virtual fallback chunks; no duplicated source rows.
- [x] Explicit null-only vector enrichment with validated metadata, replay skipping and atomic failure behavior.
- [x] One-way Stage 4 adapter, candidate indicator/source references and scope validation; no recalculation.
- [x] Four qualified assessment labels, abstention, visible contradictions, bad-sensor exclusions and untrusted-text handling.
- [x] CLI, unit/integration tests, full regression, technical documentation and preservation audits.

### Actual baseline verification

The live Stage 4-to-Stage 5 check selected `sim-30day-baseline-v1` and Hemming.
Analytics remained **46.88 JPH**, **Hemming** leading. Retrieval fetched **6 exact**
and **60 bounded lexical** matches, returned **20** records and disclosed truncation.
Source systems included Andon, CMMS, SCADA and historian. With the copied candidate
fault-occupancy indicator and linked incident records, the assessment was a
qualified **supported_hypothesis** about equipment interruptions. It did not claim
a recorded component cause, line-level causal loss or recoverable throughput gain.

Measured retrieval (excluding analytics) took **1.936 seconds**, with **16 SQL
statements including savepoint control** during another test run. Statements were
SELECT/WITH/SET/SAVEPOINT/RELEASE only. The initial linked report was 43,680 bytes
before the final original-text provenance fields were added. These are measured
observations, not guarantees. Local reports/audits are under `data/processed/stage5/`.

Actual development embedding provider/model/key remain unconfigured and all
stored embedding/model pairs remain null. Semantic retrieval correctly reports
unavailability. The OpenAI HTTP contract was tested offline and real pgvector
storage/search in rollback-only schemas used explicitly synthetic numeric geometry
fixtures; no live external API call or semantic-quality evaluation is claimed.
The documented configurable setup is OpenAI `text-embedding-3-small`, 1,536 dimensions.

### Validation commands and actual results

| Executed command/check using existing `.venv` | Actual result |
| --- | --- |
| `python -m pytest tests/unit/test_retrieval.py -q --tb=short` | **24 passed in 0.13 seconds**. |
| `STAGE2_TEST_POSTGRES=1`, then `python -m pytest tests/integration/test_retrieval.py -q --tb=short -x` | **10 passed in 13.45 seconds**. |
| Final focused retrieval unit + integration suite | **34 passed in 13.67 seconds**. |
| Final complete suite, `STAGE2_TEST_POSTGRES=1`, `python -m pytest -q --tb=short` | **123 passed in 103.47 seconds**, exit 0. |
| `ruff check .` | **Passed**, all checks passed. |
| `python -m compileall -q src tests alembic` | **Passed**, exit 0. |
| `python -m poetry check` | **Passed**, `All set!`. |
| `python -m alembic check` | **Passed**, no new upgrade operations detected. |
| `python -m alembic current` | **0002 (head)**, unchanged; no migration created. |
| Live read-only analytics-to-retrieval check | **Passed**, baseline metrics unchanged and qualified linked evidence returned. |
| Public-table preservation audit | All **21 tables** matched row counts/content digests; source-record count **555,714** unchanged. |
| Saved Stage 3 reports audit | Every saved JSON report SHA-256 matched before/after verification. |
| Post-suite embedding/schema audit | **0** populated embedding/model pairs; **0** leftover `stage2_test_%` schemas. |
| Original plan checksum and protected-code diff | Plan checksum unchanged (`AA250999107FDBFDC56F88DD6E91AC3DBCAAD41E01B46BB634EF71A9B7A6AD1D`); analytics, simulation, data, DB/domain, migrations and dependency files unchanged. |

The PowerShell full-suite sequence was:

```powershell
$env:STAGE2_TEST_POSTGRES = '1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:STAGE2_TEST_POSTGRES
```

Early checks found an untyped nullable SQL parameter and a blank-section fallback
edge case; both were fixed before final verification. Failed exploratory outputs
are superseded by the passing results above. No type checker is configured.

### Files, configuration and safety

Created eight modules under `retrieval/`: `contracts.py`, `repository.py`,
`chunking.py`, `embeddings.py`, `indexing.py`, `evidence.py`, `service.py`, `cli.py`;
`tests/unit/test_retrieval.py`, `tests/integration/test_retrieval.py`; and
`docs/design/stage-5-retrieval.md`. Modified only typed embedding settings in
`core/config.py`, `.env.example`, README, roadmap and this status record.

No files were deleted. No dependencies or migrations were added. The actual `.env`,
credentials, database/extension, existing datasets, source fields, simulation
assumptions, Stage 4 contracts/calculations and prior tests were preserved.
Embedding enrichment ran only in isolated rollback-only schemas. No Git commit
was created and no Stage 6 agent, workflow, business API or UI was implemented.

### Limits and handoff

No Stage 5 implementation/local-acceptance blocker remains. Live embedding API
behavior and retrieval quality remain unverified without external configuration;
current development semantic retrieval is unavailable rather than simulated.
SOPs owned by the authored dataset need an explicit request for that dataset;
baseline retrieval does not silently cross that boundary. Graph expansion is
bounded/one-hop, fallback scores are source-level, and shared evidence has no
model-exclusive attribution. Evidence labels are conservative deterministic
assessments; text is never causal proof or an instruction to act.

Stage 6 can consume validated analytics, simulation and retrieval interfaces.
Its exactly-four-agent orchestration remains **Not Started**.

## Stage 5 live semantic acceptance follow-up — 2026-11-08

**Status: Completed, including live provider/indexing/relevance acceptance.**

The user configured `.env`, successfully tested `text-embedding-3-small` at 1,536
dimensions, and indexed 20 Hemming records. They then explicitly authorized
completion of the remaining indexing, quality tests, regression checks and tracking.
This authorization permits derived embedding enrichment while preserving source
facts; it does not permit changing production history or starting Stage 6.

### Live indexing and preservation

| Dataset | Eligible/populated text records | Existing / newly indexed |
| --- | ---: | ---: |
| `sim-30day-baseline-v1` | 1,644 | 20 / 1,624 |
| `sim-framing-validation-v1` | 147 | 0 / 147 |
| `stage2-30day-v1` | 753, including 14 SOP sections | 0 / 753 |
| Total | **2,544** | **20 / 2,524** |

All three datasets have embeddings for relevant text across all seven stations.
The identity is `openai:text-embedding-3-small:1536:source-v1`; every populated vector
has dimension 1,536. Empty/structured source rows, stationless irrelevant notes and
sectioned SOP parents were not embedded. This avoids vectorizing hundreds of
thousands of numerical production/state rows that have no searchable prose.

Batching/caching reused genuine embeddings of identical text under the same model.
Only **22 new texts in 7 provider requests** were needed to enrich the 2,524 rows.
Compatible existing vectors were preserved. Indexing uses batches of at most 50
rows, with no dataset recreation, source duplication or automatic startup work.
A live replay skipped 50/50 indexed sources, generated 0 vectors and made **0 API requests**.

The index runner's before/after audit matched row counts and source-fact content
digests for all 21 business tables, excluding only the two explicitly authorized
derived fields. Original source IDs/text/JSON, paths, timestamps, relationships,
production records, simulation runs/configuration and all dataset hashes remain
unchanged. Saved Stage 3 JSON report SHA-256 values also match.

The first sandboxed request failed before its first batch committed. Retrying with
network access succeeded. The completed run is `live-index-v2.json`; its elapsed
time was **86.60 seconds**, including the two full source-fact audits. The failed
attempt is not counted as successful indexing evidence. No credential was printed
or placed in documentation.

### Relevance measurement and cutoff

The original 0.4 maximum cosine distance required similarity ≥0.6. Eight labeled
calibration probes found legitimate broad repair at **0.5363**, electrical repair
at **0.5889**, and SOP approval at **0.5982**; those were being excluded. Unrelated
food/travel probes scored only **0.0473/0.0060**. Based on that separation, the
default maximum distance is now **0.5** (minimum similarity 0.5).

A separate held-out fixture and boundary/hybrid checks passed **17/17** live cases:

- Robot repair paraphrase **0.6428** and electrical paraphrase **0.5399** return
  records with the expected fault categories.
- Framing-dataset retrieval returns the correct independent dataset/station.
- SOP reporting **0.7307** and approval **0.5804** return the expected section
  numbers with document IDs/versions.
- Two held-out unrelated recipe/currency questions return zero records.
- Every baseline station is explicitly tested and returns only its own records.
- The user's original broad repair question now returns relevant records (**0.5363**).
- Hybrid lookup preserves direct exact priority and deduplicates the same source
  across exact/lexical/semantic methods while retaining all methods.
- End-exclusive source-time filtering and foreign-dataset identifier rejection pass.

The 17 cases used **2 provider requests** through the operation-local cache and
took **21.19 seconds**. These are bounded synthetic acceptance examples, not proof
of general retrieval accuracy or plant causation. Query/source text remains
untrusted, and the existing conservative evidence assessments remain in force.

### Compatibility fixes and tests

The source replay verifier previously compared nullable embedding fields as if
they were original source facts. Real enrichment would therefore break normal
dataset replay. It now excludes only `embedding`/`embedding_model` from source-fact
comparison, retaining strict comparison of every other generated field. A new
integration test proves that enriched replay succeeds and changed original text
still fails. No prior tests were weakened or removed.

Indexing now batches unique texts before updates; `CachedEmbedder` provides bounded
operation-local reuse of real vectors for one identity. All generation/validation,
including fallback pooling, completes before the atomic update savepoint.

| Executed validation | Actual result |
| --- | --- |
| Focused retrieval unit/integration tests, opt-in PostgreSQL | **36 passed in 17.55 seconds** (25 unit, 11 integration). |
| Live `stage5_acceptance.py index` | **Passed**, 2,524 new / 2,544 total vectors; preservation audit passed. |
| Live `stage5_acceptance.py probe --cutoff 2` | **Passed**, eight labeled distance probes recorded; cutoff 2 used only for measurement. |
| Live `stage5_acceptance.py validate` | **17/17 passed**, exit 0. |
| Live 50-source indexing replay | **0 indexed, 50 skipped, 0 provider requests**. |
| Full pytest suite with `STAGE2_TEST_POSTGRES=1` | **125 passed in 140.14 seconds**, exit 0. |
| Ruff | **Passed**, all checks passed. |
| Compilation, `compileall -q src tests alembic scripts` | **Passed**, exit 0. |
| Poetry module check | **Passed**, `All set!`. |
| Alembic consistency/current | **Passed**, no new upgrade operations; **0002 (head)**. |
| Post-enrichment Stage 4 baseline analysis | **46.88 JPH**, 21,096 completions, 450 scheduled hours, Hemming leading, unchanged. |
| Final database audit | All three dataset hashes unchanged; **0** leftover test schemas. |

### Files and artifacts

Created `scripts/stage5_acceptance.py` for explicit resumable enrichment,
calibration and acceptance; `tests/fixtures/live-retrieval-quality.json` for
held-out examples. Updated retrieval batching/cache/default cutoff and tests,
`data/storage.py` replay compatibility, README, Stage 2/5 technical documents,
roadmap and this status record. No migration, dependency, simulation, analytics,
domain contract, agent, API or UI change was made.

Ignored artifacts under `data/processed/stage5/` include `live-index-v2.json` and
its before audit, `live-calibration-v1.json`, `live-validation-v1.json`, and
`live-post-index-analytics.json`. Reports require fresh paths. Original plan,
four-agent architecture and two-day schedule remain unchanged. No Git commit
was created. Stage 5 live acceptance is now closed; **Stage 6 remains Not Started**.
