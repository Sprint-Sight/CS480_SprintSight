import asyncio, mlflow, time, os
from schemas.artifact_bundle import ArtifactBundle
from schemas.sprint_assessment import SprintAssessment
from schemas.rubrics_score import RubricsScore, DIMENSIONS, DIMENTION_PROMPTS
from services.llm_client import evaluate_dimension
from llmops.mlflow_config import start_mlflow

'''
Receives bundle
call_llm for each dimension concurrently, aggregate results, and return a SprintAssessment. (asyncio.gather)
Builds SprtinAssessment object, return it back to assessment.py for caching and logging.
'''

start_mlflow(experiment_name="Sprintsight evaluation")  # Initialize MLflow tracking and prompt registry

@mlflow.trace(name="Evaluate_Complete_Sprint") # Trace the entire evaluation process for MLflow
async def evaluate_sprint(bundle: ArtifactBundle, model_name: str) -> SprintAssessment:
    """
    Orchestrates the grading process by calling the AI concurrently for each 
    dimension, then aggregates the results into the final SprintAssessment.
    """

    start_time = time.time() # Set start time

    # Cap no. of concurrent calls to avoid overwhelming the LLM service (if your computer can take it, you can increase this 
    # number or remove the bounded evaluate function and semaphore entirely to allow full concurrency)
    semaphore = asyncio.Semaphore(5)  

    async def _bounded_evaluate(dim):
        async with semaphore:
            return await evaluate_dimension(bundle, dim, model_name, DIMENTION_PROMPTS[dim])

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

        for dim, result in zip(DIMENSIONS, results):
            if isinstance(result, Exception):
                scores_by_dim.pop(dim, None)
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

    if not scored:
        raise RuntimeError(f"All {len(DIMENSIONS)} rubric dimensions failed to evaluate: {rubric_scores.failed_dimensions}")

    average_score = sum(s.score for s in scored) / len(scored)

    summary = ""

    # CALCULATE FAILED DIMENSIONS AND APPEND TO SUMMARY
    failed = rubric_scores.failed_dimensions
    if failed:
        summary += f''' Note: {len(failed)} dimension(s) could not be scored 
        ({', '.join(failed)}) and were excluded from this average.'''

    # Derive recommendations from the rubric dimensions' own AI-generated
    # areas_for_improvement values
    recommendations = []
    seen = set()
    for scored_item in scored:
        for item in scored_item.areas_for_improvement or []:
            normalized = str(item).strip()
            if normalized and normalized.lower() not in seen:
                recommendations.append(normalized)
                seen.add(normalized.lower())

    final_assessment = SprintAssessment(
        team_id=bundle.team_id,
        sprint_id=bundle.sprint_id,
        prompt_version="v1.0",
        rubric_scores=rubric_scores,
        overall_score=round(average_score),
        executive_summary=summary,
        key_recommendations=recommendations,
        # failed_dimensions=failed_dimensions,
    )
    
    # Log the final score to MLflow for easy dashboard filtering
    mlflow.log_metric("average_team_score", average_score)

    print(f"Evaluation by model {model_name} completed in {time.time() - start_time:.2f} seconds.")
    
    return final_assessment