import logging
from mlflow import MlflowClient
from mlflow.genai import load_prompt, register_prompt, set_prompt_alias
from prompts.templates import render_sprint_feedback_prompt
from schemas.rubrics_dimension_score import DimensionName

log = logging.getLogger(__name__)

CHALLENGER_ALIAS = "challenger" # non-production alias for newly registered prompts, awaiting promotion by judge
PRODUCTION_ALIAS = "production"

def get_production_prompt(prompt_name):
    try:
        return load_prompt(f"prompts:/{prompt_name}@{PRODUCTION_ALIAS}")
    except Exception as e:
        log.warning(f"No production prompt for '{prompt_name}': {e}")
        print("No production prompt for '{prompt_name}': {e}")
        return None

def assign_prompt_alias(name: DimensionName, alias: str, version: str):
    set_prompt_alias(name, alias, version)
    log.info(f"Set prompt alias '{alias}' for prompt '{name}', version {version}.")
    print(f"Set prompt alias '{alias}' for prompt '{name}', version {version}.")

def get_sprint_feedback_prompt_template():
    return render_sprint_feedback_prompt(
        "{{ team_id }}",
        "{{ sprint_id }}",
        "{{ scores_data }}",
        "{{ instructor_expectations }}",
        "{{ project_context }}",
    )

def register_sprint_feedback_prompt(sprint_feedback_prompt_name, client: MlflowClient):
    version = _is_prompt_registered(sprint_feedback_prompt_name, get_sprint_feedback_prompt_template(), client)
    if version is not None:
        log.info(f"Sprint feedback prompt '{sprint_feedback_prompt_name}' is already registered.")
        print(f"Sprint feedback prompt '{sprint_feedback_prompt_name}' is already registered.")
        return
    log.info(f"Registering sprint feedback prompt '{sprint_feedback_prompt_name}'.")
    print(f"Registering sprint feedback prompt '{sprint_feedback_prompt_name}'.")
    return register_prompt(
        sprint_feedback_prompt_name,
        get_sprint_feedback_prompt_template(),
        tags={'author': 'SprintSight'},
        commit_message='Prompt for sprint-leve feedback generation',
    )
    
# Evaluator calls this method, converting the dictionary prompt name -> prompt template to list prompts_list
def register_all_dimension_prompts(prompts_list: list, client: MlflowClient, experiment_exist: bool) -> dict:
    prompt_versions_registered = {} # Store prompt versions for each of the dimension prompts registered in this run
    for dimension_prompt in prompts_list:
        _register_dimension_prompt( # Prompt name for each dimension will always be the same no matter what
            name=f"Evaluate_{dimension_prompt[0]}",
            template=dimension_prompt[1],
            tags={"dimension": dimension_prompt[0]},
            prompt_versions_registered=prompt_versions_registered, 
            client=client,
            experiment_exist=experiment_exist
        )
    return prompt_versions_registered

def _register_dimension_prompt(name: str, template: str, tags: dict, prompt_versions_registered: dict, client: MlflowClient, experiment_exist: bool):
    if not experiment_exist:
        _register_prompt(name, template, tags, prompt_versions_registered)
    existing = _is_prompt_registered(name, template, client)
    if existing is not None: # Check if current dimension prompt is already registered
        log.info(f"Prompt {name} is already registered in MLflow prompt registry.\n")
        print(f"Prompt {name} is already registered in MLflow prompt registry.\n")
        prompt_versions_registered[name] = existing.version
        return
    _register_prompt(name, template, tags, prompt_versions_registered)

def _is_prompt_registered(dimension_prompt_name, dimension_prompt_template, client: MlflowClient):
    versions = client.search_prompt_versions(dimension_prompt_name) # Get all prompt version given dimension prompt name
    for version in versions:
        prompt_version = client.get_prompt_version(dimension_prompt_name, version.version)
        if prompt_version.template == dimension_prompt_template:
            return prompt_version # Return PromptVersion object
    return None

def _register_prompt(name, template, tags, prompt_versions_registered):
    registered_prompt = register_prompt(name=name, template=template, tags=tags)
    assign_prompt_alias(name, CHALLENGER_ALIAS, registered_prompt.version) # Assign alias first to challenger by default
    prompt_versions_registered[name] = registered_prompt.version
    print(f"Registered prompt '{name}' with alias '{CHALLENGER_ALIAS}' in MLflow prompt registry.\n")
    log.info(f"Registered prompt '{name}' with alias '{CHALLENGER_ALIAS}' version {registered_prompt.version} in MLflow prompt registry.\n")