// SPEC-063 R-5a / F-24 portal proof: bounded, visibility-aware recovery
// polling. While a decided card carries an unsettled execution (available but
// not yet result_recorded), the owner's chat refreshes the detail every two
// seconds for at most 120 seconds, then stops and surfaces refresh guidance.
// It never polls while streaming, never carries a window across a session
// change, keeps the last-good view on transport errors, and stops cleanly once
// a late durable result settles the execution.
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ConfirmationRecord,
  ExecutionRecovery,
  SessionDetail,
} from "../../api/sessions";
import type { ChatTurn } from "../../stream/useChatStream";
import {
  RECOVERY_POLL_INTERVAL_MS,
  RECOVERY_WINDOW_MS,
  useRecoveryPoll,
} from "../useRecoveryPoll";

const { mockGetSession } = vi.hoisted(() => ({
  mockGetSession: vi.fn(),
}));

vi.mock("../../api/sessions", () => ({ getSession: mockGetSession }));

function recoveryOf(
  overrides: Partial<ExecutionRecovery> = {},
): ExecutionRecovery {
  return {
    availability: "available",
    state: "dispatch_claimed",
    execution_id: "exec-1",
    tool_name: "k8s.restart_pod",
    requested_at: "2026-09-24T10:00:00Z",
    observe_by: "2026-09-24T10:02:00Z",
    as_of: "2026-09-24T10:01:00Z",
    replay: false,
    run_stopped: false,
    integrity_conflict: false,
    target_verification_required: true,
    receipt: null,
    observations: [],
    observations_truncated: false,
    next_observation_cursor: null,
    ...overrides,
  };
}

const SETTLED = recoveryOf({
  state: "result_recorded",
  receipt: {
    status: "succeeded",
    completed_at: "2026-09-24T10:01:30Z",
    request_id: "req-9",
  },
});

// A decided turn whose single execution carries `recovery` (undefined → no
// recovery projection at all).
function turnWith(recovery?: ExecutionRecovery): ChatTurn {
  return {
    id: "t-1",
    userMessage: "restart the pod",
    replyText: "Done.",
    completed: true,
    confirmationPending: false,
    toolCalls: [],
    toolResults: [],
    confirmations: [
      {
        confirmId: "cf-1",
        pendingCalls: [],
        mutating: true,
        status: "approved",
        sessionId: "s-1",
        executions:
          recovery === undefined
            ? undefined
            : [
                {
                  executionId: "exec-1",
                  callId: "c-1",
                  toolName: "k8s.restart_pod",
                  status: "requested",
                  recovery,
                },
              ],
      },
    ],
  };
}

function detailWith(recovery?: ExecutionRecovery | null): SessionDetail {
  const record: ConfirmationRecord = {
    confirm_id: "cf-1",
    session_id: "s-1",
    owner_user_id: "luban-operator",
    pending_calls: [],
    status: "approved",
    executions:
      recovery === undefined || recovery === null
        ? []
        : [
            {
              execution_id: "exec-1",
              call_id: "c-1",
              confirm_id: "cf-1",
              session_id: "s-1",
              tool_name: "k8s.restart_pod",
              status: "requested",
              recovery,
            },
          ],
  };
  return {
    session_id: "s-1",
    title: "Restart demo pod",
    created_at: "2026-09-24T09:00:00Z",
    last_active_at: "2026-09-24T10:00:00Z",
    pending_confirmation: false,
    user_id: "luban-operator",
    status: "active",
    session_type: "operation",
    transcript_available: true,
    transcript: [{ role: "user", content: "restart the pod" }],
    confirmations: [record],
  };
}

function renderPoll(options: {
  sessionId?: string | null;
  turns?: ChatTurn[];
  streaming?: boolean;
  executionCursor?: string;
  applyDetail?: (detail: SessionDetail) => void;
}) {
  const applyDetail = options.applyDetail ?? vi.fn();
  return {
    applyDetail,
    ...renderHook(
      (props: {
        sessionId: string | null;
        turns: ChatTurn[];
        streaming: boolean;
        executionCursor?: string;
      }) => useRecoveryPoll({ ...props, applyDetail }),
      {
        initialProps: {
          sessionId: options.sessionId ?? "s-1",
          turns: options.turns ?? [turnWith(recoveryOf())],
          streaming: options.streaming ?? false,
          ...(options.executionCursor ? { executionCursor: options.executionCursor } : {}),
        },
      },
    ),
  };
}

async function tick(times = 1) {
  await act(async () => {
    vi.advanceTimersByTime(RECOVERY_POLL_INTERVAL_MS * times);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  mockGetSession.mockReset();
  Object.defineProperty(document, "visibilityState", {
    configurable: true, value: "visible",
  });
});

afterEach(() => {
  // Vitest globals are off, so unmount explicitly: leftover hooks keep
  // visibility/focus kick listeners that would count into later tests'
  // shared fetch mock.
  cleanup();
  vi.useRealTimers();
});

describe("useRecoveryPoll (SPEC-063 R-5a)", () => {
  it("polls the selected execution page and aborts stale page reads", async () => {
    let resolve: (detail: SessionDetail) => void = () => {};
    mockGetSession.mockImplementationOnce(() => new Promise<SessionDetail>((done) => { resolve = done; }))
      .mockResolvedValue(detailWith(SETTLED));
    const { applyDetail, rerender } = renderPoll({ executionCursor: "page-two" });
    await tick();
    expect(mockGetSession).toHaveBeenLastCalledWith("s-1", expect.any(AbortSignal), { executionCursor: "page-two" });
    const signal = mockGetSession.mock.calls[0][1] as AbortSignal;
    rerender({ sessionId: "s-1", turns: [turnWith(recoveryOf())], streaming: false, executionCursor: "page-three" });
    expect(signal.aborted).toBe(true);
    await act(async () => { resolve(detailWith(SETTLED)); });
    expect(applyDetail).not.toHaveBeenCalled();
    await tick();
    expect(mockGetSession).toHaveBeenLastCalledWith("s-1", expect.any(AbortSignal), { executionCursor: "page-three" });
    expect(applyDetail).toHaveBeenCalledExactlyOnceWith(detailWith(SETTLED));
  });

  it("does not restart an expired automatic window on page changes", async () => {
    mockGetSession.mockResolvedValue(detailWith(recoveryOf()));
    const { rerender, result } = renderPoll({});
    await tick(RECOVERY_WINDOW_MS / RECOVERY_POLL_INTERVAL_MS);
    const before = mockGetSession.mock.calls.length;
    rerender({ sessionId: "s-1", turns: [turnWith(recoveryOf())], streaming: false, executionCursor: "page-two" });
    await tick(3);
    expect(mockGetSession).toHaveBeenCalledTimes(before);
    expect(result.current.recoveryGuidance).toBe(true);
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    expect(mockGetSession).toHaveBeenCalledTimes(before + 1);
    expect(mockGetSession).toHaveBeenLastCalledWith("s-1", expect.any(AbortSignal), { executionCursor: "page-two" });
  });

  it("applies a late result on the very first refresh", async () => {
    mockGetSession.mockResolvedValue(detailWith(SETTLED));
    const { applyDetail } = renderPoll({});
    await tick();
    expect(applyDetail).toHaveBeenCalledExactlyOnceWith(detailWith(SETTLED));
    await tick();
    expect(applyDetail).toHaveBeenCalledTimes(1);
  });

  it("does not poll a pending decision card", async () => {
    const turn = turnWith(recoveryOf());
    turn.confirmations[0].status = "pending";
    renderPoll({ turns: [turn] });
    await tick(3);
    expect(mockGetSession).not.toHaveBeenCalled();
  });

  it("never fetches while hidden, including focus events", async () => {
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    const { result } = renderPoll({});
    await tick(3);
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    expect(mockGetSession).not.toHaveBeenCalled();
    expect(result.current.recoveryPolling).toBe(false);
  });

  it("refreshes once after the window expires without restarting its timer", async () => {
    mockGetSession.mockResolvedValue(detailWith(recoveryOf()));
    const { result, applyDetail } = renderPoll({});
    await tick(RECOVERY_WINDOW_MS / RECOVERY_POLL_INTERVAL_MS);
    expect(result.current.recoveryGuidance).toBe(true);
    const before = mockGetSession.mock.calls.length;
    mockGetSession.mockResolvedValue(detailWith(SETTLED));
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(mockGetSession).toHaveBeenCalledTimes(before + 1);
    expect(applyDetail).toHaveBeenCalledExactlyOnceWith(detailWith(SETTLED));
    await tick(3);
    expect(mockGetSession).toHaveBeenCalledTimes(before + 1);
    expect(result.current.recoveryPolling).toBe(false);
  });

  it("does not overlap a slow request with intervals or foreground kicks", async () => {
    let resolve: (detail: SessionDetail) => void = () => {};
    mockGetSession.mockImplementation(() => new Promise<SessionDetail>((done) => { resolve = done; }));
    const { applyDetail } = renderPoll({});
    await tick(4);
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      window.dispatchEvent(new Event("focus"));
    });
    expect(mockGetSession).toHaveBeenCalledTimes(1);
    await act(async () => { resolve(detailWith(SETTLED)); });
    expect(applyDetail).toHaveBeenCalledTimes(1);
  });

  it("detects stop flags and equal-sized changed observation windows", async () => {
    const fact = { observation_id: "o-1", kind: "duplicate_seen", source: "worker", observed_at: "2026-09-24T10:01:00Z" };
    const initial = recoveryOf({ observations: [fact] });
    const stopped = recoveryOf({ observations: [fact], run_stopped: true });
    const changed = { ...stopped, observations: [{ ...fact, observation_id: "o-2" }] };
    mockGetSession.mockResolvedValueOnce(detailWith(stopped)).mockResolvedValue(detailWith(changed));
    const { applyDetail } = renderPoll({ turns: [turnWith(initial)] });
    await tick();
    await tick();
    expect(applyDetail).toHaveBeenCalledTimes(2);
  });

  it("ignores changes only to the read clock", async () => {
    mockGetSession.mockResolvedValue(detailWith(recoveryOf({ as_of: "2026-09-24T10:01:20Z" })));
    const { applyDetail } = renderPoll({});
    await tick(2);
    expect(applyDetail).not.toHaveBeenCalled();
  });

  it("retains an expired window across stream pauses", async () => {
    mockGetSession.mockResolvedValue(detailWith(recoveryOf()));
    const { result, rerender } = renderPoll({});
    await tick(RECOVERY_WINDOW_MS / RECOVERY_POLL_INTERVAL_MS);
    const before = mockGetSession.mock.calls.length;
    rerender({ sessionId: "s-1", turns: [turnWith(recoveryOf())], streaming: true });
    rerender({ sessionId: "s-1", turns: [turnWith(recoveryOf())], streaming: false });
    await tick(3);
    expect(mockGetSession).toHaveBeenCalledTimes(before);
    expect(result.current.recoveryGuidance).toBe(true);
  });

  it("drops a read completing after unmount or a stream starts", async () => {
    let resolve: (detail: SessionDetail) => void = () => {};
    mockGetSession.mockImplementation(() => new Promise<SessionDetail>((done) => { resolve = done; }));
    const { applyDetail, rerender, unmount } = renderPoll({});
    await tick();
    rerender({ sessionId: "s-1", turns: [turnWith(recoveryOf())], streaming: true });
    await act(async () => { resolve(detailWith(SETTLED)); });
    expect(applyDetail).not.toHaveBeenCalled();
    rerender({ sessionId: "s-1", turns: [turnWith(recoveryOf())], streaming: false });
    await tick();
    unmount();
    await act(async () => { resolve(detailWith(SETTLED)); });
    expect(applyDetail).not.toHaveBeenCalled();
  });

  it("re-seeds when the recovery projection moves, then gates repeats", async () => {
    mockGetSession
      .mockResolvedValueOnce(detailWith(recoveryOf({ state: "dispatch_claimed" })))
      .mockResolvedValue(detailWith(SETTLED));
    const { applyDetail } = renderPoll({});

    // The first response matches the rendered view; nothing is applied.
    await tick();
    expect(mockGetSession).toHaveBeenCalledTimes(1);
    expect(applyDetail).not.toHaveBeenCalled();

    // The next tick sees the moved fingerprint and re-seeds once.
    await tick();
    expect(applyDetail).toHaveBeenCalledTimes(1);

    // An unchanged projection afterwards never re-applies (change gate).
    await tick();
    expect(applyDetail).toHaveBeenCalledTimes(1);
  });

  it("does not poll when every execution is already settled", async () => {
    renderPoll({ turns: [turnWith(SETTLED)] });
    await tick(4);
    expect(mockGetSession).not.toHaveBeenCalled();
  });

  it("does not poll when no execution carries a recovery projection", async () => {
    renderPoll({ turns: [turnWith(undefined)] });
    await tick(4);
    expect(mockGetSession).not.toHaveBeenCalled();
  });

  it("does not poll an unavailable recovery read", async () => {
    renderPoll({
      turns: [turnWith(recoveryOf({ availability: "unavailable", state: null }))],
    });
    await tick(4);
    expect(mockGetSession).not.toHaveBeenCalled();
  });

  it("does not poll while a stream is active", async () => {
    renderPoll({ streaming: true });
    await tick(4);
    expect(mockGetSession).not.toHaveBeenCalled();
  });

  it("stops at the observation window and surfaces refresh guidance", async () => {
    mockGetSession.mockResolvedValue(
      detailWith(recoveryOf({ state: "dispatch_claimed" })),
    );
    const { result } = renderPoll({});
    await tick(); // baseline
    expect(result.current.recoveryPolling).toBe(true);
    expect(result.current.recoveryGuidance).toBe(false);

    // Advance past the 120-second window; the projection never moves, so the
    // window lapses on its own and flips to guidance.
    const ticks = RECOVERY_WINDOW_MS / RECOVERY_POLL_INTERVAL_MS + 1;
    for (let i = 0; i < ticks; i += 1) await tick();
    expect(result.current.recoveryPolling).toBe(false);
    expect(result.current.recoveryGuidance).toBe(true);

    // Polling has stopped: no further fetches.
    const stopped = mockGetSession.mock.calls.length;
    await tick(3);
    expect(mockGetSession.mock.calls.length).toBe(stopped);
  });

  it("ticks immediately when the tab becomes visible again", async () => {
    mockGetSession.mockResolvedValue(
      detailWith(recoveryOf({ state: "dispatch_claimed" })),
    );
    renderPoll({});
    await tick(); // baseline fetch
    const before = mockGetSession.mock.calls.length;

    await act(async () => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: "visible",
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    // No timer advance — the kick alone triggered a refresh.
    expect(mockGetSession.mock.calls.length).toBe(before + 1);
  });

  it("stops polling without guidance once a late result settles", async () => {
    mockGetSession
      .mockResolvedValueOnce(detailWith(recoveryOf({ state: "dispatch_claimed" })))
      .mockResolvedValue(detailWith(SETTLED));
    const applyDetail = vi.fn();
    const { result, rerender } = renderPoll({ applyDetail });

    await tick(); // baseline (claimed)
    await tick(); // late report lands → applied
    expect(applyDetail).toHaveBeenCalledTimes(1);

    // ChatView re-seeds the turns to settled after applying.
    rerender({
      sessionId: "s-1",
      turns: [turnWith(SETTLED)],
      streaming: false,
    });
    expect(result.current.recoveryPolling).toBe(false);
    expect(result.current.recoveryGuidance).toBe(false);

    const after = mockGetSession.mock.calls.length;
    await tick(3);
    expect(mockGetSession.mock.calls.length).toBe(after);
  });

  it("keeps the last-good view on transport errors and retries", async () => {
    mockGetSession
      .mockResolvedValueOnce(detailWith(recoveryOf({ state: "dispatch_claimed" })))
      .mockRejectedValueOnce(new Error("gateway blip"))
      .mockResolvedValue(detailWith(SETTLED));
    const applyDetail = vi.fn();
    renderPoll({ applyDetail });

    await tick(); // baseline
    await tick(); // rejection: nothing applied, no throw escapes
    expect(applyDetail).not.toHaveBeenCalled();
    await tick(); // retry sees the moved state
    expect(applyDetail).toHaveBeenCalledTimes(1);
  });

  it("never applies a response after the session switched", async () => {
    let resolveFirst: (detail: SessionDetail) => void = () => {};
    mockGetSession
      .mockImplementationOnce(
        () =>
          new Promise<SessionDetail>((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockResolvedValue(detailWith(recoveryOf({ state: "dispatch_claimed" })));
    const applyDetail = vi.fn();
    const { rerender } = renderPoll({ applyDetail });

    await tick(); // baseline fetch for s-1 in flight
    rerender({
      sessionId: "s-2",
      turns: [turnWith(recoveryOf())],
      streaming: false,
    });
    resolveFirst(detailWith(SETTLED));
    await tick(2);
    // The stale s-1 response is dropped; nothing from s-1 is applied, and the
    // hook only ever named s-1 or the newly active s-2 — never a third party.
    expect(applyDetail).not.toHaveBeenCalled();
    const targets = mockGetSession.mock.calls.map((call) => call[0]);
    expect(
      targets.every((target) => target === "s-1" || target === "s-2"),
    ).toBe(true);
  });
});
