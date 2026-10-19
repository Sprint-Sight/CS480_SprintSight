"""Model-selection endpoint.

Exposes the catalogue of AI models an instructor can pick for a sprint
assessment. The frontend settings page already renders a model picker from a
hard-coded placeholder list (`LlmModelOption`); this endpoint returns the same
shape so that picker can be driven by the backend instead.

The `id` of each option is the exact value the AI engine expects as its
`model_name` (an Ollama tag matching ai-engine `schemas.modelname.ModelName`).
That is the value the frontend persists as the selected model and sends in the
`/assessments/assess` request body, so the ids here MUST stay in sync with the
tags that are actually built from ai-engine/models/Modelfile.*.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import get_settings
from app.dependencies.auth import require_faculty

router = APIRouter(prefix="/models", tags=["models"])


class ModelOption(BaseModel):
    # `id` is sent verbatim to the AI engine as model_name — keep it equal to
    # the Ollama tag / ai-engine ModelName value, not a display slug.
    id: str
    provider: Literal["OpenAI", "Ollama"]
    model: str
    description: str


class ModelCatalogResponse(BaseModel):
    models: list[ModelOption]
    # The model used when the caller does not choose one. Mirrors
    # settings.default_model_name (DEFAULT_MODEL_NAME env var).
    default_model_id: str


# Curated catalogue of the models that have a Modelfile under
# ai-engine/models/. All are served locally through Ollama. Kept as a plain
# module constant (rather than imported from the AI engine) because the backend
# and AI engine are separate services with no shared Python package.
_MODEL_CATALOG: list[ModelOption] = [
    ModelOption(id="sprintsight-llama", provider="Ollama", model="Llama 3",
                description="Local general-purpose model (Llama 3)."),
    ModelOption(id="sprintsight-qwen", provider="Ollama", model="Qwen 2.5",
                description="Local general-purpose model (Qwen 2.5)."),
    ModelOption(id="sprintsight-mistral", provider="Ollama", model="Mistral 7B",
                description="Local lightweight model (Mistral 7B)."),
    ModelOption(id="sprintsight-gemma", provider="Ollama", model="Gemma",
                description="Local lightweight model (Gemma)."),
    ModelOption(id="sprintsight-llama31", provider="Ollama", model="Llama 3.1 8B",
                description="Fast, low-VRAM baseline (Llama 3.1 8B)."),
    ModelOption(id="sprintsight-qwen25-32b", provider="Ollama", model="Qwen 2.5 32B",
                description="High-quality large model (Qwen 2.5 32B); slower, needs more VRAM."),
    ModelOption(id="sprintsight-r1-32b", provider="Ollama", model="DeepSeek-R1 32B",
                description="Reasoning-focused large model (DeepSeek-R1 32B); slowest."),
    ModelOption(id="sprintsight-coder-32b", provider="Ollama", model="Qwen 2.5 Coder 32B",
                description="Code-specialised large model (Qwen 2.5 Coder 32B)."),
]


@router.get("", response_model=ModelCatalogResponse)
def list_models(
    _faculty_user: Annotated[object, Depends(require_faculty)],
) -> ModelCatalogResponse:
    """List the AI models available for sprint assessment, plus the default.

    Restricted to faculty, matching the assessment endpoint that consumes the
    chosen model. The frontend can render its model picker from `models` and
    pre-select `default_model_id`; whatever id the user picks is sent back as
    `model_name` on the assess request.
    """
    return ModelCatalogResponse(
        models=_MODEL_CATALOG,
        default_model_id=get_settings().default_model_name,
    )
