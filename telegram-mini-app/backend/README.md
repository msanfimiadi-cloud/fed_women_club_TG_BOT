# Telegram local catalog backend scaffold

This folder contains a small WSGI backend scaffold for the Telegram-only partner catalog. It is intentionally separate from the existing Vite frontend runtime and uses `TELEGRAM_APP_DATABASE_URL` instead of any WEB `DATABASE_URL`.

Development commands from `telegram-mini-app/`:

```bash
python -m backend.init_telegram_catalog_db
python -m backend.seed_telegram_catalog
python -m backend.telegram_catalog.app
```

Operational command aliases from `telegram-mini-app/`:

```bash
npm run check:tg-db-env
npm run init:tg-db
npm run seed:tg-db
```

Direct module equivalents:

```bash
python -m telegram_app.scripts.check_db_env
python -m telegram_app.scripts.init_db
python -m telegram_app.scripts.seed_dev_data
```

The scaffold supports local SQLite URLs such as `sqlite:///./telegram_app.db` and PostgreSQL URLs such as `postgresql://user:<password>@host:5432/database`. PostgreSQL support requires:

```bash
pip install -r requirements.txt
```

Configure `TELEGRAM_ADMIN_API_TOKEN` before using admin write endpoints. Do not run `seed:tg-db` automatically on production startup.
