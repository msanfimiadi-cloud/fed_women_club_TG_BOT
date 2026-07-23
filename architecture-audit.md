# Architecture Audit — Bloom Club Telegram Mini App / Admin Bot

Дата аудита: 2026-06-25.

Scope: исключительно architecture audit. Код приложения не изменялся; добавлен только этот отчёт `architecture-audit.md`.

## Методика и изученные материалы

Перед анализом были изучены обязательные документы:

- `architecture.md`
- `backend.md`
- `frontend.md`
- `state-management.md`
- `request-flow.md`
- `data-flow.md`
- `infrastructure.md`
- `security-audit.md`

После этого проведён статический обзор исходного кода Telegram Mini App frontend, Node production server, Python WSGI catalog backend, scripts, Admin Bot, Docker/deploy файлов и тестов.

Проверялись: общая архитектура, frontend architecture, backend architecture, data architecture, infrastructure architecture, maintainability, performance architecture и reliability architecture.

Severity означает архитектурный риск для production:

- **Critical** — высокий риск системной недоступности, потери/рассинхронизации критичных данных или блокировки ключевого пользовательского сценария.
- **High** — существенный риск деградации production, высокой стоимости изменений или частых пользовательских отказов.
- **Medium** — заметная поддерживаемость/надёжность/производительность, но есть обходные пути.
- **Low** — локальный архитектурный запах или улучшение, которое можно планировать позже.

---

# Findings

## ARCH-001 — Frontend root component является god-component

- **Область:** Frontend architecture / maintainability / state management.
- **Severity:** High.
- **Где найдено:** `telegram-mini-app/src/App.tsx`, компонент `App`, bootstrap, navigation, catalog/offers/profile/subscription/linking/recovery logic.
- **Описание:** Root component одновременно отвечает за Telegram bootstrap, авторизацию, восстановление состояния, глобальные данные, навигацию, каталог, partner/offers flow, trial/payment flow, profile updates, account linking, diagnostics и rendering всех страниц.
- **Почему это проблема:** В одном компоненте смешаны orchestration, domain state, UI routing и recovery. Это повышает связность и делает почти любое изменение потенциально регрессионным для startup, каталога и профиля.
- **Последствия:** Трудно покрывать тестами, трудно выделять независимые релизы, сложно анализировать race conditions между bootstrap/catalog/offers. Новым разработчикам нужно понимать весь файл перед локальным изменением.
- **Как проявится в production:** Небольшое изменение в каталоге или linking может сломать первичный запуск, восстановление после 401 или переходы между экранами.
- **Рекомендация:** Разделить `App` на application shell/router, auth bootstrap hook, catalog store/hook, partner offers hook, profile/subscription hook и diagnostics boundary. Сначала вынести pure orchestration без изменения UI.
- **Риск исправления:** High, потому что компонент содержит много взаимозависимых состояний и side effects.
- **Приоритет исправления:** P1.

## ARCH-002 — Navigation реализована как локальный enum state вместо маршрутизатора

- **Область:** Frontend architecture / navigation / recovery.
- **Severity:** Medium.
- **Где найдено:** `telegram-mini-app/src/App.tsx`, `PageId`, `setPage`, `activePage`, `selectedPartner`.
- **Описание:** Навигация хранится в `useState<PageId>`, а partner route зависит от `selectedPartner` в памяти. URL отражает только `#catalog` на старте.
- **Почему это проблема:** Экран партнёра невозможно восстановить после reload/reopen/deep link без дополнительного состояния. Telegram iOS reopen и browser history не имеют полноценной модели маршрутов.
- **Последствия:** Stale partner screen, потеря контекста при перезапуске, невозможность ссылок на партнёра/оффер, усложнение recovery logic.
- **Как проявится в production:** Пользователь открывает партнёра, Telegram WebView пересоздаётся, приложение возвращается в каталог или показывает recovery error вместо карточки.
- **Рекомендация:** Ввести lightweight router с URL state (`/catalog`, `/partners/:id`, `/profile`) и независимую загрузку partner by id. Сначала сделать совместимый слой над текущим `PageId`.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P2.

## ARCH-003 — API client смешивает identity API, TG catalog API, storage, retry и diagnostics

- **Область:** Frontend architecture / API client / maintainability.
- **Severity:** High.
- **Где найдено:** `telegram-mini-app/src/api/client.ts`.
- **Описание:** Один файл содержит нормализацию WEB/TG/same-origin base URLs, token storage, Telegram login, generic request/retry, catalog calls, profile/subscription/payment/linking calls, diagnostics types and logging.
- **Почему это проблема:** Клиент стал точкой высокой связности. Изменение retry, токена, catalog source или login diagnostics может затронуть все API flows.
- **Последствия:** Сложнее выделить контракты, моки и тесты. Нельзя безопасно независимо развивать WEB identity API и TG catalog API.
- **Как проявится в production:** Исправление одного endpoint может изменить поведение всех request paths, например retries или Authorization headers.
- **Рекомендация:** Разделить на `httpClient`, `authClient`, `webClientApi`, `tgCatalogApi`, `contentApi`, `tokenStore`, `diagnostics`. Оставить совместимые re-export функции на переходный период.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P1.

## ARCH-004 — Frontend state management не имеет единого source of truth

- **Область:** State management / data flow.
- **Severity:** High.
- **Где найдено:** `telegram-mini-app/src/App.tsx`, `AppData`, отдельные states `selectedPartner`, `partnerOffers`, `paymentRequest`, `shouldShowLinking`, catalog flags.
- **Описание:** Часть данных хранится в `data`, часть — в отдельных `useState`, часть — в `localStorage`, часть — в `window.__BLOOM_TG_CATALOG_BOOTSTRAP__`.
- **Почему это проблема:** Невозможно формально определить валидные состояния приложения. Состояния `partners loaded`, `selectedPartner`, `partnerOffers`, `bootstrap done` и `page` могут расходиться.
- **Последствия:** Race conditions, stale state, нестабильное recovery поведение, сложные guards.
- **Как проявится в production:** После retry или быстрого перехода между вкладками могут остаться устаревшие offers или diagnostic flags для другого партнёра/запроса.
- **Рекомендация:** Ввести state machine или reducer с явными состояниями `bootstrapping/authenticated/catalogLoading/partnerLoading/error`. Для server-state использовать query cache с ключами.
- **Риск исправления:** High.
- **Приоритет исправления:** P1.

## ARCH-005 — Bootstrap выполняет критические и вторичные запросы в одном orchestration flow

- **Область:** Frontend bootstrap / performance / reliability.
- **Severity:** High.
- **Где найдено:** `telegram-mini-app/src/App.tsx`, `loadAppData`.
- **Описание:** Bootstrap включает Telegram viewport, runtime check, stored token validation, login, profile/subscription, cleanup, secondary requests, linking status и conditional catalog load.
- **Почему это проблема:** Startup flow слишком широк. Ошибка/задержка в одном неключевом участке может усложнить диагностику и повлиять на perceived startup.
- **Последствия:** Waterfall запуска, трудная изоляция причин ошибок, высокая цена изменения любого secondary endpoint.
- **Как проявится в production:** При деградации WEB client endpoints пользователь видит долгий startup или частично пустой UI; диагностика показывает общую ошибку вместо независимых degraded sections.
- **Рекомендация:** Разделить minimal bootstrap (`Telegram payload -> login -> profile/subscription`) и lazy/parallel feature data (`cities`, `savings`, `verifications`, `linking`, `catalog`). Каждый feature должен иметь локальный degraded state.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P1.

## ARCH-006 — ContentProvider создаётся внутри AppShell и монтируется вокруг всех страниц, но не интегрирован с общим bootstrap/cache

- **Область:** Frontend content / state management / performance.
- **Severity:** Medium.
- **Где найдено:** `telegram-mini-app/src/content/ContentContext.tsx`, использование в `App.tsx`.
- **Описание:** Content blocks загружаются отдельным provider side effect независимо от App bootstrap, без shared retry/cache и без согласования с catalog bootstrap.
- **Почему это проблема:** Появляется параллельная подсистема server-state с отдельными правилами ошибок, загрузки и fallback.
- **Последствия:** Дублирование fetch/retry patterns, лишние запросы при remount, разные semantics для degraded state.
- **Как проявится в production:** Content API может быть недоступен, UI показывает default content без единого observability/state для startup.
- **Рекомендация:** Перевести content на общий query/cache слой или отдельный content service с TTL, retry policy и явной degraded telemetry.
- **Риск исправления:** Low/Medium.
- **Приоритет исправления:** P2.

## ARCH-007 — Node production server является монолитом с ручным роутингом и множеством ответственностей

- **Область:** Backend architecture / maintainability / routing.
- **Severity:** High.
- **Где найдено:** `telegram-mini-app/server/production-server.js`.
- **Описание:** Один файл совмещает HTTP server, routing, static serving, upload serving, DB schema init, catalog queries, bootstrap HTML injection, WEB auth proxy, WEB client proxy, Content API proxy, health/debug, logging and shutdown.
- **Почему это проблема:** Нет явных middleware boundaries, route modules, contract tests per route или shared proxy abstraction. Порядок `handleRequest` становится скрытой архитектурой.
- **Последствия:** Высокий риск regression при добавлении endpoint, сложность reuse между Node и Python backend, трудно тестировать отдельно.
- **Как проявится в production:** Изменение static fallback или `/api/*` order может случайно перехватить frontend route или API route.
- **Рекомендация:** Разделить на modules: `server`, `routes/health`, `routes/catalog`, `routes/proxyAuth`, `routes/proxyClient`, `routes/content`, `static`, `db`. Добавить route table tests.
- **Риск исправления:** Medium/High.
- **Приоритет исправления:** P1.

## ARCH-008 — Дублируются две backend реализации TG catalog API

- **Область:** Backend architecture / service boundaries / duplicated logic.
- **Severity:** High.
- **Где найдено:** Node `production-server.js` и Python `telegram-mini-app/backend/telegram_catalog/app.py`/`repository.py`/`database.py`.
- **Описание:** Public TG catalog API реализован и в Node production server, и в Python WSGI scaffold. Python дополнительно имеет admin/upload endpoints, но Docker production запускает Node.
- **Почему это проблема:** Два backend слоя имеют разные capabilities, schema management, error semantics и deployment modes. Легко получить divergent behavior.
- **Последствия:** Исправление в одном backend не попадает в другой. Документация и тесты должны учитывать два runtime, что увеличивает стоимость поддержки.
- **Как проявится в production:** Локально/в альтернативном деплое Python endpoint ведёт себя иначе, чем Docker Node production; синхронизация schema может расходиться.
- **Рекомендация:** Принять архитектурное решение: оставить один production backend для TG catalog или явно объявить Python legacy/admin-only. Вынести контракт API и schema migrations в общий слой/документ.
- **Риск исправления:** High, если Python где-то реально используется.
- **Приоритет исправления:** P1.

## ARCH-009 — Node schema initialization встроена в runtime server startup

- **Область:** Backend / infrastructure / startup safety.
- **Severity:** High.
- **Где найдено:** `production-server.js`, `schemaStatements`, `initDatabaseIfEnabled`, `start`.
- **Описание:** При `TELEGRAM_AUTO_INIT_DB=true` production server выполняет DDL во время startup.
- **Почему это проблема:** Runtime startup смешан с migrations. Ошибка прав/DDL/connection блокирует сервер, а несколько replicas могут одновременно выполнять schema init.
- **Последствия:** Непредсказуемый deployment, startup race, отсутствие контролируемого rollback plan.
- **Как проявится в production:** После включения auto-init container может не стартовать из-за DB permissions или lock; health будет недоступен.
- **Рекомендация:** Перенести DDL в отдельный migration step/CI/CD job. Runtime server должен только проверять compatibility/readiness.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P1.

## ARCH-010 — `/ready` не проверяет зависимости, а DB readiness вынесен отдельно

- **Область:** Infrastructure / health checks / reliability.
- **Severity:** Medium.
- **Где найдено:** `production-server.js`, `/ready`, `/api/tg/health/db`.
- **Описание:** `/ready` возвращает `ok` без проверки DB и upstream availability. DB health отдельный и не является readiness gate.
- **Почему это проблема:** Platform может считать сервис готовым, хотя catalog DB недоступна и каталог возвращает degraded/empty/error behavior.
- **Последствия:** Traffic направляется на частично неработающий instance.
- **Как проявится в production:** После рестарта приложение отдаёт HTML и `/ready=ok`, но `/api/tg/partners` не работает или bootstrap пустой.
- **Рекомендация:** Разделить `/live` и `/ready`: readiness должен проверять обязательные зависимости для выбранного режима (`TG_LOCAL_CATALOG_ENABLED`, DB configured, migrations compatible). Для optional upstreams — отдельный degraded status.
- **Риск исправления:** Medium из-за platform healthcheck ожиданий.
- **Приоритет исправления:** P2.

## ARCH-011 — Catalog API при не настроенной DB возвращает пустой список вместо явной ошибки

- **Область:** Backend / data architecture / reliability.
- **Severity:** High.
- **Где найдено:** `production-server.js`, `handlePartners`.
- **Описание:** Если `DATABASE_URL` отсутствует, `/api/tg/partners` возвращает `200 {items: []}`.
- **Почему это проблема:** Конфигурационная ошибка маскируется как валидный пустой каталог. Это нарушает observability и source-of-truth guarantees.
- **Последствия:** Пользователи видят пустой каталог, мониторинг может не сработать, sync/deploy ошибки неочевидны.
- **Как проявится в production:** Новый деплой без env silently показывает пустой каталог вместо fail-fast/degraded banner.
- **Рекомендация:** В production режиме возвращать 503/diagnostic и проваливать readiness, если локальный TG catalog включён. Пустой список разрешать только явно для dev/demo mode.
- **Риск исправления:** Medium, потому что может изменить текущий fallback behavior.
- **Приоритет исправления:** P1.

## ARCH-012 — Bootstrap catalog injection выполняет DB query на каждый HTML request

- **Область:** Performance architecture / bootstrap / backend.
- **Severity:** High.
- **Где найдено:** `production-server.js`, `serveFrontend`, `fetchPublicCatalogPartners`, `injectCatalogBootstrap`.
- **Описание:** Каждый запрос к frontend route читает весь public catalog из DB и вставляет его в HTML.
- **Почему это проблема:** HTML serving зависит от DB latency, payload size растёт вместе с каталогом, cacheability HTML ухудшается.
- **Последствия:** Медленный first paint, повышенная нагрузка на DB, большие HTML responses, плохое поведение при росте каталога.
- **Как проявится в production:** При большом каталоге или DB latency открытие Mini App будет медленным; CDN/platform не сможет эффективно кешировать HTML.
- **Рекомендация:** Добавить server-side catalog bootstrap cache с TTL/ETag/size limit или отдавать minimal shell и lazy-load catalog. Для critical first screen хранить compact subset.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P1.

## ARCH-013 — Нет контрактной схемы API между frontend, Node, Python и WEB backend

- **Область:** Backend/frontend/data contracts / maintainability.
- **Severity:** High.
- **Где найдено:** `src/api/types.ts`, `src/api/client.ts`, Node/Python endpoints, docs.
- **Описание:** TypeScript types описывают ожидания frontend, но нет OpenAPI/JSON Schema или generated contracts для `/api/v1`, `/api/tg`, `/api/content`.
- **Почему это проблема:** Контракты implicit и расходятся между внешним WEB backend, Node proxy, Python WSGI и frontend normalization.
- **Последствия:** Runtime parsing errors, silent empty arrays, неверные field mappings, сложность безопасного изменения endpoints.
- **Как проявится в production:** WEB API изменяет поле/shape, frontend получает пустые или некорректные данные без compile-time сигнала.
- **Рекомендация:** Ввести OpenAPI/JSON Schema для TG local API и consumed WEB endpoints, contract tests на Node/Python, runtime validation для critical responses.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P1.

## ARCH-014 — WEB → TG sync не является полноценной consistency boundary

- **Область:** Data architecture / sync / source of truth.
- **Severity:** High.
- **Где найдено:** `telegram-mini-app/telegram_app/scripts/sync_content_to_tg_catalog.py`.
- **Описание:** Sync script делает idempotent upsert, optional prune, ручные mappings и partial fetch partners/photos/offers/photos. Нет version checkpoint, transaction around remote snapshot, rollback marker или consistency window.
- **Почему это проблема:** TG DB может содержать смесь старых и новых данных, если Content API изменится во время sync или если sync упадёт после части операций.
- **Последствия:** Stale/partial catalog, несогласованные partner/offers/photos, отсутствие уверенности что TG DB соответствует WEB source-of-truth.
- **Как проявится в production:** Партнёр обновился без офферов, удалённый offer остался active без prune, фото обновились частично.
- **Рекомендация:** Ввести sync runs table, source snapshot/version, transactional staging tables, atomic publish marker, mandatory stats/alerts. Разделить demo/manual records через explicit ownership policy.
- **Риск исправления:** High.
- **Приоритет исправления:** P1.

## ARCH-015 — Demo/manual records и WEB records сосуществуют без строгой ownership model

- **Область:** Data architecture / data ownership.
- **Severity:** Medium.
- **Где найдено:** `sync_content_to_tg_catalog.py`, `external_content_id`, prune logic, seed scripts.
- **Описание:** Records с `external_content_id` считаются WEB-owned, records без него — manual/demo. Но это правило не закреплено schema-level и может быть нарушено руками.
- **Почему это проблема:** Непонятно, кто владелец данных, какие rows можно prune/update, как мигрировать manual в WEB-owned.
- **Последствия:** Stale demo data в production, collision external IDs, ручные записи могут маскировать sync проблемы.
- **Как проявится в production:** Пользователь видит старых demo-партнёров рядом с актуальными WEB партнёрами; prune не удаляет manual stale data.
- **Рекомендация:** Добавить `source_system`, `source_version`, `managed_by`, `last_synced_at`, запрет demo seeds в production и отчёт по unmanaged active rows.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P2.

## ARCH-016 — Prune является optional, поэтому stale data может жить бесконечно

- **Область:** Data architecture / consistency / stale data.
- **Severity:** High.
- **Где найдено:** `sync_content_to_tg_catalog.py`, `--prune`.
- **Описание:** По умолчанию sync не деактивирует records, исчезнувшие из WEB Content API.
- **Почему это проблема:** Default режим не поддерживает соответствие TG catalog внешнему source-of-truth.
- **Последствия:** Удалённые/неактивные партнёры и офферы остаются видимыми, если не пришло явное inactive поле или prune не запущен.
- **Как проявится в production:** После удаления партнёра в WEB CMS он продолжает отображаться в Telegram каталоге.
- **Рекомендация:** Сделать prune частью production sync policy с dry-run preview, allowlist manual records и alert на большое количество prune operations.
- **Риск исправления:** High, можно случайно скрыть реальные manual records.
- **Приоритет исправления:** P1.

## ARCH-017 — Нет rollback strategy для TG catalog sync

- **Область:** Data architecture / reliability / rollback.
- **Severity:** High.
- **Где найдено:** sync scripts and docs; отсутствуют snapshot/backup/publish controls.
- **Описание:** Sync пишет directly в live TG tables и не создаёт rollback snapshot или previous published version.
- **Почему это проблема:** Ошибка mapping или Content API response сразу портит production catalog.
- **Последствия:** Нельзя быстро откатиться к предыдущему каталогу без DB backup.
- **Как проявится в production:** Неверный sync массово меняет цены/активность/фото; приложение сразу показывает ошибочные данные.
- **Рекомендация:** Ввести staging tables, validation gate, atomic promote, backup of previous run, `sync_run_id` on rows и rollback command.
- **Риск исправления:** High.
- **Приоритет исправления:** P1.

## ARCH-018 — Proxy layer не имеет circuit breaker/cache policy для внешних WEB APIs

- **Область:** Backend proxy / reliability / performance.
- **Severity:** High.
- **Где найдено:** `production-server.js`, `handleTelegramLoginProxy`, `handleClientApiProxy`, `handleContentBlocksProxy`.
- **Описание:** Node proxies external WEB APIs with timeout, but no circuit breaker, backoff, request coalescing, cache for public content, or upstream health state.
- **Почему это проблема:** При деградации WEB API каждый пользовательский запрос продолжает бить upstream до timeout, увеличивая latency and load.
- **Последствия:** Cascading failure, медленные страницы, лог-шторм.
- **Как проявится в production:** WEB API тормозит — Mini App массово ждёт 20–30 секунд, Node держит sockets, external API получает лавину retries.
- **Рекомендация:** Добавить per-upstream circuit breaker, short fail-fast after threshold, cache/stale-while-revalidate для public content blocks, metrics.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P1.

## ARCH-019 — Retry strategy слишком примитивна и не учитывает jitter/backoff/idempotency beyond GET

- **Область:** Frontend reliability / API client.
- **Severity:** Medium.
- **Где найдено:** `src/api/client.ts`, `GET_RETRY_ATTEMPTS`, `TELEGRAM_LOGIN_RETRY_ATTEMPTS`, `request`.
- **Описание:** GET имеет один retry без backoff/jitter; non-GET generally не retry. Login has special in-flight logic but no broader resilience policy.
- **Почему это проблема:** При transient outages один немедленный retry часто не помогает, а при массовом открытии Mini App синхронные retries усиливают нагрузку.
- **Последствия:** Низкая устойчивость к кратким сбоям, thundering herd.
- **Как проявится в production:** После краткого сетевого сбоя пользователи видят ошибки, хотя повтор через 1–2 секунды мог бы сработать.
- **Рекомендация:** Central retry policy with exponential backoff + jitter, endpoint-specific idempotency, cancellation on navigation, and budget limits.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P2.

## ARCH-020 — Partial failures не имеют единой деградированной модели UI

- **Область:** Frontend reliability / diagnostics.
- **Severity:** Medium.
- **Где найдено:** `App.tsx`, `ContentContext.tsx`, pages.
- **Описание:** Secondary requests use `Promise.allSettled`, catalog has diagnostics, content has local fallback text, offers have separate statuses. Нет единого понятия degraded feature state.
- **Почему это проблема:** UI and telemetry cannot answer consistently which features are unavailable and why.
- **Последствия:** Fragmented diagnostics, inconsistent retry buttons, сложно настроить alerting by feature.
- **Как проявится в production:** Savings недоступен, content fallback включён, catalog stale — пользователь видит разные UX patterns без общего статуса.
- **Рекомендация:** Ввести feature health/degraded registry in frontend state and expose consistent components for unavailable sections.
- **Риск исправления:** Low/Medium.
- **Приоритет исправления:** P2.

## ARCH-021 — Dynamic import timeout 3 секунды может быть слишком агрессивным для Telegram WebView

- **Область:** Frontend bootstrap / performance / reliability.
- **Severity:** Medium.
- **Где найдено:** `src/main.tsx`, `MODULE_IMPORT_TIMEOUT_MS = 3_000`.
- **Описание:** Entry point показывает startup error panel if App dynamic import exceeds 3 seconds.
- **Почему это проблема:** На медленных сетях, старых Android/iOS WebView or cold cache загрузка JS chunk может занять больше 3 секунд без реальной ошибки.
- **Последствия:** False-positive startup failure, пользователь видит ошибку вместо continued loading.
- **Как проявится в production:** На мобильном интернете Telegram WebView показывает «Не удалось загрузить модуль приложения», хотя bundle eventually loads.
- **Рекомендация:** Увеличить threshold, разделить warning watchdog и hard failure, учитывать network information, добавить retry import/reload UX.
- **Риск исправления:** Low.
- **Приоритет исправления:** P2.

## ARCH-022 — Bundle/chunk architecture не выражена явно

- **Область:** Frontend performance / maintainability.
- **Severity:** Medium.
- **Где найдено:** `src/main.tsx`, `vite.config.ts`, absence of route-level code splitting beyond dynamic App import.
- **Описание:** App imports all pages/components through one root module. Dynamic import separates only entry vs App/boundary, not route features.
- **Почему это проблема:** First usable bundle includes features not needed for home startup: catalog, partner, profile, subscription, diagnostics.
- **Последствия:** Larger startup JS, slower Telegram open, less cache granularity.
- **Как проявится в production:** Cold start in Telegram takes longer, especially on mobile networks.
- **Рекомендация:** Introduce route-level lazy loading for heavy pages and diagnostics panel. Keep critical home/auth shell small.
- **Риск исправления:** Medium due to startup/recovery interactions.
- **Приоритет исправления:** P2.

## ARCH-023 — Image loading strategy не централизована

- **Область:** Performance architecture / frontend.
- **Severity:** Medium.
- **Где найдено:** `HomePage.tsx`, `CatalogPage.tsx`, `PartnerPage.tsx`, `partnerDisplay` utils.
- **Описание:** Images are rendered directly from API fields without a shared image component controlling lazy loading, dimensions, placeholder, allowed origins, CDN resizing or fallback.
- **Почему это проблема:** Layout shifts, unnecessary bytes, inconsistent broken-image behavior.
- **Последствия:** Slower catalog/home rendering and poorer mobile UX.
- **Как проявится в production:** Large CMS photos block rendering; broken external image URLs produce inconsistent UI.
- **Рекомендация:** Add `AppImage` component with `loading="lazy"`, dimensions/aspect ratio, fallback, source normalization, and future CDN resize support.
- **Риск исправления:** Low/Medium.
- **Приоритет исправления:** P3.

## ARCH-024 — Static asset responses lack cache strategy in Node

- **Область:** Backend performance / static assets / infrastructure.
- **Severity:** Medium.
- **Где найдено:** `production-server.js`, `serveAsset`, `serveUpload`, `serveFrontend`.
- **Описание:** Assets are served with content type only, no immutable cache headers for hashed Vite assets and no distinct policy for uploads/frontend HTML.
- **Почему это проблема:** Browser/platform caches cannot efficiently reuse immutable bundles; HTML and uploads need different cache semantics.
- **Последствия:** More repeated network requests, slower opens, greater bandwidth.
- **Как проявится в production:** Telegram WebView cold/warm opens still revalidate or reload assets unnecessarily.
- **Рекомендация:** Add `Cache-Control: public, max-age=31536000, immutable` for hashed `/assets/*`, `no-cache` for HTML, explicit policy for `/uploads/*`.
- **Риск исправления:** Low/Medium.
- **Приоритет исправления:** P2.

## ARCH-025 — Production server has no framework-level middleware/testable route abstraction

- **Область:** Backend maintainability / testing.
- **Severity:** Medium.
- **Где найдено:** `production-server.js`, `handleRequest` and helpers.
- **Описание:** Native HTTP is used directly. Helpers are not exported; route tests require process/server integration rather than unit tests.
- **Почему это проблема:** Simple now, but route matrix is already complex. Lack of abstractions increases accidental coupling.
- **Последствия:** Hard to test method guards, headers, proxy target building and error paths independently.
- **Как проявится в production:** Edge-case regressions in HEAD/OPTIONS/static/API fallback may pass unnoticed.
- **Рекомендация:** Either introduce a minimal internal router abstraction or a small framework, and export pure route handlers for tests.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P2.

## ARCH-026 — Admin bot is another god-component/process with large conversational logic

- **Область:** Backend/admin bot maintainability.
- **Severity:** Medium.
- **Где найдено:** `admin_bot/admin_bot/bot.py`.
- **Описание:** Admin bot file is very large and likely mixes handlers, state transitions, validation, API calls and presentation.
- **Почему это проблема:** Telegram admin workflows become hard to reason about and risky to change. State machine complexity is hidden in handlers.
- **Последствия:** Bugs in one admin flow can affect unrelated flows; hard manual QA.
- **Как проявится в production:** Admin changes for banners/offers accidentally break partner photo or giveaway flows.
- **Рекомендация:** Split by domain (`partners`, `offers`, `photos`, `home_blocks`, `giveaways`), extract FSM definitions and API service layer tests.
- **Риск исправления:** Medium/High.
- **Приоритет исправления:** P2.

## ARCH-027 — Infrastructure ownership between Docker, platform proxy and systemd is under-specified

- **Область:** Infrastructure architecture / deployment flow.
- **Severity:** Medium.
- **Где найдено:** `Dockerfile`, `docker-compose.yml`, `infrastructure.md`, `admin_bot/bloomclub-admin-bot.service.example`.
- **Описание:** Docker covers Mini App Node server; systemd example exists only for admin bot; Nginx/platform proxy is inferred, not committed.
- **Почему это проблема:** Critical production behavior (TLS, headers, health checks, route preservation, body size, timeouts) lives outside repo.
- **Последствия:** Environment drift and hard-to-reproduce production issues.
- **Как проявится в production:** A platform proxy timeout/header/caching change breaks Mini App while repo tests pass.
- **Рекомендация:** Document and version production ingress contract: expected headers, timeouts, healthcheck path, body limits, cache policy, TLS and WebView requirements.
- **Риск исправления:** Low.
- **Приоритет исправления:** P2.

## ARCH-028 — Environment variables are scattered and not typed/validated centrally

- **Область:** Infrastructure / configuration / maintainability.
- **Severity:** Medium.
- **Где найдено:** Node constants, frontend `import.meta.env`, Python settings/config, Docker compose, scripts.
- **Описание:** Config is read in multiple languages/files with different defaults and validation levels.
- **Почему это проблема:** Same deployment may appear healthy while feature flags or API bases disagree between build-time frontend and runtime backend.
- **Последствия:** Misconfiguration, hidden fallbacks to bloomclub.ru, empty catalog, wrong proxy behavior.
- **Как проявится в production:** Docker built with one `VITE_*` but runtime env points elsewhere; frontend calls unexpected origin/API.
- **Рекомендация:** Create config inventory and typed validation per runtime. Print safe effective config at startup/build and fail fast for production-required vars.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P2.

## ARCH-029 — Versioned routes are accepted by pattern but not tied to release artifacts

- **Область:** Infrastructure / frontend routing / deployment.
- **Severity:** Low/Medium.
- **Где найдено:** `production-server.js`, `isVersionedFrontendRoute`.
- **Описание:** Server accepts `/app-v*` and other versioned-looking routes, but all serve the same current `dist/index.html`.
- **Почему это проблема:** Route versioning suggests rollback/parallel versions, but implementation is alias-only.
- **Последствия:** False sense of safe rollout. Old Telegram links do not pin old assets.
- **Как проявится в production:** `/app-v1` opens current app, not v1; rollback by URL impossible.
- **Рекомендация:** Either remove version semantics from route names or implement real versioned artifact serving with retention and fallback policy.
- **Риск исправления:** Low/Medium.
- **Приоритет исправления:** P3.

## ARCH-030 — Health/status/debug endpoints mix operational and public concerns

- **Область:** Backend diagnostics / infrastructure / security-adjacent architecture.
- **Severity:** Medium.
- **Где найдено:** `production-server.js`, `/health`, `/ready`, `/api/tg/status`, `/debug/runtime-port`.
- **Описание:** Public server exposes operational endpoints with counts/runtime details, while readiness is minimal.
- **Почему это проблема:** Operational diagnostics should be designed around observability/monitoring boundaries. Public exposure constrains what can be shown and may be incomplete for operators.
- **Последствия:** Either too much public info or not enough production diagnostics; no authenticated admin diagnostics route.
- **Как проявится в production:** Operators use public endpoints manually; attackers/users can also call them; platform health uses weak readiness.
- **Рекомендация:** Define `/live`, `/ready`, `/metrics`/internal diagnostics behind ingress auth/IP allowlist. Keep public health minimal.
- **Риск исправления:** Medium because platform health paths may depend on current behavior.
- **Приоритет исправления:** P2.

## ARCH-031 — Logs are unstructured/inconsistent across frontend, Node, Python scripts and admin bot

- **Область:** Observability / reliability.
- **Severity:** Medium.
- **Где найдено:** `App.tsx`, `client.ts`, `production-server.js`, Python scripts/admin bot.
- **Описание:** There are many `console.info`/`console.warn` events and Python prints/logs, but no shared schema, correlation id propagation or metrics.
- **Почему это проблема:** During incident, difficult to trace one Telegram user/session from frontend startup to Node proxy to WEB API and sync.
- **Последствия:** Longer MTTR, hard production diagnostics.
- **Как проявится в production:** Login or catalog incident requires manual log grep without consistent request/session IDs.
- **Рекомендация:** Define structured log schema, request IDs, user-safe session correlation, proxy request id propagation and key metrics counters.
- **Риск исправления:** Low/Medium.
- **Приоритет исправления:** P2.

## ARCH-032 — Catalog partner/offers flow depends on numeric local IDs, while WEB source uses external_content_id

- **Область:** Data/frontend/backend boundary.
- **Severity:** High.
- **Где найдено:** `App.tsx`, `resolveNumericPartnerId`, `getPartnerOffersPath`, TG DB `external_content_id`.
- **Описание:** Frontend loads offers by local numeric `partner.id`; WEB sync tracks source identity in `external_content_id`.
- **Почему это проблема:** Local IDs are environment-specific and not stable across DB rebuilds. Deep links/bookmarks and diagnostics cannot rely on source IDs.
- **Последствия:** Hard migration/rollback; stale selected partner state after re-sync/reseed; impossible stable public URLs by WEB CMS id.
- **Как проявится в production:** After DB restore/reseed partner local id changes; old link/state opens wrong/missing offers.
- **Рекомендация:** Expose and route by stable `external_content_id` or slug where possible; keep local id internal. Add lookup endpoints by external id/slug.
- **Риск исправления:** High due to API/URL/frontend changes.
- **Приоритет исправления:** P1.

## ARCH-033 — Python sync uses manual SQL construction patterns that complicate portability and safety

- **Область:** Data scripts / maintainability.
- **Severity:** Medium.
- **Где найдено:** `sync_content_to_tg_catalog.py`, `upsert`, `ensure_sync_schema`, prune queries.
- **Описание:** Script dynamically builds column lists, placeholder lists and table names across SQLite/PostgreSQL compatibility layer.
- **Почему это проблема:** Although current table/column names are internal, portability and migration safety are fragile. Behavior differs between SQLite and PostgreSQL capabilities.
- **Последствия:** Future schema changes can silently break sync or behave differently by database.
- **Как проявится в production:** Adding a new nullable field or table column causes sync failures only in production DB flavor.
- **Рекомендация:** Move sync persistence to repository layer with explicit statements per entity and tests against PostgreSQL. Use migrations rather than ad-hoc `ALTER`.
- **Риск исправления:** Medium.
- **Приоритет исправления:** P2.

## ARCH-034 — Frontend recovery and diagnostics are user-visible in production without a feature gate

- **Область:** Frontend diagnostics / UX / reliability.
- **Severity:** Low/Medium.
- **Где найдено:** `App.tsx`, startup diagnostics button/panel, `main.tsx` early error panel.
- **Описание:** Startup diagnostics UI is always available to users.
- **Почему это проблема:** Diagnostics are useful, but production UX and support flows should be controlled. Internal traces can confuse users and expand UI surface.
- **Последствия:** Users may see implementation details and send inconsistent screenshots; no support-mode gating.
- **Как проявится в production:** Every user can open JSON startup trace from normal UI.
- **Рекомендация:** Gate diagnostics by query param, support mode, dev flag or long press; keep sanitized error IDs visible by default.
- **Риск исправления:** Low.
- **Приоритет исправления:** P3.

## ARCH-035 — Content blocks fallback hides upstream failures by returning empty array from Node

- **Область:** Backend content proxy / reliability / stale state.
- **Severity:** Medium.
- **Где найдено:** `production-server.js`, `handleContentBlocksProxy`, `contentBlocksFallbackResponse`.
- **Описание:** On Content API proxy error Node returns `200 []` fallback.
- **Почему это проблема:** Upstream outage is indistinguishable from legitimate empty content unless logs are checked.
- **Последствия:** Silent degradation, no client-visible retry status, weak monitoring.
- **Как проявится в production:** Content API down; home blocks disappear/default without API error to frontend.
- **Рекомендация:** Return 503 with stale cache fallback metadata, or serve stale cached content with `X-Degraded: true`; monitor fallback count.
- **Риск исправления:** Medium due to current frontend fallback expectation.
- **Приоритет исправления:** P2.

---

# Consolidated lists

## 1. Список всех найденных архитектурных проблем

1. ARCH-001 — Frontend root component является god-component — High.
2. ARCH-002 — Navigation реализована как локальный enum state вместо маршрутизатора — Medium.
3. ARCH-003 — API client смешивает identity API, TG catalog API, storage, retry и diagnostics — High.
4. ARCH-004 — Frontend state management не имеет единого source of truth — High.
5. ARCH-005 — Bootstrap выполняет критические и вторичные запросы в одном orchestration flow — High.
6. ARCH-006 — ContentProvider не интегрирован с общим bootstrap/cache — Medium.
7. ARCH-007 — Node production server является монолитом с ручным роутингом — High.
8. ARCH-008 — Дублируются две backend реализации TG catalog API — High.
9. ARCH-009 — Node schema initialization встроена в runtime server startup — High.
10. ARCH-010 — `/ready` не проверяет зависимости — Medium.
11. ARCH-011 — Catalog API при не настроенной DB возвращает пустой список вместо явной ошибки — High.
12. ARCH-012 — Bootstrap catalog injection выполняет DB query на каждый HTML request — High.
13. ARCH-013 — Нет контрактной схемы API между frontend, Node, Python и WEB backend — High.
14. ARCH-014 — WEB → TG sync не является полноценной consistency boundary — High.
15. ARCH-015 — Demo/manual records и WEB records сосуществуют без строгой ownership model — Medium.
16. ARCH-016 — Prune является optional, поэтому stale data может жить бесконечно — High.
17. ARCH-017 — Нет rollback strategy для TG catalog sync — High.
18. ARCH-018 — Proxy layer не имеет circuit breaker/cache policy для внешних WEB APIs — High.
19. ARCH-019 — Retry strategy слишком примитивна — Medium.
20. ARCH-020 — Partial failures не имеют единой деградированной модели UI — Medium.
21. ARCH-021 — Dynamic import timeout 3 секунды может быть слишком агрессивным — Medium.
22. ARCH-022 — Bundle/chunk architecture не выражена явно — Medium.
23. ARCH-023 — Image loading strategy не централизована — Medium.
24. ARCH-024 — Static asset responses lack cache strategy in Node — Medium.
25. ARCH-025 — Production server has no framework-level middleware/testable route abstraction — Medium.
26. ARCH-026 — Admin bot is another god-component/process — Medium.
27. ARCH-027 — Infrastructure ownership between Docker, platform proxy and systemd is under-specified — Medium.
28. ARCH-028 — Environment variables are scattered and not typed/validated centrally — Medium.
29. ARCH-029 — Versioned routes are accepted by pattern but not tied to release artifacts — Low.
30. ARCH-030 — Health/status/debug endpoints mix operational and public concerns — Medium.
31. ARCH-031 — Logs are unstructured/inconsistent — Medium.
32. ARCH-032 — Catalog partner/offers flow depends on numeric local IDs — High.
33. ARCH-033 — Python sync uses manual SQL construction patterns — Medium.
34. ARCH-034 — Frontend recovery and diagnostics are user-visible without feature gate — Low.
35. ARCH-035 — Content blocks fallback hides upstream failures — Medium.

## 2. TOP-20 по важности

1. ARCH-014 — WEB → TG sync consistency boundary.
2. ARCH-017 — Rollback strategy for TG catalog sync.
3. ARCH-011 — Empty catalog on missing DB config.
4. ARCH-012 — DB query and full catalog injection per HTML request.
5. ARCH-032 — Local numeric IDs as frontend/API identity.
6. ARCH-007 — Monolithic Node production server.
7. ARCH-001 — Frontend god-component.
8. ARCH-004 — No frontend source of truth/state model.
9. ARCH-013 — Missing API contracts.
10. ARCH-008 — Duplicate TG catalog backends.
11. ARCH-016 — Optional prune and stale data.
12. ARCH-018 — No circuit breaker/cache around WEB APIs.
13. ARCH-009 — Runtime DDL during server startup.
14. ARCH-003 — Overloaded frontend API client.
15. ARCH-005 — Overloaded bootstrap flow.
16. ARCH-010 — Weak readiness semantics.
17. ARCH-035 — Content proxy hides upstream failures.
18. ARCH-027 — Under-specified production proxy/infrastructure contract.
19. ARCH-028 — Scattered config validation.
20. ARCH-024 — Missing static asset cache strategy.

## 3. Что исправлять первым

1. Production safety/data correctness: ARCH-011, ARCH-014, ARCH-016, ARCH-017, ARCH-032.
2. Startup/performance risks: ARCH-012, ARCH-010, ARCH-024.
3. Maintainability blockers for safe work: ARCH-007, ARCH-001, ARCH-003, ARCH-013.
4. External dependency resilience: ARCH-018, ARCH-035.

## 4. Что можно отложить

- ARCH-023 — unified image component, если текущие изображения небольшие.
- ARCH-029 — real versioned route artifacts, если versioned links не используются как rollback mechanism.
- ARCH-034 — diagnostics feature gate, если текущий support process relies on visible diagnostics.
- ARCH-026 — admin bot decomposition, если ближайшие изменения admin bot ограничены.
- ARCH-022 — route-level code splitting, пока bundle size не подтверждён production metrics.

## 5. Что нельзя исправлять одновременно

- **ARCH-001/ARCH-004 frontend state refactor** нельзя объединять с **ARCH-002 navigation/router rewrite**: слишком высокий риск сломать recovery and partner flow.
- **ARCH-008 backend consolidation** нельзя делать одновременно с **ARCH-014/ARCH-017 sync architecture**: сначала закрепить data contract and migration path.
- **ARCH-011 DB missing behavior** нельзя менять одновременно с **ARCH-010 readiness path** без rollout plan: platform health may route traffic differently.
- **ARCH-032 identity model change** нельзя объединять с **ARCH-016 prune policy**: можно потерять связь old local IDs to WEB IDs.
- **ARCH-018 circuit breaker** нельзя внедрять одновременно с large frontend retry changes **ARCH-019**: сложно отличить эффект client/server retry policy.

## 6. Какие изменения требуют отдельного PR

- API contract introduction for TG/WEB consumed endpoints (ARCH-013).
- Node server modularization/router extraction (ARCH-007/ARCH-025).
- Frontend `App.tsx` decomposition and state model/reducer (ARCH-001/ARCH-004/ARCH-005).
- Sync staging/versioned publish/rollback architecture (ARCH-014/ARCH-017).
- Data identity migration from local id to external id/slug (ARCH-032).
- Backend consolidation decision/removal or demotion of Python WSGI runtime (ARCH-008).
- Readiness/health semantics and platform healthcheck changes (ARCH-010/ARCH-030).
- Cache strategy for assets/bootstrap/content (ARCH-012/ARCH-024/ARCH-035).

## 7. Какие изменения требуют manual QA

- Telegram startup and login on iOS/Android/Desktop after any changes to ARCH-001/ARCH-005/ARCH-021.
- Catalog open, retry, partner details, offers, back navigation after ARCH-002/ARCH-032.
- Trial activation, payment request and subscription screen after App decomposition.
- Content home blocks and fallback behavior after ARCH-006/ARCH-035.
- Admin bot flows after ARCH-026.
- Production deployment health/restart after ARCH-009/ARCH-010/ARCH-027.
- Sync/prune/rollback after ARCH-014/ARCH-016/ARCH-017.

## 8. Какие изменения требуют production rollout plan

- Any DB/schema/migration or sync publish changes (ARCH-009, ARCH-014, ARCH-016, ARCH-017, ARCH-032).
- Readiness/healthcheck behavior changes that can affect platform routing (ARCH-010, ARCH-030).
- Bootstrap catalog cache/injection strategy (ARCH-012).
- Circuit breaker/fail-fast for WEB APIs (ARCH-018).
- Static/cache headers (ARCH-024), because stale assets can break clients if headers are wrong.
- Backend consolidation/removal of Python or Node catalog responsibilities (ARCH-008).

## 9. Roadmap рефакторинга на 4 этапа

### Этап 1 — Stabilize production safety and observability

- Define required production envs and fail-fast rules for TG catalog mode.
- Split `/live` vs `/ready`; make DB readiness explicit.
- Stop masking missing DB as empty catalog in production.
- Add structured logs/request IDs for Node proxies and catalog routes.
- Add clear content proxy degraded semantics.

### Этап 2 — Data consistency and catalog ownership

- Document and implement `source_system/source_version/last_synced_at/sync_run_id`.
- Add sync run table and dry-run validation reports.
- Introduce staging tables and atomic publish for WEB → TG sync.
- Add rollback command/process.
- Decide production prune policy with manual records allowlist.

### Этап 3 — Contract and service boundary cleanup

- Create OpenAPI/JSON Schema for `/api/tg/*` and consumed WEB endpoints.
- Add contract tests for Node and Python or retire one implementation.
- Modularize Node server into route/proxy/static/db modules.
- Extract frontend API clients into auth/web/tg/content/token modules.
- Add config validation per runtime.

### Этап 4 — Frontend state, navigation and performance

- Introduce application reducer/state machine or query cache for server-state.
- Split `App.tsx` into bootstrap, router, catalog/offers/profile feature hooks.
- Move to URL-addressable catalog/partner navigation with stable ids/slugs.
- Add route-level code splitting and tune startup watchdogs.
- Centralize image component and cache/static asset policy.

---

# Итог аудита

- **Что изучено:** обязательные документы `architecture.md`, `backend.md`, `frontend.md`, `state-management.md`, `request-flow.md`, `data-flow.md`, `infrastructure.md`, `security-audit.md`; frontend `telegram-mini-app/src`; Node server `telegram-mini-app/server/production-server.js`; Python WSGI catalog backend; sync scripts; admin bot; Docker/compose/systemd files; package/test structure.
- **Сколько проблем найдено:** 35.
- **Critical / High / Medium / Low:** Critical — 0; High — 15; Medium — 18; Low — 2.
- **Что невозможно проверить без production:** реальные platform/Nginx proxy headers/timeouts/body limits; актуальные systemd units if any; production DB schema/data volume/cardinality; WEB API availability/latency/rate limits/contracts; Telegram iOS/Android reopen behavior on real devices; actual sync schedule and operational rollback process; production log aggregation/metrics/alerts; CDN/cache behavior.
- **Hash коммита:** невозможно заранее зафиксировать собственный commit hash внутри файла без изменения содержимого и, следовательно, hash; фактический hash commit указан в итоговом ответе после `git rev-parse HEAD`.
- **Commit message:** `docs: add architecture audit`.
- **Все команды проверки:** `find /workspace -path '*/AGENTS.md' -print -exec sh -c 'echo --- $1; cat "$1"' sh {} \;`; `sed -n ...` для обязательных документов и ключевых source files; `rg --files`; `wc -l`; `git diff --stat`; `git diff --name-only`; `git status --short`; `git add architecture-audit.md`; `git commit -m "docs: add architecture audit"`; `git rev-parse HEAD`.
- **Подтверждение, что код проекта не изменялся:** изменён только новый документ `architecture-audit.md`; исходный код приложения не редактировался.
