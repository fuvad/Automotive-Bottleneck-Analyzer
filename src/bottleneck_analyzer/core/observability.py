"""Metadata-only optional LangSmith spans and durable local execution events."""

import json
import logging
from datetime import UTC, datetime, timedelta

from langsmith import Client

from bottleneck_analyzer.agents.contracts import ExecutionEvent, WorkflowState
from bottleneck_analyzer.core.config import AppSettings

logger = logging.getLogger(__name__)


class WorkflowTelemetry:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.client = None
        self.unavailable = False
        if settings.langsmith_tracing:
            if not settings.langsmith_api_key or not settings.langsmith_api_key.get_secret_value():
                self.unavailable = True
            else:
                try:
                    self.client = Client(
                        api_key=settings.langsmith_api_key.get_secret_value(),
                        timeout_ms=1000,
                        auto_batch_tracing=False,
                        hide_inputs=True,
                        hide_outputs=True,
                        omit_traced_runtime_info=True,
                    )
                except Exception:
                    self.unavailable = True

    def emit(self, state: WorkflowState, event: ExecutionEvent) -> None:
        metadata = {
            "investigation_id": str(state.investigation_id),
            "dataset_id": str(state.context.dataset_id),
            "workflow": state.plan.intent.value if state.plan else "planning",
            **event.model_dump(),
        }
        logger.info(json.dumps(metadata))
        if self.client is not None and not self.unavailable:
            try:
                from uuid import uuid4

                run_id = uuid4()
                end = datetime.now(UTC)
                self.client.create_run(
                    id=run_id,
                    name=event.component,
                    run_type="chain",
                    inputs={},
                    start_time=end - timedelta(seconds=event.duration_seconds),
                    project_name=self.settings.langsmith_project,
                    extra={"metadata": metadata},
                )
                self.client.update_run(run_id, end_time=end, outputs={"status": event.status})
            except Exception:
                self.unavailable = True
                logger.warning(
                    "LangSmith unavailable; local investigation audit remains authoritative"
                )
