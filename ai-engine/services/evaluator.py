import asyncio
import logging
import os
import time

import mlflow
from mlflow.entities import SpanType

from prompts.dimension_criteria import DIMENSION_PROMPTS, DIMENSIONS
from schemas.all_dimensions_failed_error import AllDimensionsFailedError
from schemas.artifact_bundle import ArtifactBundle
from schemas.rubrics_dimension_score import DimensionName, RubricDimensionScore
from schemas.rubrics_score import RubricsScore
from schemas.sprint_assessment import SprintAssessment
from services.llm_client import (
    evaluate_dimension,
    find_loaded_model,
    generate_sprint_feedback,
    run_context,
    select_run_num_ctx,
    snapshot_loaded_models,
)

'''
Receives a bundle, evaluates each rubric dimension (serially unless
LLM_DIMENSION_CONCURRENCY is raised), generates general
sprint feedback, and returns a SprintAssessment.
'''
#start_mlflow(experiment_name="Sprintsight evaluation")  # Initialize MLflow tracking and prompt registry
log = logging.getLogger("sprintsight.evaluator")

# How many rubric dimensions call Ollama at once. 1 (default) runs them one
# after another. Higher values let one loaded model decode several dimensions
# together, which keeps the GPU busy while the client prepares and validates
# other calls. Ollama only runs OLLAMA_NUM_PARALLEL requests at once (set on
# the GPU job), so keep the two equal; extra requests just queue on the server.
# Batched decoding is not guaranteed bit-identical to one-at-a-time, so check
# scores against a concurrency-1 run before using a higher value for grading.
DIMENSION_CONCURRENCY = max(1, int(os.getenv("LLM_DIMENSION_CONCURRENCY", "1")))

async def _bounded_evaluate(dim: DimensionName, bundle: ArtifactBundle, model_name: str, run_num_ctx: int | None, semaphore: asyncio.Semaphore) -> RubricDimensionScore: # Bounded evaluation function to limit concurrent calls to the LLM service
    # Acquire the semaphore HERE, around the actual LLM call, so it genuinely
    # caps how many dimensions hit Ollama at once. (Wrapping task *creation*
    # instead does nothing — creating a coroutine runs no code.)
    async with semaphore:
        dimension_start = time.perf_counter()
        log.info("Starting rubric dimension '%s'", dim)
        try:
            result = await evaluate_dimension(bundle, dim, model_name, DIMENSION_PROMPTS[dim], num_ctx=run_num_ctx)
        except Exception:
            log.exception(
                "Rubric dimension '%s' failed after %.2f seconds.",
                dim,
                time.perf_counter() - dimension_start,
            )
            raise
        log.info( # Log the result of the dimension evaluation
            "Completed rubric dimension '%s' with score %s in %.2f seconds. "
            "Justification: %s | Evidence: %s",
            dim,
            result.score,
            time.perf_counter() - dimension_start,
            result.justification,
            result.evidence_citations,
        )
        return result

async def _log_gpu_offload(model_name: str) -> None:
    # Records how much of the model Ollama holds in VRAM, right after the
    # dimension calls (when it is certainly loaded). Telemetry only: a failure
    # here must never fail the assessment.
    try:
        loaded = await snapshot_loaded_models()
        mlflow.log_dict({"loaded_models": loaded}, "gpu/ollama_ps.json")
        entry = find_loaded_model(loaded, model_name)
        if entry is None or entry["offload_ratio"] is None:
            log.warning("Model '%s' was not in Ollama's loaded models (/api/ps): %s", model_name, loaded)
            return
        mlflow.log_metrics({
            "gpu_offload_ratio": entry["offload_ratio"],
            "gpu_model_vram_bytes": entry["size_vram"],
        })
        if entry["offload_ratio"] < 1:
            log.warning(
                ">>> Model '%s' is only %.0f%% on the GPU; Ollama put the rest on the CPU, which "
                "slows every token. Lower num_ctx / OLLAMA_NUM_PARALLEL or use a smaller KV cache type.",
                model_name, entry["offload_ratio"] * 100,
            )
    except Exception:  # telemetry must not break grading
        log.warning("Could not record GPU offload for model '%s'.", model_name, exc_info=True)

# Evaluates each rubric dimension, then generates project-level sprint feedback.
async def evaluate_sprint(bundle: ArtifactBundle, model_name: str, experiment_name: str) -> SprintAssessment:

    # Start Mlflow experiment
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment(experiment_name)
     
    # if mlflow.active_run(): # Play safe and close any active run from previous call (if any)
    #     mlflow.end_run()

    # Sized ONCE for the whole run (not per-dimension) and reused for every
    # call below, including sprint feedback: Ollama reloads the model
    # whenever num_ctx changes between requests, so varying it per-dimension
    # would force a reload before nearly every one of the ~6-7 calls here.
    run_num_ctx = select_run_num_ctx(bundle, model_name, DIMENSIONS)

    # run_context tags every request marker with this MLflow run, so GPU
    # telemetry can be matched to the run it belongs to.
    with mlflow.start_run(run_name=f"Evaluate_Sprint_{bundle.team_id}_{bundle.sprint_id}_{model_name}", nested=True) as run, \
            run_context(run_id=run.info.run_id, concurrency=DIMENSION_CONCURRENCY):
        with mlflow.start_span(name="Evaluate_Complete_Sprint", span_type=SpanType.CHAIN):
            mlflow.log_param("dimension_concurrency", DIMENSION_CONCURRENCY)
            start_time = time.time() # Start time for entire evaluation process
            mlflow.openai.autolog() # Logs everything, will create child AsyncCompletions span under LLM span

            # Cap no. of concurrent calls to the LLM service (LLM_DIMENSION_CONCURRENCY, see top of file)
            semaphore = asyncio.Semaphore(DIMENSION_CONCURRENCY)

            # 2. Create one task per dimension. Each task acquires the semaphore
            #    itself (inside _bounded_evaluate), so at most `semaphore` value
            #    dimensions call the LLM concurrently — the rest wait their turn.
            tasks = [_bounded_evaluate(dim, bundle, model_name, run_num_ctx, semaphore) for dim in DIMENSIONS]

            # 3. Schedule all tasks at once; the semaphore (not gather) is what
            #    limits real concurrency. With a cap of N, wall-clock is roughly
            #    ceil(6 / N) sequential batches of dimension calls.

            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # for dim, result in zip(dimensions, results):
                #     if isinstance(result, Exception):
                #         print(f"Dimension '{dim}' failed to score: {result}")
                #         failed_dimensions.append(dim)
                #     else:
                #         rubric_scores.append(result)

                scores_by_dim: dict[str, RubricDimensionScore] = {}
                failed_dimensions: dict[str, str] = {}

                for dim, result in zip(DIMENSIONS, results):
                    if isinstance(result, BaseException):
                        failed_dimensions[dim] = str(result)
                        # Guarantee every dimension is present in the response: a
                        # missing dimension is worse than a clearly-flagged failed one.
                        # Truncated: `justification` now has max_length=500 (see
                        # schemas/rubrics_dimension_score.py), and an unbounded
                        # exception message could otherwise fail this fallback
                        # construction itself while already handling a failure.
                        error_summary = str(result)[:300]
                        scores_by_dim[dim] = RubricDimensionScore(
                            dimension=dim,
                            score=1,
                            justification=(
                                "Automated evaluation failed for this dimension after "
                                f"all retries and could not be scored: {error_summary}. "
                                "Manual review required."
                            ),
                            evidence_citations=[],
                            evaluation_failed=True,
                        )
                    else:
                        scores_by_dim[dim] = result

            except Exception as e:  # noqa: BLE001 - translate concurrent-task failure into a domain error
                # mlflow.set_tag("error", str(e))
                raise RuntimeError(f"Failed to evaluate dimensions concurrently: {e}")

            await _log_gpu_offload(model_name)

            if len(failed_dimensions) == len(DIMENSIONS):
                raise AllDimensionsFailedError(failed_dimensions)

            rubric_scores = RubricsScore(**scores_by_dim)
            scored = [s for s in rubric_scores.scored() if not s.evaluation_failed]
            average_score = sum(s.score for s in scored) / len(scored) if scored else 0

            summary_parts = []
            if failed_dimensions:
                failure_details = "; ".join(
                    f"{dimension}: {error}" for dimension, error in failed_dimensions.items()
                )
                summary_parts.append(
                    f"The assessment is incomplete. Failed dimensions: {failure_details}"
                )
            else:
                summary_parts.append("All rubric dimensions were evaluated successfully.")
        
            feedback = None
            try:
                feedback = await generate_sprint_feedback(
                    bundle,
                    {dimension: score.model_dump() for dimension, score in scores_by_dim.items()},
                    model_name,
                    num_ctx=run_num_ctx,
                )
            except Exception:
                log.exception("General sprint feedback generation failed.")
        
            strengths = feedback.strengths if feedback else []
            weaknesses = feedback.weaknesses if feedback else []
            recommendations = feedback.recommendations if feedback else []
            if failed_dimensions:
                recommendations.append("Re-run the failed rubric dimensions before relying on this report.")
    
        final_assessment = SprintAssessment(
            team_id=bundle.team_id,
            sprint_id=bundle.sprint_id,
            prompt_version="v1.0",
            rubric_scores=rubric_scores,
            overall_score=round(average_score, 2),
            executive_summary=" ".join(summary_parts),
            strengths=strengths,
            weaknesses=weaknesses,
            key_recommendations=recommendations,
            # failed_dimensions=failed_dimensions,
        )
    log.info("Evaluation by model %s completed in %.2f seconds.", model_name, time.time() - start_time)
    print(f"Evaluation by model {model_name} completed in {time.time() - start_time:.2f} seconds.")
    return final_assessment