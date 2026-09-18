import json
from typing import Any
from mlflow.genai.scorers import scorer
from schemas.rubrics_score import DIMENSIONS
from mlflow.entities import Trace, Feedback, SpanType, AssessmentSource, AssessmentSourceType

_CODE_SOURCE = AssessmentSource(source_type=AssessmentSourceType.CODE, source_id="numeric_grade_accuracy")

'''
numeric grade accuracy checks the following:
1. Per-dimension absolute error (candidate vs gold)
2. Overall score absolute error (candidate vs gold)
3. Aggregated Mean Absolute Error (MAE) across all dimensions
'''
@scorer(name="numeric_grade_accuracy")
def numeric_grade_accuracy(outputs: dict, expectations: dict) -> list[Feedback]:
    gold = expectations["gold"]
    candidate_rubric = (outputs or {}).get("rubric_scores") or {}
    gold_rubric = gold["rubric_scores"]
    
    feedbacks, diffs = [], []

    for dim in DIMENSIONS: # Per-dimension absolute error check
        cand_dim, gold_dim = candidate_rubric.get(dim), gold_rubric.get(dim)
        if cand_dim is None:
            feedbacks.append(Feedback( # Handle structural generation failures cleanly without skewing MAE
                name=f"grade_abs_error_{dim}", value=None,
                rationale=f"Candidate did not return a score for '{dim}'", source=_CODE_SOURCE
            ))
            continue
        
        diff = abs(cand_dim["score"] - gold_dim["score"])
        diffs.append(diff)
        feedbacks.append(Feedback(
            name=f"grade_abs_error_{dim}", value=diff,
            rationale=f"candidate={cand_dim['score']} gold={gold_dim['score']}", source=_CODE_SOURCE
        ))

    if outputs and "overall_score" in outputs: # Overall score absolute error check
        overall_diff = abs(outputs["overall_score"] - gold["overall_score"])
        feedbacks.append(Feedback(
            name="grade_abs_error_overall", value=overall_diff,
            rationale=f"candidate={outputs['overall_score']} gold={gold['overall_score']}", source=_CODE_SOURCE
        ))

    if diffs: # Aggregated MAE (MAE) across all dimensions
        mae = round(sum(diffs) / len(diffs), 4)
        feedbacks.append(Feedback(
            name="grade_mae_per_dimension", value=mae,
            rationale=f"MAE calculated across {len(diffs)} scored dimensions", source=_CODE_SOURCE
        ))

    return feedbacks

@scorer
def llm_response_time_good(trace: Trace) -> Feedback: # Check if LLM response time is acceptable
    # Search particular span type from the trace
    llm_spans = trace.search_spans(span_type=SpanType.LLM)
    if not llm_spans:
        return Feedback(
            value="no",
            rationale="No LLM span found in the trace execution.",
        )

    llm_span = llm_spans[0]
    response_time = (llm_span.end_time_ns - llm_span.start_time_ns) / 1e9  # convert to seconds
    max_duration = 5.0
    if response_time <= max_duration:
        return Feedback(
            value="yes",
            rationale=f"LLM response time {response_time:.2f}s is within the {max_duration}s limit.",
        )
    else:
        return Feedback(
            value="no",
            rationale=f"LLM response time {response_time:.2f}s exceeds the {max_duration}s limit.",
        )

# # KIV after LLM grades sprint
# span_check_eval_results = mlflow.genai.evaluate(
#     data=generated_traces, scorers=[llm_response_time_good]
# )

# Can ask AI create expectation_eval_data_list for fixtures & eventually the cs203 repos

@scorer # Grade based on presence of keywords in the LLM output, as specified in the expectations.
def keyword_presence_scorer(outputs: str, expectations: dict[str, Any]) -> Feedback:
    expected_keywords = expectations.get("expected_keywords")
    print(expected_keywords)
    if expected_keywords is None:
        return Feedback(value="yes", rationale="No keywords were expected in the response.")

    # Safely stringify dictionary outputs from SprintAssessment
    output_text = json.dumps(outputs) if isinstance(outputs, dict) else str(outputs)

    missing_keywords = []
    for keyword in expected_keywords:
        if keyword.lower() not in outputs.lower():
            missing_keywords.append(keyword)

    if not missing_keywords:
        return Feedback(value="yes", rationale="All expected keywords are present in the response.")
    else:
        return Feedback(value="no", rationale=f"Missing keywords: {', '.join(missing_keywords)}.")

# keyword_presence_eval_results = mlflow.genai.evaluate(
#     data=expectations_eval_dataset_list,
#     predict_fn=sample_app,  # sample_app is from the prerequisite section
#     scorers=[keyword_presence_scorer],
# )

