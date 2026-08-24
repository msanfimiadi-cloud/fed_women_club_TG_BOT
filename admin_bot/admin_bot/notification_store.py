from __future__ import annotations

import sqlite3
import secrets
import time
from pathlib import Path
from typing import Any


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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_advertisers (
                    telegram_user_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    referral_code TEXT NOT NULL UNIQUE,
                    created_by INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_advertiser_referrals (
                    telegram_user_id INTEGER PRIMARY KEY,
                    advertiser_telegram_user_id INTEGER NOT NULL,
                    username TEXT,
                    display_name TEXT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (advertiser_telegram_user_id)
                        REFERENCES bot_advertisers (telegram_user_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS bot_advertiser_referrals_advertiser_idx
                ON bot_advertiser_referrals (advertiser_telegram_user_id, started_at)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_login_code_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    requested_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS bot_login_code_requests_user_time_idx
                ON bot_login_code_requests (telegram_user_id, requested_at)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

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

    def add_advertiser(
        self,
        telegram_user_id: int,
        *,
        name: str,
        created_by: int,
    ) -> dict[str, Any]:
        clean_name = name.strip()
        if telegram_user_id <= 0 or not clean_name:
            raise ValueError("Advertiser Telegram ID and name are required")
        referral_code = f"ad_{secrets.token_urlsafe(12)}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM bot_advertisers WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            connection.execute(
                """
                INSERT INTO bot_advertisers
                    (telegram_user_id, name, referral_code, created_by)
                VALUES (?, ?, ?, ?)
                """,
                (telegram_user_id, clean_name, referral_code, created_by),
            )
            advertiser = connection.execute(
                "SELECT * FROM bot_advertisers WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            assert advertiser is not None
            return dict(advertiser)

    def advertiser_by_code(self, referral_code: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            advertiser = connection.execute(
                """
                SELECT * FROM bot_advertisers
                WHERE referral_code = ? AND active = 1
                """,
                (referral_code,),
            ).fetchone()
            return dict(advertiser) if advertiser is not None else None

    def advertiser_by_id(self, telegram_user_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            advertiser = connection.execute(
                """
                SELECT * FROM bot_advertisers
                WHERE telegram_user_id = ? AND active = 1
                """,
                (telegram_user_id,),
            ).fetchone()
            return dict(advertiser) if advertiser is not None else None

    def is_advertiser(self, telegram_user_id: int) -> bool:
        return self.advertiser_by_id(telegram_user_id) is not None

    def register_referred_user(
        self,
        telegram_user_id: int,
        *,
        username: str | None = None,
        display_name: str | None = None,
        referral_code: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            result = connection.execute(
                """
                INSERT OR IGNORE INTO bot_started_users
                    (telegram_user_id, username, display_name)
                VALUES (?, ?, ?)
                """,
                (telegram_user_id, username, display_name),
            )
            if result.rowcount != 1 or not referral_code:
                return result.rowcount == 1, None
            advertiser = connection.execute(
                """
                SELECT * FROM bot_advertisers
                WHERE referral_code = ? AND active = 1
                """,
                (referral_code,),
            ).fetchone()
            if advertiser is None or int(advertiser["telegram_user_id"]) == telegram_user_id:
                return True, None
            connection.execute(
                """
                INSERT INTO bot_advertiser_referrals
                    (telegram_user_id, advertiser_telegram_user_id, username, display_name)
                VALUES (?, ?, ?, ?)
                """,
                (telegram_user_id, advertiser["telegram_user_id"], username, display_name),
            )
            return True, dict(advertiser)

    def advertiser_statistics(self, telegram_user_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            advertiser = connection.execute(
                "SELECT * FROM bot_advertisers WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            if advertiser is None:
                return None
            counts = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN date(started_at) = date('now') THEN 1 ELSE 0 END), 0)
                        AS today,
                    COALESCE(SUM(CASE WHEN started_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END), 0)
                        AS last_7_days,
                    COALESCE(SUM(CASE WHEN started_at >= datetime('now', '-30 days') THEN 1 ELSE 0 END), 0)
                        AS last_30_days
                FROM bot_advertiser_referrals
                WHERE advertiser_telegram_user_id = ?
                """,
                (telegram_user_id,),
            ).fetchone()
            recent = connection.execute(
                """
                SELECT telegram_user_id, username, display_name, started_at
                FROM bot_advertiser_referrals
                WHERE advertiser_telegram_user_id = ?
                ORDER BY started_at DESC, telegram_user_id DESC
                LIMIT 10
                """,
                (telegram_user_id,),
            ).fetchall()
            return {
                **dict(advertiser),
                **dict(counts or {}),
                "recent_users": [dict(row) for row in recent],
            }

    def all_advertiser_statistics(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            advertisers = connection.execute(
                """
                SELECT telegram_user_id FROM bot_advertisers
                ORDER BY active DESC, name COLLATE NOCASE, telegram_user_id
                """
            ).fetchall()
        return [
            statistics
            for advertiser in advertisers
            if (statistics := self.advertiser_statistics(int(advertiser[0]))) is not None
        ]

    def reserve_login_code_request(
        self,
        telegram_user_id: int,
        *,
        now: int | None = None,
        max_attempts: int = 5,
        window_seconds: int = 15 * 60,
    ) -> tuple[bool, int]:
        current_time = int(time.time()) if now is None else int(now)
        cutoff = current_time - window_seconds
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM bot_login_code_requests WHERE requested_at <= ?",
                (cutoff,),
            )
            attempts = connection.execute(
                """
                SELECT requested_at FROM bot_login_code_requests
                WHERE telegram_user_id = ? AND requested_at > ?
                ORDER BY requested_at
                """,
                (telegram_user_id, cutoff),
            ).fetchall()
            if len(attempts) >= max_attempts:
                retry_after = max(1, int(attempts[0]["requested_at"]) + window_seconds - current_time)
                return False, retry_after
            connection.execute(
                """
                INSERT INTO bot_login_code_requests (telegram_user_id, requested_at)
                VALUES (?, ?)
                """,
                (telegram_user_id, current_time),
            )
            return True, 0
