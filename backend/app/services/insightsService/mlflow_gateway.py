"""The only module that talks to MLflow. Always by explicit trace ID; never search/list."""

from __future__ import annotations

import httpx, importlib.metadata, json, logging, os, threading, time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.services.insightsService.trace_summary import (
    AI_ENGINE_DIMENSION_ORDER,
    TraceSummary,
    summarize_trace,
)

log = logging.getLogger(__name__)
LABEL_PREFIX = "sprintsight.instructor."
OVERRIDE_PREFIX = "sprintsight.override."

class MlflowUnavailable(RuntimeError): # noqa: N818 - named for what callers handle
    """MLflow could not be reached or answered with an error; callers degrade gracefully."""

class TraceNotFound(LookupError): # noqa: N818
    """MLflow is up but has no trace with this ID."""

class PromptNotFound(LookupError): # noqa: N818
    """MLflow is up but has no prompt with this name."""

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
    def prompt_registry(self) -> list[dict]: ...
    def get_prompt(self, name: str, version: str) -> dict: ...
    def get_eval_progress(self, correlation_id: str) -> tuple[int, int] | None: ...
    def health(self) -> GatewayHealth: ...

def client_version() -> str | None: # version of the MLflow client library
    for dist in ("mlflow-skinny", "mlflow"):
        try:
            return importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None

class RealMlflowGateway: # real implementation of MlflowGateway talking to a real MLflow server
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

    def get_eval_progress(self, correlation_id: str) -> tuple[int, int] | None:
        try:
            _, client = self._mlflow()
            ids = [e.experiment_id for e in client.search_experiments()]
            runs = client.search_runs(
                experiment_ids=ids,
                filter_string=f"tags.correlation_id = '{correlation_id}'",
                order_by=["attributes.start_time DESC"],
                max_results=1,
            )
        except Exception as exc:  # noqa: BLE001
            raise MlflowUnavailable(str(exc)) from exc
        if not runs:
            return None
        raw = runs[0].data.tags.get("eval.progress")
        try:
            done, total = (int(x) for x in str(raw).split("/", 1))
        except (TypeError, ValueError):
            return None
        return (done, total) if total > 0 and 0 <= done <= total else None

    def find_label( # finds an assessment ID for a label if it exists, else None
        self, trace_id: str, feedback_id: str, *, name_prefix: str = LABEL_PREFIX
    ) -> str | None:
        trace = self._get_trace(trace_id) # uncached on purpose: idempotency check must be fresh
        for a in getattr(trace.info, "assessments", None) or []:
            if (
                a.name.startswith(name_prefix)
                and (a.metadata or {}).get("feedback_id") == feedback_id
            ):
                return a.assessment_id
        return None

    def log_label( # logs new label to MLflow; returns the assessment ID
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

    def update_label(  # updates an existing label in MLflow
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

    def prompt_registry(self) -> list[dict]:  # production/challenger/latest per prompt
        names = [f"Evaluate_{d}" for d in AI_ENGINE_DIMENSION_ORDER] + ["Generate_Sprint_Feedback"]
        try:
            _, client = self._mlflow()
            rows = []
            for name in names:
                row = {"name": name, "production": None, "challenger": None, "latest": None}
                for alias in ("production", "challenger"):
                    try:
                        row[alias] = int(client.get_prompt_version_by_alias(name, alias).version)
                    except Exception:  # alias not set
                        pass
                versions = [
                    int(v.version) for v in client.search_prompt_versions(name, max_results=200)
                ]
                row["latest"] = max(versions) if versions else None
                rows.append(row)
            return rows
        except Exception as exc:  # noqa: BLE001
            raise MlflowUnavailable(str(exc)) from exc

    def get_prompt(self, name: str, version: str) -> dict:
        try:
            _, client = self._mlflow()
            pv = client.get_prompt_version(name, version)
        except Exception as exc:  # noqa: BLE001
            # Decide "missing" by MLflow's error code, not by guessing at message text, so a
            # network failure is never reported as a missing prompt.
            if getattr(exc, "error_code", "") == "RESOURCE_DOES_NOT_EXIST":
                raise PromptNotFound(f"{name} v{version}") from exc
            raise MlflowUnavailable(str(exc)) from exc
        template = pv.template
        created = getattr(pv, "creation_timestamp", None)  # epoch ms
        try:  # the created date is cosmetic: a bad value must not take down the whole drawer
            created_at = datetime.fromtimestamp(created / 1000, UTC).isoformat() if created else None
        except (TypeError, ValueError, OverflowError, OSError):
            created_at = None
        return {
            "template": template if isinstance(template, str) else json.dumps(template, indent=2),
            "commit_message": getattr(pv, "commit_message", None),
            "created_at": created_at,
            "aliases": list(getattr(pv, "aliases", None) or []),
        }