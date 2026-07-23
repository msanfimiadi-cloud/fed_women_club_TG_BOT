import type {
  AuthResponse,
  City,
  ClientProfile,
  Partner,
  LinkingConfirmResponse,
  LinkingStartResponse,
  LinkingStatus,
  PaymentRequest,
  ClientProfilePatch,
  Offer,
  SavingsSummary,
  Subscription,
  Verification,
  ReferralSummary,
} from "./types";
import { traceStartup } from "../diagnostics/startupTrace";

const DEFAULT_API_BASE_URL = "https://bloomclub.ru/api/v1";

function normalizeApiBaseUrl(rawBaseUrl: string | undefined): string {
  const candidate = (rawBaseUrl || DEFAULT_API_BASE_URL)
    .trim()
    .replace(/\/+$/, "");

  if (!/^https?:\/\//i.test(candidate)) {
    return DEFAULT_API_BASE_URL;
  }

  try {
    const parsedUrl = new URL(candidate);
    const defaultUrl = new URL(DEFAULT_API_BASE_URL);
    const normalizedPath = parsedUrl.pathname.replace(
      /(?:\/api\/v1)+$/,
      "/api/v1",
    );
    parsedUrl.pathname = normalizedPath || defaultUrl.pathname;

    if (
      typeof window !== "undefined" &&
      parsedUrl.origin === window.location.origin &&
      parsedUrl.origin !== defaultUrl.origin
    ) {
      return DEFAULT_API_BASE_URL;
    }

    if (
      parsedUrl.origin === defaultUrl.origin &&
      !parsedUrl.pathname.endsWith(defaultUrl.pathname)
    ) {
      parsedUrl.pathname = `${parsedUrl.pathname.replace(/\/+$/, "")}${defaultUrl.pathname}`;
    }

    return parsedUrl.toString().replace(/\/+$/, "");
  } catch {
    return DEFAULT_API_BASE_URL;
  }
}

const WEB_API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

function normalizeTgApiBaseUrl(rawBaseUrl: string | undefined): string {
  const candidate = (rawBaseUrl || "").trim().replace(/\/+$/, "");

  if (!candidate) {
    return "";
  }

  if (!/^https?:\/\//i.test(candidate)) {
    return "";
  }

  try {
    const parsedUrl = new URL(candidate);
    parsedUrl.pathname = parsedUrl.pathname.replace(/(?:\/api\/tg)+$/, "");
    return parsedUrl.toString().replace(/\/+$/, "");
  } catch {
    return "";
  }
}

const TG_API_BASE_URL = normalizeTgApiBaseUrl(
  import.meta.env.VITE_TG_API_BASE_URL,
);
export const TG_LOCAL_CATALOG_ENABLED =
  import.meta.env.VITE_TG_LOCAL_CATALOG_ENABLED === "true";
const AUTH_STORAGE_KEY = "bloom_club_tma_auth";
const AUTH_SESSION_STORAGE_KEY = "bloom_club_tma_auth_session";
const AUTH_LEGACY_LOCAL_STORAGE_ENABLED =
  import.meta.env.VITE_AUTH_STORAGE_MODE === "legacy_local_storage";
const AUTH_SESSION_TTL_MS = 30 * 60 * 1000;
const AUTH_SESSION_MAX_TTL_MS = 60 * 60 * 1000;
let inMemoryAuthToken: string | null = null;
let inMemoryAuthTokenExpiresAt = 0;
const REQUEST_TIMEOUT_MS = 30_000;
const CATALOG_TIMEOUT_MS = 12_000;
export const WEB_CATALOG_PARTNERS_PATH = "/clients/catalog/partners";
export const TG_CATALOG_PARTNERS_PATH = "/api/tg/partners";
export const CATALOG_PARTNERS_PATH = WEB_CATALOG_PARTNERS_PATH;
export const TELEGRAM_LOGIN_TIMEOUT_MS = 30_000;
export const TELEGRAM_LOGIN_PATH = "/api/v1/auth/telegram-miniapp-login";
const CLIENT_API_PROXY_PREFIX = "/api/v1";
const TELEGRAM_LOGIN_RETRY_ATTEMPTS = 1;
const GET_RETRY_ATTEMPTS = 1;
let telegramLoginInFlight: Promise<string> | null = null;

export type TelegramLoginReason = "initial" | "retry" | "manual" | "resume";
export type TelegramLoginInFlightState = "idle" | "in_flight" | "force_reset";

export interface TelegramLoginOptions {
  reason?: TelegramLoginReason;
  bootstrapAttemptId?: number;
  forceNew?: boolean;
  referralCode?: string | null;
  startParam?: string | null;
}

type ErrorResponseBody = {
  detail?: unknown;
  message?: unknown;
  error?: unknown;
};

export type TelegramLoginFetchPhase =
  | "prefetch"
  | "before_fetch"
  | "after_fetch_response"
  | "parse_json"
  | "network_catch";

export type TelegramLoginFailureStage =
  | "telegram_login_prefetch"
  | "telegram_login_request"
  | "telegram_login_response_parse"
  | "telegram_login_token_extract";

export interface TelegramLoginDiagnostic {
  requestUrl: string;
  requestUrlPath: string;
  requestOrigin: string;
  httpStatus?: number;
  backendDetail?: string;
  errorName?: string;
  errorMessageShort?: string;
  isAbortError: boolean;
  timeoutMs: number;
  fetchPhase: TelegramLoginFetchPhase;
  elapsedMs: number;
  didSendRequest: boolean;
  requestId?: string;
  corsMode: RequestMode;
  credentials: RequestCredentials;
  responseKeys?: string[];
  attempt: number;
  hasLaunchPayload: boolean;
  launchPayloadLength: number;
  willStartFetch: boolean;
  bootstrapAttemptId?: number;
  inFlightState: TelegramLoginInFlightState;
  reason: TelegramLoginReason;
  skippedReason?: string;
  hasReferralCode?: boolean;
  hasStartParam?: boolean;
  referralCodeLength?: number;
  startParamLength?: number;
}

export type CatalogFetchPhase =
  | "before_fetch"
  | "fetch_started"
  | "after_fetch_response"
  | "parse_json"
  | "network_catch"
  | "pre_fetch_catch";

export type CatalogSource = "tg_local_catalog" | "web_legacy_catalog";

export interface CatalogErrorDiagnostic {
  source: CatalogSource;
  requestUrl: string;
  requestUrlPath: string;
  requestOrigin: string;
  httpStatus?: number;
  backendDetail?: string;
  requestId?: string;
  fetchPhase: CatalogFetchPhase;
  elapsedMs: number;
  errorName?: string;
  isAbortError: boolean;
  attempt: number;
  signalAbortedBeforeFetch?: boolean;
  abortReason?: string;
  abortSource?: "timeout" | "external";
  fetchStartDelayMs?: number;
  fetchStarted?: boolean;
  timeoutStarted?: boolean;
}

export class CatalogLoadError extends Error {
  constructor(
    message: string,
    public readonly diagnostic: CatalogErrorDiagnostic,
  ) {
    super(message);
    this.name = "CatalogLoadError";
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class NetworkError extends Error {
  constructor(
    message = "Не удалось отправить запрос. Проверьте соединение и попробуйте ещё раз.",
  ) {
    super(message);
    this.name = "NetworkError";
  }
}

export class TimeoutError extends Error {
  constructor(
    message = "Не удалось загрузить данные. Проверьте соединение и повторите попытку.",
  ) {
    super(message);
    this.name = "TimeoutError";
  }
}

export class TelegramLoginError extends Error {
  constructor(
    message: string,
    public readonly loginStage: TelegramLoginFailureStage,
    public readonly diagnostic: TelegramLoginDiagnostic,
  ) {
    super(message);
    this.name = "TelegramLoginError";
  }
}

export function isTimeoutError(error: unknown): error is TimeoutError {
  return (
    error instanceof TimeoutError ||
    (error instanceof Error && error.name === "TimeoutError")
  );
}

export function isApiError(error: unknown): error is ApiError {
  return (
    error instanceof ApiError ||
    (error instanceof Error && error.name === "ApiError")
  );
}

export function isTelegramLoginError(
  error: unknown,
): error is TelegramLoginError {
  return error instanceof TelegramLoginError;
}

export function isCatalogLoadError(error: unknown): error is CatalogLoadError {
  return error instanceof CatalogLoadError;
}

type StoredAuthSession = {
  token?: unknown;
  expiresAt?: unknown;
  storedAt?: unknown;
};

function getAuthSessionExpiry(token: string, now = Date.now()): number {
  const fallbackExpiry = now + AUTH_SESSION_TTL_MS;
  const parts = token.split(".");

  if (parts.length < 2) {
    return fallbackExpiry;
  }

  try {
    const payload = JSON.parse(
      window.atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")),
    ) as { exp?: unknown };
    const jwtExpiry = typeof payload.exp === "number" ? payload.exp * 1000 : 0;

    if (!Number.isFinite(jwtExpiry) || jwtExpiry <= now) {
      return fallbackExpiry;
    }

    return Math.min(jwtExpiry, now + AUTH_SESSION_MAX_TTL_MS);
  } catch {
    return fallbackExpiry;
  }
}

function rememberAuthToken(
  token: string,
  expiresAt = getAuthSessionExpiry(token),
): void {
  inMemoryAuthToken = token;
  inMemoryAuthTokenExpiresAt = expiresAt;
}

function clearLegacyLocalAuthToken(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.removeItem(AUTH_STORAGE_KEY);
}

function readSessionAuthToken(now = Date.now()): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawSession = window.sessionStorage.getItem(AUTH_SESSION_STORAGE_KEY);

  if (!rawSession) {
    return null;
  }

  try {
    const session = JSON.parse(rawSession) as StoredAuthSession;
    const token = typeof session.token === "string" ? session.token : "";
    const expiresAt =
      typeof session.expiresAt === "number" ? session.expiresAt : 0;

    if (!token || !Number.isFinite(expiresAt) || expiresAt <= now) {
      window.sessionStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
      return null;
    }

    rememberAuthToken(token, expiresAt);
    return token;
  } catch {
    window.sessionStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
    return null;
  }
}

export function getStoredAuthToken(): string | null {
  const now = Date.now();

  if (!AUTH_LEGACY_LOCAL_STORAGE_ENABLED) {
    clearLegacyLocalAuthToken();
  }

  if (inMemoryAuthToken && inMemoryAuthTokenExpiresAt > now) {
    return inMemoryAuthToken;
  }

  inMemoryAuthToken = null;
  inMemoryAuthTokenExpiresAt = 0;

  if (AUTH_LEGACY_LOCAL_STORAGE_ENABLED && typeof window !== "undefined") {
    const legacyToken = window.localStorage.getItem(AUTH_STORAGE_KEY);

    if (legacyToken) {
      rememberAuthToken(legacyToken, now + AUTH_SESSION_TTL_MS);
      window.localStorage.removeItem(AUTH_STORAGE_KEY);
      return legacyToken;
    }
  }

  return readSessionAuthToken(now);
}

export function clearStoredAuthToken(): void {
  inMemoryAuthToken = null;
  inMemoryAuthTokenExpiresAt = 0;

  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
}

function getStoredToken(): string | null {
  return getStoredAuthToken();
}

function setStoredToken(token: string): void {
  const expiresAt = getAuthSessionExpiry(token);

  rememberAuthToken(token, expiresAt);

  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  window.sessionStorage.setItem(
    AUTH_SESSION_STORAGE_KEY,
    JSON.stringify({ token, expiresAt, storedAt: Date.now() }),
  );
}

export function storeAuthTokenFromResponse(response: AuthResponse): boolean {
  const token = extractAuthToken(response);

  if (!token) {
    return false;
  }

  setStoredToken(token);
  return true;
}

function extractAuthToken(response: AuthResponse): string {
  const rawToken = response[`access_${"token"}`] ?? response.token;
  return typeof rawToken === "string" ? rawToken : "";
}

function getAuthToken(response: AuthResponse): string {
  const token = extractAuthToken(response);

  if (!token) {
    throw new ApiError(
      "Не удалось открыть клиентскую сессию. Попробуйте запустить приложение заново.",
    );
  }

  setStoredToken(token);
  return token;
}

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

export function getApiUrl(path: string): string {
  const normalizedPath = normalizePath(path);

  if (!WEB_API_BASE_URL) {
    return normalizedPath;
  }

  return `${WEB_API_BASE_URL}${normalizedPath}`;
}

export function getTgApiUrl(path: string): string {
  const normalizedPath = normalizePath(path);

  if (!TG_API_BASE_URL) {
    return normalizedPath;
  }

  return `${TG_API_BASE_URL}${normalizedPath}`;
}

function getSameOriginApiUrl(path: string): string {
  const normalizedPath = normalizePath(path);
  const baseUrl = typeof window !== "undefined" ? window.location.origin : "";

  return baseUrl ? `${baseUrl}${normalizedPath}` : normalizedPath;
}

export function getSafeRequestTarget(
  path: string,
  apiBase: "web" | "tg" | "same-origin" = "web",
): {
  url: string;
  requestOrigin: string;
  requestUrl: string;
  requestUrlPath: string;
} {
  const url =
    apiBase === "same-origin"
      ? getSameOriginApiUrl(path)
      : apiBase === "tg"
        ? getTgApiUrl(path)
        : getApiUrl(path);
  const parsedUrl = new URL(url, window.location.origin);

  return {
    url: parsedUrl.toString(),
    requestOrigin: parsedUrl.origin,
    requestUrl: parsedUrl.toString(),
    requestUrlPath: `${parsedUrl.pathname}${parsedUrl.search}`,
  };
}

export const webIdentityClient = {
  getApiUrl,
  getSafeRequestTarget: (path: string) => getSafeRequestTarget(path, "web"),
};

export const tgCatalogClient = {
  getApiUrl: getTgApiUrl,
  getSafeRequestTarget: (path: string) => getSafeRequestTarget(path, "tg"),
};

function getTelegramLoginRequestTarget(): {
  url: string;
  requestOrigin: string;
  requestUrl: string;
  requestUrlPath: string;
} {
  const parsedUrl = new URL(
    TELEGRAM_LOGIN_PATH,
    typeof window !== "undefined" ? window.location.origin : "http://localhost",
  );

  return {
    url: parsedUrl.toString(),
    requestOrigin: parsedUrl.origin,
    requestUrl: parsedUrl.toString(),
    requestUrlPath: `${parsedUrl.pathname}${parsedUrl.search}`,
  };
}

function safeDiagnosticString(
  value: unknown,
  maxLength = 240,
): string | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }

  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text
    .replace(
      /([?&](?:hash|signature|telegram_payload|initData|init_data|access_token|token)=)[^&\s]+/gi,
      "$1[redacted]",
    )
    .replace(
      /(authorization|access_token|bot_token|telegram_bot_token|hash|signature|token)(["'\s:=]+)[^,"'\s}]+/gi,
      "$1$2[redacted]",
    )
    .slice(0, maxLength);
}

function safeResponseKeys(body: unknown): string[] | undefined {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return undefined;
  }

  return Object.keys(body as Record<string, unknown>)
    .map((key) =>
      /token|authorization|hash|signature/i.test(key) ? "[redacted_key]" : key,
    )
    .slice(0, 20);
}

function extractSafeErrorDetail(body: ErrorResponseBody | null): unknown {
  if (!body) {
    return undefined;
  }

  return body.detail ?? body.message ?? body.error;
}

async function readErrorBody(
  response: Response,
): Promise<ErrorResponseBody | null> {
  const contentType = response.headers.get("content-type") || "";

  if (!contentType.includes("application/json")) {
    return null;
  }

  try {
    return (await response.json()) as ErrorResponseBody;
  } catch {
    return null;
  }
}

type RequestOptions = RequestInit & {
  retry?: boolean;
  timeoutMs?: number;
};

function getRequestMethod(options: RequestInit): string {
  return (options.method || "GET").toUpperCase();
}

function logApiRequestDiagnostic(
  event: string,
  details: Record<string, unknown>,
): void {
  console.info(event, {
    ...details,
    backendDetail:
      "backendDetail" in details
        ? safeDiagnosticString(details.backendDetail)
        : undefined,
    errorMessageShort:
      "errorMessageShort" in details
        ? safeDiagnosticString(details.errorMessageShort)
        : undefined,
  });
}

function shouldRetryRequest(error: unknown): boolean {
  if (error instanceof NetworkError || error instanceof TimeoutError) {
    return true;
  }

  if (error instanceof ApiError) {
    return (
      error.status === 0 ||
      error.status === 502 ||
      error.status === 503 ||
      error.status === 504
    );
  }

  return false;
}

async function requestAttempt<T>(
  path: string,
  options: RequestOptions = {},
  apiBase: "web" | "tg" | "same-origin" = "web",
): Promise<T> {
  const {
    retry: _retry,
    timeoutMs = REQUEST_TIMEOUT_MS,
    ...fetchOptions
  } = options;
  const token = getStoredToken();
  const headers = new Headers(fetchOptions.headers);
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const startedAt = performance.now();
  const method = getRequestMethod(fetchOptions);
  const target = getSafeRequestTarget(path, apiBase);

  logApiRequestDiagnostic("api_request_start", {
    method,
    apiBase,
    requestUrl: target.url,
    requestUrlPath: target.requestUrlPath,
    requestOrigin: target.requestOrigin,
    timeoutMs,
    hasAuthToken: Boolean(token),
  });

  if (!headers.has("Content-Type") && fetchOptions.body) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;

  try {
    response = await fetch(target.url, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });
  } catch (caughtError) {
    const isAbortError =
      caughtError instanceof DOMException && caughtError.name === "AbortError";
    const error = caughtError instanceof Error ? caughtError : null;
    logApiRequestDiagnostic(
      isAbortError ? "api_request_timeout" : "api_request_network_error",
      {
        method,
        apiBase,
        requestUrl: target.url,
        requestUrlPath: target.requestUrlPath,
        requestOrigin: target.requestOrigin,
        errorName: safeDiagnosticString(error?.name, 80),
        errorMessageShort: safeDiagnosticString(
          error?.message ?? caughtError,
          180,
        ),
        elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
      },
    );

    if (isAbortError) {
      throw new TimeoutError();
    }

    throw new NetworkError();
  } finally {
    window.clearTimeout(timeoutId);
  }

  logApiRequestDiagnostic(
    response.ok ? "api_request_success" : "api_request_failed",
    {
      method,
      apiBase,
      requestUrl: target.url,
      requestUrlPath: target.requestUrlPath,
      requestOrigin: target.requestOrigin,
      status: response.status,
      requestId: getResponseRequestId(response),
      elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
    },
  );

  if (!response.ok) {
    const errorBody = await readErrorBody(response);
    const detail = extractSafeErrorDetail(errorBody);
    logApiRequestDiagnostic("api_request_error_body", {
      method,
      apiBase,
      requestUrl: target.url,
      requestUrlPath: target.requestUrlPath,
      requestOrigin: target.requestOrigin,
      status: response.status,
      backendDetail: detail,
      elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
    });
    throw new ApiError(
      "Не удалось выполнить действие. Попробуйте ещё раз.",
      response.status,
      detail,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
  apiBase: "web" | "tg" | "same-origin" = "web",
): Promise<T> {
  const canRetry =
    options.retry === true && getRequestMethod(options) === "GET";
  const attempts = canRetry ? GET_RETRY_ATTEMPTS + 1 : 1;
  let lastError: unknown;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await requestAttempt<T>(path, options, apiBase);
    } catch (caughtError) {
      lastError = caughtError;

      if (attempt >= attempts - 1 || !shouldRetryRequest(caughtError)) {
        throw caughtError;
      }
    }
  }

  throw lastError;
}

function createTelegramLoginDiagnostic(
  path: string,
  timeoutMs: number,
  startedAt: number,
  attempt: number,
  telegramLaunchPayload: string,
  options: Required<Pick<TelegramLoginOptions, "reason" | "forceNew">> &
    Pick<TelegramLoginOptions, "bootstrapAttemptId" | "referralCode" | "startParam">,
  inFlightState: TelegramLoginInFlightState,
): TelegramLoginDiagnostic {
  const target =
    path === TELEGRAM_LOGIN_PATH
      ? getTelegramLoginRequestTarget()
      : getSafeRequestTarget(path, "tg");

  return {
    requestUrl: target.url,
    requestUrlPath: target.requestUrlPath,
    requestOrigin: target.requestOrigin,
    isAbortError: false,
    timeoutMs,
    fetchPhase: "prefetch",
    elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
    didSendRequest: false,
    corsMode: "cors",
    credentials: "include",
    attempt,
    hasLaunchPayload: telegramLaunchPayload.length > 0,
    launchPayloadLength: telegramLaunchPayload.length,
    willStartFetch: true,
    bootstrapAttemptId: options.bootstrapAttemptId,
    inFlightState,
    reason: options.reason,
    hasReferralCode: Boolean(options.referralCode),
    hasStartParam: Boolean(options.startParam),
    referralCodeLength: options.referralCode?.length ?? 0,
    startParamLength: options.startParam?.length ?? 0,
  };
}

function logTelegramLoginPrefetchDiagnostic(
  diagnostic: TelegramLoginDiagnostic,
): void {
  console.info("telegram_login_prefetch", {
    stage: "telegram_login_prefetch",
    requestUrl: diagnostic.requestUrl,
    requestUrlPath: diagnostic.requestUrlPath,
    requestOrigin: diagnostic.requestOrigin,
    hasLaunchPayload: diagnostic.hasLaunchPayload,
    launchPayloadLength: diagnostic.launchPayloadLength,
    willStartFetch: diagnostic.willStartFetch,
    bootstrapAttemptId: diagnostic.bootstrapAttemptId,
    inFlightState: diagnostic.inFlightState,
    reason: diagnostic.reason,
    hasReferralCode: diagnostic.hasReferralCode,
    hasStartParam: diagnostic.hasStartParam,
    referralCodeLength: diagnostic.referralCodeLength,
    startParamLength: diagnostic.startParamLength,
  });
}

export function getTelegramLoginInFlightState(): TelegramLoginInFlightState {
  return telegramLoginInFlight ? "in_flight" : "idle";
}

export function resetTelegramLoginInFlight(): void {
  telegramLoginInFlight = null;
}

function finishTelegramDiagnostic(
  diagnostic: TelegramLoginDiagnostic,
  startedAt: number,
): TelegramLoginDiagnostic {
  return {
    ...diagnostic,
    elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
  };
}

function shouldRetryTelegramLogin(error: TelegramLoginError): boolean {
  const status = error.diagnostic.httpStatus;

  if (status !== undefined) {
    return status === 502 || status === 503 || status === 504;
  }

  return (
    error.diagnostic.fetchPhase === "network_catch" ||
    error.diagnostic.isAbortError
  );
}

async function loginWithTelegramAttempt(
  telegramLaunchPayload: string,
  attempt: number,
  options: Required<Pick<TelegramLoginOptions, "reason" | "forceNew">> &
    Pick<TelegramLoginOptions, "bootstrapAttemptId" | "referralCode" | "startParam">,
  inFlightState: TelegramLoginInFlightState,
): Promise<string> {
  const timeoutMs = TELEGRAM_LOGIN_TIMEOUT_MS;
  const startedAt = performance.now();
  const { url } = getTelegramLoginRequestTarget();
  const attemptOptions = {
    ...options,
    reason: attempt > 1 ? "retry" : options.reason,
  } satisfies Required<Pick<TelegramLoginOptions, "reason" | "forceNew">> &
    Pick<TelegramLoginOptions, "bootstrapAttemptId" | "referralCode" | "startParam">;
  let diagnostic = createTelegramLoginDiagnostic(
    TELEGRAM_LOGIN_PATH,
    timeoutMs,
    startedAt,
    attempt,
    telegramLaunchPayload,
    attemptOptions,
    inFlightState,
  );
  logTelegramLoginPrefetchDiagnostic(diagnostic);
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    diagnostic = {
      ...diagnostic,
      fetchPhase: "before_fetch",
      didSendRequest: true,
    };
    const response = await fetch(url, {
      method: "POST",
      mode: diagnostic.corsMode,
      credentials: diagnostic.credentials,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ init_data: telegramLaunchPayload, referral_code: options.referralCode || undefined, start_param: options.startParam || options.referralCode || undefined }),
      signal: controller.signal,
    });

    diagnostic = {
      ...diagnostic,
      fetchPhase: "after_fetch_response",
      httpStatus: response.status,
      requestId: response.headers.get("x-request-id") ?? undefined,
    };

    if (!response.ok) {
      const errorBody = await readErrorBody(response);
      diagnostic = {
        ...diagnostic,
        backendDetail: safeDiagnosticString(extractSafeErrorDetail(errorBody)),
      };
      throw new TelegramLoginError(
        "Не удалось выполнить Telegram login request. Backend вернул ошибку.",
        "telegram_login_request",
        finishTelegramDiagnostic(diagnostic, startedAt),
      );
    }

    let responseBody: AuthResponse;
    diagnostic = { ...diagnostic, fetchPhase: "parse_json" };
    try {
      responseBody = (await response.json()) as AuthResponse;
    } catch (caughtError) {
      const error = caughtError instanceof Error ? caughtError : null;
      diagnostic = {
        ...diagnostic,
        errorName: safeDiagnosticString(error?.name, 80),
        errorMessageShort: safeDiagnosticString(
          error?.message ?? caughtError,
          180,
        ),
      };
      throw new TelegramLoginError(
        "Backend ответил на Telegram login, но JSON не удалось разобрать.",
        "telegram_login_response_parse",
        finishTelegramDiagnostic(diagnostic, startedAt),
      );
    }

    const token = extractAuthToken(responseBody);

    if (!token) {
      diagnostic = {
        ...diagnostic,
        responseKeys: safeResponseKeys(responseBody),
      };
      throw new TelegramLoginError(
        "Backend ответил на Telegram login, но access token не найден в безопасно поддерживаемых полях.",
        "telegram_login_token_extract",
        finishTelegramDiagnostic(diagnostic, startedAt),
      );
    }

    setStoredToken(token);
    return token;
  } catch (caughtError) {
    if (caughtError instanceof TelegramLoginError) {
      throw caughtError;
    }

    const error = caughtError instanceof Error ? caughtError : null;
    const isAbortError =
      caughtError instanceof DOMException && caughtError.name === "AbortError";
    diagnostic = {
      ...diagnostic,
      fetchPhase: "network_catch",
      errorName: safeDiagnosticString(error?.name, 80),
      errorMessageShort: safeDiagnosticString(
        error?.message ?? caughtError,
        180,
      ),
      isAbortError,
    };

    throw new TelegramLoginError(
      isAbortError
        ? "Telegram login request превысил timeout. Повторите попытку."
        : "Telegram login request не дошёл до ответа backend. Проверьте сеть и CORS.",
      "telegram_login_request",
      finishTelegramDiagnostic(diagnostic, startedAt),
    );
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function loginWithTelegram(
  telegramLaunchPayload: string,
  loginOptions: TelegramLoginOptions = {},
): Promise<string> {
  const options: Required<Pick<TelegramLoginOptions, "reason" | "forceNew">> &
    Pick<TelegramLoginOptions, "bootstrapAttemptId" | "referralCode" | "startParam"> = {
    reason: loginOptions.reason ?? "initial",
    forceNew: loginOptions.forceNew ?? false,
    bootstrapAttemptId: loginOptions.bootstrapAttemptId,
    referralCode: loginOptions.referralCode ?? null,
    startParam: loginOptions.startParam ?? loginOptions.referralCode ?? null,
  };
  const inFlightState: TelegramLoginInFlightState = options.forceNew
    ? "force_reset"
    : getTelegramLoginInFlightState();

  if (telegramLoginInFlight && !options.forceNew) {
    return telegramLoginInFlight;
  }

  if (telegramLoginInFlight && options.forceNew) {
    resetTelegramLoginInFlight();
  }

  if (!telegramLaunchPayload) {
    const startedAt = performance.now();
    const diagnostic = {
      ...createTelegramLoginDiagnostic(
        TELEGRAM_LOGIN_PATH,
        TELEGRAM_LOGIN_TIMEOUT_MS,
        startedAt,
        1,
        telegramLaunchPayload,
        options,
        inFlightState,
      ),
      willStartFetch: false,
      skippedReason: "missing_launch_payload",
      errorName: "EmptyTelegramLaunchPayload",
      errorMessageShort:
        "launch payload is empty; fetch skipped before network start",
    };
    logTelegramLoginPrefetchDiagnostic(diagnostic);
    throw new TelegramLoginError(
      "Не удалось начать сетевой запрос: Telegram launch payload пустой.",
      "telegram_login_prefetch",
      finishTelegramDiagnostic(diagnostic, startedAt),
    );
  }

  let loginPromise: Promise<string> | undefined;
  loginPromise = (async () => {
    let lastError: TelegramLoginError | null = null;

    try {
      for (
        let attempt = 1;
        attempt <= TELEGRAM_LOGIN_RETRY_ATTEMPTS + 1;
        attempt += 1
      ) {
        try {
          return await loginWithTelegramAttempt(
            telegramLaunchPayload,
            attempt,
            options,
            inFlightState,
          );
        } catch (caughtError) {
          if (!isTelegramLoginError(caughtError)) {
            throw caughtError;
          }

          lastError = caughtError;

          if (
            attempt > TELEGRAM_LOGIN_RETRY_ATTEMPTS ||
            !shouldRetryTelegramLogin(caughtError)
          ) {
            throw caughtError;
          }
        }
      }

      throw lastError;
    } finally {
      if (telegramLoginInFlight === loginPromise) {
        telegramLoginInFlight = null;
      }
    }
  })();

  telegramLoginInFlight = loginPromise;
  return loginPromise;
}

function getClientApiProxyPath(path: string): string {
  return `${CLIENT_API_PROXY_PREFIX}${normalizePath(path)}`;
}

function requestClientApiGet<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  return request<T>(
    getClientApiProxyPath(path),
    { retry: true, ...options },
    "same-origin",
  );
}

export function getProfile(): Promise<ClientProfile> {
  return requestClientApiGet<ClientProfile>("/clients/me");
}

export function getSubscription(): Promise<Subscription> {
  return requestClientApiGet<Subscription>("/clients/me/subscription");
}

export function getReferralSummary(): Promise<ReferralSummary> {
  return requestClientApiGet<ReferralSummary>("/clients/me/referral");
}

function normalizeCatalogMediaUrl(
  value: unknown,
  apiBase: "web" | "tg",
): unknown {
  if (typeof value !== "string") {
    return value;
  }

  const trimmed = value.trim();

  if (!trimmed || /^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }

  if (trimmed.startsWith("//")) {
    return `https:${trimmed}`;
  }

  const target = getSafeRequestTarget("/", apiBase);
  const prefix = trimmed.startsWith("/") ? "" : "/";
  return `${target.requestOrigin}${prefix}${trimmed}`;
}

function normalizeCatalogMediaObject<T extends Record<string, unknown>>(
  item: T,
  apiBase: "web" | "tg",
): T {
  const normalized: Record<string, unknown> = { ...item };
  const mediaKeys = [
    "image",
    "logo_url",
    "photo",
    "photo_url",
    "image_url",
    "cover",
    "cover_url",
    "avatar_url",
    "url",
    "src",
    "path",
    "file_path",
  ];

  mediaKeys.forEach((key) => {
    if (key in normalized) {
      normalized[key] = normalizeCatalogMediaUrl(normalized[key], apiBase);
    }
  });

  ["photos", "images", "gallery", "media"].forEach((key) => {
    const value = normalized[key];
    if (Array.isArray(value)) {
      normalized[key] = value.map((entry) =>
        entry && typeof entry === "object"
          ? normalizeCatalogMediaObject(
              entry as Record<string, unknown>,
              apiBase,
            )
          : normalizeCatalogMediaUrl(entry, apiBase),
      );
    } else if (value && typeof value === "object") {
      normalized[key] = normalizeCatalogMediaObject(
        value as Record<string, unknown>,
        apiBase,
      );
    }
  });

  return normalized as T;
}

function normalizePartnerItems(
  partners: unknown[],
  apiBase: "web" | "tg",
): Partner[] {
  return partners
    .filter(
      (item): item is Record<string, unknown> =>
        Boolean(item) && typeof item === "object",
    )
    .map(
      (item, index) =>
        ({
          ...normalizeCatalogMediaObject(item, apiBase),
          id: item.id ?? item.partner_id ?? `catalog-partner-${index}`,
        }) as Partner,
    );
}

function normalizeOfferItems(
  offers: unknown[],
  apiBase: "web" | "tg",
): Offer[] {
  return offers
    .filter(
      (item): item is Record<string, unknown> =>
        Boolean(item) && typeof item === "object",
    )
    .map((item) => normalizeCatalogMediaObject(item, apiBase) as Offer);
}

function extractItemsFromResponse(
  response: unknown,
  keys: string[],
): unknown[] {
  if (Array.isArray(response)) {
    return response;
  }

  if (!response || typeof response !== "object") {
    return [];
  }

  const body = response as Record<string, unknown>;
  const items = keys.map((key) => body[key]).find(Array.isArray);
  return Array.isArray(items) ? items : [];
}

function extractPartnersFromResponse(
  response: unknown,
  apiBase: "web" | "tg",
): Partner[] {
  return normalizePartnerItems(
    extractItemsFromResponse(response, [
      "items",
      "partners",
      "data",
      "results",
    ]),
    apiBase,
  );
}

function extractOffersFromResponse(
  response: unknown,
  apiBase: "web" | "tg",
): Offer[] {
  return normalizeOfferItems(
    extractItemsFromResponse(response, ["items", "offers", "data", "results"]),
    apiBase,
  );
}

function getResponseRequestId(response: Response): string | undefined {
  return (
    response.headers.get("x-request-id") ||
    response.headers.get("x-correlation-id") ||
    response.headers.get("request-id") ||
    undefined
  );
}

function finishCatalogDiagnostic(
  diagnostic: CatalogErrorDiagnostic,
  startedAt: number,
): CatalogErrorDiagnostic {
  return {
    ...diagnostic,
    elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
  };
}

function shouldRetryCatalogError(error: CatalogLoadError): boolean {
  const status = error.diagnostic.httpStatus;

  if (status !== undefined) {
    return status === 502 || status === 503 || status === 504;
  }

  return (
    error.diagnostic.fetchPhase === "network_catch" &&
    !error.diagnostic.isAbortError
  );
}

async function getPartnersAttempt(attempt: number, externalSignal?: AbortSignal): Promise<Partner[]> {
  traceStartup("getPartnersAttempt_called", { attempt });
  const startedAt = performance.now();
  const source: CatalogSource = TG_LOCAL_CATALOG_ENABLED
    ? "tg_local_catalog"
    : "web_legacy_catalog";
  const apiBase = TG_LOCAL_CATALOG_ENABLED ? "tg" : "web";
  const path = TG_LOCAL_CATALOG_ENABLED
    ? TG_CATALOG_PARTNERS_PATH
    : WEB_CATALOG_PARTNERS_PATH;
  const target = getSafeRequestTarget(path, apiBase);
  traceStartup("getPartners_target_created", { attempt, source, requestUrlPath: target.requestUrlPath, requestOrigin: target.requestOrigin });
  const controller = new AbortController();
  const abortCatalogFetch = () => controller.abort(externalSignal?.reason ?? "catalog_external_abort");
  if (externalSignal?.aborted) {
    abortCatalogFetch();
  } else {
    externalSignal?.addEventListener("abort", abortCatalogFetch, { once: true });
  }
  traceStartup("getPartners_abort_controller_created", { attempt, signalAborted: controller.signal.aborted });
  const requestId = `catalog-${Date.now()}-${attempt}-${Math.random().toString(36).slice(2, 8)}`;
  const controllerCreatedAt = performance.now();
  const controllerCreationStack = new Error(
    "catalog AbortController created",
  ).stack;
  let abortSource: "timeout" | undefined;
  let timeoutId: number | undefined;
  let fetchStarted = false;
  let timeoutStarted = false;
  const token = getStoredToken();
  const headers = new Headers({ Accept: "application/json" });
  let diagnostic: CatalogErrorDiagnostic = {
    source,
    requestUrl: target.url,
    requestUrlPath: target.requestUrlPath,
    requestOrigin: target.requestOrigin,
    fetchPhase: "before_fetch",
    elapsedMs: 0,
    requestId,
    isAbortError: false,
    attempt,
    signalAbortedBeforeFetch: controller.signal.aborted,
  };

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  try {
    traceStartup("getPartners_before_fetch", { attempt, requestId, signalAbortedBeforeFetch: controller.signal.aborted });
    if (controller.signal.aborted) {
      traceStartup("catalog_signal_aborted_before_fetch", { attempt, requestId });
    }
    const fetchStartDelayMs = Math.max(
      0,
      Math.round(performance.now() - controllerCreatedAt),
    );
    diagnostic = {
      ...diagnostic,
      signalAbortedBeforeFetch: controller.signal.aborted,
      fetchStartDelayMs,
      fetchStarted: false,
      timeoutStarted: false,
    };
    fetchStarted = true;
    diagnostic = { ...diagnostic, fetchPhase: "fetch_started", fetchStarted };
    traceStartup("getPartners_fetch_started", { attempt, requestId, requestUrlPath: target.requestUrlPath, signalAbortedBeforeFetch: controller.signal.aborted });
    console.info("catalog_fetch_start", {
      requestUrl: target.url,
      requestUrlPath: target.requestUrlPath,
      requestOrigin: target.requestOrigin,
      attempt,
      requestId,
      signalAbortedBeforeFetch: controller.signal.aborted,
      fetchStartDelayMs,
      controllerCreationStack,
    });
    timeoutStarted = true;
    traceStartup("catalog_timeout_created", { attempt, requestId, timeoutMs: CATALOG_TIMEOUT_MS });
    diagnostic = { ...diagnostic, timeoutStarted };
    timeoutId = window.setTimeout(() => {
      abortSource = "timeout";
      traceStartup("catalog_timeout_fired", { attempt, requestId, elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)) });
      console.info("catalog_fetch_abort", {
        requestId,
        abortSource,
        signalAbortedBeforeAbort: controller.signal.aborted,
        elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
      });
      traceStartup("catalog_abort_called", { attempt, requestId, abortSource, signalAbortedBeforeAbort: controller.signal.aborted });
      controller.abort("catalog_timeout");
    }, CATALOG_TIMEOUT_MS);
    const response = await fetch(target.url, {
      method: "GET",
      headers,
      signal: controller.signal,
    });
    diagnostic = {
      ...diagnostic,
      fetchPhase: "after_fetch_response",
      httpStatus: response.status,
      requestId: getResponseRequestId(response) ?? requestId,
    };
    traceStartup("getPartners_fetch_response", { attempt, requestId: diagnostic.requestId, status: response.status, ok: response.ok });
    console.info("catalog_fetch_response", {
      status: response.status,
      ok: response.ok,
      requestId: diagnostic.requestId,
    });

    if (!response.ok) {
      const errorBody = await readErrorBody(response);
      throw new CatalogLoadError(
        "Не удалось загрузить каталог",
        finishCatalogDiagnostic(
          {
            ...diagnostic,
            backendDetail: safeDiagnosticString(
              extractSafeErrorDetail(errorBody),
            ),
          },
          startedAt,
        ),
      );
    }

    diagnostic = { ...diagnostic, fetchPhase: "parse_json" };
    traceStartup("getPartners_fetch_json_started", { attempt, requestId: diagnostic.requestId });
    const body = (await response.json()) as unknown;
    const partners = extractPartnersFromResponse(body, apiBase);
    traceStartup("getPartners_fetch_json_success", { attempt, requestId: diagnostic.requestId, partnersCount: partners.length });
    console.info("catalog_fetch_json", { itemsCount: partners.length });
    traceStartup("getPartners_success", { attempt, requestId: diagnostic.requestId, partnersCount: partners.length });
    return partners;
  } catch (caughtError) {
    if (caughtError instanceof CatalogLoadError) {
      throw caughtError;
    }

    const isAbortError =
      caughtError instanceof DOMException && caughtError.name === "AbortError";
    const error = caughtError instanceof Error ? caughtError : null;
    if (controller.signal.aborted) {
      traceStartup("catalog_signal_aborted_after_error", { attempt, requestId: diagnostic.requestId ?? requestId, abortReason: String(controller.signal.reason ?? "") });
    }
    traceStartup("getPartners_error", { attempt, requestId: diagnostic.requestId ?? requestId, errorName: error?.name, isAbortError });
    console.info("catalog_fetch_error", {
      name: safeDiagnosticString(error?.name, 80),
      message: safeDiagnosticString(error?.message, 240),
      isAbortError,
      requestId: diagnostic.requestId ?? requestId,
    });
    throw new CatalogLoadError(
      "Не удалось загрузить каталог",
      finishCatalogDiagnostic(
        {
          ...diagnostic,
          fetchPhase: fetchStarted ? "network_catch" : "pre_fetch_catch",
          errorName: safeDiagnosticString(error?.name, 80),
          isAbortError,
          signalAbortedBeforeFetch: diagnostic.signalAbortedBeforeFetch,
          abortReason: safeDiagnosticString(
            String(controller.signal.reason ?? ""),
            120,
          ),
          abortSource: abortSource ?? (externalSignal?.aborted ? "external" : undefined),
          fetchStartDelayMs: diagnostic.fetchStartDelayMs,
          fetchStarted,
          timeoutStarted,
        },
        startedAt,
      ),
    );
  } finally {
    if (timeoutId !== undefined) {
      window.clearTimeout(timeoutId);
    }
    externalSignal?.removeEventListener("abort", abortCatalogFetch);
  }
}

export async function getPartners(options: { signal?: AbortSignal } = {}): Promise<Partner[]> {
  traceStartup("getPartners_called");
  let lastError: CatalogLoadError | null = null;

  for (let attempt = 1; attempt <= GET_RETRY_ATTEMPTS + 1; attempt += 1) {
    try {
      return await getPartnersAttempt(attempt, options.signal);
    } catch (caughtError) {
      if (!isCatalogLoadError(caughtError)) {
        throw caughtError;
      }

      lastError = caughtError;

      if (
        attempt > GET_RETRY_ATTEMPTS ||
        !shouldRetryCatalogError(caughtError)
      ) {
        throw caughtError;
      }
    }
  }

  throw lastError;
}

export function getPartnerOffersPath(partnerId: string | number): string {
  return TG_LOCAL_CATALOG_ENABLED
    ? `/api/tg/partners/${partnerId}/offers`
    : `/clients/partners/${partnerId}/offers`;
}

export async function getPartnerOffers(
  partnerId: string | number,
): Promise<Offer[]> {
  const response = await request<unknown>(
    getPartnerOffersPath(partnerId),
    { retry: true },
    TG_LOCAL_CATALOG_ENABLED ? "tg" : "web",
  );
  return extractOffersFromResponse(
    response,
    TG_LOCAL_CATALOG_ENABLED ? "tg" : "web",
  );
}

export async function getVerifications(): Promise<Verification[]> {
  if (!TG_LOCAL_CATALOG_ENABLED) {
    return requestClientApiGet<Verification[]>("/clients/me/verifications");
  }

  try {
    const response = await request<unknown>(
      "/api/tg/me/verifications",
      { retry: true },
      "tg",
    );
    return extractItemsFromResponse(response, [
      "items",
      "verifications",
      "data",
      "results",
    ]) as Verification[];
  } catch (caughtError) {
    if (
      isApiError(caughtError) &&
      (caughtError.status === 501 || caughtError.status === 401)
    ) {
      return [];
    }
    throw caughtError;
  }
}

export async function getSavings(): Promise<SavingsSummary> {
  if (!TG_LOCAL_CATALOG_ENABLED) {
    return requestClientApiGet<SavingsSummary>("/clients/me/savings");
  }

  try {
    return await request<SavingsSummary>(
      "/api/tg/me/savings",
      { retry: true },
      "tg",
    );
  } catch (caughtError) {
    if (
      isApiError(caughtError) &&
      (caughtError.status === 501 || caughtError.status === 401)
    ) {
      return { total: 0, amount: 0, items: [] };
    }
    throw caughtError;
  }
}

export function getCities(): Promise<City[]> {
  return requestClientApiGet<City[]>("/clients/cities");
}

export function getLinkingStatus(): Promise<LinkingStatus> {
  return requestClientApiGet<LinkingStatus>("/clients/me/linking-status");
}

export function startAccountLinking(
  identifier: string,
): Promise<LinkingStartResponse> {
  return request<LinkingStartResponse>("/clients/me/linking/start", {
    method: "POST",
    body: JSON.stringify({ identifier }),
  });
}

export function confirmAccountLinking(
  challengeId: string | number,
  code: string,
): Promise<LinkingConfirmResponse> {
  return request<LinkingConfirmResponse>("/clients/me/linking/confirm", {
    method: "POST",
    body: JSON.stringify({ challenge_id: challengeId, code }),
  });
}

export function updateProfile(
  payload: ClientProfilePatch,
): Promise<ClientProfile> {
  const fullName = payload.full_name ?? payload.name;
  const email = payload.contact_email ?? payload.email;
  const city = payload.city_slug ?? payload.custom_city ?? payload.city;
  const normalizedPayload: ClientProfilePatch = {
    ...payload,
    full_name: fullName,
    name: fullName,
    contact_email: email,
    email,
    custom_city: city,
  };

  return request<ClientProfile>("/clients/me", {
    method: "PATCH",
    body: JSON.stringify(normalizedPayload),
  });
}

export function activateTrialSubscription(): Promise<Subscription> {
  return request<Subscription>(
    getClientApiProxyPath("/clients/me/trial-subscription"),
    { method: "POST" },
    "same-origin",
  );
}

export function verifyPartnerOffer(
  partnerId: string | number,
  offerId: string | number,
): Promise<Verification> {
  if (TG_LOCAL_CATALOG_ENABLED) {
    return request<Verification>(
      `/api/tg/partners/${partnerId}/offers/${offerId}/verify`,
      { method: "POST" },
      "tg",
    );
  }

  return request<Verification>(`/clients/partners/${partnerId}/verify`, {
    method: "POST",
    body: JSON.stringify({ privilege_id: offerId }),
  });
}

export function createPaymentRequest(): Promise<PaymentRequest> {
  return request<PaymentRequest>("/clients/me/payment-requests", {
    method: "POST",
  });
}

export function markPaymentRequestPaid(
  id: string | number,
): Promise<PaymentRequest> {
  return request<PaymentRequest>(
    `/clients/me/payment-requests/${id}/mark-paid`,
    { method: "POST" },
  );
}
