# Stage 7 — Read-only API and local interface

Stage 7 adds HTTP transport and presentation around the existing
`InvestigationWorkflow(engine, ...).run(InvestigationRequest)` interface. Exactly
four agents and the existing LangGraph remain unchanged. There is no migration,
new dependency, alternate analytics/retrieval/simulation implementation, or queue
service. This stage occupies the original Day 1 hours 7–8 block; Stage 8 remains
Not Started. Execution results are recorded in `docs/implementation-status.md`.

## Start locally

From the repository root, with the existing `.env` and Poetry environment:

```powershell
poetry run python -m bottleneck_analyzer.api.cli
```

Equivalent with the installed Windows environment:

```powershell
.\.venv\Scripts\python.exe -m bottleneck_analyzer.api.cli
```

Open `http://127.0.0.1:8000/`. The supported launcher reads `APP_HOST`/`APP_PORT`,
requires a loopback host, rejects reload, uses one Uvicorn worker and disables
proxy-header trust. Do not launch with multiple workers or reload: admission and
worker registration are process-local. An accepted full simulation can take
several minutes; normal shutdown drains accepted work before disposing the engine.
Thread cancellation is not used to pretend that running work stopped.

The UI and liveness start without PostgreSQL or model access. Database-dependent
requests report actual availability. There are no provider calls at startup.

## HTTP contracts

The later chat refinement described below supersedes the initial dashboard
presentation and archived-history UI. Existing HTTP endpoints and admission
semantics are retained.

All business routes return JSON. Errors have `error.code` and a sanitized
`error.message`, sometimes with reconciliation guidance. Validation errors expose
field locations without echoing rejected values.

| Method and route | Contract |
| --- | --- |
| `GET /health` | Existing liveness, independent of PostgreSQL. |
| `GET /health/database` | Existing database/vector checks and HTTP 200 semantics; raw failure detail is sanitized. |
| `GET /api/datasets` | Actual dataset ID/name/provenance/period; `limit` 1–50, `offset` 0–10,000. |
| `GET /api/datasets/{uuid}/options` | Actual station/model/dated-shift options; up to 1,000 dated shifts with a conservative truncation indicator; supported methods and configured execution bounds. |
| `POST /api/investigations` | Existing Stage 6 `InvestigationRequest`, plus required UUID `X-Submission-Key`; 202 only after initial audit commitment and admission. |
| `GET /api/submissions/{uuid}` | Bounded process-local submission reconciliation, never a durable queue. |
| `GET /api/investigations` | Saved audit identity/question/creation time; same bounded pagination. |
| `GET /api/investigations/{uuid}` | Persisted status/events, confirmed-final flag and separately labeled process-local execution information. |
| `GET /api/investigations/{uuid}/result` | Bounded public result, 202 while registered execution is active, 409 when finalization is unconfirmed. |
| `GET /`, `/static/...` | Local HTML/CSS/JavaScript assets only; repository root and `.env` are not mounted. |

Example submission (the user action starts real provider/simulation work when
configured; this is documentation, not an acceptance command to run implicitly):

```json
{
  "question": "Which station is the strongest historical bottleneck candidate?",
    "scope": {"dataset": "sim-30day-baseline-v1"}
}
```

The response contains the actual investigation UUID, submission UUID,
`status_url` and `result_url`. An explicit scenario uses the unchanged Stage 6
`scenario.request` structure with a real target station, `repair_duration` or
`failure_rate`, and a reduction percentage. The simulation configuration requires
the percentage to be strictly below 100. Leaving the scenario controls off lets
the existing planner interpret the question and ask for clarification as needed.
Filtered histories are not silently converted into equivalent full-line scenarios.

HTTP status and workflow outcome are separate. GET returns 200 for a confirmed
result with **any** Stage 6 outcome: `completed`, `incomplete`,
`clarification_required`, `unsupported`, or `failed`. Only `completed` means the
workflow completed successfully. An HTTP 200 does not turn a failed investigation
into success. Transport errors use 422 invalid input, 404 absent resource, 409
conflict/unconfirmed execution, 429 occupied slot, 503 unavailable infrastructure
or admission, and sanitized 500 for unexpected defects. Busy/unavailable responses
can include `Retry-After`; the frontend never automatically retries a POST.

## Admission and audit lifecycle

1. Validate the request and reserve one execution slot. There is no pending-job
   queue. Repeating the same submission key/body reuses its existing admission;
   a different body with that key returns 409.
2. Create a fresh workflow with an observing `AuditWriter` adapter. Stage 6
   resolves scope and allocates the investigation UUID itself.
3. The adapter calls the unchanged `PostgresAudit.create()`. Its `engine.begin()`
   transaction must exit successfully before the adapter publishes a confirmed ID.
4. Only after that return does the adapter wait at an in-memory gate. **No database
   transaction is held while waiting for HTTP admission.**
5. The HTTP handler and worker arbitrate admission under the submission lock.
   Acceptance before the deadline opens the graph gate and permits HTTP 202.
6. Timeout, disconnect, cancellation or shutdown before acceptance closes the
   gate. If a blocked creation later commits, its initial audit is retained but
   the graph does not run. The slot stays occupied until the worker actually exits.
7. If acceptance won before a disconnect, work may continue without the caller
   receiving its response. Reconcile the submission key; do not blindly resubmit.
8. An exception from create may mean uncertain commit. Never execute the graph
   after that exception. Reconciliation makes a SELECT using the candidate UUID;
   only an observed row establishes the committed ID. Failure to observe a row
   does not claim that an uncertain transaction could never commit later.

Admission defaults to 10 seconds (`API_ADMISSION_TIMEOUT_SECONDS`). Body size
defaults to 32 KiB (`API_MAXIMUM_BODY_BYTES`). At most 100 submission mappings are
retained by default (`API_SUBMISSION_HISTORY_LIMIT`); old entries can be evicted
after execution ends. Eviction and restart end submission-key deduplication.
The browser retains only identifiers and never automatically repeats submission.

The database audit is the only durable investigation store. It has creation time,
route, JSONB state and final answer; no updated-at or node-start fields exist.
Events are persisted **after** each node, including duration/status/category.
Planner, analytics, knowledge, simulation, validation and compose are workflow
components; validation and compose are not new agents. The API exposes only saved
events, with no percentage, guessed active agent, or synthetic update timestamp.

A compose checkpoint can precede final audit confirmation. The API requires the
persisted response's `investigation_id` and `audit_id` to match the audit row's ID.
Result projection then validates the Stage 6 response. A final-save failure is
unconfirmed, even if the preceding checkpoint says completed. After restart,
nonfinal records without a registered worker remain unconfirmed; the application
does not assert that an external CLI worker has stopped or automatically resume it.

## Public projection and UI

`schemas.py` copies computed values rather than recalculating them. It separates
historical metrics/segments, source evidence and qualified assessments,
simulation statistics/sensitivity, and interpretation. The SQL projection removes
large per-run simulation arrays and full configuration copies before transfer.
Original audit content remains unchanged. Public passages are limited to 8,000
characters, other text/list lengths are bounded, and total results are limited
to 512 KiB. Truncation is disclosed; an oversized/invalid projection reports
unavailability instead of returning a falsely complete response.

Evidence retains dataset/provenance, original source identifiers, timestamp,
station, incident/work-order references, document/section/version metadata,
direct/inferred relationship and basis, links, scores and warnings. Raw metadata,
original file paths, embeddings and internal workflow state are excluded. Selected
verbatim excerpts, support/conflicts and unresolved questions remain inspectable.

The approved chat refinement replaces category/filter forms and recent-history
tables with a single current conversation, dataset/UTC-period selectors and a
visible composer. Station/model/shift/scenario details are expressed in the
question. Each answer has a collapsed View evidence section. Historical JPH,
retrieved source text, qualified interpretation and simulated predictions remain
distinct there. Simulation retains confidence intervals, seeds, horizon,
configuration, intervention, realized downtime, sensitivity and limitations.
Clarification is answered as a new message. Human review remains explicit.

Saved results provide a labeled fallback during model-service outages. Database
unavailability remains an error; no stale output is presented as a fresh execution.

## Local boundaries

All UI/business/docs/static routes validate the Host authority against the
configured port and `localhost`, `127.0.0.1` or `::1`. An Origin, when present,
must exactly match the HTTP Host origin; unexpected, duplicate and null origins
are rejected. Cross-site fetches and preflights are rejected. No permissive CORS
middleware is installed. JSON terminal clients without Origin remain supported.
The original two infrastructure-health probes retain Host compatibility; their
errors are sanitized and the supported server still binds only to loopback.

Source/model text enters DOM `textContent`, never HTML/markdown interpretation.
Responses set a restrictive same-origin CSP, no framing, no sniffing, no-referrer
and no-store. API errors omit raw rejected values, SQL/provider responses,
credentials and stack traces. There is no new authentication infrastructure and
no operational-control, approval, source-edit or work-order endpoint. This is a
single-user local prototype, not a remotely deployable multi-user security design.

## Verification and browser acceptance

```powershell
$env:STAGE2_TEST_POSTGRES='1'
$env:STAGE7_TEST_SAVED_BROWSER='1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:STAGE2_TEST_POSTGRES
Remove-Item Env:STAGE7_TEST_SAVED_BROWSER
node --test tests/ui/client.test.mjs
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m compileall -q src tests alembic scripts
.\.venv\Scripts\python.exe -m poetry check
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m alembic current
```

Ordinary tests use fixtures rather than paid models. Database writes use the
existing isolated-schema outer rollback. The new transaction test exercises real
PostgreSQL SAVEPOINT release through `PostgresAudit`; it does not misrepresent
that release as an independent durable commit. Deterministic delegate/gate tests
cover initial commitment, late commitment, uncertainty, timeout/disconnect races,
deduplication, final-save failure, slot ownership and draining shutdown.

Existing Edge headless tooling runs real DOM journeys against controlled HTTP
fixtures. No Playwright, driver, framework or npm package was installed. These
journeys cover question groups, outcomes, evidence expansion, safe rendering and
refresh without duplicate submission. A separate opt-in browser check reads the
actual existing combined audit through FastAPI with zero POSTs. This is saved-result
acceptance, not a claim of a new live combined investigation. Edge required execution
outside the tool sandbox on this machine; missing Edge is an explicit test skip.

If automated browser tooling is unavailable, manually verify: select dataset,
submit a permitted question once, observe saved checkpoints, refresh/reconnect
without a second submission, inspect evidence/source/version/relationship, compare
historical and modeled figures/intervals, exercise clarification and unavailable
services, and open a labeled saved result. Record these as manual results only
when actually performed. No unperformed manual acceptance is claimed.

`scripts/stage7_acceptance.py --before <snapshot.json> --saved-audit <uuid>
--report <fresh-path.json>` performs read-only exact table/report/protected-file
preservation and saved API acceptance. It never reseeds, reindexes, invokes an LLM,
reruns production simulation or updates an existing audit. Full executed results,
including any failures corrected during development, belong in the status record.

## UI refinement and stylesheet correction

The original Windows MIME lookup returned `application/x-css` for `.css` files.
Although `/static/styles.css` returned HTTP 200, Edge rejected it under strict
MIME checking with `nosniff`. The link and selectors were correct. `main.py` now
explicitly registers `.css` as `text/css` before mounting the existing static
directory. CSP, `nosniff`, asset paths and all API contracts remain unchanged.
The previous browser checks proved content/interactions, not applied styles;
the fixture server also supplied its own CSS MIME type and masked this error.

The native interface now uses a light industrial dashboard with navy text,
restrained blue accents, white panels, consistent controls and responsive layout.
The form includes category buttons, an editable default question, collapsed scope
and scenario controls, and an obvious Run investigation action. The progress panel
shows only saved events and outcomes, with a copyable investigation ID. It never
guesses a running agent or percentage.

Results are organized as executive summary, historical metrics, observational
bottleneck findings, expandable source evidence, modeled simulation results, and
interpretation/review. The first answer paragraph is shown as the summary and the
complete original answer remains available in a disclosure. Structured fields
use labeled facts, lists and tables rather than raw JSON. Numeric display rounds
to at most three decimal places for readability; original precision is retained
in numeric elements' titles/data attributes. No metric or rank is calculated.
Historical throughput, design gap and modeled gain remain separate.

The current public response lacks a complete historical station ranking and an
independent design-capacity value. These limitations are disclosed instead of
inventing values or expanding backend contracts. Supplied modeled sensitivity
and observational candidates remain explicitly in the simulation section.

Saved history resolves dataset names from the existing catalog and fetches status
through the existing GET endpoint, with at most three concurrent reads across the
bounded 20 displayed entries. It does not create an investigation. Request
construction, submission keys, admission reconciliation, polling intervals,
refresh/reconnect and all five workflow outcomes retain their existing behavior.

Browser acceptance now obtains static responses from the actual FastAPI asset
mount, retains MIME/security headers, asserts computed layout/font/button styles,
checks page overflow, label/focus semantics, text and badge contrast, source text
safety and console/runtime errors. Edge is driven through its local debugging
protocol using Node's built-in WebSocket, with no package installation. Explicit
device metrics verify the actual CSS viewport at 1440×1200 and 390×1000; Edge's
window-size flag alone cropped a wider viewport on Windows and was insufficient.
Native Tab/Enter events additionally exercise visible keyboard focus and evidence
disclosures. Generated screenshots cover the workspace and results at both sizes
under ignored `data/processed/stage7/ui/`.

The pre-existing `/favicon.ico` request still returns 404. The user explicitly
declined extending the file allowlist with an SVG favicon. Real-browser reports
therefore record this known network error separately from application errors;
the acceptance harness does not substitute a successful favicon response for the
real saved-result browser check. CSS/module failures, other network errors,
uncaught exceptions and console errors remain failures. No favicon asset, route
or CSP exception was added.

The complete regression and exact preservation results for this follow-up are
recorded separately in `docs/implementation-status.md`. No fresh live model call
or production simulation is needed to verify this presentation-only change.


## Approved evidence-backed chat refinement ? 2026-11-09

This section supersedes the earlier dashboard-specific descriptions and screenshots.
The existing native HTML/CSS/JavaScript stack now provides one current conversation.
Dataset and UTC-period selectors sit above it; the composer remains visible at the
bottom. Enter sends, Shift+Enter inserts a newline, and examples populate the input.
Answers use the existing validated response text, with source-ID excerpts moved
into View evidence. No extra free-form LLM answer or invented metrics are added.
Historical measurements, source evidence, hypotheses and modeled experiments remain
separate inside that disclosure. Saved checkpoints are inspectable there after
completion; only genuine persisted events appear while work runs.

### Conversation lifetime and context

Browser local storage contains only this conversation's questions, scopes,
submission keys, investigation IDs and final-confirmation flags, plus selectors.
It does not store full source passages/results, provider keys or archived chats.
Refresh fetches existing finalized answers by GET and reconciles the one pending
request by its key. A lost acceptance response is never retried by POST. An unknown
admission or interrupted execution remains visibly uncertain; no cancellation or
automatic resume is implied. Storage must work before sending a new question.

New chat clears the visible thread and its parent connection, including the legacy
URL/local identifiers. It never deletes PostgreSQL audits or cancels accepted work.
It is disabled during known active execution. Older visible exchanges remain until
New chat, while the planner receives at most five previous finalized exchanges as
bounded summaries, oldest first. The current new question is additional. Only the
same dataset/content version and UTC period can supply context. Browser scope
changes omit the parent; server validation independently enforces boundaries.
Failed/unsupported/clarification exchanges retain the question and clarification
without factual answer content. Explicit new questions and scope win, prior causes
remain qualified hypotheses, and each follow-up reruns the registered tools.

The optional previous_investigation_id lives on the existing Stage 6 request.
workflows/context.py resolves links from existing audit JSONB; graph.py loads the
context before initial-audit creation, and planner.py passes it to the existing
structured language call. No queue, conversation table, migration or new agent is
needed. Invalid/unconfirmed parents fail before admission. The new initial audit,
202 handshake, final commit, routing registry and existing tool services retain
their original behavior.

### Historical evidence projection

ResultView adds optional historical_provenance. APIRepository selects the stored
overall line measurements, seven station reference collections, provenance and
assumptions from state.analytics, without retrieving all dated segments or
recomputing metrics. The typed projection exposes at most 50 aggregate references,
five source samples per reference and 30 assumptions. Each reference retains its
dataset/segment/station identifiers, measurement and record count; samples retain
source IDs, relationship and excerpt. Dataset mismatches reject the projection.
Truncation notices and the existing 512 KiB public-result bound remain enforced.
Old records lacking these details explicitly disclose their absence. Original
source rows, full audit content and recorded simulation values remain unchanged.

### Verification evidence

The current browser journeys cover all question groups and five outcomes, safe
source rendering, evidence expansion, initial active checkpoints, follow-up parent
IDs, changed-period context reset, truncated acceptance-response reconciliation,
refresh without duplicate POST, and New chat without deleting old fixture audits.
Real saved combined results are also rendered with unchanged 46.88 historical JPH
and 46.25588888888889 simulated baseline JPH. Installed Edge is driven with the
existing Node WebSocket tooling at 1440?1200 and 390?1000. No dependency was added.
Screenshots and JSON browser reports are ignored artifacts under
`data/processed/stage7/chat/`. Exact final commands/results and the separate real
provider follow-up are recorded in implementation-status.md.


## Comparison-answer correction ? 2026-11-09

Segmentation investigations previously returned only an overall-line answer even
though their typed historical result contained dated-shift, model and UTC-hour
comparisons. workflows/validation.py now builds the grounded introduction and
answer from those existing segment results: candidate counts across dated shifts
and UTC-hour groups, unresolved-group counts, and per-model candidate names.
Unknown candidates remain unresolved. Model-specific candidates remain historical
diagnostics; model JPH is labeled as a contribution to shared mixed-line output,
not exclusive-model capacity or a proven physical line constraint.

The existing API result projection also prepends these findings for older saved
segmentation responses, with an explicit projection notice. It never updates the
stored answer or audit. New responses already containing the findings receive no
duplicate prefix. Failed/clarification/unsupported answers retain their outcomes.
The chat displays a small SUV/Sedan comparison table directly in the answer; full
dated-shift/hour tables, warnings and source details remain under View evidence.
There is no new endpoint, contract field, model call, calculation, dataset,
migration, dependency or agent. Tests/results are recorded in implementation-status.md.


## Conversational answer correction ? 2026-11-09

The earlier comparison correction still reused an overall-line technical summary
for maintenance and what-if questions. The shared answer presenter now lives in
workflows/answers.py. It selects question-specific paragraphs from validated
historical, evidence and simulation results. Both newly executed answers and the
read-only API projection of old saved answers use it. Original audits are not
rewritten, and no language or simulation call is made when reopening a result.

What-if answers lead with the requested intervention and estimated before/after
output, followed by constraint movement and an explanation of uncertainty.
Repair-duration and failure-rate methods remain distinct. Missing scenario or
movement metadata is disclosed rather than guessed; a confidence interval that
includes zero is explicitly qualified. Rounded, readable rates appear in the
answer while full-precision values remain unchanged in the typed result and
expandable evidence.

Maintenance answers lead with the evidence at the requested station. A supported
hypothesis stays a possibility; a recorded maintenance cause remains attributed
to maintenance, and associations or insufficient evidence do not become confirmed
causes. Robot-fault wording requires a supporting fault record containing the
robot-fault category and a linked work order in the assessment evidence. Specific
component diagnoses are never invented from a relevant note. Conflicting/excluded
records and unavailable searches remain qualified. Verbatim source excerpts and
IDs remain available in the evidence/audit; raw assessment labels and unresolved
question dumps are not placed in the main answer.

Segmentation answers explain consistent or differing candidates and inconclusive
groups in ordinary language. Constraint questions retain their relevant output
and design-gap figures. Combined questions retain historical findings, evidence
and simulated effects as distinct paragraphs. The LLM still selects a validated
introduction through Agent 1; Python copies numbers and controls claim strength.
No additional free-form model, agent, endpoint, queue, migration or dependency was
introduced. The original analytics, retrieval and simulation tools are unchanged.

For completed responses, bookkeeping status and the copy-ID control are inside
View evidence. Failed/incomplete/unsupported/clarification statuses remain visible.
The existing global synthetic-data/human-review notice stays in the composer,
and the full review notice remains inside the result's evidence details. Safe
text rendering, five-exchange context, audit finalization and reconnect behavior
are preserved. Acceptance results are recorded in implementation-status.md.


## Concise user-facing evidence ? 2026-11-09

This supersedes the earlier full audit-style View evidence renderer. The user
requested only the main supporting evidence, written for quick understanding.
The change is frontend presentation only: render.mjs and small evidence spacing
rules in styles.css. Backend contracts, stored answers, analytics, retrieval,
simulation, original records and audit persistence are unchanged.

A historical constraint answer shows up to three plain-language station signals,
the recorded completions/hours/rate and design-reference gap, and a short
qualification. Normalized ranking signals are not presented as percentages or
raw scores. Missing/conflicting indicators and weak support remain disclosed.
The concrete bottleneck example is kept below 240 displayed words in browser
acceptance. No aggregate UUID list, all-station state-reference inventory,
repeated executive summary, workflow checkpoints or unrelated empty specialist
section is rendered.

Evidence is selected by the existing intent. Cause answers show at most three
distinct source passages. Cited support precedes uncited related context; source
systems are diversified within those tiers, and a conflicting/excluded record is
retained when present. Identical passages are deduplicated while document
versions remain distinct. Each excerpt has an everyday source heading, station,
time/version when available, and a direct/inferred/related link qualification.
Excerpts start at 400 characters with an explicit button for the original full
passage; source text always uses textContent. Further original records remain in
the API result and audit, not a large metadata dump in the UI.

Simulation answers show the tested method/percentage/target when supplied,
three before/after/change rows, the number/horizon of paired comparisons and the
existing gain confidence interval with a short explanation of its limits.
Historical output is not mixed into that experiment. Segmentation answers start
with a few representative groups (including differing or unresolved candidates);
users may deliberately show all comparison groups when needed. Combined answers
show the relevant historical/source/model blocks together.

Completed bookkeeping stays at the bottom of the disclosure; a failed or partial
result retains an outcome warning and the first sanitized failure explanation.
Copy investigation ID remains available. Full source identifiers, measurements,
versions, seeds, parameters, assumptions and checkpoints remain in the unchanged
existing API projection and durable audit for technical inspection. The normal
UI no longer prints that technical inventory. Answers and current-chat behavior
are unchanged, and no new dependency, service, agent or model call was introduced.


## Question-specific Agent 1 composition ? 2026-11-09

New investigations use the existing planner's model call to compose the full
answer from the exact question, selected scope, up to five qualified exchanges,
and current validated findings. A short answer-goal field and fact references
precede prose in the structured draft. The facts include station-specific queue,
blocked/starved/fault time and processing measurements, supporting/conflicting
signals, historical line context, comparison groups, source assessments and
simulation findings as available. This replaces the one-choice introduction and
category paragraphs for newly executed investigations.

Python permits quantity placeholders or verbatim computed values with matching
units from selected facts, rejects residual/unrecognized figures and references,
and checks simulation uncertainty and common claims that observations prove a
constraint/cause. It normalizes duplicate value/unit formatting. One validation
correction is permitted; repeated invalid drafts fail composition. Provider or
network failures do not trigger that correction. These are numeric/reference
consistency checks and limited overclaim guards, not a complete semantic verifier.
Human review remains required.

Explanation adds backward-compatible optional fact_ids and composition_version
metadata stored in the existing JSONB audit. The version is assigned by code only
after validation. The workflow renders that complete answer without appending the
old category text. The result projection preserves versioned answers verbatim
instead of overwriting them. Existing legacy saved answers retain their prior
read-only presentation; no GET initiates paid language calls or rewrites an audit.
Users must submit a new question/follow-up to receive newly composed wording.

No frontend, endpoint, request, admission, routing, database schema, analytical
calculation, retrieval/simulation implementation, dependency or agent change was
made for this correction. The live acceptance reuses saved historical findings
and calls the existing model for the two reported questions, without creating an
investigation or updating database records. Final results are in the status log.
