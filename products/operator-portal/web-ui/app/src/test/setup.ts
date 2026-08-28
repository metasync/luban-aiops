import { afterAll, vi } from "vitest";

// Vitest jsdom setup: antd components that measure their layout (Tabs via
// rc-resize-observer) need a ResizeObserver, which jsdom does not provide.
// The stub observes nothing — tests assert rendered DOM, not geometry.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver =
    ResizeObserverStub as unknown as typeof ResizeObserver;
}

// SPEC-042 R-2: zero-tolerance antd deprecation regression guard. Any
// `[antd: …] … deprecated` console warning emitted during the run fails
// the suite at teardown with the offending text, so new deprecations
// surface at the pull that introduces them instead of accumulating
// silently. Non-deprecation console output passes through untouched.
const antdDeprecations: string[] = [];
// Covers both antd emission modes: the standard per-component warning
// (`Warning: [antd: Alert] \`message\` is deprecated …`) and the
// aggregated batch emitted when a ConfigProvider sets
// `warning={{ strict: false }}` (`[antd] There exists deprecated usage
// in your code:`). The optional component segment keeps the strict-mode
// escape hatch from silently defeating the guard.
const DEPRECATION_PATTERN = /\[antd(?:: .+)?\].*deprecated/i;

const recordDeprecation =
  (forward: (...args: unknown[]) => void) =>
  (...args: unknown[]) => {
    const text = args
      .map((arg) => (typeof arg === "string" ? arg : String(arg)))
      .join(" ");
    if (DEPRECATION_PATTERN.test(text)) {
      antdDeprecations.push(text);
      return;
    }
    forward(...args);
  };

// Capture the originals before spying so forwarded output never recurses
// into the spies.
const originalError = console.error;
const originalWarn = console.warn;

vi.spyOn(console, "error").mockImplementation(
  recordDeprecation(originalError) as typeof console.error,
);
vi.spyOn(console, "warn").mockImplementation(
  recordDeprecation(originalWarn) as typeof console.warn,
);

afterAll(() => {
  if (antdDeprecations.length > 0) {
    const unique = [...new Set(antdDeprecations)];
    throw new Error(
      `SPEC-042 R-2 antd deprecation regression guard: the suite emitted ` +
        `${antdDeprecations.length} antd deprecation warning(s) — migrate ` +
        `the offending call site(s) to the non-deprecated API:\n` +
        unique.map((warning) => `  - ${warning}`).join("\n"),
    );
  }
});
