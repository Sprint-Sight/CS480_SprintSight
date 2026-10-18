from fastapi.testclient import TestClient

from app.dependencies.auth import get_action_audit_repository
from app.main import app

client = TestClient(app)
RETENTION_URL = "/api/v1/audit/retention"


def _token(email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_admin_can_read_and_update_audit_retention_config() -> None:
    admin_token = _token("admin@sprintsight.edu")
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "hot_retention_days": 30,
        "action_archive_retention_days": 180,
        "override_archive_retention_days": 270,
    }

    initial = client.get(RETENTION_URL, headers=headers)
    updated = client.put(RETENTION_URL, headers=headers, json=payload)
    persisted = client.get(RETENTION_URL, headers=headers)

    assert initial.status_code == 200
    assert initial.json()["hot_retention_days"] == 168
    assert updated.status_code == 200
    assert {key: updated.json()[key] for key in payload} == payload
    assert updated.json()["updated_by"] == "u-admin-1"
    assert persisted.json() == updated.json()

    audit_events = app.dependency_overrides[get_action_audit_repository]().list_action_audits()
    assert audit_events[-1].action == "update_audit_retention"
    assert audit_events[-1].actor_id == "u-admin-1"
    assert audit_events[-1].details == payload


def test_non_admin_cannot_read_or_update_audit_retention_config() -> None:
    instructor_token = _token("faculty@sprintsight.edu")
    headers = {"Authorization": f"Bearer {instructor_token}"}

    read_response = client.get(RETENTION_URL, headers=headers)
    update_response = client.put(
        RETENTION_URL,
        headers=headers,
        json={
            "hot_retention_days": 30,
            "action_archive_retention_days": 180,
            "override_archive_retention_days": 270,
        },
    )

    assert read_response.status_code == 403
    assert update_response.status_code == 403


def test_audit_retention_periods_must_be_positive() -> None:
    admin_token = _token("admin@sprintsight.edu")

    response = client.put(
        RETENTION_URL,
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "hot_retention_days": 0,
            "action_archive_retention_days": 180,
            "override_archive_retention_days": 270,
        },
    )

    assert response.status_code == 422
