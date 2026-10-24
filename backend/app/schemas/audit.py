from datetime import datetime

from pydantic import BaseModel, Field


class AuditRetentionConfigUpdate(BaseModel):
    hot_retention_days: int = Field(ge=1)
    action_archive_retention_days: int = Field(ge=1)
    override_archive_retention_days: int = Field(ge=1)


class AuditRetentionConfigResponse(AuditRetentionConfigUpdate):
    updated_at: datetime
    updated_by: str | None
