import http from 'node:http';
import { createReadStream, readFileSync } from 'node:fs';
import { access, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PORT_ENV_CANDIDATES = [
  'PORT',
  'APP_PORT',
  'HTTP_PORT',
  'SERVER_PORT',
  'WEB_PORT',
  'LISTEN_PORT',
  'CONTAINER_PORT',
  'APP_PLATFORM_PORT',
  'TIMEWEB_PORT',
];
const SAFE_RUNTIME_ENV_CANDIDATES = [...PORT_ENV_CANDIDATES, 'HOST', 'HOSTNAME', 'NODE_ENV'];
const FALLBACK_PORT = 3000;
const HOST = process.env.HOST || '0.0.0.0';


function readPackageVersion() {
  try {
    const packageJson = JSON.parse(readFileSync(path.join(PROJECT_ROOT, 'package.json'), 'utf8'));
    return String(packageJson.version || 'unknown-build');
  } catch {
    return 'unknown-build';
  }
}


function readDistBuildId() {
  try {
    return readFileSync(path.join(DIST_DIR, 'build-id.txt'), 'utf8').trim() || '';
  } catch {
    return '';
  }
}

function safeEnvValue(value) {
  if (value === undefined) {
    return 'unset';
  }
  const stringValue = String(value);
  if (stringValue.length > 80) {
    return `${stringValue.slice(0, 80)}…`;
  }
  return stringValue;
}

function getSafeRuntimeEnvCandidates() {
  return Object.fromEntries(SAFE_RUNTIME_ENV_CANDIDATES.map((name) => [name, safeEnvValue(process.env[name])]));
}

function parsePortCandidate(value) {
  if (value === undefined || value === null) {
    return null;
  }

  const stringValue = String(value).trim();
  if (!stringValue) {
    return null;
  }

  if (/^\d+$/.test(stringValue)) {
    const parsedPort = Number(stringValue);
    return parsedPort > 0 ? parsedPort : null;
  }

  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(stringValue)) {
    try {
      const parsedUrl = new URL(stringValue);
      if (/^\d+$/.test(parsedUrl.port)) {
        const parsedPort = Number(parsedUrl.port);
        return parsedPort > 0 ? parsedPort : null;
      }
    } catch {
      return null;
    }
  }

  return null;
}

function getConfiguredPort() {
  for (const name of PORT_ENV_CANDIDATES) {
    if (process.env[name] === undefined) {
      continue;
    }

    const parsedPort = parsePortCandidate(process.env[name]);
    if (parsedPort !== null) {
      return parsedPort;
    }

    console.warn(
      `Invalid runtime port env ${name}=${JSON.stringify(safeEnvValue(process.env[name]))}; expected positive integer or URL with port; skipping.`,
    );
  }

  return FALLBACK_PORT;
}

const PORT = getConfiguredPort();
const SERVICE = 'telegram-local-catalog';
const DATABASE_URL = process.env.TELEGRAM_APP_DATABASE_URL || '';
const AUTO_INIT_DB = process.env.TELEGRAM_AUTO_INIT_DB === 'true';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '..');
const DIST_DIR = path.join(PROJECT_ROOT, 'dist');
const ASSETS_DIR = path.join(DIST_DIR, 'assets');
const INDEX_HTML = path.join(DIST_DIR, 'index.html');
const UPLOADS_DIR = path.join(PROJECT_ROOT, 'uploads');
const WEB_CONTENT_API_BASE_URL = (process.env.WEB_CONTENT_API_BASE_URL || 'https://bloomclub.ru/api/content').replace(/\/+$/, '');
const WEB_CONTENT_BLOCKS_URL = `${WEB_CONTENT_API_BASE_URL}/blocks`;
const WEB_CONTENT_GIVEAWAYS_URL = `${WEB_CONTENT_API_BASE_URL}/giveaways`;
const WEB_CLIENTS_API_BASE_URL = (process.env.WEB_CLIENTS_API_BASE_URL || 'https://bloomclub.ru/api/v1').replace(/\/+$/, '');
const WEB_TELEGRAM_LOGIN_URL = `${WEB_CLIENTS_API_BASE_URL}/auth/telegram-miniapp-login`;
const TELEGRAM_BOT_USERNAME = (process.env.TELEGRAM_BOT_USERNAME || '').replace(/^@/, '').trim();
const TELEGRAM_LOGIN_PROXY_TIMEOUT_MS = 30_000;
const CLIENT_API_PROXY_TIMEOUT_MS = 30_000;
const CONTENT_BLOCKS_PROXY_TIMEOUT_MS = Number(process.env.CONTENT_PROXY_TIMEOUT_MS || 20_000);
const MAX_TELEGRAM_LOGIN_BODY_BYTES = 1024 * 1024;
const MAX_ADMIN_JSON_BODY_BYTES = 256 * 1024;
const MAX_CLIENT_ERROR_BODY_BYTES = 64 * 1024;
const TELEGRAM_ADMIN_API_TOKEN = process.env.TELEGRAM_ADMIN_API_TOKEN || '';
const HEALTH_LOG_PATHS = new Set(['/ready', '/health', '/api/tg/health', '/']);
const HTML_NO_STORE_CACHE_CONTROL = 'no-store, no-cache, max-age=0, must-revalidate';
const ASSET_IMMUTABLE_CACHE_CONTROL = 'public, max-age=31536000, immutable';
const SERVER_BUILD_ID = process.env.VITE_APP_BUILD_HASH || process.env.VITE_GIT_COMMIT || process.env.APP_BUILD_ID || readDistBuildId() || readPackageVersion();

const SECURITY_HEADERS_MODE = process.env.TELEGRAM_SECURITY_HEADERS_MODE || 'report-only';
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self' https://telegram.org",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "connect-src 'self' https://bloomclub.ru https://tg.bloomclub.ru",
  "media-src 'self' https:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org",
].join('; ');
const BASELINE_SECURITY_HEADERS = Object.freeze({
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'no-referrer',
  'permissions-policy': 'camera=(), microphone=(), geolocation=(), payment=()',
  'strict-transport-security': 'max-age=15552000; includeSubDomains',
});

function getSecurityHeaders() {
  if (SECURITY_HEADERS_MODE === 'off') {
    return {};
  }

  const cspHeader = SECURITY_HEADERS_MODE === 'enforce' ? 'content-security-policy' : 'content-security-policy-report-only';
  return {
    ...BASELINE_SECURITY_HEADERS,
    [cspHeader]: CONTENT_SECURITY_POLICY,
  };
}

function attachSecurityHeaders(response) {
  const securityHeaders = getSecurityHeaders();
  if (!Object.keys(securityHeaders).length) {
    return;
  }

  const originalWriteHead = response.writeHead.bind(response);
  response.writeHead = function writeHeadWithSecurityHeaders(statusCode, statusMessageOrHeaders, maybeHeaders) {
    let statusMessage = statusMessageOrHeaders;
    let headers = maybeHeaders;

    if (typeof statusMessageOrHeaders === 'object' && statusMessageOrHeaders !== null) {
      statusMessage = undefined;
      headers = statusMessageOrHeaders;
    }

    const mergedHeaders = { ...securityHeaders, ...(headers || {}) };
    if (statusMessage === undefined) {
      return originalWriteHead(statusCode, mergedHeaders);
    }
    return originalWriteHead(statusCode, statusMessage, mergedHeaders);
  };
}

function isVersionedFrontendRoute(pathname) {
  return (
    pathname === '/' ||
    pathname === '/app' ||
    pathname.startsWith('/app-v') ||
    pathname === '/miniapp' ||
    pathname.startsWith('/miniapp/') ||
    pathname === '/telegram-app' ||
    pathname.startsWith('/telegram-app/')
  );
}
const REQUEST_LOG_WINDOW_MS = 5 * 60 * 1000;
const SERVER_STARTED_AT = Date.now();

let pool;
let server;
let shutdownStarted = false;

async function getPool() {
  if (!DATABASE_URL) {
    return null;
  }
  if (!pool) {
    const pg = await import('pg');
    const Pool = pg.default?.Pool || pg.Pool;
    pool = new Pool({ connectionString: DATABASE_URL, max: 5, idleTimeoutMillis: 10_000 });
  }
  return pool;
}

const schemaStatements = [
  `CREATE TABLE IF NOT EXISTS telegram_partners (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    external_content_id INTEGER UNIQUE,
    title TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    city TEXT,
    category TEXT,
    address TEXT,
    phone TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT
  )`,
  'CREATE INDEX IF NOT EXISTS ix_telegram_partners_is_active ON telegram_partners (is_active)',
  'CREATE INDEX IF NOT EXISTS ix_telegram_partners_sort_order ON telegram_partners (sort_order)',
  `CREATE TABLE IF NOT EXISTS telegram_partner_photos (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES telegram_partners(id) ON DELETE CASCADE,
    external_content_id INTEGER UNIQUE,
    image_url TEXT,
    file_path TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_cover INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT,
    CHECK (image_url IS NOT NULL OR file_path IS NOT NULL)
  )`,
  'CREATE INDEX IF NOT EXISTS ix_telegram_partner_photos_partner_id ON telegram_partner_photos (partner_id)',
  'CREATE INDEX IF NOT EXISTS ix_telegram_partner_photos_sort_order ON telegram_partner_photos (sort_order)',
  `CREATE TABLE IF NOT EXISTS telegram_partner_offers (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES telegram_partners(id) ON DELETE CASCADE,
    external_content_id INTEGER UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    conditions TEXT,
    base_price REAL,
    member_price REAL,
    discount_percent REAL,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT
  )`,
  'CREATE INDEX IF NOT EXISTS ix_telegram_partner_offers_partner_id ON telegram_partner_offers (partner_id)',
  'CREATE INDEX IF NOT EXISTS ix_telegram_partner_offers_is_active ON telegram_partner_offers (is_active)',
  'CREATE INDEX IF NOT EXISTS ix_telegram_partner_offers_sort_order ON telegram_partner_offers (sort_order)',
  `CREATE TABLE IF NOT EXISTS telegram_privilege_codes (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    telegram_user_id TEXT,
    linked_client_id TEXT,
    web_client_id TEXT,
    linked_account_id TEXT,
    partner_id INTEGER NOT NULL REFERENCES telegram_partners(id) ON DELETE CASCADE,
    offer_id INTEGER REFERENCES telegram_partner_offers(id) ON DELETE SET NULL,
    code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'created',
    expires_at TEXT,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT,
    source_platform TEXT NOT NULL DEFAULT 'telegram',
    web_subscription_checked_at TEXT,
    access_snapshot TEXT,
    metadata TEXT
  )`,
  'CREATE INDEX IF NOT EXISTS ix_telegram_privilege_codes_partner_id ON telegram_privilege_codes (partner_id)',
  'CREATE INDEX IF NOT EXISTS ix_telegram_privilege_codes_offer_id ON telegram_privilege_codes (offer_id)',
  'CREATE INDEX IF NOT EXISTS ix_telegram_privilege_codes_status ON telegram_privilege_codes (status)',
  'CREATE INDEX IF NOT EXISTS ix_telegram_privilege_codes_expires_at ON telegram_privilege_codes (expires_at)',
  'CREATE INDEX IF NOT EXISTS ix_telegram_privilege_codes_telegram_user_id ON telegram_privilege_codes (telegram_user_id)',
  'CREATE INDEX IF NOT EXISTS ix_telegram_privilege_codes_linked_client_id ON telegram_privilege_codes (linked_client_id)',
];

function sendJson(response, statusCode, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(statusCode, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'cache-control': HTML_NO_STORE_CACHE_CONTROL,
  });
  response.end(body);
}

function sendText(response, statusCode, message) {
  response.writeHead(statusCode, {
    'content-type': 'text/plain; charset=utf-8',
    'content-length': Buffer.byteLength(message),
    'cache-control': HTML_NO_STORE_CACHE_CONTROL,
  });
  response.end(message);
}

function sendHead(response, statusCode, headers = {}) {
  response.writeHead(statusCode, {
    'cache-control': HTML_NO_STORE_CACHE_CONTROL,
    ...headers,
  });
  response.end();
}

function getUptimeSeconds() {
  return Math.round(process.uptime());
}

function shouldLogRequest(pathname) {
  return Date.now() - SERVER_STARTED_AT <= REQUEST_LOG_WINDOW_MS || HEALTH_LOG_PATHS.has(pathname);
}

function isTelegramUserAgent(userAgent) {
  return /Telegram|TelegramBot|Telegram-Android|Telegram-iOS|tgWebApp/i.test(String(userAgent || ''));
}

function logFrontendRoute(eventName, request, fields = {}) {
  const userAgent = request.headers['user-agent'] || '';
  console.info(eventName, {
    pathname: new URL(request.url || '/', `http://${request.headers.host || '127.0.0.1'}`).pathname,
    cacheControlType: fields.cacheControlType,
    isTelegramUserAgent: isTelegramUserAgent(userAgent),
    userAgent: userAgent ? String(userAgent).slice(0, 180) : undefined,
    ...fields,
  });
}

function logRequest(request, response, pathname) {
  if (!shouldLogRequest(pathname)) {
    return;
  }

  const startedAt = process.hrtime.bigint();
  const userAgent = request.headers['user-agent'] || '';
  const remoteAddress = request.socket?.remoteAddress || '';
  response.once('finish', () => {
    const elapsedMs = Number((process.hrtime.bigint() - startedAt) / 1_000_000n);
    const fields = [
      'http request',
      `method=${request.method}`,
      `pathname=${pathname}`,
      `statusCode=${response.statusCode}`,
      `elapsedMs=${elapsedMs}`,
    ];
    if (userAgent) {
      fields.push(`user_agent=${JSON.stringify(userAgent)}`);
    }
    if (remoteAddress) {
      fields.push(`remoteAddress=${JSON.stringify(remoteAddress)}`);
    }
    console.log(fields.join(' '));
  });
}

function redactForLog(value) {
  return String(value)
    .replace(/(authorization|cookie|token|password|secret|database_url)([\s:=]+)[^\s;]+/gi, '$1$2[redacted]')
    .replace(/postgres(?:ql)?:\/\/[^\s]+/gi, 'postgresql://[redacted]')
    .replace(/bearer\s+[^\s;]+/gi, 'Bearer [redacted]')
    .slice(0, 500);
}

function safeErrorInfo(error) {
  const name = error?.name || 'Error';
  const message = error?.message || String(error);
  const stackFirstLine = typeof error?.stack === 'string' ? error.stack.split('\n')[0] : '';
  return {
    name: redactForLog(name).slice(0, 120),
    message: redactForLog(message),
    stack_first_line: redactForLog(stackFirstLine),
  };
}

function closePool() {
  if (!pool) {
    return Promise.resolve();
  }
  return pool.end().catch(() => undefined);
}

function handleShutdown(signal) {
  if (shutdownStarted) {
    return;
  }
  shutdownStarted = true;
  console.log(`received ${signal}; uptime_seconds=${getUptimeSeconds()}; pid=${process.pid}`);

  const forceExit = setTimeout(() => {
    console.error(`forced exit after ${signal}; uptime_seconds=${getUptimeSeconds()}; pid=${process.pid}`);
    process.exit(1);
  }, 10_000);
  forceExit.unref();

  const finish = () => {
    closePool().finally(() => {
      clearTimeout(forceExit);
      process.exit(0);
    });
  };

  if (!server?.listening) {
    finish();
    return;
  }

  server.close((error) => {
    if (error) {
      const info = safeErrorInfo(error);
      console.error(
        `server close error name=${JSON.stringify(info.name)} message=${JSON.stringify(info.message)} stack_first_line=${JSON.stringify(info.stack_first_line)}`,
      );
    }
    finish();
  });
}

process.on('SIGTERM', () => handleShutdown('SIGTERM'));
process.on('SIGINT', () => handleShutdown('SIGINT'));
process.on('uncaughtException', (error) => {
  const info = safeErrorInfo(error);
  console.error(
    `uncaughtException name=${JSON.stringify(info.name)} message=${JSON.stringify(info.message)} stack_first_line=${JSON.stringify(info.stack_first_line)}`,
  );
});
process.on('unhandledRejection', (reason) => {
  const info = safeErrorInfo(reason);
  console.error(
    `unhandledRejection name=${JSON.stringify(info.name)} message=${JSON.stringify(info.message)} stack_first_line=${JSON.stringify(info.stack_first_line)}`,
  );
});


function safeClientErrorValue(value, maxLength = 1000) {
  if (value === undefined || value === null) return undefined;
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return redactForLog(text).slice(0, maxLength);
}

function normalizeClientErrorPayload(payload) {
  const error = payload && typeof payload.error === 'object' && !Array.isArray(payload.error) ? payload.error : {};
  const build = payload && typeof payload.build === 'object' && !Array.isArray(payload.build) ? payload.build : {};
  return {
    eventType: safeClientErrorValue(payload?.eventType, 120) || 'client_error',
    appVersion: safeClientErrorValue(build.buildVersion, 120),
    buildId: safeClientErrorValue(build.buildHash, 160),
    buildTimestamp: safeClientErrorValue(build.buildTimestamp, 160),
    url: safeClientErrorValue(payload?.url, 500),
    pathname: safeClientErrorValue(payload?.pathname, 300),
    search: safeClientErrorValue(payload?.search, 500),
    tgStartParam: safeClientErrorValue(payload?.tgStartParam, 256),
    userAgent: safeClientErrorValue(payload?.userAgent, 300),
    errorName: safeClientErrorValue(error.name, 120),
    errorMessage: safeClientErrorValue(error.message, 1000),
    stackFirstLine: safeClientErrorValue(typeof error.stack === 'string' ? error.stack.split('\n')[0] : '', 500),
    occurredAt: safeClientErrorValue(payload?.occurredAt, 80),
  };
}

async function handleClientErrors(request, response) {
  if (request.method === 'HEAD') {
    sendHead(response, 204);
    return;
  }
  if (request.method !== 'POST') {
    sendMethodNotAllowed(response);
    return;
  }
  try {
    const body = await collectRequestBody(request, MAX_CLIENT_ERROR_BODY_BYTES, 'client_error_body_too_large');
    const payload = JSON.parse(body.toString('utf8'));
    const safePayload = normalizeClientErrorPayload(payload);
    console.error('CLIENT_ERROR_LOG', safePayload);
    sendHead(response, 204);
  } catch (error) {
    const info = safeErrorInfo(error);
    console.warn(`CLIENT_ERROR_LOG_INVALID name=${JSON.stringify(info.name)} message=${JSON.stringify(info.message)}`);
    sendJson(response, 400, { detail: 'invalid_client_error' });
  }
}

function handleRuntimeConfig(request, response) {
  if (request.method === 'HEAD') {
    sendHead(response, 200);
    return;
  }
  if (request.method !== 'GET') {
    sendMethodNotAllowed(response);
    return;
  }
  sendJson(response, 200, {
    buildId: SERVER_BUILD_ID,
    appVersion: SERVER_BUILD_ID,
    telegramBotUsername: TELEGRAM_BOT_USERNAME,
  });
}

function sendMethodNotAllowed(response) {
  sendJson(response, 405, { detail: 'method_not_allowed' });
}

function logDatabaseError(routeName, operationName, error) {
  console.error(
    'telegram catalog admin db error ' +
      `route=${JSON.stringify(routeName)} ` +
      `operation=${JSON.stringify(operationName)} ` +
      `message=${JSON.stringify(error?.message || '')} ` +
      `code=${JSON.stringify(error?.code || '')} ` +
      `detail=${JSON.stringify(error?.detail || '')}`,
  );
}

function sendDatabaseUnavailable(response) {
  sendJson(response, 503, {
    status: 'error',
    service: SERVICE,
    database: 'error',
    detail: 'database_unavailable',
  });
}

function normalizeRow(row) {
  return {
    ...row,
    is_active: Boolean(row.is_active),
    is_cover: row.is_cover === undefined ? undefined : Boolean(row.is_cover),
    base_price: row.base_price === null || row.base_price === undefined ? row.base_price : Number(row.base_price),
    member_price: row.member_price === null || row.member_price === undefined ? row.member_price : Number(row.member_price),
    discount_percent:
      row.discount_percent === null || row.discount_percent === undefined
        ? row.discount_percent
        : Number(row.discount_percent),
  };
}

async function queryDatabase(sql, params = []) {
  const databasePool = await getPool();
  if (!databasePool) {
    return { rows: [] };
  }
  return databasePool.query(sql, params);
}

async function fetchPublicCatalogPartners() {
  const result = await queryDatabase(`
    SELECT p.*,
      (SELECT COALESCE(ph.image_url, ph.file_path)
       FROM telegram_partner_photos ph
       WHERE ph.partner_id = p.id
       ORDER BY ph.is_cover DESC, ph.sort_order ASC, ph.id ASC
       LIMIT 1) AS cover,
      (SELECT COUNT(*)::INTEGER
       FROM telegram_partner_offers o
       WHERE o.partner_id = p.id AND o.is_active = 1) AS offers_count
    FROM telegram_partners p
    WHERE p.is_active = 1
    ORDER BY p.sort_order ASC, p.id ASC
  `);
  return result.rows.map(normalizeRow);
}

function serializeBootstrapJson(payload) {
  return JSON.stringify(payload)
    .replace(/</g, '\\u003C')
    .replace(/>/g, '\\u003E')
    .replace(/&/g, '\\u0026')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

function injectHtmlScript(indexHtml, script) {
  if (indexHtml.includes('</head>')) {
    return indexHtml.replace('</head>', `${script}</head>`);
  }
  if (indexHtml.includes('</body>')) {
    return indexHtml.replace('</body>', `${script}</body>`);
  }
  return `${indexHtml}${script}`;
}

function injectCatalogBootstrap(indexHtml, payload) {
  const script = `<script>window.__BLOOM_TG_CATALOG_BOOTSTRAP__=${serializeBootstrapJson(payload)};</script>`;
  return injectHtmlScript(indexHtml, script);
}

function injectRuntimeConfig(indexHtml) {
  const script = `<script>window.__BLOOM_TG_CONFIG__=${serializeBootstrapJson({
    telegramBotUsername: TELEGRAM_BOT_USERNAME,
    buildId: SERVER_BUILD_ID,
  })};</script>`;
  return injectHtmlScript(indexHtml, script);
}

async function initDatabaseIfEnabled() {
  if (!AUTO_INIT_DB) {
    return;
  }
  const databasePool = await getPool();
  if (!databasePool) {
    throw new Error('database_not_configured');
  }

  const client = await databasePool.connect();
  try {
    await client.query('BEGIN');
    for (const statement of schemaStatements) {
      await client.query(statement);
    }
    await client.query('COMMIT');
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

async function handleHealth(request, response) {
  if (request.method === 'HEAD') {
    sendHead(response, 200);
    return;
  }
  if (request.method !== 'GET') {
    sendMethodNotAllowed(response);
    return;
  }
  sendJson(response, 200, { status: 'ok', service: SERVICE });
}

async function handleHealthDb(request, response) {
  if (request.method !== 'GET') {
    sendMethodNotAllowed(response);
    return;
  }
  if (!DATABASE_URL) {
    sendJson(response, 503, { status: 'error', database: 'not_configured', detail: 'database_not_configured' });
    return;
  }
  try {
    await queryDatabase('SELECT 1');
    sendJson(response, 200, { status: 'ok', database: 'ok' });
  } catch {
    sendDatabaseUnavailable(response);
  }
}

async function handleRuntimePort(request, response) {
  if (request.method !== 'GET') {
    sendMethodNotAllowed(response);
    return;
  }

  sendJson(response, 200, {
    status: 'ok',
    actual_port: PORT,
    host: HOST,
    port_candidates: getSafeRuntimeEnvCandidates(),
    uptime_seconds: Math.floor((Date.now() - SERVER_STARTED_AT) / 1000),
  });
}

async function handleStatus(request, response) {
  if (request.method !== 'GET') {
    sendMethodNotAllowed(response);
    return;
  }
  if (!DATABASE_URL) {
    sendJson(response, 503, {
      status: 'error',
      service: SERVICE,
      database: 'not_configured',
      detail: 'database_not_configured',
      auto_init_enabled: AUTO_INIT_DB,
    });
    return;
  }

  try {
    const result = await queryDatabase(`
      SELECT
        (SELECT COUNT(*)::INTEGER FROM telegram_partners) AS partners_count,
        (SELECT COUNT(*)::INTEGER FROM telegram_partners WHERE is_active = 1) AS active_partners_count,
        (SELECT COUNT(*)::INTEGER FROM telegram_partner_offers) AS offers_count,
        (SELECT COUNT(*)::INTEGER FROM telegram_partner_offers WHERE is_active = 1) AS active_offers_count
    `);
    sendJson(response, 200, {
      status: 'ok',
      service: SERVICE,
      database: 'ok',
      counts: result.rows[0] || {},
      auto_init_enabled: AUTO_INIT_DB,
    });
  } catch {
    sendDatabaseUnavailable(response);
  }
}


function requireObject(value, name = 'payload') {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${name}_must_be_object`);
  }
}

function optionalString(payload, field, { required = false } = {}) {
  if (payload[field] === undefined || payload[field] === null) {
    if (required) throw new Error(`${field}_is_required`);
    return null;
  }
  const value = String(payload[field]).trim();
  if (required && !value) throw new Error(`${field}_is_required`);
  return value || null;
}

function optionalInt(payload, field, defaultValue = null) {
  if (payload[field] === undefined || payload[field] === null || payload[field] === '') return defaultValue;
  const value = Number(payload[field]);
  if (!Number.isInteger(value)) throw new Error(`${field}_must_be_integer_or_null`);
  return value;
}

function optionalBool(payload, field, defaultValue = false) {
  if (payload[field] === undefined || payload[field] === null || payload[field] === '') return defaultValue;
  if (typeof payload[field] === 'boolean') return payload[field];
  if (payload[field] === 0 || payload[field] === 1) return Boolean(payload[field]);
  throw new Error(`${field}_must_be_boolean`);
}

function validateAdminPartnerPayload(payload) {
  requireObject(payload);
  return {
    external_content_id: optionalInt(payload, 'external_content_id', null),
    title: optionalString(payload, 'title', { required: true }),
    display_name: optionalString(payload, 'display_name'),
    description: optionalString(payload, 'description'),
    city: optionalString(payload, 'city'),
    category: optionalString(payload, 'category'),
    address: optionalString(payload, 'address'),
    phone: optionalString(payload, 'phone'),
    is_active: optionalBool(payload, 'is_active', true),
    sort_order: optionalInt(payload, 'sort_order', 100),
  };
}

function validateAdminPhotoPayload(payload) {
  requireObject(payload);
  const imagePayload = { ...payload };
  if (imagePayload.image_url === undefined && imagePayload.url !== undefined) {
    imagePayload.image_url = imagePayload.url;
  }
  if (imagePayload.is_cover === undefined && imagePayload.is_main !== undefined) {
    imagePayload.is_cover = imagePayload.is_main;
  }
  return {
    external_content_id: optionalInt(imagePayload, 'external_content_id', null),
    image_url: optionalString(imagePayload, 'image_url', { required: true }),
    file_path: optionalString(imagePayload, 'file_path'),
    sort_order: optionalInt(imagePayload, 'sort_order', 100),
    is_cover: optionalBool(imagePayload, 'is_cover', false),
  };
}

async function parseJsonRequestBody(request) {
  const body = await collectRequestBody(request, MAX_ADMIN_JSON_BODY_BYTES, 'admin_json_body_too_large');
  if (!body.length) return {};
  const parsed = JSON.parse(body.toString('utf8'));
  requireObject(parsed);
  return parsed;
}

function adminAuthorizationError(request) {
  if (!TELEGRAM_ADMIN_API_TOKEN) return [501, 'admin_api_token_not_configured'];
  const headerToken = firstHeaderValue(request.headers['x-telegram-admin-token']);
  const authHeader = firstHeaderValue(request.headers.authorization);
  const bearerToken = authHeader.startsWith('Bearer ') ? authHeader.slice('Bearer '.length) : '';
  if (!headerToken && !bearerToken) return [401, 'admin_api_token_required'];
  if (headerToken === TELEGRAM_ADMIN_API_TOKEN || bearerToken === TELEGRAM_ADMIN_API_TOKEN) return null;
  return [403, 'admin_api_token_invalid'];
}

async function fetchAdminPartner(partnerId) {
  const result = await queryDatabase('SELECT * FROM telegram_partners WHERE id = $1', [partnerId]);
  return result.rows[0] ? normalizeRow(result.rows[0]) : null;
}

async function handleAdminPartners(request, response, pathname) {
  const authError = adminAuthorizationError(request);
  if (authError) {
    sendJson(response, authError[0], { detail: authError[1] });
    return;
  }
  if (!DATABASE_URL) {
    sendDatabaseUnavailable(response);
    return;
  }

  try {
    if (request.method === 'GET' && pathname === '/api/tg/admin/partners') {
      const result = await queryDatabase('SELECT * FROM telegram_partners ORDER BY sort_order ASC, id ASC');
      sendJson(response, 200, { items: result.rows.map(normalizeRow) });
      return;
    }

    if (request.method === 'POST' && pathname === '/api/tg/admin/partners') {
      const data = validateAdminPartnerPayload(await parseJsonRequestBody(request));
      let result;
      const values = [
        data.title,
        data.display_name,
        data.description,
        data.city,
        data.category,
        data.address,
        data.phone,
        data.is_active ? 1 : 0,
        data.sort_order,
      ];
      if (data.external_content_id !== null) {
        const existing = await queryDatabase('SELECT id FROM telegram_partners WHERE external_content_id = $1 LIMIT 1', [
          data.external_content_id,
        ]);
        if (existing.rows[0]) {
          result = await queryDatabase(
            `UPDATE telegram_partners SET
               title = $1,
               display_name = $2,
               description = $3,
               city = $4,
               category = $5,
               address = $6,
               phone = $7,
               is_active = $8,
               sort_order = $9,
               updated_at = CURRENT_TIMESTAMP::TEXT
             WHERE id = $10
             RETURNING *`,
            [...values, existing.rows[0].id],
          );
        } else {
          result = await queryDatabase(
            `INSERT INTO telegram_partners
              (title, display_name, description, city, category, address, phone, is_active, sort_order, external_content_id)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
             RETURNING *`,
            [...values, data.external_content_id],
          );
        }
      } else {
        result = await queryDatabase(
          `INSERT INTO telegram_partners
            (title, display_name, description, city, category, address, phone, is_active, sort_order, external_content_id)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
           RETURNING *`,
          [...values, null],
        );
      }
      sendJson(response, result.command === 'UPDATE' ? 200 : 201, normalizeRow(result.rows[0]));
      return;
    }

    const partnerMatch = pathname.match(/^\/api\/tg\/admin\/partners\/(\d+)$/);
    if (partnerMatch) {
      const partnerId = Number(partnerMatch[1]);
      if (request.method === 'DELETE') {
        if (!(await fetchAdminPartner(partnerId))) {
          sendJson(response, 404, { detail: 'partner_not_found' });
          return;
        }
        const databasePool = await getPool();
        const client = await databasePool.connect();
        try {
          await client.query('BEGIN');
          const offers = await client.query('SELECT id FROM telegram_partner_offers WHERE partner_id = $1', [partnerId]);
          const offerIds = offers.rows.map((row) => row.id);
          if (offerIds.length > 0) {
            await client.query('DELETE FROM telegram_privilege_codes WHERE offer_id = ANY($1::int[])', [offerIds]);
          }
          await client.query('DELETE FROM telegram_privilege_codes WHERE partner_id = $1', [partnerId]);
          await client.query('DELETE FROM telegram_partner_photos WHERE partner_id = $1', [partnerId]);
          await client.query('DELETE FROM telegram_partner_offers WHERE partner_id = $1', [partnerId]);
          await client.query('DELETE FROM telegram_partners WHERE id = $1', [partnerId]);
          await client.query('COMMIT');
          response.writeHead(204, { 'cache-control': 'no-store' });
          response.end();
          return;
        } catch (error) {
          await client.query('ROLLBACK').catch(() => undefined);
          throw error;
        } finally {
          client.release();
        }
      }
    }

    const photoMatch = pathname.match(/^\/api\/tg\/admin\/partners\/(\d+)\/photos$/);
    if (photoMatch) {
      const partnerId = Number(photoMatch[1]);
      if (request.method === 'GET') {
        if (!(await fetchAdminPartner(partnerId))) {
          sendJson(response, 404, { detail: 'partner_not_found' });
          return;
        }
        const result = await queryDatabase('SELECT * FROM telegram_partner_photos WHERE partner_id = $1 ORDER BY sort_order ASC, id ASC', [partnerId]);
        sendJson(response, 200, { items: result.rows.map(normalizeRow) });
        return;
      }
      if (request.method === 'POST') {
        if (!(await fetchAdminPartner(partnerId))) {
          sendJson(response, 404, { detail: 'partner_not_found' });
          return;
        }
        const data = validateAdminPhotoPayload(await parseJsonRequestBody(request));
        const databasePool = await getPool();
        const client = await databasePool.connect();
        try {
            await client.query('BEGIN');
            let result;
            const coverValue = data.is_cover ? 1 : 0;
            if (data.is_cover) await client.query('UPDATE telegram_partner_photos SET is_cover = 0 WHERE partner_id = $1', [partnerId]);
            if (data.external_content_id !== null) {
              const existing = await client.query('SELECT id FROM telegram_partner_photos WHERE external_content_id = $1 LIMIT 1', [
                data.external_content_id,
              ]);
              if (existing.rows[0]) {
                result = await client.query(
                  `UPDATE telegram_partner_photos SET
                     partner_id = $1,
                     image_url = $2,
                     file_path = $3,
                     sort_order = $4,
                     is_cover = $5
                   WHERE id = $6
                   RETURNING *`,
                  [partnerId, data.image_url, data.file_path, data.sort_order, coverValue, existing.rows[0].id],
                );
              } else {
                result = await client.query(
                  `INSERT INTO telegram_partner_photos (partner_id, image_url, file_path, sort_order, is_cover, external_content_id)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   RETURNING *`,
                  [partnerId, data.image_url, data.file_path, data.sort_order, coverValue, data.external_content_id],
                );
              }
            } else {
              result = await client.query(
                `INSERT INTO telegram_partner_photos (partner_id, image_url, file_path, sort_order, is_cover, external_content_id)
                 VALUES ($1, $2, $3, $4, $5, $6)
                 RETURNING *`,
                [partnerId, data.image_url, data.file_path, data.sort_order, coverValue, null],
              );
            }
            await client.query('COMMIT');
            sendJson(response, 201, normalizeRow(result.rows[0]));
            return;
          } catch (error) {
            await client.query('ROLLBACK').catch(() => undefined);
            throw error;
          } finally {
            client.release();
          }
      }
    }

    sendJson(response, 404, { detail: 'not_found' });
  } catch (error) {
    if (error instanceof SyntaxError || /(_must_|_is_required|too_large|json_body)/.test(error?.message || '')) {
      sendJson(response, 400, { detail: error.message === 'admin_json_body_too_large' ? error.message : error.message || 'invalid_json' });
      return;
    }
    const operationName = request.method === 'POST' && pathname === '/api/tg/admin/partners'
      ? 'upsert_partner'
      : request.method === 'POST' && /^\/api\/tg\/admin\/partners\/\d+\/photos$/.test(pathname)
        ? 'upsert_partner_photo'
        : request.method.toLowerCase();
    logDatabaseError('telegram_catalog_admin', operationName, error);
    sendDatabaseUnavailable(response);
  }
}

async function handlePartners(request, response, pathname) {
  if (request.method !== 'GET') {
    sendMethodNotAllowed(response);
    return;
  }

  if (!DATABASE_URL) {
    sendJson(response, 200, { items: [] });
    return;
  }

  try {
    const offersMatch = pathname.match(/^\/api\/tg\/partners\/(\d+)\/offers$/);
    if (offersMatch) {
      const result = await queryDatabase(
        `SELECT * FROM telegram_partner_offers
         WHERE partner_id = $1 AND is_active = 1
         ORDER BY sort_order ASC, id ASC`,
        [Number(offersMatch[1])],
      );
      sendJson(response, 200, { items: result.rows.map(normalizeRow) });
      return;
    }

    const partnerMatch = pathname.match(/^\/api\/tg\/partners\/(\d+)$/);
    if (partnerMatch) {
      const result = await queryDatabase(
        `SELECT p.*,
          (SELECT COALESCE(ph.image_url, ph.file_path)
           FROM telegram_partner_photos ph
           WHERE ph.partner_id = p.id
           ORDER BY ph.is_cover DESC, ph.sort_order ASC, ph.id ASC
           LIMIT 1) AS cover,
          (SELECT COUNT(*)::INTEGER
           FROM telegram_partner_offers o
           WHERE o.partner_id = p.id AND o.is_active = 1) AS offers_count
         FROM telegram_partners p
         WHERE p.id = $1 AND p.is_active = 1`,
        [Number(partnerMatch[1])],
      );
      if (!result.rows[0]) {
        sendJson(response, 404, { detail: 'partner_not_found' });
        return;
      }
      sendJson(response, 200, normalizeRow(result.rows[0]));
      return;
    }

    if (pathname === '/api/tg/partners') {
      const items = await fetchPublicCatalogPartners();
      sendJson(response, 200, { items });
      return;
    }

    sendJson(response, 404, { detail: 'not_found' });
  } catch {
    sendDatabaseUnavailable(response);
  }
}

function firstHeaderValue(value) {
  if (Array.isArray(value)) {
    return value[0] || '';
  }
  return value || '';
}

function safeTelegramLoginLogValue(value, maxLength = 500) {
  if (value === undefined || value === null) {
    return undefined;
  }

  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return text
    .replace(/(init_data|initData|telegram_payload|hash|signature|authorization|access_token|token)(["'\s:=]+)[^,"'\s}]+/gi, '$1$2[redacted]')
    .slice(0, maxLength);
}

function collectRequestBody(request, maxBytes, tooLargeMessage) {
  const rawDeclaredLength = request.headers['content-length'];
  const declaredLength = rawDeclaredLength === undefined ? null : Number(rawDeclaredLength);
  if (declaredLength !== null && (!Number.isFinite(declaredLength) || declaredLength < 0)) {
    return Promise.reject(new Error('invalid_content_length'));
  }
  if (declaredLength !== null && declaredLength > maxBytes) {
    return Promise.reject(new Error(tooLargeMessage));
  }

  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    let settled = false;

    function fail(error) {
      if (settled) return;
      settled = true;
      reject(error);
    }

    request.on('data', (chunk) => {
      total += chunk.length;
      if (total > maxBytes) {
        fail(new Error(tooLargeMessage));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on('end', () => {
      if (settled) return;
      settled = true;
      resolve(Buffer.concat(chunks));
    });
    request.on('error', fail);
  });
}

function getTelegramLoginBodyDiagnostics(body) {
  let hasInitData = false;
  let hasLaunchPayload = false;
  let hasReferralCode = false;
  let hasStartParam = false;
  let referralCodeLength = 0;
  let startParamLength = 0;

  try {
    const parsed = JSON.parse(body.toString('utf8'));
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const referralCode = typeof parsed.referral_code === 'string' ? parsed.referral_code.trim() : '';
      const startParam = typeof parsed.start_param === 'string' ? parsed.start_param.trim() : '';
      hasInitData = typeof parsed.init_data === 'string' && parsed.init_data.length > 0;
      hasLaunchPayload = hasInitData || typeof parsed.initData === 'string' && parsed.initData.length > 0 || typeof parsed.telegram_payload === 'string' && parsed.telegram_payload.length > 0;
      hasReferralCode = referralCode.length > 0;
      hasStartParam = startParam.length > 0;
      referralCodeLength = referralCode.length;
      startParamLength = startParam.length;
    }
  } catch {
    // Keep diagnostics conservative for malformed/non-JSON bodies.
  }

  return { hasInitData, hasLaunchPayload, hasReferralCode, hasStartParam, referralCodeLength, startParamLength };
}

function writeTelegramLoginProxyResponse(response, webResponse, responseBody) {
  const headers = {
    'content-type': webResponse.headers.get('content-type') || 'application/json; charset=utf-8',
    'cache-control': HTML_NO_STORE_CACHE_CONTROL,
  };
  const requestId = webResponse.headers.get('x-request-id') || webResponse.headers.get('x-correlation-id');
  if (requestId) {
    headers['x-request-id'] = requestId;
  }
  response.writeHead(webResponse.status, headers);
  response.end(responseBody);
}

async function handleTelegramLoginProxy(request, response) {
  if (request.method !== 'POST') {
    sendMethodNotAllowed(response);
    return;
  }

  const startedAt = Date.now();
  let body = Buffer.alloc(0);

  try {
    body = await collectRequestBody(request, MAX_TELEGRAM_LOGIN_BODY_BYTES, 'telegram_login_body_too_large');
    const bodyDiagnostics = getTelegramLoginBodyDiagnostics(body);
    console.info('telegram_login_proxy_start', {
      targetUrl: WEB_TELEGRAM_LOGIN_URL,
      bodyLength: body.length,
      ...bodyDiagnostics,
    });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), TELEGRAM_LOGIN_PROXY_TIMEOUT_MS);
    let webResponse;

    try {
      webResponse = await fetch(WEB_TELEGRAM_LOGIN_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'User-Agent': firstHeaderValue(request.headers['user-agent']) || `${SERVICE}/telegram-login-proxy`,
        },
        body,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeoutId);
    }

    const responseBody = await webResponse.text();
    const requestId =
      webResponse.headers.get('x-request-id') || webResponse.headers.get('x-correlation-id') || undefined;
    console.info('telegram_login_proxy_response', {
      targetUrl: WEB_TELEGRAM_LOGIN_URL,
      status: webResponse.status,
      ok: webResponse.ok,
      requestId,
      elapsedMs: Date.now() - startedAt,
    });
    writeTelegramLoginProxyResponse(response, webResponse, responseBody);
  } catch (error) {
    const isAbortError = error?.name === 'AbortError';
    console.error('telegram_login_proxy_error', {
      targetUrl: WEB_TELEGRAM_LOGIN_URL,
      bodyLength: body.length,
      status: isAbortError ? 504 : 502,
      ok: false,
      requestId: undefined,
      elapsedMs: Date.now() - startedAt,
      name: safeTelegramLoginLogValue(error?.name, 80),
      message: safeTelegramLoginLogValue(error?.message || error),
    });
    sendJson(response, isAbortError ? 504 : 502, {
      detail: 'Не удалось выполнить вход через Telegram. Попробуйте ещё раз.',
    });
  }
}

function isClientApiProxyPath(pathname) {
  return pathname === '/api/v1/clients/cities' || pathname === '/api/v1/clients/me' || pathname.startsWith('/api/v1/clients/me/');
}

function createClientApiProxyHeaders(request) {
  const headers = {
    Accept: 'application/json',
    'User-Agent': firstHeaderValue(request.headers['user-agent']) || `${SERVICE}/client-api-proxy`,
  };
  const authorization = firstHeaderValue(request.headers.authorization);
  const contentType = firstHeaderValue(request.headers['content-type']);

  if (authorization) {
    headers.Authorization = authorization;
  }
  if (contentType) {
    headers['Content-Type'] = contentType;
  }

  return headers;
}

function writeClientApiProxyResponse(response, webResponse, responseBody, isHeadRequest) {
  const requestId = webResponse.headers.get('x-request-id') || undefined;
  const correlationId = webResponse.headers.get('x-correlation-id') || undefined;
  response.writeHead(webResponse.status, {
    'content-type': webResponse.headers.get('content-type') || 'application/json; charset=utf-8',
    'cache-control': HTML_NO_STORE_CACHE_CONTROL,
    ...(requestId ? { 'x-request-id': requestId } : {}),
    ...(correlationId ? { 'x-correlation-id': correlationId } : {}),
  });
  response.end(isHeadRequest ? undefined : responseBody);
}

async function handleClientApiProxy(request, response, requestUrl, pathname) {
  if (request.method === 'OPTIONS') {
    sendHead(response, 204, {
      allow: 'GET, POST, HEAD, OPTIONS',
    });
    return;
  }

  if (request.method !== 'GET' && request.method !== 'HEAD' && request.method !== 'POST') {
    sendMethodNotAllowed(response);
    return;
  }
  if (request.method === 'POST' && pathname !== '/api/v1/clients/me/trial-subscription') {
    sendMethodNotAllowed(response);
    return;
  }

  const method = request.method;
  const targetUrl = `${WEB_CLIENTS_API_BASE_URL}${pathname.replace(/^\/api\/v1/, '')}${requestUrl.search}`;
  const startedAt = Date.now();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CLIENT_API_PROXY_TIMEOUT_MS);
  const hasAuth = Boolean(firstHeaderValue(request.headers.authorization));
  let body = Buffer.alloc(0);

  console.info('client_api_proxy_start', {
    method,
    path: pathname,
    query: safeTelegramLoginLogValue(requestUrl.searchParams.toString(), 500),
    targetUrl: safeTelegramLoginLogValue(targetUrl, 500),
    hasAuth,
  });

  try {
    body = method === 'POST'
      ? await collectRequestBody(request, MAX_TELEGRAM_LOGIN_BODY_BYTES, 'client_api_body_too_large')
      : Buffer.alloc(0);

    const webResponse = await fetch(targetUrl, {
      method,
      headers: createClientApiProxyHeaders(request),
      ...(method === 'POST' ? { body } : {}),
      signal: controller.signal,
    });
    const responseBody = await webResponse.text();
    const requestId = webResponse.headers.get('x-request-id') || webResponse.headers.get('x-correlation-id') || undefined;

    console.info('client_api_proxy_response', {
      method,
      path: pathname,
      status: webResponse.status,
      ok: webResponse.ok,
      requestId,
      elapsedMs: Date.now() - startedAt,
    });

    writeClientApiProxyResponse(response, webResponse, responseBody, request.method === 'HEAD');
  } catch (error) {
    console.error('client_api_proxy_error', {
      method,
      path: pathname,
      message: safeTelegramLoginLogValue(error?.message || error),
      elapsedMs: Date.now() - startedAt,
    });
    sendJson(response, error?.name === 'AbortError' ? 504 : 502, {
      detail: 'Не удалось загрузить данные клуба. Попробуйте ещё раз.',
    });
  } finally {
    clearTimeout(timeoutId);
  }
}


function getJsonItemCount(payload) {
  if (Array.isArray(payload)) {
    return payload.length;
  }

  if (!payload || typeof payload !== 'object') {
    return undefined;
  }

  const body = payload;
  const candidate = [body.items, body.blocks, body.static_texts, body.data, body.results].find(Array.isArray);
  return Array.isArray(candidate) ? candidate.length : undefined;
}

function getContentBlocksProxyCount(responseBody) {
  try {
    return getJsonItemCount(JSON.parse(responseBody));
  } catch {
    return undefined;
  }
}

function normalizeListPayload(payload, keys) {
  if (Array.isArray(payload)) {
    return payload.filter((item) => item && typeof item === 'object');
  }
  if (!payload || typeof payload !== 'object') {
    return [];
  }
  for (const key of keys) {
    if (Array.isArray(payload[key])) {
      return payload[key].filter((item) => item && typeof item === 'object');
    }
  }
  return [];
}

function normalizeGiveawayItem(item) {
  const imageUrl = item.image_url || item.photo_url || item.url || item.image || item.picture || '';
  return {
    ...item,
    image_url: imageUrl,
    photo_url: item.photo_url || imageUrl,
    is_active: item.is_active !== undefined ? Boolean(item.is_active) : item.active !== undefined ? Boolean(item.active) : true,
  };
}

function normalizeGiveaway(giveaway) {
  const photoUrl = giveaway.photo_url || giveaway.image_url || giveaway.url || giveaway.image || giveaway.picture || '';
  return {
    ...giveaway,
    photo_url: photoUrl,
    image_url: giveaway.image_url || photoUrl,
    is_active:
      giveaway.is_active !== undefined ? Boolean(giveaway.is_active) : giveaway.active !== undefined ? Boolean(giveaway.active) : true,
    items: normalizeListPayload(giveaway.items || giveaway.giveaway_items || [], ['items', 'giveaway_items']).map(normalizeGiveawayItem),
    photos: normalizeListPayload(giveaway.photos || giveaway.giveaway_photos || [], ['photos', 'giveaway_photos']),
  };
}

async function fetchContentJson(targetUrl, signal) {
  const webResponse = await fetch(targetUrl, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  });
  const body = await webResponse.text();
  let payload = null;
  if (body) {
    try {
      payload = JSON.parse(body);
    } catch (error) {
      const parseError = new Error('content_api_invalid_json');
      parseError.cause = error;
      parseError.status = webResponse.status;
      throw parseError;
    }
  }
  if (!webResponse.ok) {
    const statusError = new Error('content_api_error');
    statusError.status = webResponse.status;
    statusError.payload = payload;
    throw statusError;
  }
  return { payload, status: webResponse.status, headers: webResponse.headers };
}

async function handleGiveaways(request, response) {
  if (request.method === 'HEAD') {
    sendHead(response, 200);
    return;
  }

  if (request.method !== 'GET') {
    sendMethodNotAllowed(response);
    return;
  }

  const startedAt = Date.now();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CONTENT_BLOCKS_PROXY_TIMEOUT_MS);
  try {
    const { payload, headers } = await fetchContentJson(WEB_CONTENT_GIVEAWAYS_URL, controller.signal);
    const items = normalizeListPayload(payload, ['giveaways', 'items', 'data', 'results']).map(normalizeGiveaway);
    const activeItems = items
      .filter((item) => item.is_active !== false)
      .sort((left, right) => Number(left.sort_order || left.order || 0) - Number(right.sort_order || right.order || 0));
    const requestId = headers.get('x-request-id') || headers.get('x-correlation-id') || undefined;
    console.info('giveaways_proxy_response', { status: 200, count: activeItems.length, requestId, elapsedMs: Date.now() - startedAt });
    sendJson(response, 200, { items: activeItems });
  } catch (error) {
    console.error('giveaways_proxy_error', {
      status: error?.status,
      message: safeUploadLogValue(error?.message || error),
      elapsedMs: Date.now() - startedAt,
    });
    sendJson(response, error?.name === 'AbortError' ? 504 : 502, { detail: 'content_api_unavailable' });
  } finally {
    clearTimeout(timeoutId);
  }
}

async function handleContentBlocksProxy(request, response, requestUrl) {
  if (request.method === 'OPTIONS') {
    sendHead(response, 204, {
      allow: 'GET, HEAD, OPTIONS',
    });
    return;
  }

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    sendMethodNotAllowed(response);
    return;
  }

  const targetUrl = `${WEB_CONTENT_BLOCKS_URL}${requestUrl.search}`;
  const startedAt = Date.now();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CONTENT_BLOCKS_PROXY_TIMEOUT_MS);
  console.info('content_blocks_proxy_start', {
    query: safeTelegramLoginLogValue(requestUrl.searchParams.toString(), 500),
    targetUrl: safeTelegramLoginLogValue(targetUrl, 500),
  });

  try {
    const webResponse = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
      signal: controller.signal,
    });
    const responseBody = await webResponse.text();
    const requestId = webResponse.headers.get('x-request-id') || webResponse.headers.get('x-correlation-id') || undefined;
    console.info('content_blocks_proxy_response', {
      status: webResponse.status,
      ok: webResponse.ok,
      requestId,
      count: getContentBlocksProxyCount(responseBody),
      elapsedMs: Date.now() - startedAt,
    });

    response.writeHead(webResponse.status, {
      'content-type': webResponse.headers.get('content-type') || 'application/json; charset=utf-8',
      'cache-control': HTML_NO_STORE_CACHE_CONTROL,
      ...(requestId ? { 'x-request-id': requestId } : {}),
    });
    response.end(request.method === 'HEAD' ? undefined : responseBody);
  } catch (error) {
    console.error('content_blocks_proxy_error', {
      message: safeUploadLogValue(error?.message || error),
      elapsedMs: Date.now() - startedAt,
    });
    sendJson(response, error?.name === 'AbortError' ? 504 : 502, { detail: 'content_api_unavailable' });
  } finally {
    clearTimeout(timeoutId);
  }
}

function contentTypeFor(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === '.js') return 'text/javascript; charset=utf-8';
  if (extension === '.css') return 'text/css; charset=utf-8';
  if (extension === '.svg') return 'image/svg+xml';
  if (extension === '.png') return 'image/png';
  if (extension === '.jpg' || extension === '.jpeg') return 'image/jpeg';
  if (extension === '.webp') return 'image/webp';
  if (extension === '.ico') return 'image/x-icon';
  return 'application/octet-stream';
}

async function serveAsset(request, response, pathname) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    sendMethodNotAllowed(response);
    return;
  }

  const relativeAssetPath = decodeURIComponent(pathname.replace(/^\/assets\//, ''));
  const filePath = path.resolve(ASSETS_DIR, relativeAssetPath);
  if (!filePath.startsWith(`${ASSETS_DIR}${path.sep}`)) {
    sendText(response, 404, 'Not found');
    return;
  }

  try {
    await access(filePath);
    logFrontendRoute('frontend_asset_served', request, {
      pathname,
      contentType: contentTypeFor(filePath),
      cacheControlType: 'asset-immutable',
      cacheControl: ASSET_IMMUTABLE_CACHE_CONTROL,
    });
    response.writeHead(200, {
      'content-type': contentTypeFor(filePath),
      'cache-control': ASSET_IMMUTABLE_CACHE_CONTROL,
    });
    if (request.method === 'HEAD') {
      response.end();
      return;
    }
    createReadStream(filePath).pipe(response);
  } catch {
    logFrontendRoute('frontend_asset_missing', request, {
      pathname,
      cacheControlType: 'missing-asset-no-store-404',
      cacheControl: HTML_NO_STORE_CACHE_CONTROL,
    });
    sendText(response, 404, 'Not found');
  }
}

async function serveUpload(request, response, pathname) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    sendMethodNotAllowed(response);
    return;
  }

  const relativeUploadPath = decodeURIComponent(pathname.replace(/^\/uploads\//, ''));
  const filePath = path.resolve(UPLOADS_DIR, relativeUploadPath);
  if (!filePath.startsWith(`${UPLOADS_DIR}${path.sep}`)) {
    sendText(response, 404, 'Not found');
    return;
  }

  try {
    await access(filePath);
    response.writeHead(200, { 'content-type': contentTypeFor(filePath) });
    if (request.method === 'HEAD') {
      response.end();
      return;
    }
    createReadStream(filePath).pipe(response);
  } catch {
    sendText(response, 404, 'Not found');
  }
}

async function serveFrontend(request, response, options = {}) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    sendMethodNotAllowed(response);
    return;
  }

  try {
    const indexHtml = await readFile(INDEX_HTML, 'utf8');
    let body = injectRuntimeConfig(indexHtml);
    try {
      const items = await fetchPublicCatalogPartners();
      body = injectCatalogBootstrap(body, { items });
    } catch (error) {
      const info = safeErrorInfo(error);
      console.warn(
        `catalog bootstrap unavailable name=${JSON.stringify(info.name)} message=${JSON.stringify(info.message)}`,
      );
    }
    const bodyBytes = Buffer.from(body);
    logFrontendRoute('frontend_index_served', request, {
      contentLength: bodyBytes.length,
      injectedCatalogBootstrap: body !== indexHtml,
      cacheControlType: 'html-no-store',
      cacheControl: HTML_NO_STORE_CACHE_CONTROL,
    });
    response.writeHead(200, {
      'content-type': 'text/html; charset=utf-8',
      'content-length': bodyBytes.length,
      'cache-control': HTML_NO_STORE_CACHE_CONTROL,
      pragma: 'no-cache',
      expires: '0',
    });
    response.end(request.method === 'HEAD' ? undefined : bodyBytes);
  } catch {
    if (options.fallbackOnMissingIndex) {
      logFrontendRoute('frontend_index_missing', request, {
        cacheControlType: 'html-no-store-build-missing',
        cacheControl: HTML_NO_STORE_CACHE_CONTROL,
      });
    }
    sendText(response, 500, 'Frontend build is not available. Run npm run build before starting production server.');
  }
}

async function handleRequest(request, response) {
  const url = new URL(request.url || '/', `http://${request.headers.host || '127.0.0.1'}`);
  const pathname = url.pathname.replace(/\/$/, '') || '/';

  attachSecurityHeaders(response);
  logRequest(request, response, pathname);

  if (pathname === '/api/tg/health' || pathname === '/health') {
    await handleHealth(request, response);
    return;
  }
  if (pathname === '/ready') {
    if (request.method === 'HEAD') {
      sendHead(response, 200);
      return;
    }
    if (request.method !== 'GET') {
      sendMethodNotAllowed(response);
      return;
    }
    sendText(response, 200, 'ok');
    return;
  }
  if (pathname === '/api/tg/health/db') {
    await handleHealthDb(request, response);
    return;
  }
  if (pathname === '/api/client-errors') {
    await handleClientErrors(request, response);
    return;
  }
  if (pathname === '/api/runtime-config') {
    handleRuntimeConfig(request, response);
    return;
  }
  if (pathname === '/debug/runtime-port') {
    await handleRuntimePort(request, response);
    return;
  }
  if (pathname === '/api/tg/status') {
    await handleStatus(request, response);
    return;
  }
  if (pathname === '/api/tg/giveaways') {
    handleGiveaways(request, response);
    return;
  }
  if (pathname === '/api/tg/me/verifications' || pathname === '/api/tg/me/savings') {
    if (request.method === 'HEAD') {
      sendHead(response, 501);
      return;
    }
    if (request.method !== 'GET') {
      sendMethodNotAllowed(response);
      return;
    }
    sendJson(response, 501, { detail: 'user_context_not_configured' });
    return;
  }
  if (pathname === '/api/tg/partners' || /^\/api\/tg\/partners\/\d+(?:\/offers)?$/.test(pathname)) {
    await handlePartners(request, response, pathname);
    return;
  }
  if (pathname === '/api/tg/admin/partners' || /^\/api\/tg\/admin\/partners\/\d+\/photos$/.test(pathname)) {
    await handleAdminPartners(request, response, pathname);
    return;
  }
  if (pathname === '/api/content/blocks') {
    await handleContentBlocksProxy(request, response, url);
    return;
  }
  if (pathname === '/api/v1/auth/telegram-miniapp-login') {
    await handleTelegramLoginProxy(request, response);
    return;
  }
  if (isClientApiProxyPath(pathname)) {
    await handleClientApiProxy(request, response, url, pathname);
    return;
  }
  if (pathname.startsWith('/api/')) {
    sendJson(response, 404, { detail: 'not_found' });
    return;
  }
  if (pathname.startsWith('/assets/')) {
    await serveAsset(request, response, pathname);
    return;
  }
  if (pathname.startsWith('/uploads/')) {
    await serveUpload(request, response, pathname);
    return;
  }
  if (isVersionedFrontendRoute(pathname)) {
    await serveFrontend(request, response, { fallbackOnMissingIndex: true });
    return;
  }

  sendText(response, 404, 'Not found');
}

async function start() {
  try {
    await initDatabaseIfEnabled();
  } catch {
    console.error('Telegram catalog DB auto init failed; check database target and schema permissions.');
    process.exitCode = 1;
    return;
  }

  server = http.createServer((request, response) => {
    handleRequest(request, response).catch(() => {
      if (!response.headersSent) {
        sendJson(response, 500, { detail: 'internal_server_error' });
      } else {
        response.destroy();
      }
    });
  });

  server.listen(PORT, HOST, () => {
    console.log(
      `Telegram catalog production server listening on ${HOST}:${PORT}; actual_port=${PORT}; host=${HOST}; pid=${process.pid}; node_version=${process.version}; uptime_seconds=0; db_configured=${Boolean(DATABASE_URL)}; auto_init=${AUTO_INIT_DB}; port_env_candidates=${JSON.stringify(getSafeRuntimeEnvCandidates())}; health_paths=/,/ready,/health,/api/tg/health`,
    );
  });
}

start();
