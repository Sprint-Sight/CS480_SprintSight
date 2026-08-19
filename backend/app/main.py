from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_middleware

settings = get_settings()
configure_logging()

app = FastAPI(title=settings.project_name)
app.middleware("http")(request_id_middleware)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": f"http_{exc.status_code}", "message": str(exc.detail)}},
    )


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.project_name, "status": "running"}
