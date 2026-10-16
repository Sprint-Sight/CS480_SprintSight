from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from jose import JWTError, jwt

from app.core.config import Settings, get_settings
from app.core.security import TokenPayloadError
from app.repositories.interfaces import UserRecord


def create_email_action_token(user: UserRecord, purpose: str) -> str:
    if purpose not in {"first_time_password", "password_reset"}:
        raise ValueError("Unsupported email action.")

    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=_token_expiry_minutes(settings, purpose))
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


def _token_expiry_minutes(settings: Settings, purpose: str) -> int:
    if purpose == "first_time_password":
        return settings.email_first_time_token_expire_minutes
    if purpose == "password_reset":
        return settings.email_password_reset_token_expire_minutes
    raise ValueError("Unsupported email action.")


def email_action_message(token: str, purpose: str) -> tuple[str, str]:
    settings = get_settings()
    if purpose == "first_time_password":
        subject = "Set your SprintSight password"
        purpose_label = "first-time-password"
        instruction = "Click this one-time link to set your initial password."
    elif purpose == "password_reset":
        subject = "Reset your SprintSight password"
        purpose_label = "password-reset"
        instruction = "Click this one-time link to choose a new password."
    else:
        raise ValueError("Unsupported email action.")

    expiry_minutes = _token_expiry_minutes(settings, purpose)
    link = (
        f"{settings.email_frontend_base_url.rstrip('/')}/set-password?"
        f"{urlencode({'token': token, 'purpose': purpose_label})}"
    )
    body = (
        f"{instruction}\n\n"
        f"{link}\n\n"
        f"This link expires in {expiry_minutes} minutes and can only be used once.\n\n"
        "If you did not request this, ignore this email."
    )
    return subject, body