// ModelSelect tests (SPEC-024 R-4, D-7; SPEC-026 R-2): the composer
// selector renders from the credential-gated catalog, hides on fetch
// failure, collapses to a fixed label for a single configured model,
// groups multi-provider series, and propagates the operator's choice
// through onChange.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import type { ModelCatalogResponse } from "../../api/models";
import { ModelSelect } from "../ModelSelect";

// jsdom lacks matchMedia/ResizeObserver, which rc-select (antd Select)
// probes during render; shim them so the multi-entry branch mounts.
beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
  if (!(window as unknown as { ResizeObserver?: unknown }).ResizeObserver) {
    class ResizeObserverShim {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver =
      ResizeObserverShim;
  }
});

// Vitest globals are off, so testing-library's auto-cleanup never registers;
// unmount explicitly so each render's antd Select dropdown portal (mounted into
// document.body on demand) does not leak into the next test's queries.
afterEach(() => {
  cleanup();
});

function catalogOf(
  ids: [string, string, string?][],
  defaultId: string | null = null,
  routingAvailable = false,
): ModelCatalogResponse {
  return {
    models: ids.map(([id, label, provider], index) => ({
      id,
      label,
      provider: provider ?? "deepseek",
      default: defaultId ? id === defaultId : index === 0,
    })),
    default: defaultId ?? ids[0]?.[0] ?? null,
    routing_available: routingAvailable,
  };
}

// A two-provider catalog so the multi-entry dropdown branch always mounts.
const TWO_PROVIDER_CATALOG: [string, string, string?][] = [
  ["deepseek-chat", "deepseek-chat", "deepseek"],
  ["qwen-plus", "qwen-plus", "dashscope"],
];

function openDropdown(container: HTMLElement) {
  fireEvent.mouseDown(
    container.querySelector(".ant-select-content") as HTMLElement,
  );
}

describe("ModelSelect", () => {
  it("renders nothing when the catalog is unavailable (fetch failure)", () => {
    const { container } = render(
      <ModelSelect catalog={null} value={null} onChange={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing for an empty catalog (unconfigured runtime)", () => {
    const { container } = render(
      <ModelSelect
        catalog={{ models: [], default: null }}
        value={null}
        onChange={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows a fixed label when exactly one model is configured", () => {
    render(
      <ModelSelect
        catalog={catalogOf([["deepseek-v4-flash", "deepseek-v4-flash"]])}
        value="deepseek-v4-flash"
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("deepseek-v4-flash")).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("renders a select with every catalog entry and propagates onChange", () => {
    let chosen: string | null = null;
    const { container } = render(
      <ModelSelect
        catalog={catalogOf([
          ["deepseek-chat", "deepseek-chat"],
          ["deepseek-reasoner", "deepseek-reasoner"],
        ])}
        value="deepseek-chat"
        onChange={(id) => {
          chosen = id;
        }}
      />,
    );

    fireEvent.mouseDown(
      container.querySelector(".ant-select-content") as HTMLElement,
    );
    fireEvent.click(screen.getByText("deepseek-reasoner"));
    expect(chosen).toBe("deepseek-reasoner");
  });

  it("groups multi-provider series under provider labels (SPEC-026)", () => {
    const { container } = render(
      <ModelSelect
        catalog={catalogOf(
          [
            ["deepseek-v4-flash", "deepseek-v4-flash", "deepseek"],
            ["deepseek-chat", "deepseek-chat", "deepseek"],
            ["qwen-plus", "qwen-plus", "dashscope"],
            ["qwen3-max", "qwen3-max", "dashscope"],
          ],
          "deepseek-v4-flash",
        )}
        value="deepseek-v4-flash"
        onChange={() => {}}
      />,
    );
    // Open the dropdown: options and group labels mount on demand.
    fireEvent.mouseDown(
      container.querySelector(".ant-select-content") as HTMLElement,
    );
    // Every model name is an option; both providers render as groups.
    expect(screen.getByText("qwen3-max")).toBeTruthy();
    expect(screen.getAllByText("deepseek").length).toBeGreaterThan(0);
    expect(screen.getAllByText("dashscope").length).toBeGreaterThan(0);
  });

  it("falls back to the default entry when the value is unknown", () => {
    const { container } = render(
      <ModelSelect
        catalog={catalogOf(
          [
            ["deepseek-chat", "deepseek-chat"],
            ["qwen-plus", "qwen-plus", "dashscope"],
          ],
          "qwen-plus",
        )}
        value="retired-model"
        onChange={() => {}}
      />,
    );
    expect(
      container.querySelector(".ant-select-content")?.textContent,
    ).toContain("qwen-plus");
  });

  // --- SPEC-072 R-3: the "Auto (routed)" sentinel choice ---

  it("offers 'Auto (routed)' only when routing is available", () => {
    const { container } = render(
      <ModelSelect
        catalog={catalogOf(TWO_PROVIDER_CATALOG, "deepseek-chat", true)}
        value="deepseek-chat"
        onChange={() => {}}
      />,
    );
    openDropdown(container);
    expect(screen.getByText("Auto (routed)")).toBeTruthy();
  });

  it("omits 'Auto (routed)' when routing is unavailable (byte-identical to v0.52.0)", () => {
    const { container } = render(
      <ModelSelect
        catalog={catalogOf(TWO_PROVIDER_CATALOG, "deepseek-chat", false)}
        value="deepseek-chat"
        onChange={() => {}}
      />,
    );
    openDropdown(container);
    expect(screen.queryByText("Auto (routed)")).toBeNull();
  });

  it("renders a dropdown (not the fixed label) for a single model when routing is available", () => {
    render(
      <ModelSelect
        catalog={catalogOf(
          [["deepseek-v4-flash", "deepseek-v4-flash"]],
          null,
          true,
        )}
        value="deepseek-v4-flash"
        onChange={() => {}}
      />,
    );
    // One model + Auto = two choices, so the fixed-label shortcut yields to a Select.
    expect(screen.queryByRole("combobox")).toBeTruthy();
  });

  it("propagates onChange('auto') when 'Auto (routed)' is chosen", () => {
    let chosen: string | null = null;
    const { container } = render(
      <ModelSelect
        catalog={catalogOf(TWO_PROVIDER_CATALOG, "deepseek-chat", true)}
        value="deepseek-chat"
        onChange={(id) => {
          chosen = id;
        }}
      />,
    );
    openDropdown(container);
    fireEvent.click(screen.getByText("Auto (routed)"));
    expect(chosen).toBe("auto");
  });

  it("shows 'Auto (routed)' as selected when the session is pinned to 'auto'", () => {
    const { container } = render(
      <ModelSelect
        catalog={catalogOf(TWO_PROVIDER_CATALOG, "deepseek-chat", true)}
        value="auto"
        onChange={() => {}}
      />,
    );
    // The collapsed selector reflects the pinned sentinel, not the default.
    expect(
      container.querySelector(".ant-select-content")?.textContent,
    ).toContain("Auto (routed)");
  });
});
