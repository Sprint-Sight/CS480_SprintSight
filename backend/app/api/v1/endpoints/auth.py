from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import (
    TokenPayloadError,
    create_access_token,
    decode_access_token,
    hash_password,
)
from app.dependencies.auth import (
    get_action_audit_repository,
    get_current_user,
    get_notification_service,
    get_user_repository,
    oauth2_scheme,
    require_password_changed,
)
from app.repositories.interfaces import ActionAuditRepository, UserRecord, UserRepository
from app.schemas.auth import (
    EmailAddressRequest,
    EmailPasswordResetRequest,
    LoginRequest,
    PasswordChangeRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auditLogService.service import append_action_audit
from app.services.authService.email_tokens import (
    create_email_action_token,
    decode_email_action_token,
    email_action_message,
)
from app.services.authService.service import authenticate_user, change_password, user_response
from app.services.notificationService.service import (
    NotificationConfigurationError,
    NotificationDeliveryError,
    SMTPNotificationService,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> TokenResponse:
    user = authenticate_user(repository, payload.email, payload.password)
    repository.record_login(user.id)
    token = create_access_token(subject=user.id, role=user.role.value, token_version=user.token_version)
    return TokenResponse(access_token=token, must_change_password=user.must_change_password)


def _request_password_email(
    payload: EmailAddressRequest,
    purpose: str,
    repository: UserRepository,
    notification_service: SMTPNotificationService,
) -> dict[str, str]:
    if not notification_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured.",
        )

    user = repository.get_by_email(payload.email)
    if not user or not user.is_active:
        return {"message": "If the account is eligible, password instructions have been emailed."}
    if purpose == "first_time_password" and not user.must_change_password:
        return {"message": "If the account is eligible, password instructions have been emailed."}

    token = create_email_action_token(user, purpose)
    subject, body = email_action_message(token, purpose)
    try:
        notification_service.send_email(user.email, subject, body)
    except NotificationConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured.",
        ) from exc
    except NotificationDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not deliver the email. Please try again later.",
        ) from exc

    return {"message": "If the account is eligible, password instructions have been emailed."}


def _complete_email_password_action(
    payload: EmailPasswordResetRequest,
    purpose: str,
    repository: UserRepository,
) -> UserResponse:
    try:
        token_payload = decode_email_action_token(payload.token, purpose)
    except TokenPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email action token is invalid or expired.",
        ) from exc

    user = repository.get_by_id(token_payload["sub"])
    if (
        not user
        or not user.is_active
        or user.token_version != token_payload["token_version"]
        or (purpose == "first_time_password" and not user.must_change_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email action token is invalid or expired.",
        )

    updated = repository.update_password(user.id, hash_password(payload.new_password), False)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user_response(updated)


@router.post("/first-time-password/request", status_code=status.HTTP_202_ACCEPTED)
def request_first_time_password(
    payload: EmailAddressRequest,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    notification_service: Annotated[SMTPNotificationService, Depends(get_notification_service)],
) -> dict[str, str]:
    return _request_password_email(payload, "first_time_password", repository, notification_service)


@router.post("/first-time-password/complete", response_model=UserResponse)
def complete_first_time_password(
    payload: EmailPasswordResetRequest,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserResponse:
    return _complete_email_password_action(payload, "first_time_password", repository)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    payload: EmailAddressRequest,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    notification_service: Annotated[SMTPNotificationService, Depends(get_notification_service)],
) -> dict[str, str]:
    return _request_password_email(payload, "password_reset", repository, notification_service)


@router.post("/password-reset/complete", response_model=UserResponse)
def complete_password_reset(
    payload: EmailPasswordResetRequest,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserResponse:
    return _complete_email_password_action(payload, "password_reset", repository)


@router.post("/change-password", response_model=UserResponse)
def update_password(
    payload: PasswordChangeRequest,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> UserResponse:
    updated = change_password(repository, current_user, payload.current_password, payload.new_password)
    append_action_audit(
        action_audits,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="change_own_password",
        target_type="user",
        target_id=current_user.id,
    )
    return user_response(updated)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: Annotated[object, Depends(oauth2_scheme)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> None:
    try:
        token = credentials.credentials
        payload = decode_access_token(token)
        token_id = str(UUID(payload["jti"]))
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC).replace(tzinfo=None)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.") from exc

    repository.revoke_access_token(token_id, current_user.id, expires_at)
    append_action_audit(
        action_audits,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="logout",
        target_type="user",
        target_id=current_user.id,
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[object, Depends(require_password_changed)]) -> UserResponse:
    return user_response(current_user)