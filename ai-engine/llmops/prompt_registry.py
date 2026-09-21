import logging
from typing import Optional

from mlflow.genai import load_prompt, register_prompt, set_prompt_alias

from prompts.dimension_criteria import DIMENSIONS, DIMENTION_PROMPTS
from prompts.templates import render_dimension_prompt

log = logging.getLogger(__name__)

# Substituted into render_dimension_prompt() in place of the real per-request
# bundle_data/computed_facts, so the registered template shows where they go
# without a second, hand-maintained copy of the wrapping instructions drifting
# out of sync with prompts/templates.py (which is what happened before).
_BUNDLE_DATA_PLACEHOLDER = "{{ bundle_data }}"
_COMPUTED_FACTS_PLACEHOLDER = "{{ computed_facts }}"


def dimension_prompt_template(dimension_name: str) -> str:
    """The exact prompt structure used at grading time for `dimension_name`
    (see prompts/templates.render_dimension_prompt), with bundle_data and
    computed_facts left as placeholders. Registered to the MLflow prompt
    registry for logging/versioning only -- services/llm_client.py always
    renders the real prompt locally and never fetches it back from here, so
    registry downtime can't break grading."""
    return render_dimension_prompt(
        dimension_name,
        DIMENTION_PROMPTS[dimension_name],
        _BUNDLE_DATA_PLACEHOLDER,
        _COMPUTED_FACTS_PLACEHOLDER,
    )

def register_dimension_prompt(dimension_name: str) -> None:
    try:
        # Only registers a new version if the "production" alias doesn't
        # already point at this exact template, so repeated calls (e.g. once
        # per startup) don't clutter the registry with identical versions.
        register_prompt_if_changed(
            name=f"Evaluate_{dimension_name}",
            template=dimension_prompt_template(dimension_name),
            commit_message=f"Prompt for dimension '{dimension_name}' evaluation",
            tags={"dimension": dimension_name, "author": "SprintSight"},
        )
    except Exception as e:
        raise RuntimeError(f"Failed to register prompt for dimension '{dimension_name}': {e}")

def register_all_dimension_prompts() -> None:
    """Call once at startup so every rubric dimension's live prompt is
    versioned in MLflow before any grading request arrives. Each dimension
    is registered independently so one failure doesn't block the others."""
    for dimension_name in DIMENSIONS:
        try:
            register_dimension_prompt(dimension_name)
        except Exception:
            log.exception("Failed to register prompt for dimension '%s'", dimension_name)


def register_prompt_if_changed(
    name: str,
    template: str,
    commit_message: str,
    alias: str = "production",
    tags: Optional[dict] = None,
) -> None:
    """Register a new prompt version only when no version carries `alias` yet
    or the aliased version's template differs from `template`. Safe to call
    repeatedly (e.g. once per request or at startup) without creating a new
    registry version and moving the alias each time the same template is
    registered again."""
    try:
        existing = load_prompt(f"prompts:/{name}@{alias}")
    except Exception:
        existing = None

    if existing is not None and getattr(existing, "template", None) == template:
        return

    prompt = register_prompt(name=name, template=template, commit_message=commit_message, tags=tags)
    set_prompt_alias(name, alias, prompt.version)

def load_dimension_prompt(dimension_name: str, alias: str = "production") -> str:
    try:
        return load_prompt(f"prompts:/Evaluate_{dimension_name}@{alias}")
    except Exception as e:
        print(f"Error loading prompt for dimension '{dimension_name}': {e}")
        return None  # Return None if prompt not found or any error occurs