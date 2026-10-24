from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_middleware
from app.core.security import hash_password
from app.core.storage import storage
from app.repositories.in_memory import (
    InMemoryEmailOutboxRepository,
    InMemoryExportLogRepository,
    InMemoryPeerEvaluationRepository,
)
from app.repositories.interfaces import UserRecord
from app.repositories.postgres import (
    PostgresActionAuditRepository,
    PostgresAssessmentRepository,
    PostgresAuditRepository,
    PostgresAuditRetentionConfigRepository,
    PostgresDocumentRepository,
    PostgresEmailOutboxRepository,
    PostgresInstructorModelSelectionRepository,
    PostgresJiraIngestionRunRepository,
    PostgresManualTextRepository,
    PostgresMetricsRepository,
    PostgresNotificationRepository,
    PostgresPeerEvaluationRepository,
    PostgresProjectRepository,
    PostgresRubricWeightsRepository,
    PostgresUserRepository,
    create_user_pool,
    ensure_assessment_schema,
    ensure_audit_retention_config_schema,
    ensure_audit_schema,
    ensure_email_outbox_schema,
    ensure_instructor_model_selection_schema,
    ensure_notification_schema,
    ensure_peer_evaluation_schema,
    ensure_project_credential_schema,
    ensure_rubric_weights_schema,
    ensure_user_schema,
)
from app.schemas.auth import Role
from app.services.notificationService.queue import EmailDispatcher, EmailQueue
from app.services.notificationService.service import build_email_transport

settings = get_settings()
configure_logging()


def _bootstrap_user(repository: PostgresUserRepository, email: str, password: str, name: str, role: Role) -> None:
    if email and password and not repository.get_by_email(email):
        repository.create_user(UserRecord(
            id=str(uuid4()),
            email=email,
            full_name=name,
            role=role,
            hashed_password=hash_password(password),
            student_number=1 if role == Role.STUDENT else None,
        ))


# ------------------------------------------------------------------
# Lifespan — runs startup/shutdown logic around the app lifecycle
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- STARTUP -------------------------------------------------
    pool = create_user_pool(settings.database_connection_string())
    pool.open(wait=True)
    ensure_user_schema(pool)
    ensure_project_credential_schema(pool)
    ensure_notification_schema(pool)
    ensure_email_outbox_schema(pool)
    ensure_assessment_schema(pool)
    ensure_audit_schema(pool)
    ensure_audit_retention_config_schema(
        pool,
        settings.audit_hot_retention_days,
        settings.audit_action_archive_retention_days,
        settings.audit_override_archive_retention_days,
    )
    ensure_rubric_weights_schema(pool)
    ensure_instructor_model_selection_schema(pool)
    ensure_peer_evaluation_schema(pool)
    app.state.user_repository = PostgresUserRepository(pool)
    app.state.project_repository = PostgresProjectRepository(pool)
    app.state.metrics_repository = PostgresMetricsRepository(pool)
    app.state.document_repository = PostgresDocumentRepository(pool)
    app.state.notification_repository = PostgresNotificationRepository(pool)
    app.state.jira_ingestion_repository = PostgresJiraIngestionRunRepository(pool)
    app.state.manual_text_repository = PostgresManualTextRepository(pool)
    app.state.assessment_repository = PostgresAssessmentRepository(pool)
    app.state.audit_repository = PostgresAuditRepository(pool)
    app.state.action_audit_repository = PostgresActionAuditRepository(pool)
    app.state.audit_retention_config_repository = PostgresAuditRetentionConfigRepository(pool)
    app.state.rubric_weights_repository = PostgresRubricWeightsRepository(pool)
    app.state.instructor_model_selection_repository = PostgresInstructorModelSelectionRepository(pool)
    app.state.export_log_repository = InMemoryExportLogRepository()
    app.state.peer_evaluation_repository = PostgresPeerEvaluationRepository(pool)
    app.state.email_outbox_repository = PostgresEmailOutboxRepository(pool)
    app.state.notification_service = EmailQueue(
        app.state.email_outbox_repository,
        build_email_transport(settings),
        settings,
    )
    app.state.email_dispatcher = EmailDispatcher(
        app.state.notification_service,
        settings.email_dispatch_interval_seconds,
    )
    app.state.email_dispatcher.start()

    user_repository = app.state.user_repository
    _bootstrap_user(user_repository, settings.bootstrap_admin_email, settings.bootstrap_admin_password, settings.bootstrap_admin_name, Role.ADMIN)
    _bootstrap_user(user_repository, settings.bootstrap_instructor_email, settings.bootstrap_instructor_password, settings.bootstrap_instructor_name, Role.INSTRUCTOR)
    _bootstrap_user(user_repository, settings.bootstrap_student_email, settings.bootstrap_student_password, settings.bootstrap_student_name, Role.STUDENT)

    # Create MinIO buckets if they don't exist yet
    storage.init_buckets()

    yield  # app runs here

    # ---- SHUTDOWN ------------------------------------------------
    dispatcher = getattr(app.state, "email_dispatcher", None)
    if dispatcher is not None:
        dispatcher.stop()
    pool.close()


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
app = FastAPI(
    title=settings.project_name,
    lifespan=lifespan,
)
app.state.email_outbox_repository = InMemoryEmailOutboxRepository()
app.state.export_log_repository = InMemoryExportLogRepository()
app.state.peer_evaluation_repository = InMemoryPeerEvaluationRepository()
app.state.notification_service = EmailQueue(
    app.state.email_outbox_repository,
    build_email_transport(settings),
    settings,
)

app.openapi_version = "3.0.3"


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version="0.1.0",
        openapi_version="3.0.3",
        routes=app.routes,
    )
    operation = schema["paths"]["/api/v1/projects/{project_id}/documents"]["post"]
    request_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    request_component = schema["components"]["schemas"][request_schema["$ref"].split("/")[-1]]
    request_component["properties"]["files"]["items"] = {
        "type": "string",
        "format": "binary",
    }
    import_operation = schema["paths"]["/api/v1/courses/{course_id}/students/import"]["post"]
    import_request_schema = import_operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    import_component = schema["components"]["schemas"][import_request_schema["$ref"].split("/")[-1]]
    import_component["properties"]["file"] = {
        "type": "string",
        "format": "binary",
    }

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

# Enable CORS for browser frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development (e.g., http://localhost:3000)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(request_id_middleware)
app.include_router(api_router, prefix=settings.api_v1_prefix)


# ------------------------------------------------------------------
# Exception handlers
# ------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"http_{exc.status_code}",
                "message": str(exc.detail),
            }
        },
    )


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------
@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.project_name, "status": "running"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.project_name}