from __future__ import annotations

import sqlite3
from pathlib import Path


class NotificationStore:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_started_users (
                    telegram_user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    display_name TEXT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_notification_partners (
                    telegram_user_id INTEGER PRIMARY KEY,
                    granted_by INTEGER NOT NULL,
                    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path, timeout=5)

    def register_user(
        self,
        telegram_user_id: int,
        *,
        username: str | None = None,
        display_name: str | None = None,
    ) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO bot_started_users
                    (telegram_user_id, username, display_name)
                VALUES (?, ?, ?)
                """,
                (telegram_user_id, username, display_name),
            )
            return result.rowcount == 1

    def grant_partner_access(self, telegram_user_id: int, *, granted_by: int) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO bot_notification_partners
                    (telegram_user_id, granted_by)
                VALUES (?, ?)
                """,
                (telegram_user_id, granted_by),
            )
            return result.rowcount == 1

    def is_partner(self, telegram_user_id: int) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "SELECT 1 FROM bot_notification_partners WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            return result is not None

    def partner_ids(self) -> frozenset[int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT telegram_user_id FROM bot_notification_partners"
            ).fetchall()
            return frozenset(int(row[0]) for row in rows)
