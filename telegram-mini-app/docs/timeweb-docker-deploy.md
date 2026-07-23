# Timeweb Docker deploy for Telegram Mini App

This deploy mode runs the Telegram Mini App as one production Docker app:

- Vite frontend is built during Docker image build.
- Node.js production server serves `/`, `/tg-admin`, static Vite assets, and `/api/tg/*` JSON endpoints.
- PostgreSQL is used as the Telegram catalog database.
- Python, `pip`, Vite preview, and a second always-on app are not used by Docker runtime.

## Timeweb Docker settings

Use these settings for the Timeweb app:

```text
Type: Docker
Mode: Dockerfile
Repository: Kosmos327/-fed_women_club_mini-app_TELEGA
Branch: main
Dockerfile path: Dockerfile
Port: 3000
Region: Amsterdam, if the PostgreSQL database is in the same region
Network: keep the existing private network unless Timeweb requires another value
```

The Dockerfile is in the repository root. It expects the Timeweb build context to be the repository root and then copies/builds the `telegram-mini-app` directory inside the image.

## Timeweb Docker Compose fallback

If the Dockerfile app starts successfully but Timeweb healthchecks do not reach the Node.js server, deploy the same image through Docker Compose instead. This is useful when the logs show the server listening on `0.0.0.0:3000`, Timeweb detects `3000/tcp`, but there are no request log lines for `/`, `/ready`, `/health`, or `/api/tg/health` before the container receives `SIGTERM`.

Use these settings in Timeweb:

```text
Type: Docker
Mode: Docker Compose
Repository: Kosmos327/-fed_women_club_mini-app_TELEGA
Branch: main
Docker Compose path: docker-compose.yml
Healthcheck path: /
```

The repository-root `docker-compose.yml` defines the `telegram-mini-app` service, builds from the existing root `Dockerfile`, and explicitly publishes the Node.js server with:

```yaml
ports:
  - "3000:3000"
```

Keep runtime secrets in Timeweb environment variables only. The compose file references `TELEGRAM_APP_DATABASE_URL` and `TELEGRAM_ADMIN_API_TOKEN` from the deployment environment and does not contain real secret values.

## Build env / build args

Set these values for the Docker build step:

```dotenv
VITE_API_BASE_URL=https://bloomclub.ru/api/v1
VITE_TG_LOCAL_CATALOG_ENABLED=true
VITE_TG_API_BASE_URL=
```

`VITE_*` variables are compiled into the frontend at `npm run build` time. Because this Dockerfile runs `npm run build` inside `docker build`, these values must be available as build args/build env before the build starts. The Dockerfile exposes them as `ARG` and then maps them to `ENV` before `npm run build`.

`VITE_TG_API_BASE_URL=` should stay empty for the one-domain production mode. In that mode the frontend calls the current origin with relative URLs such as `/api/tg/partners`.

## Runtime env

Set runtime environment variables on the deployed Docker app:

```dotenv
TELEGRAM_APP_DATABASE_URL=postgresql://gen_user:<password>@192.168.0.4:5432/default_db
TELEGRAM_ADMIN_API_TOKEN=<secret>
TELEGRAM_AUTO_INIT_DB=true
NODE_ENV=production
PORT=3000
HOST=0.0.0.0
```

Keep `PORT=3000` when Timeweb does not assign a runtime port automatically. If Timeweb sets its own port variable, the production server reads `PORT`, `APP_PORT`, `HTTP_PORT`, or `SERVER_PORT` in that order and falls back to `3000` when the selected value is missing, non-numeric, or less than or equal to zero.

Do not set runtime secrets as Docker build args. `TELEGRAM_APP_DATABASE_URL`, `TELEGRAM_ADMIN_API_TOKEN`, and `TELEGRAM_AUTO_INIT_DB` are runtime-only variables.

Do not add `TELEGRAM_BOT_TOKEN` or `BOT_TOKEN` to this app. Do not commit real secrets to the repository.

## Server behavior

The production server is `telegram-mini-app/server/production-server.js` and is started by:

```bash
node server/production-server.js
```

It listens on `HOST` with fallback `0.0.0.0` and uses the first configured port from `PORT`, `APP_PORT`, `HTTP_PORT`, and `SERVER_PORT`, with a safe fallback to `3000`. The Dockerfile exposes port `3000` and does not run `vite preview`.

The Dockerfile exposes port `3000` but intentionally does not define a container `HEALTHCHECK`. Configure Timeweb's own healthcheck path in the Timeweb panel instead: use `/` as the first healthcheck path. If needed, fallback to `/ready`, then `/api/tg/health`. If the Dockerfile app healthcheck does not reach the Node.js server and no request logs appear, verify Timeweb port settings or switch the Timeweb app to Docker Compose mode with `Docker Compose path: docker-compose.yml`, explicit `3000:3000` port publishing, and healthcheck path `/`.

## PostgreSQL auto init

When `TELEGRAM_AUTO_INIT_DB=true`, the production server initializes only the Telegram catalog schema:

- runs idempotent `CREATE TABLE IF NOT EXISTS` statements;
- runs idempotent `CREATE INDEX IF NOT EXISTS` statements;
- does not delete data;
- does not overwrite data;
- does not run seed scripts automatically.

After the first successful deploy and smoke test, set:

```dotenv
TELEGRAM_AUTO_INIT_DB=false
```

Then redeploy or restart the Docker app. This avoids schema initialization on every future start while preserving the existing data.

## Post-deploy checks

After a successful launch, run:

```bash
curl -i https://<TG_DOCKER_APP_DOMAIN>/ready
curl -i https://<TG_DOCKER_APP_DOMAIN>/health
curl -i https://<TG_DOCKER_APP_DOMAIN>/api/tg/health
curl -i https://<TG_DOCKER_APP_DOMAIN>/api/tg/health/db
curl -i https://<TG_DOCKER_APP_DOMAIN>/api/tg/status
curl -i https://<TG_DOCKER_APP_DOMAIN>/api/tg/partners
curl -i https://<TG_DOCKER_APP_DOMAIN>/tg-admin
```

Expected results:

- `/ready` returns `200 text/plain` with `ok`.
- Set `/` as the first Timeweb healthcheck path.
- If `/` does not pass, fallback to `/ready`, then `/api/tg/health`.
- `/api/tg/health` returns JSON, for example `{"status":"ok","service":"telegram-local-catalog"}`.
- `/health` returns the same JSON payload as `/api/tg/health`.
- `/` returns the frontend HTML when `dist/index.html` exists, or a minimal `200 text/html` fallback when it is missing.
- `/tg-admin` returns the frontend admin route HTML.
- `/api/tg/health/db` returns database JSON when `TELEGRAM_APP_DATABASE_URL` is configured and reachable.
- `/api/tg/partners` returns JSON with an `items` array.

Local Docker smoke test from repository root:

```bash
docker build \
  --build-arg VITE_API_BASE_URL=https://bloomclub.ru/api/v1 \
  --build-arg VITE_TG_LOCAL_CATALOG_ENABLED=true \
  --build-arg VITE_TG_API_BASE_URL= \
  -t telegram-mini-app-test .

docker run --rm -p 3000:3000 \
  -e PORT=3000 \
  -e HOST=0.0.0.0 \
  -e TELEGRAM_AUTO_INIT_DB=false \
  telegram-mini-app-test
```

In another terminal:

```bash
curl -i http://127.0.0.1:3000/ready
curl -i http://127.0.0.1:3000/health
curl -i http://127.0.0.1:3000/api/tg/health
curl -i http://127.0.0.1:3000/
curl -i http://127.0.0.1:3000/tg-admin
```

## Healthcheck troubleshooting

If Timeweb starts the container and then stops it after failed healthchecks, first confirm that the Timeweb panel healthcheck path is set to `/` (then fallback to `/ready` or `/api/tg/health`) and then open the application logs and look for the startup line:

```text
Telegram catalog production server listening ...
```

That line safely prints `actual_port`, `host`, `pid`, `node_version`, `uptime_seconds=0`, `db_configured`, `auto_init`, `port_env_candidates`, and `health_paths=/,/ready,/health,/api/tg/health` without logging database URLs, passwords, admin tokens, request bodies, cookies, authorization headers, or query strings.

During the first 5 minutes after startup, all incoming HTTP requests produce lightweight diagnostic log lines with only `method`, `pathname`, `statusCode`, `elapsedMs`, `user_agent` when present, and `remoteAddress` when present. Health requests to `/`, `/ready`, `/health`, and `/api/tg/health` continue to log after that 5-minute window. The server does not log query strings, cookies, authorization headers, request bodies, environment variables, database URLs, passwords, or admin tokens in these logs.

If no health request logs appear after Timeweb starts healthchecking, Timeweb is not reaching the Node.js server. In that case, use the Docker Compose deployment variant in Timeweb, set `Docker Compose path: docker-compose.yml`, set the Timeweb healthcheck path to `/`, and rely on the compose `ports` mapping to explicitly publish `3000:3000`. If health request logs appear with `statusCode=200` but the container is still stopped by Timeweb, treat it as a platform healthcheck, routing, or port configuration problem rather than a Node.js response problem.

## BotFather switch

Change the Telegram Mini App URL in BotFather only after all Docker-domain checks pass and the Mini App opens correctly on the Docker app domain.

Recommended order:

1. Deploy Docker app.
2. Check `/ready`, `/health`, `/api/tg/health`, `/api/tg/health/db`, `/api/tg/status`, `/api/tg/partners`, `/`, and `/tg-admin`.
3. Set `TELEGRAM_AUTO_INIT_DB=false` and redeploy/restart.
4. Re-check the same endpoints.
5. Change the Mini App URL in BotFather to the Docker app domain.
6. Check the Mini App inside Telegram.
7. Only after the Telegram check succeeds, delete the old React/static app to avoid paying for two applications.

## Rollback

If the Docker app fails after switching BotFather:

1. Return the Mini App URL in BotFather to the old React/static domain.
2. Keep the old app until the Docker app has been fully verified.
3. Use `VITE_TG_LOCAL_CATALOG_ENABLED=false` only when rolling back to the legacy WEB catalog behavior.
4. Do not delete or re-seed the PostgreSQL database as part of rollback.

## Scope guard

This Docker deploy changes only the Telegram Mini App repository. It does not require changes to the WEB repo, VK Mini App, `bloomclub.ru`, the main site backend, or account linking backend.

## Diagnostic runtime mode

This deployment intentionally runs the production Node server directly from the Dockerfile command:

```dockerfile
CMD ["node", "server/production-server.js"]
```

There is no npm wrapper in the runtime command. This makes Timeweb shutdown signals and Node server logs easier to read.

The container runtime should keep these safe defaults:

```dotenv
NODE_ENV=production
PORT=3000
HOST=0.0.0.0
```

The server listens on `HOST` with fallback `0.0.0.0`, and it selects the port from `PORT`, `APP_PORT`, `HTTP_PORT`, `SERVER_PORT`, `WEB_PORT`, `LISTEN_PORT`, `CONTAINER_PORT`, `APP_PLATFORM_PORT`, `TIMEWEB_PORT`, then `3000`.

For the first 5 minutes after startup, runtime logs should include one safe request log line for every incoming HTTP request. The log line includes only method, pathname without query string, status code, user-agent when present, elapsed milliseconds, and remote address when present. Health endpoint logs continue after the 5-minute diagnostic window.

Use the request logs to diagnose Timeweb healthchecks:

- If request logs are absent, the Timeweb healthcheck is not reaching the Node server. Check Timeweb routing, application/container port fields, and whether the deployed app is using this repository and image.
- If request logs are present with `statusCode=200`, but Timeweb still stops the deploy, the likely issue is Timeweb healthcheck or port configuration rather than the Node server response.

Set the Timeweb healthcheck path in this order:

1. First try `/`.
2. Fallback to `/ready`.
3. Fallback to `/api/tg/health`.

Also check whether Timeweb has a separate application port or container port field. If it exists, set it to `3000`.

## Runtime port diagnostics

The production server now logs a safe `port_env_candidates` object during startup. This object includes only these whitelisted names: `PORT`, `APP_PORT`, `HTTP_PORT`, `SERVER_PORT`, `WEB_PORT`, `LISTEN_PORT`, `CONTAINER_PORT`, `APP_PLATFORM_PORT`, `TIMEWEB_PORT`, `HOST`, `HOSTNAME`, and `NODE_ENV`. Missing values are shown as `unset`, and long values are truncated before logging.

If Timeweb startup logs show no `http request ...` lines before the healthcheck timeout, first check the startup log for `port_env_candidates`:

- If Timeweb provides a different runtime port in one of the supported variables, the server should select that value automatically. Positive integer values are accepted, and URL-style values such as `tcp://0.0.0.0:3000` or `http://0.0.0.0:3000` are parsed for their port.
- If a supported port variable is present but invalid, the server skips it and logs a safe warning with only the whitelisted variable name and truncated value.
- If all port variables are `unset` or `3000`, but port `3000` is absent from the Timeweb occupied ports list and request logs are still absent, treat the issue as Timeweb routing/container-port autodetection rather than a Node handler problem.

After the server is reachable, `GET /debug/runtime-port` returns the selected `actual_port`, `host`, whitelisted `port_candidates`, and process `uptime_seconds`. This endpoint does not print `TELEGRAM_APP_DATABASE_URL`, `TELEGRAM_ADMIN_API_TOKEN`, the full environment, cookies, authorization headers, or request bodies. The endpoint is useful only after a successful HTTP connection; the startup `port_env_candidates` log is the diagnostic source that appears even before a healthcheck timeout.

## Security headers and CSP rollout

The Node production server adds baseline browser hardening headers on every response:

- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`
- `Strict-Transport-Security: max-age=15552000; includeSubDomains`

CSP is deployed in report-only mode by default to preserve the current Telegram Mini App deploy flow while validating Telegram clients:

```dotenv
TELEGRAM_SECURITY_HEADERS_MODE=report-only
```

After validating `curl -I`, Telegram Android/iOS/Desktop, and the web Telegram client, switch to enforcement with:

```dotenv
TELEGRAM_SECURITY_HEADERS_MODE=enforce
```

Rollback for CSP-specific regressions is to set `TELEGRAM_SECURITY_HEADERS_MODE=report-only` and restart `bloomclub-tg.service`. Use `TELEGRAM_SECURITY_HEADERS_MODE=off` only as a temporary emergency rollback for the whole repo-owned header layer.
