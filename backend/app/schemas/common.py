from typing import Any

from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class SuccessEnvelope(BaseModel):
    data: Any
    message: str | None = None
