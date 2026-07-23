"""Initialize the Telegram app database schema."""
from backend.telegram_catalog.database import init_db


if __name__ == "__main__":
    init_db()
    print("Telegram app database initialized")
