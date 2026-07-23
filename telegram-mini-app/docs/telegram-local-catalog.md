# Telegram Local Catalog foundation

## 1. Что реализовано

Этот foundation PR добавляет в репозиторий `telegram-mini-app` отдельный безопасный scaffold локального Telegram catalog backend/API. Текущий пользовательский frontend flow партнёров не переключён на новый API: существующие WEB partner-запросы остаются в текущем frontend-коде до отдельного feature-flag этапа.

Репозиторий фактически был frontend-only: Vite/React приложение с `package.json`, без backend entrypoint, без миграций, без существующей локальной БД и без `uploads/media`. Поэтому backend добавлен как изолированный Python WSGI scaffold в `backend/`, чтобы не ломать текущий Vite/Timeweb запуск. Для PostgreSQL нужен `psycopg2-binary` из `requirements.txt`.

## 2. Database config

Локальная TG БД настраивается только через backend env-переменную:

```env
TELEGRAM_APP_DATABASE_URL=sqlite:///./telegram_app.db
# or in Timeweb runtime env:
# TELEGRAM_APP_DATABASE_URL=postgresql://gen_user:<password>@192.168.0.4:5432/default_db
```

Scaffold поддерживает локальный SQLite URL и PostgreSQL URL (`postgresql://`/`postgres://`). Он не использует `DATABASE_URL` основного сайта и не подключается к базе `fed_women_club_WEB`. Файл `telegram_app.db`, SQLite sidecar-файлы, production DB passwords и secrets не должны коммититься.

## 3. Таблицы/модели

DDL создаётся командой инициализации; dev server entrypoint также вызывает idempotent init перед запуском локального WSGI сервера. Добавлены таблицы:

- `telegram_partners` — `id`, `title`, `display_name`, `description`, `city`, `category`, `address`, `phone`, `is_active`, `sort_order`, `created_at`, `updated_at`.
- `telegram_partner_photos` — `id`, `partner_id`, `image_url`, `file_path`, `sort_order`, `is_cover`, `created_at`.
- `telegram_partner_offers` — `id`, `partner_id`, `title`, `description`, `conditions`, `base_price`, `member_price`, `discount_percent`, `is_active`, `sort_order`, `created_at`, `updated_at`.
- `telegram_privilege_codes` — `id`, `telegram_user_id`, `linked_client_id`, `web_client_id`, `linked_account_id`, `partner_id`, `offer_id`, `code`, `status`, `expires_at`, `used_at`, `created_at`, `source_platform`, `web_subscription_checked_at`, `access_snapshot`, `metadata`.

Связи задаются внешними ключами: partner → photos, partner → offers, offer → partner, code → partner/offer. Индексы добавлены для `partner_id`, `is_active`, `sort_order`, `status`, `expires_at`, `telegram_user_id` и `linked_client_id`.

## 4. Public TG Local API

Public endpoints читают только локальную TG DB и не обращаются к `bloomclub.ru` за партнёрами, фото или офферами.

- `GET /api/tg/partners` — возвращает `{ "items": [...] }` только для active партнёров, включая `cover` и `offers_count`.
- `GET /api/tg/partners/{partner_id}` — возвращает одного active партнёра, `photos`, `cover`, `offers_count`.
- `GET /api/tg/partners/{partner_id}/offers` — возвращает `{ "items": [...] }` только active offers партнёра.
- `POST /api/tg/partners/{partner_id}/offers/{offer_id}/verify` — пока возвращает `501 {"detail":"access_check_not_configured"}` и не создаёт код без безопасной проверки доступа.
- `GET /api/tg/me/verifications` — пока возвращает `501 {"detail":"user_context_not_configured"}` без небезопасного общего пользователя.
- `GET /api/tg/me/savings` — пока возвращает `501 {"detail":"user_context_not_configured"}` без небезопасного общего пользователя.

## 5. Admin API / scaffold

Admin endpoints находятся под `/api/tg/admin` и требуют backend-only env-переменную:

```env
TELEGRAM_ADMIN_API_TOKEN=<set on backend only>
```

Токен передаётся в `X-Telegram-Admin-Token` или `Authorization: Bearer ...`. Если токен не настроен, admin endpoints возвращают controlled `501 {"detail":"admin_api_token_not_configured"}`; при неверном токене — `403 {"detail":"admin_api_token_invalid"}`.

Добавлены endpoints:

- `GET /api/tg/admin/partners`
- `POST /api/tg/admin/partners`
- `PATCH /api/tg/admin/partners/{id}`
- `POST /api/tg/admin/partners/{id}/photos`
- `PATCH /api/tg/admin/photos/{id}`
- `GET /api/tg/admin/partners/{id}/offers`
- `POST /api/tg/admin/partners/{id}/offers`
- `PATCH /api/tg/admin/offers/{id}`

## 6. Инициализация БД

Из папки `telegram-mini-app`:

```bash
export TELEGRAM_APP_DATABASE_URL=sqlite:///./telegram_app.db
python -m backend.init_telegram_catalog_db
# or via package alias:
npm run init:tg-db
```

## 7. Seed / dev data

Seed добавляет двух тестовых партнёров, placeholder image URLs и три тестовых оффера без production DB и без реальных персональных данных:

```bash
export TELEGRAM_APP_DATABASE_URL=sqlite:///./telegram_app.db
python -m backend.seed_telegram_catalog
# or via package alias:
npm run seed:tg-db
```

Seed is not run automatically on production startup.

## 8. Проверка через curl

Запустить dev API:

```bash
export TELEGRAM_APP_DATABASE_URL=sqlite:///./telegram_app.db
python -m backend.telegram_catalog.app
```

Проверить public endpoints:

```bash
curl http://127.0.0.1:8000/api/tg/partners
curl http://127.0.0.1:8000/api/tg/partners/1
curl http://127.0.0.1:8000/api/tg/partners/1/offers
curl -X POST http://127.0.0.1:8000/api/tg/partners/1/offers/1/verify
curl http://127.0.0.1:8000/api/tg/me/verifications
curl http://127.0.0.1:8000/api/tg/me/savings
```

Проверить admin scaffold:

```bash
export TELEGRAM_ADMIN_API_TOKEN=dev-local-token
curl -H "X-Telegram-Admin-Token: dev-local-token" http://127.0.0.1:8000/api/tg/admin/partners
curl -X POST -H "Content-Type: application/json" -H "X-Telegram-Admin-Token: dev-local-token" \
  -d '{"title":"demo","display_name":"Demo"}' \
  http://127.0.0.1:8000/api/tg/admin/partners
```

## 9. Timeweb App Platform

Текущий frontend деплой остаётся Vite-based (`npm install`, `npm run build`) и этим PR не меняется. Для реального TG Local API нужен отдельный backend process/service на Timeweb App Platform или явная настройка текущего сервиса на запуск Python WSGI приложения, например:

```bash
export TELEGRAM_APP_DATABASE_URL=sqlite:////persistent/telegram_app.db
python -m backend.telegram_catalog.app
```

Для production рекомендуется managed PostgreSQL. Подробная инструкция для Timeweb PostgreSQL, one-off init и проверки `/api/tg/partners` находится в `docs/timeweb-tg-db-setup.md`.

## 10. Что остаётся в WEB identity/account flow

WEB API остаётся источником только для:

- login (`POST /auth/telegram-miniapp-login`);
- profile (`GET/PATCH /clients/me`);
- subscription/trial (`GET /clients/me/subscription`, `POST /clients/me/trial-subscription`);
- account linking (`GET /clients/me/linking-status`, `POST /clients/me/linking/start`, `POST /clients/me/linking/confirm`).

## 11. Что должно перейти в TG local

В TG Local API/DB должны перейти:

- partners;
- photos/gallery;
- offers;
- prices;
- conditions;
- TG codes;
- TG savings.

## 12. Следующий этап

Следующий PR должен:

1. Добавить `tgCatalogClient` для frontend.
2. Переключить раздел «Партнёры» только через `VITE_TG_LOCAL_CATALOG_ENABLED=true`.
3. Проверить в Network/`rg`, что включённый TG catalog flow не вызывает `bloomclub.ru` endpoints `/clients/catalog/partners` и `/clients/partners/{id}/offers`.
4. Оставить WEB identity/account endpoints нетронутыми.

## 11. TG Admin MVP для наполнения каталога

В этом PR admin scaffold расширен до минимального рабочего CRUD для локального Telegram-каталога. Пользовательская вкладка «Партнёры» в Telegram Mini App не переключалась на local catalog и продолжает работать по текущему frontend flow до отдельного feature-flag этапа.

### Как открыть admin UI

Admin UI — отдельный route Vite-приложения:

```text
https://<TG_APP_DOMAIN>/tg-admin
```

Страница не добавляется в нижнее меню пользовательского приложения, не требует Telegram login и не должна показываться обычным пользователям ссылками из user flow. Admin token вводится вручную в поле `Admin token`, хранится только в `sessionStorage` браузера и не должен попадать во frontend env, исходный код, console output или публичные скриншоты.

### Защита admin API

Все endpoints под `/api/tg/admin` требуют backend-only переменную:

```env
TELEGRAM_ADMIN_API_TOKEN=<secret>
```

Поддерживаются оба варианта заголовка:

```bash
-H "X-Telegram-Admin-Token: <TELEGRAM_ADMIN_API_TOKEN>"
# or
-H "Authorization: Bearer <TELEGRAM_ADMIN_API_TOKEN>"
```

Если token не настроен на backend — controlled `501 {"detail":"admin_api_token_not_configured"}`. Если token не передан — controlled `401 {"detail":"admin_api_token_required"}`. Если token неверный — `403 {"detail":"admin_api_token_invalid"}`. Token не возвращается в ответах и не логируется.

### Реализованные admin endpoints

Partners:

- `GET /api/tg/admin/partners` — список всех партнёров, включая inactive, в shape `{ "items": [...] }`.
- `POST /api/tg/admin/partners` — создать партнёра.
- `PATCH /api/tg/admin/partners/{partner_id}` — частично обновить партнёра, обновляет `updated_at`.
- `DELETE /api/tg/admin/partners/{partner_id}` — soft delete: `is_active=false`, `updated_at=now`.

Photos:

- `GET /api/tg/admin/partners/{partner_id}/photos` — список фото партнёра.
- `POST /api/tg/admin/partners/{partner_id}/photos` — добавить metadata фото по `image_url`.
- `PATCH /api/tg/admin/photos/{photo_id}` — обновить `image_url`/`file_path`/`sort_order`/`is_cover`.
- `DELETE /api/tg/admin/photos/{photo_id}` — удалить только metadata-запись; файлы физически не удаляются в этом PR.

Если `is_cover=true`, backend снимает `is_cover` с остальных фото этого партнёра. Public `GET /api/tg/partners` выбирает `cover` сначала из фото с `is_cover=true`, иначе из первого фото по `sort_order`, `id`. Битый `image_url` не валидируется сетевым запросом и не ломает API.

Offers:

- `GET /api/tg/admin/partners/{partner_id}/offers` — все offers партнёра, включая inactive.
- `POST /api/tg/admin/partners/{partner_id}/offers` — создать offer.
- `PATCH /api/tg/admin/offers/{offer_id}` — частично обновить offer, обновляет `updated_at`.
- `DELETE /api/tg/admin/offers/{offer_id}` — soft delete: `is_active=false`, `updated_at=now`.

### Безопасная валидация payload

Partner:

- `title` обязателен при создании;
- строки trim;
- пустые строки сохраняются как `null`, кроме обязательного `title`;
- object/array вместо string запрещены;
- `is_active` default `true`;
- `sort_order` default `100`.

Photo:

- `image_url` обязателен при создании;
- `image_url` должен быть непустой string;
- `sort_order` default `100`;
- `is_cover` default `false`.

Offer:

- `title` обязателен при создании;
- `base_price`, `member_price`, `discount_percent` принимают number или `null`;
- пустая строка в money field нормализуется в `null`;
- object/array вместо number запрещены;
- `member_price=0` не считается валидной клубной ценой;
- цены округляются backend до двух знаков, чтобы не отдавать странные дроби;
- `is_active` default `true`;
- `sort_order` default `100`.

Ошибки payload возвращаются controlled `400 {"detail":"..."}` без traceback и без секретов.

### Curl-проверки admin CRUD

Подготовьте переменные локально в shell, не коммитьте их:

```bash
export TG_APP_ORIGIN="https://<TG_APP_DOMAIN>"
export TG_ADMIN_TOKEN="<TELEGRAM_ADMIN_API_TOKEN>"
```

Создать партнёра:

```bash
curl -sS -X POST "$TG_APP_ORIGIN/api/tg/admin/partners" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Admin-Token: $TG_ADMIN_TOKEN" \
  -d '{
    "title":"Счастье есть",
    "display_name":"Счастье есть",
    "description":"Описание партнёра",
    "city":"Новосибирск",
    "category":"Кафе",
    "address":"Адрес",
    "phone":"+79999999999",
    "is_active":true,
    "sort_order":100
  }'
```

Добавить фото URL:

```bash
curl -sS -X POST "$TG_APP_ORIGIN/api/tg/admin/partners/<partner_id>/photos" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TG_ADMIN_TOKEN" \
  -d '{"image_url":"https://example.com/photo.jpg","sort_order":100,"is_cover":true}'
```

Добавить offer:

```bash
curl -sS -X POST "$TG_APP_ORIGIN/api/tg/admin/partners/<partner_id>/offers" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Admin-Token: $TG_ADMIN_TOKEN" \
  -d '{
    "title":"Классика",
    "description":"Описание услуги",
    "conditions":"Условия получения привилегии",
    "base_price":2550,
    "member_price":2250,
    "discount_percent":null,
    "is_active":true,
    "sort_order":100
  }'
```

Выключить партнёра:

```bash
curl -sS -X DELETE "$TG_APP_ORIGIN/api/tg/admin/partners/<partner_id>" \
  -H "X-Telegram-Admin-Token: $TG_ADMIN_TOKEN"
```

Выключить offer:

```bash
curl -sS -X DELETE "$TG_APP_ORIGIN/api/tg/admin/offers/<offer_id>" \
  -H "X-Telegram-Admin-Token: $TG_ADMIN_TOKEN"
```

### Проверка public catalog

Public endpoints читают только локальную TG DB и не используют основной сайт `bloomclub.ru` для partners/offers/photos:

```bash
curl -sS "$TG_APP_ORIGIN/api/tg/partners"
curl -sS "$TG_APP_ORIGIN/api/tg/partners/<partner_id>"
curl -sS "$TG_APP_ORIGIN/api/tg/partners/<partner_id>/offers"
```

Public catalog отдаёт только active partners/offers и сохраняет shape `{ "items": [...] }` для списков. Основной сайт `bloomclub.ru`, WEB/VK repos, account linking backend и текущие пользовательские карточки Telegram Mini App в этом PR не менялись.

## Переключение пользовательской вкладки «Партнёры» на TG local catalog

Frontend Telegram Mini App поддерживает безопасное переключение источника данных через feature flag:

```dotenv
VITE_TG_LOCAL_CATALOG_ENABLED=true
VITE_TG_API_BASE_URL=
```

- `VITE_TG_LOCAL_CATALOG_ENABLED=true` включает локальный Telegram catalog API для пользовательской вкладки «Партнёры».
- `VITE_TG_API_BASE_URL=` оставляют пустым в production, если frontend и `/api/tg/...` обслуживаются с одного origin. В этом режиме запросы строятся как `/api/tg/partners`, `/api/tg/partners/<partner_id>` и `/api/tg/partners/<partner_id>/offers` от текущего origin.
- Если TG API вынесен на отдельный origin, укажите origin в `VITE_TG_API_BASE_URL`; относительные `image_url`/`file_path` из TG payload будут нормализованы от этого origin.

Для быстрого отката верните legacy WEB catalog flow:

```dotenv
VITE_TG_LOCAL_CATALOG_ENABLED=false
VITE_TG_API_BASE_URL=
```

При `VITE_TG_LOCAL_CATALOG_ENABLED=true` пользовательские экраны используют локальные endpoints:

```text
GET  /api/tg/partners
GET  /api/tg/partners/<partner_id>
GET  /api/tg/partners/<partner_id>/offers
POST /api/tg/partners/<partner_id>/offers/<offer_id>/verify
GET  /api/tg/me/verifications
GET  /api/tg/me/savings
```

Если `/api/tg/partners` возвращает пустой список, добавьте партнёров, фото и offers через отдельную страницу `/tg-admin` или admin endpoints `/api/tg/admin/...`.

### Как проверить, что WEB больше не грузит партнёров

1. Соберите и задеплойте frontend с `VITE_TG_LOCAL_CATALOG_ENABLED=true` и пустым `VITE_TG_API_BASE_URL`.
2. Откройте Telegram Mini App.
3. Откройте вкладку «Партнёры».
4. Проверьте network/server logs: для partners flow больше не должно быть запросов:
   - `/clients/catalog/partners`;
   - `/clients/partners/{id}/offers`.
5. Проверьте TG local API напрямую:

```bash
curl -sS "$TG_APP_ORIGIN/api/tg/partners"
curl -sS "$TG_APP_ORIGIN/api/tg/partners/<partner_id>"
curl -sS "$TG_APP_ORIGIN/api/tg/partners/<partner_id>/offers"
```

### Какие WEB endpoints остаются

Даже при включённом TG local catalog frontend продолжает использовать WEB identity/account API основного backend для сессии и профиля пользователя:

- `POST /auth/telegram-miniapp-login`;
- `GET/PATCH /clients/me`;
- `GET /clients/me/subscription`;
- `POST /clients/me/trial-subscription`;
- `GET /clients/me/linking-status`;
- `POST /clients/me/linking/start`;
- `POST /clients/me/linking/confirm`.

Эти endpoints остаются на `VITE_API_BASE_URL=https://bloomclub.ru/api/v1`, потому что они относятся к identity/account linking, профилю, подписке и trial, а не к локальному каталогу партнёров Telegram Mini App.

## Production switch checklist

### 1. Env

В production Timeweb env для финального включения local catalog задайте:

```dotenv
TELEGRAM_APP_DATABASE_URL=postgresql://gen_user:<password>@192.168.0.4:5432/default_db
TELEGRAM_ADMIN_API_TOKEN=<secret>
TELEGRAM_AUTO_INIT_DB=true
VITE_TG_LOCAL_CATALOG_ENABLED=true
VITE_TG_API_BASE_URL=
```

`VITE_TG_API_BASE_URL=` оставляется пустым, когда frontend и `/api/tg/*` обслуживаются с одного origin. Секреты не должны попадать в frontend bundle, git, console output или скриншоты.

### 2. Redeploy

Сделайте redeploy/restart. При `TELEGRAM_AUTO_INIT_DB=true` backend выполняет только idempotent schema init и не запускает seed.

### 3. Проверить backend endpoints

```bash
curl -i https://<TG_APP_DOMAIN>/api/tg/health
curl -i https://<TG_APP_DOMAIN>/api/tg/health/db
curl -i https://<TG_APP_DOMAIN>/api/tg/status
curl -i https://<TG_APP_DOMAIN>/api/tg/partners
```

Если эти URLs не отвечают JSON с production-домена, проверьте Timeweb routing/start command: Vite static build сам по себе не обслуживает Python WSGI backend. `/api/tg/*` должен быть прокинут в `backend.telegram_catalog.app:application`, а `/tg-admin` должен открываться как SPA route из Vite `dist/`.

### 4. Открыть admin UI

```text
https://<TG_APP_DOMAIN>/tg-admin
```

В блоке «Проверка системы» нажмите «Проверить API». Блок проверяет `/api/tg/health`, `/api/tg/health/db`, `/api/tg/status` и показывает API доступен/недоступен, DB ok/ошибка, active partners count и active offers count без вывода admin token или DB URL.

### 5. Создать данные

Создайте в `/tg-admin`:

- партнёра;
- фото;
- offer.

### 6. Проверить пользовательскую вкладку «Партнёры»

Проверьте, что `/api/tg/partners` не пустой, затем откройте Telegram Mini App → «Партнёры». При `VITE_TG_LOCAL_CATALOG_ENABLED=true` вкладка должна использовать TG local catalog endpoints и показывать TG-партнёров.

Если `/api/tg/partners` успешно возвращает `{ "items": [] }`, пользовательский экран показывает мягкое empty state: «Партнёры скоро появятся» и «Каталог Telegram-приложения наполняется. Загляните чуть позже.». Это не считается ошибкой загрузки.

Если `/api/tg/partners` недоступен, возвращает `503` или request timeout, пользовательский экран показывает «Не удалось загрузить каталог Telegram» и «Проверьте подключение и попробуйте снова.». Debug/details содержат только безопасные поля `source`, `requestUrlPath`, `requestOrigin`, `httpStatus`, `requestId`, `elapsedMs`, `attempt`.

### 7. Проверить WEB logs

В логах `fed_women_club_WEB` после открытия TG «Партнёры» не должно быть:

- `/clients/catalog/partners`;
- `/clients/partners/{id}/offers`.

Но могут оставаться WEB identity/account endpoints:

- `/auth/telegram-miniapp-login`;
- `/clients/me`;
- `/clients/me/subscription`;
- `/clients/me/trial-subscription`;
- `/clients/me/linking-status`.

### 8. Выключить auto init после успешной проверки

После успешной production-проверки можно поставить:

```dotenv
TELEGRAM_AUTO_INIT_DB=false
```

и сделать redeploy. Данные TG DB при этом остаются на месте.

### 9. Rollback

Если TG local catalog не работает, переключите frontend flag назад:

```dotenv
VITE_TG_LOCAL_CATALOG_ENABLED=false
VITE_TG_API_BASE_URL=
```

После redeploy пользовательский каталог временно вернётся на WEB legacy flow. Не нужно менять WEB/VK/site, account linking backend или удалять локальную TG DB.


## Если `/api/tg/health` отдаёт HTML вместо JSON

Причина: production-домен Timeweb обслуживает только Vite static `dist/index.html`, и SPA fallback перехватывает `/api/tg/*`. В этом состоянии `/api/tg/health` не попадает в Python WSGI backend, поэтому вместо JSON возвращается HTML frontend Bloom Club и возможна frontend-ошибка `init_data_read`.

Нужный production entrypoint в этом репозитории:

```bash
python -m backend.telegram_catalog.production_app
```

Он маршрутизирует:

- `/api/tg/*` → `backend.telegram_catalog.app:application` и JSON responses;
- `/assets/*` → файлы из Vite `dist/assets`;
- `/tg-admin`, `/` и остальные frontend routes → `dist/index.html`;
- неизвестные `/api/tg/*` и `/api/*` → JSON `404`, не HTML.

Timeweb Build command:

```bash
npm install && npm run build && pip install -r requirements.txt
```

Timeweb Start command:

```bash
npm run start:production
```

Если npm wrapper недоступен, используйте:

```bash
python -m backend.telegram_catalog.production_app
```

Production app слушает `0.0.0.0` и порт из env `PORT`; если `PORT` не задан, используется `8000`.

Production env:

```dotenv
TELEGRAM_APP_DATABASE_URL=postgresql://gen_user:<password>@192.168.0.4:5432/default_db
TELEGRAM_ADMIN_API_TOKEN=<secret>
TELEGRAM_AUTO_INIT_DB=true
VITE_TG_LOCAL_CATALOG_ENABLED=true
VITE_TG_API_BASE_URL=
```

После успешной проверки поставьте:

```dotenv
TELEGRAM_AUTO_INIT_DB=false
```

Проверка API:

```bash
curl -i https://<TG_APP_DOMAIN>/api/tg/health
```

Ожидание:

```text
Content-Type: application/json
{"status":"ok","service":"telegram-local-catalog"}
```

Проверка admin SPA route:

```bash
curl -i https://<TG_APP_DOMAIN>/tg-admin
```

Ожидание:

```text
Content-Type: text/html
```

Rollback, если routing сломался:

1. вернуть старую Timeweb start command/static deployment;
2. поставить `VITE_TG_LOCAL_CATALOG_ENABLED=false` и `VITE_TG_API_BASE_URL=`;
3. redeploy.

WEB/VK/site repos, backend основного сайта `bloomclub.ru`, account linking backend и пользовательский UI при этом не меняются.
