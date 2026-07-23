import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  activateTrialSubscription,
  createPaymentRequest,
  getCities,
  getLinkingStatus,
  getReferralSummary,
  clearStoredAuthToken,
  getPartnerOffersPath,
  getPartnerOffers,
  getPartners,
  getProfile,
  getStoredAuthToken,
  getSavings,
  getSubscription,
  getVerifications,
  isApiError,
  isCatalogLoadError,
  isTimeoutError,
  loginWithTelegram,
  resetTelegramLoginInFlight,
  TG_LOCAL_CATALOG_ENABLED,
  updateProfile,
  verifyPartnerOffer,
} from "./api/client";
import type { CatalogErrorDiagnostic } from "./api/client";
import type {
  ApiId,
  City,
  ClientProfile,
  ClientProfilePatch,
  Offer,
  Partner,
  PaymentRequest,
  LinkingStatus,
  ReferralSummary,
  SavingsSummary,
  Subscription,
  Verification,
} from "./api/types";
import { AccountLinkingOnboarding } from "./components/AccountLinkingOnboarding";
import { AppShell } from "./components/AppShell";
import { ErrorState } from "./components/ErrorState";
import { LoadingState } from "./components/LoadingState";
import { DiagnosticOverlay } from "./components/DiagnosticOverlay";
import { CatalogPage } from "./pages/CatalogPage";
import { HomePage } from "./pages/HomePage";
import { PartnerPage } from "./pages/PartnerPage";
import { PrivilegesPage } from "./pages/PrivilegesPage";
import { ProfilePage } from "./pages/ProfilePage";
import { SavingsPage } from "./pages/SavingsPage";
import { SubscriptionPage } from "./pages/SubscriptionPage";
import { ContentProvider } from "./content/ContentContext";
import {
  createDiagnostic,
  createUnknownStateDiagnostic,
  type AppDiagnostic,
  type AppStage,
} from "./diagnostics";
import {
  lifecycleTrace,
  markReactMounted,
  setLifecyclePageId,
} from "./diagnostics/lifecycleTrace";
import {
  getStartupTrace,
  traceFail,
  traceMark,
  traceOk,
  traceStart,
  traceStartup,
} from "./diagnostics/startupTrace";
import { catalogTrace, enableBloomDebug, isBloomDebugEnabled } from "./diagnostics/productionDebug";
import { clearCrashDump, markStartupCompletedSuccessfully, readCompatibleCrashDump, saveCrashDump, type BloomCrashDump } from "./diagnostics/crashDump";
import { formatDate } from "./utils/format";
import { getSubscriptionEnd } from "./utils/subscription";
import { resolveNumericPartnerId, sortOffersForPartner, sortPartnersForCatalog } from "./utils/partnerDisplay";
import {
  getReferralCodeFromStartParam,
  getTelegramStartParam,
  getTelegramRuntimeDiagnostics,
  getTelegramLaunchPayloadWithRetry,
  isTelegramRuntime,
  getTelegramWebApp,
  prepareTelegramViewport,
} from "./telegram/webapp";
import { clearStaleAppState } from "./stateRecovery";
import { removeEntryFallbackOverlay } from "./main";

export type PageId =
  | "home"
  | "catalog"
  | "partner"
  | "privileges"
  | "savings"
  | "profile"
  | "subscription";
type AsyncStatus =
  | "idle"
  | "loading"
  | "success"
  | "empty"
  | "error"
  | "timeout";
type BootstrapReason = "initial" | "retry" | "manual" | "resume";

const BOOTSTRAP_HARD_TIMEOUT_MS = 9_000;
const CATALOG_CLOSED_DURING_LOAD_KEY = "bloom_catalog_closed_during_load";
const CATALOG_RECOVERY_MESSAGE = "Загрузка клуба была прервана. Нажмите, чтобы попробовать снова.";

const RETRYABLE_LOAD_ERROR_MESSAGE =
  "Не удалось загрузить данные. Проверьте соединение и повторите попытку.";


function hasCatalogRecoveryFlag(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.sessionStorage.getItem(CATALOG_CLOSED_DURING_LOAD_KEY) === "true" ||
      window.localStorage.getItem(CATALOG_CLOSED_DURING_LOAD_KEY) === "true";
  } catch {
    return false;
  }
}

function setCatalogRecoveryFlag(): void {
  if (typeof window === "undefined") return;
  try { window.sessionStorage.setItem(CATALOG_CLOSED_DURING_LOAD_KEY, "true"); } catch { /* ignore */ }
  try { window.localStorage.setItem(CATALOG_CLOSED_DURING_LOAD_KEY, "true"); } catch { /* ignore */ }
  console.info("catalog_closed_during_load_flag_set", { key: CATALOG_CLOSED_DURING_LOAD_KEY });
  traceStartup("catalog_closed_during_load_flag_set", { key: CATALOG_CLOSED_DURING_LOAD_KEY });
}

function clearCatalogRecoveryFlag(): void {
  if (typeof window === "undefined") return;
  try { window.sessionStorage.removeItem(CATALOG_CLOSED_DURING_LOAD_KEY); } catch { /* ignore */ }
  try { window.localStorage.removeItem(CATALOG_CLOSED_DURING_LOAD_KEY); } catch { /* ignore */ }
}

function clearStartupRecoveryStorage(): void {
  const keyPattern = /(bloom|auth|bootstrap|build|token|crash|startup|telegram_login)/i;
  try {
    [window.sessionStorage, window.localStorage].forEach((storage) => {
      Object.keys(storage).forEach((key) => {
        if (keyPattern.test(key)) storage.removeItem(key);
      });
    });
  } catch {
    // Recovery must work even when storage is blocked.
  }
}

function restartAppAfterStartupFailure(): void {
  clearStartupRecoveryStorage();
  const url = new URL(window.location.href);
  url.searchParams.set("bloom_recovery", "app_watchdog");
  url.searchParams.set("bloom_recovery_ts", String(Date.now()));
  window.location.replace(url.toString());
}

function StartupRecoveryScreen({ message }: { message: string | null }): React.ReactElement {
  return (
    <main className="startup-recovery-screen" role="alert">
      <h1>Не удалось завершить запуск</h1>
      <p>{message ?? "Приложение не стало интерактивным. Можно безопасно перезапустить Mini App."}</p>
      <button className="button button--primary" type="button" onClick={restartAppAfterStartupFailure}>
        Перезапустить приложение
      </button>
    </main>
  );
}

function isStartupDebugUiEnabled(): boolean {
  if (import.meta.env.DEV) {
    return true;
  }

  if (typeof window === "undefined") {
    return false;
  }

  try {
    return isBloomDebugEnabled() || new URLSearchParams(window.location.search).get("debug") === "1";
  } catch {
    return false;
  }
}
export interface PartnerOffersDiagnostic {
  numericPartnerId?: number;
  partnerIdSource?: "partner.id";
  offersUrlPath?: string;
  source?: "tg_local_catalog" | "web_legacy_catalog";
  httpStatus?: number;
  backendDetail?: string;
  partnerIdMissingOrInvalid?: boolean;
}

declare global {
  interface Window {
    __BLOOM_TG_CATALOG_BOOTSTRAP__?: {
      items?: Partner[];
      consumed?: boolean;
    };
    __BLOOM_LAST_CATALOG_ERROR__?: unknown;
  }
}

interface AppData {
  profile: ClientProfile | null;
  subscription: Subscription | null;
  partners: Partner[];
  verifications: Verification[];
  savings: SavingsSummary | null;
  cities: City[];
  linkingStatus: LinkingStatus | null;
  referralSummary: ReferralSummary | null;
}

const emptyData: AppData = {
  profile: null,
  subscription: null,
  partners: [],
  verifications: [],
  savings: null,
  cities: [],
  linkingStatus: null,
  referralSummary: null,
};

function asObject<T extends object>(value: T | null | undefined): T | null {
  return value && typeof value === "object" ? value : null;
}

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function normalizeAppData(data: Partial<AppData>): AppData {
  return {
    profile: asObject(data.profile),
    subscription: asObject(data.subscription),
    partners: sortPartnersForCatalog(asArray(data.partners)),
    verifications: asArray(data.verifications),
    savings: asObject(data.savings),
    cities: asArray(data.cities),
    linkingStatus: asObject(data.linkingStatus),
    referralSummary: asObject(data.referralSummary),
  };
}

function consumeCatalogBootstrap(): Partner[] | null {
  if (typeof window === "undefined") {
    traceMark("catalog_bootstrap_missing", { reason: "no_window" });
    return null;
  }

  const bootstrap = window.__BLOOM_TG_CATALOG_BOOTSTRAP__;
  if (
    !bootstrap ||
    bootstrap.consumed ||
    !Array.isArray(bootstrap.items) ||
    bootstrap.items.length === 0
  ) {
    traceMark("catalog_bootstrap_missing", {
      consumed: bootstrap?.consumed,
      hasItems: Array.isArray(bootstrap?.items),
      itemsCount: bootstrap?.items?.length ?? 0,
    });
    return null;
  }

  traceMark("catalog_bootstrap_available", {
    itemsCount: bootstrap.items.length,
  });
  bootstrap.consumed = true;
  traceMark("catalog_bootstrap_consumed", {
    itemsCount: bootstrap.items.length,
  });
  const items = bootstrap.items;
  window.__BLOOM_TG_CATALOG_BOOTSTRAP__ = { items: [], consumed: true };
  return items;
}

function normalizeOffersResponse(response: unknown): Offer[] {
  if (Array.isArray(response)) {
    return sortOffersForPartner(response as Offer[]);
  }

  if (!response || typeof response !== "object") {
    return [];
  }

  const body = response as Record<string, unknown>;
  const candidates = [body.items, body.offers, body.data, body.results];
  const offers = candidates.find(Array.isArray);
  return sortOffersForPartner(Array.isArray(offers) ? (offers as Offer[]) : []);
}

function extractTrialPayload(response: unknown): {
  subscription: Subscription | null;
  profile: ClientProfile | null;
} {
  if (!response || typeof response !== "object") {
    return { subscription: null, profile: null };
  }

  const body = response as Record<string, unknown>;
  const subscription = asObject((body.subscription ?? body) as Subscription);
  const profile = asObject((body.profile ?? body.client) as ClientProfile);

  return { subscription, profile };
}

function safeDiagnosticText(value: unknown): string | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }

  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text
    .replace(
      /(credential|signature|token)(["'\s:=]+)[^,"'\s}]+/gi,
      "$1$2[hidden]",
    )
    .slice(0, 500);
}

function logBootstrapDiagnostic(
  event: string,
  details: Record<string, unknown>,
): void {
  console.info(event, {
    ...details,
    errorMessageShort:
      "errorMessageShort" in details
        ? safeDiagnosticText(details.errorMessageShort)
        : undefined,
  });
}

function getLinkingDismissKey(profile: ClientProfile | null): string | null {
  const identity = profile?.telegram_user_id ?? profile?.id;
  return identity === undefined || identity === null
    ? null
    : `bloom_club_tma_linking_dismissed_${identity}`;
}

function isProfileLinked(status: LinkingStatus | null | undefined): boolean {
  if (!status || typeof status !== "object") {
    return false;
  }

  if (
    status.linked === true ||
    status.is_linked === true ||
    status.has_linked_account === true
  ) {
    return true;
  }

  if (status.needs_linking === true) {
    return false;
  }

  const statusText = String(status.status ?? "").toLowerCase();
  return (
    ["linked", "connected", "merged"].includes(statusText) ||
    Boolean(status.linked_profile_id)
  );
}

function shouldShowLinkingOnboarding(
  isTelegram: boolean,
  profile: ClientProfile | null,
  status: LinkingStatus | null,
  dismissedKey: string | null,
): boolean {
  if (
    !isTelegram ||
    !profile ||
    !status ||
    isProfileLinked(status) ||
    !dismissedKey
  ) {
    return false;
  }

  return window.localStorage.getItem(dismissedKey) !== "1";
}

function getStartupPage(): PageId {
  if (typeof window === "undefined") {
    return "home";
  }

  return window.location.hash === "#catalog" ? "catalog" : "home";
}

function isUnsafeStartupScreen(page: PageId): boolean {
  return page === "partner";
}

function isKnownPage(page: string): page is PageId {
  return [
    "home",
    "catalog",
    "partner",
    "privileges",
    "savings",
    "profile",
    "subscription",
  ].includes(page);
}

export default function App() {
  traceStartup("app_component_rendered");
  lifecycleTrace("app_render", {
    page:
      typeof window === "undefined"
        ? "unknown"
        : window.__BLOOM_PAGE_LIFECYCLE_PAGE_ID__,
  });
  const [page, setPage] = useState<PageId>(() => getStartupPage());
  const [data, setData] = useState<AppData>(emptyData);
  const [selectedPartner, setSelectedPartner] = useState<Partner | null>(null);
  const [partnerOffers, setPartnerOffers] = useState<Offer[]>([]);
  const [partnerOffersStatus, setPartnerOffersStatus] =
    useState<AsyncStatus>("idle");
  const [partnerOffersError, setPartnerOffersError] = useState("");
  const [partnerOffersDiagnostic, setPartnerOffersDiagnostic] =
    useState<PartnerOffersDiagnostic | null>(null);
  const [paymentRequest, setPaymentRequest] = useState<PaymentRequest | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<AppDiagnostic | null>(null);
  const [isCreatingPayment, setIsCreatingPayment] = useState(false);
  const [trialMessage, setTrialMessage] = useState<string | null>(null);
  const [paymentMessage, setPaymentMessage] = useState<string | null>(null);
  const [isPartnersLoading, setIsPartnersLoading] = useState(false);
  const [partnersError, setPartnersError] = useState("");
  const [partnersErrorTitle, setPartnersErrorTitle] = useState(
    "Не удалось загрузить каталог",
  );
  const [partnersErrorDetails, setPartnersErrorDetails] = useState<
    | Pick<
        CatalogErrorDiagnostic,
        | "source"
        | "requestUrl"
        | "requestUrlPath"
        | "requestOrigin"
        | "httpStatus"
        | "requestId"
        | "elapsedMs"
        | "attempt"
        | "fetchPhase"
        | "errorName"
        | "isAbortError"
      >
    | undefined
  >(undefined);
  const [catalogErrorCreatedAt, setCatalogErrorCreatedAt] = useState<
    string | undefined
  >(undefined);
  const [catalogLoadStartedAt, setCatalogLoadStartedAt] = useState<
    string | undefined
  >(undefined);
  const [catalogLoadRequestId, setCatalogLoadRequestId] = useState<
    number | undefined
  >(undefined);
  // Catalog diagnostic UI intentionally allows only safe request fields plus local freshness markers.
  const [hasPartnersLoaded, setHasPartnersLoaded] = useState(false);
  const [catalogRecoveryPending, setCatalogRecoveryPending] = useState(() => hasCatalogRecoveryFlag());
  const [shouldShowLinking, setShouldShowLinking] = useState(false);
  const [isTelegramApp, setIsTelegramApp] = useState(false);
  const isStartupDebugUiEnabledValue = useMemo(isStartupDebugUiEnabled, []);
  const [showStartupDiagnostics, setShowStartupDiagnostics] = useState(false);
  const [diagnosticOverlayReason, setDiagnosticOverlayReason] = useState<
    string | null
  >(null);
  const [previousCrashDump, setPreviousCrashDump] = useState<BloomCrashDump | null>(() => readCompatibleCrashDump());
  const debugTapCountRef = useRef(0);
  const debugTapTimerRef = useRef<number | undefined>(undefined);
  const [watchdogMessage, setWatchdogMessage] = useState<string | null>(null);
  const [showStartupRecovery, setShowStartupRecovery] = useState(false);
  const [isBootstrapDone, setIsBootstrapDone] = useState(false);
  const [hasRenderedPageContent, setHasRenderedPageContent] = useState(false);
  const partnersPromiseRef = useRef<Promise<void> | null>(null);
  const catalogAbortControllerRef = useRef<AbortController | null>(null);
  const catalogLoadSequenceRef = useRef(0);
  const pageRef = useRef<PageId>(page);
  const clearCatalogDiagnostic = setPartnersErrorDetails;
  const bootstrapPromiseRef = useRef<Promise<void> | null>(null);
  const bootstrapSequenceRef = useRef(0);
  const appActiveRef = useRef(true);
  const catalogLoadingRef = useRef(false);
  const mountedRef = useRef(false);
  const diagnosticSessionIdRef = useRef(
    `bootstrap-deadlock-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
  );
  const logBootstrapDeadlockDiagnostic = useCallback(
    (event: string, details: Record<string, unknown> = {}) => {
      console.info("bootstrap_deadlock_diagnostic", {
        event,
        sessionId: diagnosticSessionIdRef.current,
        visibilityState: document.visibilityState,
        performanceNow: performance.now(),
        bootstrapSequence: bootstrapSequenceRef.current,
        bootstrapPromiseExists: Boolean(bootstrapPromiseRef.current),
        mountedRef: mountedRef.current,
        appActive: appActiveRef.current,
        ...details,
      });
    },
    [],
  );

  useEffect(() => {
    lifecycleTrace("app_effect_page_start", {
      from: pageRef.current,
      to: page,
    });
    pageRef.current = page;
    setLifecyclePageId(page);
    lifecycleTrace("page_transition", { page });
    return () => lifecycleTrace("app_effect_page_cleanup", { page });
  }, [page]);

  const resetCatalogStateForForceReload = useCallback(() => {
    catalogAbortControllerRef.current?.abort("catalog_force_reload");
    catalogAbortControllerRef.current = null;
    partnersPromiseRef.current = null;
    setPartnersError("");
    clearCatalogDiagnostic(undefined);
    setCatalogErrorCreatedAt(undefined);
    setCatalogLoadStartedAt(undefined);
    setCatalogLoadRequestId(undefined);
    setHasPartnersLoaded(false);
    catalogLoadingRef.current = false;
    setIsPartnersLoading(false);
  }, [logBootstrapDeadlockDiagnostic]);


  const abortInFlightCatalogLoad = useCallback((reason: string) => {
    const hadCatalogPromise = Boolean(partnersPromiseRef.current);
    catalogAbortControllerRef.current?.abort(reason);
    catalogAbortControllerRef.current = null;
    partnersPromiseRef.current = null;
    catalogLoadingRef.current = false;
    setIsPartnersLoading(false);
    console.info("catalog_load_aborted_for_lifecycle", {
      reason,
      hadCatalogPromise,
      page: pageRef.current,
    });
  }, []);

  useEffect(() => {
    const webApp = getTelegramWebApp();
    const shouldConfirmClosing = isLoading || isPartnersLoading;
    try {
      if (shouldConfirmClosing) {
        webApp?.enableClosingConfirmation?.();
        console.info("closing_confirmation_enabled", { isLoading, isPartnersLoading });
        traceStartup("closing_confirmation_enabled", { isLoading, isPartnersLoading });
      } else {
        webApp?.disableClosingConfirmation?.();
        console.info("closing_confirmation_disabled", { isLoading, isPartnersLoading });
        traceStartup("closing_confirmation_disabled", { isLoading, isPartnersLoading });
      }
    } catch (caughtError) {
      traceStartup("closing_confirmation_error", { error: caughtError });
    }
    return () => {
      try { webApp?.disableClosingConfirmation?.(); } catch { /* ignore */ }
    };
  }, [isLoading, isPartnersLoading]);

  useEffect(() => {
    window.__BLOOM_OPEN_DIAGNOSTICS__ = (reason = "external_open") => {
      enableBloomDebug();
      setDiagnosticOverlayReason(reason);
      setShowStartupDiagnostics(true);
    };
    return () => { window.__BLOOM_OPEN_DIAGNOSTICS__ = undefined; };
  }, []);

  useEffect(() => {
    console.info("app_component_mount_start");
    logBootstrapDeadlockDiagnostic("react_mount");
    markReactMounted(true);
    lifecycleTrace("app_mount", { page });
    traceStartup("app_component_mounted", { page });
    traceMark("ui_mounted", { page });
    traceMark("app_component_mount");
    traceMark("app_initial_state", {
      page,
      isLoading,
      hasError: Boolean(error),
    });
    mountedRef.current = true;
    removeEntryFallbackOverlay();

    return () => {
      lifecycleTrace("app_unmount", { page: pageRef.current });
      logBootstrapDeadlockDiagnostic("react_unmount_before_mountedRef_false", {
        page: pageRef.current,
      });
      markReactMounted(false);
      mountedRef.current = false;
      logBootstrapDeadlockDiagnostic("react_unmount_after_mountedRef_false", {
        page: pageRef.current,
      });
    };
  }, [logBootstrapDeadlockDiagnostic]);

  useEffect(() => {
    lifecycleTrace("app_effect_watchdogs_start", { page: pageRef.current });
    const reactMountTimer = window.setTimeout(() => {
      if (!mountedRef.current) {
        lifecycleTrace("react_mount_timeout", { timeoutMs: 5000 });
        if (isStartupDebugUiEnabledValue) {
          setDiagnosticOverlayReason("React не смонтировался за 5 секунд.");
        }
      }
    }, 5000);

    const bootstrapLongTimer = window.setTimeout(() => {
      if (!isBootstrapDone) {
        lifecycleTrace("bootstrap_timeout", {
          timeoutMs: 8000,
          page: pageRef.current,
        });
        if (isStartupDebugUiEnabledValue) {
          setDiagnosticOverlayReason("Bootstrap не завершился за 8 секунд.");
        }
      }
    }, 8000);

    const rootEmptyTimer = window.setTimeout(() => {
      const root = document.getElementById("root");
      if (
        hasRenderedPageContent &&
        root &&
        root.textContent?.trim().length === 0
      ) {
        lifecycleTrace("root_visually_empty_timeout", {
          timeoutMs: 8000,
          page: pageRef.current,
        });
        if (isStartupDebugUiEnabledValue) {
          setDiagnosticOverlayReason(
            "Страница отрисована, но root визуально пустой через 8 секунд.",
          );
        }
      }
    }, 8000);

    const openOnWindowError = () => {
      if (isStartupDebugUiEnabledValue) {
        setDiagnosticOverlayReason("Сработал window.error.");
      }
    };
    const openOnUnhandledRejection = () => {
      if (isStartupDebugUiEnabledValue) {
        setDiagnosticOverlayReason("Сработал unhandledrejection.");
      }
    };
    window.addEventListener("error", openOnWindowError);
    window.addEventListener("unhandledrejection", openOnUnhandledRejection);

    const bootstrapTimer = window.setTimeout(() => {
      if (!isBootstrapDone && !error) {
        traceMark("startup_watchdog_5s", { page: pageRef.current });
        saveCrashDump("startup_watchdog_5s", { startupTimedOut: true, page: pageRef.current });
        console.warn(
          "Bloom startup watchdog: bootstrap is not done after 5 seconds",
          getStartupTrace().slice(-30),
        );
        setWatchdogMessage("Bootstrap не завершён через 5 секунд.");
      }
    }, 5000);

    const renderTimer = window.setTimeout(() => {
      if (!hasRenderedPageContent) {
        traceMark("startup_watchdog_8s", { page: pageRef.current });
        saveCrashDump("react_app_ready_timeout", { reactAppReady: false, page: pageRef.current });
        if (isStartupDebugUiEnabledValue) {
          setShowStartupDiagnostics(true);
          setDiagnosticOverlayReason(
            "Контент страницы не отрисован через 8 секунд.",
          );
          setWatchdogMessage("Контент страницы не отрисован через 8 секунд.");
        } else {
          setWatchdogMessage("Запуск не завершился за 8 секунд.");
        }
        setShowStartupRecovery(true);
        traceMark("startup_recovery_screen_requested", { page: pageRef.current });
      }
    }, 8000);

    return () => {
      lifecycleTrace("app_effect_watchdogs_cleanup", { page: pageRef.current });
      window.clearTimeout(reactMountTimer);
      window.clearTimeout(bootstrapLongTimer);
      window.clearTimeout(rootEmptyTimer);
      window.clearTimeout(bootstrapTimer);
      window.clearTimeout(renderTimer);
      window.removeEventListener("error", openOnWindowError);
      window.removeEventListener(
        "unhandledrejection",
        openOnUnhandledRejection,
      );
    };
  }, [error, hasRenderedPageContent, isBootstrapDone, isStartupDebugUiEnabledValue]);

  const resetPartnerFlowState = useCallback((nextPage: PageId = "catalog") => {
    setSelectedPartner(null);
    setPartnerOffers([]);
    setPartnerOffersStatus("idle");
    setPartnerOffersError("");
    setPartnerOffersDiagnostic(null);
    setPage(isUnsafeStartupScreen(nextPage) ? "catalog" : nextPage);
  }, []);

  const loadAppData = useCallback(
    (reason: BootstrapReason = "initial", forceNew = false) => {
      if (forceNew) {
        if (bootstrapPromiseRef.current) {
          logBootstrapDeadlockDiagnostic("bootstrapPromiseRef_cleared", {
            reason: "forceNew",
          });
        }
        bootstrapPromiseRef.current = null;
        resetTelegramLoginInFlight();
      } else if (bootstrapPromiseRef.current) {
        return bootstrapPromiseRef.current;
      }

      const sequenceId = bootstrapSequenceRef.current + 1;
      bootstrapSequenceRef.current = sequenceId;
      logBootstrapDeadlockDiagnostic("bootstrapSequenceRef_updated", {
        sequenceId,
        reason,
        forceNew,
      });
      const isActive = () =>
        mountedRef.current && appActiveRef.current && bootstrapSequenceRef.current === sequenceId;

      if (isActive()) {
        setIsLoading(true);
        setError(null);
      }

      let bootstrapPromise: Promise<void> | undefined;
      bootstrapPromise = (async () => {
        let stage: AppStage = "telegram_runtime_check";
        const startedAt = performance.now();

        lifecycleTrace("bootstrap_start", { reason, forceNew, sequenceId });
        traceMark("auth_started", { reason, sequenceId });
        traceStartup("loadAppData_called", { reason, forceNew, sequenceId });
        traceStart("loadAppData_started", { reason, forceNew, sequenceId });
        logBootstrapDiagnostic("app_bootstrap_start", {
          reason,
          forceNew,
          sequenceId,
        });

        const hardTimeoutId = window.setTimeout(() => {
          if (bootstrapPromiseRef.current === bootstrapPromise) {
            bootstrapPromiseRef.current = null;
            bootstrapSequenceRef.current += 1;
            resetTelegramLoginInFlight();
            setIsLoading(false);
            setWatchdogMessage("Bootstrap не завершился за 9 секунд. Повторите запуск приложения.");
            setShowStartupRecovery(true);
            traceStartup("bootstrap_hard_timeout", { sequenceId, timeoutMs: BOOTSTRAP_HARD_TIMEOUT_MS });
            logBootstrapDeadlockDiagnostic("bootstrap_hard_timeout", {
              sequenceId,
              timeoutMs: BOOTSTRAP_HARD_TIMEOUT_MS,
            });
          }
        }, BOOTSTRAP_HARD_TIMEOUT_MS);

        try {
          lifecycleTrace("telegram_ready_start");
          lifecycleTrace("telegram_expand_start");
          traceStart("telegram_prepare_start");
          try {
            prepareTelegramViewport();
            lifecycleTrace("telegram_ready_ok");
            lifecycleTrace("telegram_expand_ok");
            traceOk("telegram_prepare_ok");
          } catch (prepareError) {
            lifecycleTrace("telegram_ready_fail", prepareError);
            lifecycleTrace("telegram_expand_fail", prepareError);
            traceFail("telegram_prepare_fail", prepareError);
            throw prepareError;
          }
          traceStart("telegram_runtime_check_start");
          const isTelegram = isTelegramRuntime();
          traceOk("telegram_runtime_check_ok", { isTelegram });
          if (isActive()) {
            setIsTelegramApp(isTelegram);
          }

          const requestProfileAndSubscription = async () => {
            stage = "profile_request";
            traceStartup("loadAppData_profile_started");
            traceStartup("loadAppData_subscription_started");
            traceStart("stored_token_profile_start");
            traceStart("stored_token_subscription_start");
            const [nextProfile, nextSubscription] = await Promise.all([
              getProfile(),
              getSubscription(),
            ]);
            traceStartup("loadAppData_profile_success");
            traceOk("stored_token_profile_ok", {
              hasProfile: Boolean(nextProfile),
            });
            traceStartup("loadAppData_subscription_success");
            traceOk("stored_token_subscription_ok", {
              hasSubscription: Boolean(nextSubscription),
            });
            stage = "subscription_request";
            return { profile: nextProfile, subscription: nextSubscription };
          };

          const loginWithTelegramPayload = async () => {
            stage = "init_data_read";
            traceStart("launch_payload_read_start");
            const telegramLaunchPayload =
              await getTelegramLaunchPayloadWithRetry();
            traceOk("launch_payload_read_ok", {
              hasPayload: Boolean(telegramLaunchPayload),
            });

            if (!telegramLaunchPayload && isTelegram) {
              throw new Error(
                "Telegram WebApp доступен, но Telegram не передал launch payload. Попробуйте открыть Mini App с телефона или через полноценную кнопку приложения у бота.",
              );
            }

            if (!telegramLaunchPayload && !isTelegram && !import.meta.env.DEV) {
              throw new Error(
                "Telegram WebApp SDK не найден. Приложение открыто как обычная веб-страница.",
              );
            }

            if (telegramLaunchPayload) {
              stage = "telegram_login_prefetch";
              lifecycleTrace("login_start", { reason, sequenceId });
              traceStartup("loadAppData_login_started", { reason, sequenceId });
              traceStart("telegram_login_start", { reason, sequenceId });
              const telegramStartParam = getTelegramStartParam();
              const referralCode = getReferralCodeFromStartParam(telegramStartParam);
              const telegramRuntimeDiagnostics = getTelegramRuntimeDiagnostics();
              traceOk("telegram_start_param_sources", {
                sourceNames: telegramRuntimeDiagnostics.startParamSourceNames,
                initDataHasStartParamKey: telegramRuntimeDiagnostics.initDataHasStartParamKey,
                locationHasStartParamKey: telegramRuntimeDiagnostics.locationHasStartParamKey,
                locationSearchHasStartParamKey: telegramRuntimeDiagnostics.locationSearchHasStartParamKey,
                locationHashHasStartParamKey: telegramRuntimeDiagnostics.locationHashHasStartParamKey,
                retrieveLaunchParamsHasStartParam: telegramRuntimeDiagnostics.retrieveLaunchParamsHasStartParam,
                retrieveLaunchParamsHasInitDataRaw: telegramRuntimeDiagnostics.retrieveLaunchParamsHasInitDataRaw,
                hasStartParam: telegramStartParam.length > 0,
                startParamLength: telegramStartParam.length,
                hasReferralCode: Boolean(referralCode),
                referralCodeLength: referralCode?.length ?? 0,
              });
              await loginWithTelegram(telegramLaunchPayload, {
                reason,
                bootstrapAttemptId: sequenceId,
                forceNew: true,
                referralCode,
                startParam: telegramStartParam || referralCode,
              });
              stage = "telegram_login_request";
              lifecycleTrace("login_ok", { sequenceId });
              traceStartup("loadAppData_login_success", { sequenceId });
              traceOk("telegram_login_ok");
            }
          };

          let profile: ClientProfile;
          let subscription: Subscription;
          lifecycleTrace("stored_token_auth_start", { forceNew });
          traceStart("stored_token_check_start");
          const storedAuthToken = getStoredAuthToken();
          lifecycleTrace("stored_token_auth_ok", {
            hasStoredAuthToken: Boolean(storedAuthToken),
            forceNew,
          });
          traceOk("stored_token_check_ok", {
            hasStoredAuthToken: Boolean(storedAuthToken),
            forceNew,
          });

          if (storedAuthToken && !forceNew) {
            try {
              ({ profile, subscription } =
                await requestProfileAndSubscription());
            } catch (caughtError) {
              if (!isApiError(caughtError) || caughtError.status !== 401) {
                throw caughtError;
              }

              lifecycleTrace("stored_token_auth_fail", caughtError);
              traceFail("stored_token_profile_fail", caughtError);
              traceFail("stored_token_subscription_fail", caughtError);
              clearStoredAuthToken();
              await loginWithTelegramPayload();
              traceStart("fresh_profile_start");
              traceStart("fresh_subscription_start");
              ({ profile, subscription } =
                await requestProfileAndSubscription());
              traceOk("fresh_profile_ok", { hasProfile: Boolean(profile) });
              traceOk("fresh_subscription_ok", {
                hasSubscription: Boolean(subscription),
              });
            }
          } else {
            await loginWithTelegramPayload();
            traceStart("fresh_profile_start");
            traceStart("fresh_subscription_start");
            ({ profile, subscription } = await requestProfileAndSubscription());
            traceOk("fresh_profile_ok", { hasProfile: Boolean(profile) });
            traceOk("fresh_subscription_ok", {
              hasSubscription: Boolean(subscription),
            });
          }

          traceMark("auth_finished", { sequenceId });
          const postAuthMounted = mountedRef.current;
          const postAuthBootstrapSequence = bootstrapSequenceRef.current;
          const postAuthIsActive = isActive();

          traceStartup("loadAppData_before_post_auth_isActive_guard", {
            sequenceId,
            mounted: postAuthMounted,
            bootstrapSequence: postAuthBootstrapSequence,
            isActive: postAuthIsActive,
          });

          if (!isActive()) {
            traceStartup("loadAppData_post_auth_isActive_guard_return", {
              sequenceId,
              mounted: postAuthMounted,
              bootstrapSequence: postAuthBootstrapSequence,
              reason: !postAuthMounted
                ? "mountedRef_false"
                : postAuthBootstrapSequence !== sequenceId
                  ? "sequence_mismatch"
                  : "unknown",
            });
            return;
          }

          traceStart("stale_state_cleanup_start");
          resetCatalogStateForForceReload();
          clearStaleAppState();
          traceOk("stale_state_cleanup_ok");
          traceStart("partner_flow_reset_start");
          resetPartnerFlowState(
            getStartupPage() === "catalog" ? "catalog" : "home",
          );
          traceOk("partner_flow_reset_ok");

          traceStart("app_data_set_start");
          setData(
            normalizeAppData({
              profile,
              subscription,
              partners: [],
              verifications: [],
              savings: null,
              cities: [],
              linkingStatus: null,
            }),
          );

          traceOk("app_data_set_ok", { page: pageRef.current });
          setIsLoading(false);
          setIsBootstrapDone(true);
          window.clearTimeout(hardTimeoutId);
          lifecycleTrace("bootstrap_ok", { sequenceId, page: pageRef.current });
          traceStartup("loadAppData_finished", { sequenceId, page: pageRef.current });
          traceOk("bootstrap_done", { sequenceId, page: pageRef.current });
          traceOk("startup_completed_successfully", { sequenceId, page: pageRef.current });
          markStartupCompletedSuccessfully();
          setPreviousCrashDump(null);
          logBootstrapDiagnostic("app_bootstrap_success", {
            sequenceId,
            elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
            hasProfile: Boolean(profile),
            hasSubscription: Boolean(subscription),
          });

          if (hasCatalogRecoveryFlag()) {
            console.info("catalog_recovery_flag_detected", { sequenceId, page: pageRef.current });
            traceStartup("catalog_recovery_flag_detected", { sequenceId, page: pageRef.current });
            setCatalogRecoveryPending(true);
            setPage("catalog");
            setPartnersErrorTitle("Загрузка клуба прервана");
            setPartnersError(CATALOG_RECOVERY_MESSAGE);
          } else if (pageRef.current === "catalog") {
            console.info("catalog_reload_after_bootstrap", {
              sequenceId,
              page: pageRef.current,
              reason: "startup_core_catalog_load",
            });
            traceStartup("loadAppData_core_catalog_requested", { sequenceId });
            window.setTimeout(() => void loadPartners(true), 0);
          } else {
            traceStartup("loadAppData_core_catalog_skipped", {
              sequenceId,
              page: pageRef.current,
              reason: "safe_shell_not_catalog",
            });
          }

          traceStartup("loadAppData_optional_requests_started", { sequenceId });
          traceStart("secondary_requests_start");
          traceStart("verifications_start");
          traceStart("savings_start");
          traceStart("cities_start");
          traceStart("linking_status_start");
          const [
            verificationsResult,
            savingsResult,
            citiesResult,
            linkingStatusResult,
          ] = await Promise.allSettled([
            getVerifications(),
            getSavings(),
            getCities(),
            getLinkingStatus(),
          ]);

          traceStartup("loadAppData_before_post_optional_isActive_guard", {
            sequenceId,
            mounted: mountedRef.current,
            bootstrapSequence: bootstrapSequenceRef.current,
            isActive: isActive(),
          });

          if (!isActive()) {
            traceStartup("loadAppData_post_optional_isActive_guard_return", {
              sequenceId,
              mounted: mountedRef.current,
              bootstrapSequence: bootstrapSequenceRef.current,
              reason: !mountedRef.current
                ? "mountedRef_false"
                : bootstrapSequenceRef.current !== sequenceId
                  ? "sequence_mismatch"
                  : "unknown",
            });
            return;
          }

          lifecycleTrace("secondary_requests_ok", { sequenceId });
          traceStartup("loadAppData_optional_requests_finished", { sequenceId });
          traceMark("secondary_requests_done", {
            verifications: verificationsResult.status,
            savings: savingsResult.status,
            cities: citiesResult.status,
            linkingStatus: linkingStatusResult.status,
          });
          verificationsResult.status === "fulfilled"
            ? traceOk("verifications_ok")
            : traceFail("verifications_fail", verificationsResult.reason);
          savingsResult.status === "fulfilled"
            ? traceOk("savings_ok")
            : traceFail("savings_fail", savingsResult.reason);
          citiesResult.status === "fulfilled"
            ? traceOk("cities_ok")
            : traceFail("cities_fail", citiesResult.reason);
          linkingStatusResult.status === "fulfilled"
            ? traceOk("linking_status_ok")
            : traceFail("linking_status_fail", linkingStatusResult.reason);

          const nextLinkingStatus =
            linkingStatusResult.status === "fulfilled"
              ? linkingStatusResult.value
              : null;

          setData((current) =>
            normalizeAppData({
              ...current,
              verifications:
                verificationsResult.status === "fulfilled"
                  ? verificationsResult.value
                  : current.verifications,
              savings:
                savingsResult.status === "fulfilled"
                  ? savingsResult.value
                  : current.savings,
              cities:
                citiesResult.status === "fulfilled"
                  ? citiesResult.value
                  : current.cities,
              linkingStatus: nextLinkingStatus ?? current.linkingStatus,
            }),
          );

          const dismissedKey = getLinkingDismissKey(profile);
          setShouldShowLinking(
            shouldShowLinkingOnboarding(
              isTelegram,
              profile,
              nextLinkingStatus,
              dismissedKey,
            ),
          );

          logBootstrapDiagnostic("app_bootstrap_optional_success", {
            sequenceId,
            elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
            hasProfile: Boolean(profile),
            hasSubscription: Boolean(subscription),
            secondaryRequests: {
              verifications: verificationsResult.status,
              savings: savingsResult.status,
              cities: citiesResult.status,
              linkingStatus: linkingStatusResult.status,
            },
          });
        } catch (caughtError) {
          const error = caughtError instanceof Error ? caughtError : null;
          traceMark("auth_finished", { sequenceId, failed: true, stage });
          lifecycleTrace("bootstrap_fail", { stage, error: caughtError });
          traceStartup("loadAppData_failed", { stage, error: caughtError });
          traceFail(`${stage}_fail`, caughtError);
          saveCrashDump("fatal_startup_error", { stage });
          logBootstrapDiagnostic("app_bootstrap_error", {
            sequenceId,
            stage,
            errorName: safeDiagnosticText(error?.name),
            errorMessageShort: safeDiagnosticText(
              error?.message ?? caughtError,
            ),
            elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
          });
          if (isActive()) {
            setError(createDiagnostic(stage, caughtError));
          }
        } finally {
          window.clearTimeout(hardTimeoutId);
          if (isActive()) {
            setIsLoading(false);
          }

          if (bootstrapPromiseRef.current === bootstrapPromise) {
            bootstrapPromiseRef.current = null;
            logBootstrapDeadlockDiagnostic("bootstrapPromiseRef_cleared", {
              reason: "finally",
              sequenceId,
            });
          }
        }
      })();

      bootstrapPromiseRef.current = bootstrapPromise;
      logBootstrapDeadlockDiagnostic("bootstrapPromiseRef_created", {
        sequenceId,
        reason,
        forceNew,
      });
      return bootstrapPromise;
    },
    [logBootstrapDeadlockDiagnostic, resetCatalogStateForForceReload, resetPartnerFlowState],
  );

  useEffect(() => {
    void loadAppData();
  }, [loadAppData, logBootstrapDeadlockDiagnostic]);

  useEffect(() => {
    const refreshAfterWebViewResume = (event: PageTransitionEvent | Event) => {
      lifecycleTrace("webview_resume_prepare_start", {
        eventType: event.type,
        persisted:
          event instanceof PageTransitionEvent ? event.persisted : undefined,
        visibilityState: document.visibilityState,
      });
      try {
        traceStartup("telegram_viewport_prepare_called", { eventType: event.type });
        prepareTelegramViewport();
        traceStartup("telegram_viewport_prepare_finished", { eventType: event.type });
        lifecycleTrace("webview_resume_prepare_ok", { eventType: event.type });
      } catch (caughtError) {
        lifecycleTrace("webview_resume_prepare_fail", caughtError);
      }
    };

    const markActive = (event: PageTransitionEvent | Event) => {
      appActiveRef.current = true;
      logBootstrapDeadlockDiagnostic("webview_active", {
        lifecycleEvent: event.type,
        persisted:
          event instanceof PageTransitionEvent ? event.persisted : undefined,
      });
      traceStartup("webview_active", { eventType: event.type });
      refreshAfterWebViewResume(event);
    };

    const markInactive = (event: Event) => {
      appActiveRef.current = false;
      logBootstrapDeadlockDiagnostic("webview_inactive", { lifecycleEvent: event.type });
      traceStartup("webview_inactive", { eventType: event.type });
      if (catalogLoadingRef.current || partnersPromiseRef.current) {
        setCatalogRecoveryFlag();
        console.info("catalog_load_aborted_on_hide", { eventType: event.type, page: pageRef.current });
        traceStartup("catalog_load_aborted_on_hide", { eventType: event.type, page: pageRef.current });
      }
      abortInFlightCatalogLoad(event.type);
    };

    const onPageShow = (event: PageTransitionEvent) => {
      traceStartup("pageshow", { persisted: event.persisted });
      markActive(event);
    };
    const onPageHide = (event: PageTransitionEvent) => markInactive(event);
    const onResume = (event: Event) => markActive(event);
    const onFocus = (event: Event) => {
      traceStartup("focus");
      markActive(event);
    };
    const onBlur = (event: Event) => markInactive(event);
    const onVisibilityChange = (event: Event) => {
      traceStartup("visibilitychange", { visibilityState: document.visibilityState });
      if (document.visibilityState === "visible") {
        markActive(event);
      } else if (document.visibilityState === "hidden") {
        markInactive(event);
      }
    };

    window.addEventListener("pageshow", onPageShow);
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("focus", onFocus);
    window.addEventListener("blur", onBlur);
    document.addEventListener("resume", onResume);
    document.addEventListener("visibilitychange", onVisibilityChange);

    const telegramWebApp = window.Telegram?.WebApp;
    const onTelegramActivated = () => markActive(new Event("telegram_activated"));
    const onTelegramDeactivated = () => markInactive(new Event("telegram_deactivated"));
    telegramWebApp?.onEvent?.("activated" as never, onTelegramActivated);
    telegramWebApp?.onEvent?.("deactivated" as never, onTelegramDeactivated);

    return () => {
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("resume", onResume);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      telegramWebApp?.offEvent?.("activated" as never, onTelegramActivated);
      telegramWebApp?.offEvent?.("deactivated" as never, onTelegramDeactivated);
    };
  }, [abortInFlightCatalogLoad, logBootstrapDeadlockDiagnostic]);

  const loadPartners = useCallback(
    (forceRetry = true) => {
      const logCatalogReturn = (reason: string) => {
        console.info("catalog_return", {
          reason,
          force: forceRetry,
          catalogLoaded: hasPartnersLoaded,
          catalogLoading: isPartnersLoading,
          hasInflight: Boolean(partnersPromiseRef.current),
          partnersCount: data.partners.length,
          hasError: Boolean(partnersError),
          hasDiagnostic: Boolean(partnersErrorDetails),
        });
      };

      if (forceRetry) {
        resetCatalogStateForForceReload();
      } else if (partnersPromiseRef.current) {
        console.info("catalog_load_skipped_with_reason", {
          reason: "inflight",
          forceRetry,
        });
        logCatalogReturn("inflight");
        return partnersPromiseRef.current;
      }

      const localRequestId = catalogLoadSequenceRef.current + 1;
      catalogLoadSequenceRef.current = localRequestId;
      const startedAtIso = new Date().toISOString();
      const catalogAbortController = new AbortController();
      catalogAbortControllerRef.current = catalogAbortController;

      let promise!: Promise<void>;
      promise = (async () => {
        catalogTrace("catalog requested", { forceRetry, localRequestId });
        traceStartup("loadPartners_called", { forceRetry, localRequestId });
        catalogTrace("loadPartners entered", { forceRetry, localRequestId });
        traceStartup("loadPartners_entered", { forceRetry, localRequestId });
        traceStart("catalog_load_start", { forceRetry, localRequestId });
        console.info("catalog_load_started", {
          forceRetry,
          localRequestId,
          startedAtIso,
        });
        catalogLoadingRef.current = true;
        setIsPartnersLoading(true);
        setPartnersError("");
        setPartnersErrorDetails(undefined);
        setCatalogErrorCreatedAt(undefined);
        setCatalogLoadStartedAt(startedAtIso);
        setCatalogLoadRequestId(localRequestId);

        try {
          const bootstrapPartners = forceRetry ? null : consumeCatalogBootstrap();
          traceStartup("loadPartners_before_getPartners", { localRequestId });
          catalogTrace("getPartners entered", { localRequestId });
          // Regression anchor: previous code used `const partners = await getPartners();`;
          // keep catalog fetch non-bootstrap-blocking while allowing lifecycle aborts.
          const partners = await getPartners({ signal: catalogAbortController.signal });
          if (catalogAbortController.signal.aborted) {
            traceStartup("loadPartners_aborted_before_state_update", { localRequestId });
            return;
          }
          if (bootstrapPartners && partners.length === 0) {
            console.info("catalog_bootstrap_replaced_by_empty_fetch", {
              bootstrapCount: bootstrapPartners.length,
              localRequestId,
            });
          }
          setData((current) => normalizeAppData({ ...current, partners }));
          setHasPartnersLoaded(true);
          lifecycleTrace("catalog_load_ok", {
            partnersCount: partners.length,
            source: "fetch",
            hadBootstrap: Boolean(bootstrapPartners),
          });
          catalogTrace("catalog rendered", { localRequestId, partnersCount: partners.length });
          traceStartup("loadPartners_success", { localRequestId, partnersCount: partners.length });
          traceOk("catalog_load_ok", {
            partnersCount: partners.length,
            source: "fetch",
            hadBootstrap: Boolean(bootstrapPartners),
          });
          console.info("catalog_load_success", {
            partnersCount: partners.length,
            localRequestId,
            source: "fetch",
            hadBootstrap: Boolean(bootstrapPartners),
          });
        } catch (caughtError) {
          const diagnostic = isCatalogLoadError(caughtError)
            ? caughtError.diagnostic
            : undefined;
          lifecycleTrace("catalog_load_fail", caughtError);
          catalogTrace("fetch rejected", { localRequestId, error: caughtError });
          traceStartup("loadPartners_error", { localRequestId, error: caughtError });
          traceFail("catalog_load_fail", caughtError);
          saveCrashDump("catalog_load_interrupted", { localRequestId });
          if (typeof window !== "undefined") {
            window.__BLOOM_LAST_CATALOG_ERROR__ = diagnostic ?? caughtError;
          }
          console.info(
            "catalog_load_failed",
            diagnostic ?? {
              errorName:
                caughtError instanceof Error ? caughtError.name : undefined,
              errorMessage:
                caughtError instanceof Error
                  ? safeDiagnosticText(caughtError.message)
                  : undefined,
            },
          );
          if (catalogAbortController.signal.aborted) {
            traceStartup("loadPartners_aborted", { localRequestId, reason: String(catalogAbortController.signal.reason ?? "") });
            return;
          }
          setCatalogErrorCreatedAt(new Date().toISOString());
          setPartnersErrorTitle(
            TG_LOCAL_CATALOG_ENABLED
              ? "Не удалось загрузить каталог Telegram"
              : "Не удалось загрузить каталог",
          );
          setPartnersError(
            diagnostic?.abortSource === "timeout"
              ? "Загрузка каталога заняла слишком много времени. Закройте этот экран или попробуйте ещё раз."
              : TG_LOCAL_CATALOG_ENABLED
                ? "Проверьте подключение и попробуйте снова."
                : "Не удалось загрузить каталог",
          );
          setPartnersErrorDetails(
            diagnostic
              ? {
                  source: diagnostic.source,
                  requestUrl: diagnostic.requestUrl,
                  requestUrlPath: diagnostic.requestUrlPath,
                  requestOrigin: diagnostic.requestOrigin,
                  httpStatus: diagnostic.httpStatus,
                  requestId: diagnostic.requestId,
                  elapsedMs: diagnostic.elapsedMs,
                  attempt: diagnostic.attempt,
                  fetchPhase: diagnostic.fetchPhase,
                  errorName: diagnostic.errorName,
                  isAbortError: diagnostic.isAbortError,
                }
              : undefined,
          );
        } finally {
          const ownsCatalogPromise = partnersPromiseRef.current === promise;
          const ownsCatalogAbortController =
            catalogAbortControllerRef.current === catalogAbortController;

          if (ownsCatalogAbortController) {
            catalogAbortControllerRef.current = null;
          }
          if (ownsCatalogPromise) {
            catalogLoadingRef.current = false;
            setIsPartnersLoading(false);
            partnersPromiseRef.current = null;
            if (!hasCatalogRecoveryFlag()) clearCatalogRecoveryFlag();
          }
        }
      })();

      partnersPromiseRef.current = promise;
      logCatalogReturn("started");
      return promise;
    },
    [
      data.partners.length,
      hasPartnersLoaded,
      isPartnersLoading,
      partnersError,
      partnersErrorDetails,
      resetCatalogStateForForceReload,
    ],
  );

  const openCatalog = useCallback(() => {
    lifecycleTrace("catalog_open", { forceReload: false });
    console.info("catalog_open_requested", {
      catalogLoaded: hasPartnersLoaded,
      catalogLoading: isPartnersLoading,
      partnersCount: data.partners.length,
      hasCatalogError: Boolean(partnersError),
      hasCatalogDiagnostic: Boolean(partnersErrorDetails),
      forceReload: false,
    });

    setSelectedPartner(null);
    setPartnerOffers([]);
    setPartnerOffersStatus("idle");
    setPartnerOffersError("");
    setPartnerOffersDiagnostic(null);
    setPage("catalog");
    if (hasCatalogRecoveryFlag() || catalogRecoveryPending) {
      console.info("catalog_recovery_flag_detected", { source: "openCatalog" });
      traceStartup("catalog_recovery_flag_detected", { source: "openCatalog" });
      setCatalogRecoveryPending(true);
      setPartnersErrorTitle("Загрузка клуба прервана");
      setPartnersError(CATALOG_RECOVERY_MESSAGE);
      return;
    }
    window.setTimeout(() => void loadPartners(false), 0);
  }, [
    data.partners.length,
    hasPartnersLoaded,
    isPartnersLoading,
    loadPartners,
    partnersError,
    partnersErrorDetails,
    catalogRecoveryPending,
  ]);

  const navigate = useCallback(
    (nextPage: PageId) => {
      if (nextPage === "catalog") {
        openCatalog();
        return;
      }

      lifecycleTrace("page_transition_request", { nextPage });
      setPage(nextPage);
    },
    [openCatalog],
  );

  const cancelCatalogLoad = useCallback(() => {
    lifecycleTrace("recovery_action", { action: "cancel_catalog_load" });
    console.info("catalog_load_cancelled_by_user", { page: pageRef.current });
    abortInFlightCatalogLoad("user_cancel_catalog");
    clearCatalogRecoveryFlag();
    setCatalogRecoveryPending(false);
    setPartnersError("");
    setPartnersErrorDetails(undefined);
    setCatalogErrorCreatedAt(undefined);
    setPage("home");
  }, [abortInFlightCatalogLoad]);

  const retryCatalogAfterRecovery = useCallback(() => {
    clearCatalogRecoveryFlag();
    setCatalogRecoveryPending(false);
    setPartnersError("");
    setPartnersErrorDetails(undefined);
    void loadPartners(true);
  }, [loadPartners]);

  const loadPartnerOffers = useCallback(async (partner: Partner) => {
    const resolved = resolveNumericPartnerId(partner);

    setPartnerOffers([]);
    setPartnerOffersError("");
    setPartnerOffersDiagnostic(null);
    lifecycleTrace("offers_load_start", { hasPartner: Boolean(partner) });
    traceStart("offers_load_start", { hasPartner: Boolean(partner) });
    setPartnerOffersStatus("loading");

    if (!resolved) {
      traceFail("offers_load_fail", { reason: "missing_numeric_partner_id" });
      setPartnerOffersStatus("error");
      setPartnerOffersError("Не удалось загрузить предложения партнёра");
      setPartnerOffersDiagnostic({
        partnerIdSource: "partner.id",
        partnerIdMissingOrInvalid: true,
        backendDetail:
          "partner.id отсутствует или не является numeric Partner.id.",
      });
      return;
    }

    const offersUrlPath = getPartnerOffersPath(resolved.numericPartnerId);
    const baseDiagnostic: PartnerOffersDiagnostic = {
      numericPartnerId: resolved.numericPartnerId,
      partnerIdSource: resolved.source,
      offersUrlPath,
      source: TG_LOCAL_CATALOG_ENABLED
        ? "tg_local_catalog"
        : "web_legacy_catalog",
    };

    try {
      const response = await getPartnerOffers(resolved.numericPartnerId);
      const safeOffers = normalizeOffersResponse(response);
      setPartnerOffers(safeOffers);
      setPartnerOffersStatus(safeOffers.length ? "success" : "empty");
      lifecycleTrace("offers_load_ok", { offersCount: safeOffers.length });
      traceOk("offers_load_ok", { offersCount: safeOffers.length });
    } catch (caughtError) {
      lifecycleTrace("offers_load_fail", caughtError);
      traceFail("offers_load_fail", caughtError);
      setPartnerOffers([]);
      setPartnerOffersDiagnostic({
        ...baseDiagnostic,
        httpStatus: isApiError(caughtError) ? caughtError.status : undefined,
        backendDetail: isApiError(caughtError)
          ? safeDiagnosticText(caughtError.detail)
          : undefined,
      });

      if (isTimeoutError(caughtError)) {
        setPartnerOffersStatus("timeout");
        setPartnerOffersError("Не удалось загрузить предложения партнёра");
      } else if (isApiError(caughtError) && caughtError.status === 401) {
        setPartnerOffersStatus("error");
        setPartnerOffersError("Сессия истекла, откройте приложение заново");
      } else {
        setPartnerOffersStatus("error");
        setPartnerOffersError("Не удалось загрузить предложения партнёра");
      }
    } finally {
      setPartnerOffersStatus((current) =>
        current === "loading" ? "error" : current,
      );
    }
  }, []);

  const openPartner = useCallback(
    (partner: Partner) => {
      lifecycleTrace("partner_open", { hasPartner: Boolean(partner) });
      traceStart("partner_open_start", { hasPartner: Boolean(partner) });
      setSelectedPartner(partner);
      setPage("partner");
      void loadPartnerOffers(partner);
    },
    [loadPartnerOffers],
  );

  const retryPartnerOffers = useCallback(() => {
    lifecycleTrace("recovery_action", { action: "retry_partner_offers" });
    if (selectedPartner) {
      void loadPartnerOffers(selectedPartner);
    }
  }, [loadPartnerOffers, selectedPartner]);

  const refreshProfileAndSubscription = useCallback(async () => {
    const [profile, subscription] = await Promise.all([
      getProfile(),
      getSubscription(),
    ]);
    setData((current) =>
      normalizeAppData({ ...current, profile, subscription }),
    );
    return { profile, subscription };
  }, []);

  const saveProfile = useCallback(async (payload: ClientProfilePatch) => {
    try {
      await updateProfile(payload);
      const profile = await getProfile();
      setData((current) => normalizeAppData({ ...current, profile }));
      return profile;
    } catch (caughtError) {
      throw caughtError;
    }
  }, []);

  const activateTrial = useCallback(async () => {
    setTrialMessage(null);

    try {
      const trialResponse = await activateTrialSubscription();
      const trialPayload = extractTrialPayload(trialResponse);
      const subscription = trialPayload.subscription || trialResponse;
      setData((current) =>
        normalizeAppData({
          ...current,
          profile: trialPayload.profile || current.profile,
          subscription,
        }),
      );
      const refreshed = await refreshProfileAndSubscription().catch(() => null);
      const referralSummary = await getReferralSummary().catch(() => null);
      if (referralSummary) {
        setData((current) => normalizeAppData({ ...current, referralSummary }));
      }
      const updatedSubscription = refreshed?.subscription || subscription;
      const end = getSubscriptionEnd(updatedSubscription);
      setTrialMessage(
        end
          ? `Тестовый период активирован. Доступ к клубу до ${formatDate(end)}.`
          : "Тестовый период активирован.",
      );
      return updatedSubscription;
    } catch (caughtError) {
      throw caughtError;
    }
  }, [refreshProfileAndSubscription]);

  const createVerification = useCallback(
    async (partnerId: string | number, offerId: string | number) => {
      try {
        const verification = await verifyPartnerOffer(partnerId, offerId);
        setData((current) =>
          normalizeAppData({
            ...current,
            verifications: [
              verification,
              ...current.verifications.filter(
                (item) => item.id !== verification.id,
              ),
            ],
          }),
        );

        const refreshedVerifications = await getVerifications().catch(
          () => null,
        );
        if (refreshedVerifications) {
          setData((current) =>
            normalizeAppData({
              ...current,
              verifications: refreshedVerifications,
            }),
          );
        }

        return verification;
      } catch (caughtError) {
        throw caughtError;
      }
    },
    [],
  );

  const openPayment = useCallback(async () => {
    setIsCreatingPayment(true);
    setPaymentMessage(null);

    try {
      const request = await createPaymentRequest();
      setPaymentRequest(request);
      setPaymentMessage("Запрос на продление создан.");
    } catch (caughtError) {
      setPaymentMessage(
        isTimeoutError(caughtError)
          ? RETRYABLE_LOAD_ERROR_MESSAGE
          : "Не удалось подготовить продление. Попробуйте ещё раз.",
      );
    } finally {
      setIsCreatingPayment(false);
    }
  }, []);

  const refreshAfterLinking = useCallback(async () => {
    const [profile, subscription, linkingStatus, referralSummary] = await Promise.all([
      getProfile(),
      getSubscription(),
      getLinkingStatus().catch(() => null),
      getReferralSummary().catch(() => null),
    ]);

    setData((current) =>
      normalizeAppData({
        ...current,
        profile,
        subscription,
        linkingStatus: linkingStatus ?? current.linkingStatus,
        referralSummary: referralSummary ?? current.referralSummary,
      }),
    );
  }, []);

  const dismissLinkingOnboarding = useCallback(() => {
    const key = getLinkingDismissKey(data.profile);
    if (key) {
      window.localStorage.setItem(key, "1");
    }
    setShouldShowLinking(false);
  }, [data.profile]);

  useEffect(() => {
    if (!isLoading && !error) {
      lifecycleTrace(`page_render_${page}`, { page });
      traceStart("render_page_start", { page });
      traceOk("render_page_ok", { page });
      traceMark("app_interactive", { page });
      window.__BLOOM_APP_INTERACTIVE__ = true;
      setHasRenderedPageContent(true);
      setShowStartupRecovery(false);
    }
  }, [error, isLoading, page]);

  const activeNavPage = useMemo<PageId>(() => {
    if (page === "partner") {
      return "catalog";
    }

    if (page === "subscription") {
      return "profile";
    }

    return page;
  }, [page]);

  const safeData = normalizeAppData(data);
  const hasValidSelectedPartner = selectedPartner !== null;
  const activePage = isKnownPage(page)
    ? page === "partner" && !hasValidSelectedPartner
      ? "catalog"
      : page
    : "home";
  const unknownStateDiagnostic = !isKnownPage(page)
    ? createUnknownStateDiagnostic(`Unknown page: ${page}`)
    : page === "partner" && !hasValidSelectedPartner
      ? createUnknownStateDiagnostic(
          "Stale partner screen without selected partner",
        )
      : null;


  const openDiagnosticsByHiddenGesture = useCallback(() => {
    debugTapCountRef.current += 1;
    if (debugTapTimerRef.current !== undefined) window.clearTimeout(debugTapTimerRef.current);
    debugTapTimerRef.current = window.setTimeout(() => { debugTapCountRef.current = 0; }, 2500);
    if (debugTapCountRef.current >= 7) {
      debugTapCountRef.current = 0;
      enableBloomDebug();
      lifecycleTrace("diagnostic_overlay_hidden_gesture_open", { page: activePage });
      setDiagnosticOverlayReason("Диагностика открыта скрытым жестом: 7 тапов.");
      setShowStartupDiagnostics(true);
    }
  }, [activePage]);

  if (showStartupRecovery) {
    return <StartupRecoveryScreen message={watchdogMessage} />;
  }

  if (isLoading) {
    return <LoadingState title="Загружаем данные клуба" />;
  }

  if (error) {
    return (
      <ErrorState
        title="Не удалось открыть Bloom Club"
        description={error.message}
        diagnostic={error}
        onRetry={() => loadAppData("manual", true)}
        startupContext={{
          currentPage: page,
          bootstrapStatus: isBootstrapDone ? "done" : "pending",
          catalogStatus: isPartnersLoading
            ? "loading"
            : hasPartnersLoaded
              ? "loaded"
              : partnersError
                ? "error"
                : "idle",
          offersStatus: partnerOffersStatus,
        }}
      />
    );
  }


  if (!isKnownPage(page) && unknownStateDiagnostic) {
    return (
      <ContentProvider>
        <AppShell activePage="home" onNavigate={setPage}>
          <ErrorState
            title="Не удалось определить раздел приложения"
            description="Откройте главный экран или повторите запуск Mini App."
            diagnostic={unknownStateDiagnostic}
            onRetry={() => setPage("home")}
            startupContext={{
              currentPage: page,
              bootstrapStatus: isBootstrapDone ? "done" : "pending",
              catalogStatus: hasPartnersLoaded ? "loaded" : "idle",
              offersStatus: partnerOffersStatus,
            }}
          />
        </AppShell>
      </ContentProvider>
    );
  }


  const catalogStatus = isPartnersLoading
    ? "loading"
    : hasPartnersLoaded
      ? "loaded"
      : partnersError
        ? "error"
        : "idle";
  const latestCatalogTrace = getStartupTrace();
  const diagnosticFlags = {
    catalogLoadRequested: catalogLoadRequestId !== undefined,
    fetchStarted: latestCatalogTrace.some((event) => event.step === "getPartners_fetch_started"),
    timeoutStarted: latestCatalogTrace.some((event) => event.step === "catalog_timeout_created"),
    activePage,
    currentPath: typeof window === "undefined" ? "" : `${window.location.pathname}${window.location.search}${window.location.hash}`,
    hasToken: Boolean(getStoredAuthToken()),
    hasProfile: Boolean(safeData.profile),
    hasSubscription: Boolean(safeData.subscription),
    partnerCount: safeData.partners.length,
    catalogStatus,
  };



  const startupDiagnostics = showStartupDiagnostics ? (
    <div className="startup-diagnostic-panel" role="status">
      <button
        className="button button--secondary"
        type="button"
        onClick={() => setShowStartupDiagnostics(false)}
      >
        Скрыть диагностику запуска
      </button>
      <h2>Диагностика запуска</h2>
      {watchdogMessage ? <p>{watchdogMessage}</p> : null}
      <pre>{JSON.stringify(getStartupTrace().slice(-30), null, 2)}</pre>
    </div>
  ) : null;

  return (
    <ContentProvider>
      <AppShell activePage={activeNavPage} onNavigate={navigate} onHiddenDiagnosticsGesture={openDiagnosticsByHiddenGesture}>
        {activePage === "home" ? (
          <HomePage
            profile={safeData.profile}
            subscription={safeData.subscription}
            cities={safeData.cities}
            partners={safeData.partners}
            onOpenCatalog={openCatalog}
            onOpenSubscription={() => setPage("subscription")}
            onActivateTrial={activateTrial}
            trialMessage={trialMessage}
            referralSummary={safeData.referralSummary}
          />
        ) : null}

        {activePage === "catalog" && unknownStateDiagnostic ? (
          <ErrorState
            title="Не удалось восстановить карточку партнёра"
            description="Откройте каталог и выберите партнёра заново."
            diagnostic={unknownStateDiagnostic}
            onRetry={openCatalog}
            startupContext={{
              currentPage: page,
              bootstrapStatus: isBootstrapDone ? "done" : "pending",
              catalogStatus: hasPartnersLoaded ? "loaded" : "idle",
              offersStatus: partnerOffersStatus,
            }}
          />
        ) : null}

        {activePage === "catalog" && !unknownStateDiagnostic ? (
          <CatalogPage
            partners={safeData.partners}
            isLoading={isPartnersLoading}
            error={partnersError}
            errorTitle={partnersErrorTitle}
            errorDetails={partnersErrorDetails}
            errorCreatedAt={catalogErrorCreatedAt}
            loadStartedAt={catalogLoadStartedAt}
            loadRequestId={catalogLoadRequestId}
            onRetry={catalogRecoveryPending ? retryCatalogAfterRecovery : () => void loadPartners(true)}
            onCancel={cancelCatalogLoad}
            isRecovery={catalogRecoveryPending}
            onOpenPartner={openPartner}
          />
        ) : null}
        {activePage === "partner" ? (
          <PartnerPage
            partner={selectedPartner}
            profile={safeData.profile}
            offers={partnerOffers}
            offersStatus={partnerOffersStatus}
            offersError={partnerOffersError}
            offersDiagnostic={partnerOffersDiagnostic}
            subscription={safeData.subscription}
            onBack={openCatalog}
            onVerifyOffer={createVerification}
            onOpenSubscription={() => setPage("subscription")}
            onActivateTrial={activateTrial}
            onRetryOffers={retryPartnerOffers}
          />
        ) : null}
        {activePage === "privileges" ? (
          <PrivilegesPage
            verifications={safeData.verifications}
            emptyTitle={
              TG_LOCAL_CATALOG_ENABLED
                ? "Привилегии Telegram-каталога скоро появятся."
                : undefined
            }
            emptyDescription={
              TG_LOCAL_CATALOG_ENABLED
                ? "Выберите партнёра в Telegram-каталоге и получите код, когда выдача кодов будет подключена."
                : undefined
            }
          />
        ) : null}
        {activePage === "savings" ? (
          <SavingsPage
            savings={safeData.savings}
            emptyTitle={
              TG_LOCAL_CATALOG_ENABLED
                ? "Экономия Telegram-каталога скоро появится."
                : undefined
            }
            emptyDescription={
              TG_LOCAL_CATALOG_ENABLED
                ? "История экономии появится после подключения пользовательского контекста Telegram-каталога."
                : undefined
            }
          />
        ) : null}
        {activePage === "profile" ? (
          <ProfilePage
            profile={safeData.profile}
            subscription={safeData.subscription}
            cities={safeData.cities}
            onOpenSubscription={() => setPage("subscription")}
            onActivateTrial={activateTrial}
            onSaveProfile={saveProfile}
            referralSummary={safeData.referralSummary}
          />
        ) : null}
        {activePage === "subscription" ? (
          <SubscriptionPage
            profile={safeData.profile}
            subscription={safeData.subscription}
            paymentRequest={paymentRequest}
            isCreatingPayment={isCreatingPayment}
            trialMessage={paymentMessage || trialMessage}
            onCreatePayment={openPayment}
            onActivateTrial={activateTrial}
            onBack={() => setPage("profile")}
          />
        ) : null}

        {shouldShowLinking && isTelegramApp ? (
          <AccountLinkingOnboarding
            onDismiss={dismissLinkingOnboarding}
            onLinked={async () => {
              await refreshAfterLinking();
              setShouldShowLinking(false);
            }}
          />
        ) : null}

        {previousCrashDump ? (
          <div className="crash-dump-banner" role="status">
            <p>Обнаружена диагностика предыдущего неудачного запуска</p>
            <div>
              <button
                className="button button--primary"
                type="button"
                onClick={() => {
                  setDiagnosticOverlayReason("Диагностика предыдущего неудачного запуска.");
                  setShowStartupDiagnostics(true);
                }}
              >
                Открыть диагностику
              </button>
              <button
                className="button button--secondary"
                type="button"
                onClick={() => {
                  clearCrashDump("user_clear_previous_crash_dump");
                  setPreviousCrashDump(null);
                }}
              >
                Очистить
              </button>
            </div>
          </div>
        ) : null}
        {isStartupDebugUiEnabledValue ? (
          <>
            <button
              className="startup-diagnostic-button"
              type="button"
              onClick={() => {
                lifecycleTrace("diagnostic_overlay_manual_open", {
                  page: activePage,
                });
                setDiagnosticOverlayReason("Диагностика открыта вручную.");
                setShowStartupDiagnostics(true);
              }}
            >
              Открыть debug диагностику
            </button>
            {startupDiagnostics}
          </>
        ) : null}
        {Boolean(diagnosticOverlayReason) ? (
          <DiagnosticOverlay
            open={Boolean(diagnosticOverlayReason)}
            reason={diagnosticOverlayReason}
            onClose={() => setDiagnosticOverlayReason(null)}
            currentFlags={{ ...diagnosticFlags, previousCrashDump }}
          />
        ) : null}
      </AppShell>
    </ContentProvider>
  );
}
