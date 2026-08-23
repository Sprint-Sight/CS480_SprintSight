from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_middleware
from app.core.storage import storage
from app.repositories.postgres import PostgresUserRepository, create_user_pool

settings = get_settings()
configure_logging()


# ------------------------------------------------------------------
# Lifespan — runs startup/shutdown logic around the app lifecycle
# Replaces the deprecated @app.on_event("startup") pattern
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- STARTUP -------------------------------------------------
    pool = create_user_pool(settings.database_connection_string())
    pool.open(wait=True)
    app.state.user_repository = PostgresUserRepository(pool)

    # Create MinIO buckets if they don't exist yet
    # Safe to call every restart — skips buckets that already exist
    storage.init_buckets()

    yield  # app runs here

    # ---- SHUTDOWN ------------------------------------------------
    # Add any cleanup here (close DB pool, flush logs, etc.)
    pool.close()


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
app = FastAPI(
    title=settings.project_name,
    lifespan=lifespan,
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
    """
    Lightweight health endpoint.
    Docker, load balancers, and monitoring tools can poll this.
    """
    return {"status": "ok", "service": settings.project_name}