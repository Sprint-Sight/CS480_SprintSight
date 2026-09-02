from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.core.config import get_settings
from app.core.storage import storage
from app.dependencies.auth import get_current_user, get_document_repository, get_project_repository
from app.repositories.interfaces import DocumentRepository, ProjectRepository, UserRecord
from app.schemas.auth import Role
from app.schemas.documents import DocumentResponse, DocumentUploadResponse
from app.services.documentsService.service import DocumentValidationError, upload_documents

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])


def _get_authorized_project(project_id: str, current_user: UserRecord, projects: ProjectRepository):
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    allowed = current_user.role == Role.INSTRUCTOR and projects.is_instructor_assigned(project.course_id, current_user.id)
    allowed = allowed or current_user.id in projects.list_member_ids(project_id)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    return project


def _response(document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        project_id=document.project_id,
        filename=document.filename,
        mime_type=document.mime_type,
        byte_size=document.byte_size,
        checksum=document.checksum,
        uploaded_by=document.uploaded_by,
        created_at=document.created_at,
    )


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_project_documents(
    project_id: str,
    files: Annotated[list[UploadFile], File(...)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    documents: Annotated[DocumentRepository, Depends(get_document_repository)],
) -> DocumentUploadResponse:
    _get_authorized_project(project_id, current_user, projects)
    uploaded_files = [(file.filename or "", file.content_type, await file.read()) for file in files]
    try:
        records = upload_documents(project_id, current_user.id, uploaded_files, documents, storage, get_settings())
    except DocumentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    return DocumentUploadResponse(documents=[_response(record) for record in records])


@router.get("", response_model=list[DocumentResponse])
def list_project_documents(
    project_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    documents: Annotated[DocumentRepository, Depends(get_document_repository)],
) -> list[DocumentResponse]:
    _get_authorized_project(project_id, current_user, projects)
    return [_response(document) for document in documents.list_documents(project_id)]


@router.get("/{document_id}")
def download_project_document(
    project_id: str,
    document_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    documents: Annotated[DocumentRepository, Depends(get_document_repository)],
) -> Response:
    _get_authorized_project(project_id, current_user, projects)
    document = documents.get_document(project_id, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return Response(
        content=storage.download(document.storage_bucket, document.storage_key),
        media_type=document.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
    )