// ComposerSelectionBar tests: the selection strip under the message
// input collapses when the catalog is unavailable, hosts the fixed
// model label for a single configured model, and propagates the
// operator's choice from the multi-model select.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import type { ModelCatalogResponse } from "../../api/models";
import { ComposerSelectionBar } from "../ComposerSelectionBar";

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

describe("ComposerSelectionBar", () => {
  it("collapses when the catalog is unavailable (fetch failure)", () => {
    const { container } = render(
      <ComposerSelectionBar
        catalog={null}
        model={null}
        onModelChange={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("collapses for an empty catalog (unconfigured runtime)", () => {
    const { container } = render(
      <ComposerSelectionBar
        catalog={{ models: [], default: null }}
        model={null}
        onModelChange={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("labels the strip and shows the fixed label for one model", () => {
    const { container } = render(
      <ComposerSelectionBar
        catalog={catalogOf([["deepseek-chat", "DeepSeek Chat"]])}
        model="deepseek-chat"
        onModelChange={() => {}}
      />,
    );
    expect(
      container.querySelector(".composer-selection-bar"),
    ).toBeTruthy();
    expect(screen.getByText("Model")).toBeTruthy();
    expect(screen.getByText("DeepSeek Chat")).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("hosts the select and propagates the operator's choice", () => {
    let chosen: string | null = null;
    const { container } = render(
      <ComposerSelectionBar
        catalog={catalogOf([
          ["deepseek-chat", "DeepSeek Chat"],
          ["glm-4.6", "GLM 4.6"],
        ])}
        model="deepseek-chat"
        onModelChange={(id) => {
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
});
