"""Provenance for offline runs: which code, which Ollama server and which model weights.

Shared by the model-comparison runner and the judge study, which used to carry their own copies.
Every helper degrades to "unknown" / None instead of raising: a missing git checkout or an
unreachable Ollama is not an evaluation failure.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

import httpx


def _ollama_base() -> str:
    return (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434/v1").replace("/v1", "")


def git_sha() -> str:
    """Short SHA of HEAD, or "unknown" outside a git checkout."""
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001 - absent git is not an eval failure
        return "unknown"


def ollama_version() -> str | None:
    try:
        resp = httpx.get(f"{_ollama_base()}/api/version", timeout=5.0)
        resp.raise_for_status()
        return resp.json().get("version")
    except (httpx.HTTPError, ValueError):
        return None


def _show(model: str) -> Any:
    response = httpx.post(f"{_ollama_base()}/api/show", json={"name": model}, timeout=10.0)
    response.raise_for_status()
    return response.json()


def model_digest(model: str) -> str | None:
    """First 16 characters of the Ollama manifest digest, or None if unknown.

    A model TAG is not provenance: the same tag can be re-pulled at a different quantisation,
    which changes behaviour while leaving every run name identical. The digest pins the weights.
    """
    try:
        payload = _show(model)
        digest = payload.get("digest") or payload.get("model_info", {}).get("general.digest")
        return (digest or "")[:16] or None
    except Exception:  # noqa: BLE001 - absence of Ollama is not an eval failure
        return None


def model_family(model: str) -> tuple[str | None, str | None]:
    """(family, parent_model) for an Ollama tag, or (None, None) if unknown."""
    try:
        details = _show(model).get("details") or {}
        return details.get("family"), details.get("parent_model")
    except Exception:  # noqa: BLE001 - absence of Ollama is not an eval failure
        return None, None
