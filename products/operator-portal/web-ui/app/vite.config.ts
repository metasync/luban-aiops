import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// SPEC-023 R-1: PLATFORM_VERSION is injected at build time from the root
// VERSION file and stays asserted by `make validate-version` (the
// validator follows the constant to this injection point).
const versionFile = fileURLToPath(
  new URL("../../../../VERSION", import.meta.url),
);
const platformVersion = `v${readFileSync(versionFile, "utf8").trim()}`;

// v0.23.4: the Settings platform inventory names the tech stack under
// the portal itself; the resolved (locked) dependency versions are
// injected at build time so the table matches the shipped bundle.
const lockFile = JSON.parse(
  readFileSync(fileURLToPath(new URL("./package-lock.json", import.meta.url)), "utf8"),
) as { packages?: Record<string, { version?: string }> };
const manifest = JSON.parse(
  readFileSync(fileURLToPath(new URL("./package.json", import.meta.url)), "utf8"),
) as { dependencies?: Record<string, string> };
const lockedVersion = (name: string): string =>
  lockFile.packages?.[`node_modules/${name}`]?.version ??
  (manifest.dependencies?.[name] || "unknown").replace(/^[\^~]/, "");

export default defineConfig({
  plugins: [react()],
  define: {
    __PLATFORM_VERSION__: JSON.stringify(platformVersion),
    __REACT_VERSION__: JSON.stringify(lockedVersion("react")),
    __ANTD_VERSION__: JSON.stringify(lockedVersion("antd")),
  },
  build: {
    // The runtime stage serves web-ui/dist at / (nginx.conf); content-hash
    // filenames make the hashed assets immutable-cacheable while index.html
    // stays no-store (SPEC-023 R-1).
    outDir: "../dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      // Local development convenience: `npm run dev` proxies the gateway
      // API through the Vite dev server (port-forward platform-gateway
      // to localhost:8080, or point this at any gateway).
      "/api": "http://localhost:8080",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
