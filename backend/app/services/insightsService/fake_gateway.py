"""In-memory MLflow for tests and offline demos."""

from __future__ import annotations

from uuid import uuid4

from app.services.insightsService.mlflow_gateway import (
    LABEL_PREFIX,
    GatewayHealth,
    MlflowUnavailable,
    TraceNotFound,
)
from app.services.insightsService.trace_summary import TraceSummary


class FakeMlflowGateway:
    def __init__(self, server_version: str = "3.16.1", client_version: str = "3.16.1") -> None:
        self.traces: dict[str, TraceSummary] = {}
        self.labels: dict[str, dict[str, dict]] = {}  # trace_id -> assessment_id -> data
        self.down = False
        # The write succeeds but the caller sees an error: the worst case for retries.
        self.lose_next_response = 0
        self.server_version, self.client_version = server_version, client_version

    def _check(self) -> None:
        if self.down:
            raise MlflowUnavailable("fake MLflow is down")

    def get_trace_summary(self, trace_id: str) -> TraceSummary:
        self._check()
        if trace_id not in self.traces:
            raise TraceNotFound(trace_id)
        return self.traces[trace_id]

    def find_label(
        self, trace_id: str, feedback_id: str, *, name_prefix: str = LABEL_PREFIX
    ) -> str | None:
        self._check()
        for assessment_id, data in self.labels.get(trace_id, {}).items():
            if data["feedback_id"] == feedback_id and data["name"].startswith(name_prefix):
                return assessment_id
        return None

    def log_label(
        self,
        trace_id: str,
        *,
        feedback_id: str,
        report_id: str,
        instructor_id: str,
        dimension: str,
        score: float,
        reason: str | None,
        blind: bool,
        name_prefix: str = LABEL_PREFIX,
        extra_metadata: dict[str, str] | None = None,
    ) -> str:
        self._check()
        assessment_id = f"a-{uuid4().hex[:10]}"
        self.labels.setdefault(trace_id, {})[assessment_id] = {
            "feedback_id": feedback_id,
            "name": name_prefix + dimension,
            "metadata": {"blind": str(blind).lower(), **(extra_metadata or {})},
            "report_id": report_id,
            "dimension": dimension,
            "score": score,
            "reason": reason,
            "instructor_id": instructor_id,
            "blind": blind,
        }
        if self.lose_next_response:
            self.lose_next_response -= 1
            raise MlflowUnavailable("response lost after write")
        return assessment_id

    def update_label(
        self,
        trace_id: str,
        assessment_id: str,
        *,
        dimension: str,
        score: float,
        reason: str | None,
        name_prefix: str = LABEL_PREFIX,
    ) -> None:
        self._check()
        self.labels[trace_id][assessment_id].update(score=score, reason=reason)

    def health(self) -> GatewayHealth:
        if self.down:
            return GatewayHealth(False, None, self.client_version)
        return GatewayHealth(True, self.server_version, self.client_version)