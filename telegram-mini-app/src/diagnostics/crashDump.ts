import { appBuildInfo } from "../buildInfo";
import { getStartupTrace } from "./startupTrace";

export const BLOOM_LAST_CRASH_DUMP_KEY = "BLOOM_LAST_CRASH_DUMP";

export interface BloomCrashDump {
  buildHash: string;
  buildDate: string;
  appVersion: string;
  startupSessionId: string;
  timestamp: string;
  reason: string;
  startupTrace: unknown[];
  catalogTrace: unknown[];
  networkTrace: unknown[];
  abortTrace: unknown[];
  errors: unknown[];
  flags: Record<string, unknown>;
}

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try { return window.localStorage; } catch { return null; }
}

const SENSITIVE = /^(authorization|initdata|init_data|telegram_payload|access_token|token|signature|credential|cookie|secret|password)$/i;
function cleanText(s: string): string { return s.replace(/(Authorization\s*[:=]\s*)[^\s,}]+/gi, "$1[redacted]").replace(/([?&#]?(?:initData|init_data|telegram_payload|access_token|token|signature|hash)=)([^&\s]+)/gi, "$1[redacted]").slice(0, 900); }
function sanitizeCrashValue(value: unknown, depth = 0): unknown { if (depth > 4) return "[depth-limit]"; if (value instanceof Error) return { name: value.name, message: cleanText(value.message), stack: cleanText(value.stack ?? "").slice(0, 1200) }; if (typeof value === "string") return cleanText(value); if (typeof value === "number" || typeof value === "boolean" || value === null) return value; if (Array.isArray(value)) return value.slice(0, 80).map((item) => sanitizeCrashValue(item, depth + 1)); if (value && typeof value === "object") return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, SENSITIVE.test(key) ? "[redacted]" : sanitizeCrashValue(item, depth + 1)])); return undefined; }
function currentBuildHash(): string { return appBuildInfo.buildHash || appBuildInfo.buildVersion; }
function startupSessionId(): string { return typeof window === "undefined" ? "server" : window.__BLOOM_STARTUP_SESSION_ID__ ?? "unknown"; }

export function createCrashDump(reason: string, flags: Record<string, unknown> = {}): BloomCrashDump {
  const startupTrace = getStartupTrace();
  return sanitizeCrashValue({
    buildHash: currentBuildHash(),
    buildDate: appBuildInfo.buildTimestamp,
    appVersion: appBuildInfo.buildVersion,
    startupSessionId: startupSessionId(),
    timestamp: new Date().toISOString(),
    reason,
    startupTrace,
    catalogTrace: typeof window === "undefined" ? [] : (window as any).__BLOOM_CATALOG_TRACE__ ?? [],
    networkTrace: typeof window === "undefined" ? [] : (window as any).__BLOOM_NETWORK_TRACE__ ?? [],
    abortTrace: typeof window === "undefined" ? [] : (window as any).__BLOOM_ABORT_TRACE__ ?? [],
    errors: typeof window === "undefined" ? [] : (window as any).__BLOOM_ERROR_TRACE__ ?? [],
    flags: { startupFinished: startupTrace.some((event) => event.step === "bootstrap_done" || event.step === "startup_completed_successfully"), startupFailed: startupTrace.some((event) => event.status === "fail" || event.step.includes("fail")), catalogRequested: startupTrace.some((event) => event.step.includes("catalog") || event.step.includes("Partners")), hasToken: false, ...flags },
  }) as BloomCrashDump;
}

export function saveCrashDump(reason: string, flags: Record<string, unknown> = {}): void {
  const target = storage();
  if (!target) return;
  try { target.setItem(BLOOM_LAST_CRASH_DUMP_KEY, JSON.stringify(createCrashDump(reason, flags))); } catch {}
}

export function clearCrashDump(reason = "manual_clear"): void {
  const target = storage();
  if (!target) return;
  try { target.removeItem(BLOOM_LAST_CRASH_DUMP_KEY); } catch {}
  void reason;
}

export function readCompatibleCrashDump(): BloomCrashDump | null {
  const target = storage();
  if (!target) return null;
  try {
    const raw = target.getItem(BLOOM_LAST_CRASH_DUMP_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BloomCrashDump;
    if (parsed?.buildHash !== currentBuildHash()) {
      target.removeItem(BLOOM_LAST_CRASH_DUMP_KEY);
      return null;
    }
    return parsed;
  } catch {
    target.removeItem(BLOOM_LAST_CRASH_DUMP_KEY);
    return null;
  }
}

export function markStartupCompletedSuccessfully(): void {
  if (typeof window !== "undefined") window.__BLOOM_STARTUP_COMPLETED_SUCCESSFULLY__ = true;
  clearCrashDump("startup_completed_successfully");
}

declare global { interface Window { __BLOOM_STARTUP_COMPLETED_SUCCESSFULLY__?: boolean; __BLOOM_STARTUP_SESSION_ID__?: string; } }
