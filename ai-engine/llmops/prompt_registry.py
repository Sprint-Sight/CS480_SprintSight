import logging, hashlib, mlflow

from mlflow.genai import load_prompt, register_prompt, set_prompt_alias

from prompts.dimension_criteria import DIMENSION_PROMPTS, DIMENSIONS
from prompts.templates import render_dimension_prompt, render_sprint_feedback_prompt
from schemas.rubrics_dimension_score import DimensionName

log = logging.getLogger(__name__)

# Substituted into render_dimension_prompt() in place of the real per-request
# bundle_data/computed_facts, so the registered template shows where they go
# without a second, hand-maintained copy of the wrapping instructions drifting
# out of sync with prompts/templates.py (which is what happened before).
_PROMPT_ALIAS = "production"
_BUNDLE_DATA_PLACEHOLDER = "{{ bundle_data }}"
_COMPUTED_FACTS_PLACEHOLDER = "{{ computed_facts }}"
_SCORES_DATA_PLACEHOLDER = "{{ scores_data }}"
_INSTRUCTOR_EXPECTATIONS_PLACEHOLDER = "{{ instructor_expectations }}"
SPRINT_FEEDBACK_PROMPT_NAME = 'Generate_Sprint_Feedback'
_registered_versions: dict[str, str] = {}  # name -> version registered by this process
_template_hashes: dict[str, str] = {} # name -> hash of template registered by this process
_registered_in_experiments: set[str] = set() # experiment_id -> True if prompts registered for this experiment

def dimension_prompt_name(dimension_name: DimensionName) -> str:
    return f"Evaluate_{dimension_name}"

def sprint_feedback_prompt_template() -> str:
    return render_sprint_feedback_prompt("{{ team_id }}", "{{ sprint_id }}", _SCORES_DATA_PLACEHOLDER, _INSTRUCTOR_EXPECTATIONS_PLACEHOLDER)

def register_sprint_feedback_prompt() -> None:
    try:
        register_prompt_if_changed(
            name=SPRINT_FEEDBACK_PROMPT_NAME,
            template=sprint_feedback_prompt_template(),
            commit_message="Prompt for sprint-level feedback generation",
            tags={"author": "SprintSight"},
        )
    except Exception as e:
        raise RuntimeError(f"Failed to register sprint feedback prompt: {e}")

def load_sprint_feedback_prompt(alias: str = _PROMPT_ALIAS):
    try:
        return load_prompt(f"prompts:/Generate_Sprint_Feedback@{alias}")
    except Exception as e:
        print(f"Error loading sprint feedback prompt: {e}")
        return None

def dimension_prompt_template(dimension_name: DimensionName) -> str:
    return render_dimension_prompt(
        dimension_name,
        DIMENSION_PROMPTS[dimension_name],
        _BUNDLE_DATA_PLACEHOLDER,
        _COMPUTED_FACTS_PLACEHOLDER,
    )

def register_dimension_prompt(dimension_name: DimensionName) -> None:
    try:
        # Only registers a new version if the "production" alias doesn't
        # already point at this exact template, so repeated calls (e.g. once
        # per startup) don't clutter the registry with identical versions.
        register_prompt_if_changed(
            name=dimension_prompt_name(dimension_name),
            template=dimension_prompt_template(dimension_name),
            commit_message=f"Prompt for dimension '{dimension_name}' evaluation",
            tags={"dimension": dimension_name, "author": "SprintSight"},
        )
    except Exception as e:  # noqa: BLE001 - translate any registry failure into a domain error
        raise RuntimeError(f"Failed to register prompt for dimension '{dimension_name}': {e}")

# Call once at startup so every rubric dimension's live prompt is versioned
def register_all_dimension_prompts() -> None:
    for dimension_name in DIMENSIONS:
        try:
            register_dimension_prompt(dimension_name)
        except Exception:
            log.exception("Failed to register prompt for dimension '%s'", dimension_name)

# Register new prompt version whenever it differs
def register_prompt_if_changed(name, template, commit_message, alias=_PROMPT_ALIAS, tags=None):
    # Compute a hash of the template to detect changes. This is recorded even if the registry is down, so we can avoid unnecessary re-registration attempts in future runs.
    digest = hashlib.sha256(template.encode()).hexdigest()
    _template_hashes[name] = digest # recorded even if registry is down
    try:
        existing = load_prompt(f"prompts:/{name}@{alias}")
    except Exception:  # noqa: BLE001 - alias/version not existing yet is expected, not exceptional
        existing = None

    if existing is not None and getattr(existing, "template", None) == template:
        _registered_versions[name] = str(existing.version)
        return existing

    prompt = register_prompt(name=name, template=template, commit_message=commit_message, tags={**(tags or {}), "template_hash": digest})
    set_prompt_alias(name, alias, prompt.version)
    _registered_versions[name] = str(prompt.version)
    return prompt

def load_dimension_prompt(dimension_name: str, alias: str = "production") -> str | None:
    try:
        return load_prompt(f"prompts:/Evaluate_{dimension_name}@{alias}")
    except Exception as e:  # noqa: BLE001 - prompt lookup failure must not crash the caller
        print(f"Error loading prompt for dimension '{dimension_name}': {e}")
        return None  # Return None if prompt not found or any error occurs

def prompt_trace_attrs(name): # Template for trace attributes to record in MLflow for a given prompt name
    return {
        "prompt_name": name,
        "prompt_version": _registered_versions.get(name, "unregistered"),
        "prompt_template_sha256": _template_hashes.get(name),
    }

# Register every dimension prompt and the sprint feedback prompt at module load time, so they are available for use in any trace evaluation. This is idempotent and will not create duplicate versions if already registered.
def ensure_prompts_registered(force: bool = False):
    active = mlflow.tracking.fluent._get_experiment_id()
    if active in _registered_in_experiments and not force:
        return True

    failures = []
    for dimension_name in DIMENSIONS:
        try:
            register_dimension_prompt(dimension_name)
        except Exception as e:
            failures.append(f"Failed to register prompt for dimension '{dimension_name}': {e}")

    try:
        register_sprint_feedback_prompt()
    except Exception as e:
        failures.append(f"Failed to register '{SPRINT_FEEDBACK_PROMPT_NAME}': {e}")

    if failures:
        log.error("Prompt registration failures:\n%s", "\n".join(failures))
        return False
    
    _registered_in_experiments.add(active)
    log.info("Prompts registered for experiment '%s': %s", active, sorted(_registered_versions.items()))
    return True

def link_prompt_to_trace(name: str):
    version = _registered_versions.get(name)
    if not version:
        log.warning("Prompt '%s' has not been registered yet; cannot link to trace", name)
        return
    try:
        return load_prompt(f"prompts:/{name}/{version}") # versions use "/<n>"; @ for alias
    except Exception as e:
        log.warning("Failed to load prompt '%s' version '%s': %s", name, version, e)
        return None