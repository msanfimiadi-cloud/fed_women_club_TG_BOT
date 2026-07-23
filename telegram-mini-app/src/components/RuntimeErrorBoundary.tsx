import {
  Component,
  type ErrorInfo,
  type PropsWithChildren,
  type ReactNode,
} from "react";
import {
  createRuntimeErrorDiagnostic,
  type AppDiagnostic,
} from "../diagnostics";
import { clearStaleAppState } from "../stateRecovery";
import { ErrorState } from "./ErrorState";
import { lifecycleTrace } from "../diagnostics/lifecycleTrace";
import { traceStartup } from "../diagnostics/startupTrace";
import { saveCrashDump } from "../diagnostics/crashDump";
import { reportClientError } from "../diagnostics/clientErrorReporter";

interface RuntimeErrorBoundaryState {
  diagnostic: AppDiagnostic | null;
}

function recoverToCatalog(): void {
  lifecycleTrace("recovery_action", { action: "recover_to_catalog" });
  clearStaleAppState();
  window.location.hash = "#catalog";
  window.location.reload();
}

export class RuntimeErrorBoundary extends Component<
  PropsWithChildren,
  RuntimeErrorBoundaryState
> {
  state: RuntimeErrorBoundaryState = {
    diagnostic: null,
  };

  private handleWindowError = (event: ErrorEvent): void => {
    saveCrashDump("window.onerror", { source: "RuntimeErrorBoundary" });
    reportClientError("window.onerror", event.error ?? event.message, { source: "RuntimeErrorBoundary", filename: event.filename, line: event.lineno, column: event.colno });
    this.setState({
      diagnostic: createRuntimeErrorDiagnostic(
        event.error ?? event.message,
        null,
        "window_runtime_error",
      ),
    });
  };

  private handleUnhandledRejection = (event: PromiseRejectionEvent): void => {
    saveCrashDump("unhandledrejection", { source: "RuntimeErrorBoundary" });
    reportClientError("unhandledrejection", event.reason, { source: "RuntimeErrorBoundary" });
    this.setState({
      diagnostic: createRuntimeErrorDiagnostic(
        event.reason,
        null,
        "unhandled_promise_rejection",
      ),
    });
  };

  static getDerivedStateFromError(error: unknown): RuntimeErrorBoundaryState {
    lifecycleTrace("RuntimeErrorBoundary_error", error);
    saveCrashDump("RuntimeErrorBoundary", { source: "getDerivedStateFromError" });
    return {
      diagnostic: createRuntimeErrorDiagnostic(error),
    };
  }

  componentDidMount(): void {
    traceStartup("runtime_error_boundary_mounted");
    lifecycleTrace("RuntimeErrorBoundary_mount");
    window.addEventListener("error", this.handleWindowError);
    window.addEventListener(
      "unhandledrejection",
      this.handleUnhandledRejection,
    );
  }

  componentWillUnmount(): void {
    lifecycleTrace("RuntimeErrorBoundary_unmount");
    window.removeEventListener("error", this.handleWindowError);
    window.removeEventListener(
      "unhandledrejection",
      this.handleUnhandledRejection,
    );
  }

  componentDidCatch(error: unknown, errorInfo: ErrorInfo): void {
    lifecycleTrace("RuntimeErrorBoundary_error", {
      error,
      componentStack: errorInfo.componentStack,
    });
    saveCrashDump("RuntimeErrorBoundary", { source: "componentDidCatch" });
    reportClientError("ReactErrorBoundary", error, { source: "componentDidCatch", componentStack: errorInfo.componentStack });
    this.setState({
      diagnostic: createRuntimeErrorDiagnostic(error, errorInfo.componentStack),
    });
  }

  render(): ReactNode {
    lifecycleTrace("RuntimeErrorBoundary_render", {
      hasDiagnostic: Boolean(this.state.diagnostic),
    });
    if (this.state.diagnostic) {
      return (
        <ErrorState
          title="Не удалось показать интерфейс Bloom Club"
          description="Произошла ошибка отображения. Мы сохранили безопасную диагностику без токенов и Telegram launch payload."
          diagnostic={this.state.diagnostic}
          onRetry={recoverToCatalog}
          retryLabel="Вернуться в каталог"
        />
      );
    }

    return this.props.children;
  }
}

// static regression anchor: window.addEventListener('error', this.handleWindowError)
// static regression anchor: window.addEventListener('unhandledrejection', this.handleUnhandledRejection)
