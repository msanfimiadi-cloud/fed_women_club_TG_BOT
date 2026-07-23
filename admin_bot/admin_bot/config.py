from __future__ import annotations

import os
from dataclasses import dataclass
from typing import FrozenSet

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional in production envs
    load_dotenv = None


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_admin_ids: FrozenSet[int]
    web_content_api_base_url: str
    web_api_base_url: str
    telegram_admin_api_token: str
    bot_service_token: str
    browser_app_public_url: str
    telegram_catalog_api_base_url: str | None = None
    max_upload_size_mb: int = 10


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _parse_admin_ids(raw: str) -> FrozenSet[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError as exc:
            raise RuntimeError("TELEGRAM_ADMIN_IDS must contain Telegram user IDs separated by commas") from exc
    if not ids:
        raise RuntimeError("TELEGRAM_ADMIN_IDS must contain at least one Telegram user ID")
    return frozenset(ids)


def load_settings() -> Settings:
    if load_dotenv is not None:
        load_dotenv()

    return Settings(
        telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
        telegram_admin_ids=_parse_admin_ids(_required("TELEGRAM_ADMIN_IDS")),
        web_content_api_base_url=_required("WEB_CONTENT_API_BASE_URL").rstrip("/"),
        web_api_base_url=_required("WEB_API_BASE_URL").rstrip("/"),
        telegram_admin_api_token=_required("TELEGRAM_ADMIN_API_TOKEN"),
        bot_service_token=_required("BOT_SERVICE_TOKEN"),
        browser_app_public_url=(os.getenv("BROWSER_APP_PUBLIC_URL", "https://app.bloomclub.ru").strip().rstrip("/") or "https://app.bloomclub.ru"),
        telegram_catalog_api_base_url=(os.getenv("TELEGRAM_CATALOG_API_BASE_URL", "").strip().rstrip("/") or None),
    )
