from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def token(email: str, password: str = "password123") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def create_course() -> tuple[str, dict[str, str]]:
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    response = client.post(
        "/api/v1/courses",
        json={"code": "CS480", "name": "Capstone", "section": "001", "year": 2026, "term": "Fall"},
        headers=instructor_headers,
    )
    assert response.status_code == 201
    return response.json()["id"], instructor_headers


def test_bulk_import_creates_and_enrolls_students() -> None:
    course_id, instructor_headers = create_course()
    response = client.post(
        f"/api/v1/courses/{course_id}/students/import",
        files={
            "file": (
                "students.csv",
                "student_name,student_id,student_email\n"
                "New Student,480001,new.student@sprintsight.edu\n",
                "text/csv",
            )
        },
        headers=instructor_headers,
    )

    assert response.status_code == 200
    assert response.json()["created_students"] == 1
    assert response.json()["enrolled_students"] == 1
    roster = client.get(f"/api/v1/courses/{course_id}/students", headers=instructor_headers)
    assert roster.status_code == 200
    assert roster.json()[0]["email"] == "new.student@sprintsight.edu"


def test_bulk_import_is_idempotent_for_existing_enrollment() -> None:
    course_id, instructor_headers = create_course()
    csv = (
        "student_name,student_id,student_email\n"
        "Existing Student,480002,existing.student@sprintsight.edu\n"
    )
    first = client.post(
        f"/api/v1/courses/{course_id}/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
        headers=instructor_headers,
    )
    second = client.post(
        f"/api/v1/courses/{course_id}/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
        headers=instructor_headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["created_students"] == 0
    assert second.json()["enrolled_students"] == 0
    assert second.json()["already_enrolled"] == 1


def test_bulk_import_rejects_duplicate_rows_before_persisting() -> None:
    course_id, instructor_headers = create_course()
    response = client.post(
        f"/api/v1/courses/{course_id}/students/import",
        files={
            "file": (
                "students.csv",
                "student_name,student_id,student_email\n"
                "First Student,480003,first.student@sprintsight.edu\n"
                "Duplicate Student,480003,duplicate.student@sprintsight.edu\n",
                "text/csv",
            )
        },
        headers=instructor_headers,
    )

    assert response.status_code == 422
    roster = client.get(f"/api/v1/courses/{course_id}/students", headers=instructor_headers)
    assert roster.json() == []


def test_student_number_must_be_unique() -> None:
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    first = client.post(
        "/api/v1/users",
        json={
            "email": "number.one@sprintsight.edu",
            "full_name": "Number One",
            "password": "temporary123",
            "student_number": 480010,
        },
        headers=instructor_headers,
    )
    duplicate = client.post(
        "/api/v1/users",
        json={
            "email": "number.two@sprintsight.edu",
            "full_name": "Number Two",
            "password": "temporary123",
            "student_number": 480010,
        },
        headers=instructor_headers,
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
