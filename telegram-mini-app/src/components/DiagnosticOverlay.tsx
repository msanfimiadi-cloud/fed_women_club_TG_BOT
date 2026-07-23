import {
  getLifecycleTrace,
  lifecycleTrace,
  createLifecycleDiagnosticSnapshot,
} from "../diagnostics/lifecycleTrace";
import { getStartupTrace } from "../diagnostics/startupTrace";
import { createProductionDiagnosticSnapshot } from "../diagnostics/productionDebug";
import { appBuildInfo } from "../buildInfo";

declare global {
  interface Window {
    __BLOOM_LAST_CATALOG_ERROR__?: unknown;
  }
}

interface DiagnosticOverlayProps {
  open: boolean;
  reason?: string | null;
  onClose?: () => void;
  currentFlags?: Record<string, unknown>;
}

export function DiagnosticOverlay({
  open,
  reason,
  onClose,
  currentFlags,
}: DiagnosticOverlayProps) {
  if (!open) return null;

  const snapshot = createProductionDiagnosticSnapshot(reason ?? "manual_overlay_open");

  const copyDiagnostics = async () => {
    lifecycleTrace("diagnostics_copy_action", { reason });
    const payload = JSON.stringify(
      createProductionDiagnosticSnapshot(reason ?? "copy"),
      null,
      2,
    );
    await navigator.clipboard.writeText(payload);
  };

  const reload = () => {
    lifecycleTrace("reload_action", { source: "diagnostic_overlay" });
    window.location.reload();
  };

  return (
    <aside
      className="diagnostic-overlay"
      role="dialog"
      aria-modal="false"
      aria-label="Диагностика Bloom Club"
    >
      <div className="diagnostic-overlay__header">
        <div>
          <p className="eyebrow">Bloom diagnostics</p>
          <h2>Диагностика запуска</h2>
          {reason ? <p>{reason}</p> : null}
        </div>
        {onClose ? (
          <button
            className="button button--secondary"
            type="button"
            onClick={onClose}
          >
            Скрыть
          </button>
        ) : null}
      </div>
      <div className="diagnostic-overlay__actions">
        <button
          className="button button--primary"
          type="button"
          onClick={() => void copyDiagnostics()}
        >
          Скопировать диагностику
        </button>
        <button
          className="button button--secondary"
          type="button"
          onClick={reload}
        >
          Перезагрузить
        </button>
      </div>
      <dl className="diagnostic-overlay__summary">
        <div><dt>startup session id</dt><dd>{String(snapshot.startupSessionId)}</dd></div>
        <div><dt>app version</dt><dd>{appBuildInfo.buildVersion}</dd></div>
        <div><dt>build date</dt><dd>{appBuildInfo.buildTimestamp}</dd></div>
        <div>
          <dt>document.visibilityState</dt>
          <dd>{String((snapshot as any).documentVisibilityState ?? document.visibilityState)}</dd>
        </div>
        <div>
          <dt>document.readyState</dt>
          <dd>{String((snapshot as any).documentReadyState ?? document.readyState)}</dd>
        </div>
        <div>
          <dt>location.href</dt>
          <dd>{String((snapshot as any).browser?.currentRoute ?? window.location.href)}</dd>
        </div>
        <div>
          <dt>location.hash</dt>
          <dd>{window.location.hash}</dd>
        </div>
        <div>
          <dt>React mounted</dt>
          <dd>{String((snapshot as any).lifecycleTrace?.some((e:any)=>e.event==="app_mount") ? "yes" : "unknown")}</dd>
        </div>
        <div>
          <dt>Telegram object</dt>
          <dd>{String((snapshot as any).telegram?.hasTelegramObject ? "yes" : "no")}</dd>
        </div>
        <div>
          <dt>Telegram WebApp</dt>
          <dd>{String((snapshot as any).telegram?.hasWebApp ? "yes" : "no")}</dd>
        </div>
        <div>
          <dt>current page</dt>
          <dd>{String((snapshot as any).browser?.currentRoute ?? "unknown")}</dd>
        </div>
        <div>
          <dt>last render</dt>
          <dd>{String((snapshot as any).lifecycleTrace?.slice(-1)?.[0]?.event ?? "unknown")}</dd>
        </div>
        <div>
          <dt>last effect</dt>
          <dd>{String((snapshot as any).flags?.startupFinished ? "startup finished" : "startup pending")}</dd>
        </div>
        <div>
          <dt>last completed bootstrap step</dt>
          <dd>{String((snapshot as any).flags?.startupFailed ? "failed" : "not failed")}</dd>
        </div>
      </dl>
      {currentFlags ? (
        <>
          <h3>Startup/catalog flags</h3>
          <pre>{JSON.stringify(currentFlags, null, 2)}</pre>
        </>
      ) : null}
      <h3>Last catalog error</h3>
      <pre>{JSON.stringify(typeof window === "undefined" ? null : window.__BLOOM_LAST_CATALOG_ERROR__ ?? null, null, 2)}</pre>
      <h3>Network</h3>
      <pre>{JSON.stringify((snapshot as any).networkTrace?.slice(-50), null, 2)}</pre>
      <h3>AbortController</h3>
      <pre>{JSON.stringify((snapshot as any).abortTrace?.slice(-50), null, 2)}</pre>
      <h3>Errors</h3>
      <pre>{JSON.stringify((snapshot as any).errors?.slice(-50), null, 2)}</pre>
      <h3>window.__BLOOM_PAGE_LIFECYCLE__</h3>
      <pre>{JSON.stringify(getLifecycleTrace().slice(-100), null, 2)}</pre>
      <h3>window.__BLOOM_STARTUP_TRACE__</h3>
      <pre>{JSON.stringify(getStartupTrace().slice(-100), null, 2)}</pre>
    </aside>
  );
}
