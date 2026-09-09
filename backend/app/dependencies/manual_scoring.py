from fastapi import Request

from app.repositories.manual_override import (
    InMemoryManualOverrideRepository,
    ManualOverrideRepository,
)


def get_manual_override_repository(request: Request) -> ManualOverrideRepository:
    return getattr(
        request.app.state,
        "manual_override_repository",
        InMemoryManualOverrideRepository(),
    )
