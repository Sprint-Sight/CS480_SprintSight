from fastapi import APIRouter

from app.api.v1.endpoints import assessment, audit, auth, documents, health, ingestion, manual_scoring, manual_text, projects, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(projects.router)
api_router.include_router(manual_text.router)
api_router.include_router(ingestion.router)
api_router.include_router(ingestion.jira_ingestion_router)
api_router.include_router(assessment.router)
api_router.include_router(manual_scoring.router)
api_router.include_router(audit.router)
api_router.include_router(documents.router)
