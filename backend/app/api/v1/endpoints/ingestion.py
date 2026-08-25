from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_faculty
from app.schemas.assessment import IngestionRequest
from app.services.documentsService.service import collect_document_signals
from app.services.gitlabGithub.service import ingest_github_metrics
from app.services.jiraService.service import enrich_jira_metrics

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/sync")
def sync_ingestion(
    payload: IngestionRequest,
    faculty_user: Annotated[object, Depends(require_faculty)],
) -> dict:
    _ = faculty_user
    github_metrics = ingest_github_metrics(payload)
    jira_metrics = enrich_jira_metrics(payload)
    document_signals = collect_document_signals(payload)
    return {
        "github_metrics": github_metrics,
        "jira_metrics": jira_metrics,
        "document_signals": document_signals,
    }
