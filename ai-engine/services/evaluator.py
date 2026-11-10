import asyncio
import logging
import os
import threading
import time

import mlflow
from mlflow.entities import SpanType

from llmops.prompt_registry import (
    register_all_dimension_prompts,
    register_sprint_feedback_prompt,
)
from llmops.review_queue import add_to_review_queue
from llmops.run_tracking import TrackedRun, tracked_run
from prompts.dimension_criteria import (
    DIMENSION_PROMPTS,
    DIMENSIONS,
    SPRINT_FEEDBACK_PROMPT_NAME,
)
from schemas.all_dimensions_failed_error import AllDimensionsFailedError
from schemas.artifact_bundle import ArtifactBundle
from schemas.bundle_registry import remember_bundle
from schemas.failure_class import describe_failure
from schemas.modelname import MODEL_NUM_CTX
from schemas.rubrics_dimension_score import DimensionName, RubricDimensionScore
from schemas.rubrics_score import RubricsScore
from schemas.sprint_assessment import SprintAssessment
from services.failures import classify_failure, failure_detail
from services.llm_client import (
    evaluate_dimension,
    find_loaded_model,
    generate_sprint_feedback,
    run_context,
    select_run_num_ctx,
    snapshot_loaded_models,
)
from services.save_results import save_run_results

'''
Receives a bundle, evaluates each rubric dimension (serially unless
LLM_DIMENSION_CONCURRENCY is raised), generates general
sprint feedback, and returns a SprintAssessment.
'''
MAX_CONCURRENCY = 6  # Limit the number of concurrent calls to the LLM service to avoid overwhelming it. Adjust as needed based on your system's capabilities.
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

async def _bounded_evaluate(dim: DimensionName, bundle: ArtifactBundle, model_name: str, run_num_ctx: int | None, semaphore: asyncio.Semaphore, prompts) -> RubricDimensionScore: # Bounded evaluation function to limit concurrent calls to the LLM service
    # Acquire the semaphore HERE, around the actual LLM call, so it genuinely
    # caps how many dimensions hit Ollama at once. (Wrapping task *creation*
    # instead does nothing — creating a coroutine runs no code.)
    async with semaphore:
        dimension_start = time.perf_counter()
        log.info("Starting rubric dimension '%s'", dim)
        print(f"Starting rubric dimension '{dim}'...")
        try:
            result = await evaluate_dimension(bundle, dim, model_name, prompts[dim], num_ctx=run_num_ctx)
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
        print(f"Completed rubric dimension '{dim}' with score {result.score} in {time.perf_counter() - dimension_start:.2f} seconds. Justification: {result.justification} | Evidence: {result.evidence_citations}")
        return result

_autolog_lock = threading.Lock()
_autolog_enabled = False

def _ensure_openai_autolog() -> None:
    # openai autologging patches the SDK process-wide, so it is switched on once instead of on
    # every request (a second request re-patching while another is mid-call is needless churn).
    global _autolog_enabled
    with _autolog_lock:
        if not _autolog_enabled:
            mlflow.openai.autolog()  # Logs everything, will create child AsyncCompletions span under LLM span
            _autolog_enabled = True

async def _log_gpu_offload(model_name: str, run: TrackedRun | None = None) -> None:
    # Records how much of the model Ollama holds in VRAM, right after the
    # dimension calls (when it is certainly loaded). Telemetry only: a failure
    # here must never fail the assessment. With a TrackedRun it logs to that run by id;
    # without one it falls back to the fluent API's active run.
    try:
        loaded = await snapshot_loaded_models()
        log_dict = run.log_dict if run is not None else mlflow.log_dict
        log_metrics = run.log_metrics if run is not None else mlflow.log_metrics
        log_dict({"loaded_models": loaded}, "gpu/ollama_ps.json")
        entry = find_loaded_model(loaded, model_name)
        if entry is None or entry["offload_ratio"] is None:
            log.warning("Model '%s' was not in Ollama's loaded models (/api/ps): %s", model_name, loaded)
            return
        log_metrics({
            "gpu_offload_ratio": entry["offload_ratio"],
            "gpu_model_vram_bytes": entry["size_vram"],
            **({"gpu_context_length": entry["context_length"]} if entry.get("context_length") else {}),
        })
        configured = MODEL_NUM_CTX.get(model_name)
        if configured and entry.get("context_length") and entry["context_length"] != configured:
            log.warning(
                ">>> Model '%s' is loaded with a %d-token context but MODEL_NUM_CTX says %d; "
                "prompts are budgeted for the configured size. Align schemas/modelname.py and "
                "the Modelfile with the loaded value.",
                model_name, entry["context_length"], configured,
            )
        if entry["offload_ratio"] < 1:
            log.warning(
                ">>> Model '%s' is only %.0f%% on the GPU; Ollama put the rest on the CPU, which "
                "slows every token. Lower num_ctx / OLLAMA_NUM_PARALLEL or use a smaller KV cache type.",
                model_name, entry["offload_ratio"] * 100,
            )
    except Exception:  # telemetry must not break grading
        log.warning("Could not record GPU offload for model '%s'.", model_name, exc_info=True)

# Evaluates each rubric dimension, then generates project-level sprint feedback.
async def evaluate_sprint(bundle: ArtifactBundle, model_name: str, experiment_name: str, mlflow_client: mlflow.MlflowClient, trace_ids: list[str] | None = None, dimension_prompts=None) -> tuple[SprintAssessment, dict[str, int]]:

    if trace_ids is None:
        trace_ids = []
    
    remember_bundle(bundle)  # Store the bundle in a global registry for later retrieval by the judge

    # No mlflow.set_tracking_uri / set_experiment here: both are process-global, and this runs
    # inside an async route where concurrent requests share one thread. tracked_run() below
    # configures the tracking URI once and scopes the experiment to this request's context.
    _ensure_openai_autolog()

    # Register all dimension prompts in MLflow prompt registry
    prompts = dimension_prompts or DIMENSION_PROMPTS
    prompt_versions_registered = register_all_dimension_prompts(list(prompts.items()), mlflow_client)

    # Sized ONCE for the whole run (not per-dimension) and reused for every
    # call below, including sprint feedback: Ollama reloads the model
    # whenever num_ctx changes between requests, so varying it per-dimension
    # would force a reload before nearly every one of the ~6-7 calls here.
    run_num_ctx = select_run_num_ctx(bundle, model_name, DIMENSIONS)

    # run_context tags every request marker with this MLflow run, so GPU
    # telemetry can be matched to the run it belongs to.
    run_name = f"Evaluate_Sprint_{bundle.team_id}_{bundle.sprint_id}_{model_name}"
    with tracked_run(mlflow_client, experiment_name, run_name) as run, \
            run_context(run_id=run.run_id, concurrency=DIMENSION_CONCURRENCY), \
            mlflow.start_span(name="Evaluate_Complete_Sprint", span_type=SpanType.CHAIN) as root:
        run.link_current_trace()  # what the active run used to do implicitly
        run.log_param("dimension_concurrency", DIMENSION_CONCURRENCY)
        start_time = time.time() # Start time for entire evaluation process
        run.log_params({
            "model_name": model_name,
            "num_ctx": run_num_ctx,
        })
        run.set_tag("team_id", bundle.team_id)
        run.set_tag("sprint_id", bundle.sprint_id)

        trace_ids.append(root.trace_id)  # Add the root trace ID to the list of trace IDs for this evaluation

        mlflow.update_current_trace(
            request_preview=f"{model_name} evaluation of sprint {bundle.sprint_id} for team {bundle.team_id}",
            tags={"model": model_name, "team_id": bundle.team_id, "sprint_id": bundle.sprint_id, **{f"prompt.{name}": str(version) for name, version in prompt_versions_registered.items()}},
        )
        root.set_inputs({"team_id": bundle.team_id, "sprint_id": bundle.sprint_id, "model_name": model_name})

        # Cap no. of concurrent calls to the LLM service (LLM_DIMENSION_CONCURRENCY, see top of file)
        semaphore = asyncio.Semaphore(DIMENSION_CONCURRENCY)

        # 2. Create one task per dimension. Each task acquires the semaphore
        #    itself (inside _bounded_evaluate), so at most `semaphore` value
        #    dimensions call the LLM concurrently — the rest wait their turn.
        tasks = [_bounded_evaluate(dim, bundle, model_name, run_num_ctx, semaphore, prompts) for dim in DIMENSIONS]

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
            failed_dimensions: dict[str, str] = {}    # dimension -> "<failure_class>: <full error>"
            failure_classes: dict[str, str] = {}      # dimension -> failure_class

            for dim, result in zip(DIMENSIONS, results):
                if isinstance(result, BaseException):
                    # Classified, not truncated: a transient infrastructure failure (timeout,
                    # server down) and a schema failure call for different follow-up, and the
                    # full text is kept in error_detail for whoever investigates.
                    failure_class = classify_failure(result)
                    detail = failure_detail(result)
                    failure_classes[dim] = failure_class.value
                    failed_dimensions[dim] = f"{failure_class.value}: {detail}"
                    # Guarantee every dimension is present in the response: a missing
                    # dimension is worse than a clearly-flagged failed one. `justification`
                    # (max_length=500) gets only the short user-safe description; consumers
                    # must read evaluation_failed, never the placeholder score.
                    scores_by_dim[dim] = RubricDimensionScore(
                        dimension=dim,
                        score=1,
                        justification=(
                            f"Automated evaluation failed for this dimension: "
                            f"{describe_failure(failure_class)}. It could not be scored "
                            "and needs manual review."
                        ),
                        evidence_citations=[],
                        evaluation_failed=True,
                        failure_class=failure_class.value,
                        error_detail=detail,
                    )
                else:
                    scores_by_dim[dim] = result

        except Exception as e:  # noqa: BLE001 - translate concurrent-task failure into a domain error
            # mlflow.set_tag("error", str(e))
            raise RuntimeError(f"Failed to evaluate dimensions concurrently: {e}")

        await _log_gpu_offload(model_name, run)

        queue_name = f"review_queue_{bundle.team_id}_{bundle.sprint_id}" # Standby review queue for each team's sprint being evaluated in case trace needs to be flagged for review

        rubric_scores = RubricsScore(**scores_by_dim)
        scored = [s for s in rubric_scores.scored() if not s.evaluation_failed]
        average_score = sum(s.score for s in scored) / len(scored) if scored else 0

        summary_parts = []
        if failed_dimensions:
            # Short and user-safe: this sentence becomes part of the report students may see.
            # The full errors live on each dimension's error_detail and in the audit log.
            failure_summary = "; ".join(
                f"{dimension} ({describe_failure(failure_class)})"
                for dimension, failure_class in failure_classes.items()
            )
            summary_parts.append(
                f"The assessment is incomplete: {len(failed_dimensions)} of {len(DIMENSIONS)} "
                f"dimensions could not be scored automatically and need manual review "
                f"- {failure_summary}."
            )
            mlflow.update_current_trace(tags={
                "Flagged for review": "; ".join(f"{d}={c}" for d, c in failure_classes.items()),
            })
        else:
            summary_parts.append("All rubric dimensions were evaluated successfully.")
    
        feedback = None
        try:
            feedback = await generate_sprint_feedback(
                bundle,
                {dimension: score.model_dump(exclude={"prompt_version"}) for dimension, score in scores_by_dim.items()},
                model_name,
                num_ctx=run_num_ctx,
                sprint_feedback_prompt_name=SPRINT_FEEDBACK_PROMPT_NAME,
            )
            sprint_feedback_prompt = register_sprint_feedback_prompt(SPRINT_FEEDBACK_PROMPT_NAME, mlflow_client) # Ensure the sprint feedback prompt is registered in MLflow prompt registry
            
        except Exception:
            sprint_feedback_prompt = None
            log.exception("General sprint feedback generation failed.")
    
        strengths = feedback.strengths if feedback else []
        weaknesses = feedback.weaknesses if feedback else []
        recommendations = feedback.recommendations if feedback else []
        if failed_dimensions:
            recommendations.append("Re-run the failed rubric dimensions before relying on this report.")

        final_assessment = SprintAssessment(
            team_id=bundle.team_id,
            sprint_id=bundle.sprint_id,
            rubric_scores=rubric_scores,
            overall_score=round(average_score, 2),
            executive_summary=" ".join(summary_parts),
            strengths=strengths,
            weaknesses=weaknesses,
            key_recommendations=recommendations,
            prompt_version=str(sprint_feedback_prompt.version) if sprint_feedback_prompt else None,
            trace_id=root.trace_id,  # the backend stores it so a report can be joined to its judge verdict
        )

        run.log_metric("overall_score", average_score)
        for dim_name, score in scores_by_dim.items():
            if not score.evaluation_failed:
                run.log_metric(f"{dim_name}_score", score.score)
        run.log_metric("failed_dimensions_count", len(failed_dimensions))
        run.log_metric("evaluation_duration_seconds", time.time() - start_time)

        save_run_results(
            experiment_name=experiment_name,
            model_name=model_name,
            team_id=bundle.team_id,
            sprint_id=bundle.sprint_id,
            trace_id=root.trace_id,
            run_id=run.run_id,
            overall_score=average_score,
            scores_by_dim=scores_by_dim,
            failed_dimensions=failed_dimensions,
            failure_classes=failure_classes,
            prompt_versions=prompt_versions_registered,
            duration_seconds=time.time() - start_time,
        )

        root.set_outputs(final_assessment.model_dump(mode="json"))  # Store the final assessment in the root span outputs for traceability
        # Store the prompt versions used for each dimension & the sprint feedback prompt in the root span attributes for traceability
        root.set_attributes({"prompt_versions": {
            "version": {dim: prompt_versions_registered[f"Evaluate_{dim}"] for dim in DIMENSIONS},
            "sprint_feedback_prompt": final_assessment.prompt_version,
        }})

        mlflow.update_current_trace(response_preview=f"Average score: {average_score}, failed dimensions: {list(failed_dimensions.keys())}")

    if failed_dimensions:
        # Create and add trace to review queue for manual review if all dimensions failed
        mlflow.flush_trace_async_logging() # ensure all spans are written before the judge reads the trace
        add_to_review_queue(queue_name, [root.trace_id])
        if len(failed_dimensions) == len(DIMENSIONS):
            raise AllDimensionsFailedError(failed_dimensions)
    
    log.info("Evaluation by model %s completed in %.2f seconds.", model_name, time.time() - start_time)
    print(f"Evaluation by model {model_name} completed in {time.time() - start_time:.2f} seconds.")
    prompt_versions_int: dict[str, int] = {k: int(v) for k, v in prompt_versions_registered.items()}
    return final_assessment, prompt_versions_int