from fastapi import APIRouter

from app.api.v1.endpoints import (
    artifacts,
    assessment,
    audit,
    auth,
    documents,
    export,
    health,
    ingestion,
    insights,
    jira_outlier,
    manual_text,
    models,
    notifications,
    peer_evaluation,
    projects,
    settings,
    users,
)
from app.core.config import get_settings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(projects.router)
api_router.include_router(settings.router)
api_router.include_router(manual_text.router)
api_router.include_router(ingestion.router)
api_router.include_router(ingestion.jira_ingestion_router)
api_router.include_router(jira_outlier.router)
api_router.include_router(assessment.router)
api_router.include_router(artifacts.router)
api_router.include_router(models.router)
api_router.include_router(audit.router)
api_router.include_router(documents.router)
api_router.include_router(notifications.router)
api_router.include_router(export.router, prefix="/export")
api_router.include_router(peer_evaluation.router, prefix="/peer-evaluation")
if get_settings().insights_enabled:  # INSIGHTS_ENABLED=false is the AI Insights kill switch
    api_router.include_router(insights.router)
