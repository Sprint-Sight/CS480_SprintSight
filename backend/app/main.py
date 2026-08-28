from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_middleware
from app.core.storage import storage
from app.core.security import hash_password
from app.repositories.interfaces import UserRecord
from app.repositories.postgres import PostgresMetricsRepository, PostgresProjectRepository, PostgresUserRepository, create_user_pool
from app.schemas.auth import Role
from uuid import uuid4

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
        ))


# ------------------------------------------------------------------
# Lifespan — runs startup/shutdown logic around the app lifecycle
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- STARTUP -------------------------------------------------
    pool = create_user_pool(settings.database_connection_string())
    pool.open(wait=True)
    app.state.user_repository = PostgresUserRepository(pool)
    app.state.project_repository = PostgresProjectRepository(pool)
    app.state.metrics_repository = PostgresMetricsRepository(pool)

    user_repository = app.state.user_repository
    _bootstrap_user(user_repository, settings.bootstrap_admin_email, settings.bootstrap_admin_password, settings.bootstrap_admin_name, Role.ADMIN)
    _bootstrap_user(user_repository, settings.bootstrap_instructor_email, settings.bootstrap_instructor_password, settings.bootstrap_instructor_name, Role.INSTRUCTOR)
    _bootstrap_user(user_repository, settings.bootstrap_student_email, settings.bootstrap_student_password, settings.bootstrap_student_name, Role.STUDENT)

    # Create MinIO buckets if they don't exist yet
    storage.init_buckets()

    yield  # app runs here

    # ---- SHUTDOWN ------------------------------------------------
    pool.close()


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
app = FastAPI(
    title=settings.project_name,
    lifespan=lifespan,
)

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