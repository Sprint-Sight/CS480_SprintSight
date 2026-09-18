"""
LLM Output Validation Harness for SprintSight
================================================
updated against real evaluator.py, llm_client.py, and assessment.py

Validates local LLM grading behaviour WITHOUT ground-truth grades, by testing
four properties that are checkable regardless:

  1. Structural validity     - do dimension calls parse & return valid JSON,
                                measured PER DIMENSION (evaluate_sprint
                                tolerates up to 4/5 dimension failures and
                                still returns an assessment -- only raises
                                if ALL 5 fail).

  2. Discriminative validity - does struggling < imbalanced < high_performing
                                hold, overall AND per rubric dimension?
                                (Per-dimension matters: with the current
                                5-field JiraTicket, "requirements" and
                                "code_quality" have much less structured
                                signal than "collaboration")

  3. Reliability              - variance of the RAW (unrounded) average score
                                across repeats -- overall_score itself is
                                rounded to an int by evaluator.py, which would
                                mask real variance if used directly.

  4. Cross-model agreement    - do independent models rank/score similarly?

Results:
  research/validation_results/raw_<timestamp>.jsonl      one row per run
  research/validation_results/summary_<timestamp>.json   aggregated metrics

  - Field is `assessment.rubric_scores`, not `.dimension_scores`.

  - overall_score is `round(average_score)` -- an int. This harness now
    recomputes the raw float average itself from rubric_scores for the
    reliability metric, since the rounding would hide real variance.

  - member_contributions is NOT populated by the current evaluator.py (it's
    only demonstrated with fake data in assessment.py's smoke test). There is
    currently nothing to run the evidence-grounding check against for member
    contributions -- only rubric_scores[*].evidence_citations exists today.

STILL UNCONFIRMED (flagging rather than guessing further):
  - The exact fixture names/callable-ness in schemas/fixtures.py. Your
    README implies factory functions (create_struggling_sprint(), etc.),
    but llm_client.py's own import statement -- from schemas.fixtures import high_performing_team, imbalanced_team, struggling_team
    
    -- uses bare names with no `create_` prefix and no call, which reads
    like pre-built ArtifactBundle instances, not factories. _load_fixture()
    below tries both conventions so this doesn't block you, but send
    fixtures.py to replace the guesswork with certainty.

  - Exact field types on RubricDimensionScore (schemas/rubrics_dimension_score.py)
    and SprintAssessment (schemas/sprint_assessment.py) -- inferred from how
    they're constructed in evaluator.py / assessment.py, not seen directly.
"""

import argparse, asyncio, json, mlflow, os, statistics, time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import schemas.fixtures as fixtures_module
from schemas.artifact_bundle import ArtifactBundle
from schemas.expected_orders import GENERAL_ORDER, COLLABORATION_ORDER, check_order
from services.evaluator import evaluate_sprint
from llmops.mlflow_config import start_mlflow

load_dotenv()  # Load environment variables from .env file

DIMENSIONS = ["code_quality", "testing", "documentation", "requirements", "collaboration"]

# Tries factory-function naming (per README) first, then bare-instance naming
# (per llm_client.py's own import) -- see "STILL UNCONFIRMED" above.
FIXTURE_CANDIDATES = {
    "struggling": ["create_struggling_sprint", "struggling_team"],
    #"imbalanced": ["create_imbalanced_sprint", "imbalanced_team"],
    "high_performing": ["create_high_performer_sprint", "high_performing_team"],
    "good_collab_low_output": ["good_collab_low_output_team"],
    "imbalanced_high_output": ["imbalanced_high_output_team"],
    # "one_free_rider": ["one_free_rider_team"],
    # "graduated_imbalance": ["graduated_imbalance_team"],
    "lone_contributor_poor_outcome": ["lone_contributor_poor_outcome_team"],
}

def _load_fixture(key: str) -> ArtifactBundle: # Load all 3 team types
    for name in FIXTURE_CANDIDATES[key]:
        candidate = getattr(fixtures_module, name, None)
        if candidate is not None:
            return candidate() if callable(candidate) else candidate
    raise AttributeError(
        f"Could not find a fixture for '{key}' in schemas.fixtures. "
        f"Tried: {FIXTURE_CANDIDATES[key]}. Update FIXTURE_CANDIDATES to match "
        f"your actual fixtures.py once you confirm the real names."
    )

@dataclass
class RunResult: # Stores the result of a single (model, fixture, repeat) run
    model: str
    fixture: str
    repeat_index: int
    timestamp: str
    success: bool                       # if assessment object was returned at all
    fully_succeeded: bool               # AND zero dimensions failed
    failed_dimensions: list             # dimensions that failed (all 5 if success=False)
    overall_score: Optional[int]        # rounded int, as returned by evaluator.py
    raw_average_score: Optional[float]  # recomputed float average from rubric_scores
    rubric_scores: Optional[dict]       # {dimension: score}
    evidence_citations: Optional[dict]  # {dimension: [citation, ...]}
    error: Optional[str]
    latency_seconds: Optional[float]

async def run_single(model: str, fixture_name: str, repeat_index: int) -> RunResult:
    bundle = _load_fixture(fixture_name)
    loop = asyncio.get_event_loop() # Get the current event loop to measure latency
    start = loop.time()
    try:
        assessment = await evaluate_sprint(bundle, model)
        latency = loop.time() - start # Measure latency after evaluation
 
        # rubric_scores = {r.dimension: r.score for r in assessment.rubric_scores}
        # evidence = {r.dimension: r.evidence_citations for r in assessment.rubric_scores}
        rubric_scores = {
            dim: getattr(assessment.rubric_scores, dim).score
            for dim in DIMENSIONS if getattr(assessment.rubric_scores, dim) is not None
        }
        evidence = {
            dim: getattr(assessment.rubric_scores, dim).evidence_citations
            for dim in DIMENSIONS if getattr(assessment.rubric_scores, dim) is not None
        }
        raw_average = sum(rubric_scores.values()) / len(rubric_scores) if rubric_scores else None
        failed = list(assessment.failed_dimensions or [])
 
        return RunResult(
            model=model,
            fixture=fixture_name,
            repeat_index=repeat_index,
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            fully_succeeded=(len(failed) == 0),
            failed_dimensions=failed,
            overall_score=assessment.overall_score,
            raw_average_score=round(raw_average, 3) if raw_average is not None else None,
            rubric_scores=rubric_scores,
            evidence_citations=evidence,
            error=None,
            latency_seconds=latency,
        )
    except Exception as e:  # evaluate_sprint raises when any required dimension fails
        latency = loop.time() - start
        return RunResult(
            model=model,
            fixture=fixture_name,
            repeat_index=repeat_index,
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=False,
            fully_succeeded=False,
            failed_dimensions=list(DIMENSIONS),
            overall_score=None,
            raw_average_score=None,
            rubric_scores=None,
            evidence_citations=None,
            error=f"{type(e).__name__}: {e}",
            latency_seconds=latency,
        )

async def run_all(models: list[str], repeats: int) -> list[RunResult]: # Run all combinations of models, fixtures, and repeats, collecting results
    results: list[RunResult] = []
    total = len(models) * len(FIXTURE_CANDIDATES) * repeats
    done = 0
    for model in models:
        print(f"\n=== Running model '{model}' with {repeats} repeats per fixture ===")
        for fixture_name in FIXTURE_CANDIDATES:
            for i in range(repeats):
                start_time = time.time()
                print(f"\nRunning model {model} on fixture {fixture_name}, repeat {i + 1}/{repeats}...\n")
                result = await run_single(model, fixture_name, i)
                results.append(result)
                done += 1
                status = "OK" if result.success else f"FAIL ({result.error})"
                partial = "" if result.fully_succeeded else f" [partial: {result.failed_dimensions} failed]"
                print(f"[{done}/{total}] {model} | {fixture_name} | run {i + 1}/{repeats} -> {status}{partial}")
                if result.latency_seconds is not None:
                                    mlflow.log_metric(
                                        f"latency_seconds/{model}/{fixture_name}",
                                        result.latency_seconds,
                                        step=i,
                                    )
            print(f"\nTIME TAKEN to run model {model} at repeat {i}: {time.time() - start_time:.2f} seconds\n")
    return results

def write_raw_results(results: list[RunResult], out_path: Path) -> None:
    with out_path.open("w") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")

'''
Compute pearson to measure cross-model agreement. Returns NaN if either input is constant (stddev=0).
'''
def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    mean_x, mean_y = sum(x) / n, sum(y) / n
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    std_x = sum((a - mean_x) ** 2 for a in x) ** 0.5
    std_y = sum((b - mean_y) ** 2 for b in y) ** 0.5
    if std_x == 0 or std_y == 0:
        return float("nan")
    return cov / (std_x * std_y)

# '''
# Checks each (lower, higher) pair in `pairs` against `means`: True if lower's mean
# is strictly less than higher's, None if either mean is missing. Independent checks,
# not a chain -- see EXPECTED_PAIRS/COLLABORATION_EXPECTED_PAIRS comments above.
# '''
# def _pairwise_validity(means: dict, pairs: list[tuple[str, str]]) -> dict:
#     result = {}
#     for lower, higher in pairs:
#         lo, hi = means.get(lower), means.get(higher)
#         result[f"{lower} < {higher}"] = lo < hi if lo is not None and hi is not None else None
#     return result

# Aggregates all RunResults into a summary dictionary with metrics for each model and cross-model agreement.
def compute_summary(results: list[RunResult]) -> dict:
    summary: dict = {"models": {}}
    models = sorted({r.model for r in results})
 
    for model in models: # Compute per-model metrics
        model_results = [r for r in results if r.model == model]
        successful = [r for r in model_results if r.success]
 
        # 1. Structural validity, at DIMENSION granularity (not just run granularity).
        # A failed run contributes 0/5; a successful run has all five dimensions.
        dim_attempts = len(model_results) * len(DIMENSIONS) # Total dimension calls attempted
        dim_successes = sum(len(DIMENSIONS) - len(r.failed_dimensions) for r in model_results)
        dimension_structural_validity_rate = round(dim_successes / dim_attempts, 3) if dim_attempts else 0.0
        run_returned_rate = round(len(successful) / len(model_results), 3) if model_results else 0.0
 
        # 2 & 3: overall discriminative validity + reliability, using the RAW
        # (unrounded) average, not evaluator.py's rounded overall_score.
        reliability, fixture_means = {}, {} # Reliability (stdev) and mean raw average score per fixture
        for fixture_name in FIXTURE_CANDIDATES:
            scores = [
                r.raw_average_score for r in successful
                if r.fixture == fixture_name and r.raw_average_score is not None
            ]
            reliability[fixture_name] = round(statistics.stdev(scores), 3) if len(scores) >= 2 else None
            fixture_means[fixture_name] = round(statistics.mean(scores), 3) if scores else None
 
        # Top-level (overall raw_average) check -- fixture_means/reliability
        # (computed just above) already give us real per-fixture stdevs, so
        # this gets the noise-band tolerance for free.
        pairwise_discriminative_validity = check_order(fixture_means, GENERAL_ORDER, reliability)
 
        # Per-dimension discriminative validity -- shows WHICH rubric dimensions
        # discriminate and which don't, using the dimension-appropriate order:
        # collaboration has its own chain (should NOT just track output volume),
        # the other four dimensions use GENERAL_ORDER.
        dimension_breakdown = {}
        for dim in DIMENSIONS:
            dim_means, dim_stdevs = {}, {}
            for fixture_name in FIXTURE_CANDIDATES:
                dim_scores = [
                    r.rubric_scores[dim] for r in successful
                    if r.fixture == fixture_name and r.rubric_scores and dim in r.rubric_scores
                ]
                dim_means[fixture_name] = round(statistics.mean(dim_scores), 3) if dim_scores else None
                dim_stdevs[fixture_name] = round(statistics.stdev(dim_scores), 3) if len(dim_scores) >= 2 else 0.0
 
            order = COLLABORATION_ORDER if dim == "collaboration" else GENERAL_ORDER
            dimension_breakdown[dim] = { # Store mean/stdev and pairwise discriminative validity for each dimension
                "mean_score_by_fixture": dim_means,
                "stdev_by_fixture": dim_stdevs,
                "pairwise_discriminative_validity": check_order(dim_means, order, dim_stdevs),
            }
 
        # Kept as its own top-level key for backward compatibility with existing
        # summary.json consumers (e.g. the research memo script) -- it's just a
        # reference to what the loop above already computed for collaboration,
        # not a second computation, so it can't drift out of sync with it the
        # way the old separately-computed version could.
        collaboration_pairwise_discriminative_validity = dimension_breakdown["collaboration"]["pairwise_discriminative_validity"]
 
        # Does good_collab_low_output score collaboration noticeably higher than
        # its own other 4 dimensions? Verifies the model can differentiate
        # collaboration quality from delivery quality on the SAME team, not just
        # track overall quality across different teams.
        collab_mean = dimension_breakdown["collaboration"]["mean_score_by_fixture"].get("good_collab_low_output")
        output_dims = ["code_quality", "testing", "documentation", "requirements"]
        output_means = [dimension_breakdown[d]["mean_score_by_fixture"].get("good_collab_low_output") for d in output_dims]
        if collab_mean is not None and all(m is not None for m in output_means):
            collaboration_output_divergence_holds = (collab_mean - sum(output_means) / len(output_means)) > 1.5
        else:
            collaboration_output_divergence_holds = None
 
        summary["models"][model] = { # Store all computed metrics for this model
            "run_returned_rate": run_returned_rate,
            "dimension_structural_validity_rate": dimension_structural_validity_rate,
            "mean_raw_average_score_by_fixture": fixture_means,
            "raw_average_score_stdev_by_fixture": reliability,
            "pairwise_discriminative_validity": pairwise_discriminative_validity,
            "collaboration_pairwise_discriminative_validity": collaboration_pairwise_discriminative_validity,
            "collaboration_output_divergence_holds": collaboration_output_divergence_holds,
            "dimension_breakdown": dimension_breakdown,
            "n_runs": len(model_results),
            "n_runs_fully_failed": len(model_results) - len(successful),
        }
 
    # 4. Cross-model agreement: correlate each model pair's mean-score profile across fixtures
    if len(models) >= 2:
        agreement = {}
        for i, m1 in enumerate(models): # Compute Pearson correlation for each pair of models
            for m2 in models[i + 1:]: # Avoid double-counting pairs (m1, m2) and (m2, m1)
                means1 = [summary["models"][m1]["mean_raw_average_score_by_fixture"][f] for f in FIXTURE_CANDIDATES]
                means2 = [summary["models"][m2]["mean_raw_average_score_by_fixture"][f] for f in FIXTURE_CANDIDATES]
                if all(v is not None for v in means1 + means2): # Only compute Pearson if both models have valid means for all fixtures
                    agreement[f"{m1} vs {m2}"] = round(_pearson(means1, means2), 3)
                else: # If either model has missing means for any fixture, we cannot compute Pearson correlation
                    agreement[f"{m1} vs {m2}"] = None
        summary["cross_model_agreement_pearson_r"] = agreement
 
    return summary

def main() -> None:
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description="SprintSight LLM output validation harness")
    parser.add_argument( # Add required argument for model tags to compare
        "--models", nargs="+", required=True,
        help="Ollama model tags to compare, e.g. sprintsight-grader qwen2.5:7b mistral:7b",
    )
    parser.add_argument( # Add optional argument for number of repeats per (model, fixture) pair
        "--repeats", type=int, default=5,
        help="Repeats per (model, fixture) pair -- drives the reliability metric",
    )
    parser.add_argument("--out-dir", type=str, default="research/validation_results")
    args = parser.parse_args()
 
    out_dir = Path(args.out_dir) # Create output directory if it doesn't exist
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
 
    total = len(args.models) * len(FIXTURE_CANDIDATES) * args.repeats # Total no. of evaluations to be run
    print(f"Running {len(args.models)} models x {len(FIXTURE_CANDIDATES)} fixtures x {args.repeats} repeats = {total} evaluations")
    print(
        "Note: evaluator.py's semaphore caps concurrency to 1 within each evaluate_sprint call, "
        "so each run takes roughly (5 dimension calls x per-call latency), sequentially. "
        "For a first smoke test, try --repeats 1 with a single model before committing to the full grid.\n"
    )
 
    start_mlflow(experiment_name="SprintSight-Research")
 
    if mlflow.active_run():
        mlflow.end_run()  # Close any active run left open from a previous call
 
    with mlflow.start_run(run_name=f"Harness_Run_{ts}"):
        mlflow.log_param("models_tested", args.models)
        mlflow.log_param("repeats", args.repeats)
        mlflow.log_param("total_evaluations", total)
 
        # Inside the run now, so every evaluate_sprint() trace generated
        # during run_all() nests under this run instead of floating
        # unassociated in the experiment.
        results = asyncio.run(run_all(args.models, args.repeats))
 
        raw_path = out_dir / f"raw_{ts}.jsonl"
        write_raw_results(results, raw_path)
        print(f"\nRaw results written to {raw_path}")
 
        summary = compute_summary(results)
        summary_path = out_dir / f"summary_{ts}.json"
        with summary_path.open("w") as f:
            json.dump(summary, f, indent=2)
        print(f"Summary written to {summary_path}\n")
        print(json.dumps(summary, indent=2))
 
        mlflow.log_artifact(local_path=str(raw_path), artifact_path="dataset")
        mlflow.log_artifact(local_path=str(summary_path), artifact_path="dataset")
 
        for model in summary["models"]: # Log top-level metrics to dashboard
            validity = summary["models"][model]["dimension_structural_validity_rate"]
            mlflow.log_metric(f"{model}_structural_validity", validity)
 
            # Aggregated grading-time metrics -- the clean single-number
            # comparison to pair with the per-repeat time series logged
            overall_latency = summary["models"][model].get("overall_mean_latency_seconds")
            if overall_latency is not None:
                mlflow.log_metric(f"mean_latency_seconds/{model}/overall", overall_latency)
            for fixture_name, mean_lat in summary["models"][model].get("mean_latency_seconds_by_fixture", {}).items():
                if mean_lat is not None:
                    mlflow.log_metric(f"mean_latency_seconds/{model}/{fixture_name}", mean_lat)
 
    print("Research results successfully logged to MLflow!")

if __name__ == "__main__":
    main()