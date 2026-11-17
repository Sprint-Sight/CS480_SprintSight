"""Who wrote this commit / owns this ticket? Resolved from current data, in any setup order.

Matching precedence (first hit wins; nothing is ever guessed):
  1. an instructor override in project_git_identities (email, then name);
  2. the author's email equals one project member's login email (case-insensitive);
  3. the author's name equals one project member's full name (case-insensitive, trimmed).
Only the project's current, active student members can be matched, and a match that would be
ambiguous (two members share the email/name) resolves to None.

The resolver is built from the project's *current* membership, so the result does not depend on
whether students were created, enrolled or added to the team before or after ingestion. The
`student_id` stored on commits and Jira tickets is a cache: callers re-resolve when reading and
`relink_project` refreshes the stored copies whenever membership or identities change.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.storage import storage
from app.repositories.interfaces import (
    GitIdentityRepository,
    JiraIngestionRunRepository,
    MetricsRepository,
    ProjectRepository,
    UserRecord,
    UserRepository,
)
from app.schemas.assessment import CommitInfo, JiraCleanedSnapshot
from app.schemas.auth import Role
from app.services.jiraService.normalizer import normalize_jira_envelope

log = logging.getLogger(__name__)

EMAIL, NAME = "email", "name"


def normalize_email(email: str | None) -> str | None:
    normalized = email.strip().casefold() if email else ""
    return normalized or None


def normalize_name(name: str | None) -> str | None:
    normalized = " ".join(name.split()).casefold() if name else ""
    return normalized or None


def normalize_identity_value(kind: str, value: str) -> str | None:
    return normalize_email(value) if kind == EMAIL else normalize_name(value)


@dataclass(frozen=True)
class IdentityResolver:
    members: dict[str, UserRecord]
    ids_by_email: dict[str, list[str]] = field(default_factory=dict)
    ids_by_name: dict[str, list[str]] = field(default_factory=dict)
    email_overrides: dict[str, str] = field(default_factory=dict)
    name_overrides: dict[str, str] = field(default_factory=dict)

    def resolve(self, author: str | None, author_email: str | None = None) -> str | None:
        email, name = normalize_email(author_email), normalize_name(author)
        if email and email in self.email_overrides:
            return self.email_overrides[email]
        if name and name in self.name_overrides:
            return self.name_overrides[name]
        if email:
            candidates = self.ids_by_email.get(email, [])
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                return None  # two members share the email: do not guess
        if name and name != email:
            candidates = self.ids_by_name.get(name, [])
            if len(candidates) == 1:
                return candidates[0]
        return None


def build_resolver(
    project_id: str,
    projects: ProjectRepository,
    users: UserRepository,
    identities: GitIdentityRepository | None = None,
) -> IdentityResolver:
    members: dict[str, UserRecord] = {}
    ids_by_email: dict[str, list[str]] = {}
    ids_by_name: dict[str, list[str]] = {}
    for member_id in projects.list_member_ids(project_id):
        user = users.get_by_id(member_id)
        if not user or not user.is_active or user.role != Role.STUDENT:
            continue
        members[member_id] = user
        if email := normalize_email(user.email):
            ids_by_email.setdefault(email, []).append(member_id)
        if name := normalize_name(user.full_name):
            ids_by_name.setdefault(name, []).append(member_id)
    email_overrides: dict[str, str] = {}
    name_overrides: dict[str, str] = {}
    for record in identities.list_identities(project_id) if identities else []:
        if record.student_id not in members:
            continue  # the student left the team: the override is dormant, not deleted
        (email_overrides if record.kind == EMAIL else name_overrides)[record.value] = (
            record.student_id
        )
    return IdentityResolver(members, ids_by_email, ids_by_name, email_overrides, name_overrides)


def apply_to_commits(commits: list[CommitInfo], resolver: IdentityResolver) -> None:
    for commit in commits:
        commit.student_id = resolver.resolve(commit.author, commit.author_email)


def apply_to_snapshot(snapshot: JiraCleanedSnapshot, resolver: IdentityResolver) -> None:
    """Fill Jira tickets the normaliser could not link, and drop links to people who left the
    team. A ticket the normaliser matched by email keeps that match while the member is current."""
    for ticket in snapshot.tickets:
        if ticket.student_id and ticket.student_id not in resolver.members:
            ticket.student_id = None
        if ticket.student_id is None:
            ticket.student_id = resolver.resolve(ticket.assignee, None)


def normalize_run(run, resolver: IdentityResolver) -> JiraCleanedSnapshot:
    """Re-normalise one stored Jira run against the project's current members."""
    settings = get_settings()
    envelope = json.loads(storage.download(run.raw_bucket, run.raw_object_key))
    snapshot = normalize_jira_envelope(
        envelope,
        story_points_field=(
            envelope.get("story_points_field") or settings.jira_story_points_field or None
        ),
        sprint_field=(
            envelope.get("sprint_field") or settings.jira_sprint_field or "customfield_10020"
        ),
        completion_date_field=(
            envelope.get("completion_date_field") or settings.jira_completed_date_field or None
        ),
        sprint_start_date_field=(
            envelope.get("sprint_start_date_field") or settings.jira_sprint_start_date_field or None
        ),
        sprint_end_date_field=(
            envelope.get("sprint_end_date_field") or settings.jira_sprint_end_date_field or None
        ),
        users_by_id=resolver.members,
        ids_by_email=resolver.ids_by_email,
        ids_by_name=resolver.ids_by_name,
        project_member_ids=set(resolver.members),
    )
    apply_to_snapshot(snapshot, resolver)
    return snapshot


def relink_project(
    project_id: str,
    projects: ProjectRepository,
    users: UserRepository,
    identities: GitIdentityRepository | None,
    metrics: MetricsRepository | None,
    jira_runs: JiraIngestionRunRepository | None,
) -> dict[str, int]:
    """Refresh the stored student_id on a project's commits and cleaned Jira snapshots.

    Best effort and idempotent: a failure here is logged and never blocks the change that
    triggered it, because reads re-resolve anyway.
    """
    from datetime import UTC, datetime

    result = {"commits_changed": 0, "jira_runs_updated": 0}
    try:
        resolver = build_resolver(project_id, projects, users, identities)
    except Exception:
        log.exception("Could not build the identity resolver for project %s", project_id)
        return result
    if metrics is not None:
        try:
            result["commits_changed"] = metrics.relink_commits(project_id, resolver.resolve)
        except Exception:
            log.exception("Could not re-link commits for project %s", project_id)
    if jira_runs is not None:
        try:
            runs = jira_runs.list_project_runs(project_id)
        except Exception:
            log.exception("Could not list Jira runs for project %s", project_id)
            runs = []
        for run in runs:
            if not run.cleaned_snapshot:
                continue
            try:
                snapshot = run.cleaned_snapshot
                before = [ticket.student_id for ticket in snapshot.tickets]
                apply_to_snapshot(snapshot, resolver)
                if before == [ticket.student_id for ticket in snapshot.tickets]:
                    continue
                jira_runs.update_processed_run(
                    project_id,
                    run.sprint_id,
                    run.id,
                    "completed",
                    datetime.now(UTC),
                    snapshot.normalization_version,
                    None,
                    snapshot,
                )
                result["jira_runs_updated"] += 1
            except Exception:
                log.exception("Could not re-link Jira run %s of project %s", run.id, project_id)
    return result


def relink_for_user(
    user_id: str,
    projects: ProjectRepository,
    users: UserRepository,
    identities: GitIdentityRepository | None,
    metrics: MetricsRepository | None,
    jira_runs: JiraIngestionRunRepository | None,
    project_ids: list[str] | None = None,
) -> None:
    """Re-link every project a student belongs to (or the given ones, e.g. just left)."""
    targets = set(project_ids or [])
    if not targets:
        for course in projects.list_courses():
            for project in projects.list_projects(course.id):
                if user_id in projects.list_member_ids(project.id):
                    targets.add(project.id)
    for project_id in targets:
        relink_project(project_id, projects, users, identities, metrics, jira_runs)


__all__ = [
    "IdentityResolver",
    "apply_to_commits",
    "apply_to_snapshot",
    "build_resolver",
    "normalize_identity_value",
    "normalize_run",
    "relink_for_user",
    "relink_project",
]
