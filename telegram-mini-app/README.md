# Bloom Club Telegram Mini App

Telegram Mini App is a second frontend for the existing Bloom Club backend. It does not own partner catalog data, photos, offers, subscriptions, verifications, savings, payments, an admin panel, or a separate database.

## Data flow

```text
Bloom Club site / admin
→ existing backend
→ shared data
→ VK Mini App
→ Telegram Mini App
```

Admin changes on the existing site are reflected in Telegram Mini App through the same client API that VK Mini App already uses.

## Authentication

Telegram Mini App reads Telegram launch payload and sends it to the backend endpoint:

```http
POST /api/v1/auth/telegram-miniapp-login
Content-Type: application/json

{ "init_data": "<telegram launch payload>" }
```

The frontend never validates Telegram signatures and never stores bot secrets. Signature validation must happen on the backend with the Telegram bot token. After login the backend returns the same client access token format used by VK Mini App, and this frontend calls existing `/clients/...` endpoints.


## Telegram WebApp SDK

`index.html` must load the official Telegram WebApp SDK before the React/Vite bundle:

```html
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script type="module" src="/src/main.tsx"></script>
```

The SDK creates `window.Telegram.WebApp`, which `src/telegram/webapp.ts` reads at runtime. Do not remove this script or move it after the React bundle. If CSP or other security headers are added, they must allow loading `https://telegram.org/js/telegram-web-app.js` in `script-src`.

## Troubleshooting Telegram runtime

If the app is opened from the bot Menu Button in Telegram Desktop and the error screen shows `stage: init_data_read`, Telegram may have provided the WebApp runtime object without providing Telegram launch payload. In this state the frontend intentionally does not send `POST /auth/telegram-miniapp-login`, because the backend cannot validate an empty Telegram launch payload.

Safe diagnostics on the error screen show only runtime metadata and lengths, not secrets. Use them to compare Desktop/Menu Button behavior with mobile Telegram:

- `hasTelegramObject`
- `hasWebApp`
- `platform`
- `version`
- `colorScheme`
- `launchPayloadLength`
- `hasLaunchUnsafe`
- `hasLaunchUnsafeUser`
- `hasStartParam`
- `startParamLength`
- `currentLocationHost`
- `currentUserAgentShort`

Recommended checks:

1. Open the same Mini App from mobile Telegram and confirm `launchPayloadLength` is greater than `0`.
2. If Desktop/Menu Button still gives `launchPayloadLength: 0`, test a full bot app button / Mini App launch button instead of only the Menu Button.
3. Keep the login endpoint configured through `VITE_API_BASE_URL=https://bloomclub.ru/api/v1`; the final login URL remains `https://bloomclub.ru/api/v1/auth/telegram-miniapp-login`.

Never paste or expose full Telegram launch data, signature values, backend access tokens, bot tokens, or any other secrets while debugging.

### Telegram iOS reopen/cache workaround

If Telegram iOS shows the system Mini App loader on repeated opens but the server receives no new nginx requests, Telegram may be reusing a stale WebView session before it reaches the origin. In that case, update the BotFather Mini App URL to a path-versioned URL instead of relying only on a query-string cache buster:

```text
https://tg.bloomclub.ru/app-vYYYYMMDD-N
```

For example, use `https://tg.bloomclub.ru/app-v20260625-12` for a new release. The production Node server serves this path as the same SPA HTML as `/`, while keeping `/assets/*`, `/uploads/*`, `/api/*`, `/ready`, `/health`, and `/debug/runtime-port` on their dedicated routes.

## Existing API used by this app

- `GET /clients/me`
- `PATCH /clients/me`
- `GET /clients/me/subscription`
- `POST /clients/me/trial-subscription`
- `GET /clients/catalog/partners`
- `GET /clients/partners/{numericPartnerId}/offers` — uses numeric `partner.id` only; the response is expected to be a plain array.
- `POST /clients/partners/{numericPartnerId}/verify` — sends `{ "privilege_id": offer.id }` like VK Mini App.
- `GET /clients/me/verifications`
- `GET /clients/me/savings`
- `GET /clients/cities`

## Backend contract notes

- Partner offers are loaded strictly by numeric `partner.id`; text identifiers such as names, titles, and display names are never used as path identifiers for that endpoint.
- Offer cards use backend/VK fields `title`, `description`, `benefit_text`, `conditions`, `base_price`, `discount_percent`, `image_url`, `photo_url`, and `photos`. If the backend does not send a ready member price, the frontend computes it from `base_price * (1 - discount_percent / 100)` and computes saving as `base_price - memberPrice`.
- User flow shows a text privilege code only. Graphic scan codes are intentionally not part of the Telegram Mini App user flow.

## Account linking / duplicate prevention

Account linking is not implemented in this frontend PR and must be solved in `fed_women_club_WEB` backend. Current platform auth can create duplicates because VK lookup is based on `vk_user_id`, while Telegram lookup is based on `telegram_user_id`. A safe linking flow must use verified phone/email plus explicit user consent, and trial eligibility must be limited once per verified identity rather than once per platform.

## Local setup

```bash
npm install
npm run typecheck
npm run build
```

Create `.env` from `.env.example` and set `VITE_API_BASE_URL` to the existing API base, for example `https://bloomclub.ru/api/v1`. Login uses `/auth/telegram-miniapp-login`, so the final request URL is `https://bloomclub.ru/api/v1/auth/telegram-miniapp-login` without duplicating `/api/v1`.

Do not add bot tokens or backend secrets to frontend environment files.

## Sync WEB Content CMS to Telegram local catalog

Telegram Mini App reads partners and offers from the local TG catalog endpoints (`/api/tg/partners` and `/api/tg/partners/{id}/offers`). Admin Bot writes real catalog content to the WEB Content Admin API, so production servers must periodically sync WEB Content CMS into the TG local database.

Required environment variables on the Telegram Mini App server:

```bash
export TELEGRAM_APP_DATABASE_URL='postgresql://...'
export WEB_CONTENT_API_BASE_URL='https://bloomclub.ru/api/content'
export TELEGRAM_ADMIN_API_TOKEN='...'
```

Run a safe preview first. Dry run prints how many records would be created/updated/pruned and does not insert/update catalog records:

```bash
cd /path/to/bloom_app_TELEGA_NEW/telegram-mini-app
npm run sync:content-to-tg-db -- --dry-run
```

Run the actual sync:

```bash
cd /path/to/bloom_app_TELEGA_NEW/telegram-mini-app
npm run sync:content-to-tg-db
```

Optional pruning is off by default. Use it only when you want WEB Content CMS to hide previously synced TG-local partners/offers that are no longer returned by WEB Content API. Pruning only marks synced rows inactive and does not delete demo/manual rows without `external_content_id`:

```bash
npm run sync:content-to-tg-db -- --prune
```

The sync creates missing `external_content_id` columns/indexes for `telegram_partners`, `telegram_partner_photos`, and `telegram_partner_offers` on write runs. Existing demo records are preserved because rows without `external_content_id` are not pruned or matched.

Typical server update flow:

```bash
cd /path/to/bloom_app_TELEGA_NEW
git pull
cd telegram-mini-app
npm install
npm run build
npm run sync:content-to-tg-db -- --dry-run
npm run sync:content-to-tg-db
# restart the configured Node/Python process manager after the build if required by hosting
```
