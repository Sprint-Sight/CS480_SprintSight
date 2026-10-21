from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def login(email: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_create_user_and_user_must_change_temporary_password() -> None:
    admin = login("admin@sprintsight.edu", "password123")
    response = client.post(
        "/api/v1/users",
        json={"email": "new@sprintsight.edu", "full_name": "New User", "role": "student", "password": "temporary123"},
        headers=auth_header(admin["access_token"]),
    )
    assert response.status_code == 201
    assert response.json()["must_change_password"] is True
    assert "hashed_password" not in response.json()

    new_user = login("new@sprintsight.edu", "temporary123")
    assert new_user["must_change_password"] is True
    me_response = client.get("/api/v1/auth/me", headers=auth_header(new_user["access_token"]))
    assert me_response.status_code == 403

    change_response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "temporary123", "new_password": "permanent123"},
        headers=auth_header(new_user["access_token"]),
    )
    assert change_response.status_code == 200
    assert change_response.json()["must_change_password"] is False
    assert client.get("/api/v1/auth/me", headers=auth_header(new_user["access_token"])).status_code == 401
    assert login("new@sprintsight.edu", "permanent123")["must_change_password"] is False


def test_instructor_set_fallback_password_lets_a_student_in_without_the_email() -> None:
    """The fallback path when the setup email cannot be delivered.

    The instructor sets a password, the student logs in with it once, and is then
    forced onto the change-first-password screen.
    """
    instructor = login("faculty@sprintsight.edu", "password123")
    response = client.post(
        "/api/v1/users",
        json={
            "email": "fallback@sprintsight.edu",
            "full_name": "Fallback Student",
            "role": "student",
            "password": "fallback123",
        },
        headers=auth_header(instructor["access_token"]),
    )
    assert response.status_code == 201
    assert response.json()["must_change_password"] is True
    # The password is never echoed back to the client.
    assert "password" not in response.json()

    student = login("fallback@sprintsight.edu", "fallback123")
    assert student["must_change_password"] is True
    # Blocked from the rest of the app until they choose their own password.
    me = client.get("/api/v1/auth/me", headers=auth_header(student["access_token"]))
    assert me.status_code == 403

    change = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "fallback123", "new_password": "studentchosen123"},
        headers=auth_header(student["access_token"]),
    )
    assert change.status_code == 200
    assert change.json()["must_change_password"] is False
    assert login("fallback@sprintsight.edu", "studentchosen123")["must_change_password"] is False


def test_student_created_without_a_password_cannot_log_in_without_the_email() -> None:
    """Without an instructor-set password there is no fallback: only the link works."""
    instructor = login("faculty@sprintsight.edu", "password123")
    response = client.post(
        "/api/v1/users",
        json={"email": "nolink@sprintsight.edu", "full_name": "No Link", "role": "student"},
        headers=auth_header(instructor["access_token"]),
    )
    assert response.status_code == 201
    assert response.json()["must_change_password"] is True
    assert "password" not in response.json()

    # A random placeholder was generated, so no guessed password gets in.
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "nolink@sprintsight.edu", "password": "temporary123"},
    ).status_code == 401


def test_non_admin_cannot_manage_users() -> None:
    student = login("student@sprintsight.edu", "password123")
    response = client.get("/api/v1/users", headers=auth_header(student["access_token"]))
    assert response.status_code == 403


def test_admin_can_update_reset_and_deactivate_user() -> None:
    admin = login("admin@sprintsight.edu", "password123")
    created = client.post(
        "/api/v1/users",
        json={"email": "managed@sprintsight.edu", "full_name": "Managed User", "role": "student", "password": "temporary123"},
        headers=auth_header(admin["access_token"]),
    ).json()
    user_id = created["id"]

    update = client.patch(
        f"/api/v1/users/{user_id}",
        json={"full_name": "Updated User", "role": "instructor"},
        headers=auth_header(admin["access_token"]),
    )
    assert update.status_code == 200
    assert update.json()["full_name"] == "Updated User"

    reset = client.post(
        f"/api/v1/users/{user_id}/reset-password",
        json={"password": "resetpass123"},
        headers=auth_header(admin["access_token"]),
    )
    assert reset.status_code == 200
    assert reset.json()["must_change_password"] is True

    deactivate = client.patch(
        f"/api/v1/users/{user_id}",
        json={"is_active": False},
        headers=auth_header(admin["access_token"]),
    )
    assert deactivate.status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "managed@sprintsight.edu", "password": "resetpass123"}).status_code == 401