// Approvals view tests (SPEC-031 R-5): the decider's inbox renders
// pending items on the default Pending tab with history on its own tab,
// decides through the shared confirm surface, and flips race-losers to
// the winner's outcome on the structured already_resolved 409.
import {
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfirmationRecord } from "../../api/sessions";
import ApprovalsView, { useApprovalsInbox } from "../control/ApprovalsView";

const { mockUseAuth, mockGetInbox, mockOpenStream, mockConsumeStream } =
  vi.hoisted(() => ({
    mockUseAuth: vi.fn(),
    mockGetInbox: vi.fn(),
    mockOpenStream: vi.fn(),
    mockConsumeStream: vi.fn(),
  }));

vi.mock("../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));
vi.mock("../../api/approvals", () => ({ getApprovalsInbox: mockGetInbox }));
// Keep StreamOpenError and alreadyResolvedDetail real; only the network
// surface is stubbed.
vi.mock("../../stream/transport", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../stream/transport")>();
  return {
    ...actual,
    openStream: mockOpenStream,
    consumeStream: mockConsumeStream,
  };
});

function recordOf(
  overrides: Partial<ConfirmationRecord> = {},
): ConfirmationRecord {
  return {
    confirm_id: "cf-1",
    session_id: "s-1",
    owner_user_id: "luban-operator",
    session_title: "Restart API pods",
    pending_calls: [
      {
        call_id: "c-1",
        tool_name: "k8s.restart_pod",
        parameters: { pod: "api" },
        risk_level: "write",
        action: "tools:mutate",
      },
    ],
    action: "tools:mutate",
    status: "pending",
    parked_at: "2026-08-25T10:00:00Z",
    ...overrides,
  };
}

function Harness() {
  const inbox = useApprovalsInbox(true);
  return <ApprovalsView inbox={inbox} />;
}

beforeEach(() => {
  mockUseAuth.mockReset();
  mockUseAuth.mockReturnValue({
    username: "luban-approver",
    roles: ["approver"],
  });
  mockGetInbox.mockReset();
  mockOpenStream.mockReset();
  mockConsumeStream.mockReset();
});

// Vitest globals are off, so testing-library's auto-cleanup never
// registers; unmount explicitly to keep renders isolated.
afterEach(() => {
  cleanup();
});

describe("ApprovalsView (SPEC-031 R-5)", () => {
  it("keeps pending on the default tab and history on its own tab", async () => {
    mockGetInbox.mockResolvedValue([
      recordOf(),
      recordOf({
        confirm_id: "cf-0",
        status: "approved",
        decider_user_id: "luban-approver",
        decision: "approve",
        decided_at: "2026-08-24T09:00:00Z",
        parked_at: "2026-08-24T08:00:00Z",
      }),
    ]);

    render(<Harness />);

    // Pending card is actionable for a designated approver.
    expect(await screen.findByText("Approve")).toBeTruthy();
    expect(screen.getByText("Deny")).toBeTruthy();
    // SPEC-034 R-3: history stays out of the way until its tab opens.
    expect(screen.queryByText("History (1)")).toBeTruthy();
    expect(
      screen.queryByText(
        "Approved by luban-approver at 2026-08-24T09:00:00Z.",
      ),
    ).toBeNull();

    fireEvent.click(screen.getByText("History (1)"));
    // History card renders read-only with decider attribution.
    expect(
      await screen.findByText(
        "Approved by luban-approver at 2026-08-24T09:00:00Z.",
      ),
    ).toBeTruthy();
    // Provenance stays metadata-only (SPEC-030 Q-1): session, owner, age.
    expect(screen.getAllByText("Restart API pods").length).toBe(2);
    expect(screen.getAllByText("owner: luban-operator").length).toBe(2);
  });

  it("shows the empty states when the inbox has no records", async () => {
    mockGetInbox.mockResolvedValue([]);
    render(<Harness />);
    expect(
      await screen.findByText(
        "No confirmations are waiting for a decision.",
      ),
    ).toBeTruthy();
    fireEvent.click(screen.getByText("History (0)"));
    expect(
      await screen.findByText("No decisions in the last 30 days."),
    ).toBeTruthy();
  });

  it("approves through the confirm stream and resyncs the inbox", async () => {
    const pending = recordOf();
    const approved = recordOf({
      status: "approved",
      decider_user_id: "luban-approver",
      decision: "approve",
      decided_at: "2026-08-25T10:05:00Z",
    });
    mockGetInbox.mockResolvedValueOnce([pending]).mockResolvedValue([approved]);
    mockOpenStream.mockResolvedValue({ requestId: "req-1", chunks: [] });
    mockConsumeStream.mockImplementation(
      async (_chunks: unknown, onEvent: (event: unknown) => void) => {
        onEvent({
          frame: {
            kind: "confirmation_result",
            confirmId: "cf-1",
            status: "approved",
          },
        });
      },
    );

    render(<Harness />);
    fireEvent.click(await screen.findByText("Approve"));

    // The decided record leaves the Pending tab; its attributed card
    // renders on the History tab once opened.
    await waitFor(() => {
      expect(screen.getByText("History (1)")).toBeTruthy();
    });
    fireEvent.click(screen.getByText("History (1)"));
    expect(
      await screen.findByText(
        "Approved by luban-approver at 2026-08-25T10:05:00Z.",
      ),
    ).toBeTruthy();
    // The decision rides the shared confirm surface with the parked ids.
    expect(mockOpenStream).toHaveBeenCalledWith(
      "/api/v1/chat/confirm",
      expect.objectContaining({
        method: "POST",
        body: {
          session_id: "s-1",
          confirm_id: "cf-1",
          decision: "approve",
        },
      }),
    );
    // Refresh re-reads the durable store after the decision settles.
    expect(mockGetInbox).toHaveBeenCalledTimes(2);
  });

  it("flips a race-loser card to the winner's outcome on the 409", async () => {
    const { StreamOpenError } =
      await import("../../stream/transport");
    mockGetInbox.mockResolvedValue([recordOf()]);
    mockOpenStream.mockRejectedValue(
      new StreamOpenError(409, undefined, {
        detail: {
          reason: "already_resolved",
          status: "denied",
          decider_user_id: "luban-admin",
          decision: "deny",
          decided_at: "2026-08-25T10:05:00Z",
        },
      }),
    );

    render(<Harness />);
    fireEvent.click(await screen.findByText("Approve"));

    // The card flips to denied with the winner's attribution instead of
    // staying pending (which would invite a doomed retry); the decided
    // record lands on the History tab.
    await waitFor(() => {
      expect(screen.getByText("History (1)")).toBeTruthy();
    });
    fireEvent.click(screen.getByText("History (1)"));
    expect(
      await screen.findByText("Denied by luban-admin at 2026-08-25T10:05:00Z."),
    ).toBeTruthy();
    expect(screen.getByText("denied")).toBeTruthy();
    expect(screen.queryByText("Approve")).toBeNull();
  });
});

describe("useApprovalsInbox (SPEC-031 R-5)", () => {
  it("exposes the pending count for the sidebar badge", async () => {
    mockGetInbox.mockResolvedValue([
      recordOf(),
      recordOf({ confirm_id: "cf-2" }),
      recordOf({ confirm_id: "cf-0", status: "denied" }),
    ]);
    const { result } = renderHook(() => useApprovalsInbox(true));
    await waitFor(() => {
      expect(result.current.pendingCount).toBe(2);
    });
  });

  it("stays idle and makes no requests when disabled (non-decider)", async () => {
    const { result } = renderHook(() => useApprovalsInbox(false));
    expect(result.current.records).toEqual([]);
    expect(result.current.pendingCount).toBe(0);
    // Give any stray effect a tick; the disabled hook never fetches.
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(mockGetInbox).not.toHaveBeenCalled();
  });

  it("keeps the last good list when a poll fails", async () => {
    mockGetInbox
      .mockResolvedValueOnce([recordOf()])
      .mockRejectedValueOnce(new Error("gateway 502"));
    const { result } = renderHook(() => useApprovalsInbox(true));
    await waitFor(() => {
      expect(result.current.records).toHaveLength(1);
    });
    await result.current.refresh();
    expect(result.current.records).toHaveLength(1);
    expect(result.current.error).toContain("gateway 502");
  });
});
