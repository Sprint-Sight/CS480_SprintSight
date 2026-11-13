"""Turn the exceptions an LLM call can end in into a FailureClass.

The grader and the judge both call a local model through instructor + the OpenAI SDK, so
a "max retries failed" can mean very different things: the model server timed out, the
server was down, the model kept answering in the wrong shape, or it never stopped
generating. Which one it was decides whether a retry could help (see
schemas/failure_class.py), so it is classified here once instead of being flattened into
`str(exception)[:300]`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import httpx
import openai
from instructor.core.exceptions import (
    IncompleteOutputException,
    InstructorRetryException,
    ResponseParsingError,
)
from instructor.core.exceptions import (
    ValidationError as InstructorValidationError,
)
from pydantic import ValidationError as PydanticValidationError
from schemas.failure_class import FailureClass

# Long enough to keep a full validation report or HTTP error body, short enough that one
# runaway message (instructor can embed the whole failed completion) cannot bloat a report.
ERROR_DETAIL_LIMIT = 4000

_MAX_CHAIN = 25


class PromptTruncatedError(RuntimeError):
    """The prompt did not fit in the model's context window, or the server cut it silently.

    A verdict or grade computed on a truncated prompt looked at partial evidence, so it must
    be treated as a failure rather than as a result."""


def _chain(error: BaseException) -> Iterator[BaseException]:
    """The exception, then whatever caused it, breadth first, including the exceptions of
    the individual attempts instructor recorded before giving up."""
    queue: list[BaseException | None] = [error]
    seen: set[int] = set()
    while queue and len(seen) < _MAX_CHAIN:
        current = queue.pop(0)
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        queue.extend((current.__cause__, current.__context__))
        for attempt in getattr(current, "failed_attempts", None) or []:
            queue.append(getattr(attempt, "exception", None))


def _classify_one(error: BaseException) -> FailureClass | None:
    if isinstance(error, IncompleteOutputException):
        return FailureClass.OUTPUT_LENGTH
    if isinstance(error, PromptTruncatedError):
        return FailureClass.CONTEXT_TRUNCATED
    # APITimeoutError subclasses APIConnectionError, so timeouts are matched first.
    if isinstance(error, (openai.APITimeoutError, httpx.TimeoutException, TimeoutError, asyncio.TimeoutError)):
        return FailureClass.TIMEOUT
    if isinstance(
        error,
        (
            openai.APIConnectionError,
            openai.InternalServerError,
            openai.RateLimitError,
            httpx.TransportError,
            ConnectionError,
        ),
    ):
        return FailureClass.INFRA_UNAVAILABLE
    if isinstance(error, openai.APIStatusError) and error.status_code >= 500:
        return FailureClass.INFRA_UNAVAILABLE
    if isinstance(
        error,
        (PydanticValidationError, InstructorValidationError, ResponseParsingError, json.JSONDecodeError),
    ):
        return FailureClass.SCHEMA_VALIDATION
    return None


def classify_failure(error: BaseException) -> FailureClass:
    """The most specific class found anywhere in the error's cause chain."""
    saw_retry_exhaustion = False
    for candidate in _chain(error):
        found = _classify_one(candidate)
        if found is not None:
            return found
        saw_retry_exhaustion = saw_retry_exhaustion or isinstance(candidate, InstructorRetryException)
    # instructor only re-asks after a response failed validation, so exhausting its retries
    # with no more specific cause is a schema failure.
    return FailureClass.SCHEMA_VALIDATION if saw_retry_exhaustion else FailureClass.UNKNOWN


def failure_detail(error: BaseException, limit: int = ERROR_DETAIL_LIMIT) -> str:
    """The full error text for operators, bounded at `limit` characters."""
    text = f"{type(error).__name__}: {error}"
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [{len(text) - limit} more characters]"
