import {
  ApiError,
  NetworkError,
  isTelegramLoginError,
  type TelegramLoginDiagnostic,
} from "../api/client";
import {
  getTelegramRuntimeDiagnostics,
  type TelegramRuntimeDiagnostics,
} from "../telegram/webapp";
import { appBuildInfo } from "../buildInfo";

export type AppStage =
  | "telegram_runtime_check"
  | "init_data_read"
  | "telegram_login_prefetch"
  | "telegram_login_request"
  | "telegram_login_response_parse"
  | "telegram_login_token_extract"
  | "profile_request"
  | "subscription_request"
  | "partners_request"
  | "verifications_request"
  | "savings_request"
  | "cities_request"
  | "unknown_app_state"
  | "react_runtime_error"
  | "window_runtime_error"
  | "unhandled_promise_rejection";

export interface AppDiagnostic {
  stage: AppStage;
  message: string;
  status?: number;
  detail?: string;
  technicalMessage?: string;
  errorName?: string;
  errorMessageShort?: string;
  componentStackShort?: string;
  telegramLogin?: TelegramLoginDiagnostic;
  telegramRuntime: TelegramRuntimeDiagnostics;
  buildInfo: typeof appBuildInfo;
}

const GENERIC_UNKNOWN_MESSAGE = "Неизвестная ошибка приложения";

export function safeText(value: unknown, maxLength = 240): string | undefined {
  if (typeof value === "string") {
    return value
      .replace(
        /(telegram_payload|initData|init_data|hash|signature|access_token|token)=([^&\s]+)/gi,
        "$1=[redacted]",
      )
      .slice(0, maxLength);
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return undefined;
}

export function createDiagnostic(
  stage: AppStage,
  caughtError: unknown,
): AppDiagnostic {
  const telegramRuntime = getTelegramRuntimeDiagnostics();

  if (isTelegramLoginError(caughtError)) {
    return {
      stage: caughtError.loginStage,
      message: caughtError.message,
      errorName:
        safeText(caughtError.diagnostic.errorName, 80) || caughtError.name,
      errorMessageShort: safeText(
        caughtError.diagnostic.errorMessageShort,
        180,
      ),
      status: caughtError.diagnostic.httpStatus,
      detail: safeText(caughtError.diagnostic.backendDetail),
      telegramLogin: caughtError.diagnostic,
      telegramRuntime,
      buildInfo: appBuildInfo,
    };
  }

  if (caughtError instanceof ApiError) {
    return {
      stage,
      message: caughtError.message,
      status: caughtError.status,
      detail: safeText(caughtError.detail),
      telegramRuntime,
      buildInfo: appBuildInfo,
    };
  }

  if (caughtError instanceof NetworkError) {
    return {
      stage,
      message: "Сетевой запрос не отправлен / network error",
      technicalMessage: caughtError.message,
      telegramRuntime,
      buildInfo: appBuildInfo,
    };
  }

  if (caughtError instanceof Error) {
    return {
      stage,
      message: caughtError.message || GENERIC_UNKNOWN_MESSAGE,
      telegramRuntime,
      buildInfo: appBuildInfo,
    };
  }

  return {
    stage,
    message: GENERIC_UNKNOWN_MESSAGE,
    telegramRuntime,
    buildInfo: appBuildInfo,
  };
}

export function createRuntimeErrorDiagnostic(
  caughtError: unknown,
  componentStack?: string | null,
  stage: Extract<
    AppStage,
    "react_runtime_error" | "window_runtime_error" | "unhandled_promise_rejection"
  > = "react_runtime_error",
): AppDiagnostic {
  const error = caughtError instanceof Error ? caughtError : null;
  const errorMessageShort =
    safeText(error?.message ?? caughtError, 180) || GENERIC_UNKNOWN_MESSAGE;

  return {
    stage,
    message:
      stage === "react_runtime_error" ? "React runtime error" : "Runtime error",
    errorName: safeText(error?.name, 80) || "Error",
    errorMessageShort,
    componentStackShort: safeText(componentStack, 500),
    telegramRuntime: getTelegramRuntimeDiagnostics(),
    buildInfo: appBuildInfo,
  };
}

export function createUnknownStateDiagnostic(
  message = "Unexpected application state",
): AppDiagnostic {
  return {
    stage: "unknown_app_state",
    message,
    telegramRuntime: getTelegramRuntimeDiagnostics(),
    buildInfo: appBuildInfo,
  };
}
