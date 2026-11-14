"""The only module that talks to MLflow. Always by explicit trace ID; never search/list."""

from __future__ import annotations

import importlib.metadata
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.services.insightsService.trace_summary import TraceSummary, summarize_trace

log = logging.getLogger(__name__)
LABEL_PREFIX = "sprintsight.instructor."
OVERRIDE_PREFIX = "sprintsight.override."

class MlflowUnavailable(RuntimeError): # noqa: N818 - named for what callers handle
    """MLflow could not be reached or answered with an error; callers degrade gracefully."""

class TraceNotFound(LookupError): # noqa: N818
    """MLflow is up but has no trace with this ID."""

@dataclass(frozen=True)
class GatewayHealth:
    reachable: bool
    server_version: str | None
    client_version: str | None

class MlflowGateway(Protocol):
    def get_trace_summary(self, trace_id: str) -> TraceSummary: ...
    def find_label(
        self, trace_id: str, feedback_id: str, *, name_prefix: str = LABEL_PREFIX
    ) -> str | None: ...
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
    ) -> str: ...
    def update_label(
        self,
        trace_id: str,
        assessment_id: str,
        *,
        dimension: str,
        score: float,
        reason: str | None,
        name_prefix: str = LABEL_PREFIX,
    ) -> None: ...
    def health(self) -> GatewayHealth: ...

def client_version() -> str | None:
    for dist in ("mlflow-skinny", "mlflow"):
        try:
            return importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None

class RealMlflowGateway:
    def __init__(
        self, tracking_uri: str, timeout_seconds: float = 5.0, cache_ttl_seconds: float = 15.0
    ) -> None:
        # Fail fast: a slow MLflow must degrade the page, not hang the request.
        os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", str(int(timeout_seconds)))
        os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
        os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")
        self._uri = tracking_uri.rstrip("/")
        self._ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, TraceSummary]] = {}
        self._lock = threading.Lock()
        self._client = None

    def _mlflow(self):
        import mlflow  # lazy: tests and app import never need MLflow installed/running

        with self._lock:
            # log_feedback/update_assessment use MLflow's process-global tracking URI, so it
            # is set on every call, not only once: a write must never go to another server.
            mlflow.set_tracking_uri(self._uri)
            if self._client is None:
                self._client = mlflow.MlflowClient(tracking_uri=self._uri)
        return mlflow, self._client

    def _get_trace(self, trace_id: str):
        try:
            _, client = self._mlflow()
            return client.get_trace(trace_id, display=False)
        except Exception as exc:  # noqa: BLE001 - MLflow raises many types
            text = str(exc)
            if "RESOURCE_DOES_NOT_EXIST" in text or "not found" in text.lower():
                raise TraceNotFound(trace_id) from exc
            raise MlflowUnavailable(text) from exc

    def get_trace_summary(self, trace_id: str) -> TraceSummary:
        now = time.monotonic()
        cached = self._cache.get(trace_id)
        if cached and now - cached[0] < self._ttl:
            return cached[1]
        summary = summarize_trace(self._get_trace(trace_id))
        self._cache[trace_id] = (now, summary)
        return summary

    def find_label(
        self, trace_id: str, feedback_id: str, *, name_prefix: str = LABEL_PREFIX
    ) -> str | None:
        trace = self._get_trace(trace_id)  # uncached on purpose: idempotency check must be fresh
        for a in getattr(trace.info, "assessments", None) or []:
            if (
                a.name.startswith(name_prefix)
                and (a.metadata or {}).get("feedback_id") == feedback_id
            ):
                return a.assessment_id
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
        try:
            self._mlflow()
            from mlflow.entities import AssessmentSource, AssessmentSourceType
            from mlflow.tracing.assessment import log_feedback

            assessment = log_feedback(
                trace_id=trace_id,
                name=name_prefix + dimension,
                value=score,
                rationale=reason,
                # source_id is the user UUID, never an email (privacy)
                source=AssessmentSource(
                    source_type=AssessmentSourceType.HUMAN, source_id=instructor_id
                ),
                metadata={
                    "feedback_id": feedback_id,
                    "report_id": report_id,
                    "blind": str(blind).lower(),
                    **(extra_metadata or {}),
                },
            )
        except Exception as exc:  # noqa: BLE001
            raise MlflowUnavailable(str(exc)) from exc
        self._cache.pop(trace_id, None)
        return assessment.assessment_id

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
        try:
            self._mlflow()
            from mlflow.entities import Feedback
            from mlflow.tracing.assessment import update_assessment

            update_assessment(
                trace_id=trace_id,
                assessment_id=assessment_id,
                assessment=Feedback(name=name_prefix + dimension, value=score, rationale=reason),
            )
        except Exception as exc:  # noqa: BLE001
            raise MlflowUnavailable(str(exc)) from exc
        self._cache.pop(trace_id, None)

    def health(self) -> GatewayHealth:
        try:
            with httpx.Client(timeout=2.0) as http:
                reachable = http.get(f"{self._uri}/health").status_code == 200
                version = http.get(f"{self._uri}/version").text.strip() if reachable else None
        except httpx.HTTPError:
            return GatewayHealth(False, None, client_version())
        return GatewayHealth(reachable, version, client_version())