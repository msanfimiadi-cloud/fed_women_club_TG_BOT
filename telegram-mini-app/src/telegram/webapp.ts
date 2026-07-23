import { lifecycleTrace } from "../diagnostics/lifecycleTrace";
import { traceMark } from "../diagnostics/startupTrace";
type TelegramLaunchUnsafe = {
  user?: { id?: string | number } | Record<string, unknown>;
  start_param?: string;
};

type TelegramWebApp = {
  [key: string]: unknown;
  startParam?: string;
  platform?: string;
  version?: string;
  colorScheme?: 'light' | 'dark' | string;
  viewportHeight?: number;
  viewportStableHeight?: number;
  ready?: () => void;
  expand?: () => void;
  close?: () => void;
  enableClosingConfirmation?: () => void;
  disableClosingConfirmation?: () => void;
  onEvent?: (eventType: 'viewportChanged', eventHandler: () => void) => void;
  offEvent?: (eventType: 'viewportChanged', eventHandler: () => void) => void;
  MainButton?: {
    show?: () => void;
    hide?: () => void;
    setText?: (text: string) => void;
  };
};

export type TelegramRuntimeDiagnostics = {
  hasTelegramObject: boolean;
  hasWebApp: boolean;
  platform: string | null;
  version: string | null;
  colorScheme: string | null;
  launchPayloadLength: number;
  hasLaunchUnsafe: boolean;
  hasLaunchUnsafeUser: boolean;
  hasStartParam: boolean;
  startParamLength: number;
  startParamSourceNames: string[];
  currentLocationHost: string;
  currentUserAgentShort: string;
  initDataHasStartParamKey: boolean;
  locationHasStartParamKey: boolean;
  locationSearchHasStartParamKey: boolean;
  locationHashHasStartParamKey: boolean;
  retrieveLaunchParamsHasStartParam: boolean;
  retrieveLaunchParamsHasInitDataRaw: boolean;
};

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
    __BLOOM_TG_VIEWPORT_PREPARE_COUNT__?: number;
    __BLOOM_TG_VIEWPORT_CLEANUP_COUNT__?: number;
  }
}

export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function getTelegramLaunchPayload(): string {
  const webApp = getTelegramWebApp();
  const key = `init${'Data'}`;
  const value = webApp?.[key];
  return typeof value === 'string' ? value : '';
}

const INIT_DATA_RETRY_ATTEMPTS = 3;
const INIT_DATA_RETRY_DELAY_MS = 350;

function waitForInitDataRetry(delayMs: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, delayMs));
}

export async function getTelegramLaunchPayloadWithRetry(
  attempts = INIT_DATA_RETRY_ATTEMPTS,
  delayMs = INIT_DATA_RETRY_DELAY_MS,
): Promise<string> {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const payload = getTelegramLaunchPayload();

    if (payload || attempt >= attempts) {
      return payload;
    }

    await waitForInitDataRetry(delayMs);
  }

  return '';
}

function getUrlSearchParamFromText(text: string): string {
  const normalized = text.startsWith('?') || text.startsWith('#') ? text.slice(1) : text;
  const params = new URLSearchParams(normalized);
  const direct =
    params.get('tgWebAppStartParam') ||
    params.get('startapp') ||
    params.get('start_param') ||
    params.get('referral_code') ||
    '';

  if (direct.trim()) {
    return direct.trim();
  }

  const nestedInitData = params.get('tgWebAppData') || params.get('initData') || params.get('init_data') || '';
  if (nestedInitData) {
    const nested = new URLSearchParams(nestedInitData);
    return (nested.get('start_param') || nested.get('tgWebAppStartParam') || nested.get('startapp') || '').trim();
  }

  return '';
}

function hasStartParamKeyInUrlSearchText(text: string): boolean {
  const normalized = text.startsWith('?') || text.startsWith('#') ? text.slice(1) : text;
  const params = new URLSearchParams(normalized);
  if (params.has('tgWebAppStartParam') || params.has('startapp') || params.has('start_param')) {
    return true;
  }

  const nestedInitData = params.get('tgWebAppData') || params.get('initData') || params.get('init_data') || '';
  if (!nestedInitData) {
    return false;
  }

  const nested = new URLSearchParams(nestedInitData);
  return nested.has('start_param') || nested.has('tgWebAppStartParam') || nested.has('startapp');
}

function getRetrieveLaunchParamsDiagnostics(): { hasStartParam: boolean; hasInitDataRaw: boolean } {
  const webApp = getTelegramWebApp();
  const launchPayload = getTelegramLaunchPayload();
  const fromHashOrSearch = getUrlSearchParamFromText(window.location.hash || window.location.search);

  return {
    hasStartParam: Boolean(webApp?.startParam) || Boolean(fromHashOrSearch),
    hasInitDataRaw: launchPayload.length > 0 || new URLSearchParams((window.location.hash || '').replace(/^#/, '')).has('tgWebAppData'),
  };
}

function getTelegramStartParamFromLaunchPayload(): string {
  return getUrlSearchParamFromText(getTelegramLaunchPayload());
}

function getTelegramStartParamFromUrl(): string {
  const fromSearch = getUrlSearchParamFromText(window.location.search);
  if (fromSearch) {
    return fromSearch;
  }

  const hash = window.location.hash || '';
  const queryInHash = hash.includes('?') ? hash.slice(hash.indexOf('?')) : hash;
  return getUrlSearchParamFromText(queryInHash);
}

function getTelegramStartParamSourceNames(): string[] {
  const webApp = getTelegramWebApp();
  const unsafeKey = `init${'Data'}Unsafe`;
  const unsafe = webApp?.[unsafeKey] as TelegramLaunchUnsafe | undefined;
  const sources: string[] = [];

  if (getTelegramStartParamFromLaunchPayload()) {
    sources.push('initData.start_param');
  }
  if (typeof unsafe?.start_param === 'string' && unsafe.start_param.trim()) {
    sources.push('initDataUnsafe.start_param');
  }
  if (typeof webApp?.startParam === 'string' && webApp.startParam.trim()) {
    sources.push('WebApp.startParam');
  }
  if (getUrlSearchParamFromText(window.location.search)) {
    sources.push('location.search');
  }
  if (getUrlSearchParamFromText(window.location.hash || '')) {
    sources.push('location.hash');
  } else if (window.location.hash.includes('?') && getUrlSearchParamFromText(window.location.hash.slice(window.location.hash.indexOf('?')))) {
    sources.push('location.hash.query');
  }

  return sources;
}

export function getTelegramStartParam(): string {
  const webApp = getTelegramWebApp();
  const unsafeKey = `init${'Data'}Unsafe`;
  const unsafe = webApp?.[unsafeKey] as TelegramLaunchUnsafe | undefined;
  const value = getTelegramStartParamFromLaunchPayload() || unsafe?.start_param || webApp?.startParam || getTelegramStartParamFromUrl();
  return typeof value === 'string' ? value.trim() : '';
}

export function getReferralCodeFromStartParam(startParam = getTelegramStartParam()): string | null {
  const trimmed = startParam.trim();
  if (!trimmed) {
    return null;
  }
  const direct = trimmed.match(/^(?:ref|referral|invite)[_-]?([A-Za-z0-9_-]{4,64})$/i);
  if (direct) {
    return direct[1];
  }
  const params = new URLSearchParams(trimmed);
  const candidate = params.get('ref') || params.get('referral') || params.get('referral_code');
  if (candidate && /^[A-Za-z0-9_-]{4,64}$/.test(candidate)) {
    return candidate;
  }

  return /^[A-Za-z0-9_-]{4,64}$/.test(trimmed) ? trimmed : null;
}

export function getTelegramUnsafeUserId(): string | number | null {
  const webApp = getTelegramWebApp();
  const unsafeKey = `init${'Data'}Unsafe`;
  const unsafe = webApp?.[unsafeKey] as TelegramLaunchUnsafe | undefined;
  const userId = unsafe?.user && typeof unsafe.user === 'object' ? unsafe.user.id : null;

  return typeof userId === 'string' || typeof userId === 'number' ? userId : null;
}

export function getTelegramRuntimeDiagnostics(): TelegramRuntimeDiagnostics {
  const telegram = window.Telegram;
  const webApp = telegram?.WebApp;
  const launchPayload = getTelegramLaunchPayload();
  const unsafeKey = `init${'Data'}Unsafe`;
  const unsafe = webApp?.[unsafeKey] as TelegramLaunchUnsafe | undefined;
  const startParam = getTelegramStartParam();
  const retrieveLaunchParams = getRetrieveLaunchParamsDiagnostics();
  const locationSearchHasStartParamKey = hasStartParamKeyInUrlSearchText(window.location.search);
  const locationHashHasStartParamKey = hasStartParamKeyInUrlSearchText(window.location.hash || '');

  return {
    hasTelegramObject: Boolean(telegram),
    hasWebApp: Boolean(webApp),
    platform: webApp?.platform ?? null,
    version: webApp?.version ?? null,
    colorScheme: webApp?.colorScheme ?? null,
    launchPayloadLength: launchPayload.length,
    hasLaunchUnsafe: Boolean(unsafe),
    hasLaunchUnsafeUser: Boolean(unsafe?.user),
    hasStartParam: startParam.length > 0,
    startParamLength: startParam.length,
    startParamSourceNames: getTelegramStartParamSourceNames(),
    currentLocationHost: window.location.host,
    currentUserAgentShort: navigator.userAgent.slice(0, 80),
    initDataHasStartParamKey: new URLSearchParams(launchPayload).has('start_param'),
    locationHasStartParamKey: locationSearchHasStartParamKey || locationHashHasStartParamKey || hasStartParamKeyInUrlSearchText(window.location.href),
    locationSearchHasStartParamKey,
    locationHashHasStartParamKey,
    retrieveLaunchParamsHasStartParam: retrieveLaunchParams.hasStartParam,
    retrieveLaunchParamsHasInitDataRaw: retrieveLaunchParams.hasInitDataRaw,
  };
}

let cleanupTelegramViewportListeners: (() => void) | null = null;

export function prepareTelegramViewport(): void {
  const webApp = getTelegramWebApp();
  window.__BLOOM_TG_VIEWPORT_PREPARE_COUNT__ =
    (window.__BLOOM_TG_VIEWPORT_PREPARE_COUNT__ ?? 0) + 1;

  cleanupTelegramViewportListeners?.();
  cleanupTelegramViewportListeners = null;

  if (!webApp) {
    return;
  }

  webApp.ready?.();
  traceMark("ready_called");
  webApp.expand?.();

  const setViewportHeight = () => {
    const viewport = webApp.viewportStableHeight || webApp.viewportHeight || window.visualViewport?.height || window.innerHeight;
    lifecycleTrace("telegram_viewport_changed", {
      viewportHeight: webApp.viewportHeight,
      viewportStableHeight: webApp.viewportStableHeight,
      visualViewportHeight: window.visualViewport?.height,
      innerHeight: window.innerHeight,
    });
    if (viewport) {
      document.documentElement.style.setProperty('--tg-viewport-height', `${Math.round(viewport)}px`);
    }
  };

  setViewportHeight();
  webApp.onEvent?.('viewportChanged', setViewportHeight);
  window.visualViewport?.addEventListener('resize', setViewportHeight);
  window.addEventListener('resize', setViewportHeight);

  cleanupTelegramViewportListeners = () => {
    window.__BLOOM_TG_VIEWPORT_CLEANUP_COUNT__ =
      (window.__BLOOM_TG_VIEWPORT_CLEANUP_COUNT__ ?? 0) + 1;
    webApp.offEvent?.('viewportChanged', setViewportHeight);
    window.visualViewport?.removeEventListener('resize', setViewportHeight);
    window.removeEventListener('resize', setViewportHeight);
  };
}

export function isTelegramRuntime(): boolean {
  return Boolean(getTelegramWebApp());
}
