// Approvals view layout tests (SPEC-034 R-3/R-4/R-5): Pending/History
// tabs with counts, separated entries with structured provenance headers,
// and the expiry rule in the banner. SPEC-036 R-5: the History tab is
// server-paged, so pagination tests render the view through a harness
// that simulates the offset refetch.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import type { ConfirmationRecord } from "../../../api/sessions";
import ApprovalsView, {
  type ApprovalsInboxState,
} from "../ApprovalsView";

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }));
vi.mock("../../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));

// jsdom lacks matchMedia, which antd's Pagination probes through the
// responsive observer; shim it so the pager mounts (SPEC-035 R-7).
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
});

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
  // SPEC-036 R-5: pending arrives complete while history is a server
  // page; the fixture derives both from one record list.
  const pending = records.filter((record) => record.status === "pending");
  const history = records.filter((record) => record.status !== "pending");
  return {
    pending,
    history,
    historyTotal: history.length,
    historyOffset: 0,
    loading: false,
    error: null,
    pendingCount: pending.length,
    busyConfirmId: null,
    refresh: vi.fn(async () => {}),
    setPageOffset: vi.fn(),
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

describe("ApprovalsView banner (SPEC-034 R-5 / SPEC-035 R-6)", () => {
  it("states the pending-request expiry rule and default timeout", () => {
    const { container } = render(
      <ApprovalsView inbox={inboxOf([pendingRecord])} />,
    );
    const text = (container.textContent ?? "").replace(/\s+/g, " ");
    expect(text).toContain("unanswered requests expire");
    expect(text).toContain("10 minutes by default");
    expect(text).toContain("History keeps decisions for 30 days");
  });

  it("renders the banner on its own line under the title row", () => {
    // SPEC-035 R-6: the title row keeps only the heading and the Refresh
    // button; the info text is a block-level sibling below it.
    render(<ApprovalsView inbox={inboxOf([pendingRecord])} />);
    const banner = screen.getByText(/unanswered requests expire/);
    expect((banner as HTMLElement).style.display).toBe("block");
    const titleRow = screen
      .getByRole("button", { name: "Refresh inbox" })
      .closest("div");
    expect(titleRow?.contains(banner)).toBe(false);
  });
});

// SPEC-035 R-7 / SPEC-036 R-5: the 30-day history paginates so the tab
// stays legible — server-side now, so page navigation refetches the
// requested offset instead of slicing a local list.
function historyRecordOf(index: number): ConfirmationRecord {
  return {
    ...historyRecord,
    confirm_id: `cf-h-${index}`,
    session_title: `Session ${index}`,
  };
}

// Simulates the hook's offset-aware refetch: page navigation swaps the
// history prop for the requested server page.
function ServerPagedHarness({
  records,
}: {
  records: ConfirmationRecord[];
}) {
  const [offset, setOffset] = useState(0);
  return (
    <ApprovalsView
      inbox={{
        pending: [],
        history: records.slice(offset, offset + 10),
        historyTotal: records.length,
        historyOffset: offset,
        loading: false,
        error: null,
        pendingCount: 0,
        busyConfirmId: null,
        refresh: vi.fn(async () => {}),
        setPageOffset: setOffset,
        decide: vi.fn(async () => {}),
      }}
    />
  );
}

describe("ApprovalsView history pagination (SPEC-035 R-7 / SPEC-036 R-5)", () => {
  it("shows ten entries per page with a pager past one page", () => {
    const records = Array.from({ length: 23 }, (_, index) =>
      historyRecordOf(index),
    );
    const { container } = render(<ServerPagedHarness records={records} />);
    fireEvent.click(screen.getByText("History (23)"));
    expect(screen.getAllByText(/^Session \d+$/)).toHaveLength(10);
    expect(container.querySelector(".ant-pagination")).toBeTruthy();
  });

  it("refetches the requested offset page and clamps a short tail", () => {
    const records = Array.from({ length: 23 }, (_, index) =>
      historyRecordOf(index),
    );
    const { container } = render(<ServerPagedHarness records={records} />);
    fireEvent.click(screen.getByText("History (23)"));
    const pageThree = container.querySelector('li[title="3"]');
    expect(pageThree).toBeTruthy();
    fireEvent.click(pageThree as HTMLElement);
    expect(screen.getAllByText(/^Session \d+$/)).toHaveLength(3);
  });

  it("hides the pager when the history fits on one page", () => {
    const records = Array.from({ length: 10 }, (_, index) =>
      historyRecordOf(index),
    );
    const { container } = render(<ServerPagedHarness records={records} />);
    fireEvent.click(screen.getByText("History (10)"));
    expect(screen.getAllByText(/^Session \d+$/)).toHaveLength(10);
    expect(container.querySelector(".ant-pagination")).toBeNull();
  });
});
