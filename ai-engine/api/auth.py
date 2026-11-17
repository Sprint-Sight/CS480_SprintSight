"""Service-to-service authentication for the engine's HTTP API.

The engine runs GPU grading for whoever can reach it, so when AI_ENGINE_SERVICE_TOKEN is set every
request must carry it in the X-Service-Token header (the backend sends it). When it is unset the
engine stays open, as in a single-machine demo; main.py logs a warning at startup.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status

TOKEN_ENV = "AI_ENGINE_SERVICE_TOKEN"


def service_token_configured() -> bool:
    return bool(os.getenv(TOKEN_ENV, "").strip())


def require_service_token(x_service_token: str | None = Header(default=None)) -> None:
    expected = os.getenv(TOKEN_ENV, "").strip()
    if not expected:
        return
    if not x_service_token or not hmac.compare_digest(x_service_token.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token.")
