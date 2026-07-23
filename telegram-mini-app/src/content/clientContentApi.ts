import { ApiError, NetworkError, TimeoutError } from "../api/client";

const DEFAULT_CONTENT_API_BASE_URL = "https://bloomclub.ru/api/content";
const SAME_ORIGIN_CONTENT_API_BASE_PATH = "/api/content";
const CONTENT_REQUEST_TIMEOUT_MS = 20_000;

export interface ContentBlock {
  key: string;
  value: string;
  title?: string;
  placement?: string;
  updated_at?: string;
}

export type HomeBlockType =
  | "hero"
  | "banner"
  | "text"
  | "partners_carousel"
  | "giveaway"
  | "custom_cta"
  | "image"
  | "html_text";

export interface HomeBlock {
  id: string | number;
  type: HomeBlockType;
  title: string;
  subtitle: string;
  body: string;
  image_url: string;
  cta_text: string;
  cta_action: string;
  sort_order: number;
  is_active: boolean;
  metadata_json: Record<string, unknown>;
  updated_at?: string;
}

function normalizeContentApiBaseUrl(rawBaseUrl: string | undefined): string {
  const candidate = (rawBaseUrl || DEFAULT_CONTENT_API_BASE_URL).trim().replace(/\/+$/, "");

  if (!/^https?:\/\//i.test(candidate)) {
    return DEFAULT_CONTENT_API_BASE_URL;
  }

  try {
    return new URL(candidate).toString().replace(/\/+$/, "");
  } catch {
    return DEFAULT_CONTENT_API_BASE_URL;
  }
}

export const CONTENT_API_BASE_URL = normalizeContentApiBaseUrl(import.meta.env.VITE_CONTENT_API_BASE_URL);

function getContentApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return normalizedPath.startsWith("/blocks")
    ? `${SAME_ORIGIN_CONTENT_API_BASE_PATH}${normalizedPath}`
    : `${CONTENT_API_BASE_URL}${normalizedPath}`;
}

function asString(value: unknown): string {
  return value === undefined || value === null ? "" : String(value);
}

function asNumber(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseMetadata(value: unknown): Record<string, unknown> {
  if (!value) {
    return {};
  }

  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value) as unknown;
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }

  return typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function normalizeContentBlock(item: unknown): ContentBlock | null {
  if (!item || typeof item !== "object") {
    return null;
  }

  const record = item as Record<string, unknown>;
  const key = record.key ?? record.block_key ?? record.name;
  const value = record.value ?? record.text ?? record.content ?? record.body;

  if (typeof key !== "string" || key.trim() === "") {
    return null;
  }

  return {
    key: key.trim(),
    value: value === undefined || value === null ? "" : String(value),
    title: typeof record.title === "string" ? record.title : undefined,
    placement: typeof record.placement === "string" ? record.placement : undefined,
    updated_at: typeof record.updated_at === "string" ? record.updated_at : undefined,
  };
}

function extractBlocksFromResponse(response: unknown): ContentBlock[] {
  if (Array.isArray(response)) {
    return response.map(normalizeContentBlock).filter((item): item is ContentBlock => Boolean(item));
  }

  if (!response || typeof response !== "object") {
    return [];
  }

  const body = response as Record<string, unknown>;
  const candidate = [body.items, body.blocks, body.data, body.results].find(Array.isArray);
  return Array.isArray(candidate)
    ? candidate.map(normalizeContentBlock).filter((item): item is ContentBlock => Boolean(item))
    : [];
}

const HOME_BLOCK_TYPES: HomeBlockType[] = ["hero", "banner", "text", "partners_carousel", "giveaway", "custom_cta", "image", "html_text"];

function normalizeHomeBlock(item: unknown, fallbackSortOrder = 100): HomeBlock | null {
  if (!item || typeof item !== "object") {
    return null;
  }

  const record = item as Record<string, unknown>;
  const rawType = asString(record.type ?? record.block_type ?? record.kind).trim();
  const type = HOME_BLOCK_TYPES.includes(rawType as HomeBlockType) ? (rawType as HomeBlockType) : null;
  const id = record.id ?? record.block_id ?? record.key;

  if (!type || id === undefined || id === null || String(id).trim() === "") {
    return null;
  }

  return {
    id: typeof id === "number" ? id : String(id),
    type,
    title: asString(record.title ?? record.name),
    subtitle: asString(record.subtitle ?? record.caption),
    body: asString(record.body ?? record.description ?? record.value ?? record.text ?? record.content),
    image_url: asString(record.image_url ?? record.photo_url ?? record.cover_url ?? record.image),
    cta_text: asString(record.cta_text ?? record.button_text),
    cta_action: asString(record.cta_action ?? record.cta_url ?? record.action),
    sort_order: asNumber(record.sort_order ?? record.order ?? record.position, fallbackSortOrder),
    is_active: record.is_active === false || record.active === false || record.hidden === true ? false : true,
    metadata_json: parseMetadata(record.metadata_json ?? record.metadata ?? record.meta),
    updated_at: typeof record.updated_at === "string" ? record.updated_at : undefined,
  };
}

function extractHomeBlocksFromResponse(response: unknown): HomeBlock[] {
  const normalize = (items: unknown[]) =>
    items
      .map((item, index) => normalizeHomeBlock(item, (index + 1) * 100))
      .filter((item): item is HomeBlock => Boolean(item))
      .sort((left, right) => left.sort_order - right.sort_order);

  if (Array.isArray(response)) {
    return normalize(response);
  }

  if (!response || typeof response !== "object") {
    return [];
  }

  const body = response as Record<string, unknown>;
  const candidate = [body.items, body.blocks, body.home_blocks, body.data, body.results].find(Array.isArray);
  return Array.isArray(candidate) ? normalize(candidate) : [];
}

function safeContentDiagnosticText(value: unknown, maxLength = 500): string | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }

  return (typeof value === "string" ? value : JSON.stringify(value))
    .replace(/(credential|signature|token)(["'\s:=]+)(?:Bearer\s+)?[^,"'\s}]+/gi, "$1$2[hidden]")
    .slice(0, maxLength);
}

function getContentRequestId(response: Response): string | undefined {
  return response.headers.get("x-request-id") || response.headers.get("x-correlation-id") || response.headers.get("request-id") || undefined;
}

async function readContentErrorDetail(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return undefined;
  }

  try {
    const body = (await response.clone().json()) as Record<string, unknown>;
    return body.detail ?? body.message ?? body.error;
  } catch {
    return undefined;
  }
}

async function contentRequest<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), CONTENT_REQUEST_TIMEOUT_MS);
  const requestUrl = getContentApiUrl(path);
  const parsedRequestUrl = new URL(requestUrl, window.location.origin);
  const startedAt = performance.now();

  console.info("content_request_start", {
    method: "GET",
    requestUrlPath: `${parsedRequestUrl.pathname}${parsedRequestUrl.search}`,
    requestOrigin: parsedRequestUrl.origin,
    timeoutMs: CONTENT_REQUEST_TIMEOUT_MS,
    hasAuthToken: false,
  });

  let response: Response;

  try {
    response = await fetch(requestUrl, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
  } catch (caughtError) {
    const isAbortError = caughtError instanceof DOMException && caughtError.name === "AbortError";
    const error = caughtError instanceof Error ? caughtError : null;
    console.info(isAbortError ? "content_request_timeout" : "content_request_network_error", {
      method: "GET",
      requestUrlPath: `${parsedRequestUrl.pathname}${parsedRequestUrl.search}`,
      requestOrigin: parsedRequestUrl.origin,
      errorName: safeContentDiagnosticText(error?.name, 80),
      errorMessageShort: safeContentDiagnosticText(error?.message ?? caughtError, 180),
      elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
    });

    if (isAbortError) {
      throw new TimeoutError(`Content API не отвечает: GET ${parsedRequestUrl.pathname}${parsedRequestUrl.search}`);
    }

    throw new NetworkError(`Content API недоступен: GET ${parsedRequestUrl.pathname}${parsedRequestUrl.search}`);
  } finally {
    window.clearTimeout(timeoutId);
  }

  console.info(response.ok ? "content_request_success" : "content_request_failed", {
    method: "GET",
    requestUrlPath: `${parsedRequestUrl.pathname}${parsedRequestUrl.search}`,
    requestOrigin: parsedRequestUrl.origin,
    status: response.status,
    requestId: getContentRequestId(response),
    elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
  });

  if (!response.ok) {
    console.info("content_request_error_body", {
      method: "GET",
      requestUrlPath: `${parsedRequestUrl.pathname}${parsedRequestUrl.search}`,
      requestOrigin: parsedRequestUrl.origin,
      status: response.status,
      backendDetail: safeContentDiagnosticText(await readContentErrorDetail(response)),
      elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
    });
    throw new ApiError(`Content API вернул ошибку: GET ${parsedRequestUrl.pathname}${parsedRequestUrl.search}`, response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(`Content API вернул некорректный JSON: GET ${parsedRequestUrl.pathname}${parsedRequestUrl.search}`, response.status);
  }
}

function contentBlocksEndpoint(path: string): string {
  const requestUrl = getContentApiUrl(path);
  const parsedRequestUrl = new URL(requestUrl, window.location.origin);
  return `${parsedRequestUrl.pathname}${parsedRequestUrl.search}`;
}

function logContentBlocksLoaded(placementOrType: string, count: number): void {
  console.info("content_blocks_loaded", { placementOrType, count });

  if (count === 0) {
    console.warn("content_blocks_empty", { placementOrType });
  }
}

function logContentBlocksFailed(endpoint: string, status: number | undefined, error: unknown): void {
  console.error("content_blocks_failed", {
    endpoint,
    status,
    message: safeContentDiagnosticText(error instanceof Error ? error.message : error, 240),
  });
}

export async function getContentBlocks(): Promise<ContentBlock[]> {
  const path = "/blocks?type=static_texts";
  const placementOrType = "type=static_texts";

  try {
    const response = await contentRequest<unknown>(path);
    const blocks = extractBlocksFromResponse(response);
    logContentBlocksLoaded(placementOrType, blocks.length);
    return blocks;
  } catch (caughtError) {
    logContentBlocksFailed(contentBlocksEndpoint(path), caughtError instanceof ApiError ? caughtError.status : undefined, caughtError);
    return [];
  }
}

export async function getHomeBlocks(): Promise<HomeBlock[]> {
  const path = "/blocks?placement=telegram_home";
  const placementOrType = "telegram_home";

  try {
    const response = await contentRequest<unknown>(path);
    const blocks = extractHomeBlocksFromResponse(response);
    logContentBlocksLoaded(placementOrType, blocks.length);
    return blocks;
  } catch (caughtError) {
    logContentBlocksFailed(contentBlocksEndpoint(path), caughtError instanceof ApiError ? caughtError.status : undefined, caughtError);
    return [];
  }
}
