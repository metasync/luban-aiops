// usePendingDecisionPoll tests (SPEC-032): the owner's chat view learns
// about externally made decisions through a bounded, change-gated poll of
// the session-detail surface — never while streaming, never when no card
// is pending, and only past the settle window once the last card resolves.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfirmationRecord, SessionDetail } from "../../api/sessions";
import type { ChatTurn } from "../../stream/useChatStream";
import {
  PENDING_SYNC_INTERVAL_MS,
  SETTLE_TICKS,
  usePendingDecisionPoll,
} from "../usePendingDecisionPoll";

const { mockGetSession } = vi.hoisted(() => ({
  mockGetSession: vi.fn(),
}));

vi.mock("../../api/sessions", () => ({ getSession: mockGetSession }));

function recordOf(overrides: Partial<ConfirmationRecord> = {}): ConfirmationRecord {
  return {
    confirm_id: "cf-1",
    session_id: "s-1",
    owner_user_id: "luban-operator",
    session_title: "Restart demo pod",
    pending_calls: [
      {
        call_id: "c-1",
        tool_name: "k8s.delete_pod",
        parameters: { pod: "scratch-restart-demo-0" },
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

function detailOf(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    session_id: "s-1",
    title: "Restart demo pod",
    created_at: "2026-08-25T09:00:00Z",
    last_active_at: "2026-08-25T10:00:00Z",
    pending_confirmation: true,
    user_id: "luban-operator",
    status: "active",
    transcript_available: true,
    transcript: [{ role: "user", content: "restart the pod" }],
    confirmations: [recordOf()],
    ...overrides,
  };
}

function turnOf(overrides: Partial<ChatTurn> = {}): ChatTurn {
  return {
    id: "t-1",
    userMessage: "restart the pod",
    replyText: "",
    completed: false,
    confirmationPending: true,
    toolCalls: [],
    toolResults: [],
    confirmations: [],
    ...overrides,
  };
}

function renderPoll(options: {
  sessionId?: string | null;
  turns?: ChatTurn[];
  streaming?: boolean;
  applyDetail?: (detail: SessionDetail) => void;
}) {
  const applyDetail = options.applyDetail ?? vi.fn();
  return {
    applyDetail,
    ...renderHook(
      (props: { sessionId: string | null; turns: ChatTurn[]; streaming: boolean }) =>
        usePendingDecisionPoll({ ...props, applyDetail }),
      {
        initialProps: {
          sessionId: options.sessionId ?? "s-1",
          turns: options.turns ?? [turnOf()],
          streaming: options.streaming ?? false,
        },
      },
    ),
  };
}

async function tick(times = 1) {
  await act(async () => {
    vi.advanceTimersByTime(PENDING_SYNC_INTERVAL_MS * times);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  mockGetSession.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("usePendingDecisionPoll (SPEC-032)", () => {
  it("re-seeds the timeline when an external decision moves the state", async () => {
    const pending = detailOf();
    const decided = detailOf({
      pending_confirmation: false,
      transcript: [
        { role: "user", content: "restart the pod" },
        { role: "assistant", content: "Done — the pod was restarted." },
      ],
      confirmations: [
        recordOf({
          status: "approved",
          decision: "approve",
          decider_user_id: "luban-approver",
          decided_at: "2026-08-25T10:05:00Z",
        }),
      ],
    });
    mockGetSession.mockResolvedValueOnce(pending).mockResolvedValue(decided);

    const { applyDetail } = renderPoll({});

    // First tick only records the baseline; nothing is applied.
    await tick();
    expect(mockGetSession).toHaveBeenCalledTimes(1);
    expect(applyDetail).not.toHaveBeenCalled();

    // The next tick sees the moved fingerprint and re-seeds once.
    await tick();
    expect(applyDetail).toHaveBeenCalledTimes(1);
    expect((applyDetail as ReturnType<typeof vi.fn>).mock.calls[0][0]).toEqual(
      decided,
    );

    // Unchanged responses afterwards never re-apply (change gate).
    await tick();
    expect(applyDetail).toHaveBeenCalledTimes(1);
  });

  it("does not poll when no confirmation card is pending", async () => {
    renderPoll({ turns: [turnOf({ confirmationPending: false })] });
    await tick(4);
    expect(mockGetSession).not.toHaveBeenCalled();
  });

  it("does not poll while a stream is active", async () => {
    renderPoll({ streaming: true });
    await tick(4);
    expect(mockGetSession).not.toHaveBeenCalled();
  });

  it("drops an in-flight response when a stream starts", async () => {
    let resolveFirst: (detail: SessionDetail) => void = () => {};
    mockGetSession.mockImplementationOnce(
      () =>
        new Promise<SessionDetail>((resolve) => {
          resolveFirst = resolve;
        }),
    );
    const applyDetail = vi.fn();
    const { rerender } = renderPoll({ applyDetail });

    // Tick 1 starts the fetch; the operator starts typing before it lands.
    await tick();
    rerender({ sessionId: "s-1", turns: [turnOf()], streaming: true });
    resolveFirst(detailOf({ confirmations: [] }));
    await tick(2);
    expect(applyDetail).not.toHaveBeenCalled();
  });

  it("keeps polling through the settle window, then stops on its own", async () => {
    const pending = detailOf();
    const decided = detailOf({
      pending_confirmation: false,
      confirmations: [recordOf({ status: "approved", decision: "approve" })],
    });
    mockGetSession.mockResolvedValueOnce(pending).mockResolvedValue(decided);

    const applyDetail = vi.fn();
    // Simulate ChatView: applying the decided detail re-seeds the turns
    // with no pending card, which reruns the effect mid-settle.
    const { rerender } = renderPoll({ applyDetail });

    await tick(); // baseline
    await tick(); // apply → settle window opens
    expect(applyDetail).toHaveBeenCalledTimes(1);
    rerender({
      sessionId: "s-1",
      turns: [turnOf({ confirmationPending: false })],
      streaming: false,
    });

    // The settle window survives the pending → settled rerun: one more
    // interval is scheduled and keeps fetching.
    const callsAfterFlip = mockGetSession.mock.calls.length;
    await tick();
    expect(mockGetSession.mock.calls.length).toBe(callsAfterFlip + 1);

    // Unchanged fingerprints count the window down until the poll stops.
    for (let i = 0; i < SETTLE_TICKS; i += 1) await tick();
    const settled = mockGetSession.mock.calls.length;
    await tick(3);
    expect(mockGetSession.mock.calls.length).toBe(settled);
  });

  it.each([
    ["denied", "deny"],
    ["expired", undefined],
  ] as const)(
    "flips %s resolutions through the same poll path",
    async (status, decision) => {
      mockGetSession
        .mockResolvedValueOnce(detailOf())
        .mockResolvedValue(
          detailOf({
            pending_confirmation: false,
            confirmations: [
              recordOf({
                status,
                ...(decision ? { decision } : {}),
              }),
            ],
          }),
        );
      const applyDetail = vi.fn();
      renderPoll({ applyDetail });

      await tick(); // baseline
      await tick(); // moved
      expect(applyDetail).toHaveBeenCalledTimes(1);
      const applied = (applyDetail as ReturnType<typeof vi.fn>).mock
        .calls[0][0] as SessionDetail;
      expect(applied.confirmations?.[0]?.status).toBe(status);
    },
  );

  it("keeps the last-good view on transport errors and retries", async () => {
    mockGetSession
      .mockResolvedValueOnce(detailOf())
      .mockRejectedValueOnce(new Error("gateway blip"))
      .mockResolvedValue(
        detailOf({
          confirmations: [recordOf({ status: "denied", decision: "deny" })],
        }),
      );
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
      .mockResolvedValue(detailOf({ session_id: "s-2" }));
    const applyDetail = vi.fn();
    const { rerender } = renderPoll({ applyDetail });

    await tick(); // baseline fetch for s-1 in flight
    rerender({ sessionId: "s-2", turns: [turnOf()], streaming: false });
    resolveFirst(
      detailOf({ confirmations: [recordOf({ status: "approved" })] }),
    );
    await tick(2);
    // The stale s-1 response is dropped; only the new session's baseline
    // fetches run, and nothing from s-1 is applied.
    expect(applyDetail).not.toHaveBeenCalled();
    const targets = mockGetSession.mock.calls.map((call) => call[0]);
    expect(targets.every((target) => target === "s-1" || target === "s-2")).toBe(
      true,
    );
    expect(targets.filter((target) => target === "s-2").length).toBeGreaterThan(
      0,
    );
  });
});
