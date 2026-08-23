from datetime import datetime
from uuid import UUID
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.repositories.interfaces import UserRecord, UserRepository
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


def create_user_pool(connection_string: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=connection_string,
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=5,
        open=False,
    )