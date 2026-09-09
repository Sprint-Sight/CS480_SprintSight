from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from psycopg_pool import ConnectionPool


@dataclass
class ManualOverrideRecord:
    override_id: str
    course_id: str
    project_id: str
    sprint_id: str
    team_name: str
    requirements_score: float
    code_quality_score: float
    testing_score: float
    documentation_score: float
    collaboration_score: float
    total_score: float
    graded_by: str
    created_at: datetime
    updated_at: datetime


class ManualOverrideRepository:
    def upsert(
        self,
        *,
        course_id: str,
        project_id: str,
        sprint_id: str,
        team_name: str,
        requirements_score: float,
        code_quality_score: float,
        testing_score: float,
        documentation_score: float,
        collaboration_score: float,
        total_score: float,
        graded_by: str,
    ) -> ManualOverrideRecord:
        raise NotImplementedError

    def list(
        self, *, course_id: str, project_id: str, sprint_id: str | None = None
    ) -> list[ManualOverrideRecord]:
        raise NotImplementedError


class InMemoryManualOverrideRepository(ManualOverrideRepository):
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], ManualOverrideRecord] = {}

    def upsert(self, **values: object) -> ManualOverrideRecord:
        key = (str(values["course_id"]), str(values["project_id"]), str(values["sprint_id"]))
        now = datetime.now().astimezone()
        existing = self._records.get(key)
        record = ManualOverrideRecord(
            override_id=existing.override_id if existing else str(uuid4()),
            course_id=key[0],
            project_id=key[1],
            sprint_id=key[2],
            team_name=str(values["team_name"]),
            requirements_score=float(values["requirements_score"]),
            code_quality_score=float(values["code_quality_score"]),
            testing_score=float(values["testing_score"]),
            documentation_score=float(values["documentation_score"]),
            collaboration_score=float(values["collaboration_score"]),
            total_score=float(values["total_score"]),
            graded_by=str(values["graded_by"]),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._records[key] = record
        return record

    def list(
        self, *, course_id: str, project_id: str, sprint_id: str | None = None
    ) -> list[ManualOverrideRecord]:
        records = [
            record
            for record in self._records.values()
            if record.course_id == course_id
            and record.project_id == project_id
            and (sprint_id is None or record.sprint_id == sprint_id)
        ]
        return sorted(
            records,
            key=lambda record: (record.sprint_id, record.updated_at),
            reverse=True,
        )


def ensure_manual_scoring_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS assessment_override (
                override_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                course_id UUID NOT NULL,
                project_id UUID NOT NULL,
                sprint_id VARCHAR(100) NOT NULL,
                requirements_score NUMERIC(5, 2) NOT NULL
                    CHECK (requirements_score BETWEEN 0 AND 100),
                code_quality_score NUMERIC(5, 2) NOT NULL
                    CHECK (code_quality_score BETWEEN 0 AND 100),
                testing_score NUMERIC(5, 2) NOT NULL
                    CHECK (testing_score BETWEEN 0 AND 100),
                documentation_score NUMERIC(5, 2) NOT NULL
                    CHECK (documentation_score BETWEEN 0 AND 100),
                collaboration_score NUMERIC(5, 2) NOT NULL
                    CHECK (collaboration_score BETWEEN 0 AND 100),
                total_score NUMERIC(5, 2) GENERATED ALWAYS AS (
                    (
                        requirements_score + code_quality_score + testing_score
                        + documentation_score + collaboration_score
                    ) / 5.0
                ) STORED,
                graded_by UUID NOT NULL REFERENCES users(user_id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (course_id, project_id, sprint_id),
                FOREIGN KEY (project_id, course_id)
                    REFERENCES projects(project_id, course_id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_assessment_override_project_sprint "
            "ON assessment_override(project_id, sprint_id)"
        )


class PostgresManualOverrideRepository(ManualOverrideRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def upsert(self, **values: object) -> ManualOverrideRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO assessment_override (
                    course_id, project_id, sprint_id, requirements_score, code_quality_score,
                    testing_score, documentation_score, collaboration_score, graded_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (course_id, project_id, sprint_id) DO UPDATE SET
                    requirements_score = EXCLUDED.requirements_score,
                    code_quality_score = EXCLUDED.code_quality_score,
                    testing_score = EXCLUDED.testing_score,
                    documentation_score = EXCLUDED.documentation_score,
                    collaboration_score = EXCLUDED.collaboration_score,
                    graded_by = EXCLUDED.graded_by,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING override_id, course_id, project_id, sprint_id,
                    requirements_score, code_quality_score, testing_score,
                    documentation_score, collaboration_score, total_score,
                    graded_by, created_at, updated_at
                """,
                (
                    UUID(str(values["course_id"])),
                    UUID(str(values["project_id"])),
                    str(values["sprint_id"]),
                    values["requirements_score"],
                    values["code_quality_score"],
                    values["testing_score"],
                    values["documentation_score"],
                    values["collaboration_score"],
                    UUID(str(values["graded_by"])),
                ),
            ).fetchone()
        return self._record(row)

    def list(
        self, *, course_id: str, project_id: str, sprint_id: str | None = None
    ) -> list[ManualOverrideRecord]:
        query = """
            SELECT o.override_id, o.course_id, o.project_id, o.sprint_id,
                p.team_name, o.requirements_score, o.code_quality_score,
                o.testing_score, o.documentation_score, o.collaboration_score,
                o.total_score, o.graded_by, o.created_at, o.updated_at
            FROM assessment_override o
            JOIN projects p ON p.project_id = o.project_id AND p.course_id = o.course_id
            WHERE o.course_id = %s AND o.project_id = %s
        """
        parameters: list[object] = [UUID(course_id), UUID(project_id)]
        if sprint_id is not None:
            query += " AND o.sprint_id = %s"
            parameters.append(sprint_id)
        query += " ORDER BY o.updated_at DESC, o.sprint_id DESC"
        with self._pool.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._record(row) for row in rows]

    @staticmethod
    def _record(row: dict) -> ManualOverrideRecord:
        return ManualOverrideRecord(
            override_id=str(row["override_id"]),
            course_id=str(row["course_id"]),
            project_id=str(row["project_id"]),
            sprint_id=row["sprint_id"],
            team_name=row.get("team_name", ""),
            requirements_score=float(row["requirements_score"]),
            code_quality_score=float(row["code_quality_score"]),
            testing_score=float(row["testing_score"]),
            documentation_score=float(row["documentation_score"]),
            collaboration_score=float(row["collaboration_score"]),
            total_score=float(row["total_score"]),
            graded_by=str(row["graded_by"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
