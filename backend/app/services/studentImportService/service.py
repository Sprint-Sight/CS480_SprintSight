import csv
import io
import secrets
import string
from dataclasses import dataclass

from fastapi import HTTPException, status
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.repositories.interfaces import ProjectRepository, UserRecord, UserRepository
from app.schemas.auth import Role
from app.schemas.student_import import StudentImportResult
from app.services.authService.service import create_user

REQUIRED_HEADERS = {"student_name", "student_id", "student_email"}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000
EMAIL_ADAPTER = TypeAdapter(EmailStr)


@dataclass(frozen=True)
class StudentImportRow:
    row_number: int
    name: str
    student_number: int
    email: str


def _temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def parse_student_csv(contents: bytes) -> list[StudentImportRow]:
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="CSV file is too large."
        )
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="CSV must be UTF-8 encoded."
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    headers = set(reader.fieldnames or [])
    if headers != REQUIRED_HEADERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "CSV headers must be student_name, student_id, and student_email.",
                "headers": sorted(headers),
            },
        )

    rows: list[StudentImportRow] = []
    seen_numbers: set[int] = set()
    seen_emails: set[str] = set()
    errors: list[str] = []
    for row_number, row in enumerate(reader, start=2):
        if row_number > MAX_ROWS + 1:
            errors.append(f"Row {row_number}: CSV exceeds the maximum of {MAX_ROWS} rows.")
            break
        name = (row.get("student_name") or "").strip()
        raw_number = (row.get("student_id") or "").strip()
        raw_email = (row.get("student_email") or "").strip()
        try:
            student_number = int(raw_number)
            if student_number <= 0:
                raise ValueError
            email = str(EMAIL_ADAPTER.validate_python(raw_email)).lower()
            if not name or len(name) > 100:
                raise ValueError("student_name must be between 1 and 100 characters.")
        except (ValueError, ValidationError):
            errors.append(f"Row {row_number}: invalid student_name, student_id, or student_email.")
            continue
        if student_number in seen_numbers:
            errors.append(f"Row {row_number}: duplicate student_id {student_number}.")
        if email in seen_emails:
            errors.append(f"Row {row_number}: duplicate student_email {email}.")
        seen_numbers.add(student_number)
        seen_emails.add(email)
        rows.append(StudentImportRow(row_number, name, student_number, email))

    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="CSV contains no student rows."
        )
    return rows


def import_students(
    contents: bytes,
    course_id: str,
    users: UserRepository,
    projects: ProjectRepository,
) -> tuple[StudentImportResult, list[tuple[UserRecord, bool]]]:
    rows = parse_student_csv(contents)
    course = projects.get_course(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")

    resolved: list[tuple[StudentImportRow, UserRecord, bool]] = []
    errors: list[str] = []
    for row in rows:
        by_number = users.get_by_student_number(row.student_number)
        by_email = users.get_by_email(row.email)
        if by_number and by_email and by_number.id != by_email.id:
            errors.append(
                f"Row {row.row_number}: student_id and student_email belong to different accounts."
            )
            continue
        user = by_number or by_email
        if user:
            if user.role != Role.STUDENT:
                errors.append(f"Row {row.row_number}: matched account is not a student.")
            elif user.student_number not in (None, row.student_number):
                errors.append(
                    f"Row {row.row_number}: student_id conflicts with the existing account."
                )
            elif user.email.casefold() != row.email.casefold():
                errors.append(f"Row {row.row_number}: email conflicts with the existing account.")
            elif not user.is_active:
                errors.append(f"Row {row.row_number}: matched account is disabled.")
            else:
                resolved.append((row, user, False))
        else:
            resolved.append((row, UserRecord("", row.email, row.name, Role.STUDENT, ""), True))

    for row, user, _ in resolved:
        if user.id and not projects.is_student_enrolled(course_id, user.id):
            for existing_course in projects.list_courses():
                if (
                    existing_course.id != course_id
                    and existing_course.code.casefold() == course.code.casefold()
                    and existing_course.year == course.year
                    and existing_course.term.casefold() == course.term.casefold()
                    and projects.is_student_enrolled(existing_course.id, user.id)
                ):
                    errors.append(
                        f"Row {row.row_number}: student is enrolled in another section "
                        "of this course."
                    )
                    break
    if errors:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=errors)

    for row, user, needs_creation in resolved:
        if not needs_creation and user.student_number is None:
            updated = users.set_student_number(user.id, row.student_number)
            if updated:
                user.student_number = updated.student_number

    created = 0
    enrolled = 0
    already_enrolled = 0
    enrolled_users: list[tuple[UserRecord, bool]] = []
    for row, user, needs_creation in resolved:
        if needs_creation:
            user = create_user(
                users, row.email, row.name, Role.STUDENT, _temporary_password(), row.student_number
            )
            created += 1
            enrolled_users.append((user, True))
        elif projects.is_student_enrolled(course_id, user.id):
            already_enrolled += 1
            continue
        if projects.enroll_student(course_id, user.id):
            enrolled += 1
            enrolled_users.append((user, False))
        else:
            already_enrolled += 1

    return (
        StudentImportResult(
            course_id=course_id,
            total_rows=len(rows),
            created_students=created,
            enrolled_students=enrolled,
            already_enrolled=already_enrolled,
        ),
        enrolled_users,
    )
