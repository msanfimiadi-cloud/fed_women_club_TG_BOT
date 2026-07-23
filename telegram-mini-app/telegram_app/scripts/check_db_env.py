"""Print a safe TELEGRAM_APP_DATABASE_URL visibility check without secrets."""
from __future__ import annotations

from backend.telegram_catalog.config import get_settings
from backend.telegram_catalog.database import safe_database_url_summary


if __name__ == "__main__":
    settings = get_settings()
    print(
        "TELEGRAM_APP_DATABASE_URL is visible: "
        f"{safe_database_url_summary(settings.telegram_app_database_url)}"
    )
