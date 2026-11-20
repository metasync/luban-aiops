// SPEC-079 R-1/R-2/R-3: transpose only the presentation of the server-scoped
// matrix. Exercise the real antd table; shared test setup supplies matchMedia.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PermissionsView from "../PermissionsView";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const globalStyles = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "../../../theme/global.css"),
  "utf8",
);

const { mockRequestJson } = vi.hoisted(() => ({ mockRequestJson: vi.fn() }));
vi.mock("../../../api/client", () => ({ requestJson: mockRequestJson }));

const PAYLOAD = {
  version: "3",
  source: "fixture-bundle",
  scope: "all",
  actions: ["chat", "tools:mutate", "policy:read", "tools:read"],
  roles: ["operator", "platform-admin", "read-only-observer"],
  matrix: {
    operator: { chat: true, "tools:mutate": false, "policy:read": true, "tools:read": true },
    "platform-admin": { chat: true, "tools:mutate": true, "policy:read": true, "tools:read": true },
    "read-only-observer": { chat: true, "tools:mutate": false, "policy:read": true },
  },
  approval_requirements: {
    operator: {
      "tools:mutate": { tier: "tier_2", decided_by_roles: ["approver", "platform-admin"], rule_id: "two" },
    },
    "platform-admin": {
      "tools:mutate": { tier: "tier_1", decided_by_roles: ["platform-admin"], rule_id: "one" },
    },
  },
};

beforeEach(() => {
  mockRequestJson.mockReset();
  mockRequestJson.mockResolvedValue(structuredClone(PAYLOAD));
});

afterEach(() => cleanup());

async function openMatrix() {
  render(<PermissionsView />);
  return screen.findByRole("table");
}

function rowCells(table: HTMLElement, action: string) {
  const label = within(table).getByRole("cell", { name: action });
  const row = label.closest("tr")!;
  expect(row.dataset.rowKey).toBe(action);
  return within(row).getAllByRole("cell");
}

describe("PermissionsView transpose (SPEC-079)", () => {
  it("keeps the request and metadata while rendering every cell at its transposed coordinate", async () => {
    const table = await openMatrix();
    expect(mockRequestJson).toHaveBeenCalledExactlyOnceWith("/api/v1/policy/matrix", {
      signal: expect.any(AbortSignal),
    });
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent))
      .toEqual(["permission", ...PAYLOAD.roles]);
    expect(within(table).getAllByRole("row")).toHaveLength(PAYLOAD.actions.length + 1);

    // Explicit coordinates prevent a swapped-axis lookup from passing merely
    // because some allow/deny tags still appear somewhere in the matrix.
    const expected = [
      ["chat", "allow", "allow", "allow"],
      ["tools:mutate", "approver required", "self-approval", "deny"],
      ["policy:read", "allow", "allow", "allow"],
      ["tools:read", "allow", "allow", "deny"],
    ];
    for (const [action, ...states] of expected) {
      const cells = rowCells(table, action);
      expect(cells.map((cell) => cell.textContent)).toEqual([action, ...states]);
      for (const [index, state] of states.entries()) {
        const color = state === "allow" ? "success" : state === "deny" ? "error" : "warning";
        expect(cells[index + 1].querySelector(`.ant-tag-${color}`)).not.toBeNull();
      }
    }
    expect(screen.getByRole("heading", { name: "Permissions" })).toBeTruthy();
    expect(screen.getByText("Policy bundle v3 · fixture-bundle · scope: all")).toBeTruthy();
    expect(screen.getByText("4 permissions × 3 roles · evaluated from the enforced bundle")).toBeTruthy();
  });

  it.each([
    ["approver required", "deciders: approver, platform-admin"],
    ["self-approval", "deciders: platform-admin"],
  ])("preserves the %s label and designated-deciders tooltip", async (label, tooltip) => {
    await openMatrix();
    fireEvent.mouseEnter(screen.getByText(label));
    expect((await screen.findByRole("tooltip")).textContent).toBe(tooltip);
  });

  it("renders only server-listed role columns, without widening or filtering the payload", async () => {
    // Extra backing-map keys must not become columns; there is no client role gate.
    mockRequestJson.mockResolvedValue({ ...PAYLOAD, scope: "self", roles: ["operator"] });
    const table = await openMatrix();
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent))
      .toEqual(["permission", "operator"]);
    expect(within(table).queryByRole("columnheader", { name: "platform-admin" })).toBeNull();
    expect(rowCells(table, "tools:mutate").map((cell) => cell.textContent))
      .toEqual(["tools:mutate", "approver required"]);
    expect(screen.getByText("4 permissions × 1 role · evaluated from the enforced bundle")).toBeTruthy();
  });

  it("keeps a long permission list in server order without pagination or forced horizontal scrolling", async () => {
    const actions = Array.from({ length: 40 }, (_, index) => `permission:${index}`);
    mockRequestJson.mockResolvedValue({ ...PAYLOAD, actions });
    const table = await openMatrix();
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual(actions);
    expect(rows.every((row) => within(row).getAllByRole("cell").length === 4)).toBe(true);
    expect(table.style.width).not.toBe("max-content");
    expect(table.closest(".ant-table")?.querySelector(".ant-table-body")).toBeNull();
    expect(document.querySelector(".ant-pagination")).toBeNull();
  });

  it("isolates horizontal overflow in a keyboard-accessible matrix region, outside page chrome", async () => {
    const table = await openMatrix();
    const region = screen.getByRole("region", { name: "Permissions matrix" });
    expect(region.classList.contains("permissions-matrix-scroll")).toBe(true);
    expect(region.tabIndex).toBe(0);
    expect(region.contains(table)).toBe(true);
    expect(region.contains(screen.getByRole("heading", { name: "Permissions" }))).toBe(false);
    expect(region.contains(screen.getByText("Policy bundle v3 · fixture-bundle · scope: all"))).toBe(false);
    expect(region.contains(screen.getByText("4 permissions × 3 roles · evaluated from the enforced bundle"))).toBe(false);
    expect(table.style.width).not.toBe("max-content");
    expect(region.querySelector(".ant-table-body")).toBeNull();

    // Load the real CSS so losing containment cannot pass on markup alone.
    // jsdom checks the rule wiring; browser geometry is verified separately.
    expect(globalStyles).toContain(".permissions-matrix-scroll");
    const style = document.createElement("style");
    style.textContent = globalStyles;
    document.head.appendChild(style);
    try {
      const computed = getComputedStyle(region);
      expect(computed.overflowX).toBe("auto");
      expect(computed.maxWidth).toBe("100%");
      expect(["", "none"]).toContain(computed.maxHeight);
      expect(["", "auto"]).toContain(computed.height);
    } finally {
      style.remove();
    }
  });

  it("keeps decorative table shadows inside the matrix without a second vertical scroll range", async () => {
    await openMatrix();
    const region = screen.getByRole("region", { name: "Permissions matrix" });
    const container = region.querySelector(".ant-table-container");
    expect(container).not.toBeNull();

    // Ant's container shadow extends 1px below the table by default. jsdom
    // cannot lay out pseudo-elements; assert the real scoped rule here and
    // verify zero vertical scroll range and PageDown behavior in a browser.
    const style = document.createElement("style");
    style.textContent = globalStyles;
    document.head.appendChild(style);
    try {
      const rules = Array.from(style.sheet!.cssRules).filter(
        (rule): rule is CSSStyleRule => rule.type === CSSRule.STYLE_RULE,
      );
      for (const pseudo of ["::before", "::after"]) {
        const selector = `.permissions-matrix-scroll .ant-table-container${pseudo}`;
        const rule = rules.find((candidate) =>
          candidate.selectorText.split(",").some((part) => part.trim() === selector),
        );
        expect(container!.matches(selector.replace(pseudo, ""))).toBe(true);
        expect(rule?.style.bottom).toBe("0px");
      }
    } finally {
      style.remove();
    }
  });

  it("falls back to boolean allow/deny when optional approval metadata is absent", async () => {
    mockRequestJson.mockResolvedValue({ ...PAYLOAD, approval_requirements: undefined });
    const table = await openMatrix();
    expect(rowCells(table, "tools:mutate").map((cell) => cell.textContent))
      .toEqual(["tools:mutate", "deny", "allow", "deny"]);
    expect(screen.queryByText("approver required")).toBeNull();
  });

  it("keeps the empty matrix metadata and zero-count footer", async () => {
    mockRequestJson.mockResolvedValue({ ...PAYLOAD, roles: [], actions: [], matrix: {} });
    await openMatrix();
    expect(screen.getByRole("columnheader", { name: "permission" })).toBeTruthy();
    expect(screen.getByText("0 permissions × 0 roles · evaluated from the enforced bundle")).toBeTruthy();
  });

  it.each(["403 Forbidden", "502 Bad Gateway"])("preserves the gateway error display for %s", async (message) => {
    mockRequestJson.mockRejectedValue(new Error(message));
    render(<PermissionsView />);
    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(screen.queryByRole("table")).toBeNull();
  });
});
