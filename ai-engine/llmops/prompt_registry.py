import logging

from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from mlflow.genai import load_prompt, register_prompt, set_prompt_alias

from prompts.dimension_criteria import DIMENSION_PROMPTS
from prompts.templates import render_sprint_feedback_prompt

log = logging.getLogger(__name__)

CHALLENGER_ALIAS = "challenger" # non-production alias for newly registered prompts, awaiting promotion by judge
PRODUCTION_ALIAS = "production"

def get_production_prompt(prompt_name):
    try:
        return load_prompt(f"prompts:/{prompt_name}@{PRODUCTION_ALIAS}")
    except MlflowException as e:
        log.warning("No production prompt for '%s': %s", prompt_name, e)
        print(f"No production prompt for '{prompt_name}': {e}")
        return None

def assign_prompt_alias(name: str, alias: str, version: str):
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
    existing = _is_prompt_registered(sprint_feedback_prompt_name, get_sprint_feedback_prompt_template(), client)
    if existing is not None:
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
def register_all_dimension_prompts(
    prompts_list: list[tuple[str, str]] | None = None,
    client: MlflowClient | None = None,
) -> dict[str, str]:
    if prompts_list is None:
        prompts_list = list(DIMENSION_PROMPTS.items())
    if client is None:
        client = MlflowClient()
    prompt_versions_registered: dict[str, str] = {}
    for dimension_prompt in prompts_list:
        _register_dimension_prompt( # Prompt name for each dimension will always be the same no matter what
            name=f"Evaluate_{dimension_prompt[0]}",
            template=dimension_prompt[1],
            tags={"dimension": dimension_prompt[0]},
            prompt_versions_registered=prompt_versions_registered, 
            client=client,
        )
    return prompt_versions_registered

def register_prompt_if_changed(
    name: str,
    template: str,
    commit_message: str,
    alias: str,
    tags: dict[str, str] | None = None,
):
    """Register a prompt version only when its template differs, then set its alias."""
    client = MlflowClient()
    prompt = _is_prompt_registered(name, template, client)
    if prompt is None:
        prompt = register_prompt(
            name=name,
            template=template,
            tags=tags or {},
            commit_message=commit_message,
        )
    set_prompt_alias(name, alias, prompt.version)
    return prompt


def _register_dimension_prompt(
    name: str,
    template: str,
    tags: dict[str, str],
    prompt_versions_registered: dict[str, str],
    client: MlflowClient,
) -> None:
    existing = _is_prompt_registered(name, template, client)
    if existing is not None: # Check if current dimension prompt is already registered
        log.info(f"Prompt {name} is already registered in MLflow prompt registry.\n")
        print(f"Prompt {name} is already registered in MLflow prompt registry.\n")
        prompt_versions_registered[name] = existing.version
        return
    _register_prompt(name, template, tags, prompt_versions_registered)

def _is_prompt_registered(
    dimension_prompt_name: str,
    dimension_prompt_template: str,
    client: MlflowClient,
):
    if client.get_prompt(dimension_prompt_name) is None: # never registered; search_prompt_versions raises for an unknown name
        return None
    versions = client.search_prompt_versions(dimension_prompt_name) # Get all prompt version given dimension prompt name
    for version in versions:
        prompt_version = client.get_prompt_version(dimension_prompt_name, version.version)
        if prompt_version.template == dimension_prompt_template:
            return prompt_version # Return PromptVersion object
    return None

def _register_prompt(
    name: str,
    template: str,
    tags: dict[str, str],
    prompt_versions_registered: dict[str, str],
) -> None:
    registered_prompt = register_prompt(name=name, template=template, tags=tags)
    assign_prompt_alias(name, CHALLENGER_ALIAS, registered_prompt.version) # Assign alias first to challenger by default
    prompt_versions_registered[name] = str(registered_prompt.version)
    print(f"Registered prompt '{name}' with alias '{CHALLENGER_ALIAS}' in MLflow prompt registry.\n")
    log.info(f"Registered prompt '{name}' with alias '{CHALLENGER_ALIAS}' version {registered_prompt.version} in MLflow prompt registry.\n")
