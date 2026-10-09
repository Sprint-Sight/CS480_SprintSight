import json
from typing import Any
from mlflow.genai.scorers import scorer
from schemas.rubrics_score import DIMENSIONS
from mlflow.entities import Trace, Feedback, SpanType, AssessmentSource, AssessmentSourceType

'''
numeric grade accuracy checks the following:
1. Per-dimension absolute error (candidate vs gold)
2. Overall score absolute error (candidate vs gold)
3. Aggregated Mean Absolute Error (MAE) across all dimensions
'''

_CODE_SOURCE = AssessmentSource(source_type=AssessmentSourceType.CODE, source_id="numeric_grade_accuracy")
MAX_ERROR = 9  # worst possible miss on a 1-10 scale (10 - 1)
BANDS = [(1, 2), (3, 5), (6, 8), (9, 10)]  # purpose of bands: if candidate and gold scores are in the same band, an instructor would likely agree with the candidate's score

def _band(score: int) -> int: # determine which band a score falls into (0..3). Same band = an instructor would agree.
    """Which band a score is in (0..3). Same band = an instructor would agree."""
    return next(i for i, (lo, hi) in enumerate(BANDS) if lo <= score <= hi)

@scorer(name="numeric_grade_accuracy")
def numeric_grade_accuracy(outputs: dict, expectations: dict) -> list[Feedback]:
    gold = expectations["gold"]
    candidate_rubric = (outputs or {}).get("rubric_scores") or {}
    gold_rubric = gold["rubric_scores"]
    
    abs_errors, signed_errors, feedbacks, band_hits = [], [], [], []

    for dim in DIMENSIONS: # Per-dimension absolute error check
        cand_dim, gold_dim = candidate_rubric.get(dim), gold_rubric.get(dim)
        if cand_dim is None or cand_dim.get("evaluation_failed") or gold_dim is None: # If either candidate or gold score is missing, report it
            feedbacks.append(Feedback(
                name=f"grade_abs_error_{dim}", value=None,
                rationale=f"Missing candidate or gold score for dimension '{dim}'", source=_CODE_SOURCE
            ))
            continue
        
        candidate_score, gold_score = cand_dim.get("score"), gold_dim.get("score")
        abs_errors.append(abs(candidate_score - gold_score))
        signed_errors.append(candidate_score - gold_score)
        band_hits.append(_band(candidate_score) == _band(gold_score)) # Check if candidate and gold scores are in the same band
        feedbacks.append(Feedback(name=f"grade_abs_error_{dim}", value=abs(candidate_score - gold_score),
            rationale=f"candidate={candidate_score} gold={gold_score}", source=_CODE_SOURCE
        ))

    total_dimensions, scored_dimensions = len(DIMENSIONS), len(abs_errors) # Total dimensions vs scored dimensions

    # Coverage check: if any dimension is missing/failed, report it
    feedbacks.append(Feedback(name="coverage_check", value=round(scored_dimensions / total_dimensions, 4),
                              rationale=f"Missing/failed dimensions count as MAX_ERROR (fixed penalty)", source=_CODE_SOURCE))

    # Penalised MAE: Missing dim counts as worst possible error
    penalised = (sum(abs_errors) + (total_dimensions - scored_dimensions) * MAX_ERROR) / total_dimensions
    feedbacks.append(Feedback(name="grade_penalised_mae", value=round(penalised, 4),
                              rationale=f"Missing dimensions count as the worst error", source=_CODE_SOURCE))

    if scored_dimensions:
        feedbacks += [
            Feedback(name="grade_mae_scored_only", # Average miss on the dimensions it did score (your old MAE).
                     value=round(sum(abs_errors) / scored_dimensions, 4), source=_CODE_SOURCE),
            Feedback(name="grade_bias", value=round(sum(signed_errors) / scored_dimensions, 4), # Bias: positive = too generous, negative = too harsh.
                     rationale="positive = generous, negative = harsh", source=_CODE_SOURCE),
            Feedback(name="grade_within_1_rate",  # Share of scores within 1 point of the human.
                     value=round(sum(e <= 1 for e in abs_errors) / scored_dimensions, 4), source=_CODE_SOURCE),
            Feedback(name="grade_band_agreement", # Share of scores landing in the same rubric band as the human.
                     value=round(sum(band_hits) / scored_dimensions, 4), source=_CODE_SOURCE),
        ]
    return feedbacks

# @scorer
# def llm_response_time_good(trace: Trace) -> Feedback: # Check if LLM response time is acceptable
#     # Search particular span type from the trace
#     # mlflow's SpanType is a plain str-constants class, not a real enum, so
#     # its own members don't structurally satisfy search_spans' stub signature.
#     llm_spans = trace.search_spans(span_type=SpanType.LLM)  # type: ignore[arg-type]
#     if not llm_spans:
#         return Feedback(
#             value="no",
#             rationale="No LLM span found in the trace execution.",
#         )

#     llm_span = llm_spans[0]
#     if llm_span.end_time_ns is None or llm_span.start_time_ns is None:
#         return Feedback(
#             value="no",
#             rationale="LLM span is missing start/end timestamps.",
#         )
#     response_time = (llm_span.end_time_ns - llm_span.start_time_ns) / 1e9  # convert to seconds
#     max_duration = 5.0
#     if response_time <= max_duration:
#         return Feedback(
#             value="yes",
#             rationale=f"LLM response time {response_time:.2f}s is within the {max_duration}s limit.",
#         )
#     else:
#         return Feedback(
#             value="no",
#             rationale=f"LLM response time {response_time:.2f}s exceeds the {max_duration}s limit.",
#         )

# # KIV after LLM grades sprint
# span_check_eval_results = mlflow.genai.evaluate(
#     data=generated_traces, scorers=[llm_response_time_good]
# )

# Can ask AI create expectation_eval_data_list for fixtures & eventually the cs203 repos

# @scorer # Grade based on presence of keywords in the LLM output, as specified in the expectations.
# def keyword_presence_scorer(outputs: str, expectations: dict[str, Any]) -> Feedback:
#     expected_keywords = expectations.get("expected_keywords")
#     print(expected_keywords)
#     if expected_keywords is None:
#         return Feedback(value="yes", rationale="No keywords were expected in the response.")

#     # Safely stringify dictionary outputs from SprintAssessment
#     output_text = json.dumps(outputs) if isinstance(outputs, dict) else str(outputs)

#     missing_keywords = []
#     for keyword in expected_keywords:
#         if keyword.lower() not in outputs.lower():
#         #if keyword.lower() not in output_text.lower():
#             missing_keywords.append(keyword)

#     if not missing_keywords:
#         return Feedback(value="yes", rationale="All expected keywords are present in the response.")
#     else:
#         return Feedback(value="no", rationale=f"Missing keywords: {', '.join(missing_keywords)}.")

# keyword_presence_eval_results = mlflow.genai.evaluate(
#     data=expectations_eval_dataset_list,
#     predict_fn=sample_app,  # sample_app is from the prerequisite section
#     scorers=[keyword_presence_scorer],
# )