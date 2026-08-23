// ModelSelect tests (SPEC-024 R-4, D-7): the composer selector renders
// from the credential-gated catalog, hides on fetch failure, collapses
// to a fixed label for a single configured model, and propagates the
// operator's choice through onChange.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
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

function catalogOf(
  ids: [string, string][],
  defaultId: string | null = null,
): ModelCatalogResponse {
  return {
    models: ids.map(([id, label], index) => ({
      id,
      label,
      provider: "deepseek",
      default: defaultId ? id === defaultId : index === 0,
    })),
    default: defaultId ?? ids[0]?.[0] ?? null,
  };
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
        catalog={catalogOf([["deepseek-chat", "DeepSeek Chat"]])}
        value="deepseek-chat"
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("DeepSeek Chat")).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("renders a select with every catalog entry and propagates onChange", () => {
    let chosen: string | null = null;
    const { container } = render(
      <ModelSelect
        catalog={catalogOf([
          ["deepseek-chat", "DeepSeek Chat"],
          ["glm-4.6", "GLM 4.6"],
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
    fireEvent.click(screen.getByText("GLM 4.6"));
    expect(chosen).toBe("glm-4.6");
  });

  it("falls back to the first catalog entry when the value is unknown", () => {
    const { container } = render(
      <ModelSelect
        catalog={catalogOf([
          ["deepseek-chat", "DeepSeek Chat"],
          ["glm-4.6", "GLM 4.6"],
        ])}
        value="retired-model"
        onChange={() => {}}
      />,
    );
    expect(
      container.querySelector(".ant-select-content")?.textContent,
    ).toContain("DeepSeek Chat");
  });
});
