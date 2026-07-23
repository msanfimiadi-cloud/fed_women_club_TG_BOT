/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_TG_LOCAL_CATALOG_ENABLED?: string;
  readonly VITE_TG_API_BASE_URL?: string;
  readonly VITE_CONTENT_API_BASE_URL?: string;
  readonly VITE_APP_VERSION?: string;
  readonly VITE_APP_BUILD_TIMESTAMP?: string;
}
