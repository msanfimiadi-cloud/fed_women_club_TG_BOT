export interface PageLifecycleTraceEvent {
  timestamp: string;
  elapsedMs: number;
  event: string;
  visibilityState: DocumentVisibilityState;
  documentReadyState: DocumentReadyState;
  locationHref: string;
  locationHash: string;
  pageId?: string;
  hasReactRoot: boolean;
  hasTelegramObject: boolean;
  hasTelegramWebApp: boolean;
  details?: Record<string, unknown>;
}

type LifecycleListenerCleanup = () => void;

type BrowserLifecycleEventName =
  | "DOMContentLoaded"
  | "load"
  | "readystatechange"
  | "visibilitychange"
  | "pageshow"
  | "pagehide"
  | "freeze"
  | "resume"
  | "focus"
  | "blur"
  | "beforeunload"
  | "unload"
  | "hashchange"
  | "popstate"
  | "online"
  | "offline"
  | "error"
  | "unhandledrejection";

declare global {
  interface Window {
    __BLOOM_PAGE_LIFECYCLE__?: PageLifecycleTraceEvent[];
    __BLOOM_PAGE_LIFECYCLE_PAGE_ID__?: string;
    __BLOOM_PAGE_LIFECYCLE_CLEANUP__?: LifecycleListenerCleanup;
    __BLOOM_REACT_MOUNTED__?: boolean;
    __BLOOM_LAST_RENDER__?: string;
    __BLOOM_LAST_EFFECT__?: string;
    __BLOOM_LAST_BOOTSTRAP_STEP__?: string;
  }
}

const MAX_LIFECYCLE_EVENTS = 300;
const lifecycleStartTime = Date.now();
const SENSITIVE_KEY_PATTERN =
  /(authorization|initdata|init_data|telegram_payload|launch_payload|telegram payload|jwt|cookie|secret|password|access_token|token|signature|hash|credential|telegram_admin_api_token)/i;
const installedListeners: LifecycleListenerCleanup[] = [];
let listenersInstalled = false;

function sanitizeText(text: string): string {
  try {
    return text
      .replace(/(Authorization\s*[:=]\s*)[^\s,}]+/gi, "$1[redacted]")
      .replace(
        /([?&#](?:initData|init_data|telegram_payload|access_token|token|signature|hash)=)([^&\s]+)/gi,
        "$1[redacted]",
      )
      .replace(
        /((?:initData|init_data|telegram_payload|access_token|token|signature|hash)\s*[:=]\s*)[^&\s,}]+/gi,
        "$1[redacted]",
      )
      .slice(0, 800);
  } catch {
    return "[unserializable]";
  }
}

function sanitizeValue(value: unknown, depth = 0): unknown {
  try {
    if (depth > 3) return "[depth-limit]";
    if (value instanceof Error)
      return { name: value.name, message: sanitizeText(value.message) };
    if (typeof value === "string") return sanitizeText(value);
    if (
      typeof value === "number" ||
      typeof value === "boolean" ||
      value === null
    )
      return value;
    if (Array.isArray(value))
      return value.slice(0, 20).map((item) => sanitizeValue(item, depth + 1));
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value as Record<string, unknown>).map(([key, item]) => [
          key,
          SENSITIVE_KEY_PATTERN.test(key)
            ? "[redacted]"
            : sanitizeValue(item, depth + 1),
        ]),
      );
    }
    return undefined;
  } catch {
    return "[unserializable]";
  }
}

function getSafeLocationHref(): string {
  return typeof window === "undefined"
    ? ""
    : sanitizeText(window.location.href);
}

function getSafeLocationHash(): string {
  return typeof window === "undefined"
    ? ""
    : sanitizeText(window.location.hash);
}

function getPageId(): string | undefined {
  return typeof window === "undefined"
    ? undefined
    : window.__BLOOM_PAGE_LIFECYCLE_PAGE_ID__;
}

function hasReactRoot(): boolean {
  if (typeof document === "undefined") return false;
  const root = document.getElementById("root");
  return Boolean(root && root.childElementCount > 0);
}

function createEvent(
  eventName: string,
  details?: unknown,
): PageLifecycleTraceEvent {
  let telegram: Window["Telegram"] | undefined;
  try {
    telegram = typeof window === "undefined" ? undefined : window.Telegram;
  } catch {
    telegram = undefined;
  }
  return {
    timestamp: new Date().toISOString(),
    elapsedMs: Math.max(0, Date.now() - lifecycleStartTime),
    event: eventName,
    visibilityState:
      typeof document === "undefined" ? "visible" : document.visibilityState,
    documentReadyState:
      typeof document === "undefined" ? "loading" : document.readyState,
    locationHref: getSafeLocationHref(),
    locationHash: getSafeLocationHash(),
    pageId: getPageId(),
    hasReactRoot: hasReactRoot(),
    hasTelegramObject: Boolean(telegram),
    hasTelegramWebApp: Boolean(telegram?.WebApp),
    details: sanitizeValue(details) as Record<string, unknown> | undefined,
  };
}

export function lifecycleTrace(
  eventName: string,
  details?: unknown,
): PageLifecycleTraceEvent {
  let event: PageLifecycleTraceEvent;
  try {
    event = createEvent(eventName, details);
  } catch {
    event = {
      timestamp: new Date().toISOString(),
      elapsedMs: Math.max(0, Date.now() - lifecycleStartTime),
      event: eventName,
      visibilityState: "visible",
      documentReadyState: "loading",
      locationHref: "",
      locationHash: "",
      hasReactRoot: false,
      hasTelegramObject: false,
      hasTelegramWebApp: false,
      details: { sanitizeError: true },
    };
  }

  if (typeof window !== "undefined") {
    if (eventName.includes("render")) window.__BLOOM_LAST_RENDER__ = eventName;
    if (
      eventName.includes("effect") ||
      eventName.includes("mount") ||
      eventName.includes("unmount")
    )
      window.__BLOOM_LAST_EFFECT__ = eventName;
    if (eventName.endsWith("_ok") || eventName === "bootstrap_done")
      window.__BLOOM_LAST_BOOTSTRAP_STEP__ = eventName;
  }

  if (typeof window !== "undefined") {
    const trace = window.__BLOOM_PAGE_LIFECYCLE__ ?? [];
    trace.push(event);
    if (trace.length > MAX_LIFECYCLE_EVENTS) {
      trace.splice(0, trace.length - MAX_LIFECYCLE_EVENTS);
    }
    window.__BLOOM_PAGE_LIFECYCLE__ = trace;
  }

  try {
    console.info("bloom_page_lifecycle", event);
  } catch {
    // keep diagnostics fail-safe
  }
  return event;
}

export function setLifecyclePageId(pageId: string | undefined): void {
  if (typeof window === "undefined") return;
  window.__BLOOM_PAGE_LIFECYCLE_PAGE_ID__ = pageId;
  lifecycleTrace("page_id_update", { pageId });
}

export function getLifecycleTrace(): PageLifecycleTraceEvent[] {
  return typeof window === "undefined"
    ? []
    : [...(window.__BLOOM_PAGE_LIFECYCLE__ ?? [])];
}

function addLifecycleListener(
  target: Window | Document,
  eventName: BrowserLifecycleEventName,
  listener: EventListener,
): void {
  target.addEventListener(eventName, listener);
  installedListeners.push(() =>
    target.removeEventListener(eventName, listener),
  );
}

function getEventDetails(event: Event): Record<string, unknown> | undefined {
  if (event instanceof PageTransitionEvent)
    return { persisted: event.persisted };
  if (event instanceof HashChangeEvent)
    return { oldURL: event.oldURL, newURL: event.newURL };
  if (event instanceof PopStateEvent) return { state: event.state };
  if (event instanceof ErrorEvent)
    return {
      message: event.message,
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
      error: event.error,
    };
  if (event instanceof PromiseRejectionEvent) return { reason: event.reason };
  return undefined;
}

export function cleanupLifecycleTraceListeners(): void {
  while (installedListeners.length > 0) {
    installedListeners.pop()?.();
  }
  listenersInstalled = false;
}

export function installLifecycleTraceListeners(): LifecycleListenerCleanup {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return () => undefined;
  }

  if (listenersInstalled) {
    return cleanupLifecycleTraceListeners;
  }

  listenersInstalled = true;
  const documentEvents: BrowserLifecycleEventName[] = [
    "DOMContentLoaded",
    "readystatechange",
    "visibilitychange",
    "freeze",
    "resume",
  ];
  const windowEvents: BrowserLifecycleEventName[] = [
    "load",
    "pageshow",
    "pagehide",
    "focus",
    "blur",
    "beforeunload",
    "unload",
    "hashchange",
    "popstate",
    "online",
    "offline",
    "error",
    "unhandledrejection",
  ];

  try {
    documentEvents.forEach((eventName) => {
      try {
        addLifecycleListener(document, eventName, (event) =>
          lifecycleTrace(eventName, getEventDetails(event)),
        );
      } catch {
        // listener setup must not break entry startup
      }
    });
    windowEvents.forEach((eventName) => {
      try {
        addLifecycleListener(window, eventName, (event) =>
          lifecycleTrace(eventName, getEventDetails(event)),
        );
      } catch {
        // listener setup must not break entry startup
      }
    });

    window.__BLOOM_PAGE_LIFECYCLE_CLEANUP__ = cleanupLifecycleTraceListeners;
    lifecycleTrace("lifecycle_listeners_installed", {
      bufferSize: MAX_LIFECYCLE_EVENTS,
    });
  } catch {
    listenersInstalled = false;
  }
  return cleanupLifecycleTraceListeners;
}

try {
  installLifecycleTraceListeners();
} catch {
  // lifecycleTrace is diagnostic-only and must never break entry startup
}

export function markReactMounted(isMounted: boolean): void {
  if (typeof window !== "undefined") window.__BLOOM_REACT_MOUNTED__ = isMounted;
}

export function createLifecycleDiagnosticSnapshot(
  reason: string,
): Record<string, unknown> {
  const telegram = typeof window === "undefined" ? undefined : window.Telegram;
  return {
    reason: sanitizeValue(reason),
    pageLifecycle: getLifecycleTrace().slice(-100),
    startupTrace:
      typeof window === "undefined"
        ? []
        : (window.__BLOOM_STARTUP_TRACE__ ?? []).slice(-100),
    documentVisibilityState:
      typeof document === "undefined" ? "unknown" : document.visibilityState,
    documentReadyState:
      typeof document === "undefined" ? "unknown" : document.readyState,
    locationHref: getSafeLocationHref(),
    locationHash: getSafeLocationHash(),
    reactMounted: Boolean(
      typeof window !== "undefined" && window.__BLOOM_REACT_MOUNTED__,
    ),
    hasTelegramObject: Boolean(telegram),
    hasTelegramWebApp: Boolean(telegram?.WebApp),
    currentPage: getPageId(),
    lastRender:
      typeof window === "undefined" ? undefined : window.__BLOOM_LAST_RENDER__,
    lastEffect:
      typeof window === "undefined" ? undefined : window.__BLOOM_LAST_EFFECT__,
    lastCompletedBootstrapStep:
      typeof window === "undefined"
        ? undefined
        : window.__BLOOM_LAST_BOOTSTRAP_STEP__,
  };
}
