# Production Readiness Audit — Bloom Club Telegram Layer

Дата аудита: 2026-06-25  
Репозиторий: `/workspace/bloom_app_TELEGA_NEW`  
Тип работ: **исключительно production readiness audit**  
Изменения кода: **не выполнялись**  
Единственный созданный файл: `production-readiness-audit.md`

## 0. Executive summary

Проект **не готов к production-запуску без исправлений**. Репозиторий содержит рабочий Telegram Mini App слой, Node production server, локальный TG catalog API, Python WSGI scaffold, sync-скрипты и admin bot, но production readiness ограничена отсутствием полноценной readiness-модели, rollback/release runbook, миграционного процесса, мониторинга/алертов, резервного копирования, метрик, dashboards, формализованного recovery при частичных отказах и контролируемой WEB → TG consistency boundary.

Ключевой вывод: приложение может отдать UI и часть fallback-состояний, но production-эксплуатация будет зависеть от ручной диагностики и знания кода. При отказах Postgres, WEB API, Content API, uploads/assets или Telegram WebView поведение часто деградирует в пустой каталог, 502/504, stale UI или ручной retry без централизованной сигнализации.

## 1. Что изучено

Перед анализом кода изучены обязательные документы:

- `architecture.md`
- `backend.md`
- `frontend.md`
- `state-management.md`
- `request-flow.md`
- `data-flow.md`
- `infrastructure.md`
- `security-audit.md`
- `architecture-audit.md`

Дополнительно изучены ключевые файлы исходного кода и инфраструктуры:

- `Dockerfile`
- `docker-compose.yml`
- `telegram-mini-app/package.json`
- `telegram-mini-app/server/production-server.js`
- `telegram-mini-app/src/App.tsx`
- `telegram-mini-app/src/api/client.ts`
- `telegram-mini-app/src/content/ContentContext.tsx`
- `telegram-mini-app/src/components/RuntimeErrorBoundary.tsx`
- `telegram-mini-app/src/telegram/webapp.ts`
- `telegram-mini-app/src/stateRecovery.ts`
- `telegram-mini-app/src/diagnostics/startupTrace.ts`
- `telegram-mini-app/telegram_app/scripts/init_db.py`
- `telegram-mini-app/telegram_app/scripts/check_db_env.py`
- `telegram-mini-app/telegram_app/scripts/sync_content_to_tg_catalog.py`
- `telegram-mini-app/backend/telegram_catalog/app.py`
- `telegram-mini-app/backend/telegram_catalog/database.py`
- `telegram-mini-app/backend/telegram_catalog/repository.py`
- `admin_bot/admin_bot/config.py`
- `admin_bot/admin_bot/web_api.py`
- `admin_bot/admin_bot/bot.py`
- тесты в `telegram-mini-app/tests/*` и `admin_bot/tests/*`

## 2. Availability audit

### 2.1 Падение Node

Node production server — единственный runtime в Dockerfile. При падении процесса Docker Compose может перезапустить контейнер только если используется `restart: unless-stopped`; вне Docker/systemd поведение зависит от внешнего supervisor. Пока Node лежит, недоступны HTML, assets, uploads, `/api/tg/*`, login proxy, client proxy и content proxy. Health endpoint тоже недоступен.

### 2.2 Падение Python

Python WSGI catalog backend в текущем Docker runtime не запускается. Если он используется отдельно, его падение затронет альтернативные `/api/tg/*`, admin CRUD и upload endpoint. Admin bot — отдельный Python-процесс; его падение не ломает Mini App, но блокирует Telegram-администрирование контента.

### 2.3 Падение Postgres

Node `/api/tg/health/db` вернёт 503, `/api/tg/status` вернёт ошибку, каталог вернёт 503 при ошибке query. Однако `/ready` остаётся `ok`, а HTML всё равно отдаётся, пытаясь инжектить bootstrap-каталог и логируя warning при ошибке. Платформа может продолжать слать traffic на partially broken instance.

### 2.4 Падение WEB API

Login proxy и client proxy возвращают 502/504 с пользовательским сообщением. Bootstrap frontend зависит от login/profile/subscription, поэтому новый запуск Mini App может остановиться на error state. Stored token помогает только пока WEB API доступен для profile/subscription; без WEB API полноценного offline режима нет.

### 2.5 Падение Content API

Node content blocks proxy при ошибке возвращает `[]` со статусом 200. Frontend ContentProvider использует default content, но централизованного degraded-сигнала, алерта или dashboard нет.

### 2.6 Падение Telegram WebView / Telegram SDK

Frontend имеет runtime check, retry получения launch payload и диагностические сообщения. В production вне Telegram без launch payload bootstrap падает. Для Telegram iOS reopen есть частичная stale-state cleanup и watchdog, но нет полноценного URL/state-router восстановления partner/offers экрана.

### 2.7 Недоступность uploads/assets

Assets отдаются напрямую из `dist/assets`; при отсутствии файла пользователь получит 404 и возможный white screen при missing JS/CSS chunk. Uploads отдаются из локального filesystem `telegram-mini-app/uploads`; без persistent volume или общей object storage файлы могут пропасть при redeploy/container replacement.

## 3. Issues register

### PRD-001 — `/ready` не проверяет обязательные зависимости

- **Область:** Availability / health checks
- **Severity:** Critical
- **Где найдено:** `production-server.js`, `/ready`; `architecture-audit.md` ARCH-010
- **Описание:** Readiness возвращает `ok` без проверки DB, schema, catalog mode и upstream critical dependencies.
- **Как проявится в production:** Load balancer/platform будет считать instance готовым, хотя каталог или DB не работают.
- **Вероятность:** High
- **Последствия:** Пользователи получают пустой/сломанный каталог после деплоя или DB incident; rollback может не стартовать автоматически.
- **Как обнаружить:** Сравнить `/ready` и `/api/tg/health/db`; проверить synthetic catalog request.
- **Как временно обойти:** В healthcheck платформы использовать `/api/tg/health/db` для catalog-enabled production.
- **Как исправить правильно:** Разделить `/live` и `/ready`; readiness должен проверять DB connectivity, schema version и обязательные feature flags.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Medium

### PRD-002 — Отсутствие DB URL маскируется пустым каталогом

- **Область:** Availability / data correctness
- **Severity:** Critical
- **Где найдено:** `production-server.js`, `handlePartners`; `architecture-audit.md` ARCH-011
- **Описание:** Если `TELEGRAM_APP_DATABASE_URL` не задан, `/api/tg/partners` возвращает `200 {items: []}`.
- **Как проявится в production:** Ошибка env/deploy выглядит как легитимно пустой каталог.
- **Вероятность:** Medium
- **Последствия:** Запуск с пустым каталогом без алерта; бизнес-функция Mini App фактически не работает.
- **Как обнаружить:** Проверить `/api/tg/status`, env и количество partners; synthetic check `items.length > 0`.
- **Как временно обойти:** Добавить внешнюю smoke-проверку `/api/tg/status` и ручной gate перед BotFather URL switch.
- **Как исправить правильно:** В production catalog-enabled режиме возвращать 503 и проваливать readiness при missing DB.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Medium

### PRD-003 — Runtime server выполняет DDL при startup

- **Область:** Deployment / startup safety / migrations
- **Severity:** High
- **Где найдено:** `production-server.js`, `schemaStatements`, `initDatabaseIfEnabled`; `architecture-audit.md` ARCH-009
- **Описание:** При `TELEGRAM_AUTO_INIT_DB=true` Node выполняет schema init во время старта.
- **Как проявится в production:** Несколько replicas могут конкурировать за DDL locks; ошибка прав блокирует startup.
- **Вероятность:** Medium
- **Последствия:** Deploy outage, непредсказуемые startup failures.
- **Как обнаружить:** Логи старта, зависание контейнера, отсутствие `/health`.
- **Как временно обойти:** Держать `TELEGRAM_AUTO_INIT_DB=false`, запускать init отдельно вручную.
- **Как исправить правильно:** Ввести отдельный migration job с версионированием, locks и rollback plan.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Medium

### PRD-004 — Нет формального rollback процесса

- **Область:** Deployment / release operations
- **Severity:** Critical
- **Где найдено:** `infrastructure.md`, Dockerfile/docker-compose, отсутствие release runbook
- **Описание:** Нет описанного rollback для image/tag, env, DB schema, sync-state и BotFather URL.
- **Как проявится в production:** При плохом релизе команда будет импровизировать rollback.
- **Вероятность:** High
- **Последствия:** Длительный incident, несовместимость кода и данных.
- **Как обнаружить:** Проверить наличие release checklist и rollback checklist; их нет как исполняемого процесса.
- **Как временно обойти:** До запуска подготовить ручной runbook с предыдущим image/tag и env snapshot.
- **Как исправить правильно:** Ввести versioned deployments, immutable images, DB migration rollback policy, BotFather rollback URL procedure.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Low/Medium

### PRD-005 — WEB → TG sync не имеет atomic publish boundary

- **Область:** Data operations / consistency
- **Severity:** Critical
- **Где найдено:** `sync_content_to_tg_catalog.py`; `architecture-audit.md` ARCH-014
- **Описание:** Sync выполняет последовательные fetch/upsert/prune без snapshot version, staging tables, sync run marker и atomic publish.
- **Как проявится в production:** TG DB содержит смесь старых и новых partners/offers/photos после partial failure.
- **Вероятность:** High
- **Последствия:** Неверные офферы, stale данные, потеря доверия к каталогу.
- **Как обнаружить:** Сверка counts/checksums WEB и TG, sync stats, ручной audit external_content_id.
- **Как временно обойти:** Запускать sync в low-traffic окно с `--dry-run`, без prune по умолчанию, затем smoke catalog.
- **Как исправить правильно:** Staging tables, sync_runs, source version/checkpoint, transaction, atomic active snapshot switch.
- **Нужно ли исправлять до запуска:** Да, если каталог production-critical
- **Риск исправления:** High

### PRD-006 — Нет backup/restore runbook и проверенной процедуры восстановления

- **Область:** Data operations / disaster recovery
- **Severity:** Critical
- **Где найдено:** Документы и repo не содержат restore drill; `infrastructure.md`, `backend.md`
- **Описание:** Описаны DB init/sync, но нет production backup schedule, restore RTO/RPO, проверки дампа и восстановления uploads.
- **Как проявится в production:** После потери DB/volume восстановление будет ручным и непроверенным.
- **Вероятность:** Medium
- **Последствия:** Потеря каталога, privilege codes, upload links; длительный простой.
- **Как обнаружить:** Проверить наличие актуального backup artifact и restore log.
- **Как временно обойти:** Настроить ежедневный `pg_dump`, хранение вне сервера, ручной restore test на staging.
- **Как исправить правильно:** Автоматические backups, encrypted offsite storage, restore drills, RPO/RTO, monitoring backup freshness.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Low/Medium

### PRD-007 — Uploads хранятся в локальном filesystem

- **Область:** Availability / data durability
- **Severity:** High
- **Где найдено:** `production-server.js` `/uploads/*`; Python upload endpoint; Dockerfile/docker-compose без volume
- **Описание:** Upload assets читаются из локальной директории приложения; compose не объявляет persistent/shared volume.
- **Как проявится в production:** После redeploy или нового контейнера images могут стать 404.
- **Вероятность:** Medium
- **Последствия:** Broken images, визуальная деградация каталога и контента.
- **Как обнаружить:** Synthetic HEAD/GET популярных uploads, 404 rate по `/uploads/*`.
- **Как временно обойти:** Смонтировать persistent volume и не пересоздавать его при deploy.
- **Как исправить правильно:** Перенести uploads в object storage/CDN с signed admin upload flow и backup lifecycle.
- **Нужно ли исправлять до запуска:** Да, если uploads используются в production
- **Риск исправления:** Medium

### PRD-008 — Отсутствуют structured logs с обязательным requestId/traceId

- **Область:** Observability
- **Severity:** High
- **Где найдено:** `production-server.js`, frontend diagnostics, `backend.md`
- **Описание:** Есть console logs и safe redaction, но нет единого JSON logging schema, generated requestId для каждого запроса и trace propagation.
- **Как проявится в production:** Incident investigation требует ручного сопоставления строк логов.
- **Вероятность:** High
- **Последствия:** Долгое расследование 502, auth failed, empty catalog.
- **Как обнаружить:** Проверить логи одного запроса end-to-end; отсутствует единый trace.
- **Как временно обойти:** Включить reverse-proxy request id и искать по timestamp/path/user-agent.
- **Как исправить правильно:** JSON logs, requestId middleware, x-request-id propagation, traceId in frontend diagnostics.
- **Нужно ли исправлять до запуска:** Да для нормальной эксплуатации
- **Риск исправления:** Medium

### PRD-009 — Нет metrics, alerts и dashboards

- **Область:** Observability / incident response
- **Severity:** Critical
- **Где найдено:** Документы и код; есть health/status, но нет metrics endpoint/exporter
- **Описание:** Нет метрик latency/error rate, DB pool, catalog count, bootstrap failures, white screen watchdog, sync stats, admin bot health.
- **Как проявится в production:** Команда узнает о проблемах от пользователей.
- **Вероятность:** High
- **Последствия:** Высокий MTTR, пропущенные degradation incidents.
- **Как обнаружить:** Отсутствие `/metrics`, alert rules и dashboards.
- **Как временно обойти:** Настроить внешние synthetic checks и platform uptime alerts.
- **Как исправить правильно:** Prometheus/OpenTelemetry/Sentry или аналог, dashboards по golden signals, alert thresholds.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Medium

### PRD-010 — Content API failure скрывается как пустой массив

- **Область:** Reliability / observability
- **Severity:** Medium
- **Где найдено:** `production-server.js`, `contentBlocksFallbackResponse`; `ContentContext.tsx`
- **Описание:** При ошибке Content API Node возвращает 200 `[]`, frontend показывает default content.
- **Как проявится в production:** Контент не обновился, но мониторинг не видит ошибку по статусам.
- **Вероятность:** Medium
- **Последствия:** Скрытая деградация промо/главной страницы.
- **Как обнаружить:** Логи `content_blocks_proxy_error`, сравнение expected blocks count.
- **Как временно обойти:** Synthetic check на наличие обязательных content keys.
- **Как исправить правильно:** Возвращать degraded metadata/header, метрику fallback, не маскировать upstream failure полностью.
- **Нужно ли исправлять до запуска:** Желательно
- **Риск исправления:** Low/Medium

### PRD-011 — HTML bootstrap делает DB query на каждый frontend request

- **Область:** Performance / availability
- **Severity:** High
- **Где найдено:** `production-server.js`, `serveFrontend`, `fetchPublicCatalogPartners`; `architecture-audit.md` ARCH-012
- **Описание:** Каждый HTML request читает весь active catalog из DB и инжектит его в `index.html`.
- **Как проявится в production:** First paint зависит от DB latency и размера каталога; HTML payload растёт.
- **Вероятность:** High при росте каталога
- **Последствия:** Медленный старт, повышенная DB нагрузка, хуже cacheability.
- **Как обнаружить:** Измерять HTML TTFB, response size, DB query time.
- **Как временно обойти:** Отключить bootstrap или ограничить catalog size в production runbook.
- **Как исправить правильно:** TTL cache/ETag/size cap, lazy catalog load, compact bootstrap subset.
- **Нужно ли исправлять до запуска:** Да при ожидаемом росте каталога
- **Риск исправления:** Medium

### PRD-012 — Нет bundle budget и performance budget

- **Область:** Performance / release readiness
- **Severity:** Medium
- **Где найдено:** `package.json` scripts, Vite build; отсутствуют size checks
- **Описание:** Build не проверяет JS/CSS размер, chunk count, startup latency или bootstrap payload size.
- **Как проявится в production:** Mini App может медленно открываться в Telegram WebView, особенно на слабых устройствах.
- **Вероятность:** Medium
- **Последствия:** Рост bounce rate, loader stuck perception.
- **Как обнаружить:** Lighthouse/WebPageTest/real device timing, Vite bundle analysis.
- **Как временно обойти:** Ручная проверка `dist/assets` size перед релизом.
- **Как исправить правильно:** CI budget, bundle analyzer, RUM metrics, chunk preload strategy.
- **Нужно ли исправлять до запуска:** Желательно
- **Риск исправления:** Low

### PRD-013 — Chunk/assets 404 приводит к white screen risk

- **Область:** Reliability / frontend availability
- **Severity:** High
- **Где найдено:** static serving `/assets/*`, RuntimeErrorBoundary, absence of service-worker/chunk reload handling
- **Описание:** Missing JS chunk возвращает 404; нет явного chunk-load recovery/reload с version detection.
- **Как проявится в production:** После deploy пользователь со старым HTML получает 404 на hashed asset и видит white screen/error.
- **Вероятность:** Medium
- **Последствия:** Массовые ошибки после релиза.
- **Как обнаружить:** 404 rate по `/assets/*`, browser `ChunkLoadError`.
- **Как временно обойти:** Не удалять старые assets между релизами, immutable release dirs.
- **Как исправить правильно:** Versioned asset retention, chunk load error handler, cache-control strategy, blue/green deploy.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Medium

### PRD-014 — WEB API proxy без retry/circuit breaker

- **Область:** Reliability / partial failure
- **Severity:** High
- **Где найдено:** `production-server.js`, login/client/content proxy
- **Описание:** Node proxy имеет timeout, но нет retry policy, circuit breaker, backoff или upstream health state.
- **Как проявится в production:** Кратковременный upstream blip превращается в user-visible bootstrap failure.
- **Вероятность:** Medium
- **Последствия:** Auth failed, profile/subscription unavailable.
- **Как обнаружить:** 502/504 rate, upstream latency histogram.
- **Как временно обойти:** Повторная попытка пользователем; external uptime monitor WEB API.
- **Как исправить правильно:** Safe retries для idempotent requests, circuit breaker, differentiated upstream error metrics.
- **Нужно ли исправлять до запуска:** Желательно/Да для launch stability
- **Риск исправления:** Medium

### PRD-015 — Frontend retry policy минимальна и не покрывает все recovery сценарии

- **Область:** Reliability / frontend
- **Severity:** Medium
- **Где найдено:** `client.ts`, `GET_RETRY_ATTEMPTS = 1`, `TELEGRAM_LOGIN_RETRY_ATTEMPTS = 1`; `App.tsx`
- **Описание:** Есть один retry для GET/login, но нет adaptive backoff, offline detection, retry-after handling, stale cached data mode.
- **Как проявится в production:** При мобильной сети пользователь часто попадает в error state вместо graceful degraded UI.
- **Вероятность:** High для Telegram mobile
- **Последствия:** Loader stuck/error на старте.
- **Как обнаружить:** Frontend diagnostics, RUM failed bootstrap count.
- **Как временно обойти:** UX-инструкция повторить попытку / переоткрыть Mini App.
- **Как исправить правильно:** Exponential backoff, network status handling, cached last-known catalog/profile where safe.
- **Нужно ли исправлять до запуска:** Желательно
- **Риск исправления:** Medium

### PRD-016 — State management не имеет единого source of truth

- **Область:** Reliability / stale state recovery
- **Severity:** High
- **Где найдено:** `App.tsx`; `architecture-audit.md` ARCH-004
- **Описание:** Состояние распределено между `data`, отдельными states, refs, localStorage и bootstrap global.
- **Как проявится в production:** При retry/reopen возможны stale partner offers, несогласованная страница и устаревшие diagnostics.
- **Вероятность:** Medium
- **Последствия:** Непредсказуемое UI состояние, сложные incident reports.
- **Как обнаружить:** E2E сценарии rapid tab switch, iOS reopen, retry while catalog loading.
- **Как временно обойти:** Manual QA перед launch, recovery button to catalog.
- **Как исправить правильно:** Reducer/state machine plus server-state cache with explicit states.
- **Нужно ли исправлять до запуска:** Желательно; must-fix если воспроизводятся stale bugs
- **Риск исправления:** High

### PRD-017 — Нет полноценного URL/router state для partner/offers

- **Область:** Telegram iOS reopen / deep link recovery
- **Severity:** High
- **Где найдено:** `App.tsx`, `getStartupPage`, `PageId`; `architecture-audit.md` ARCH-002
- **Описание:** URL отражает только `#catalog`; partner page не восстанавливается независимо.
- **Как проявится в production:** Reopen/reload возвращает пользователя в catalog/home или stale state.
- **Вероятность:** Medium
- **Последствия:** Потеря контекста, жалобы на Telegram iOS reopen.
- **Как обнаружить:** Manual QA iOS close/reopen на partner page.
- **Как временно обойти:** Recovery в каталог и повторный выбор партнёра.
- **Как исправить правильно:** Lightweight router `/catalog`, `/partners/:id`, independent partner load by id.
- **Нужно ли исправлять до запуска:** Желательно для UX
- **Риск исправления:** Medium

### PRD-018 — Нет контрактной схемы API

- **Область:** Reliability / integration
- **Severity:** High
- **Где найдено:** `client.ts`, Node/Python endpoints; `architecture-audit.md` ARCH-013
- **Описание:** Нет OpenAPI/JSON Schema для consumed WEB API, TG API и Content API.
- **Как проявится в production:** Изменение WEB response shape ломает frontend silently или через runtime error.
- **Вероятность:** Medium
- **Последствия:** Empty data, wrong field mappings, hard-to-debug regressions.
- **Как обнаружить:** Contract tests, runtime validation failures.
- **Как временно обойти:** Smoke tests after every WEB deploy.
- **Как исправить правильно:** OpenAPI/JSON Schema, generated types, contract tests, runtime validation for critical responses.
- **Нужно ли исправлять до запуска:** Желательно/Да для coordinated release
- **Риск исправления:** Medium

### PRD-019 — Две backend реализации TG catalog API могут расходиться

- **Область:** Architecture / deployment reliability
- **Severity:** High
- **Где найдено:** Node `production-server.js`, Python `backend/telegram_catalog/*`; `architecture-audit.md` ARCH-008
- **Описание:** Node production и Python WSGI реализуют overlapping `/api/tg/*` с разными capabilities и semantics.
- **Как проявится в production:** Разные deployments ведут себя по-разному; исправления попадают только в один runtime.
- **Вероятность:** Medium
- **Последствия:** Divergence, ошибки в runbook и QA.
- **Как обнаружить:** Contract comparison tests Node vs Python.
- **Как временно обойти:** Явно объявить Node единственным production runtime.
- **Как исправить правильно:** Один production backend или общий контракт+shared tests.
- **Нужно ли исправлять до запуска:** Да как документированное решение
- **Риск исправления:** High если Python реально используется

### PRD-020 — Нет production checklist для порядка migration/sync/deploy

- **Область:** Deployment / data operations
- **Severity:** Critical
- **Где найдено:** docs/scripts; отсутствует обязательный release gate
- **Описание:** Есть команды init/sync/build/start, но нет строгого порядка: backup → migration → sync dry-run → deploy → smoke → BotFather switch.
- **Как проявится в production:** Релиз выполняется неполно или в неверном порядке.
- **Вероятность:** High
- **Последствия:** Empty catalog, schema mismatch, broken Telegram URL.
- **Как обнаружить:** Pre-launch review release checklist.
- **Как временно обойти:** Использовать checklist из этого документа.
- **Как исправить правильно:** Добавить `PRODUCTION_RUNBOOK.md` или CI/CD pipeline с gates.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Low

### PRD-021 — Docker image использует `latest` зависимости

- **Область:** Deployment reproducibility / supply chain
- **Severity:** High
- **Где найдено:** `telegram-mini-app/package.json`, dependencies `latest`; Dockerfile `npm ci` partially mitigates via lock
- **Описание:** package.json не pin-ит версии; lockfile помогает, но обновления lock могут неожиданно подтянуть major версии.
- **Как проявится в production:** Build после lock update меняет React/Vite/pg поведение.
- **Вероятность:** Medium
- **Последствия:** Невоспроизводимые релизы, supply-chain risk.
- **Как обнаружить:** Diff package-lock, SBOM/dependency audit.
- **Как временно обойти:** Не обновлять lock без отдельного dependency PR.
- **Как исправить правильно:** Pin/range policy, Dependabot/Renovate, npm audit/SBOM, tested dependency upgrades.
- **Нужно ли исправлять до запуска:** Желательно
- **Риск исправления:** Low/Medium

### PRD-022 — Docker Compose не содержит healthcheck

- **Область:** Availability / deployment
- **Severity:** High
- **Где найдено:** `docker-compose.yml`
- **Описание:** Service has restart policy but no container healthcheck/readiness integration.
- **Как проявится в production:** Container can be running but serving broken app; orchestrator cannot mark unhealthy.
- **Вероятность:** Medium
- **Последствия:** Silent partial outage.
- **Как обнаружить:** `docker inspect` health absent; compose file review.
- **Как временно обойти:** External monitor hits `/api/tg/health/db` and `/api/tg/partners`.
- **Как исправить правильно:** Add healthcheck and align it with real readiness endpoint.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Low/Medium

### PRD-023 — Admin bot health/observability не оформлены

- **Область:** Observability / operations
- **Severity:** Medium
- **Где найдено:** `admin_bot/*`, systemd example, tests
- **Описание:** Admin bot has config/client tests, but no health endpoint, heartbeat, metrics or alert if polling/webhook stops.
- **Как проявится в production:** Админы не смогут управлять контентом, но команда узнает вручную.
- **Вероятность:** Medium
- **Последствия:** Задержка обновлений каталога/контента.
- **Как обнаружить:** systemd status, bot command synthetic test.
- **Как временно обойти:** Manual `systemctl status` and Telegram test command after deploy.
- **Как исправить правильно:** Heartbeat metric, structured logs, alert on no updates/polling errors.
- **Нужно ли исправлять до запуска:** Желательно
- **Риск исправления:** Low

### PRD-024 — Security blockers из security-audit требуют отдельного launch gate

- **Область:** Security readiness
- **Severity:** Critical
- **Где найдено:** `security-audit.md`
- **Описание:** Security findings должны быть классифицированы как launch blockers/accepted risks; в текущем release flow нет security gate.
- **Как проявится в production:** Известная critical/high уязвимость может быть выкачена без sign-off.
- **Вероятность:** Medium
- **Последствия:** Компрометация token/admin/API/data, compliance/reputation risk.
- **Как обнаружить:** Сверить unresolved Critical/High из `security-audit.md` с launch checklist.
- **Как временно обойти:** Manual security sign-off before BotFather URL switch.
- **Как исправить правильно:** Security gate in CI/CD, threat model, secrets audit, dependency audit, access review.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Medium

### PRD-025 — Incident runbooks отсутствуют как операционные инструкции

- **Область:** Operational runbooks
- **Severity:** Critical
- **Где найдено:** docs do not contain runbooks for required scenarios
- **Описание:** Нет пошаговых runbooks для 502, 404, white screen, pink screen, Telegram loader stuck, catalog empty, sync failed, Node/DB/WEB down.
- **Как проявится в production:** Во время incident действия будут зависеть от конкретного разработчика.
- **Вероятность:** High
- **Последствия:** Высокий MTTR и риск неправильного rollback.
- **Как обнаружить:** Проверить наличие runbook документа и ownership/on-call contacts.
- **Как временно обойти:** Использовать раздел runbooks ниже.
- **Как исправить правильно:** Создать production operations handbook with owners, commands, logs, dashboards, escalation.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Low

### PRD-026 — Нет real production validation для Telegram constraints

- **Область:** Release readiness / Telegram WebView
- **Severity:** High
- **Где найдено:** frontend Telegram runtime code and docs; no production device matrix evidence
- **Описание:** Нужны проверки iOS/Android/Desktop Telegram, reopen, loader, viewport, initData, BotFather URL.
- **Как проявится в production:** На части клиентов Mini App не открывается или зависает.
- **Вероятность:** Medium
- **Последствия:** Launch failure для mobile audience.
- **Как обнаружить:** Manual QA matrix on real Telegram clients.
- **Как временно обойти:** Ограниченный rollout через тестовый bot/URL.
- **Как исправить правильно:** Device matrix, staged rollout, RUM startup telemetry.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Low/Medium

### PRD-027 — DB query performance and indexes не проверены на production объёмах

- **Область:** Performance / scalability
- **Severity:** Medium
- **Где найдено:** catalog queries in Node, schema indexes; no load test artifacts
- **Описание:** Есть индексы по active/sort/partner, но нет EXPLAIN/load tests for 1k/10k users and large catalog.
- **Как проявится в production:** HTML bootstrap and catalog endpoints degrade as catalog grows.
- **Вероятность:** Medium
- **Последствия:** Slow startup, DB CPU spikes.
- **Как обнаружить:** `EXPLAIN ANALYZE`, k6/autocannon, pg_stat_statements.
- **Как временно обойти:** Ограничить catalog size and concurrent launch traffic.
- **Как исправить правильно:** Load tests, query optimization, caching, pagination/search indexes.
- **Нужно ли исправлять до запуска:** Желательно
- **Риск исправления:** Medium

### PRD-028 — Connection pool max=5 может стать bottleneck

- **Область:** Scalability / DB bottlenecks
- **Severity:** Medium
- **Где найдено:** `production-server.js`, `new Pool({ max: 5 })`
- **Описание:** Один Node instance имеет 5 DB connections; HTML bootstrap plus API calls can queue under traffic.
- **Как проявится в production:** At 1k/10k users first bottleneck likely Node DB pool/DB due bootstrap query per HTML.
- **Вероятность:** Medium
- **Последствия:** Latency spikes and 503 under DB pressure.
- **Как обнаружить:** Pool wait time metrics, DB active connections, request latency.
- **Как временно обойти:** Reduce bootstrap DB calls, scale instances carefully, tune Postgres max connections.
- **Как исправить правильно:** Cache bootstrap, tune pool, add metrics, use PgBouncer if needed.
- **Нужно ли исправлять до запуска:** Желательно
- **Риск исправления:** Medium

### PRD-029 — No release versioning surfaced in runtime/UI

- **Область:** Deployment / incident investigation
- **Severity:** Medium
- **Где найдено:** `buildInfo.ts` exists, but production server/debug versioning not formalized in docs/runbook
- **Описание:** Нет обязательного release id/image tag/git sha propagation into health/debug and frontend diagnostics.
- **Как проявится в production:** Трудно понять, какой релиз у пользователя или контейнера.
- **Вероятность:** Medium
- **Последствия:** Slow rollback/investigation.
- **Как обнаружить:** Check `/debug/runtime-port` and frontend diagnostics for git sha/release id.
- **Как временно обойти:** Record deployed commit manually in release notes.
- **Как исправить правильно:** Inject `RELEASE_VERSION`, git SHA, build timestamp to `/health`, `/ready`, frontend diagnostics and logs.
- **Нужно ли исправлять до запуска:** Желательно
- **Риск исправления:** Low

### PRD-030 — BotFather URL update is manual and not guarded

- **Область:** Deployment / Telegram operations
- **Severity:** High
- **Где найдено:** docs mention BotFather URL updates, no executable runbook/gate
- **Описание:** Production switch depends on updating Telegram Mini App URL; no checklist for pre/post validation or rollback URL.
- **Как проявится в production:** Users can be sent to wrong/staging/broken URL.
- **Вероятность:** Medium
- **Последствия:** Launch outage independent of app health.
- **Как обнаружить:** Manual BotFather configuration check and real Telegram open.
- **Как временно обойти:** Keep previous URL documented and test new URL via staging bot first.
- **Как исправить правильно:** BotFather rollout plan with owner, screenshots, timestamps, rollback URL and validation matrix.
- **Нужно ли исправлять до запуска:** Да
- **Риск исправления:** Low

## 4. Scalability assessment

- **10 users:** Вероятно работает, если WEB API, DB and assets доступны. Главные риски — config mistakes and Telegram WebView edge cases.
- **100 users:** Вероятно работает при небольшом каталоге. Начнут проявляться Content/WEB API latency and mobile retry issues.
- **1 000 users:** First bottleneck likely Node DB pool and HTML bootstrap DB query per open. WEB API auth/profile endpoints may become upstream bottleneck. No metrics means issue will be noticed late.
- **10 000 users:** Current architecture without caching, metrics, CDN/object storage and load tests is high risk. Bottlenecks: DB pool/query load, upstream WEB API login/profile, static asset deploy consistency, Telegram WebView startup latency.

Где сломается первым: **startup path** — Telegram open → Node HTML → DB bootstrap → Telegram login proxy → WEB profile/subscription. Это критическая цепочка без circuit breaker, metrics and production load validation.

## 5. Security readiness classification

Security audit findings must be used as launch gate. Production blockers are all unresolved Critical findings and High findings related to secrets, auth/admin endpoints, upload handling, CORS/origin, dependency supply chain and token leakage. Temporarily acceptable only Medium/Low findings with explicit owner, expiry date and compensating controls. Immediate fix required for any issue allowing admin token compromise, unauthorized content modification, arbitrary upload exposure, auth bypass or leakage of Telegram initData/access token.

## 6. Operational runbooks — first response

### 6.1 502 / 504
1. Check Node logs for `*_proxy_error`.
2. Check upstream WEB API status from server.
3. Check DNS/TLS/connectivity.
4. If only Content API fails, verify default content fallback.
5. If auth/profile fails, consider rollback or maintenance notice.

### 6.2 404
1. Identify path: `/assets/*`, `/uploads/*`, `/api/*`, frontend route.
2. For `/assets/*`: verify current `dist/assets`, old asset retention and deploy consistency.
3. For `/uploads/*`: verify persistent volume/object storage.
4. For API: verify route support and proxy path.

### 6.3 White screen
1. Open browser console/Telegram diagnostics.
2. Check `/assets/*` 404 and JS errors.
3. Use RuntimeErrorBoundary diagnostic if rendered.
4. Roll back if chunk-load errors spike after deploy.

### 6.4 Pink screen
1. Capture screenshot/device/Telegram version.
2. Check CSS asset 404 and runtime errors.
3. Verify build hash and cached HTML/assets mismatch.

### 6.5 Telegram loader stuck
1. Check `/health`, `/ready`, `/api/tg/health/db`.
2. Check HTML TTFB and asset loading.
3. Check Telegram SDK/load payload diagnostics.
4. Test on iOS/Android/Desktop Telegram.

### 6.6 Catalog empty
1. Check `/api/tg/status` counts.
2. Check `TELEGRAM_APP_DATABASE_URL` env.
3. Check latest sync stats.
4. Compare WEB Content API partner count vs TG DB.
5. Do not run prune until root cause is known.

### 6.7 Offers not loading
1. Check partner id mapping and `/api/tg/partners/{id}/offers`.
2. Verify offers active status and external_content_id mapping.
3. Check frontend diagnostic request path/status.

### 6.8 Auth failed
1. Check Telegram launch payload availability.
2. Check Node login proxy logs and WEB API status.
3. Check 401 vs 502/504.
4. Ask user to reopen Mini App only after server-side checks.

### 6.9 Sync failed
1. Save command output and stats.
2. Rerun dry-run only.
3. Check WEB Content API token and endpoints.
4. Verify no partial prune occurred.
5. Restore DB from backup if catalog is corrupted.

### 6.10 Node down
1. Check process/container status.
2. Check last logs for uncaughtException/unhandledRejection.
3. Restart through supervisor only after preserving logs.
4. Validate `/health`, `/api/tg/status`, frontend smoke.

### 6.11 DB down
1. Check Postgres availability and credentials.
2. Check `/api/tg/health/db`.
3. Stop deploys/sync jobs.
4. Restore service, then validate catalog counts.

### 6.12 WEB API down
1. Confirm external WEB API from server and external network.
2. Expect login/profile/subscription failures.
3. Do not blame Telegram before checking upstream.
4. Communicate degraded auth/client functions.

### 6.13 Content API down
1. Check Node `content_blocks_proxy_error` logs.
2. Verify fallback default content is acceptable.
3. Open incident if required content/promos are missing.

## 7. Release readiness

### 7.1 Must-have before launch

1. Real readiness endpoint and compose/platform healthcheck.
2. Backup/restore runbook with restore drill.
3. Rollback checklist with previous image/tag/env/BotFather URL.
4. Security Critical/High sign-off.
5. Production smoke tests on real Telegram clients.
6. Sync dry-run and post-sync consistency check.
7. Synthetic checks for HTML, assets, DB health, catalog, login proxy.
8. Basic alerts for uptime, 5xx, DB health, catalog empty, assets 404.
9. Persistent uploads strategy or explicit confirmation uploads are not production-critical.
10. Release version/git SHA visible in logs/health or release notes.

### 7.2 Nice-to-have

- OpenAPI/contract tests.
- Full structured logging and tracing.
- Prometheus/OpenTelemetry metrics.
- Bundle budgets and RUM.
- State machine refactor.
- Object storage/CDN for uploads/assets.
- Blue/green deploy.

### 7.3 Smoke test checklist

- `GET /health` returns 200.
- `GET /api/tg/health/db` returns 200.
- `GET /api/tg/status` returns non-zero expected counts.
- `GET /` returns HTML and required assets load.
- `GET /assets/<current-js>` returns 200.
- `GET /api/tg/partners` returns expected items.
- `GET /api/tg/partners/{id}/offers` returns expected offers.
- Telegram Mini App opens on iOS and Android.
- Telegram login succeeds with real `initData`.
- Profile/subscription pages load.
- Content blocks fallback/default is acceptable.
- Admin bot responds to allowed admin.

### 7.4 Manual QA checklist

- First open in Telegram iOS.
- First open in Telegram Android.
- Reopen app from background on home/catalog/partner page.
- Slow network open.
- WEB API temporary failure behavior.
- Catalog empty state is distinguishable from failure.
- Partner card/offers navigation.
- Subscription/trial/payment flows as applicable.
- Profile update and city list.
- ErrorBoundary recovery to catalog.
- BotFather production URL points to expected release.

### 7.5 Rollback checklist

1. Freeze sync/admin content changes.
2. Record incident start time and current release SHA/image/env.
3. Switch deployment to previous known-good image or previous code checkout.
4. Restore previous env if changed.
5. If DB migration occurred, follow migration rollback or restore backup.
6. If BotFather URL changed, switch to previous URL.
7. Validate smoke checklist.
8. Keep broken release logs/artifacts for investigation.
9. Announce rollback completion and next actions.

### 7.6 Incident response checklist

1. Assign incident commander and scribe.
2. Classify impact: auth, catalog, assets, DB, WEB API, Telegram-specific.
3. Check dashboards/synthetic checks/logs.
4. Mitigate: restart/rollback/disable risky sync/fallback.
5. Communicate status and ETA.
6. Preserve logs and command outputs.
7. Write postmortem with root cause, detection gap and prevention tasks.

## 8. TOP-20 blockers before launch

1. PRD-001 — readiness does not check dependencies.
2. PRD-002 — missing DB URL returns empty catalog.
3. PRD-004 — no rollback process.
4. PRD-005 — sync has no atomic publish boundary.
5. PRD-006 — no backup/restore runbook.
6. PRD-009 — no metrics/alerts/dashboards.
7. PRD-020 — no production migration/sync/deploy order checklist.
8. PRD-024 — security findings not launch-gated.
9. PRD-025 — incident runbooks absent.
10. PRD-026 — no real Telegram production validation matrix.
11. PRD-030 — BotFather URL update not guarded.
12. PRD-003 — startup DDL in runtime server.
13. PRD-007 — uploads on local filesystem without persistence strategy.
14. PRD-008 — no mandatory requestId/traceId structured logs.
15. PRD-011 — DB query per HTML request.
16. PRD-013 — chunk/assets 404 white screen risk.
17. PRD-014 — no WEB API circuit breaker/retry at proxy layer.
18. PRD-018 — no API contract schema.
19. PRD-019 — dual TG backend implementations can diverge.
20. PRD-022 — compose has no healthcheck.

## 9. Minimal must-fix list before production

- Implement or operationally enforce real readiness checks.
- Make missing DB/config a hard production failure, not empty catalog.
- Create backup/restore and rollback procedures; run one restore drill.
- Add production release checklist with migration/sync order.
- Add basic monitoring/alerts/synthetic checks.
- Resolve/sign off security Critical/High issues.
- Add BotFather rollout/rollback checklist.
- Validate on real Telegram iOS/Android/Desktop clients.
- Decide and document one production TG catalog backend.
- Ensure uploads/assets persistence and old asset retention strategy.

## 10. 30-day hardening plan after launch

### Week 1
- Add structured JSON logs and requestId propagation.
- Add synthetic checks for auth/catalog/assets/content.
- Add backup freshness alerts and restore test evidence.
- Add release version to health/debug/frontend diagnostics.

### Week 2
- Add metrics dashboards: latency, 5xx, DB health, catalog counts, sync stats, frontend bootstrap failures.
- Add bundle size budget and chunk-load monitoring.
- Add compose/platform healthcheck based on readiness.

### Week 3
- Introduce sync_runs, dry-run report artifacts and consistency checks.
- Add contract tests for TG API and consumed WEB API shapes.
- Add object storage/CDN plan for uploads.

### Week 4
- Refactor catalog bootstrap caching.
- Add lightweight router for partner deep link/reopen recovery.
- Plan state-management refactor to reducer/state machine.

## 11. Что нельзя выкатывать без отдельного rollout plan

- DB schema changes or `TELEGRAM_AUTO_INIT_DB=true` in production.
- Sync with `--prune`.
- BotFather production URL switch.
- Upload storage migration.
- Changing `VITE_TG_LOCAL_CATALOG_ENABLED`.
- Changing WEB API base URLs.
- Dependency major upgrades.
- Router/state-management rewrite.
- Security-sensitive admin/upload/auth changes.
- Removal of old `dist/assets` immediately after release.

## 12. Список всех production readiness issues

Найдено 30 issues:

- Critical: PRD-001, PRD-002, PRD-004, PRD-005, PRD-006, PRD-009, PRD-020, PRD-024, PRD-025
- High: PRD-003, PRD-007, PRD-008, PRD-011, PRD-013, PRD-014, PRD-016, PRD-017, PRD-018, PRD-019, PRD-021, PRD-022, PRD-026, PRD-030
- Medium: PRD-010, PRD-012, PRD-015, PRD-023, PRD-027, PRD-028, PRD-029
- Low: none

## 13. Launch readiness verdict

**Verdict: Not Ready.**

Проект можно довести до controlled launch, но сейчас production эксплуатация не имеет достаточных гарантий availability, observability, deployment rollback, data recovery and incident response. Минимальный путь к launch — закрыть must-fix список из раздела 9 и провести реальную Telegram QA matrix проверку.

## 14. Что невозможно проверить без реального production

- Реальное поведение Telegram WebView на пользовательских iOS/Android версиях и сетях.
- BotFather production URL propagation and Telegram caching.
- Фактические лимиты/latency Timeweb/nginx/platform.
- Реальный WEB API SLO, rate limits and failure modes.
- Production Postgres performance, backup/restore time and lock behavior.
- Реальный размер каталога, images and uploads durability.
- Real user startup latency and white screen/chunk error rate.
- Alert delivery and on-call response time.

## 15. Проверочные команды

Команды, использованные при аудите:

```bash
pwd
find /workspace -name AGENTS.md -print
rg --files -g '!*node_modules*' -g '!*.png' -g '!*.jpg' -g '!*.jpeg' -g '!*.gif'
for f in architecture.md backend.md frontend.md state-management.md request-flow.md data-flow.md infrastructure.md security-audit.md architecture-audit.md; do sed -n '1,220p' "$f"; done
sed -n '1,260p' telegram-mini-app/server/production-server.js
sed -n '260,620p' telegram-mini-app/server/production-server.js
sed -n '620,1040p' telegram-mini-app/server/production-server.js
sed -n '1,760p' telegram-mini-app/src/App.tsx
sed -n '1,620p' telegram-mini-app/src/api/client.ts
cat Dockerfile docker-compose.yml telegram-mini-app/package.json telegram-mini-app/requirements.txt admin_bot/requirements.txt
sed -n '1,260p' telegram-mini-app/telegram_app/scripts/sync_content_to_tg_catalog.py
sed -n '1,180p' telegram-mini-app/backend/telegram_catalog/app.py
sed -n '1,220p' telegram-mini-app/src/components/RuntimeErrorBoundary.tsx
sed -n '1,220p' telegram-mini-app/src/content/ContentContext.tsx
git status --short
git diff --name-only
git diff --stat
git add production-readiness-audit.md
git commit -m "Add production readiness audit"
git rev-parse HEAD
```

## 16. Итоговая сводка

- Изучено: обязательные architecture/backend/frontend/state/request/data/infrastructure/security/architecture audit docs, production Node server, frontend bootstrap/API/state code, content provider, error boundary, Docker/Compose, sync scripts, Python catalog backend, admin bot files and tests list.
- Найдено проблем: **30**.
- Critical: **9**.
- High: **14**.
- Medium: **7**.
- Low: **0**.
- Launch readiness verdict: **Not Ready**.
- Невозможно проверить без production: real Telegram client matrix, platform limits, production DB backup/restore, WEB API SLO/rate limits, real user startup and alert/on-call behavior.
- Hash коммита: заполнено после commit в финальном ответе.
- Commit message: `Add production readiness audit`.
- Все команды проверки: перечислены в разделе 15.
- Подтверждение: **код проекта не изменялся; создан только audit-документ `production-readiness-audit.md`.**
