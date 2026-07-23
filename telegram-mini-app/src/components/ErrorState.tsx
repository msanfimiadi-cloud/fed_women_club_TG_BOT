import type { AppDiagnostic } from "../diagnostics";
import { getStartupTrace } from "../diagnostics/startupTrace";
import { lifecycleTrace } from "../diagnostics/lifecycleTrace";

interface ErrorStateProps {
  title?: string;
  description?: string;
  diagnostic?: AppDiagnostic;
  onRetry?: () => void;
  retryLabel?: string;
  startupContext?: {
    currentPage: string;
    bootstrapStatus: string;
    catalogStatus: string;
    offersStatus: string;
  };
}

export function ErrorState({
  title = "Не удалось загрузить данные",
  description = "Проверьте подключение и попробуйте ещё раз.",
  diagnostic,
  onRetry,
  retryLabel = "Повторить",
  startupContext,
}: ErrorStateProps) {
  lifecycleTrace("ErrorState_render", { title, stage: diagnostic?.stage });
  const startupTrace = getStartupTrace().slice(-30);

  return (
    <div className="state state--error" role="alert">
      <p className="eyebrow">Bloom Club</p>
      <h2>{title}</h2>
      <p>{description}</p>
      {diagnostic ? (
        <dl
          className="diagnostic-list"
          aria-label="Безопасная диагностика ошибки"
        >
          <div>
            <dt>stage</dt>
            <dd>{diagnostic.stage}</dd>
          </div>
          <div>
            <dt>message</dt>
            <dd>{diagnostic.message}</dd>
          </div>
          {diagnostic.errorName ? (
            <div>
              <dt>errorName</dt>
              <dd>{diagnostic.errorName}</dd>
            </div>
          ) : null}
          {diagnostic.errorMessageShort ? (
            <div>
              <dt>errorMessageShort</dt>
              <dd>{diagnostic.errorMessageShort}</dd>
            </div>
          ) : null}
          {diagnostic.componentStackShort ? (
            <div>
              <dt>componentStackShort</dt>
              <dd>{diagnostic.componentStackShort}</dd>
            </div>
          ) : null}
          {typeof diagnostic.status === "number" ? (
            <div>
              <dt>HTTP status</dt>
              <dd>{diagnostic.status}</dd>
            </div>
          ) : null}
          {diagnostic.detail ? (
            <div>
              <dt>detail</dt>
              <dd>{diagnostic.detail}</dd>
            </div>
          ) : null}
          {diagnostic.technicalMessage ? (
            <div>
              <dt>network</dt>
              <dd>{diagnostic.technicalMessage}</dd>
            </div>
          ) : null}
          {diagnostic.telegramLogin
            ? Object.entries(diagnostic.telegramLogin).map(([key, value]) => (
                <div key={`telegram-login-${key}`}>
                  <dt>{key}</dt>
                  <dd>
                    {Array.isArray(value) ? value.join(", ") : String(value)}
                  </dd>
                </div>
              ))
            : null}
          {Object.entries(diagnostic.telegramRuntime).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{String(value)}</dd>
            </div>
          ))}
          <div>
            <dt>startupTrace</dt>
            <dd>
              <pre>
                {JSON.stringify(
                  {
                    lastEvents: startupTrace,
                    currentPage: startupContext?.currentPage ?? "unknown",
                    bootstrapStatus:
                      startupContext?.bootstrapStatus ?? "unknown",
                    catalogStatus: startupContext?.catalogStatus ?? "unknown",
                    offersStatus: startupContext?.offersStatus ?? "unknown",
                  },
                  null,
                  2,
                )}
              </pre>
            </dd>
          </div>
          {Object.entries(diagnostic.buildInfo).map(([key, value]) => (
            <div key={`build-${key}`}>
              <dt>{key}</dt>
              <dd>{String(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {onRetry ? (
        <button
          className="button button--primary"
          type="button"
          onClick={onRetry}
        >
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}
