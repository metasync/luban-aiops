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
