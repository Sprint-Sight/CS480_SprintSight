import asyncio
import logging
import os
import time

import mlflow
from mlflow.entities import SpanType
from llmops.review_queue import add_to_review_queue
from llmops.prompt_registry import load_dimension_prompt, load_sprint_feedback_prompt, SPRINT_FEEDBACK_PROMPT_NAME, prompt_trace_attrs, ensure_prompts_registered, dimension_prompt_name
from prompts.dimension_criteria import DIMENSION_PROMPTS, DIMENSIONS#, WORSE_DIMENSION_PROMPTS
from schemas.all_dimensions_failed_error import AllDimensionsFailedError
from schemas.artifact_bundle import ArtifactBundle
from schemas.rubrics_dimension_score import DimensionName, RubricDimensionScore
from schemas.rubrics_score import RubricsScore
from schemas.sprint_assessment import SprintAssessment
from services.llm_client import (
    evaluate_dimension,
    generate_sprint_feedback,
    select_run_num_ctx,
)

'''
Receives a bundle, evaluates each rubric dimension serially, generates general
sprint feedback, and returns a SprintAssessment.
'''
MAX_CONCURRENCY = 6  # Limit the number of concurrent calls to the LLM service to avoid overwhelming it. Adjust as needed based on your system's capabilities.
#start_mlflow(experiment_name="Sprintsight evaluation")  # Initialize MLflow tracking and prompt registry
log = logging.getLogger("sprintsight.evaluator")

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

# Evaluates each rubric dimension, then generates project-level sprint feedback.
async def evaluate_sprint(bundle: ArtifactBundle, model_name: str, experiment_name: str) -> SprintAssessment:

    # Start Mlflow experiment
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment(experiment_name)
    ensure_prompts_registered()
     
    # if mlflow.active_run(): # Play safe and close any active run from previous call (if any)
    #     mlflow.end_run()

    # Sized ONCE for the whole run (not per-dimension) and reused for every
    # call below, including sprint feedback: Ollama reloads the model
    # whenever num_ctx changes between requests, so varying it per-dimension
    # would force a reload before nearly every one of the ~6-7 calls here.
    run_num_ctx = select_run_num_ctx(bundle, model_name, DIMENSIONS)
    run_name = f"Evaluate_Sprint_{bundle.team_id}_{bundle.sprint_id}_{model_name}"
    with mlflow.start_run(run_name=run_name, nested=True):
        with mlflow.start_span(name="Evaluate_Complete_Sprint", span_type=SpanType.CHAIN) as root:
            start_time = time.time() # Start time for entire evaluation process
            mlflow.openai.autolog() # Logs everything, will create child AsyncCompletions span under LLM span
            mlflow.log_params({
                "model_name": model_name,
                "num_ctx": run_num_ctx,
            })
            mlflow.set_tags({
                "team_id": bundle.team_id,
                "sprint_id": bundle.sprint_id,
            })

            mlflow.update_current_trace(
                request_preview=f"{model_name} evaluation of sprint {bundle.sprint_id} for team {bundle.team_id}",
                tags={"model": model_name, "team_id": bundle.team_id}
            )
            root.set_inputs({"team_id": bundle.team_id, "sprint_id": bundle.sprint_id, "model_name": model_name})

            # Cap no. of concurrent calls to avoid overwhelming the LLM service (if your computer can take it, you can increase this 
            # number or remove the bounded evaluate function and semaphore entirely to allow full concurrency)
            semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

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

            queue_name = f"review_queue_{bundle.team_id}_{bundle.sprint_id}" # Standby review queue for each team's sprint being evaluated in case trace needs to be flagged for review
            if len(failed_dimensions) == len(DIMENSIONS):
                # Create and add trace to review queue for manual review if all dimensions failed
                mlflow.update_current_trace(tags={"Flagged for review": "All dimensions failed to evaluate."})
                add_to_review_queue(queue_name, [root.trace_id])
                raise AllDimensionsFailedError(failed_dimensions)

            rubric_scores = RubricsScore(**scores_by_dim)
            scored = [s for s in rubric_scores.scored() if not s.evaluation_failed]
            average_score = sum(s.score for s in scored) / len(scored) if scored else 0

            summary_parts = []
            if failed_dimensions:
                add_to_review_queue(queue_name, [root.trace_id]) # Create and add trace to review queue for manual review if any dimensions failed
                failure_details = "; ".join(
                    f"{dimension}: {error}" for dimension, error in failed_dimensions.items()
                )
                summary_parts.append(
                    f"The assessment is incomplete. Failed dimensions: {failure_details}"
                )
                mlflow.update_current_trace(tags={"Flagged for review": failure_details})
            else:
                summary_parts.append("All rubric dimensions were evaluated successfully.")
        
            feedback = None
            try:
                feedback = await generate_sprint_feedback(
                    bundle,
                    {dimension: score.model_dump(exclude={"prompt_version"}) for dimension, score in scores_by_dim.items()},
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
                prompt_version=prompt_trace_attrs(SPRINT_FEEDBACK_PROMPT_NAME)["prompt_version"],
                rubric_scores=rubric_scores,
                overall_score=round(average_score, 2),
                executive_summary=" ".join(summary_parts),
                strengths=strengths,
                weaknesses=weaknesses,
                key_recommendations=recommendations,
                # failed_dimensions=failed_dimensions,
            )
            mlflow.log_metric("overall_score", average_score)
            for dim, score in scores_by_dim.items():
                if not score.evaluation_failed:
                    mlflow.log_metric(f"{dim}_score", score.score)
            mlflow.log_metric("failed_dimensions_count", len(failed_dimensions))
            mlflow.log_metric("evaluation_duration_seconds", time.time() - start_time)
            root.set_outputs(final_assessment.model_dump(mode="json"))  # Store the final assessment in the root span outputs for traceability
            # Store the prompt versions used for each dimension & the sprint feedback prompt in the root span attributes for traceability
            root.set_attributes({"prompt_versions": {
                "dimension_prompts": {dim: prompt_trace_attrs(dimension_prompt_name(dim))["prompt_version"] for dim in DIMENSIONS},
                "sprint_feedback_prompt": final_assessment.prompt_version,
            }})

            mlflow.update_current_trace(response_preview=f"Average score: {average_score}, failed dimensions: {list(failed_dimensions.keys())}")

    log.info("Evaluation by model %s completed in %.2f seconds.", model_name, time.time() - start_time)
    print(f"Evaluation by model {model_name} completed in {time.time() - start_time:.2f} seconds.")
    return final_assessment