// Skills inventory view tests (SPEC-052 R-2): a per-row View action that
// lazily fetches the single-skill detail (the list omits body by contract) and
// opens the read-only content viewer. The API client is mocked; the gateway
// re-enforces skills:read server-side regardless of these client gates.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillsView from "../SkillsView";

const { mockRequestJson } = vi.hoisted(() => ({ mockRequestJson: vi.fn() }));

vi.mock("../../../api/client", () => ({
  requestJson: mockRequestJson,
}));

const LIST = {
  skills: [
    {
      skill_id: "sre-alerting/reset-password",
      title: "Reset password",
      source_id: "sre-alerting",
      tags: ["browser"],
      version: "1.0.0",
      updated_at: "2026-09-01T00:00:00Z",
    },
    {
      skill_id: "sre-alerting/kubepodnotready",
      title: "KubePodNotReady",
      source_id: "sre-alerting",
      tags: ["k8s"],
      version: "1.2.0",
      updated_at: "2026-09-02T00:00:00Z",
    },
  ],
  total: 2,
};

const DETAIL = {
  skill_id: "sre-alerting/reset-password",
  title: "Reset password",
  source_id: "sre-alerting",
  version: "1.0.0",
  tags: ["browser"],
  body: "# Steps\n\nClick **Confirm reset**.",
};

beforeEach(() => {
  mockRequestJson.mockReset();
  mockRequestJson.mockResolvedValue(LIST);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SkillsView content viewer (SPEC-052 R-2)", () => {
  it("renders a View control per skill row", async () => {
    render(<SkillsView />);
    await waitFor(() => expect(screen.getByText("Reset password")).toBeTruthy());
    expect(screen.getByLabelText("View Reset password")).toBeTruthy();
    expect(screen.getByLabelText("View KubePodNotReady")).toBeTruthy();
  });

  it("fetches the detail only when View is invoked, then opens the viewer", async () => {
    render(<SkillsView />);
    await waitFor(() => expect(screen.getByText("Reset password")).toBeTruthy());
    // Only the list fetch so far — no row bodies were pulled eagerly.
    expect(mockRequestJson).toHaveBeenCalledTimes(1);
    expect(String(mockRequestJson.mock.calls[0][0])).toContain("/api/v1/skills?");

    mockRequestJson.mockResolvedValueOnce(DETAIL);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("View Reset password"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("skill-content-body")).toBeTruthy(),
    );

    // Exactly one detail call, to the namespaced path (slashes preserved).
    const detailCall = mockRequestJson.mock.calls.find((call) =>
      String(call[0]).includes("reset-password"),
    );
    expect(detailCall?.[0]).toBe("/api/v1/skills/sre-alerting/reset-password");
    expect(mockRequestJson).toHaveBeenCalledTimes(2);
  });

  it("surfaces an error inline and does not open the viewer on failure", async () => {
    render(<SkillsView />);
    await waitFor(() => expect(screen.getByText("Reset password")).toBeTruthy());
    mockRequestJson.mockRejectedValueOnce(new Error("skills hub unavailable"));
    await act(async () => {
      fireEvent.click(screen.getByLabelText("View Reset password"));
    });
    await waitFor(() =>
      expect(screen.getByText(/skills hub unavailable/)).toBeTruthy(),
    );
    expect(screen.queryByTestId("skill-content-body")).toBeNull();
  });
});
