import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class CredentialDecryptionError(ValueError):
    pass


def _fernet() -> Fernet:
    settings = get_settings()
    configured = settings.credentials_encryption_key.strip()
    if configured:
        key = configured.encode("utf-8") if isinstance(configured, str) else configured
        return Fernet(key)
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise CredentialDecryptionError("Could not decrypt stored credential.") from exc


def normalize_jira_domain(value: str | None) -> str | None:
    if value is None:
        return None
    domain = value.strip()
    for prefix in ("https://", "http://"):
        if domain.lower().startswith(prefix):
            domain = domain[len(prefix) :]
    domain = domain.split("/")[0].strip()
    return domain or None
