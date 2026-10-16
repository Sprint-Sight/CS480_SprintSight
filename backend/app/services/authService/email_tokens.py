from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.security import TokenPayloadError
from app.repositories.interfaces import UserRecord


def create_email_action_token(user: UserRecord, purpose: str) -> str:
    if purpose not in {"first_time_password", "password_reset"}:
        raise ValueError("Unsupported email action.")

    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.email_action_token_expire_minutes,
    )
    payload: dict[str, Any] = {
        "sub": user.id,
        "token_version": user.token_version,
        "purpose": purpose,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_email_action_token(token: str, expected_purpose: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise TokenPayloadError("Email action token is invalid or expired.") from exc

    if (
        not payload.get("sub")
        or type(payload.get("token_version")) is not int
        or payload.get("purpose") != expected_purpose
    ):
        raise TokenPayloadError("Email action token is invalid or expired.")
    return payload


def email_action_message(token: str, purpose: str) -> tuple[str, str]:
    settings = get_settings()
    if purpose == "first_time_password":
        subject = "Set your SprintSight password"
        endpoint = "first-time-password"
        instruction = "Use this one-time token to set your initial password."
    elif purpose == "password_reset":
        subject = "Reset your SprintSight password"
        endpoint = "password-reset"
        instruction = "Use this one-time token to choose a new password."
    else:
        raise ValueError("Unsupported email action.")

    url = (
        f"{settings.email_api_base_url.rstrip('/')}"
        f"{settings.api_v1_prefix}/auth/{endpoint}/complete"
    )
    body = (
        f"{instruction}\n\n"
        f"Token (expires in {settings.email_action_token_expire_minutes} minutes):\n"
        f"{token}\n\n"
        f"Complete the request by POSTing JSON to {url}:\n"
        '{"token":"<token from this email>","new_password":"<your new password>"}\n\n'
        "If you did not request this, ignore this email."
    )
    return subject, body