"""Agent 2: invoke verified analytics, without duplicating its calculations."""

from sqlalchemy.engine import Engine

from bottleneck_analyzer.analytics.contracts import AnalyticsResult, AnalyticsScope
from bottleneck_analyzer.analytics.service import analyze


class AnalyticsAgent:
    def __init__(self, engine: Engine):
        self.engine = engine

    def run(self, scope: AnalyticsScope) -> AnalyticsResult:
        result = AnalyticsResult.model_validate(analyze(self.engine, scope).model_dump())
        if result.dataset_name != scope.dataset or result.scope != scope:
            raise ValueError("Analytics returned a different scope")
        if result.overall.line.scheduled_hours > 0 and (
            (scope.start_time and result.overall.start_time < scope.start_time)
            or (scope.end_time and result.overall.end_time > scope.end_time)
        ):
            raise ValueError("Analytics returned a broader period")
        return result
