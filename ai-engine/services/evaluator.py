import asyncio, mlflow
from schemas.artifact_bundle import ArtifactBundle
from schemas.assessment import SprintAssessment, RubricDimensionScore
from services.llm_client import evaluate_dimension
from llmops.mlflow_config import start_mlflow

'''
Receives bundle
call_llm for each dimension concurrently, aggregate results, and return a SprintAssessment. (asyncio.gather)
Builds SprtinAssessment object, return it back to assessment.py for caching and logging.
'''

@mlflow.trace(name="Evaluate_Complete_Sprint") # Trace the entire evaluation process for MLflow
async def evaluate_sprint(bundle: ArtifactBundle, model_name: str) -> SprintAssessment:
    """
    Orchestrates the grading process by calling the AI concurrently for each 
    dimension, then aggregates the results into the final SprintAssessment.
    """

    dimensions = [
        "code_quality", 
        "testing", 
        "documentation", 
        "requirements",  
        "collaboration"
    ]

    # Cap no. of concurrent calls to avoid overwhelming the LLM service (if your computer can take it, you can increase this 
    # number or remove the bounded evaluate function and semaphore entirely to allow full concurrency)
    semaphore = asyncio.Semaphore(1)  

    async def _bounded_evaluate(dim):
        async with semaphore:
            return await evaluate_dimension(bundle, dim, model_name)

    # 2. Create a list of asynchronous tasks (one for each dimension)
    tasks = [_bounded_evaluate(dim) for dim in dimensions]
    
    # 3. Execute all tasks concurrently (If one takes 5 seconds, all 5 take 5 seconds total, not 25 seconds
    # It will only run concurrently if you remove the semaphore portion above. Else it will run 1 by 1 instead
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        # mlflow.set_tag("error", str(e))
        raise RuntimeError(f"Failed to evaluate dimensions concurrently: {e}")

    # 4. Extract the results into our typed schema
    rubric_scores = list(results)
    
    # 5. Calculate a simple overall average for the executive summary (CAN BE RECTIFIED IF THIS IS TOO SIMPLE)
    total_score = sum(score.score for score in rubric_scores)
    average_score = total_score / len(dimensions)
    
    # 6. Generate a deterministic summary based on the math
    if average_score >= 8:
        summary = f"Excellent work this sprint. The team achieved an average score of {average_score}."
    elif average_score >= 5:
        summary = f"Satisfactory progress, but room for improvement. Average score: {average_score}."
    else:
        summary = f"The team struggled significantly this sprint. Average score: {average_score}."

    # 7. Assemble and return the Final Plate
    final_assessment = SprintAssessment(
        team_id=bundle.team_id,
        sprint_id=bundle.sprint_id,
        prompt_version="v1.0",  # This could be dynamic if you have a prompt registry
        rubric_scores=rubric_scores,
        overall_score=int(average_score),
        executive_summary=summary,
        key_recommendations=[summary], # For now, just echoing the summary; could be more nuanced based on rubric scores
        #member_contributions=[]  # Assuming this is part of the bundle
    )
    
    # Log the final score to MLflow for easy dashboard filtering
    mlflow.log_metric("average_team_score", average_score)
    
    return final_assessment