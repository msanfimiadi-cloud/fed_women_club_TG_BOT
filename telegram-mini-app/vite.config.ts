import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { execSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import packageJson from "./package.json";

function getBuildHash(): string {
  return process.env.VITE_APP_BUILD_HASH || process.env.VITE_GIT_COMMIT || execSync("git rev-parse --short=12 HEAD", { encoding: "utf8" }).trim();
}

export default defineConfig(() => {
  const buildTimestamp = new Date().toISOString();
  const buildHash = getBuildHash();
  return ({
  plugins: [react(), { name: "bloom-build-id", closeBundle() { writeFileSync("dist/build-id.txt", buildHash); } }],
  define: {
    __APP_BUILD_TIMESTAMP__: JSON.stringify(buildTimestamp),
    __APP_BUILD_HASH__: JSON.stringify(buildHash),
    __APP_PACKAGE_VERSION__: JSON.stringify(packageJson.version),
  },
  server: {
    port: 5174,
  },
  build: {
    emptyOutDir: false,
  },
});
});
