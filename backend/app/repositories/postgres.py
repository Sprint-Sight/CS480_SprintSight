from datetime import datetime
from uuid import UUID

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
                SELECT user_id, email, full_name, password_hash, role, is_active
                FROM users
                WHERE lower(email) = lower(%s) AND is_active = TRUE
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
                SELECT user_id, email, full_name, password_hash, role, is_active
                FROM users
                WHERE user_id = %s AND is_active = TRUE
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
        )


def create_user_pool(connection_string: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=connection_string,
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=5,
        open=False,
    )