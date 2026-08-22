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

export default defineConfig({
  plugins: [react()],
  define: {
    __PLATFORM_VERSION__: JSON.stringify(platformVersion),
  },
  // Coexistence serving path (nginx.conf): the compiled SPA ships at /next/
  // until stage 6 flips the runtime root to the hashed bundle.
  base: "/next/",
  build: {
    // The runtime stage serves web-ui/dist; content-hash filenames make
    // the hashed assets immutable-cacheable while index.html stays
    // no-store (nginx.conf, SPEC-023 R-1).
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
    // Stage-1 scaffolding has no suites yet; the SSE adapter tests land
    // in stage 2.
    passWithNoTests: true,
  },
});
