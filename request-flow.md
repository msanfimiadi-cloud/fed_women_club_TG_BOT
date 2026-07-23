# Жизненный цикл HTTP-запросов Bloom Telegram Mini App

Документ описывает только найденные HTTP-запросы приложения и их жизненный цикл. Архитектура и обзор файлов намеренно не повторяются. Если поведение внешнего WEB/Content API не реализовано в репозитории, это явно отмечено как неизвестное.

## Границы анализа

Изучены frontend Telegram Mini App, Node production server, Python WSGI TG API, admin Telegram bot, Content API client, proxy-поведение, uploads, health/diagnostics и тесты как подтверждение контрактов. Существующий код не изменялся; добавлен только этот документ.

## Общие правила frontend HTTP-клиента

### WEB/TG client (`telegram-mini-app/src/api/client.ts`)

- Базовый WEB API по умолчанию: `https://bloomclub.ru/api/v1`.
- Telegram login всегда идёт same-origin на `/api/v1/auth/telegram-miniapp-login`.
- GET client API (`/clients/...`) в frontend превращается в same-origin `/api/v1/clients/...` и проходит через Node proxy.
- Часть write-запросов (`PATCH /clients/me`, `POST /clients/me/...`) идёт напрямую на WEB API base, если `VITE_API_BASE_URL` абсолютный.
- TG local catalog включается только при `VITE_TG_LOCAL_CATALOG_ENABLED === "true"`; тогда catalog/offers/verifications/savings идут в `/api/tg/*`.
- Timeout обычных API-запросов: 30 секунд; catalog: 30 секунд; Telegram login: 30 секунд.
- Authorization: если в `localStorage` есть `bloom_club_tma_auth`, обычный `request()` и catalog GET добавляют `Authorization: Bearer <token>`.
- `request()` retry есть только для GET при `retry: true`: всего 2 попытки (1 retry) только для `NetworkError`, `TimeoutError`, `ApiError` со статусом 0/502/503/504.
- `loginWithTelegram()` также имеет 1 retry для network/timeout/502/503/504 и дедупликацию через module-level `telegramLoginInFlight`.
- HTTP 401/403/404/500 в универсальном `requestAttempt()` становятся `ApiError(status, detail)`. Специальная обработка есть не везде и описана у конкретных запросов.
- AbortController используется как механизм timeout; отдельной ручной отмены пользовательских запросов в репозитории не найдено.
- Diagnostics: `console.info`/`console.error` события `api_request_*`, `catalog_fetch_*`, `telegram_login_*`, `content_request_*`, startup trace.

### Content client (`telegram-mini-app/src/content/clientContentApi.ts`)

- Только GET.
- `/blocks?...` всегда same-origin `/api/content/blocks?...` и проходит через Node proxy.
- Остальные Content endpoints строятся от `VITE_CONTENT_API_BASE_URL` / `https://bloomclub.ru/api/content`, но frontend-код в репозитории вызывает только `/blocks?...`.
- Timeout: 20 секунд.
- Authorization не добавляется.
- Любая ошибка `getContentBlocks()`/`getHomeBlocks()` логируется и превращается в fallback `[]`.

### Admin bot HTTP client (`admin_bot/admin_bot/web_api.py`)

- Все admin-запросы идут через `httpx.AsyncClient(timeout=30)`.
- Headers на все запросы: `Authorization: Bearer <TELEGRAM_ADMIN_API_TOKEN>` и `X-Telegram-Admin-Token: <TELEGRAM_ADMIN_API_TOKEN>`.
- Retry не реализован.
- Network/timeout/любой `httpx.HTTPError` превращается в `WebApiError("WEB API недоступен. Попробуйте позже.")`.
- HTTP status `>=400` превращается в `WebApiError("WEB API вернул ошибку <status>: <detail>")`.
- Некорректный JSON превращается в `WebApiError("WEB API вернул некорректный JSON.")`.

## Frontend bootstrap и основные запросы

### 1. `POST /api/v1/auth/telegram-miniapp-login`

**Кто вызывает:** React `App`, функция `loadAppData()`, вложенная `loginWithTelegramPayload()`.

**Файл/функция:** `telegram-mini-app/src/App.tsx` → `loginWithTelegram()` из `telegram-mini-app/src/api/client.ts` → `loginWithTelegramAttempt()`.

**Когда:** при первом запуске, ручном retry bootstrap, либо после 401 на stored-token profile/subscription.

**Условия:** есть Telegram launch payload. Если payload пустой, fetch не начинается, создаётся diagnostic `telegram_login_prefetch`.

**Параметры/body:** JSON `{ "init_data": telegramLaunchPayload }`.

**Headers:** `Accept: application/json`, `Content-Type: application/json`.

**Authorization:** frontend не отправляет Bearer для login.

**URL:** browser same-origin `/api/v1/auth/telegram-miniapp-login`.

**Proxy:** да. Node production server принимает same-origin path и проксирует в `https://bloomclub.ru/api/v1/auth/telegram-miniapp-login`.

**Кто принимает:** Node `handleTelegramLoginProxy()`; upstream WEB API принимает внешний login endpoint. Реализация WEB API в репозитории отсутствует.

**Backend внутри Node:** проверяет метод POST, читает body с лимитом 1 MiB, ставит AbortController на 30 секунд, проксирует body как есть. Forward headers: `content-type: application/json`, `accept: application/json`, `user-agent` из исходного запроса или service UA. Ответ upstream прокидывается с content-type/cache-control/x-request-id.

**Проверки:** method POST; body size; upstream timeout/network; WEB API, предположительно, валидирует Telegram init data, но деталей в репозитории нет.

**Данные/таблицы:** Node DB не читает. Таблицы WEB API неизвестны.

**Возврат:** JSON `AuthResponse`; frontend ищет `access_token` или `token`, сохраняет в localStorage `bloom_club_tma_auth`.

**После ответа frontend:** `loadAppData()` продолжает `getProfile()` и `getSubscription()`, затем выставляет `data.profile`, `data.subscription`, сбрасывает catalog/partner flow, снимает `isLoading`.

**React state:** `isTelegramApp`, `isLoading`, `error`, `data`, `shouldShowLinking`, `isBootstrapDone`, watchdog states при задержках. На login напрямую меняется localStorage, а не React state.

**Context:** напрямую не меняется.

**useRef:** `bootstrapPromiseRef`, `bootstrapSequenceRef`, `mountedRef`; в API client module-level `telegramLoginInFlight`.

**Перерисовка:** `App`, `LoadingState`/`ErrorState`/страницы внутри `AppShell`; далее Home/Profile/Subscription получают обновлённые props.

**Страницы:** bootstrap нужен всем страницам.

**Timeout/AbortController:** через 30 секунд controller abort; ошибка становится `TelegramLoginError` с `isAbortError=true`; возможен 1 retry.

**Network error:** `TelegramLoginError` stage `telegram_login_request`; возможен 1 retry.

**HTTP 401/403/404/500:** не retry, кроме 502/503/504. Ошибка попадает в bootstrap diagnostic и `setError(createDiagnostic(...))`.

**Retry:** да, 1 retry для timeout/network/502/503/504.

**Fallback:** нет успешного fallback без токена; bootstrap останавливается с error.

**Bootstrap:** да, центральный login-запрос.

**Diagnostics/recovery:** `telegram_login_prefetch`, startup trace; recovery — ручной retry `loadAppData("manual", true)`, сброс `telegramLoginInFlight`, очистка stale state.

**Цепочка:**

React `App.loadAppData()` → `loginWithTelegramPayload()` → `loginWithTelegram()` → `loginWithTelegramAttempt()` → `fetch('/api/v1/auth/telegram-miniapp-login')` → Node production server `handleTelegramLoginProxy()` → WEB API `https://bloomclub.ru/api/v1/auth/telegram-miniapp-login` → JSON token → frontend `setStoredToken()` → `getProfile()/getSubscription()` → `setData()` → render.

### 2. `GET /api/v1/clients/me`

**Кто вызывает:** React bootstrap, profile refresh, save profile after patch, linking refresh.

**Файл/функция:** `App.loadAppData()` / `refreshProfileAndSubscription()` / `saveProfile()` / `refreshAfterLinking()` → `getProfile()` → `requestClientApiGet()`.

**Когда:** при stored token check, после fresh login, после profile update, after linking.

**Условия:** нужен stored token, иначе Authorization не будет добавлен; frontend всё равно вызовет endpoint после login или при stored token.

**Параметры:** query/body нет.

**Headers:** `Authorization: Bearer <stored token>` если есть; Content-Type не ставится; browser может отправить стандартные headers.

**Authorization:** Bearer token из `localStorage`.

**URL:** same-origin `/api/v1/clients/me`.

**Proxy:** да, Node client API proxy → `https://bloomclub.ru/api/v1/clients/me`.

**Кто принимает:** Node `handleClientApiProxy()`, затем внешний WEB API. WEB API код отсутствует.

**Backend внутри Node:** допускает GET/HEAD/OPTIONS для `/api/v1/clients/me`; копирует `Authorization`, `Accept`, `Content-Type`, `User-Agent`; ставит timeout 30 секунд; прокидывает status/body/request id.

**Проверки:** Node проверяет allowed path/method; WEB API проверяет Bearer token. При 401 frontend на bootstrap очищает token и делает Telegram login; вне bootstrap 401 пробрасывается вызывающим компонентам.

**Данные/таблицы:** Node не читает БД. WEB API таблицы неизвестны.

**Возврат:** `ClientProfile` JSON.

**После ответа frontend:** bootstrap кладёт `data.profile`; refresh — обновляет profile; `saveProfile()` после PATCH заново читает profile.

**React state:** `data.profile`, `isLoading`, `error`, `shouldShowLinking`.

**Context:** нет.

**useRef:** bootstrap refs; при refresh refs не меняются.

**Перерисовка:** HomePage, ProfilePage, AccountLinkingOnboarding, SubscriptionPage области, AppShell.

**Страницы:** Home, Profile, Subscription, onboarding.

**Timeout/Abort/network:** превращаются в `TimeoutError`/`NetworkError`; так как GET с retry, есть 1 retry.

**HTTP 401:** в bootstrap triggers `clearStoredAuthToken()` → login → повтор profile/subscription. В других местах проброс наверх.

**HTTP 403/404/500:** `ApiError`; retry только 502/503/504, не 500.

**Retry:** да, 1 retry для GET retryable errors.

**Fallback:** bootstrap после 401 имеет fallback login; для других статусов нет.

**Bootstrap/diagnostics/recovery:** bootstrap да; diagnostics `api_request_*`, startup trace; recovery ручной retry bootstrap.

**Цепочка:**

React `loadAppData()` → `getProfile()` → `requestClientApiGet('/clients/me')` → `fetch('/api/v1/clients/me')` → Node client proxy → WEB API `/clients/me` → JSON profile → `setData(profile)` → render Home/Profile.

### 3. `GET /api/v1/clients/me/subscription`

Аналогичен `GET /api/v1/clients/me`, но path `/clients/me/subscription`, функция `getSubscription()`, результат `Subscription` кладётся в `data.subscription`. Используется bootstrap, `refreshProfileAndSubscription()`, `activateTrial()` refresh, `refreshAfterLinking()`. Страницы: HomePage, SubscriptionPage, ProfilePage. Node proxy разрешает path, WEB API реализация неизвестна.

**Цепочка:** React → `getSubscription()` → `requestClientApiGet('/clients/me/subscription')` → same-origin `/api/v1/clients/me/subscription` → Node proxy → WEB API → JSON subscription → `setData(subscription)` → render.

### 4. `GET /api/v1/clients/me/verifications` или `GET /api/tg/me/verifications`

**Кто вызывает:** `loadAppData()` secondary requests и `createVerification()` после успешной verify.

**Файл/функция:** `App.tsx` → `getVerifications()`.

**Когда:** после основного bootstrap data set; после создания verification.

**Условия:** если local TG catalog выключен — WEB client proxy `/api/v1/clients/me/verifications`; если включён — TG `/api/tg/me/verifications`.

**Параметры:** нет.

**Headers:** Bearer token добавляется, если есть. Для TG path тоже добавляется, но Node TG stub его не использует.

**Authorization:** Bearer token для WEB; TG local backend user context не реализован.

**URL/proxy:** WEB mode — same-origin `/api/v1/clients/me/verifications` через Node proxy к WEB API. TG mode — `/api/tg/me/verifications` напрямую на TG API текущего origin или `VITE_TG_API_BASE_URL`.

**Кто принимает:** Node client proxy/WEB API либо Node TG stub/Python WSGI TG API.

**Backend:** Node TG возвращает 501 `{detail:'user_context_not_configured'}`; Python WSGI тоже 501. WEB API backend неизвестен.

**Проверки/данные/таблицы:** TG не читает user data; WEB неизвестно.

**Возврат:** WEB — `Verification[]` по контракту frontend; TG 501 даёт fallback `[]`.

**После ответа frontend:** `data.verifications` обновляется при fulfilled. При secondary request rejected старое значение сохраняется.

**React state:** `data.verifications`.

**Context/useRef:** нет прямых изменений.

**Перерисовка:** PrivilegesPage, PartnerPage (коды/верификации), Home badges если использует data.

**Timeout/network:** GET retry 1 раз; затем secondary request fail не ломает bootstrap, сохраняет старые verifications.

**401:** TG mode 401 fallback `[]`; WEB mode 401 как rejected secondary, bootstrap продолжается без обновления.

**403/404/500:** `ApiError`; no fallback кроме secondary сохранения старого значения; 502/503/504 retry.

**Retry:** да.

**Fallback:** TG 501/401 → `[]`; bootstrap secondary Promise.allSettled сохраняет current value при ошибке.

**Bootstrap/diagnostics/recovery:** secondary bootstrap; diagnostics `api_request_*`/startup trace; recovery через повтор bootstrap или после verify refresh.

**Цепочка:** React → `getVerifications()` → WEB `/api/v1/clients/me/verifications` через Node proxy или TG `/api/tg/me/verifications` → backend → JSON/501 → fallback or array → `setData(verifications)` → render Privileges/Partner.

### 5. `GET /api/v1/clients/me/savings` или `GET /api/tg/me/savings`

Полностью аналогичен verifications, функция `getSavings()`. WEB mode возвращает `SavingsSummary`; TG mode 501/401 превращается в `{total:0, amount:0, items:[]}`. State: `data.savings`. Страница: SavingsPage, Home summary. Retry/fallback/diagnostics как у verifications.

**Цепочка:** React → `getSavings()` → WEB client proxy или TG `/api/tg/me/savings` → backend → JSON/501 → `setData(savings)` → render Savings.

### 6. `GET /api/v1/clients/cities`

**Кто вызывает:** bootstrap secondary requests; profile UI использует список городов.

**Файл/функция:** `App.loadAppData()` → `getCities()`.

**Когда:** после profile/subscription.

**Условия:** всегда во secondary Promise.allSettled.

**Параметры:** нет.

**Headers/Authorization:** Bearer token если есть.

**URL/proxy:** same-origin `/api/v1/clients/cities` → Node proxy → WEB API `/clients/cities`.

**Backend:** Node path allowlist; WEB API details/tables неизвестны.

**Возврат:** `City[]`.

**Frontend после ответа:** `data.cities` обновляется; ProfilePage получает список.

**Errors:** GET retry; при final fail bootstrap не падает, city list остаётся старым/empty. 401/403/404/500 — `ApiError`, no special handling.

**Цепочка:** React → `getCities()` → `/api/v1/clients/cities` → Node proxy → WEB API → JSON cities → `setData(cities)` → render Profile.

### 7. `GET /api/v1/clients/me/linking-status`

**Кто вызывает:** bootstrap secondary requests; `refreshAfterLinking()`.

**Файл/функция:** `App.tsx` → `getLinkingStatus()`.

**Когда:** после bootstrap, after account linking confirm.

**Условия:** Bearer token желательно; no request body.

**URL/proxy:** same-origin `/api/v1/clients/me/linking-status` → Node proxy → WEB API.

**Возврат:** `LinkingStatus`.

**Frontend:** `data.linkingStatus`; `setShouldShowLinking()` вычисляется из profile/status/localStorage. AccountLinkingOnboarding показывается/скрывается.

**Errors:** GET retry; bootstrap allSettled fallback keeps current/null. In `refreshAfterLinking()`, linking status catch → null.

**Цепочка:** React → `getLinkingStatus()` → Node proxy → WEB API → JSON status → `setData(linkingStatus)`/`setShouldShowLinking()` → render onboarding.

### 8. `GET /api/tg/partners` или `GET /api/v1/clients/catalog/partners`

**Кто вызывает:** `loadPartners()` при открытии каталога, startup page `#catalog`, after bootstrap if current page catalog, retry button.

**Файл/функция:** `App.tsx` → `loadPartners()` → `getPartners()` → `getPartnersAttempt()`.

**Когда:** при переходе в catalog или необходимости загрузить partners. Если не forceRetry, сначала пробует bootstrap data из `window.__BLOOM_TG_CATALOG_BOOTSTRAP__`.

**Условия:** local TG catalog flag выбирает endpoint. Если bootstrap partners есть и не consumed, HTTP не делается.

**Параметры:** нет.

**Headers:** `Accept: application/json`; `Authorization: Bearer <token>` если есть.

**Authorization:** для WEB может быть нужен Bearer; TG Node/Python public не требуют.

**URL:** TG mode `/api/tg/partners` current origin/TG base. WEB legacy mode `https://bloomclub.ru/api/v1/clients/catalog/partners`.

**Proxy:** TG mode обычно напрямую к Node TG API same-origin; WEB mode напрямую к WEB API, не Node proxy, потому path не начинается с same-origin `/api/v1` в getPartnersAttempt.

**Кто принимает:** Node `handlePartners()` или Python WSGI `list_active_partners()`; WEB API details unknown.

**Backend:** Node: если DB не настроена, `{items:[]}`; иначе SELECT active partners with cover/offers count/photos. Python: connect DB, `list_active_partners()`.

**Проверки:** method GET; DB availability; active partners only. No auth in TG public.

**Таблицы:** `telegram_partners`, `telegram_partner_photos`, `telegram_partner_offers`.

**Возврат:** `{items:[Partner...]}` or compatible keys. Frontend normalizes media URLs and id.

**Frontend:** `setData({...partners})`, `setHasPartnersLoaded(true)`, clears errors/loading flags.

**React state:** `isPartnersLoading`, `partnersError`, `partnersErrorDetails`, `catalogErrorCreatedAt`, `catalogLoadStartedAt`, `catalogLoadRequestId`, `hasPartnersLoaded`, `data.partners`.

**Context/useRef:** `partnersPromiseRef`, `catalogLoadSequenceRef`; no Context.

**Перерисовка:** CatalogPage, HomePage partner carousel, AppShell.

**Timeout/Abort/network:** catalog controller abort after 30s, 1 retry; after failure diagnostic is stored in state and CatalogPage error UI can retry.

**401:** no special handling in catalog except diagnostic; TG mode `getPartners()` does not fallback on 401.

**403/404/500:** `CatalogLoadError`; 502/503/504 retry; 500 no retry.

**Retry:** да, 1 retry for network/timeout/502/503/504.

**Fallback:** bootstrap injected catalog avoids HTTP; TG no DB returns empty items; Content/home UI may show empty.

**Bootstrap:** yes, Node `serveFrontend()` injects catalog bootstrap by DB read.

**Diagnostics/recovery:** `catalog_fetch_*`, `catalog_load_*`, retry button `loadPartners(true)`.

**Цепочка:** React `openCatalog/loadPartners()` → `consumeCatalogBootstrap()` or `getPartners()` → `fetch('/api/tg/partners')` or WEB catalog → Node/Python TG API or WEB API → Postgres/SQLite TG tables or WEB backend → JSON `{items}` → `setData(partners)` → CatalogPage/Home render.

### 9. `GET /api/tg/partners/:id/offers` или `GET /api/v1/clients/partners/:id/offers`

**Кто вызывает:** opening partner page and retry offers.

**Файл/функция:** `App.openPartner()` → `loadPartnerOffers()` → `getPartnerOffers()`.

**Когда:** user selects partner from catalog/home.

**Условия:** partner id must resolve to numeric id; otherwise no request and error state.

**Параметры:** path parameter `partnerId`.

**Headers/Authorization:** Bearer token if exists; Content-Type absent for GET.

**URL/proxy:** TG mode `/api/tg/partners/{id}/offers` direct TG API. WEB mode `https://bloomclub.ru/api/v1/clients/partners/{id}/offers` direct WEB API, not Node proxy.

**Backend:** Node TG SELECT active offers by partner id; Python checks active partner exists then lists offers. WEB unknown.

**Проверки:** method GET; numeric id via route; active offers. Python returns 404 if partner missing; Node returns empty items for missing partner offers path.

**Таблицы:** `telegram_partner_offers`; Python also checks `telegram_partners`.

**Возврат:** `{items:[Offer...]}` or compatible; frontend extracts offer array.

**Frontend state:** before request clears `partnerOffers`, error/diagnostic; sets `partnerOffersStatus='loading'`; on success sets `partnerOffers`, status `success` or `empty`. On error sets status `timeout` for TimeoutError, special 401 message, otherwise `error`.

**useRef/Context:** no direct Context/ref changes.

**Перерисовка/pages:** PartnerPage.

**Timeout/network:** `request()` GET retry 1; final timeout status `timeout`.

**401:** PartnerPage shows “Сессия истекла...”.

**403/404/500:** generic offers error; 502/503/504 retry.

**Retry/fallback:** retry yes; no data fallback except empty state on successful empty response.

**Diagnostics/recovery:** `api_request_*`, partner diagnostic stored; retry button calls `retryPartnerOffers()`.

**Цепочка:** Partner card click → `openPartner()` → `loadPartnerOffers()` → `getPartnerOffers()` → TG/WEB offers endpoint → backend DB/WEB → JSON offers → `setPartnerOffers()`/`setPartnerOffersStatus()` → PartnerPage render.

### 10. `POST /api/tg/partners/:partnerId/offers/:offerId/verify` или `POST /api/v1/clients/partners/:partnerId/verify`

**Кто вызывает:** PartnerPage privilege verification action via prop `onCreateVerification`.

**Файл/функция:** `App.createVerification()` → `verifyPartnerOffer()`.

**Когда:** user requests offer verification/code.

**Условия:** selected partner/offer ids provided. TG mode if local catalog enabled; WEB mode otherwise.

**Параметры/body:** TG mode no body. WEB mode body `{ "privilege_id": offerId }`.

**Headers:** WEB mode `Content-Type: application/json`, `Authorization` if token. TG mode Authorization if token but no body Content-Type unless body exists.

**URL/proxy:** TG mode `/api/tg/partners/{partnerId}/offers/{offerId}/verify`; Node production server does not implement this route and returns 404; Python WSGI implements route but returns 501. WEB mode direct `https://bloomclub.ru/api/v1/clients/partners/{partnerId}/verify`.

**Backend:** Node: falls through `/api/` 404. Python: returns 501 `access_check_not_configured`. WEB unknown.

**Checks:** WEB presumably checks subscription/access, not in repo. TG no real access check.

**Tables:** Python route does not write. Node no DB. WEB unknown.

**Возврат:** WEB expected `Verification`. TG local currently 404/501.

**Frontend after response:** on success prepends verification to `data.verifications`, then calls `getVerifications()` and replaces if refresh succeeds.

**State:** `data.verifications`; PartnerPage internal action state (component local not detailed here if not in repo-level API client); error thrown to component.

**useRef/Context:** none.

**Errors:** POST no retry. Timeout/network no retry. 401/403/404/500 become `ApiError` and are thrown.

**Fallback:** after successful verify, refresh verifications failure is ignored. No fallback for verify failure.

**Diagnostics/recovery:** `api_request_*`; user can retry action manually.

**Цепочка:** PartnerPage action → `createVerification()` → `verifyPartnerOffer()` → WEB direct or TG verify path → backend → JSON verification/error → `setData(verifications)` → optional `getVerifications()` refresh → Partner/Privileges render.

### 11. `PATCH /api/v1/clients/me`

**Кто вызывает:** ProfilePage save via `saveProfile()`.

**Файл/функция:** `App.saveProfile()` → `updateProfile()`.

**Когда:** user saves profile.

**Условия:** payload from profile form.

**Параметры/body:** normalized profile patch includes aliases: `full_name/name`, `contact_email/email`, `custom_city/city_slug/city`, plus original fields.

**Headers/Auth:** `Content-Type: application/json`, `Authorization: Bearer <token>` if present.

**URL/proxy:** direct WEB API `https://bloomclub.ru/api/v1/clients/me`; not Node proxy when WEB base absolute. If misconfigured same-origin, Node only allows GET and would 405.

**Backend:** WEB API unknown.

**Возврат:** `ClientProfile`; frontend ignores direct result and calls `getProfile()` after success.

**State:** after refresh `data.profile`.

**Errors:** no retry; Timeout/Network/401/403/404/500 thrown to ProfilePage. Timeout becomes `TimeoutError`.

**Fallback/recovery:** no automatic fallback; user can retry save.

**Цепочка:** ProfilePage form → `saveProfile()` → `updateProfile()` PATCH WEB → WEB API → JSON/204 → `getProfile()` via Node proxy → `setData(profile)` → ProfilePage render.

### 12. `POST /api/v1/clients/me/trial-subscription`

**Кто вызывает:** SubscriptionPage/Home trial action via `activateTrial()`.

**Файл/функция:** `App.activateTrial()` → `activateTrialSubscription()`.

**Когда:** user activates trial.

**Параметры:** no body.

**Headers/Auth:** Authorization if token; no Content-Type without body.

**URL/proxy:** direct WEB API `/clients/me/trial-subscription`.

**Backend:** WEB unknown.

**Возврат:** `Subscription` or object with `subscription` and optional `profile`.

**Frontend:** updates `data.subscription`, maybe `data.profile`, then `refreshProfileAndSubscription()` calls GET profile/subscription; sets `trialMessage`.

**Errors:** no retry; thrown to caller.

**Цепочка:** user action → `activateTrial()` → POST WEB trial → JSON → `setData(subscription/profile)` → `getProfile()+getSubscription()` → `setTrialMessage()` → render Subscription/Home.

### 13. `POST /api/v1/clients/me/payment-requests`

**Кто вызывает:** SubscriptionPage payment prolongation action via `openPayment()`.

**Файл/функция:** `App.openPayment()` → `createPaymentRequest()`.

**Когда:** user opens/creates payment request.

**Headers/Auth:** Authorization if token.

**URL/proxy:** direct WEB API `/clients/me/payment-requests`.

**Backend:** WEB unknown.

**Возврат:** `PaymentRequest`.

**Frontend:** `setIsCreatingPayment(true/false)`, `setPaymentRequest(request)`, `setPaymentMessage(...)`.

**Errors:** no retry. Timeout message is retryable text; other errors generic payment message. No throw after catch.

**Цепочка:** SubscriptionPage → `openPayment()` → POST WEB payment requests → WEB → JSON → `setPaymentRequest()`/`setPaymentMessage()` → render Subscription.

### 14. `POST /api/v1/clients/me/payment-requests/:id/mark-paid`

**Кто вызывает:** exported `markPaymentRequestPaid()`.

**Использование в UI:** в изученном `App.tsx` вызов не найден.

**Файл/функция:** `api/client.ts` → `markPaymentRequestPaid(id)`.

**Когда/условия:** неизвестно; функция экспортирована.

**Headers/Auth:** Authorization if token.

**URL/proxy:** direct WEB API `/clients/me/payment-requests/{id}/mark-paid`.

**Backend/таблицы:** WEB unknown.

**Возврат:** `PaymentRequest`.

**Errors/retry/fallback:** POST no retry/fallback.

**Цепочка:** неизвестный caller → `markPaymentRequestPaid()` → POST WEB → JSON PaymentRequest.

### 15. `POST /api/v1/clients/me/linking/start`

**Кто вызывает:** AccountLinkingOnboarding.

**Файл/функция:** component `AccountLinkingOnboarding` → `startAccountLinking(identifier)`.

**Когда:** user enters identifier and starts account linking.

**Параметры/body:** `{identifier}`.

**Headers/Auth:** `Content-Type: application/json`, Bearer token if exists.

**URL/proxy:** direct WEB API `/clients/me/linking/start`.

**Backend:** WEB unknown.

**Возврат:** `LinkingStartResponse`.

**Frontend:** component local state changes for challenge/code step; app-level state not changed until confirm refresh.

**Errors:** no retry; component displays error (details in component).

**Цепочка:** onboarding form → `startAccountLinking()` → POST WEB → JSON challenge → component state → render code step.

### 16. `POST /api/v1/clients/me/linking/confirm`

**Кто вызывает:** AccountLinkingOnboarding.

**Файл/функция:** component → `confirmAccountLinking(challengeId, code)`; on success calls App `refreshAfterLinking()`.

**Параметры/body:** `{challenge_id: challengeId, code}`.

**Headers/Auth:** JSON + Bearer token.

**URL/proxy:** direct WEB API `/clients/me/linking/confirm`.

**Backend:** WEB unknown.

**Возврат:** `LinkingConfirmResponse`.

**Frontend:** component local success; App refreshes profile/subscription/linking-status using GETs and updates `data`.

**Errors:** no retry/fallback except user retry.

**Цепочка:** onboarding code → `confirmAccountLinking()` → POST WEB → JSON → `refreshAfterLinking()` → GET profile/subscription/linking-status → `setData()` → hide/show onboarding.

## Content frontend requests

### 17. `GET /api/content/blocks?type=static_texts`

**Кто вызывает:** ContentProvider / content consumers through `getContentBlocks()`.

**Файл/функция:** `telegram-mini-app/src/content/clientContentApi.ts` → `getContentBlocks()` → `contentRequest()`.

**Когда:** when content provider loads static texts.

**Условия:** no auth; always same-origin for `/blocks`.

**Headers:** `Accept: application/json`.

**Authorization:** none.

**URL/proxy:** same-origin `/api/content/blocks?type=static_texts` → Node content blocks proxy → `https://bloomclub.ru/api/content/blocks?type=static_texts`.

**Backend:** Node only proxies. WEB Content API implementation not in repo.

**Checks:** Node allows GET/HEAD/OPTIONS only; timeout 20s.

**Data/tables:** Node no DB. Content API tables unknown.

**Return:** list/objects normalized into `ContentBlock[]`.

**Frontend:** ContentContext state likely receives blocks; if error returns `[]`.

**React state/context:** ContentProvider context changes, not App data. Exact context internals in `ContentContext`.

**Timeout/network/HTTP 401/403/404/500:** `contentRequest()` throws Timeout/Network/ApiError; `getContentBlocks()` catches all and returns `[]`.

**Retry:** none.

**Fallback:** yes, empty array. Node proxy itself also fallback empty array on upstream failure.

**Diagnostics:** `content_request_*`, `content_blocks_failed/loaded`.

**Цепочка:** ContentProvider → `getContentBlocks()` → `fetch('/api/content/blocks?type=static_texts')` → Node `handleContentBlocksProxy()` → WEB Content API → JSON/error → normalize or `[]` → ContentContext value → render text consumers.

### 18. `GET /api/content/blocks?placement=telegram_home`

Same as previous, but function `getHomeBlocks()`, placement `telegram_home`, return `HomeBlock[]`. Used by home content rendering through ContentProvider/hooks. Fallback `[]` on any error. Proxy and backend same.

**Цепочка:** Home content consumer → `getHomeBlocks()` → same-origin content proxy → WEB Content API → JSON home blocks → ContentContext/HomePage render.

## Production server direct routes

### 19. `GET|HEAD /`, `/app`, `/app-v*`, `/miniapp/*`, `/telegram-app/*`

**Кто вызывает:** browser navigation, Telegram WebView loading SPA.

**Файл/функция:** Node `handleRequest()` → `serveFrontend()`.

**Когда:** initial app load or frontend route refresh.

**Параметры/headers/auth:** no app auth.

**Proxy:** platform/nginx may forward to Node; inside Node no upstream HTTP except DB bootstrap.

**Backend:** reads `dist/index.html`, tries DB catalog bootstrap via `fetchPublicCatalogPartners()`, injects `window.__BLOOM_TG_CATALOG_BOOTSTRAP__`.

**Checks:** method GET/HEAD; route whitelist; asset existence; if missing index and fallback enabled returns small fallback HTML.

**Tables:** `telegram_partners`, `telegram_partner_photos`, `telegram_partner_offers` for bootstrap.

**Return:** HTML SPA.

**Frontend after response:** browser loads JS; App bootstraps; optional catalog bootstrap consumed by `loadPartners(false)`.

**Errors/fallback:** missing index fallback for versioned frontend routes; DB bootstrap failure logs warning and serves HTML without bootstrap.

**Цепочка:** Telegram/browser → production proxy/platform → Node route → `serveFrontend()` → DB bootstrap SELECT → HTML with optional bootstrap → browser JS → React render.

### 20. `GET|HEAD /assets/*`

Static asset serving by Node `serveAsset()`. Method GET/HEAD only; path traversal protected by resolved path prefix; returns content-type by extension or 404. No auth, no retry by app. Browser consumes JS/CSS/images.

### 21. `GET|HEAD /uploads/*`

Node `serveUpload()` serves files from `telegram-mini-app/uploads`. GET/HEAD only; path traversal protected; content-type by extension; 404 if missing. No auth. Used by media URLs if catalog/upload responses point to `/uploads/...`.

### 22. `GET|HEAD /health`, `/api/tg/health`, `/ready`

**Кто вызывает:** platform health checks, operators.

**Backend:** Node `handleHealth()` or ready branch. Non-DB health.

**Return:** JSON health for `/health` and `/api/tg/health`; text `ok` for `/ready`.

**Checks:** method GET/HEAD; no DB.

**Frontend:** not called by frontend code found.

### 23. `GET /api/tg/health/db`

Node/Python DB readiness. Checks DB configured and query works. Returns 200 if DB ok, 503 if DB not configured/unavailable. Frontend code not found calling it.

### 24. `GET /api/tg/status`

Node/Python catalog status/counts. Reads TG catalog tables and returns counts/status. No frontend caller found. Used for diagnostics/operators/tests.

### 25. `GET /debug/runtime-port`

Node diagnostics endpoint. Returns safe runtime port/env information. No frontend caller found. No auth in code.

## Python WSGI TG/Admin/Uploads API

### Public TG API

- `GET /api/tg/health`: JSON service status.
- `GET /api/tg/health/db`: DB check.
- `GET /api/tg/status`: catalog counts.
- `GET /api/tg/partners`: active partners from `telegram_partners`, photos/offers via repository.
- `GET /api/tg/partners/:id`: active partner or 404.
- `GET /api/tg/partners/:id/offers`: checks active partner then active offers or 404.
- `POST /api/tg/partners/:partnerId/offers/:offerId/verify`: returns 501 `access_check_not_configured`.
- `GET /api/tg/me/verifications`, `GET /api/tg/me/savings`: return 501 `user_context_not_configured`.

### Admin TG API (Python WSGI)

All `/api/tg/admin/*` require either `X-Telegram-Admin-Token` or `Authorization: Bearer`, matching `TELEGRAM_ADMIN_API_TOKEN`. Missing token: 401; invalid token: 403; token not configured: 501.

- `GET /api/tg/admin/partners`: list admin partners.
- `POST /api/tg/admin/partners`: create partner; validates JSON object and partner fields.
- `PATCH /api/tg/admin/partners/:id`: update partner; 404 if missing.
- `DELETE /api/tg/admin/partners/:id`: soft delete partner; 404 if missing.
- `GET /api/tg/admin/partners/:id/photos`: list photos; 404 if partner missing.
- `POST /api/tg/admin/partners/:id/photos`: create photo; 404 if partner missing.
- `PATCH /api/tg/admin/photos/:photoId`: update photo; 404 if missing.
- `DELETE /api/tg/admin/photos/:photoId`: delete photo; 404 if missing.
- `GET /api/tg/admin/partners/:id/offers`: list offers; 404 if partner missing.
- `POST /api/tg/admin/partners/:id/offers`: create offer; 404 if partner missing.
- `PATCH /api/tg/admin/offers/:offerId`: update offer; 404 if missing.
- `DELETE /api/tg/admin/offers/:offerId`: soft delete offer; 404 if missing.

Tables: `telegram_partners`, `telegram_partner_photos`, `telegram_partner_offers`.

### Uploads Python WSGI

`POST /api/content/uploads` accepts multipart `file`, requires admin auth through same token mechanism, limits request to about 11 MiB and file to 10 MiB, allows jpg/jpeg/png/webp, writes into `uploads/content`, returns file URL. Also rejects invalid multipart, missing file, too large, unsupported type. Method handling is inside upload response; non-POST behavior should be treated as not fully documented unless tests cover it.

## Admin bot Content Admin API requests

All below are called by Telegram admin bot handlers in `admin_bot/admin_bot/bot.py` through `ContentAdminApiClient`. They go to `WEB_CONTENT_API_BASE_URL` (example `/api/content`) plus path, directly; not through Node production proxy unless that base URL is configured to point there. Headers always include Bearer and `X-Telegram-Admin-Token`. Timeout 30s. No retry. HTTP >=400 and network errors are reported to admin as `WebApiError`.

### Admin bot request chains

Generic chain for every admin bot call:

Telegram admin message/callback → aiogram handler in `bot.py` → `get_api(event)` → `ContentAdminApiClient.<method>()` → `_request(method, path)` → `httpx.AsyncClient` → Content Admin API / Upload endpoint → JSON → normalize `_as_list/_as_dict` if applicable → bot sends/edits Telegram message.

### Endpoints called by admin bot

- `POST /uploads`: `upload_file()`; multipart file. Used when admin sends photos for giveaways, giveaway items, partners, offers, banners. Returns URL.
- `GET /admin/partners`: `list_partners()`; partner list menus.
- `POST /admin/partners`: `create_partner(payload)`; create partner wizard.
- `PATCH /admin/partners/:partner_id`: `update_partner()`; edit/toggle partner.
- `GET /admin/partners/:partner_id/photos`: `list_partner_photos()`.
- `POST /admin/partners/:partner_id/photos`: `add_partner_photo()` with `{url,image_url}`.
- `PATCH /admin/partner-photos/:photo_id`: `update_partner_photo()`.
- `GET /admin/partners/:partner_id/offers`: `list_offers()`.
- `POST /admin/partners/:partner_id/offers`: `create_offer()`.
- `PATCH /admin/offers/:offer_id`: `update_offer()`.
- `GET /admin/offers/:offer_id/photos`: `list_offer_photos()`; method exists, UI caller not found in current scan.
- `POST /admin/offers/:offer_id/photos`: `add_offer_photo()`.
- `PATCH /admin/offer-photos/:photo_id`: `update_offer_photo()`.
- `GET /admin/blocks`: `list_blocks()`.
- `GET /admin/blocks/:block_id`: `get_block()`; fallback lists all blocks and finds locally if endpoint errors.
- `POST /admin/blocks`: `create_block()`.
- `PATCH /admin/blocks/:block_id`: `update_block()`, `hide_block()`, `publish_block()`.
- `GET /admin/banners`: `list_banners()`.
- `GET /admin/banners/:banner_id`: `get_banner()`; fallback lists all banners and finds locally if endpoint errors.
- `POST /admin/banners`: `create_banner()`.
- `PATCH /admin/banners/:banner_id`: `update_banner()`, hide/publish/photo update.
- `GET /admin/cities`: `list_cities()`.
- `GET /admin/cities/:city_id`: `get_city()`; fallback lists all cities and finds locally if endpoint errors.
- `POST /admin/cities`: `create_city()`.
- `PATCH /admin/cities/:city_id`: `update_city()`, hide/publish.
- `GET /admin/categories`: `list_categories()`.
- `GET /admin/categories/:category_id`: `get_category()`; fallback lists all categories and finds locally if endpoint errors.
- `POST /admin/categories`: `create_category()`.
- `PATCH /admin/categories/:category_id`: `update_category()`, hide/publish.
- `GET /admin/giveaways`: `list_giveaways()`.
- `GET /admin/giveaways/:giveaway_id`: `get_giveaway()`.
- `POST /admin/giveaways`: `create_giveaway()`.
- `PATCH /admin/giveaways/:giveaway_id`: `update_giveaway()`, hide/publish/photo fallback update.
- `GET /admin/giveaways/:giveaway_id/photos`: `list_giveaway_photos()`; method exists, UI caller not found in current scan.
- `POST /admin/giveaways/:giveaway_id/photos`: `add_giveaway_photo()`.
- `PATCH /admin/giveaway-photos/:photo_id`: `update_giveaway_photo()`; method exists, UI caller not found in current scan.
- `GET /admin/giveaways/:giveaway_id/items`: `list_giveaway_items()`.
- `GET /admin/giveaway-items/:item_id`: `get_giveaway_item()`.
- `POST /admin/giveaways/:giveaway_id/items`: `create_giveaway_item()`.
- `PATCH /admin/giveaway-items/:item_id`: `update_giveaway_item()`, hide/publish/photo update.

For these Content Admin endpoints, repository does not contain receiving WEB Content Admin API implementation, database tables, exact validations or status semantics. Only caller behavior is known.

## Полная карта всех API

### WEB API

- `POST /api/v1/auth/telegram-miniapp-login` — same-origin Node proxy to WEB auth.
- `GET /api/v1/clients/me` — same-origin Node proxy.
- `GET /api/v1/clients/me/subscription` — same-origin Node proxy.
- `GET /api/v1/clients/me/verifications` — same-origin Node proxy in non-local catalog mode.
- `GET /api/v1/clients/me/savings` — same-origin Node proxy in non-local catalog mode.
- `GET /api/v1/clients/cities` — same-origin Node proxy.
- `GET /api/v1/clients/me/linking-status` — same-origin Node proxy.
- `GET /api/v1/clients/catalog/partners` — direct WEB legacy catalog when local TG catalog disabled.
- `GET /api/v1/clients/partners/:id/offers` — direct WEB.
- `POST /api/v1/clients/partners/:partnerId/verify` — direct WEB.
- `PATCH /api/v1/clients/me` — direct WEB.
- `POST /api/v1/clients/me/trial-subscription` — direct WEB.
- `POST /api/v1/clients/me/payment-requests` — direct WEB.
- `POST /api/v1/clients/me/payment-requests/:id/mark-paid` — exported, UI caller not found.
- `POST /api/v1/clients/me/linking/start` — direct WEB.
- `POST /api/v1/clients/me/linking/confirm` — direct WEB.

### TG API

- `GET /api/tg/health`
- `GET /api/tg/health/db`
- `GET /api/tg/status`
- `GET /api/tg/partners`
- `GET /api/tg/partners/:id`
- `GET /api/tg/partners/:id/offers`
- `POST /api/tg/partners/:partnerId/offers/:offerId/verify`
- `GET /api/tg/me/verifications`
- `GET /api/tg/me/savings`

### Admin API (Python TG admin)

- `GET /api/tg/admin/partners`
- `POST /api/tg/admin/partners`
- `PATCH /api/tg/admin/partners/:id`
- `DELETE /api/tg/admin/partners/:id`
- `GET /api/tg/admin/partners/:id/photos`
- `POST /api/tg/admin/partners/:id/photos`
- `PATCH /api/tg/admin/photos/:photoId`
- `DELETE /api/tg/admin/photos/:photoId`
- `GET /api/tg/admin/partners/:id/offers`
- `POST /api/tg/admin/partners/:id/offers`
- `PATCH /api/tg/admin/offers/:offerId`
- `DELETE /api/tg/admin/offers/:offerId`

### Content API

- `GET /api/content/blocks?type=static_texts`
- `GET /api/content/blocks?placement=telegram_home`
- `POST /api/content/uploads` (Python WSGI upload)
- Content Admin bot base paths: `/api/content/admin/*` and `/api/content/uploads` depending on `WEB_CONTENT_API_BASE_URL`; receiving implementation not in repo.

### Production Server

- `GET|HEAD /`, `/app`, `/app-v*`, `/miniapp`, `/miniapp/*`, `/telegram-app`, `/telegram-app/*`
- `GET|HEAD /assets/*`
- `GET|HEAD /uploads/*`
- `GET|HEAD /ready`
- `GET|HEAD /health`
- `GET|HEAD /api/tg/health`
- `GET /api/tg/health/db`
- `GET /api/tg/status`
- `GET /debug/runtime-port`
- `OPTIONS /api/v1/clients/*` allowed by proxy for selected paths.
- `OPTIONS /api/content/blocks` allowed by content proxy.

### Proxy API

- `POST /api/v1/auth/telegram-miniapp-login` → `https://bloomclub.ru/api/v1/auth/telegram-miniapp-login`
- `GET|HEAD|OPTIONS /api/v1/clients/cities` → `https://bloomclub.ru/api/v1/clients/cities`
- `GET|HEAD|OPTIONS /api/v1/clients/me` → `https://bloomclub.ru/api/v1/clients/me`
- `GET|HEAD|OPTIONS /api/v1/clients/me/*` → `https://bloomclub.ru/api/v1/clients/me/*`
- `GET|HEAD|OPTIONS /api/content/blocks` → `https://bloomclub.ru/api/content/blocks`

### Uploads

- `GET|HEAD /uploads/*` — static uploaded files served by Node.
- `POST /api/content/uploads` — Python WSGI admin upload.
- `POST <WEB_CONTENT_API_BASE_URL>/uploads` — admin bot upload to Content API base.

### Health

- `GET|HEAD /ready`
- `GET|HEAD /health`
- `GET|HEAD /api/tg/health`
- `GET /api/tg/health/db`

### Diagnostics

- `GET /debug/runtime-port`
- frontend console events: `api_request_*`, `telegram_login_*`, `catalog_fetch_*`, `content_request_*`, startup trace.
- Node console events: `telegram_login_proxy_*`, `client_api_proxy_*`, `content_blocks_proxy_*`, request logs, bootstrap warnings.

## Итоговая таблица endpoints

| Endpoint | Кто вызывает | Используется | Proxy | Авторизация | Retry | Fallback | Recovery |
|---|---|---:|---|---|---|---|---|
| `POST /api/v1/auth/telegram-miniapp-login` | App bootstrap | Да | Node→WEB | Нет на frontend | 1 | Нет | manual bootstrap retry |
| `GET /api/v1/clients/me` | App/Profile/Linking | Да | Node→WEB | Bearer | 1 | login after bootstrap 401 | manual retry/refresh |
| `GET /api/v1/clients/me/subscription` | App/Subscription | Да | Node→WEB | Bearer | 1 | login after bootstrap 401 | manual retry/refresh |
| `GET /api/v1/clients/me/verifications` | App/verify refresh | Да | Node→WEB | Bearer | 1 | secondary keeps old | bootstrap/manual refresh |
| `GET /api/v1/clients/me/savings` | App | Да | Node→WEB | Bearer | 1 | secondary keeps old | bootstrap retry |
| `GET /api/v1/clients/cities` | App/Profile | Да | Node→WEB | Bearer | 1 | secondary keeps old | bootstrap retry |
| `GET /api/v1/clients/me/linking-status` | App/Linking | Да | Node→WEB | Bearer | 1 | catch→null in refresh | refreshAfterLinking |
| `GET /api/v1/clients/catalog/partners` | Catalog | Да if local off | Direct WEB | Bearer if stored | 1 | none | catalog retry |
| `GET /api/v1/clients/partners/:id/offers` | PartnerPage | Да if local off | Direct WEB | Bearer if stored | 1 | empty only if backend returns empty | offers retry |
| `POST /api/v1/clients/partners/:id/verify` | PartnerPage | Да if local off | Direct WEB | Bearer | Нет | refresh verification failure ignored after success | user retry |
| `PATCH /api/v1/clients/me` | ProfilePage | Да | Direct WEB | Bearer | Нет | Нет | user retry |
| `POST /api/v1/clients/me/trial-subscription` | Subscription/Home | Да | Direct WEB | Bearer | Нет | Нет | user retry |
| `POST /api/v1/clients/me/payment-requests` | SubscriptionPage | Да | Direct WEB | Bearer | Нет | message only | user retry |
| `POST /api/v1/clients/me/payment-requests/:id/mark-paid` | Exported function | Caller not found | Direct WEB | Bearer | Нет | Нет | unknown |
| `POST /api/v1/clients/me/linking/start` | AccountLinkingOnboarding | Да | Direct WEB | Bearer | Нет | Нет | user retry |
| `POST /api/v1/clients/me/linking/confirm` | AccountLinkingOnboarding | Да | Direct WEB | Bearer | Нет | refresh after success | user retry |
| `GET /api/tg/partners` | Catalog | Да if local on | Direct TG same-origin | Public/Bearer ignored | 1 | bootstrap/empty no DB | catalog retry |
| `GET /api/tg/partners/:id` | API exists | No frontend caller found | Direct TG | Public | No caller | Нет | unknown |
| `GET /api/tg/partners/:id/offers` | PartnerPage | Да if local on | Direct TG | Public/Bearer ignored | 1 | empty possible | offers retry |
| `POST /api/tg/partners/:partnerId/offers/:offerId/verify` | PartnerPage | Да if local on | Direct TG | Not enforced | Нет | Нет | user retry; currently 404/501 |
| `GET /api/tg/me/verifications` | App | Да if local on | Direct TG | Not enforced | 1 | 501/401→[] | bootstrap retry |
| `GET /api/tg/me/savings` | App | Да if local on | Direct TG | Not enforced | 1 | 501/401→zero summary | bootstrap retry |
| `GET /api/content/blocks?type=static_texts` | ContentProvider | Да | Node→Content | Нет | Нет | [] | reload/content rerender |
| `GET /api/content/blocks?placement=telegram_home` | Home content | Да | Node→Content | Нет | Нет | [] | reload/content rerender |
| `POST /api/content/uploads` | Python/admin upload | Да if WSGI used | No | Admin token | Нет | Нет | admin retry |
| `POST <content>/uploads` | Admin bot | Да | Direct configured | Admin token | Нет | Нет | admin retry |
| `/api/content/admin/*` | Admin bot | Да | Direct configured | Admin token | Нет | selected get_* list fallback | admin retry |
| `GET|HEAD /` and frontend routes | Browser/Telegram | Да | Platform→Node | Нет | Browser-level | fallback HTML if index missing | reload |
| `GET|HEAD /assets/*` | Browser | Да | Platform→Node | Нет | Browser-level | 404 | reload |
| `GET|HEAD /uploads/*` | Browser/media | Да | Platform→Node | Нет | Browser-level | 404 | reload |
| `GET|HEAD /health` | Platform/operator | Да | Platform→Node | Нет | External | no DB required | platform restart |
| `GET|HEAD /ready` | Platform/operator | Да | Platform→Node | Нет | External | no DB required | platform restart |
| `GET /api/tg/health/db` | Operator/tests | Да | Direct TG | Нет | External | 503 detail | fix DB/restart |
| `GET /api/tg/status` | Operator/tests | Да | Direct TG | Нет | External | 503 detail | fix DB/restart |
| `GET /debug/runtime-port` | Operator | Да | Direct Node | Нет | External | Нет | inspect env |

## Что изучено

- Frontend API client, bootstrap flow, catalog/offers/profile/subscription/linking/payment/verification calls.
- Content API client and ContentProvider-facing fallbacks.
- Node production server routes, proxies, static/uploads, health and diagnostics.
- Python WSGI TG catalog/admin/uploads backend.
- Admin Telegram bot Content Admin API client and bot handler call sites.
- Tests and existing docs as auxiliary confirmation of route contracts.

## Что найдено

- Приложение использует три разных HTTP канала: same-origin Node proxy, direct WEB API, direct/configured TG/Content API.
- GET-запросы frontend имеют ограниченный retry, POST/PATCH retry не имеют.
- Content blocks имеют двойной fallback: frontend `[]` и Node proxy empty response on upstream failure.
- Local TG verification route фактически не даёт рабочую проверку: Node route отсутствует, Python route возвращает 501.
- User-context TG endpoints verifications/savings не реализованы и имеют frontend fallback.
- Admin bot работает с Content Admin API, реализация которого в репозитории отсутствует.

## Что не удалось определить

- Реальные таблицы, проверки, схемы ответов и точные status codes внешнего `https://bloomclub.ru/api/v1`.
- Реальные таблицы и validations внешнего `https://bloomclub.ru/api/content` и `/api/content/admin/*`.
- Полный набор callers для exported `markPaymentRequestPaid()`, `list_offer_photos()`, `list_giveaway_photos()`, `update_giveaway_photo()` не найден.
- Поведение platform/nginx proxy вне Node process не описано в коде репозитория.
- Точные local state изменения внутри некоторых page/components возможны только на уровне их component state; глобальный App state описан полностью по найденным call paths.

## Потенциальные проблемы

1. `POST /api/tg/partners/:partnerId/offers/:offerId/verify` вызывается frontend при local catalog, но Node production server его не реализует.
2. Node client API proxy read-only для `/clients/me/*`; write operations должны идти только direct WEB API. Same-origin WEB base сломает PATCH/POST writes.
3. Content proxy masks upstream outage empty list, что улучшает UX, но скрывает сбои контента.
4. TG public catalog не требует auth; Bearer header может отправляться, но backend его игнорирует.
5. `GET /api/tg/partners/:id/offers` различается: Node может вернуть empty items для missing partner, Python возвращает 404.
6. 500 не retry-ится frontend-клиентом, retry есть только для 502/503/504/network/timeout.

## Количество строк документации

Будет рассчитано командой проверки перед коммитом.

## Commit

Commit hash и commit message будут предоставлены в финальном ответе после `git commit`.
