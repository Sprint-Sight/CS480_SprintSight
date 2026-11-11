"""Why a rubric dimension (or a judge call) failed, as a closed vocabulary.

Retries are only worth repeating for some failures. A timeout or a model server
that is down is *transient infrastructure*: the same request can succeed later.
A response that never matched the schema, or that kept hitting the output-length
cap, is *deterministic-ish*: resending the identical prompt will most likely fail
the same way. Recording which one happened lets callers (the backend's manual
review flow, the judge job queue, the analytics) treat them differently instead
of parsing a truncated exception string.
"""

from enum import StrEnum


class FailureClass(StrEnum):
    SCHEMA_VALIDATION = "schema_validation"    # answered, but never matched the response schema after re-asks
    OUTPUT_LENGTH = "output_length"            # hit the max_tokens cap, also after the concise re-ask
    TIMEOUT = "timeout"                        # no response inside the client timeout (transient)
    INFRA_UNAVAILABLE = "infra_unavailable"    # connection refused, 5xx, rate limited (transient)
    CONTEXT_TRUNCATED = "context_truncated"    # the prompt did not fit / was silently cut by the server
    UNKNOWN = "unknown"


TRANSIENT_FAILURES = frozenset({FailureClass.TIMEOUT, FailureClass.INFRA_UNAVAILABLE})


def is_transient(failure_class: "FailureClass | str | None") -> bool:
    """True when retrying the same request later may succeed."""
    if failure_class is None:
        return False
    try:
        return FailureClass(failure_class) in TRANSIENT_FAILURES
    except ValueError:
        return False


# One short, user-safe sentence per class. These end up in a report's
# justification text, so they must not leak URLs, prompts or stack traces.
FAILURE_DESCRIPTIONS: dict[FailureClass, str] = {
    FailureClass.SCHEMA_VALIDATION: "the model's answer did not match the required format after several attempts",
    FailureClass.OUTPUT_LENGTH: "the model's answer kept exceeding the length limit",
    FailureClass.TIMEOUT: "the model did not respond in time",
    FailureClass.INFRA_UNAVAILABLE: "the model service was unavailable",
    FailureClass.CONTEXT_TRUNCATED: "the evidence did not fit in the model's context window",
    FailureClass.UNKNOWN: "an unexpected error occurred",
}


def describe_failure(failure_class: "FailureClass | str | None") -> str:
    try:
        return FAILURE_DESCRIPTIONS[FailureClass(str(failure_class))]  # str(None) -> "None": unknown, handled below
    except (ValueError, KeyError):
        return FAILURE_DESCRIPTIONS[FailureClass.UNKNOWN]
