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

// SPEC-036 R-3 shape: the pending queue and the (server-paginated)
// history page arrive as separate arrays plus the retention total.
function inboxPayload(
  confirmations: ConfirmationRecord[],
  history: ConfirmationRecord[] = [],
  historyTotal?: number,
) {
  return {
    confirmations,
    history,
    history_total: historyTotal ?? history.length,
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
    mockGetInbox.mockResolvedValue(
      inboxPayload(
        [recordOf()],
        [
          recordOf({
            confirm_id: "cf-0",
            status: "approved",
            decider_user_id: "luban-approver",
            decision: "approve",
            decided_at: "2026-08-24T09:00:00Z",
            parked_at: "2026-08-24T08:00:00Z",
          }),
        ],
      ),
    );

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
    mockGetInbox.mockResolvedValue(inboxPayload([], []));
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
    mockGetInbox
      .mockResolvedValueOnce(inboxPayload([pending]))
      .mockResolvedValue(inboxPayload([], [approved]));
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
    mockGetInbox.mockResolvedValue(inboxPayload([recordOf()]));
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
    mockGetInbox.mockResolvedValue(
      inboxPayload(
        [recordOf(), recordOf({ confirm_id: "cf-2" })],
        [recordOf({ confirm_id: "cf-0", status: "denied" })],
      ),
    );
    const { result } = renderHook(() => useApprovalsInbox(true));
    await waitFor(() => {
      expect(result.current.pendingCount).toBe(2);
    });
  });

  it("stays idle and makes no requests when disabled (non-decider)", async () => {
    const { result } = renderHook(() => useApprovalsInbox(false));
    expect(result.current.pending).toEqual([]);
    expect(result.current.history).toEqual([]);
    expect(result.current.pendingCount).toBe(0);
    // Give any stray effect a tick; the disabled hook never fetches.
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(mockGetInbox).not.toHaveBeenCalled();
  });

  it("keeps the last good list when a poll fails", async () => {
    mockGetInbox
      .mockResolvedValueOnce(inboxPayload([recordOf()]))
      .mockRejectedValueOnce(new Error("gateway 502"));
    const { result } = renderHook(() => useApprovalsInbox(true));
    await waitFor(() => {
      expect(result.current.pending).toHaveLength(1);
    });
    await result.current.refresh();
    // React 19 flushes the hook's error state asynchronously after the
    // rejected refresh settles; observe it through waitFor.
    await waitFor(() => {
      expect(result.current.error).toContain("gateway 502");
    });
    expect(result.current.pending).toHaveLength(1);
  });

  // SPEC-036 R-5: page navigation refetches with the new offset.
  it("forwards the page offset to the inbox API", async () => {
    mockGetInbox.mockResolvedValue(inboxPayload([], [], 25));
    const { result } = renderHook(() => useApprovalsInbox(true));
    await waitFor(() => {
      expect(result.current.historyTotal).toBe(25);
    });
    result.current.setPageOffset(20);
    await waitFor(() => {
      expect(result.current.historyOffset).toBe(20);
    });
    expect(mockGetInbox).toHaveBeenLastCalledWith(
      expect.objectContaining({ historyLimit: 10, historyOffset: 20 }),
    );
  });

  // SPEC-036 R-5: a decision leaves the pending queue and appears on
  // the first history page immediately, ahead of the server resync.
  it("moves a decided record onto the first history page", async () => {
    // The resync refresh after the decision stays in flight (never
    // resolves) so the test observes the optimistic move alone — the
    // server truth takes over only once the durable store settles.
    mockGetInbox
      .mockResolvedValueOnce(inboxPayload([recordOf()], [], 0))
      .mockReturnValueOnce(new Promise(() => {}));
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
    const { result } = renderHook(() => useApprovalsInbox(true));
    await waitFor(() => {
      expect(result.current.pendingCount).toBe(1);
    });
    await result.current.decide("cf-1", "approve");
    // React 19 flushes the move asynchronously after decide settles.
    await waitFor(() => {
      expect(result.current.pendingCount).toBe(0);
    });
    expect(result.current.history[0]?.confirm_id).toBe("cf-1");
    expect(result.current.history[0]?.status).toBe("approved");
    expect(result.current.historyTotal).toBe(1);
  });
});
