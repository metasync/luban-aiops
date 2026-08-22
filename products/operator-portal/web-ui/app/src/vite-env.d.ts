/// <reference types="vite/client" />

// SPEC-023 R-1: injected at build time from the root VERSION file by
// vite.config.ts; asserted by make validate-version.
declare const __PLATFORM_VERSION__: string;
