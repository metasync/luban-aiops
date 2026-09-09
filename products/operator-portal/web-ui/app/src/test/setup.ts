import { afterAll, afterEach, vi } from "vitest";
import { act } from "@testing-library/react";

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

// antd responsive components (Tabs/Grid breakpoint hooks) register a
// matchMedia listener, which jsdom does not provide. The stub reports a
// static non-matching media query — tests assert rendered DOM, not
// breakpoints (SPEC-046 R-5).
if (typeof window.matchMedia === "undefined") {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

// React 19 + jsdom teardown race. React's scheduler defers root work to a
// macrotask (`setImmediate` — jsdom offers no MessageChannel) and antd's
// rc-motion advances an animated dialog's enter step over several animation
// frames, so a test that opens one (the shared skill-draft preview, any
// Modal/Drawer, an imperative toast) can still have a scheduler task queued
// when it finishes. Vitest destroys the file's jsdom environment on worker
// hand-off, that task then fires against a deleted `window`, and React's
// `performWorkOnRootViaSchedulerTask` throws `ReferenceError: window is not
// defined` reading `window.event`. Vitest reports it as an uncaught exception
// attributed to whichever file the *worker* runs next — so a suite in which
// every test passed still exits non-zero, and the blame lands on an unrelated
// file. Draining after each test, while the environment is alive and `act` is
// still legal, empties the queue instead of leaving it to outlive the file.
// Per file is not enough: the task is queued per test, and an `afterAll` drain
// runs outside a test, where flushing React work produces a wall of
// "not wrapped in act" warnings and still loses the race.
//
// The count is a **ceiling**, not a tuned constant. rc-motion advances an
// enter transition one step per frame, so one iteration covers one step of
// choreography; three covers a plain dialog plus margin. The frame and the
// immediate are interleaved rather than batched (all frames, then one
// immediate) because work drained by the immediate — a React commit — can
// itself queue the next frame, which a trailing immediate would leave behind.
// If a future test chains a longer transition (a nested modal, a multi-step
// enter) and the suite starts exiting non-zero with `window is not defined`
// blamed on an unrelated file, that is this ceiling being exceeded: raise it
// here rather than adding a per-file drain.
const DRAIN_ITERATIONS = 3;

afterEach(async () => {
  // `act` needs this flag, but it must not be left set: React's dev build
  // warns on *every* state update that lands outside `act` while it is true,
  // and this suite has always run with it unset between RTL's own calls (an
  // async mock resolving after a test's `act` block would otherwise print a
  // wall of "not wrapped in act" against tests that are correct as written).
  // Scope it to the drain and put back whatever RTL left.
  const environment = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const previous = environment.IS_REACT_ACT_ENVIRONMENT;
  environment.IS_REACT_ACT_ENVIRONMENT = true;
  try {
    await act(async () => {
      for (let iteration = 0; iteration < DRAIN_ITERATIONS; iteration += 1) {
        await new Promise((resolve) => requestAnimationFrame(resolve));
        await new Promise((resolve) => setImmediate(resolve));
      }
    });
  } finally {
    environment.IS_REACT_ACT_ENVIRONMENT = previous;
  }
});

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
