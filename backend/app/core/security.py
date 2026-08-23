import base64
import hashlib
import hmac
import secrets
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import get_settings


class TokenPayloadError(ValueError):
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        algorithm, iterations_str, salt_b64, digest_b64 = hashed_password.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        salt = base64.urlsafe_b64decode(salt_b64.encode("utf-8"))
        expected_digest = base64.urlsafe_b64decode(digest_b64.encode("utf-8"))
        computed = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(computed, expected_digest)
    except (ValueError, TypeError):
        return False


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 200_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode("utf-8"),
        base64.urlsafe_b64encode(digest).decode("utf-8"),
    )


def create_access_token(subject: str, role: str, token_version: int = 0, expires_delta_minutes: int | None = None) -> str:
    settings = get_settings()
    expire_minutes = expires_delta_minutes or settings.access_token_expire_minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "token_version": token_version,
        "jti": str(uuid4()),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        sub = payload.get("sub")
        role = payload.get("role")
        token_id = payload.get("jti")
        if not sub or not role or not token_id or "token_version" not in payload:
            raise TokenPayloadError("Invalid token payload.")
        return payload
    except JWTError as exc:
        raise TokenPayloadError("Could not validate credentials.") from exc
