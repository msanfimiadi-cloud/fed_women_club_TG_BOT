import { appBuildInfo } from "../buildInfo";

const ENDPOINT = "/api/client-errors";
const MAX_MESSAGE_LENGTH = 2000;
const MAX_STACK_LENGTH = 6000;

function truncate(value: unknown, maxLength: number): string | undefined {
  if (value === undefined || value === null) return undefined;
  const text = value instanceof Error ? value.message : String(value);
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
}

function getTelegramStartParam(): string | undefined {
  try {
    const webApp = window.Telegram?.WebApp;
    const startParam = (webApp?.initDataUnsafe as { start_param?: unknown } | undefined)?.start_param;
    if (typeof startParam === "string" && startParam) return startParam.slice(0, 256);
    const params = new URLSearchParams(window.location.search);
    return params.get("tgWebAppStartParam")?.slice(0, 256) || params.get("startapp")?.slice(0, 256) || undefined;
  } catch {
    return undefined;
  }
}

function normalizeError(error: unknown): { name?: string; message?: string; stack?: string } {
  if (error instanceof Error) {
    return {
      name: truncate(error.name, 120),
      message: truncate(error.message, MAX_MESSAGE_LENGTH),
      stack: truncate(error.stack, MAX_STACK_LENGTH),
    };
  }
  return { message: truncate(error, MAX_MESSAGE_LENGTH) };
}

export function reportClientError(eventType: string, error: unknown, extra: Record<string, unknown> = {}): void {
  if (typeof window === "undefined") return;
  const payload = {
    eventType,
    build: appBuildInfo,
    url: window.location.href,
    pathname: window.location.pathname,
    search: window.location.search,
    hash: window.location.hash,
    tgStartParam: getTelegramStartParam(),
    userAgent: navigator.userAgent,
    error: normalizeError(error),
    extra,
    occurredAt: new Date().toISOString(),
  };

  try {
    const body = JSON.stringify(payload);
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(ENDPOINT, blob)) return;
    }
    void fetch(ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
      credentials: "same-origin",
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // Client-side diagnostics must never break app startup.
  }
}

function getForcedReloadCount(): number {
  try {
    return Number(window.sessionStorage.getItem("bloom_forced_reload_count") ?? "0") || 0;
  } catch {
    return 0;
  }
}

function incrementForcedReloadCount(): void {
  try {
    window.sessionStorage.setItem("bloom_forced_reload_count", String(getForcedReloadCount() + 1));
  } catch {
    // Storage failures must not block startup.
  }
}

export async function reloadWhenServerBuildDiffers(): Promise<void> {
  try {
    const response = await fetch(`/api/runtime-config?clientBuildId=${encodeURIComponent(appBuildInfo.buildHash)}`, {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) return;
    const config = await response.json() as { buildId?: string };
    if (config.buildId && config.buildId !== appBuildInfo.buildHash) {
      const forcedReloadCount = getForcedReloadCount();
      if (forcedReloadCount >= 2) {
        reportClientError("frontend_build_mismatch_reload_limit", new Error("frontend_build_mismatch_reload_limit"), {
          clientBuildId: appBuildInfo.buildHash,
          serverBuildId: config.buildId,
          forcedReloadCount,
        });
        return;
      }
      reportClientError("frontend_build_mismatch_reload", new Error("frontend_build_mismatch"), {
        clientBuildId: appBuildInfo.buildHash,
        serverBuildId: config.buildId,
      });
      incrementForcedReloadCount();
      const url = new URL(window.location.href);
      url.searchParams.set("bloom_reload_build", config.buildId);
      url.searchParams.set("bloom_reload_ts", String(Date.now()));
      window.location.replace(url.toString());
    }
  } catch (error) {
    reportClientError("runtime_config_check_failed", error);
  }
}
