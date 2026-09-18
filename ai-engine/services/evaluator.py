import asyncio, logging, mlflow, time, os
from schemas.artifact_bundle import ArtifactBundle
from schemas.sprint_assessment import SprintAssessment
from schemas.rubrics_score import RubricsScore, DIMENSIONS, DIMENTION_PROMPTS
from schemas.rubrics_dimension_score import RubricDimensionScore
from services.llm_client import evaluate_dimension, generate_sprint_feedback
from llmops.mlflow_config import start_mlflow

'''
Receives a bundle, evaluates each rubric dimension serially, generates general
sprint feedback, and returns a SprintAssessment.
'''

start_mlflow(experiment_name="Sprintsight evaluation")  # Initialize MLflow tracking and prompt registry
log = logging.getLogger("sprintsight.evaluator")

@mlflow.trace(name="Evaluate_Complete_Sprint") # Trace the entire evaluation process for MLflow
async def evaluate_sprint(bundle: ArtifactBundle, model_name: str) -> SprintAssessment:
    """
    Evaluates each rubric dimension, then generates project-level sprint feedback.
    """

    start_time = time.time() # Set start time

    # Limit parallel requests to avoid overloading one local Ollama model.
    semaphore = asyncio.Semaphore(1)

    async def _bounded_evaluate(dim):
        async with semaphore:
            dimension_start = time.perf_counter()
            log.info("Starting rubric dimension '%s'", dim)
            try:
                result = await evaluate_dimension(bundle, dim, model_name, DIMENTION_PROMPTS[dim])
            except Exception:
                log.exception(
                    "Rubric dimension '%s' failed after %.2f seconds.",
                    dim,
                    time.perf_counter() - dimension_start,
                )
                raise
            log.info(
                "Completed rubric dimension '%s' with score %s in %.2f seconds. "
                "Justification: %s | Evidence: %s",
                dim,
                result.score,
                time.perf_counter() - dimension_start,
                result.justification,
                result.evidence_citations,
            )
            return result

    # 2. Create a list of asynchronous tasks (one for each dimension)
    tasks = [_bounded_evaluate(dim) for dim in DIMENSIONS] # For running with a semaphore to limit concurrency
    # tasks = [evaluate_dimension(bundle, dim, model_name) for dim in DIMENSIONS] # For concurrency
    
    # 3. Execute all tasks concurrently (If one takes 5 seconds, all 5 take 5 seconds total, not 25 seconds
    # It will only run concurrently if you remove the semaphore portion above. Else it will run 1 by 1 instead
    # rubric_scores: list[RubricDimensionScore] = []
    # failed_dimensions: list[str] = []
    
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # for dim, result in zip(dimensions, results):
        #     if isinstance(result, Exception):
        #         print(f"Dimension '{dim}' failed to score: {result}")
        #         failed_dimensions.append(dim)
        #     else:
        #         rubric_scores.append(result)

        scores_by_dim = {}
        failed_dimensions = {}

        for dim, result in zip(DIMENSIONS, results):
            if isinstance(result, Exception):
                failed_dimensions[dim] = str(result)
                # Guarantee every dimension is present in the response: a
                # missing dimension is worse than a clearly-flagged failed one.
                scores_by_dim[dim] = RubricDimensionScore(
                    dimension=dim,
                    score=1,
                    justification=(
                        "Automated evaluation failed for this dimension after "
                        f"all retries and could not be scored: {result}. "
                        "Manual review required."
                    ),
                    evidence_citations=[],
                    evaluation_failed=True,
                )
            else:
                scores_by_dim[dim] = result

    except Exception as e:
        # mlflow.set_tag("error", str(e))
        raise RuntimeError(f"Failed to evaluate dimensions concurrently: {e}")
    
    # 5. Calculate a simple overall average for the executive summary (CAN BE RECTIFIED IF THIS IS TOO SIMPLE)
    # total_score = sum(score.score for score in rubric_scores)
    # average_score = total_score / len(rubric_scores)

    rubric_scores = RubricsScore(**scores_by_dim)
    scored = rubric_scores.scored()
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
        overall_score=round(average_score),
        executive_summary=" ".join(summary_parts),
        strengths=strengths,
        weaknesses=weaknesses,
        key_recommendations=recommendations,
        # failed_dimensions=failed_dimensions,
    )
    
    # Log the final score to MLflow for easy dashboard filtering
    mlflow.log_metric("average_team_score", average_score)

    print(f"Evaluation by model {model_name} completed in {time.time() - start_time:.2f} seconds.")
    
    return final_assessment