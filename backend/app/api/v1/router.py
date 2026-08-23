from fastapi import APIRouter

from app.api.v1.endpoints import assessment, audit, auth, health, ingestion, manual_text, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(manual_text.router)
api_router.include_router(ingestion.router)
api_router.include_router(assessment.router)
api_router.include_router(audit.router)
