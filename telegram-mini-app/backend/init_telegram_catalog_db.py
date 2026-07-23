"""Initialize the local Telegram catalog database."""
from backend.telegram_catalog.database import init_db

if __name__ == "__main__":
    init_db()
    print("Telegram catalog database initialized")
