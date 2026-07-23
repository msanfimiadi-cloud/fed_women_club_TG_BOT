"""Configuration for the local Telegram catalog backend."""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_DATABASE_URL = "sqlite:///./telegram_app.db"


@dataclass(frozen=True)
class Settings:
    telegram_app_database_url: str = DEFAULT_DATABASE_URL
    telegram_admin_api_token: str | None = None
    telegram_auto_init_db: bool = False
    telegram_bot_username: str | None = None
    telegram_mini_app_short_name: str | None = None


def env_flag_is_true(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() == "true"


def get_settings() -> Settings:
    token = os.getenv("TELEGRAM_ADMIN_API_TOKEN") or None
    return Settings(
        telegram_app_database_url=os.getenv(
            "TELEGRAM_APP_DATABASE_URL", DEFAULT_DATABASE_URL
        ),
        telegram_admin_api_token=token,
        telegram_auto_init_db=env_flag_is_true("TELEGRAM_AUTO_INIT_DB"),
        telegram_bot_username=(os.getenv("TELEGRAM_BOT_USERNAME") or os.getenv("BOT_USERNAME") or None),
        telegram_mini_app_short_name=(os.getenv("TELEGRAM_MINI_APP_SHORT_NAME") or None),
    )
