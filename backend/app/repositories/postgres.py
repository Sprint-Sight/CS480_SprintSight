from datetime import datetime
from uuid import UUID
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from app.repositories.interfaces import AssessmentRepository, CourseRecord, DocumentRecord, DocumentRepository, IngestionMetricBundle, JiraIngestionRunRecord, JiraIngestionRunRepository, ManualTextRepository, MetricsRepository, ProjectRecord, ProjectRepository, RubricWeightsRecord, RubricWeightsRepository, UserRecord, UserRepository
from app.schemas.assessment import AssessmentReport, JiraCleanedSnapshot, ManualTextPayload
from app.schemas.auth import Role

_PROJECT_COLUMNS = """p.project_id, p.project_name, p.team_name, p.description, p.course_id, c.code AS course_code,
    p.github_repo_url, p.local_repo_path, p.created_by, p.created_at,
    p.jira_email, p.jira_domain, p.jira_project_key, p.jira_api_token_encrypted"""


def ensure_project_credential_schema(pool: ConnectionPool) -> None:
    statements = (
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS team_name VARCHAR(255)",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_email VARCHAR(255)",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_domain VARCHAR(255)",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_project_key VARCHAR(50)",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_api_token_encrypted TEXT",
    )
    with pool.connection() as connection:
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            """CREATE TABLE IF NOT EXISTS project_documents (
                document_id UUID PRIMARY KEY,
                project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                uploader_id UUID NOT NULL REFERENCES users(user_id),
                filename VARCHAR(255) NOT NULL,
                mime_type VARCHAR(100) NOT NULL,
                byte_size BIGINT NOT NULL CHECK (byte_size > 0),
                checksum VARCHAR(64) NOT NULL,
                storage_bucket VARCHAR(255) NOT NULL,
                storage_key TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_project_id ON project_documents(project_id)")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS jira_ingestion_runs (
                run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                sprint_id VARCHAR(100) NOT NULL,
                jira_project_key VARCHAR(50) NOT NULL,
                jql TEXT NOT NULL,
                raw_bucket VARCHAR(255) NOT NULL,
                raw_object_key TEXT NOT NULL UNIQUE,
                issue_count INTEGER NOT NULL CHECK (issue_count >= 0),
                captured_at TIMESTAMPTZ NOT NULL,
                processed_at TIMESTAMPTZ,
                processing_status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (processing_status IN ('pending', 'completed', 'failed')),
                normalization_version VARCHAR(50),
                processing_error TEXT,
                cleaned_snapshot JSONB CHECK (cleaned_snapshot IS NULL OR jsonb_typeof(cleaned_snapshot) = 'object')
            )"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_runs_project_sprint_captured "
            "ON jira_ingestion_runs(project_id, sprint_id, captured_at DESC)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS manual_text (
                manual_text_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                sprint_id VARCHAR(100) NOT NULL,
                expectations_text TEXT NOT NULL CHECK (length(btrim(expectations_text)) BETWEEN 1 AND 5000),
                updated_by UUID NOT NULL REFERENCES users(user_id),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (course_id, project_id, sprint_id),
                FOREIGN KEY (project_id, course_id) REFERENCES projects(project_id, course_id) ON DELETE CASCADE
            )"""
        )


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
            
    def unassign_instructor(self, course_id: str, user_id: str) -> None:   # ← add this
        with self._pool.connection() as connection:
            connection.execute(
                "DELETE FROM course_instructors WHERE course_id = %s AND user_id = %s",
                (UUID(course_id), UUID(user_id)),
            )

    def is_instructor_assigned(self, course_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute("SELECT 1 FROM course_instructors WHERE course_id = %s AND user_id = %s", (UUID(course_id), UUID(user_id))).fetchone()
        return row is not None

    def enroll_student(self, course_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            # Check if student is already in any section of the same course code/term/year
            row = connection.execute("""
                SELECT 1 FROM course_students cs
                JOIN courses c ON c.course_id = cs.course_id
                WHERE cs.user_id = %s
                AND lower(c.code) = lower((SELECT code FROM courses WHERE course_id = %s))
                AND c.year = (SELECT year FROM courses WHERE course_id = %s)
                AND lower(c.term) = lower((SELECT term FROM courses WHERE course_id = %s))
            """, (UUID(user_id), UUID(course_id), UUID(course_id), UUID(course_id))).fetchone()

            if row:
                return False

            inserted = connection.execute("""
                INSERT INTO course_students (course_id, user_id, code, term, year)
                SELECT %s, %s, c.code, c.term, c.year
                FROM courses c
                WHERE c.course_id = %s
                ON CONFLICT DO NOTHING
                RETURNING course_id
            """, (UUID(course_id), UUID(user_id), UUID(course_id))).fetchone()

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
                """INSERT INTO projects (
                    project_id, project_name, team_name, description, course_id,
                    github_repo_url, local_repo_path, created_by,
                    jira_email, jira_domain, jira_project_key, jira_api_token_encrypted
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING project_id, project_name, team_name, description, course_id,
                        github_repo_url, local_repo_path, created_by, created_at,
                        jira_email, jira_domain, jira_project_key, jira_api_token_encrypted""",
                (
                    UUID(project.id), project.project_name, project.team_name,
                    project.description, UUID(project.course_id),
                    project.github_repo_url, project.local_repo_path,
                    UUID(project.created_by), project.jira_email, project.jira_domain,
                    project.jira_project_key, project.jira_api_token_encrypted,
                ),
            ).fetchone()

            course = connection.execute(
                "SELECT code FROM courses WHERE course_id = %s",
                (UUID(project.course_id),)
            ).fetchone()
            row["course_code"] = course["code"]

            # ← FIX: include course_id in the insert
            for member_id in dict.fromkeys(member_ids):
                connection.execute(
                    """INSERT INTO project_members (project_id, course_id, user_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING""",
                    (UUID(project.id), UUID(project.course_id), UUID(member_id))
                )

        return self._project(row)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                f"""SELECT {_PROJECT_COLUMNS}
                FROM projects p JOIN courses c ON c.course_id = p.course_id WHERE p.project_id = %s""",
                (UUID(project_id),),
            ).fetchone()
        return self._project(row) if row else None

    def list_projects(self, course_id: str) -> list[ProjectRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                f"""SELECT {_PROJECT_COLUMNS}
                FROM projects p JOIN courses c ON c.course_id = p.course_id WHERE p.course_id = %s ORDER BY p.project_name""",
                (UUID(course_id),),
            ).fetchall()
        return [self._project(row) for row in rows]

    def update_project(
        self,
        project_id: str,
        project_name: str,
        team_name: str,
        description: str | None,
        github_repo_url: str | None,
        local_repo_path: str | None,
        jira_email: str | None,
        jira_domain: str | None,
        jira_project_key: str | None,
        jira_api_token_encrypted: str | None,
    ) -> ProjectRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE projects SET project_name = %s, team_name = %s, description = %s, github_repo_url = %s, local_repo_path = %s,
                    jira_email = %s, jira_domain = %s, jira_project_key = %s, jira_api_token_encrypted = %s
                WHERE project_id = %s RETURNING project_id, project_name, team_name, description, course_id, github_repo_url, local_repo_path, created_by, created_at, jira_email, jira_domain, jira_project_key, jira_api_token_encrypted""",
                (
                    project_name,
                    team_name,
                    description,
                    github_repo_url,
                    local_repo_path,
                    jira_email,
                    jira_domain,
                    jira_project_key,
                    jira_api_token_encrypted,
                    UUID(project_id),
                ),
            ).fetchone()
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
            # Get course_id from the project first
            project_row = connection.execute(
                "SELECT course_id FROM projects WHERE project_id = %s",
                (UUID(project_id),)
            ).fetchone()

            if not project_row:
                raise ValueError(f"Project {project_id} not found")

            course_id = project_row["course_id"]

            connection.execute(
                "DELETE FROM project_members WHERE project_id = %s",
                (UUID(project_id),)
            )

            # ← FIX: include course_id in the insert
            for member_id in dict.fromkeys(member_ids):
                connection.execute(
                    """INSERT INTO project_members (project_id, course_id, user_id)
                    VALUES (%s, %s, %s)""",
                    (UUID(project_id), course_id, UUID(member_id))
                )

    def list_member_ids(self, project_id: str) -> list[str]:
        with self._pool.connection() as connection:
            rows = connection.execute("SELECT user_id FROM project_members WHERE project_id = %s", (UUID(project_id),)).fetchall()
        return [str(row["user_id"]) for row in rows]

    @staticmethod
    def _project(row: dict) -> ProjectRecord:
        return ProjectRecord(
            str(row["project_id"]),
            row["project_name"],
            row["team_name"],
            row["description"],
            str(row["course_id"]),
            row["course_code"],
            row["github_repo_url"],
            row["local_repo_path"],
            str(row["created_by"]),
            row["created_at"],
            row.get("jira_email"),
            row.get("jira_domain"),
            row.get("jira_project_key"),
            row.get("jira_api_token_encrypted"),
        )


class PostgresDocumentRepository(DocumentRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @staticmethod
    def _document(row: dict) -> DocumentRecord:
        return DocumentRecord(
            id=str(row["document_id"]),
            project_id=str(row["project_id"]),
            filename=row["filename"],
            mime_type=row["mime_type"],
            byte_size=row["byte_size"],
            checksum=row["checksum"],
            storage_bucket=row["storage_bucket"],
            storage_key=row["storage_key"],
            uploaded_by=str(row["uploader_id"]),
            created_at=row["created_at"],
        )

    def create_document(self, document: DocumentRecord) -> DocumentRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO project_documents
                (document_id, project_id, uploader_id, filename, mime_type, byte_size,
                 checksum, storage_bucket, storage_key, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING document_id, project_id, uploader_id, filename, mime_type,
                          byte_size, checksum, storage_bucket, storage_key, created_at""",
                (UUID(document.id), UUID(document.project_id), UUID(document.uploaded_by),
                 document.filename, document.mime_type, document.byte_size, document.checksum,
                 document.storage_bucket, document.storage_key, document.created_at),
            ).fetchone()
        return self._document(row)

    def list_documents(self, project_id: str) -> list[DocumentRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT document_id, project_id, uploader_id, filename, mime_type,
                          byte_size, checksum, storage_bucket, storage_key, created_at
                   FROM project_documents WHERE project_id = %s
                   ORDER BY created_at, document_id""",
                (UUID(project_id),),
            ).fetchall()
        return [self._document(row) for row in rows]

    def get_document(self, project_id: str, document_id: str) -> DocumentRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT document_id, project_id, uploader_id, filename, mime_type,
                          byte_size, checksum, storage_bucket, storage_key, created_at
                   FROM project_documents WHERE project_id = %s AND document_id = %s""",
                (UUID(project_id), UUID(document_id)),
            ).fetchone()
        return self._document(row) if row else None


class PostgresManualTextRepository(ManualTextRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def upsert(self, payload: ManualTextPayload, updated_by: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """INSERT INTO manual_text
                (course_id, project_id, sprint_id, expectations_text, updated_by)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (course_id, project_id, sprint_id)
                DO UPDATE SET expectations_text = EXCLUDED.expectations_text,
                              updated_by = EXCLUDED.updated_by,
                              updated_at = CURRENT_TIMESTAMP""",
                (UUID(payload.course_id), UUID(payload.project_id), payload.sprint_id,
                 " ".join(payload.expectations_text.split()), UUID(updated_by)),
            )

    def get(self, course_id: str, project_id: str, sprint_id: str) -> str | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT expectations_text FROM manual_text
                WHERE course_id = %s AND project_id = %s AND sprint_id = %s""",
                (UUID(course_id), UUID(project_id), sprint_id),
            ).fetchone()
        return row["expectations_text"] if row else None


def ensure_rubric_weights_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS rubric_weight_configs (
                course_id UUID PRIMARY KEY REFERENCES courses(course_id) ON DELETE CASCADE,
                weights JSONB NOT NULL,
                updated_by UUID NOT NULL REFERENCES users(user_id),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )


class PostgresRubricWeightsRepository(RubricWeightsRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_weights(self, course_id: str) -> RubricWeightsRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT course_id, weights, updated_by, updated_at
                FROM rubric_weight_configs WHERE course_id = %s""",
                (UUID(course_id),),
            ).fetchone()
        if not row:
            return None
        return RubricWeightsRecord(
            course_id=str(row["course_id"]),
            weights=row["weights"],
            updated_by=str(row["updated_by"]),
            updated_at=row["updated_at"],
        )

    def set_weights(self, course_id: str, weights: dict[str, float], updated_by: str) -> RubricWeightsRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO rubric_weight_configs (course_id, weights, updated_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (course_id)
                DO UPDATE SET weights = EXCLUDED.weights,
                              updated_by = EXCLUDED.updated_by,
                              updated_at = CURRENT_TIMESTAMP
                RETURNING course_id, weights, updated_by, updated_at""",
                (UUID(course_id), Json(weights), UUID(updated_by)),
            ).fetchone()
        return RubricWeightsRecord(
            course_id=str(row["course_id"]),
            weights=row["weights"],
            updated_by=str(row["updated_by"]),
            updated_at=row["updated_at"],
        )


def ensure_assessment_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS assessment_reports (
                report_id UUID PRIMARY KEY,
                model_name VARCHAR(255) NOT NULL,
                mode VARCHAR(255) NOT NULL,
                course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                sprint_id VARCHAR(100) NOT NULL,
                generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                rubric_weights JSONB NOT NULL,
                team_score JSONB NOT NULL,
                individual_scores JSONB NOT NULL DEFAULT '[]'::jsonb,
                recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
                rubric_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
                strengths JSONB NOT NULL DEFAULT '[]'::jsonb,
                weaknesses JSONB NOT NULL DEFAULT '[]'::jsonb,
                override BOOLEAN NOT NULL DEFAULT FALSE,
                requirements_score NUMERIC(5, 2) CHECK (requirements_score BETWEEN 0 AND 100),
                code_quality_score NUMERIC(5, 2) CHECK (code_quality_score BETWEEN 0 AND 100),
                documentation_score NUMERIC(5, 2) CHECK (documentation_score BETWEEN 0 AND 100),
                collaboration_score NUMERIC(5, 2) CHECK (collaboration_score BETWEEN 0 AND 100),
                requirements_justification VARCHAR(500),
                code_quality_justification VARCHAR(500),
                documentation_justification VARCHAR(500),
                collaboration_justification VARCHAR(500),
                CONSTRAINT assessment_reports_manual_fields_check CHECK (
                    NOT override OR (
                        requirements_score IS NOT NULL AND
                        code_quality_score IS NOT NULL AND
                        documentation_score IS NOT NULL AND
                        collaboration_score IS NOT NULL AND
                        requirements_justification IS NOT NULL AND
                        code_quality_justification IS NOT NULL AND
                        documentation_justification IS NOT NULL AND
                        collaboration_justification IS NOT NULL
                    )
                )
            )"""
        )
        for statement in (
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS override BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS requirements_score NUMERIC(5, 2)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS code_quality_score NUMERIC(5, 2)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS documentation_score NUMERIC(5, 2)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS collaboration_score NUMERIC(5, 2)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS requirements_justification VARCHAR(500)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS code_quality_justification VARCHAR(500)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS documentation_justification VARCHAR(500)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS collaboration_justification VARCHAR(500)",
        ):
            connection.execute(statement)
        connection.execute(
            """DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'assessment_reports_manual_fields_check'
                ) THEN
                    ALTER TABLE assessment_reports
                    ADD CONSTRAINT assessment_reports_manual_fields_check CHECK (
                        NOT override OR (
                            requirements_score IS NOT NULL AND
                            code_quality_score IS NOT NULL AND
                            documentation_score IS NOT NULL AND
                            collaboration_score IS NOT NULL AND
                            requirements_justification IS NOT NULL AND
                            code_quality_justification IS NOT NULL AND
                            documentation_justification IS NOT NULL AND
                            collaboration_justification IS NOT NULL
                        )
                    );
                END IF;
            END $$"""
        )
        connection.execute("DROP TABLE IF EXISTS assessment_override")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_assessment_reports_course_project_sprint ON assessment_reports(course_id, project_id, sprint_id, generated_at DESC)")


class PostgresAssessmentRepository(AssessmentRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def save_report(self, report: AssessmentReport) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """INSERT INTO assessment_reports
                (report_id, model_name, mode, course_id, project_id,
                 sprint_id, generated_at, rubric_weights, team_score,
                 individual_scores, recommendations, rubric_scores,
                 strengths, weaknesses)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_id)
                DO UPDATE SET model_name = EXCLUDED.model_name,
                              mode = EXCLUDED.mode,
                              course_id = EXCLUDED.course_id,
                              project_id = EXCLUDED.project_id,
                              sprint_id = EXCLUDED.sprint_id,
                              generated_at = EXCLUDED.generated_at,
                              rubric_weights = EXCLUDED.rubric_weights,
                              team_score = EXCLUDED.team_score,
                              individual_scores = EXCLUDED.individual_scores,
                              recommendations = EXCLUDED.recommendations,
                              rubric_scores = EXCLUDED.rubric_scores,
                              strengths = EXCLUDED.strengths,
                              weaknesses = EXCLUDED.weaknesses""",
                (
                    UUID(report.report_id.replace('rpt-', '')) if report.report_id.startswith('rpt-') else UUID(report.report_id),
                    report.model_name,
                    report.mode,
                    UUID(report.course_id),
                    UUID(report.project_id),
                    report.sprint_id,
                    report.generated_at,
                    Json(report.rubric_weights),
                    Json(report.team_score.model_dump(mode='json')),
                    Json([score.model_dump(mode='json') for score in report.individual_scores]),
                    Json(report.recommendations),
                    Json({k: v.model_dump(mode='json') for k, v in report.rubric_scores.items()}),
                    Json(report.strengths),
                    Json(report.weaknesses),
                ),
            )

    def get_report(self, report_id: str) -> AssessmentReport | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM assessment_reports WHERE report_id = %s",
                (UUID(report_id),),
            ).fetchone()
            return self._report(row) if row else None

    def update_manual_assessment(self, report_id: str, patch: dict[str, object]) -> AssessmentReport | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE assessment_reports
                SET override = TRUE,
                    requirements_score = %s,
                    code_quality_score = %s,
                    documentation_score = %s,
                    collaboration_score = %s,
                    requirements_justification = %s,
                    code_quality_justification = %s,
                    documentation_justification = %s,
                    collaboration_justification = %s
                WHERE report_id = %s
                RETURNING *""",
                (
                    patch["requirements_score"],
                    patch["code_quality_score"],
                    patch["documentation_score"],
                    patch["collaboration_score"],
                    patch["requirements_justification"],
                    patch["code_quality_justification"],
                    patch["documentation_justification"],
                    patch["collaboration_justification"],
                    UUID(report_id.replace("rpt-", "")),
                ),
            ).fetchone()
        return self._report(row) if row else None

    def list_reports(self, course_id: str, project_id: str, sprint_id: str) -> list[AssessmentReport]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM assessment_reports
                WHERE course_id = %s AND project_id = %s AND sprint_id = %s
                ORDER BY generated_at DESC""",
                (UUID(course_id), UUID(project_id), sprint_id),
            ).fetchall()
        return [self._report(row) for row in rows or []]

    def list_project_reports(self, course_id: str, project_id: str) -> list[AssessmentReport]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM assessment_reports
                WHERE course_id = %s AND project_id = %s
                ORDER BY generated_at DESC""",
                (UUID(course_id), UUID(project_id)),
            ).fetchall()
        return [self._report(row) for row in rows or []]

    def get_latest_report(self, course_id: str, project_id: str, sprint_id: str) -> AssessmentReport | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT * FROM assessment_reports
                WHERE course_id = %s AND project_id = %s AND sprint_id = %s
                ORDER BY generated_at DESC LIMIT 1""",
                (UUID(course_id), UUID(project_id), sprint_id),
            ).fetchone()
            return self._report(row) if row else None

    @staticmethod
    def _report(row: dict) -> AssessmentReport:
        from app.schemas.assessment import TeamScore, StudentScore, RubricDimensionScoreDetail
        rubric_scores = {}
        if row.get("rubric_scores"):
            for key, value in row["rubric_scores"].items():
                rubric_scores[key] = RubricDimensionScoreDetail.model_validate(value)

        return AssessmentReport(
            report_id=str(row["report_id"]),
            model_name=row["model_name"],
            mode=row["mode"],
            course_id=str(row["course_id"]),
            project_id=str(row["project_id"]),
            sprint_id=row["sprint_id"],
            generated_at=row["generated_at"],
            rubric_weights=row["rubric_weights"],
            team_score=TeamScore.model_validate(row["team_score"]),
            individual_scores=[StudentScore.model_validate(x) for x in row["individual_scores"]],
            recommendations=row["recommendations"],
            rubric_scores=rubric_scores,
            strengths=row["strengths"],
            weaknesses=row["weaknesses"],
            override=row.get("override", False),
            requirements_score=float(row["requirements_score"]) if row.get("requirements_score") is not None else None,
            code_quality_score=float(row["code_quality_score"]) if row.get("code_quality_score") is not None else None,
            documentation_score=float(row["documentation_score"]) if row.get("documentation_score") is not None else None,
            collaboration_score=float(row["collaboration_score"]) if row.get("collaboration_score") is not None else None,
            requirements_justification=row.get("requirements_justification"),
            code_quality_justification=row.get("code_quality_justification"),
            documentation_justification=row.get("documentation_justification"),
            collaboration_justification=row.get("collaboration_justification"),
        )


class PostgresMetricsRepository(MetricsRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def save_metrics(self, metrics: IngestionMetricBundle) -> None:
        with self._pool.connection() as connection:
            with connection.transaction():
                connection.execute(
                    "DELETE FROM ingestion_runs WHERE project_id = %s AND sprint_id = %s",
                    (UUID(metrics.project_id), metrics.sprint_id),
                )
                head_sha = metrics.commits[0].sha if metrics.commits else None
                run = connection.execute(
                    """INSERT INTO ingestion_runs
                    (course_id, project_id, sprint_id, local_repo_path, head_sha,
                     commit_frequency, code_churn, pr_turnaround_hours,
                     assigned_story_points, completion_percent, captured_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING ingestion_run_id""",
                    (UUID(metrics.course_id), UUID(metrics.project_id), metrics.sprint_id,
                     metrics.local_repo_path, metrics.head_sha, metrics.commit_frequency, metrics.code_churn,
                     metrics.pr_turnaround_hours, metrics.assigned_story_points,
                     metrics.completion_percent, metrics.captured_at),
                ).fetchone()
                for commit in metrics.commits:
                    connection.execute(
                        """INSERT INTO ingestion_commits
                        (ingestion_run_id, sha, author, author_email, student_id, message, timestamp,
                         lines_added, lines_deleted, files_changed)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (run["ingestion_run_id"], commit.sha, commit.author, commit.author_email, commit.student_id, commit.message,
                         commit.timestamp, commit.lines_added, commit.lines_deleted,
                         Json([file.model_dump() for file in commit.files_changed])),
                    )

    def get_metrics(
        self,
        course_id: str,
        project_id: str,
        sprint_id: str,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
    ) -> IngestionMetricBundle | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT ir.course_id, ir.project_id, ir.sprint_id,
                    ir.local_repo_path, ir.head_sha,
                    ir.commit_frequency, ir.code_churn, ir.pr_turnaround_hours,
                    ir.assigned_story_points, ir.completion_percent, ir.captured_at
                    FROM ingestion_runs ir
                    WHERE ir.course_id = %s AND ir.project_id = %s AND ir.sprint_id = %s""",
                (UUID(course_id), UUID(project_id), sprint_id),
            ).fetchone()
            if not row:
                return None
            commit_filters = [
                "ingestion_run_id = (SELECT ingestion_run_id FROM ingestion_runs "
                "WHERE course_id = %s AND project_id = %s AND sprint_id = %s)"
            ]
            commit_params: list[object] = [UUID(course_id), UUID(project_id), sprint_id]
            if start_datetime is not None:
                commit_filters.append("timestamp >= %s")
                commit_params.append(start_datetime)
            if end_datetime is not None:
                commit_filters.append("timestamp < %s")
                commit_params.append(end_datetime)
            commit_rows = connection.execute(
                """SELECT sha, author, author_email, student_id, message, timestamp, lines_added,
                    lines_deleted, files_changed
                    FROM ingestion_commits WHERE """
                + " AND ".join(commit_filters)
                + " ORDER BY timestamp, sha",
                commit_params,
            ).fetchall()
        from app.schemas.assessment import CommitInfo
        return IngestionMetricBundle(
            course_id=str(row["course_id"]), project_id=str(row["project_id"]),
            sprint_id=row["sprint_id"], commit_frequency=row["commit_frequency"],
            code_churn=row["code_churn"], pr_turnaround_hours=row["pr_turnaround_hours"],
            assigned_story_points=row["assigned_story_points"],
            completion_percent=row["completion_percent"],
            commits=[
                CommitInfo(
                    **{
                        **dict(commit),
                        "student_id": str(commit["student_id"]) if commit["student_id"] else None,
                        "files_changed": commit["files_changed"],
                    }
                )
                for commit in commit_rows
            ],
            local_repo_path=row["local_repo_path"],
            head_sha=row["head_sha"],
            captured_at=row["captured_at"],
        )

    def get_metrics_page(
        self,
        course_id: str,
        project_id: str,
        sprint_id: str,
        limit: int,
        offset: int,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
    ) -> tuple[IngestionMetricBundle | None, int]:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT ir.course_id, ir.project_id, ir.sprint_id,
                    ir.local_repo_path, ir.head_sha, ir.commit_frequency,
                    ir.code_churn, ir.pr_turnaround_hours,
                    ir.assigned_story_points, ir.completion_percent, ir.captured_at,
                    ir.ingestion_run_id
                    FROM ingestion_runs ir
                    WHERE ir.course_id = %s AND ir.project_id = %s AND ir.sprint_id = %s""",
                (UUID(course_id), UUID(project_id), sprint_id),
            ).fetchone()
            if not row:
                return None, 0
            commit_filters = ["ingestion_run_id = %s"]
            commit_params: list[object] = [row["ingestion_run_id"]]
            if start_datetime is not None:
                commit_filters.append("timestamp >= %s")
                commit_params.append(start_datetime)
            if end_datetime is not None:
                commit_filters.append("timestamp < %s")
                commit_params.append(end_datetime)
            total = connection.execute(
                "SELECT COUNT(*) AS total FROM ingestion_commits WHERE "
                + " AND ".join(commit_filters),
                commit_params,
            ).fetchone()["total"]
            commit_rows = connection.execute(
                """SELECT sha, author, author_email, student_id, message, timestamp, lines_added,
                    lines_deleted, files_changed
                    FROM ingestion_commits
                    WHERE """
                + " AND ".join(commit_filters)
                + " ORDER BY timestamp, sha LIMIT %s OFFSET %s",
                [*commit_params, limit, offset],
            ).fetchall()
        from app.schemas.assessment import CommitInfo
        return IngestionMetricBundle(
            course_id=str(row["course_id"]), project_id=str(row["project_id"]),
            sprint_id=row["sprint_id"], commit_frequency=row["commit_frequency"],
            code_churn=row["code_churn"], pr_turnaround_hours=row["pr_turnaround_hours"],
            assigned_story_points=row["assigned_story_points"],
            completion_percent=row["completion_percent"],
            commits=[
                CommitInfo(
                    **{
                        **dict(commit),
                        "student_id": str(commit["student_id"]) if commit["student_id"] else None,
                        "files_changed": commit["files_changed"],
                    }
                )
                for commit in commit_rows
            ],
            local_repo_path=row["local_repo_path"], head_sha=row["head_sha"],
            captured_at=row["captured_at"],
        ), total


class PostgresJiraIngestionRunRepository(JiraIngestionRunRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @staticmethod
    def _run(row: dict) -> JiraIngestionRunRecord:
        snapshot = row.get("cleaned_snapshot")
        return JiraIngestionRunRecord(
            id=str(row["run_id"]),
            course_id=str(row["course_id"]),
            project_id=str(row["project_id"]),
            sprint_id=row["sprint_id"],
            jira_project_key=row["jira_project_key"],
            jql=row["jql"],
            raw_bucket=row["raw_bucket"],
            raw_object_key=row["raw_object_key"],
            issue_count=row["issue_count"],
            captured_at=row["captured_at"],
            processed_at=row["processed_at"],
            processing_status=row["processing_status"],
            normalization_version=row["normalization_version"],
            processing_error=row["processing_error"],
            cleaned_snapshot=JiraCleanedSnapshot.model_validate(snapshot) if snapshot else None,
        )

    def create_run(self, run: JiraIngestionRunRecord) -> JiraIngestionRunRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO jira_ingestion_runs
                (run_id, course_id, project_id, sprint_id, jira_project_key, jql,
                 raw_bucket, raw_object_key, issue_count, captured_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *""",
                (UUID(run.id), UUID(run.course_id), UUID(run.project_id), run.sprint_id,
                 run.jira_project_key, run.jql, run.raw_bucket, run.raw_object_key,
                 run.issue_count, run.captured_at),
            ).fetchone()
        return self._run(row)

    def get_run(self, project_id: str, sprint_id: str, run_id: str) -> JiraIngestionRunRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM jira_ingestion_runs WHERE project_id = %s AND sprint_id = %s AND run_id = %s",
                (UUID(project_id), sprint_id, UUID(run_id)),
            ).fetchone()
        return self._run(row) if row else None

    def list_project_runs(self, project_id: str) -> list[JiraIngestionRunRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jira_ingestion_runs WHERE project_id = %s ORDER BY captured_at DESC, run_id DESC",
                (UUID(project_id),),
            ).fetchall()
        return [self._run(row) for row in rows]

    def list_runs(self, project_id: str, sprint_id: str) -> list[JiraIngestionRunRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jira_ingestion_runs WHERE project_id = %s AND sprint_id = %s ORDER BY captured_at DESC, run_id DESC",
                (UUID(project_id), sprint_id),
            ).fetchall()
        return [self._run(row) for row in rows]

    def update_processed_run(self, project_id: str, sprint_id: str, run_id: str, status: str, processed_at: datetime | None, normalization_version: str | None, processing_error: str | None, cleaned_snapshot: JiraCleanedSnapshot | None) -> JiraIngestionRunRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE jira_ingestion_runs SET processing_status = %s,
                processed_at = %s, normalization_version = %s, processing_error = %s,
                cleaned_snapshot = %s
                WHERE project_id = %s AND sprint_id = %s AND run_id = %s
                RETURNING *""",
                (status, processed_at, normalization_version, processing_error,
                 Json(cleaned_snapshot.model_dump(mode="json")) if cleaned_snapshot else None,
                 UUID(project_id), sprint_id, UUID(run_id)),
            ).fetchone()
        return self._run(row) if row else None


def create_user_pool(connection_string: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=connection_string,
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=5,
        open=False,
    )