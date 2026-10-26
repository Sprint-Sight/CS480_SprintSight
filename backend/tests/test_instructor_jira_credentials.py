import json
from datetime import UTC, datetime
from types import SimpleNamespace

from app.api.v1.endpoints.settings import (
    JiraCredentialsPayload,
    get_jira_credentials,
    put_jira_credentials,
)
from app.core.credential_crypto import decrypt_secret
from app.repositories.in_memory import InMemoryInstructorJiraCredentialsRepository
from app.repositories.interfaces import ProjectRecord
from app.schemas.auth import Role
from app.services.jiraService.service import _resolve_jira_auth


def test_instructor_jira_token_is_encrypted_and_never_returned() -> None:
    repository = InMemoryInstructorJiraCredentialsRepository()
    instructor = SimpleNamespace(id="instructor-1", role=Role.INSTRUCTOR)
    action_audits = _InMemoryActionAudits()
    secret = "shared-jira-api-token"

    saved = put_jira_credentials(
        JiraCredentialsPayload(
            jira_email="jira-instructor@example.edu",
            jira_api_token=secret,
        ),
        instructor,
        repository,
        action_audits,
    )
    assert saved.jira_email == "jira-instructor@example.edu"
    assert saved.jira_token_configured is True
    assert saved.is_saved is True
    assert secret not in json.dumps(saved.model_dump())

    record = repository.get_credentials(instructor.id)
    assert record is not None
    assert record.jira_api_token_encrypted != secret
    assert decrypt_secret(record.jira_api_token_encrypted) == secret

    updated = put_jira_credentials(
        JiraCredentialsPayload(jira_email="jira-instructor@example.edu"),
        instructor,
        repository,
        action_audits,
    )
    assert updated.jira_token_configured is True
    updated_record = repository.get_credentials(instructor.id)
    assert updated_record is not None
    assert decrypt_secret(updated_record.jira_api_token_encrypted) == secret

    fetched = get_jira_credentials(instructor, repository)
    assert fetched.jira_email == "jira-instructor@example.edu"
    assert fetched.jira_token_configured is True
    assert secret not in json.dumps(fetched.model_dump())


def test_shared_instructor_jira_credentials_take_precedence_over_project_legacy_values() -> None:
    project = ProjectRecord(
        id="project-1",
        project_name="Project",
        team_name="Team",
        description=None,
        course_id="course-1",
        course_code="CS480",
        github_repo_url=None,
        local_repo_path=None,
        created_by="instructor-1",
        created_at=datetime.now(UTC),
        jira_email="old-project-email@example.edu",
        jira_domain="https://group.atlassian.net",
        jira_project_key="GROUP",
        jira_api_token_encrypted="legacy-encrypted-token",
    )

    assert _resolve_jira_auth(project, ("shared@example.edu", "shared-token")) == (
        "group.atlassian.net",
        "shared@example.edu",
        "shared-token",
    )


class _InMemoryActionAudits:
    def __init__(self) -> None:
        self.records = []

    def save_action_audit(self, record) -> None:
        self.records.append(record)
