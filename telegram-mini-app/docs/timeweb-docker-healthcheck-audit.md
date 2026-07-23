# Timeweb Docker healthcheck audit for Telegram Mini App

## 1. Current production goal

The production goal is to deploy only the Telegram Mini App from this repository as a Docker-based Timeweb Cloud App Platform service. The target runtime process is the Node production server in `server/production-server.js`, not the Vite dev server and not the static React template server.

The expected production behavior is:

- the container starts a long-running Node HTTP server;
- the server binds to `0.0.0.0` and the configured container port, currently defaulting to `3000`;
- Timeweb routes external HTTP traffic to that container port;
- health endpoints return `200` without requiring database availability;
- frontend routes continue to serve the built Vite application from `dist`.

This audit was updated by a diagnostic-first PR that changes only the Telegram Mini App Docker/runtime diagnostics and docs. It does not change user UI, the WEB app, VK Mini App, bloomclub.ru site/backend, account linking backend, or real environment secret values.

## 2. What has been verified

Verified files and facts in this repository:

- `telegram-mini-app/package.json` has `start`, `start:production`, and `start:api` all mapped to `node server/production-server.js`; `build` runs `tsc --noEmit && vite build`.
- `telegram-mini-app/package-lock.json` is lockfile version 3 and describes the same application package/dependency set that `npm ci` will install inside the Docker image.
- root `Dockerfile` uses `node:24-alpine`, sets `WORKDIR /app`, copies `telegram-mini-app/package*.json`, runs `npm ci`, copies `telegram-mini-app/`, runs `npm run build`, exposes `3000`, and starts with direct `node server/production-server.js`.
- root `docker-compose.yml` builds from repository root with `dockerfile: Dockerfile`, maps host `3000` to container `3000`, sets `PORT=3000` and `HOST=0.0.0.0`, and does not override Dockerfile `CMD` or define an entrypoint.
- root `.dockerignore` excludes root-level `node_modules`, `dist`, `.git`, `.env`, logs, SQLite files, and Python cache/test artifacts.
- `telegram-mini-app/server/production-server.js` implements health endpoints, frontend serving, catalog API routes, DB initialization gating, and startup logging.
- `telegram-mini-app/vite.config.ts` builds two React entry points: `src/main.tsx` and `src/admin.tsx`, and defines frontend compile-time API/catalog flags.
- `telegram-mini-app/docs/timeweb-docker-deploy.md` documents Timeweb Docker deployment around root `Dockerfile`, Node.js 24, port `3000`, `/api/tg/health`, and required production environment variables.
- `telegram-mini-app/docs/timeweb-tg-db-setup.md` documents Timeweb PostgreSQL setup and Telegram catalog DB environment variables without requiring this audit to expose secret values.

Local checks for the diagnostic runtime mode are listed in the final answer. No `.env` file was read or committed.

## 3. Current repo deployment files

### package.json

Relevant scripts:

- `dev`: starts Vite dev server on `0.0.0.0`.
- `build`: runs TypeScript check and Vite build.
- `preview`: starts Vite preview on `0.0.0.0`.
- `start:production`: starts `node server/production-server.js`.
- `start`: starts the same production server.
- `start:api`: starts the same production server.

The scripts are internally consistent for Docker production: `node server/production-server.js` should start the Node server from the Docker image working directory `/app`, because `server/production-server.js` is copied to `/app/server/production-server.js`.

### package-lock.json

The lockfile is present in `telegram-mini-app/package-lock.json`. The Dockerfile copies it together with `package.json` via `COPY telegram-mini-app/package*.json ./`, so `npm ci` runs against a lockfile in `/app`. This means dependency installation in the image should be deterministic relative to the committed lockfile.

### Dockerfile

The Dockerfile is at repository root, not inside `telegram-mini-app/`. It uses the repository root as build context and explicitly copies files from `telegram-mini-app/` into image working directory `/app`.

Important behavior:

- `WORKDIR /app` means all subsequent `RUN` and `CMD` commands execute from `/app`.
- `COPY telegram-mini-app/package*.json ./` places `package.json` and `package-lock.json` at `/app/`.
- `RUN npm ci` executes in `/app` and uses `/app/package-lock.json`.
- `COPY telegram-mini-app/ ./` copies application source, server code, docs, tests, and other files from the app subdirectory into `/app`.
- `RUN npm run build` should create `/app/dist` if TypeScript and Vite build succeed.
- `CMD ["node", "server/production-server.js"]` runs the production server directly from `/app`, without the npm runtime wrapper.
- There is no `ENTRYPOINT`.
- There is no Docker `HEALTHCHECK` instruction.
- `EXPOSE 3000` is metadata and does not itself publish or force traffic to the port.

### docker-compose.yml

The compose file defines one service, `telegram-mini-app`:

- build context is `.` (repository root);
- Dockerfile path is `Dockerfile`;
- build args pass through Vite compile-time variables;
- `ports` maps `3000:3000` for local Docker/Compose use;
- runtime environment sets `NODE_ENV=production`, `PORT=3000`, `HOST=0.0.0.0`, DB URL, admin token, and `TELEGRAM_AUTO_INIT_DB` defaulting to `false`;
- there is no `command` override;
- there is no `entrypoint` override.

For Timeweb App Platform, the compose `ports` section may be ignored or partially interpreted depending on the selected deployment mode. Timeweb's log `Found 1 HTTP ports: ["3000/tcp"]` shows it detected `3000/tcp`, but does not prove that the healthcheck is configured to request the intended path or that the platform has selected this port as the externally routed application port.

### .dockerignore

The root `.dockerignore` excludes root-level `node_modules`, `dist`, `.git`, `.env`, logs, DB files, and cache artifacts. Because the app's local dependencies are under `telegram-mini-app/node_modules`, the pattern `node_modules` may or may not exclude nested `telegram-mini-app/node_modules` depending on Docker ignore semantics and version. This is not the most likely healthcheck root cause because the build reportedly passes and `npm ci` installs production image dependencies before copying the source, but it is a secondary image hygiene issue worth checking in a later cleanup PR.

### vite config

The Vite config:

- uses `@vitejs/plugin-react`;
- defines `__BLOOM_API_BASE_URL__`, `__TG_LOCAL_CATALOG_ENABLED__`, and `__TG_API_BASE_URL__` from env/build args;
- builds a Rollup input map with `main` and `admin` entry points.

This config affects frontend build output, not the Node server's port binding or health endpoint routing.

## 4. Node server behavior

### Port selection

The server computes `PORT` from the first available value among:

1. `process.env.PORT`
2. `process.env.APP_PORT`
3. `process.env.HTTP_PORT`
4. `process.env.SERVER_PORT`

The value is converted to a number and must be a positive integer. Invalid, empty, missing, zero, negative, or non-integer values fall back to `3000`.

### Host binding

The server uses a hardcoded host:

```text
0.0.0.0
```

This is the correct bind host for a Docker container that must accept traffic from the platform network namespace. The observed startup log also confirms `host=0.0.0.0` and `actual_port=3000`.

### Health and frontend endpoints

The server normalizes a trailing slash away except for root. Therefore `/health/` is treated like `/health`, `/ready/` like `/ready`, and `/api/tg/health/` like `/api/tg/health`.

Endpoint behavior from code inspection:

| Request | Expected response |
| --- | --- |
| `GET /ready` | `200 text/plain`, body `ok`, `cache-control: no-store` |
| `HEAD /ready` | `200`, empty body, `cache-control: no-store` |
| `GET /health` | `200 application/json`, body includes `status: ok` and service name |
| `HEAD /health` | `200`, empty body, `cache-control: no-store` |
| `GET /api/tg/health` | `200 application/json`, body includes `status: ok` and service name |
| `HEAD /api/tg/health` | `200`, empty body, `cache-control: no-store` |
| `GET /` | `200 text/html`; serves `dist/index.html` if present; if missing, returns a minimal fallback HTML page with body `ok` |
| `HEAD /` | `200`; same headers path as `GET /`, empty body |

Important distinction: `/api/tg/health/db` is DB-dependent and returns `503` when `TELEGRAM_APP_DATABASE_URL` is missing or the DB query fails. It should not be used as the platform readiness/liveness healthcheck unless database readiness is intentionally required for deploy success.

### Diagnostic request logs

During the first 5 minutes after startup, the server logs every completed HTTP request. After that diagnostic window, it continues to log completed requests for health paths `/`, `/ready`, `/health`, and `/api/tg/health`.

The log format includes method, normalized pathname without query string, response status code, elapsed milliseconds, user-agent when present, and remote address when present. If Timeweb healthcheck reaches the Node server, a line beginning with `http request` should appear after response completion.

The observed absence of request log lines is important evidence. It suggests either Timeweb is not reaching this Node process, is checking a different port/container, or runtime logs being viewed are not the logs that include request output.

### Self-termination behavior

The server does not set timers that intentionally exit the process. It creates an HTTP server and calls `server.listen(PORT, HOST, ...)`. If startup succeeds, the Node event loop should remain alive.

The code now installs `SIGTERM` and `SIGINT` handlers, logs safe shutdown facts, calls `server.close()`, and exits after close. A 10-second forced-exit timeout prevents indefinite shutdown hangs.

### `process.exit`, `throw`, and startup failure conditions

There is no direct `process.exit(...)` call in the server file. Startup DB initialization can fail when `TELEGRAM_AUTO_INIT_DB=true` and database configuration/permissions are invalid:

- `initDatabaseIfEnabled()` returns immediately when auto init is disabled.
- When auto init is enabled, it calls `getPool()`.
- If no `TELEGRAM_APP_DATABASE_URL` is configured, it throws `database_not_configured`.
- If the DB connection, schema creation, transaction, or permissions fail, the error is rethrown.
- `start()` catches the failure, logs `Telegram catalog DB auto init failed; check database target and schema permissions.`, sets `process.exitCode = 1`, and returns before creating the HTTP server.

That failure mode does not match the provided Timeweb symptom because the production server startup log was observed. If the startup log exists, the HTTP server reached `listen()` successfully.

Other runtime request handlers catch database/API errors and return HTTP error responses rather than intentionally exiting the process.

### `TELEGRAM_AUTO_INIT_DB=false`

When `TELEGRAM_AUTO_INIT_DB` is anything other than exact string `true`, auto init is disabled. With `false`, startup does not require DB connectivity or schema permissions. The server can start and the non-DB health endpoints remain `200`.

### `TELEGRAM_APP_DATABASE_URL` configured or missing

When `TELEGRAM_APP_DATABASE_URL` is configured:

- `db_configured=true` appears in the startup log;
- DB-backed endpoints create a lazy PostgreSQL pool on first use;
- `/api/tg/health/db` validates the DB with `SELECT 1`;
- catalog endpoints query PostgreSQL.

When `TELEGRAM_APP_DATABASE_URL` is missing:

- `db_configured=false` appears in startup log;
- non-DB health endpoints still return `200`;
- `/api/tg/health/db` returns `503 database_not_configured`;
- public partners list returns `{ "items": [] }` instead of failing startup;
- status endpoint returns `503 database_not_configured`.

Therefore, database configuration should not cause the observed Timeweb healthcheck kill unless Timeweb is checking `/api/tg/health/db` or another DB-dependent path.

## 5. Dockerfile behavior

### Working directory and copied files

The Dockerfile sets `WORKDIR /app`. It then copies app package metadata from the repo subdirectory into the image root of the app:

```dockerfile
COPY telegram-mini-app/package*.json ./
RUN npm ci
COPY telegram-mini-app/ ./
```

After these instructions:

- image `package.json` is at `/app/package.json`;
- image lockfile is at `/app/package-lock.json`;
- server is at `/app/server/production-server.js`;
- Vite config is at `/app/vite.config.ts`;
- build output is expected at `/app/dist` after `npm run build`.

This layout is consistent with the `CMD` script, so npm is not expected to run from the wrong directory if the Dockerfile `CMD` is honored.

### Build commands

`npm ci` should run before the full source copy, which is cache-friendly and based on the lockfile. `npm run build` should create `dist` during image build. The provided context says Timeweb Dockerfile build passes, which strongly implies `npm ci`, TypeScript check, and Vite build have succeeded in the platform build environment.

### Runtime command and signal surface

The Dockerfile uses:

```dockerfile
CMD ["node", "server/production-server.js"]
```

This starts Node directly, without the npm runtime wrapper. If Timeweb sends `SIGTERM` after a healthcheck timeout, the application-level signal handler should log the signal, uptime, and pid before closing the HTTP server.

### ENTRYPOINT, HEALTHCHECK, and EXPOSE

There is no `ENTRYPOINT`. There is no Docker `HEALTHCHECK`. `EXPOSE 3000` declares image metadata for port detection but does not configure the Timeweb healthcheck path or guarantee external routing by itself.

### WORKDIR versus Timeweb

`WORKDIR /app` does not appear to conflict with Timeweb Dockerfile mode. It is a normal container-local path. If Timeweb honors the image `CMD`, Node runs from `/app` and finds `server/production-server.js`.

If Timeweb overrides the command outside Dockerfile mode, that would be a platform setting issue to verify in screenshots. The intended image command now runs Node directly.

## 6. Docker Compose behavior

The compose configuration is valid for local Docker Compose smoke testing, but it should not be treated as proof of Timeweb App Platform routing behavior.

Key observations:

- `build.context: .` is correct because the Dockerfile is at repository root and references `telegram-mini-app/...` paths.
- `build.dockerfile: Dockerfile` is correct for the root Dockerfile.
- `ports: "3000:3000"` is correct for local host-to-container testing.
- `environment.PORT=3000` and `environment.HOST=0.0.0.0` align with `EXPOSE 3000` and the server defaults.
- No compose `command` or `entrypoint` conflicts with Dockerfile `CMD`.
- Build args set Vite compile-time values and do not affect Node healthcheck routing at runtime.

Potential Timeweb caveat: App Platform Dockerfile deployments often use their own port detection and service routing settings. They may ignore `docker-compose.yml` entirely in Dockerfile mode or use only selected metadata. Therefore, adding `ports` to compose may not change Timeweb healthcheck behavior unless the selected Timeweb deployment mode explicitly uses compose and maps the service/port accordingly.

## 7. Timeweb observed symptoms

Provided facts:

- Timeweb build passes.
- Timeweb reports `Found 1 HTTP ports: ["3000/tcp"]`.
- Container starts.
- Timeweb begins app health checking.
- Timeweb waits for container healthcheck to pass.
- Health status remains `starting`.
- Deployment eventually fails and the container receives `SIGTERM`.
- the direct Node runtime should log `received SIGTERM` with safe shutdown fields.
- Application startup log exists: `Telegram catalog production server listening on 0.0.0.0:3000; actual_port=3000; host=0.0.0.0; db_configured=true; auto_init=false; ...`.
- After request logging was added for health paths, no health request log lines were visible.

Interpretation:

1. The Node server starts and binds successfully to `0.0.0.0:3000`.
2. `TELEGRAM_AUTO_INIT_DB=false` prevents DB auto-init from blocking startup.
3. The observed `SIGTERM` is most likely sent by Timeweb after the platform healthcheck does not reach a passing state.
4. The absence of health request logs is stronger evidence than the npm SIGTERM line. It indicates the failing healthcheck probably does not hit `/ready`, `/health`, `/api/tg/health`, or `/` on this Node server, or those request logs are not being viewed in the relevant runtime log stream.

## 8. Most likely root causes ranked

### 1. Timeweb healthcheck path is different from the intended endpoint

Most likely.

If Timeweb is checking an implicit path such as an internal default, a configured stale path, or a path outside `/ready`, `/health`, `/api/tg/health`, and `/`, then the current health request logger would not emit lines. If the path starts with `/api/` and is not implemented, it returns JSON `404`. If it is another frontend route, most unknown non-API routes return text `404`, except `/` and `/tg-admin`.

This matches:

- server startup log exists;
- no logged request for known health paths;
- health status stays `starting`;
- platform sends `SIGTERM` after timeout.

### 2. Timeweb requires an explicit application/container port setting even though it detected `EXPOSE 3000`

Very likely.

`Found 1 HTTP ports: ["3000/tcp"]` proves detection, not necessarily readiness routing. Timeweb may still require the App Platform service port/container port field to be set to `3000`, or it may have a stale port setting from an earlier Node/Vite/static deployment. If the healthchecker targets a different internal port, no Node request log will appear.

This covers causes B and C from the task list: wrong port, or detected port not selected as the actual healthcheck/routing port.

### 3. Timeweb is not using `docker-compose.yml` ports in the selected deployment mode

Likely.

The compose `ports` mapping is helpful locally, but App Platform Dockerfile mode may ignore it. If the user expects `docker-compose.yml` to force Timeweb health routing, that assumption may be wrong. The platform log detecting `3000/tcp` from the Dockerfile still leaves open whether the app's service port setting points to `3000`.

This maps to cause I and partly C.

### 4. Node receives SIGTERM from the platform after healthcheck timeout

Likely as a symptom, not root cause.

The npm error lines are consistent with Timeweb killing the container after a readiness timeout. They do not prove that npm failed to start the application. The startup log proves npm successfully launched Node. Direct Node `CMD` would make logs cleaner, but it probably will not fix the healthcheck by itself unless Timeweb handles npm-wrapped processes poorly.

This maps to cause E.

### 5. Timeweb healthcheck uses a method/protocol/Host combination the server handles differently

Possible, but less likely for known paths.

For `/ready`, `/health`, `/api/tg/health`, and `/`, both `GET` and `HEAD` should return `200`. The server constructs `new URL()` with a fallback host and should not reject unusual `Host` headers. If the platform checks HTTPS directly inside the container instead of HTTP, or checks a non-normalized absolute URL in an unexpected way, that could fail before Node routing. However, normal App Platform container checks are usually HTTP to the container port.

This maps to cause F.

### 6. Healthcheck path `/` depends on `dist` or static frontend behavior

Possible but currently less likely.

If Timeweb checks `/`, the server logs `/` and returns `200`. If `dist/index.html` is missing, `/` still returns fallback HTML with `200`. Therefore `/` should pass a basic HTTP 200 check. Other frontend routes can return `404`, and `/tg-admin` returns `500` if `dist` is missing, but the Docker build reportedly passes and should create `dist`.

This maps to cause G.

### 7. Bind host is wrong

Unlikely.

The code hardcodes `0.0.0.0`, and the observed startup log confirms it. Binding to `127.0.0.1` would be a classic Docker health routing issue, but it does not match current facts.

This maps to cause H.

### 8. Timeweb does not support a long-running server in the selected Dockerfile mode

Less likely.

The platform starts the container and checks health, which is exactly the flow for long-running app services. This would become plausible only if screenshots show the service was created as a job/build-only/static mode rather than a web service mode.

This maps to cause D.

## 9. Required Timeweb screenshots/checks from user

Ask the user for screenshots or copied values from Timeweb without secrets.

### Screenshots to request

1. App deployment mode page showing whether the app is Dockerfile, Docker Compose, static, Node template, worker, or web service mode.
2. Build settings showing repository, branch, Dockerfile path, build context, and whether compose is enabled/ignored.
3. Runtime/start command settings showing whether Timeweb overrides Dockerfile `CMD`.
4. Port/network settings showing detected ports, selected container port, public HTTP port, and protocol.
5. Healthcheck settings showing path, method, expected status, timeout, interval, retries, and initial delay if Timeweb exposes these fields.
6. Environment variable settings showing variable names only or values redacted. Required names to verify: `PORT`, `TELEGRAM_APP_DATABASE_URL`, `TELEGRAM_AUTO_INIT_DB`, `NODE_ENV`, `VITE_API_BASE_URL`, `VITE_TG_LOCAL_CATALOG_ENABLED`, and `VITE_TG_API_BASE_URL`.
7. Runtime logs page after container start, not only deploy/build logs.
8. Events/activity page around the failed deploy showing exact timestamps for container start, healthcheck start, status changes, and SIGTERM/stop event.

### Environment checks

Verify without exposing values:

- `PORT` is set to `3000` or omitted. It must not be set to a different port unless Timeweb routes to that same port.
- `TELEGRAM_AUTO_INIT_DB` is `false` for this healthcheck debugging phase.
- `TELEGRAM_APP_DATABASE_URL` exists only if DB-backed catalog is intended, but non-DB health endpoints should not depend on it.
- `VITE_*` variables are build-time frontend values and will not fix container healthcheck routing by themselves.
- No secret values should be pasted into chat or committed.

### Runtime logs versus deploy logs

The user should open logs from the running container/runtime stream after `Container started`, not only build/deploy logs. The key question is whether request logs appear after the platform starts health checking.

Look for:

- startup line with `listening on 0.0.0.0:3000`;
- any line beginning with `http request`;
- request path and status code in that line;
- whether the user-agent indicates a Timeweb healthchecker;
- whether there are errors before SIGTERM;
- exact time gap between startup log and SIGTERM.

### URLs to open if the container stays running long enough

If Timeweb exposes a temporary or production app URL during the `starting` phase, open these in a browser or with curl from outside:

1. `https://<app-domain>/ready` — expected `200` and body `ok`.
2. `https://<app-domain>/health` — expected JSON `200`.
3. `https://<app-domain>/api/tg/health` — expected JSON `200`.
4. `https://<app-domain>/` — expected frontend HTML `200`.
5. Do not use `/api/tg/health/db` as the platform healthcheck until DB connectivity is confirmed.

### How to know healthcheck reaches Node

Healthcheck reaches Node if runtime logs include a line like:

```text
http request method=GET pathname=/api/tg/health statusCode=200 elapsedMs=1 user_agent="..." remoteAddress="..."
```

or the same pattern for `HEAD`, `/ready`, `/health`, or `/`.

If such a line appears with `statusCode=200` but Timeweb still fails, then the next investigation should focus on Timeweb's expected protocol/status/body, selected healthcheck target, reverse proxy, or a mismatch between runtime log stream and health status.

### How to know healthcheck does not reach Node

Healthcheck likely does not reach Node if all are true:

- startup log confirms `0.0.0.0:3000`;
- Timeweb says it is checking health;
- no `http request` lines appear for several healthcheck intervals;
- container is killed after timeout.

Then the next checks are Timeweb selected port, healthcheck path, service mode, and whether compose ports are ignored.

## 10. Implemented diagnostic PR scope

This diagnostic PR intentionally keeps the repo-side change small and focused on runtime facts:

1. Docker now starts the production server with direct Node execution: `CMD ["node", "server/production-server.js"]`.
2. Docker runtime defaults now include `ENV HOST=0.0.0.0` and `ENV PORT=3000`.
3. `docker-compose.yml` keeps `ports: "3000:3000"`, adds `HOST=0.0.0.0`, and does not override the Dockerfile command.
4. The Node server reads `HOST` from the environment, logs safe startup fields, logs `SIGTERM` / `SIGINT`, and closes the HTTP server before exit.
5. The Node server logs every HTTP request during the first 5 minutes after startup, while health path logs continue after the diagnostic window.

Most likely actual fix outside the repo may still be a Timeweb setting change: explicitly set the selected container/application port to `3000` and the healthcheck path to `/`, then fallback to `/ready` or `/api/tg/health`.

## 11. Things still not to change

For this repository and this diagnostic scope, do not change:

- React user UI or user-facing routes;
- Telegram login/profile/subscription/account linking behavior;
- `package.json`;
- `package-lock.json`;
- Timeweb DB schema or database contents;
- `.env` files;
- secrets or token values;
- the main `bloomclub.ru` website backend;
- account linking backend on the website;
- VK Mini App;
- other repositories such as `Kosmos327/fed_women_club_WEB` or `Kosmos327/fed_women_club_mini-app`.

## Diagnostic runtime mode

The follow-up diagnostic runtime mode changes the container runtime command to direct Node execution:

```dockerfile
CMD ["node", "server/production-server.js"]
```

This removes the npm wrapper from the runtime signal path and should make `SIGTERM` / `SIGINT` behavior visible in application logs.

The runtime should expose and use these safe defaults:

```dotenv
NODE_ENV=production
PORT=3000
HOST=0.0.0.0
```

The Node server listens on `HOST` with fallback `0.0.0.0`. The port selection order is `PORT`, `APP_PORT`, `HTTP_PORT`, `SERVER_PORT`, `WEB_PORT`, `LISTEN_PORT`, `CONTAINER_PORT`, `APP_PLATFORM_PORT`, `TIMEWEB_PORT`, then `3000`.

During the first 5 minutes after startup, the server logs every incoming HTTP request using safe fields only: method, pathname without query string, status code, user-agent when present, elapsed milliseconds, and remote address when present. Health paths `/`, `/ready`, `/health`, and `/api/tg/health` continue to log after the first 5 minutes.

Use these runtime facts in Timeweb:

- If request logs are absent, Timeweb healthcheck traffic is not reaching the Node server or is targeting a different port/container.
- If request logs are present with `statusCode=200`, but Timeweb still terminates the container, focus on Timeweb healthcheck success criteria, selected path, and application/container port settings.

Set the healthcheck path in this order:

1. Start with `/`.
2. If needed, fallback to `/ready`.
3. If needed, fallback to `/api/tg/health`.

If Timeweb exposes a separate application port or container port setting, set it to `3000`.

## Runtime port diagnostics

Startup now includes a safe `port_env_candidates` diagnostic object. It is limited to the whitelisted runtime names `PORT`, `APP_PORT`, `HTTP_PORT`, `SERVER_PORT`, `WEB_PORT`, `LISTEN_PORT`, `CONTAINER_PORT`, `APP_PLATFORM_PORT`, `TIMEWEB_PORT`, `HOST`, `HOSTNAME`, and `NODE_ENV`; missing values are reported as `unset`, and long values are truncated.

Use this section when Timeweb shows container startup but no request logs:

- Check the startup log for `port_env_candidates` before assuming the Node server is unhealthy.
- If Timeweb passes a different port through a supported variable, the server should choose it. The parser accepts positive integers and URL-like values with ports, for example `tcp://0.0.0.0:3000` and `http://0.0.0.0:3000`.
- If a candidate is invalid, the server logs a safe warning and skips that value.
- If all port candidates are `unset` or `3000`, but Timeweb occupied ports still do not include `3000` and no `http request ...` lines appear, the likely failure is Timeweb routing or container-port autodetection outside this Node process.

When HTTP routing works, verify `GET /debug/runtime-port`. It returns JSON with `status`, `actual_port`, `host`, whitelisted `port_candidates`, and `uptime_seconds`. It intentionally excludes `TELEGRAM_APP_DATABASE_URL`, `TELEGRAM_ADMIN_API_TOKEN`, the full `process.env`, cookies, authorization headers, and request bodies. Because this endpoint requires successful routing, the startup `port_env_candidates` log remains the primary diagnostic signal before Timeweb kills an unreachable container.
