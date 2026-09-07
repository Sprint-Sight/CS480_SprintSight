from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    project_id: str
    filename: str
    mime_type: str
    byte_size: int
    checksum: str
    uploaded_by: str
    created_at: datetime


class DocumentUploadResponse(BaseModel):
    documents: list[DocumentResponse]
