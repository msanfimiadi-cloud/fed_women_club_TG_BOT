export type StartupTraceStatus = "start" | "ok" | "fail" | "mark";

export interface StartupTraceEvent {
  timestamp: string;
  elapsedMs: number;
  step: string;
  status: StartupTraceStatus;
  details?: Record<string, unknown>;
}

declare global {
  interface Window {
    __BLOOM_STARTUP_TRACE__?: StartupTraceEvent[];
  }
}

const appEntryTime = Date.now();
const SENSITIVE_KEY_PATTERN = /(authorization|initdata|init_data|telegram_payload|access_token|token|signature|hash|credential|telegram_admin_api_token)/i;
const MAX_EVENTS = 200;

function sanitizeText(text: string): string {
  return text
    .replace(/(Authorization\s*[:=]\s*)[^\s,}]+/gi, "$1[redacted]")
    .replace(/(initData|init_data|telegram_payload|access_token|token|signature|hash)=([^&\s]+)/gi, "$1=[redacted]")
    .slice(0, 500);
}

function sanitizeValue(value: unknown, depth = 0): unknown {
  if (depth > 3) return "[depth-limit]";
  if (value instanceof Error) return { name: value.name, message: sanitizeText(value.message) };
  if (typeof value === "string") return sanitizeText(value);
  if (typeof value === "number" || typeof value === "boolean" || value === null) return value;
  if (Array.isArray(value)) return value.slice(0, 20).map((item) => sanitizeValue(item, depth + 1));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([key]) => !SENSITIVE_KEY_PATTERN.test(key))
        .map(([key, item]) => [key, sanitizeValue(item, depth + 1)]),
    );
  }
  return undefined;
}

function isStartupTraceEnabled(): boolean {
  if (import.meta.env.DEV) return true;
  if (typeof window === "undefined") return false;
  try {
    return window.BLOOM_DEBUG === true ||
      window.__BLOOM_DEBUG_ENABLED__ === true ||
      window.localStorage.getItem("BLOOM_DEBUG") === "1" ||
      window.sessionStorage.getItem("BLOOM_DEBUG") === "1" ||
      new URLSearchParams(window.location.search).get("debug") === "1";
  } catch {
    return window.BLOOM_DEBUG === true || window.__BLOOM_DEBUG_ENABLED__ === true;
  }
}

function isStartupTraceConsoleEnabled(): boolean {
  if (typeof window === "undefined") return false;
  return window.__BLOOM_DEBUG_ENABLED__ === true || new URLSearchParams(window.location.search).get("debug") === "1";
}

function pushTrace(status: StartupTraceStatus, step: string, details?: unknown): StartupTraceEvent {
  const event: StartupTraceEvent = {
    timestamp: new Date().toISOString(),
    elapsedMs: Math.max(0, Date.now() - appEntryTime),
    step,
    status,
    details: sanitizeValue(details) as Record<string, unknown> | undefined,
  };

  if (isStartupTraceEnabled() && typeof window !== "undefined") {
    const trace = window.__BLOOM_STARTUP_TRACE__ ?? [];
    trace.push(event);
    if (trace.length > MAX_EVENTS) trace.splice(0, trace.length - MAX_EVENTS);
    window.__BLOOM_STARTUP_TRACE__ = trace;
  }

  if (isStartupTraceConsoleEnabled()) {
    console.debug("bloom_startup_trace", event);
  }
  return event;
}

export function traceStart(step: string, details?: unknown): StartupTraceEvent {
  return pushTrace("start", step, details);
}

export function traceOk(step: string, details?: unknown): StartupTraceEvent {
  return pushTrace("ok", step, details);
}

export function traceFail(step: string, errorOrDetails?: unknown): StartupTraceEvent {
  return pushTrace("fail", step, errorOrDetails);
}

export function traceMark(step: string, details?: unknown): StartupTraceEvent {
  return pushTrace("mark", step, details);
}

export function getStartupTrace(): StartupTraceEvent[] {
  return typeof window === "undefined" ? [] : [...(window.__BLOOM_STARTUP_TRACE__ ?? [])];
}


export function traceStartup(event: string, payload?: unknown): StartupTraceEvent {
  return traceMark(event, payload);
}

export function isStartupTraceDebugEnabled(): boolean {
  return isStartupTraceEnabled();
}
