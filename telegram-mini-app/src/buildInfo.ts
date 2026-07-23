import packageJson from "../package.json";

declare const __APP_BUILD_TIMESTAMP__: string | undefined;
declare const __APP_BUILD_HASH__: string | undefined;

const fallbackTimestamp = "dev-runtime";

export const appBuildInfo = {
  buildVersion: import.meta.env.VITE_APP_VERSION || packageJson.version,
  buildHash: import.meta.env.VITE_APP_BUILD_HASH || import.meta.env.VITE_GIT_COMMIT || (typeof __APP_BUILD_HASH__ === "string" ? __APP_BUILD_HASH__ : undefined) || import.meta.env.VITE_APP_VERSION || packageJson.version,
  buildTimestamp:
    import.meta.env.VITE_APP_BUILD_TIMESTAMP ||
    (typeof __APP_BUILD_TIMESTAMP__ === "string"
      ? __APP_BUILD_TIMESTAMP__
      : fallbackTimestamp),
};
