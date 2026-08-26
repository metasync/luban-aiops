// Approvals view layout tests (SPEC-034 R-3/R-4/R-5): Pending/History
// tabs with counts, separated entries with structured provenance headers,
// and the expiry rule in the banner.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfirmationRecord } from "../../../api/sessions";
import ApprovalsView, {
  type ApprovalsInboxState,
} from "../ApprovalsView";

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }));
vi.mock("../../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));

const pendingRecord: ConfirmationRecord = {
  confirm_id: "cf-pending",
  session_id: "ses-1",
  owner_user_id: "luban-operator",
  session_title: "Restart scratch demo pod",
  pending_calls: [
    { call_id: "c-1", tool_name: "k8s.restart_pod", risk_level: "write" },
  ],
  action: "tools:mutate",
  status: "pending",
  parked_at: new Date(Date.now() - 7 * 60_000).toISOString(),
};

const historyRecord: ConfirmationRecord = {
  confirm_id: "cf-history",
  session_id: "ses-2",
  owner_user_id: "luban-operator",
  session_title: "Old drain-disk session",
  pending_calls: [
    { call_id: "c-2", tool_name: "k8s.delete_pod", risk_level: "write" },
  ],
  action: "tools:mutate",
  status: "approved",
  parked_at: new Date(Date.now() - 60 * 60_000).toISOString(),
  decider_user_id: "luban-approver",
  decision: "approve",
  decided_at: new Date(Date.now() - 55 * 60_000).toISOString(),
};

function inboxOf(records: ConfirmationRecord[]): ApprovalsInboxState {
  return {
    records,
    loading: false,
    error: null,
    pendingCount: records.filter((record) => record.status === "pending")
      .length,
    busyConfirmId: null,
    refresh: vi.fn(async () => {}),
    decide: vi.fn(async () => {}),
  };
}

beforeEach(() => {
  mockUseAuth.mockReset();
  mockUseAuth.mockReturnValue({ roles: ["approver"], username: "luban-approver" });
});

// Vitest globals are off, so testing-library's auto-cleanup never
// registers; unmount explicitly to keep renders isolated.
afterEach(() => {
  cleanup();
});

describe("ApprovalsView tabs (SPEC-034 R-3)", () => {
  it("defaults to Pending and hides history entries", () => {
    render(<ApprovalsView inbox={inboxOf([pendingRecord, historyRecord])} />);
    expect(screen.getByText("Pending (1)")).toBeTruthy();
    expect(screen.getByText("History (1)")).toBeTruthy();
    expect(screen.getByText("Restart scratch demo pod")).toBeTruthy();
    expect(screen.queryByText("Old drain-disk session")).toBeNull();
  });

  it("shows decided entries only after switching to History", () => {
    render(<ApprovalsView inbox={inboxOf([pendingRecord, historyRecord])} />);
    fireEvent.click(screen.getByText("History (1)"));
    expect(screen.getByText("Old drain-disk session")).toBeTruthy();
  });
});

describe("ApprovalsView entry header (SPEC-034 R-4)", () => {
  it("renders session title, owner, and parked relative time", () => {
    render(<ApprovalsView inbox={inboxOf([pendingRecord])} />);
    expect(screen.getByText("Restart scratch demo pod")).toBeTruthy();
    expect(screen.getByText("owner: luban-operator")).toBeTruthy();
    expect(screen.getByText(/^parked /)).toBeTruthy();
  });

  it("adds outcome and decision attribution for history entries", () => {
    render(<ApprovalsView inbox={inboxOf([historyRecord])} />);
    fireEvent.click(screen.getByText("History (1)"));
    expect(screen.getAllByText("approved").length).toBeGreaterThan(0);
    expect(screen.getByText(/^decided .* by luban-approver$/)).toBeTruthy();
  });
});

describe("ApprovalsView banner (SPEC-034 R-5)", () => {
  it("states the pending-request expiry rule and default timeout", () => {
    const { container } = render(
      <ApprovalsView inbox={inboxOf([pendingRecord])} />,
    );
    const text = (container.textContent ?? "").replace(/\s+/g, " ");
    expect(text).toContain("unanswered requests expire");
    expect(text).toContain("10 minutes by default");
    expect(text).toContain("History keeps decisions for 30 days");
  });
});
