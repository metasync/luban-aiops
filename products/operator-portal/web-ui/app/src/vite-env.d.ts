/// <reference types="vite/client" />

// SPEC-023 R-1: injected at build time from the root VERSION file by
// vite.config.ts; asserted by make validate-version.
declare const __PLATFORM_VERSION__: string;

// v0.23.4: locked tech-stack versions injected at build time for the
// Settings platform inventory.
declare const __REACT_VERSION__: string;
declare const __ANTD_VERSION__: string;
