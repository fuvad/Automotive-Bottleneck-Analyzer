"""Small acyclic LangGraph with Python-owned routes and exactly four agents."""

from time import monotonic
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from sqlalchemy.engine import Engine

from bottleneck_analyzer.agents.analytics import AnalyticsAgent
from bottleneck_analyzer.agents.composition import CompositionValidationError
from bottleneck_analyzer.agents.contracts import (
    ExecutionError,
    ExecutionEvent,
    InvestigationRequest,
    InvestigationResponse,
    KnowledgeInput,
    SimulationInput,
    WorkflowState,
)
from bottleneck_analyzer.agents.knowledge import KnowledgeAgent
from bottleneck_analyzer.agents.planner import (
    ClarificationRequired,
    PlannerAgent,
    UnsupportedQuestion,
)
from bottleneck_analyzer.agents.simulation import SimulationAgent
from bottleneck_analyzer.core.config import AppSettings, get_settings
from bottleneck_analyzer.core.llm import LLMUnavailable, OpenAIStructuredLLM, StructuredLLM
from bottleneck_analyzer.core.observability import WorkflowTelemetry
from bottleneck_analyzer.domain.enums import InvestigationStatus
from bottleneck_analyzer.simulation.config import updated
from bottleneck_analyzer.workflows.audit import (
    AuditUnavailable,
    AuditWriter,
    PostgresAudit,
    load_context,
)
from bottleneck_analyzer.workflows.context import load_conversation
from bottleneck_analyzer.workflows.validation import (
    render,
    summarize,
    validate_plan,
    validate_results,
)


class InvestigationWorkflow:
    def __init__(
        self,
        engine: Engine,
        *,
        settings: AppSettings | None = None,
        llm: StructuredLLM | None = None,
        audit: AuditWriter | None = None,
    ):
        self.engine = engine
        self.settings = settings or get_settings()
        language = llm or OpenAIStructuredLLM(self.settings)
        self.planner = PlannerAgent(language)
        self.analytics = AnalyticsAgent(engine)
        self.knowledge = KnowledgeAgent(engine, language)
        self.simulation = SimulationAgent(self.settings)
        self.audit = audit or PostgresAudit(engine)
        self.telemetry = WorkflowTelemetry(self.settings)
        graph = StateGraph(WorkflowState)
        for name, fn in (
            ("planner", self._plan),
            ("analytics", self._analytics),
            ("knowledge", self._knowledge),
            ("simulation", self._simulation),
            ("validation", self._validate),
            ("compose", self._compose),
        ):
            graph.add_node(name, self._node(name, fn))
        graph.add_edge(START, "planner")
        targets = {
            name: name for name in ("analytics", "knowledge", "simulation", "validation", "compose")
        }
        for name in ("planner", "analytics", "knowledge", "simulation", "validation"):
            graph.add_conditional_edges(name, self._route, targets)
        graph.add_edge("compose", END)
        self.graph = graph.compile()
        self.latest: WorkflowState | None = None

    def _node(self, name, fn):
        def run(state: WorkflowState) -> dict:
            start = monotonic()
            category = None
            try:
                changes = fn(state)
                status = "completed"
            except (ClarificationRequired, UnsupportedQuestion) as exc:
                changes = {
                    "outcome": "clarification_required"
                    if isinstance(exc, ClarificationRequired)
                    else "unsupported",
                    "clarification": str(exc),
                    "status": InvestigationStatus.BLOCKED,
                }
                status = "completed"
            except Exception as exc:
                category = type(exc).__name__
                error = ExecutionError(
                    component=name,
                    category=category,
                    message=(
                        "LLM unavailable or output invalid; verify LLM_PROVIDER, LLM_MODEL "
                        "and LLM_API_KEY."
                        if isinstance(exc, LLMUnavailable)
                        else exc.public_message
                        if isinstance(exc, CompositionValidationError)
                        else f"{name} did not return a valid result; investigation is incomplete."
                    ),
                )
                changes = {
                    "errors": [*state.errors, error],
                    "outcome": "failed",
                    "status": InvestigationStatus.BLOCKED,
                }
                if name == "compose":
                    changes["response"] = self._failure_response(state, [*state.errors, error])
                status = "failed"
            event = ExecutionEvent(
                component=name,
                status=status,
                duration_seconds=monotonic() - start,
                category=category,
            )
            changes["events"] = [*state.events, event]
            next_state = WorkflowState.model_validate({**state.model_dump(), **changes})
            self.telemetry.emit(next_state, event)
            if self.telemetry.unavailable:
                next_state.warnings = list(
                    dict.fromkeys(
                        [
                            *next_state.warnings,
                            "LangSmith unavailable; local audit and logs retained.",
                        ]
                    )
                )
            self.latest = next_state
            # A failed audit stops execution; successful tool calls alone cannot
            # imply a complete, auditable investigation.
            self.audit.save(next_state)
            return next_state.model_dump()

        return run

    def _route(self, state: WorkflowState) -> str:
        if state.outcome or state.errors:
            return "compose"
        if state.plan is None:
            raise ValueError("Planner did not supply a registered plan")
        validate_plan(state.plan)
        for name in state.plan.agents:
            if getattr(state, name) is None:
                return name
        return "compose" if state.validation_status == "validated" else "validation"

    def _plan(self, state: WorkflowState) -> dict:
        plan = self.planner.plan(state)
        validate_plan(plan)
        context = load_context(self.engine, plan.scope)
        if (
            context.dataset_id != state.context.dataset_id
            or context.content_hash != state.context.content_hash
        ):
            raise ValueError("Dataset changed during planning")
        return {
            "plan": plan,
            "intent": plan.intent,
            "scope": plan.scope,
            "status": InvestigationStatus.IN_PROGRESS,
        }

    def _analytics(self, state: WorkflowState) -> dict:
        return {"analytics": self.analytics.run(state.scope)}

    def _knowledge(self, state: WorkflowState) -> dict:
        if state.analytics is None:
            raise ValueError("Analytics must precede candidate evidence retrieval")
        station = state.scope.station or state.analytics.overall.leading_candidate
        if not station:
            raise ClarificationRequired(
                "No leading candidate is established; select a station for evidence retrieval"
            )
        result = self.knowledge.run(
            KnowledgeInput(
                analytics=state.analytics,
                stations=[station],
                query=state.question[:1000],
                limit=min(state.request.retrieval_limit, self.settings.workflow_retrieval_limit),
                incident_ids=state.request.incident_ids,
                work_order_ids=state.request.work_order_ids,
            )
        )
        warnings = list(state.warnings)
        if not result.retrieval.evidence:
            warnings.append("No matching evidence; no cause is established.")
        if result.retrieval.diagnostics.unavailable:
            warnings.append("Retrieval coverage is partial; inspect unavailable search methods.")
        return {"knowledge": result, "warnings": warnings}

    def _simulation(self, state: WorkflowState) -> dict:
        if state.plan is None or state.plan.scenario is None or state.analytics is None:
            raise ValueError("A validated scenario and analytics are required")
        config = state.context.simulation_config
        if config is None:
            raise ClarificationRequired(
                "This dataset has no unambiguous stored simulation configuration"
            )
        # Segmented history cannot silently become an unsegmented counterfactual.
        if state.scope.model or state.scope.shift or state.scope.shift_id or state.scope.utc_hours:
            raise ClarificationRequired(
                "The simulator compares full-line calendars/mix. Request a separate unsegmented "
                "scenario; filtered history cannot be simulated as an equivalent baseline."
            )
        if state.scope.start_time != config.start_time or state.scope.end_time != config.end_time:
            raise ClarificationRequired(
                "Scenario history must use the stored baseline's full period"
            )
        scenario = state.plan.scenario
        if scenario.request.target_station == "candidate":
            target = state.analytics.overall.leading_candidate
            if target is None:
                raise ClarificationRequired(
                    "Select a scenario target; historical evidence has no leader"
                )
            scenario = type(scenario).model_validate(
                {
                    **scenario.model_dump(),
                    "request": {**scenario.request.model_dump(), "target_station": target},
                }
            )
        result = self.simulation.run(
            SimulationInput(config=updated(config, record_history=False), scenario=scenario)
        )
        warnings = [*state.warnings]
        if not state.context.configuration_approved:
            warnings.append(
                "Stored synthetic configuration has no operational approval; human review required."
            )
        return {
            "simulation": result,
            "simulation_parameters": {
                "configuration_id": str(state.context.configuration_id),
                "scenario": scenario.model_dump(mode="json"),
                "seeds": result.seeds,
            },
            "warnings": warnings,
        }

    def _validate(self, state: WorkflowState) -> dict:
        validate_results(state)
        return {"validation_status": "validated"}

    def _compose(self, state: WorkflowState) -> dict:
        if state.errors or state.outcome:
            response = self._failure_response(state, state.errors)
            return {"response": response}
        validate_results(state)
        ids = [e.evidence_id for e in state.knowledge.retrieval.evidence] if state.knowledge else []
        explanation = self.planner.explain(state, ids)
        warnings = [*state.warnings, *state.analytics.warnings, *state.analytics.overall.warnings]
        incomplete = False
        if state.knowledge:
            retrieval = state.knowledge.retrieval
            warnings.extend(retrieval.diagnostics.warnings)
            incomplete = (
                not retrieval.evidence
                or bool(retrieval.diagnostics.unavailable)
                or not any(item.evidence_ids for item in state.knowledge.interpretations)
            )
        response = InvestigationResponse(
            investigation_id=state.investigation_id,
            question=state.question,
            scope=state.scope,
            intent=state.intent,
            outcome="incomplete" if incomplete else "completed",
            status=InvestigationStatus.BLOCKED if incomplete else InvestigationStatus.COMPLETED,
            answer=render(state, explanation.summary),
            historical=summarize(state) if state.validation_status == "validated" else None,
            evidence=state.knowledge,
            simulation=state.simulation,
            interpretation=explanation,
            warnings=list(dict.fromkeys(warnings)),
            limitations=[
                *state.analytics.assumptions,
                "Historical candidates and linked incidents do not establish line-level causation.",
                "LLM synthesis is restricted to supplied assessments and validated summaries.",
            ],
            events=state.events,
        )
        return {
            "response": response,
            "status": response.status,
            "outcome": response.outcome,
            "evidence_ids": ids,
        }

    def _failure_response(
        self, state: WorkflowState, errors: list[ExecutionError]
    ) -> InvestigationResponse:
        outcome = state.outcome or "failed"
        if errors:
            outcome = "failed"
        return InvestigationResponse(
            investigation_id=state.investigation_id,
            question=state.question,
            scope=state.scope,
            intent=state.intent,
            outcome=outcome,
            status=InvestigationStatus.BLOCKED,
            answer=state.clarification
            or (
                "I couldn't finish validating the answer. " + errors[-1].message
                if errors and errors[-1].category == "CompositionValidationError"
                else "Investigation incomplete. Inspect the failure before using partial results."
            ),
            historical=summarize(state) if state.validation_status == "validated" else None,
            evidence=state.knowledge,
            simulation=state.simulation,
            clarification=state.clarification,
            warnings=state.warnings,
            errors=errors,
            events=state.events,
        )

    def run(self, request: InvestigationRequest) -> InvestigationResponse:
        request = InvestigationRequest.model_validate(request.model_dump())
        context = load_context(self.engine, request.scope)
        if request.dataset_id is not None and request.dataset_id != context.dataset_id:
            raise ValueError("Dataset UUID does not belong to the selected dataset")
        scope = type(request.scope).model_validate(
            {
                **request.scope.model_dump(),
                "start_time": request.scope.start_time or context.start_time,
                "end_time": request.scope.end_time or context.end_time,
            }
        )
        state = WorkflowState(
            investigation_id=uuid4(),
            question=request.question,
            request=request,
            scope=scope,
            context=context,
            model_versions={
                "llm_provider": self.settings.llm_provider,
                "llm_requested_model": self.settings.llm_model,
                "llm_adapter": type(self.planner.llm).__name__,
                "embedding_provider": self.settings.embedding_provider,
                "embedding_model": self.settings.embedding_model,
                "embedding_dimensions": str(self.settings.embedding_dimensions),
                "simulation": context.simulation_config.version
                if context.simulation_config
                else "unavailable",
            },
            execution_limits={
                "workflow_max_steps": self.settings.workflow_max_steps,
                "retrieval_limit": self.settings.workflow_retrieval_limit,
                "llm_timeout_seconds": self.settings.llm_timeout_seconds,
                "llm_max_output_tokens": self.settings.llm_max_output_tokens,
                "simulation_max_days": self.settings.simulation_max_days,
                "simulation_max_replications": self.settings.simulation_max_replications,
                "simulation_timeout_seconds": self.settings.simulation_timeout_seconds,
            },
        )
        if request.previous_investigation_id is not None:
            turns, notices = load_conversation(
                self.engine, request.previous_investigation_id, scope, context
            )
            state.conversation_context = turns
            state.conversation_warnings = notices
            state.warnings.extend(notices)
        self.latest = state
        try:
            self.audit.create(state)
        except Exception:
            raise AuditUnavailable(
                "Cannot start an investigation without durable audit storage"
            ) from None
        try:
            # Disable automatic tracing of graph state: it contains source text.
            # Explicit metadata-only spans are emitted by WorkflowTelemetry.
            with tracing_context(enabled=False):
                result = self.graph.invoke(
                    state, {"recursion_limit": self.settings.workflow_max_steps}
                )
            final = WorkflowState.model_validate(result)
        except Exception as exc:
            final = self.latest
            final.errors.append(
                ExecutionError(
                    component="workflow",
                    category=type(exc).__name__,
                    message="Workflow interrupted or audit checkpoint failed",
                )
            )
            final.outcome = "failed"
            final.status = InvestigationStatus.BLOCKED
            final.response = self._failure_response(final, final.errors)
        response = final.response
        if response is None:
            response = self._failure_response(
                final,
                [
                    ExecutionError(
                        component="workflow",
                        category="MissingResponse",
                        message="Graph returned no response",
                    )
                ],
            )
        response = InvestigationResponse.model_validate(
            {
                **response.model_dump(),
                "events": final.events,
                "audit_id": final.investigation_id,
                "warnings": list(dict.fromkeys([*response.warnings, *final.warnings])),
            }
        )
        final.response = response
        self.latest = final
        try:
            self.audit.save(final)
        except Exception:
            raise AuditUnavailable(
                "Final investigation audit could not be saved; completion is unconfirmed"
            ) from None
        return response
