# Timeweb App Platform: PostgreSQL для Telegram Mini App

Документ описывает безопасную инициализацию отдельной PostgreSQL БД Telegram Mini App в Timeweb App Platform. Инициализация схемы создаёт только отсутствующие таблицы и индексы, не удаляет данные, не перезаписывает данные и не запускает seed.


## Docker one-app deploy on Timeweb

For the current recommended one-app production deployment, use Timeweb `Docker` → `Dockerfile` mode with the repository-root Dockerfile.

See the step-by-step Docker instructions in [`timeweb-docker-deploy.md`](./timeweb-docker-deploy.md). The Dockerfile path in Timeweb is:

```text
Dockerfile
```

Use port `3000` if Timeweb asks for a port. The Docker image builds the Vite frontend and runs the Node production server; it does not run Python, `pip`, or `vite preview`.

## 1. Фактический flow проекта

Репозиторий `telegram-mini-app/` остаётся Vite/React приложением с отдельным Python WSGI backend scaffold в `backend/`:

- frontend dependencies: `npm install`;
- frontend checks/build: `npm run typecheck`, `npm run build`;
- Python backend scaffold: `backend/telegram_catalog/app.py`;
- DB scripts: `npm run init:tg-db`, `npm run seed:tg-db`, `npm run check:tg-db-env`.

Для PostgreSQL backend-зависимость устанавливается отдельно:

```bash
pip install -r requirements.txt
```

`requirements.txt` содержит `psycopg2-binary`. Пароль берётся только из `TELEGRAM_APP_DATABASE_URL`; helper-скрипты и startup auto init печатают только безопасную сводку `scheme/host/port/database`, без password и без `TELEGRAM_ADMIN_API_TOKEN`.

## 2. Env в Timeweb

В панели Timeweb App Platform добавьте переменные окружения приложения:

```dotenv
TELEGRAM_APP_DATABASE_URL=postgresql://gen_user:<password>@192.168.0.4:5432/default_db
TELEGRAM_ADMIN_API_TOKEN=<secret>
TELEGRAM_AUTO_INIT_DB=true
VITE_TG_LOCAL_CATALOG_ENABLED=false
VITE_TG_API_BASE_URL=
```

`TELEGRAM_AUTO_INIT_DB=true` нужен только если в Timeweb App Platform нет видимого shell/console для ручного запуска `npm run init:tg-db` или `python -m telegram_app.scripts.init_db`.

Безопасный режим по умолчанию: если `TELEGRAM_AUTO_INIT_DB` отсутствует или равен `false`, backend не выполняет автоматическую инициализацию БД при старте.

## 3. Автоматический init при недоступном shell

Если shell в Timeweb App Platform недоступен:

1. Установите `TELEGRAM_AUTO_INIT_DB=true` в env приложения.
2. Выполните redeploy/restart приложения.
3. При старте backend выполнит idempotent `init_db`: `CREATE TABLE IF NOT EXISTS` и `CREATE INDEX IF NOT EXISTS`.
4. После успешного запуска можно отключить auto init:

```dotenv
TELEGRAM_AUTO_INIT_DB=false
```

Повторный restart/redeploy с `TELEGRAM_AUTO_INIT_DB=true` безопасен: schema init не удаляет существующие данные и не перезаписывает записи.

Выбранное поведение при ошибке auto init: backend падает на старте с controlled error, где указаны только safe `scheme/host/port/database`. Это безопаснее, чем запускать приложение с неинициализированной схемой и получать runtime-ошибки на пользовательских запросах. Пароль из `TELEGRAM_APP_DATABASE_URL` и `TELEGRAM_ADMIN_API_TOKEN` не логируются.

## 4. Ручной init, если shell/one-off command доступен

Если Timeweb позволяет запускать команду вручную, можно оставить `TELEGRAM_AUTO_INIT_DB=false` и выполнить из директории `telegram-mini-app`:

```bash
npm run init:tg-db
```

Эквивалент без npm:

```bash
python -m telegram_app.scripts.init_db
```

Проверить, что приложение видит `TELEGRAM_APP_DATABASE_URL`, можно безопасной командой:

```bash
npm run check:tg-db-env
```

Она выводит только сводку вида `scheme=postgresql host=192.168.0.4 port=5432 database=default_db`.

## 5. Seed data

Seed автоматически не запускается ни при startup, ни при `TELEGRAM_AUTO_INIT_DB=true`. Команда seed существует только для dev/test-данных и должна запускаться осознанно:

```bash
npm run seed:tg-db
```

или:

```bash
python -m telegram_app.scripts.seed_dev_data
```

Не запускайте seed в production, если в БД должны быть реальные партнёры.

## 6. Как проверить после redeploy

После redeploy проверьте health endpoints и публичный список партнёров:

```bash
curl -i https://<TG_APP_DOMAIN>/api/tg/health
curl -i https://<TG_APP_DOMAIN>/api/tg/health/db
curl -i https://<TG_APP_DOMAIN>/api/tg/partners
```

Ожидаемые ответы:

- `/api/tg/health` → `200 OK` и `{"status":"ok","service":"telegram-local-catalog"}`;
- `/api/tg/health/db` → `200 OK` и `{"status":"ok","database":"ok"}`, если PostgreSQL доступен;
- `/api/tg/health/db` → controlled `503` без password/secret, если БД недоступна;
- `/api/tg/partners` → `200 OK` и `{"items":[...]}` или `{"items":[]}`, если schema создана, но партнёры ещё не добавлены;
- `404` на `/api/tg/...` обычно означает, что текущий Timeweb route/start command отдаёт только Vite static frontend, а Python WSGI API ещё не подключён к web process/reverse proxy.

Admin write endpoints требуют `TELEGRAM_ADMIN_API_TOKEN`, например:

```bash
curl -i \
  -H "Authorization: Bearer <TELEGRAM_ADMIN_API_TOKEN>" \
  https://<TG_APP_DOMAIN>/api/tg/admin/partners
```

Не вставляйте реальный token в публичные логи, issue или скриншоты.


## 7. Проверка запуска npm start в текущем React Node.js 24 Timeweb app

Цель проверки — понять, запускает ли текущий Timeweb шаблон `React` на `Node.js 24` стандартный `npm start` после сборки. В этом PR `npm start` привязан к Node production server:

```bash
npm start
```

Ожидаемая команда внутри `package.json`:

```json
"start": "node server/production-server.js"
```

Настройки текущего приложения в Timeweb:

```text
Framework: React
Node.js: 24
Build command: npm install && npm run build
Dependencies: empty
Output dir: dist
Path: /telegram-mini-app
```

Env для проверки one-app deployment:

```dotenv
VITE_API_BASE_URL=https://bloomclub.ru/api/v1
VITE_TG_LOCAL_CATALOG_ENABLED=true
VITE_TG_API_BASE_URL=
TELEGRAM_APP_DATABASE_URL=postgresql://gen_user:<password>@192.168.0.4:5432/default_db
TELEGRAM_ADMIN_API_TOKEN=<secret>
TELEGRAM_AUTO_INIT_DB=true
```

После deploy/redeploy проверьте health endpoint текущего TG app домена:

```bash
curl -i https://<TG_APP_DOMAIN>/api/tg/health
```

Если ответ JSON вида:

```json
{"status":"ok","service":"telegram-local-catalog"}
```

значит Timeweb запускает `npm start`, и one-app deployment для React frontend + Node production server работает в текущем приложении.

Если вместо JSON приходит HTML/SPA (`index.html`), значит текущий Timeweb `React` template отдаёт только static `dist` и не запускает `npm start`. В этом режиме backend внутри текущего static-шаблона невозможен: нужен runtime-шаблон, отдельное временное приложение для миграции или Docker. Это не требует менять основной сайт `bloomclub.ru`, VK Mini App, WEB repo или account linking backend.

## 8. TG Admin MVP в Timeweb

Для наполнения локального Telegram-каталога после redeploy откройте отдельную страницу:

```text
https://<TG_APP_DOMAIN>/tg-admin
```

Эта страница не встроена в пользовательский Telegram Mini App flow и не добавлена в нижнее меню. Она не требует Telegram login. Admin token вводится вручную и хранится только в `sessionStorage` браузера. Не добавляйте `TELEGRAM_ADMIN_API_TOKEN` во frontend env (`VITE_*`), не хардкодьте его и не публикуйте в логах/скриншотах.

Backend env в Timeweb должен включать:

```dotenv
TELEGRAM_APP_DATABASE_URL=postgresql://gen_user:<password>@192.168.0.4:5432/default_db
TELEGRAM_ADMIN_API_TOKEN=<secret>
TELEGRAM_AUTO_INIT_DB=true
VITE_TG_LOCAL_CATALOG_ENABLED=false
VITE_TG_API_BASE_URL=
```

Admin endpoints принимают token через `X-Telegram-Admin-Token` или `Authorization: Bearer ...` и не используют основной сайт `bloomclub.ru` для partners/offers/photos.

### Curl smoke test admin

```bash
export TG_APP_ORIGIN="https://<TG_APP_DOMAIN>"
export TG_ADMIN_TOKEN="<TELEGRAM_ADMIN_API_TOKEN>"

curl -sS -X POST "$TG_APP_ORIGIN/api/tg/admin/partners" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Admin-Token: $TG_ADMIN_TOKEN" \
  -d '{"title":"Счастье есть","display_name":"Счастье есть","city":"Новосибирск","category":"Кафе","is_active":true,"sort_order":100}'

curl -sS -X POST "$TG_APP_ORIGIN/api/tg/admin/partners/<partner_id>/photos" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TG_ADMIN_TOKEN" \
  -d '{"image_url":"https://example.com/photo.jpg","sort_order":100,"is_cover":true}'

curl -sS -X POST "$TG_APP_ORIGIN/api/tg/admin/partners/<partner_id>/offers" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Admin-Token: $TG_ADMIN_TOKEN" \
  -d '{"title":"Классика","description":"Описание услуги","conditions":"Условия получения привилегии","base_price":2550,"member_price":2250,"discount_percent":null,"is_active":true,"sort_order":100}'

curl -sS -X DELETE "$TG_APP_ORIGIN/api/tg/admin/partners/<partner_id>" \
  -H "X-Telegram-Admin-Token: $TG_ADMIN_TOKEN"

curl -sS -X DELETE "$TG_APP_ORIGIN/api/tg/admin/offers/<offer_id>" \
  -H "X-Telegram-Admin-Token: $TG_ADMIN_TOKEN"
```

### Curl smoke test public catalog

```bash
curl -i "$TG_APP_ORIGIN/api/tg/partners"
curl -i "$TG_APP_ORIGIN/api/tg/partners/<partner_id>"
curl -i "$TG_APP_ORIGIN/api/tg/partners/<partner_id>/offers"
```

Ожидание: public list endpoints возвращают `{ "items": [...] }`, inactive partners/offers не попадают в public responses, а данные берутся только из отдельной локальной TG DB. Пользовательский frontend flow «Партнёры» переключается на local catalog только при `VITE_TG_LOCAL_CATALOG_ENABLED=true`; `false` остаётся безопасным rollback значением.

## 9. Production switch пользовательского TG local catalog

Для включения пользовательской вкладки «Партнёры» на локальной TG DB задайте frontend env перед build/deploy:

```dotenv
VITE_TG_LOCAL_CATALOG_ENABLED=true
VITE_TG_API_BASE_URL=
```

Пустой `VITE_TG_API_BASE_URL` означает, что Mini App берёт TG catalog с текущего origin Timeweb и строит запросы как `/api/tg/...`. Это рекомендуемый production режим, если frontend и Python WSGI API обслуживаются на одном домене.

Откат без изменения backend/database:

```dotenv
VITE_TG_LOCAL_CATALOG_ENABLED=false
VITE_TG_API_BASE_URL=
```

После включения проверьте:

```bash
curl -i "$TG_APP_ORIGIN/api/tg/partners"
curl -i "$TG_APP_ORIGIN/api/tg/partners/<partner_id>"
curl -i "$TG_APP_ORIGIN/api/tg/partners/<partner_id>/offers"
```

Затем откройте Mini App → «Партнёры» и убедитесь, что в логах WEB backend больше нет catalog-запросов:

```text
/clients/catalog/partners
/clients/partners/{id}/offers
```

WEB backend при этом продолжает обслуживать только identity/account flow Telegram Mini App: `telegram-miniapp-login`, `clients/me`, subscription/trial и account linking. Если `/api/tg/partners` отвечает `{"items":[]}`, наполните локальную TG DB через `/tg-admin`; основной сайт, VK Mini App и account linking backend для этого не нужны и не меняются.

## 10. Production switch checklist

### 10.1 Env

Перед финальным включением TG local catalog в Timeweb production env должны быть заданы:

```dotenv
TELEGRAM_APP_DATABASE_URL=postgresql://gen_user:<password>@192.168.0.4:5432/default_db
TELEGRAM_ADMIN_API_TOKEN=<secret>
TELEGRAM_AUTO_INIT_DB=true
VITE_TG_LOCAL_CATALOG_ENABLED=true
VITE_TG_API_BASE_URL=
```

Не добавляйте реальные значения этих секретов в git, frontend env `VITE_*`, issue, скриншоты или публичные логи.

### 10.2 Routing / serving в Timeweb

После `npm run build` Vite создаёт только статический frontend bundle. Routes `/tg-admin` и пользовательские страницы может отдавать static hosting с SPA fallback на `index.html`, но `/api/tg/*` не заработают от одного Vite static output без Python WSGI process или reverse proxy к нему.

Для production Timeweb должен запускать web process, который одновременно:

1. отдаёт `dist/` для Vite frontend и SPA route `/tg-admin`;
2. прокидывает `/api/tg/*` в WSGI app `backend.telegram_catalog.app:application`.

Если текущий Timeweb start command обслуживает только static frontend, ожидаемые симптомы:

- `/tg-admin` открывается;
- `/api/tg/health`, `/api/tg/health/db`, `/api/tg/status`, `/api/tg/partners` возвращают `404`/HTML frontend или вообще не отвечают как JSON.

В этом случае нужно поменять Timeweb start command на единый production entrypoint из `telegram-mini-app/`:

```bash
npm run start:production
```

Эквивалентная Python-команда:

```bash
python -m backend.telegram_catalog.production_app
```

Этот app server отдаёт Vite `dist/`, прокидывает `/api/tg/*` в `backend.telegram_catalog.app:application`, слушает `0.0.0.0` и берёт порт из env `PORT` с fallback `8000`. Не считайте TG local catalog включённым, пока JSON endpoints ниже не отвечают с production-домена.

### 10.3 Redeploy

После изменения env выполните redeploy/restart приложения. Если `TELEGRAM_AUTO_INIT_DB=true`, backend при старте выполнит idempotent schema init без seed и без удаления данных.

### 10.4 Проверить endpoints

```bash
curl -i https://<TG_APP_DOMAIN>/api/tg/health
curl -i https://<TG_APP_DOMAIN>/api/tg/health/db
curl -i https://<TG_APP_DOMAIN>/api/tg/status
curl -i https://<TG_APP_DOMAIN>/api/tg/partners
```

Ожидается:

- `/api/tg/health` → `200` и service `telegram-local-catalog`;
- `/api/tg/health/db` → `200`/`database=ok` или controlled `503` без секретов;
- `/api/tg/status` → counts `partners_count`, `active_partners_count`, `offers_count`, `active_offers_count`, `auto_init_enabled`, `local_catalog_enabled_hint=frontend_env_only`;
- `/api/tg/partners` → JSON `{ "items": [...] }` или `{ "items": [] }`, если каталог ещё пустой.

### 10.5 Открыть admin UI

```text
https://<TG_APP_DOMAIN>/tg-admin
```

В блоке «Проверка системы» нажмите «Проверить API» и проверьте, что UI показывает API доступен, DB ok, active partners count и active offers count. Admin token вводится только вручную в поле страницы и не выводится в проверке системы.

### 10.6 Создать данные

Через `/tg-admin` или admin API создайте:

- партнёра;
- фото;
- offer.

### 10.7 Проверить пользовательский каталог

Проверьте, что `/api/tg/partners` больше не пустой, затем откройте Telegram Mini App вкладку «Партнёры» и убедитесь, что отображаются TG-партнёры из локальной TG DB.

### 10.8 Проверить WEB logs

В логах `fed_women_club_WEB` после открытия TG вкладки «Партнёры» не должно быть:

- `/clients/catalog/partners`;
- `/clients/partners/{id}/offers`.

При этом могут оставаться identity/account запросы:

- `/auth/telegram-miniapp-login`;
- `/clients/me`;
- `/clients/me/subscription`;
- `/clients/me/trial-subscription`;
- `/clients/me/linking-status`.

### 10.9 Отключить auto init после успешной проверки

После успешной production-проверки можно поставить:

```dotenv
TELEGRAM_AUTO_INIT_DB=false
```

и сделать redeploy. Это уменьшает startup-поверхность, не меняя уже созданные таблицы.

### 10.10 Rollback

Если TG local catalog не работает, выполните frontend rollback без изменения WEB/VK/site и без удаления TG DB:

```dotenv
VITE_TG_LOCAL_CATALOG_ENABLED=false
VITE_TG_API_BASE_URL=
```

После redeploy пользовательская вкладка «Партнёры» временно вернётся на WEB legacy catalog flow. Backend `/api/tg/*` и `/tg-admin` можно чинить отдельно.


## Если `/api/tg/health` отдаёт HTML вместо JSON

Это означает, что Timeweb сейчас запускает только Vite/static frontend с SPA fallback на `dist/index.html`. В таком режиме неизвестный URL `/api/tg/health` попадает в frontend, а не в Python backend `backend.telegram_catalog.app:application`, поэтому браузер видит HTML Bloom Club и frontend-ошибку вроде `init_data_read`.

Исправление — запускать единый production entrypoint из текущего репозитория `Kosmos327/-fed_women_club_mini-app_TELEGA`, не WEB/VK/site repos.

### Timeweb commands

Build command:

```bash
npm install && npm run build && pip install -r requirements.txt
```

Start command:

```bash
npm run start:production
```

Эквивалентная команда без npm wrapper:

```bash
python -m backend.telegram_catalog.production_app
```

### Production env

```dotenv
TELEGRAM_APP_DATABASE_URL=postgresql://gen_user:<password>@192.168.0.4:5432/default_db
TELEGRAM_ADMIN_API_TOKEN=<secret>
TELEGRAM_AUTO_INIT_DB=true
VITE_TG_LOCAL_CATALOG_ENABLED=true
VITE_TG_API_BASE_URL=
```

`TELEGRAM_AUTO_INIT_DB=true` запускает только idempotent init schema при старте backend; seed не запускается автоматически. После успешной проверки можно поставить:

```dotenv
TELEGRAM_AUTO_INIT_DB=false
```

### Проверка API и frontend routes

```bash
curl -i https://<TG_APP_DOMAIN>/api/tg/health
```

Ожидание:

```text
Content-Type: application/json
{"status":"ok","service":"telegram-local-catalog"}
```

```bash
curl -i https://<TG_APP_DOMAIN>/tg-admin
```

Ожидание:

```text
Content-Type: text/html
```

### Rollback

Если routing сломался:

1. верните старую Timeweb start command/static deployment;
2. поставьте frontend flag rollback:

```dotenv
VITE_TG_LOCAL_CATALOG_ENABLED=false
VITE_TG_API_BASE_URL=
```

3. redeploy.

Rollback не требует изменений WEB/VK/site repos, основного backend `bloomclub.ru`, account linking backend или удаления TG DB.
