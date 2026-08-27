from datetime import datetime
from uuid import UUID
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.repositories.interfaces import CourseRecord, ProjectRecord, ProjectRepository, UserRecord, UserRepository
from app.schemas.auth import Role


class PostgresUserRepository(UserRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_by_email(self, email: str) -> UserRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version
                FROM users
                WHERE lower(email) = lower(%s)
                """,
                (email,),
            ).fetchone()
        return self._to_record(row) if row else None

    def get_by_id(self, user_id: str) -> UserRecord | None:
        try:
            parsed_id = UUID(user_id)
        except ValueError:
            return None

        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version
                FROM users
                WHERE user_id = %s
                """,
                (parsed_id,),
            ).fetchone()
        return self._to_record(row) if row else None

    def record_login(self, user_id: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = %s",
                (UUID(user_id),),
            )

    def revoke_access_token(self, token_id: str, user_id: str, expires_at: datetime) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO revoked_access_tokens (token_id, user_id, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (token_id) DO NOTHING
                """,
                (UUID(token_id), UUID(user_id), expires_at),
            )

    def is_access_token_revoked(self, token_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM revoked_access_tokens
                WHERE token_id = %s AND expires_at > CURRENT_TIMESTAMP
                """,
                (UUID(token_id),),
            ).fetchone()
        return row is not None

    def list_users(self) -> list[UserRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version FROM users ORDER BY email"
            ).fetchall()
        return [self._to_record(row) for row in rows]

    def create_user(self, user: UserRecord) -> UserRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO users (user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version""",
                (UUID(user.id), user.email.lower(), user.full_name, user.hashed_password, user.role.value,
                 user.is_active, user.must_change_password, user.token_version),
            ).fetchone()
        return self._to_record(row)

    def update_user(self, user_id: str, email: str, full_name: str, role: Role, is_active: bool) -> UserRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE users SET email = %s, full_name = %s, role = %s, is_active = %s
                WHERE user_id = %s
                RETURNING user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version""",
                (email.lower(), full_name, role.value, is_active, UUID(user_id)),
            ).fetchone()
        return self._to_record(row) if row else None

    def update_password(self, user_id: str, hashed_password: str, must_change_password: bool) -> UserRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE users SET password_hash = %s, must_change_password = %s, token_version = token_version + 1
                WHERE user_id = %s
                RETURNING user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version""",
                (hashed_password, must_change_password, UUID(user_id)),
            ).fetchone()
        return self._to_record(row) if row else None

    @staticmethod
    def _to_record(row: tuple | dict) -> UserRecord:
        if not isinstance(row, dict):
            raise TypeError("Postgres user rows must use dict_row")
        return UserRecord(
            id=str(row["user_id"]),
            email=row["email"],
            full_name=row["full_name"],
            role=Role(row["role"]),
            hashed_password=row["password_hash"],
            is_active=row["is_active"],
            must_change_password=row["must_change_password"],
            token_version=row["token_version"],
        )


class PostgresProjectRepository(ProjectRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create_course(self, code: str, name: str, section: str, year: int, term: str, created_by: str) -> CourseRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                "INSERT INTO courses (code, name, section, year, term, created_by) VALUES (%s, %s, %s, %s, %s, %s) RETURNING course_id, code, name, section, year, term, created_by, created_at",
                (code.upper(), name, section, year, term, UUID(created_by)),
            ).fetchone()
            connection.execute("INSERT INTO course_instructors (course_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (row["course_id"], UUID(created_by)))
        return self._course(row)

    def get_course(self, course_id: str) -> CourseRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT course_id, code, name, section, year, term, created_by, created_at FROM courses WHERE course_id = %s", (UUID(course_id),)
            ).fetchone()
        return self._course(row) if row else None

    def list_courses(self) -> list[CourseRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute("SELECT course_id, code, name, section, year, term, created_by, created_at FROM courses ORDER BY code, year, term, section").fetchall()
        return [self._course(row) for row in rows]

    @staticmethod
    def _course(row: dict) -> CourseRecord:
        return CourseRecord(str(row["course_id"]), row["code"], row["name"], row["section"], row["year"], row["term"], str(row["created_by"]), row["created_at"])

    def assign_instructor(self, course_id: str, user_id: str) -> None:
        with self._pool.connection() as connection:
            connection.execute("INSERT INTO course_instructors (course_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (UUID(course_id), UUID(user_id)))

    def is_instructor_assigned(self, course_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute("SELECT 1 FROM course_instructors WHERE course_id = %s AND user_id = %s", (UUID(course_id), UUID(user_id))).fetchone()
        return row is not None

    def enroll_student(self, course_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute("""SELECT 1 FROM course_students cs JOIN courses c ON c.course_id = cs.course_id
                WHERE cs.user_id = %s AND lower(c.code) = lower((SELECT code FROM courses WHERE course_id = %s))""", (UUID(user_id), UUID(course_id))).fetchone()
            if row:
                return False
            inserted = connection.execute("INSERT INTO course_students (course_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING course_id", (UUID(course_id), UUID(user_id))).fetchone()
        return inserted is not None

    def is_student_enrolled(self, course_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute("SELECT 1 FROM course_students WHERE course_id = %s AND user_id = %s", (UUID(course_id), UUID(user_id))).fetchone()
        return row is not None

    def unenroll_student(self, course_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute("DELETE FROM course_students WHERE course_id = %s AND user_id = %s RETURNING course_id", (UUID(course_id), UUID(user_id))).fetchone()
        return row is not None

    def list_enrolled_student_ids(self, course_id: str) -> list[str]:
        with self._pool.connection() as connection:
            rows = connection.execute("SELECT user_id FROM course_students WHERE course_id = %s ORDER BY enrolled_at", (UUID(course_id),)).fetchall()
        return [str(row["user_id"]) for row in rows]

    def list_student_course_codes(self, user_id: str) -> list[str]:
        with self._pool.connection() as connection:
            rows = connection.execute("SELECT c.code FROM course_students cs JOIN courses c ON c.course_id = cs.course_id WHERE cs.user_id = %s", (UUID(user_id),)).fetchall()
        return [row["code"] for row in rows]

    def update_course(self, course_id: str, code: str, name: str, section: str, year: int, term: str) -> CourseRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute("""UPDATE courses SET code = %s, name = %s, section = %s, year = %s, term = %s
                WHERE course_id = %s RETURNING course_id, code, name, section, year, term, created_by, created_at""", (code.upper(), name, section, year, term, UUID(course_id))).fetchone()
        return self._course(row) if row else None

    def delete_course(self, course_id: str) -> CourseRecord | None:
        course = self.get_course(course_id)
        if course:
            with self._pool.connection() as connection:
                connection.execute("DELETE FROM courses WHERE course_id = %s", (UUID(course_id),))
        return course

    def create_project(self, project: ProjectRecord, member_ids: list[str]) -> ProjectRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO projects (project_id, project_name, description, course_id, github_repo_url, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING project_id, project_name, description, course_id, github_repo_url, created_by, created_at""",
                (UUID(project.id), project.project_name, project.description, UUID(project.course_id), project.github_repo_url, UUID(project.created_by)),
            ).fetchone()
            course = connection.execute("SELECT code FROM courses WHERE course_id = %s", (UUID(project.course_id),)).fetchone()
            row["course_code"] = course["code"]
            for member_id in dict.fromkeys(member_ids):
                connection.execute("INSERT INTO project_members (project_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (UUID(project.id), UUID(member_id)))
        return self._project(row)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute("""SELECT p.project_id, p.project_name, p.description, p.course_id, c.code AS course_code, p.github_repo_url, p.created_by, p.created_at
                FROM projects p JOIN courses c ON c.course_id = p.course_id WHERE p.project_id = %s""", (UUID(project_id),)).fetchone()
        return self._project(row) if row else None

    def list_projects(self, course_id: str) -> list[ProjectRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute("""SELECT p.project_id, p.project_name, p.description, p.course_id, c.code AS course_code, p.github_repo_url, p.created_by, p.created_at
                FROM projects p JOIN courses c ON c.course_id = p.course_id WHERE p.course_id = %s ORDER BY p.project_name""", (UUID(course_id),)).fetchall()
        return [self._project(row) for row in rows]

    def update_project(self, project_id: str, project_name: str, description: str | None, github_repo_url: str | None) -> ProjectRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute("""UPDATE projects SET project_name = %s, description = %s, github_repo_url = %s
                WHERE project_id = %s RETURNING project_id, project_name, description, course_id, github_repo_url, created_by, created_at""", (project_name, description, github_repo_url, UUID(project_id))).fetchone()
            if row:
                course = connection.execute("SELECT code FROM courses WHERE course_id = %s", (row["course_id"],)).fetchone()
                row["course_code"] = course["code"]
        return self._project(row) if row else None

    def delete_project(self, project_id: str) -> ProjectRecord | None:
        project = self.get_project(project_id)
        if project:
            with self._pool.connection() as connection:
                connection.execute("DELETE FROM projects WHERE project_id = %s", (UUID(project_id),))
        return project

    def set_members(self, project_id: str, member_ids: list[str]) -> None:
        with self._pool.connection() as connection:
            connection.execute("DELETE FROM project_members WHERE project_id = %s", (UUID(project_id),))
            for member_id in dict.fromkeys(member_ids):
                connection.execute("INSERT INTO project_members (project_id, user_id) VALUES (%s, %s)", (UUID(project_id), UUID(member_id)))

    def list_member_ids(self, project_id: str) -> list[str]:
        with self._pool.connection() as connection:
            rows = connection.execute("SELECT user_id FROM project_members WHERE project_id = %s", (UUID(project_id),)).fetchall()
        return [str(row["user_id"]) for row in rows]

    @staticmethod
    def _project(row: dict) -> ProjectRecord:
        return ProjectRecord(str(row["project_id"]), row["project_name"], row["description"], str(row["course_id"]), row["course_code"], row["github_repo_url"], str(row["created_by"]), row["created_at"])


def create_user_pool(connection_string: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=connection_string,
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=5,
        open=False,
    )