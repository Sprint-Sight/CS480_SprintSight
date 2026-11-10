"""Failure classification: transient infrastructure vs schema vs length vs truncation."""

import httpx
import openai
import pytest
from instructor.core.exceptions import (
    IncompleteOutputException,
    InstructorRetryException,
)
from pydantic import ValidationError

from schemas.failure_class import FailureClass, describe_failure, is_transient
from schemas.rubrics_dimension_score import ModelOutput
from services.failures import (
    ERROR_DETAIL_LIMIT,
    PromptTruncatedError,
    classify_failure,
    failure_detail,
)

_REQUEST = httpx.Request("POST", "http://ollama:11434/v1/chat/completions")


def _exhausted_after(cause: BaseException) -> InstructorRetryException:
    """What instructor raises when its re-asks run out, chained to the last attempt's error."""
    try:
        try:
            raise cause
        except BaseException as inner:
            raise InstructorRetryException("retries exhausted", n_attempts=4, total_usage=None) from inner
    except InstructorRetryException as exc:
        return exc


def _schema_error() -> ValidationError:
    with pytest.raises(ValidationError) as raised:
        ModelOutput.model_validate({})
    return raised.value


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (openai.APITimeoutError(request=_REQUEST), FailureClass.TIMEOUT),
        (httpx.ReadTimeout("slow"), FailureClass.TIMEOUT),
        (TimeoutError(), FailureClass.TIMEOUT),
        (openai.APIConnectionError(request=_REQUEST), FailureClass.INFRA_UNAVAILABLE),
        (httpx.ConnectError("refused"), FailureClass.INFRA_UNAVAILABLE),
        (ConnectionResetError(), FailureClass.INFRA_UNAVAILABLE),
        (IncompleteOutputException(), FailureClass.OUTPUT_LENGTH),
        (PromptTruncatedError("did not fit"), FailureClass.CONTEXT_TRUNCATED),
        (_schema_error(), FailureClass.SCHEMA_VALIDATION),
        (ValueError("something else"), FailureClass.UNKNOWN),
    ],
)
def test_direct_errors_are_classified(error, expected) -> None:
    assert classify_failure(error) is expected


def test_timeout_is_found_underneath_instructors_retry_wrapper() -> None:
    wrapped = _exhausted_after(openai.APITimeoutError(request=_REQUEST))
    assert classify_failure(wrapped) is FailureClass.TIMEOUT


def test_validation_failure_underneath_the_retry_wrapper_is_a_schema_failure() -> None:
    assert classify_failure(_exhausted_after(_schema_error())) is FailureClass.SCHEMA_VALIDATION


def test_exhausted_retries_with_no_recorded_cause_count_as_schema_failure() -> None:
    bare = InstructorRetryException("retries exhausted", n_attempts=4, total_usage=None)
    assert classify_failure(bare) is FailureClass.SCHEMA_VALIDATION


def test_the_most_specific_cause_wins_over_the_wrapper() -> None:
    wrapped = _exhausted_after(httpx.ConnectError("refused"))
    assert classify_failure(wrapped) is FailureClass.INFRA_UNAVAILABLE


def test_only_infrastructure_failures_are_transient() -> None:
    transient = {FailureClass.TIMEOUT, FailureClass.INFRA_UNAVAILABLE}
    for failure_class in FailureClass:
        assert is_transient(failure_class) is (failure_class in transient)
    assert is_transient(None) is False
    assert is_transient("not-a-class") is False


def test_every_class_has_a_user_safe_description() -> None:
    for failure_class in FailureClass:
        text = describe_failure(failure_class)
        assert text and "http" not in text.lower()
    assert describe_failure("not-a-class") == describe_failure(FailureClass.UNKNOWN)


def test_failure_detail_keeps_the_full_message_up_to_the_limit() -> None:
    message = "x" * 1000  # the old code cut this at 300 characters
    assert failure_detail(ValueError(message)) == f"ValueError: {message}"


def test_failure_detail_is_bounded_and_says_what_was_cut() -> None:
    text = failure_detail(ValueError("y" * (ERROR_DETAIL_LIMIT * 3)))
    assert len(text) < ERROR_DETAIL_LIMIT + 100
    assert "more characters" in text
