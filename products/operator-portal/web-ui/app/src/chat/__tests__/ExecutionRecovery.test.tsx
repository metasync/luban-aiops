// SPEC-063 R-5a / F-24 portal proof: a decided card renders the owner-facing
// recovery projection for each execution — the durable-ledger state label
// (claimed / unknown / recorded tool report / late report / conflict /
// unavailable), the correlating times and IDs, the replay and missing-output
// explanations, history truncation, and independent-verification guidance.
//
// The recovery read is never an original response, so the card must expose NO
// retry, reset, mark-success, or reveal-old-password control: the only
// guidance offered is to verify the target system independently. Recovery is
// also independent of the legacy presentation row — a row whose presentation
// write never landed (status still "requested") still shows its ledger state.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExecutionRecovery, SessionDetail } from "../../api/sessions";
import type { ConfirmationCard } from "../../stream/useChatStream";
import { ConfirmationCardView, RecoveryPager, RECOVERY_VOCABULARY } from "../ChatView";

const { mockUseAuth, mockGetSession } = vi.hoisted(() => ({ mockUseAuth: vi.fn(), mockGetSession: vi.fn() }));
vi.mock("../../api/sessions", () => ({ getSession: mockGetSession }));
vi.mock("../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));

function recoveryOf(
  overrides: Partial<ExecutionRecovery> = {},
): ExecutionRecovery {
  return {
    availability: "available",
    state: "dispatch_claimed",
    execution_id: "exec-1",
    tool_name: "k8s.restart_pod",
    requested_at: "2026-09-24T10:00:00Z",
    expires_at: "2026-09-24T10:10:00Z",
    claimed_at: "2026-09-24T10:00:05Z",
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

// A decided card whose single execution row carries `recovery`. The
// presentation status stays "requested" on purpose: the recovery projection
// is fetched from the ledger independently, so it must render the true state
// even when the legacy presentation write never landed.
function decidedCard(recovery?: ExecutionRecovery | null): ConfirmationCard {
  return {
    confirmId: "cf-1",
    message: "Approve the restart?",
    pendingCalls: [
      {
        callId: "c-1",
        toolName: "k8s.restart_pod",
        riskLevel: "write",
        action: "tools:mutate",
      },
    ],
    mutating: true,
    status: "approved",
    sessionId: "s-1",
    note: "Approved by luban-approver at 2026-09-24T10:00:10Z.",
    deciderUserId: "luban-approver",
    decidedAt: "2026-09-24T10:00:10Z",
    executions: [
      {
        executionId: "exec-1",
        callId: "c-1",
        toolName: "k8s.restart_pod",
        status: "requested",
        digestMatch: true,
        recovery: recovery ?? undefined,
      },
    ],
  };
}

function renderCard(card: ConfirmationCard) {
  return render(
    <ConfirmationCardView
      card={card}
      canDecide
      busy={false}
      onDecide={() => {}}
    />,
  );
}

beforeEach(() => {
  mockUseAuth.mockReset();
  mockGetSession.mockReset();
  mockUseAuth.mockReturnValue({ roles: ["approver"] });
});

// Vitest globals are off, so testing-library's auto-cleanup never registers;
// unmount explicitly to keep renders isolated.
afterEach(() => {
  cleanup();
});

describe("ConfirmationCardView recovery labels (SPEC-063 R-5a)", () => {
  it("labels a claimed dispatch and guides independent verification", () => {
    renderCard(decidedCard(recoveryOf({ state: "dispatch_claimed" })));
    expect(screen.getByText("dispatch claimed")).toBeTruthy();
    expect(
      screen.getByText(/no tool result has been durably recorded yet/i),
    ).toBeTruthy();
    expect(
      screen.getByText(/this recovery read is not proof of the current state/i),
    ).toBeTruthy();
  });

  it("labels an unknown outcome and explains the missing output", () => {
    renderCard(
      decidedCard(
        recoveryOf({ state: "outcome_unknown", claimed_at: null, receipt: null }),
      ),
    );
    expect(screen.getByText("outcome unknown")).toBeTruthy();
    expect(
      screen.getByText(/Missing output is inconclusive/i)
    ).toBeTruthy();
  });

  it("labels a recorded tool report", () => {
    renderCard(
      decidedCard(
        recoveryOf({
          state: "result_recorded",
          receipt: {
            status: "succeeded",
            completed_at: "2026-09-24T10:01:30Z",
            request_id: "req-9",
          },
        }),
      ),
    );
    expect(screen.getByText("tool report recorded")).toBeTruthy();
    expect(
      screen.getByText(/durably recorded\. This is the recorded report, not a live re-run/i),
    ).toBeTruthy();
  });

  it("labels a late report when the durable result lands after the deadline", () => {
    renderCard(
      decidedCard(
        recoveryOf({
          state: "result_recorded",
          observe_by: "2026-09-24T10:02:00Z",
          receipt: {
            status: "succeeded",
            completed_at: "2026-09-24T10:05:00Z",
            request_id: "req-9",
          },
        }),
      ),
    );
    expect(screen.getByText("late tool report recorded")).toBeTruthy();
    expect(
      screen.getByText(/landed after the observation window closed/i),
    ).toBeTruthy();
  });

  it("labels conflicting reports and treats the result as unknown", () => {
    renderCard(
      decidedCard(
        recoveryOf({ state: "outcome_unknown", integrity_conflict: true }),
      ),
    );
    expect(screen.getByText("conflicting reports")).toBeTruthy();
    expect(
      screen.getByText(/could not be reconciled into one outcome/i),
    ).toBeTruthy();
  });

  it("degrades to recovery unavailable without hiding the presentation row", () => {
    renderCard(
      decidedCard(
        recoveryOf({
          availability: "unavailable",
          state: null,
          claimed_at: null,
          receipt: null,
          observations: [],
        }),
      ),
    );
    expect(screen.getByText("recovery unavailable")).toBeTruthy();
    expect(
      screen.getByText(/This is not evidence either way/i),
    ).toBeTruthy();
    // The legacy presentation row (tool name) is still rendered — an outage
    // never hides historical facts. (It appears on both the parked call and
    // the execution row.)
    expect(screen.getAllByText("k8s.restart_pod").length).toBeGreaterThan(0);
  });

  it("distinguishes positive refusal from unresolved registration", () => {
    const { unmount } = renderCard(
      decidedCard(
        recoveryOf({ state: "not_dispatched", run_stopped: true, claimed_at: null }),
      ),
    );
    expect(screen.getByText("not dispatched")).toBeTruthy();
    expect(screen.getByText(/This submission was positively refused/)).toBeTruthy();
    expect(screen.getByText(/does not establish the outcome of any other attempt/)).toBeTruthy();
    unmount();
    renderCard(
      decidedCard(
        recoveryOf({
          state: null,
          preparation_state: "registered",
          claimed_at: null,
        }),
      ),
    );
    expect(screen.getByText("registered — dispatch not established")).toBeTruthy();
    expect(screen.getByText(/Registration alone does not prove that the target did nothing/)).toBeTruthy();
  });
});

describe("recovery minimization and contract parity (SPEC-063 F-27)", () => {
  it("pins portal vocabulary and observation bounds to shared schemas", () => {
    const schema = (name: string) => JSON.parse(readFileSync(resolve(
      process.cwd(), "../../../../shared/shared-contracts/schemas", `${name}.schema.json`,
    ), "utf8"));
    const recovery = schema("execution-recovery");
    const observation = schema("execution-observation");
    expect(RECOVERY_VOCABULARY.availability).toEqual(recovery.properties.availability.enum);
    expect(RECOVERY_VOCABULARY.state).toEqual(recovery.properties.state.enum);
    expect(RECOVERY_VOCABULARY.source).toEqual(observation.properties.source.enum);
    expect(RECOVERY_VOCABULARY.kind).toEqual(observation.properties.kind.enum);
    expect(RECOVERY_VOCABULARY.reason).toEqual(observation.$defs.reason.enum);
    expect(RECOVERY_VOCABULARY.receipt).toEqual(schema("execution-receipt").properties.status.enum);
    expect(recovery.properties.observations.maxItems).toBe(20);
    expect(observation.$defs.id.maxLength).toBe(256);
    expect(observation.$defs.time.maxLength).toBe(40);
  });

  it.each([null, {}, { status: "unknown-status-canary" }])(
    "does not infer success from an incomplete recorded receipt (%j)", (receipt) => {
      renderCard(decidedCard(recoveryOf({ state: "result_recorded",
        receipt: receipt as ExecutionRecovery["receipt"],
      })));
      expect(screen.getByText("outcome unknown")).toBeTruthy();
      expect(screen.queryByText("tool report recorded")).toBeNull();
      expect(document.body.textContent?.includes("unknown-status-canary")).toBe(false);
    },
  );

  it("does not mistake an unknown state for a registered or successful execution", () => {
    renderCard(decidedCard(recoveryOf({ state: "unknown-state-canary" as ExecutionRecovery["state"] })));
    expect(screen.getByText("outcome unknown")).toBeTruthy();
    expect(screen.queryByText("registered — dispatch not established")).toBeNull();
    expect(document.body.textContent?.includes("unknown-state-canary")).toBe(false);
  });

  it("fails closed on unknown availability even with a historical successful receipt", () => {
    renderCard(decidedCard(recoveryOf({ availability: "unknown" as ExecutionRecovery["availability"],
      state: "result_recorded", receipt: { status: "succeeded" },
    })));
    expect(screen.getByText("recovery unavailable")).toBeTruthy();
    expect(screen.queryByText("tool report recorded")).toBeNull();
  });

  it("projects only bounded metadata without modifying the original signed objects", () => {
    const canary = "https://invalid.test/?password=display-canary";
    const recovery = recoveryOf({
      run_id: canary, confirm_id: canary, attempt_request_id: "x".repeat(257),
      requested_at: canary, claimed_at: "x".repeat(41), as_of: canary,
      state: "result_recorded", receipt: { status: "succeeded", completed_at: canary },
      observations: [null, { observation_id: canary, kind: canary, source: canary,
        reason_code: canary, request_id: canary, observed_at: canary,
        parameters: { password: canary }, result: canary,
      }] as unknown as ExecutionRecovery["observations"],
    });
    const before = JSON.stringify(recovery);
    const { container } = renderCard(decidedCard(recovery));
    expect(container.textContent?.includes(canary)).toBe(false);
    expect(container.textContent?.includes("x".repeat(41))).toBe(false);
    expect(screen.getAllByText("unrecognized observation")).toHaveLength(2);
    expect(screen.getByText("tool report recorded")).toBeTruthy();
    expect(JSON.stringify(recovery) === before).toBe(true);
  });

  it("bounds oversize history and preserves valid observations in recorded order", () => {
    const recovery = recoveryOf({ observations: Array.from({ length: 23 }, (_, i) => ({
      observation_id: `o-${i}`, source: "agent", kind: "wait_expired",
      reason_code: "wait_expired", request_id: `req-${i}`, observed_at: "2026-09-24T10:00:05Z",
    })), observations_truncated: false });
    const before = JSON.stringify(recovery);
    renderCard(decidedCard(recovery));
    const list = screen.getByRole("list", { name: "Execution observations", hidden: true });
    const rows = within(list).getAllByRole("listitem", { hidden: true });
    expect(rows).toHaveLength(20);
    expect(rows[0].textContent).toContain("Request: req-0");
    expect(rows[19].textContent).toContain("Request: req-19");
    expect(rows[19].textContent).toContain("Reason: wait_expired");
    expect(screen.getByText(/bounded to 20 entries per page/)).toBeTruthy();
    expect(JSON.stringify(recovery) === before).toBe(true);
  });

  it("ignores a malformed observation collection", () => {
    renderCard(decidedCard(recoveryOf({ observations: { token: "not-an-array" } as unknown as ExecutionRecovery["observations"] })));
    expect(screen.queryByRole("list", { name: "Execution observations", hidden: true })).toBeNull();
    expect(document.body.textContent?.includes("not-an-array")).toBe(false);
  });
});

function detailOf(recovery = recoveryOf()): SessionDetail {
  return {
    session_id: "s-1", user_id: "owner", title: "Recovery", status: "active",
    created_at: "2026-09-24T10:00:00Z", last_active_at: null,
    pending_confirmation: false, session_type: "operation",
    transcript_available: true, transcript: [], execution_recovery_availability: "available",
    confirmations: [{ confirm_id: "cf-1", session_id: "s-1", owner_user_id: "owner",
      status: "approved", pending_calls: [], executions: [{
        execution_id: "exec-1", call_id: "c-1", confirm_id: "cf-1", session_id: "s-1",
        tool_name: "k8s.restart_pod", status: "requested", recovery,
      }] }],
  };
}

async function clickPage(name: string) {
  await act(async () => { fireEvent.click(screen.getByRole("button", { name, hidden: true })); });
}

describe("read-only recovery pagination", () => {
  it("reads next and first observation pages without accumulating old observations", async () => {
    const initial = recoveryOf({ next_observation_cursor: "observations-two", observations_truncated: true });
    const next = recoveryOf({ state: "outcome_unknown", observations: [{
      observation_id: "o-21", kind: "wait_expired", source: "agent", observed_at: "2026-09-24T10:02:01Z",
    }] });
    mockGetSession.mockResolvedValueOnce(detailOf(next)).mockResolvedValueOnce(detailOf(initial));
    renderCard(decidedCard(initial));
    await clickPage("Next observation page");
    expect(mockGetSession).toHaveBeenLastCalledWith("s-1", expect.any(AbortSignal), {
      execution: "exec-1", executionCursor: "observations-two", pageSize: 1,
    });
    expect(screen.getByText("outcome unknown")).toBeTruthy();
    expect(screen.getByText("wait_expired")).toBeTruthy();
    await clickPage("First observation page");
    expect(mockGetSession).toHaveBeenLastCalledWith("s-1", expect.any(AbortSignal), {
      execution: "exec-1", executionCursor: undefined, pageSize: 1,
    });
    expect(screen.queryByText("wait_expired")).toBeNull();
    expect(screen.getByText("dispatch claimed")).toBeTruthy();
  });

  it.each(["transport", "unavailable", "wrong-session", "wrong-execution"])("retains observations after %s failure", async (failure) => {
    const detail = detailOf();
    if (failure === "transport") mockGetSession.mockRejectedValue(new Error("offline"));
    else {
      if (failure === "unavailable") detail.confirmations![0].executions![0].recovery!.availability = "unavailable";
      if (failure === "wrong-session") detail.session_id = "other";
      if (failure === "wrong-execution") detail.confirmations![0].executions![0].execution_id = "other";
      mockGetSession.mockResolvedValue(detail);
    }
    renderCard(decidedCard(recoveryOf({ next_observation_cursor: "next" })));
    await clickPage("Next observation page");
    expect(screen.getByRole("status").textContent).toContain("last readable view is retained");
    expect(screen.getByText("dispatch claimed")).toBeTruthy();
  });

  it.each(["stream", "session", "unmount"])("aborts an observation read on %s", async (change) => {
    let resolve: (detail: SessionDetail) => void = () => {};
    mockGetSession.mockImplementation(() => new Promise<SessionDetail>((done) => { resolve = done; }));
    const card = decidedCard(recoveryOf({ next_observation_cursor: "next" }));
    const view = renderCard(card);
    await clickPage("Next observation page");
    await clickPage("Next observation page");
    expect(mockGetSession).toHaveBeenCalledTimes(1);
    const signal = mockGetSession.mock.calls[0][1] as AbortSignal;
    if (change === "unmount") view.unmount();
    else view.rerender(<ConfirmationCardView card={change === "session" ? { ...card, sessionId: "s-2" } : card}
      canDecide busy={change === "stream"} onDecide={vi.fn()} />);
    expect(signal.aborted).toBe(true);
    await act(async () => { resolve(detailOf(recoveryOf({ state: "outcome_unknown" }))); });
    expect(screen.queryByText("outcome unknown")).toBeNull();
  });

  it("pages executions in the parent while reporting busy without canceling itself", async () => {
    const first = { ...detailOf(), executions_truncated: true, next_execution_cursor: "executions-two" };
    const second = { ...detailOf(), executions_truncated: false, next_execution_cursor: null };
    mockGetSession.mockResolvedValueOnce(second).mockResolvedValueOnce(first);
    function Host() {
      const [page, setPage] = useState<{ detail: SessionDetail; cursor?: string }>({ detail: first });
      const [loading, setLoading] = useState(false);
      return <><span>{loading ? "reading" : "idle"}</span>
        <RecoveryPager sessionId="s-1" {...page} busy={false} onBusy={setLoading}
          onPage={(detail, cursor) => setPage({ detail, cursor })} /></>;
    }
    render(<Host />);
    await clickPage("Next execution page");
    expect(mockGetSession).toHaveBeenLastCalledWith("s-1", expect.any(AbortSignal), { executionCursor: "executions-two" });
    expect(screen.queryByText("Next execution page")).toBeNull();
    expect(screen.getByText("idle")).toBeTruthy();
    await clickPage("First execution page");
    expect(mockGetSession).toHaveBeenLastCalledWith("s-1", expect.any(AbortSignal), undefined);
    expect(screen.getByText("Next execution page")).toBeTruthy();
    expect(screen.queryByText("First execution page")).toBeNull();
  });

  it.each(["transport", "unavailable", "wrong-session"])("retains execution page on %s", async (failure) => {
    if (failure === "transport") mockGetSession.mockRejectedValue(new Error("offline"));
    else mockGetSession.mockResolvedValue({ ...detailOf(),
      ...(failure === "unavailable" ? { execution_recovery_availability: "unavailable" } : { session_id: "foreign" }),
    });
    const onPage = vi.fn();
    const onBusy = vi.fn();
    render(<RecoveryPager sessionId="s-1" detail={{ ...detailOf(), next_execution_cursor: "next" }}
      busy={false} onBusy={onBusy} onPage={onPage} />);
    await clickPage("Next execution page");
    expect(onPage).not.toHaveBeenCalled();
    expect(onBusy.mock.calls.map(([value]) => value)).toEqual([true, false]);
    expect(screen.getByRole("status").textContent).toContain("last readable page is retained");
  });

  it.each(["stream", "session", "unmount"])("aborts an execution-page read on %s", async (change) => {
    let resolve: (detail: SessionDetail) => void = () => {};
    mockGetSession.mockImplementation(() => new Promise<SessionDetail>((done) => { resolve = done; }));
    const props = { sessionId: "s-1", detail: { ...detailOf(), next_execution_cursor: "next" },
      busy: false, onBusy: vi.fn(), onPage: vi.fn() };
    const view = render(<RecoveryPager {...props} />);
    await clickPage("Next execution page");
    await clickPage("Next execution page");
    expect(mockGetSession).toHaveBeenCalledTimes(1);
    const signal = mockGetSession.mock.calls[0][1] as AbortSignal;
    if (change === "unmount") view.unmount();
    else view.rerender(<RecoveryPager {...props} busy={change === "stream"} sessionId={change === "session" ? "s-2" : "s-1"} />);
    expect(signal.aborted).toBe(true);
    await act(async () => { resolve(detailOf()); });
    expect(props.onPage).not.toHaveBeenCalled();
    expect(props.onBusy).toHaveBeenLastCalledWith(false);
  });

  it("shows unavailable with no rows, without implying zero executions", () => {
    render(<RecoveryPager sessionId="s-1" detail={{ ...detailOf(), confirmations: [], execution_recovery_availability: "unavailable" }}
      busy={false} onBusy={vi.fn()} onPage={vi.fn()} />);
    expect(screen.getByRole("alert").textContent).toContain("does not mean there were no executions");
    expect(mockGetSession).not.toHaveBeenCalled();
  });
});

describe("ConfirmationCardView recovery detail (SPEC-063 R-5a)", () => {
  it("shows correlating times, ids, replay and truncation in the expander", () => {
    renderCard(
      decidedCard(
        recoveryOf({
          state: "dispatch_claimed",
          replay: true,
          observations_truncated: true,
          next_observation_cursor: "opaque-cursor",
          attempt_request_id: "original-request",
          run_id: "run-1",
          confirm_id: "cf-1",
          run_stopped: true,
          observations: [
            {
              observation_id: "o-1",
              source: "worker",
              kind: "claim_committed",
              observed_at: "2026-09-24T10:00:05Z",
              request_id: "req-7",
            },
          ],
        }),
      ),
    );
    // IDs and times ride the fact list.
    expect(screen.getByText("exec-1")).toBeTruthy();
    expect(screen.getByText("original-request")).toBeTruthy();
    expect(screen.getByText("run-1")).toBeTruthy();
    expect(screen.getByText(/Work already running at the target is not necessarily canceled/)).toBeTruthy();
    const history = screen.getByRole("list", { name: "Execution observations", hidden: true });
    expect(within(history).getByText("claim_committed")).toBeTruthy();
    expect(within(history).getByText(/Request: req-7/)).toBeTruthy();
    expect(screen.getByText("2026-09-24T10:00:00Z")).toBeTruthy();
    expect(screen.getByText("2026-09-24T10:02:00Z")).toBeTruthy();
    // Replay + truncation explanations.
    expect(screen.getByText(/replayed recovery read/i)).toBeTruthy();
    expect(
      screen.getByText(/bounded to 20 entries per page in recorded order/i)
    ).toBeTruthy();
    expect(
      screen.getByText(/More observations remain in the ledger/i)
    ).toBeTruthy();
  });

  it("exposes no retry, reset, mark-success, or reveal control", () => {
    const { container } = renderCard(
      decidedCard(recoveryOf({ state: "outcome_unknown" })),
    );
    // A decided card renders no buttons at all, and recovery adds none.
    expect(container.querySelectorAll("button")).toHaveLength(0);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/retry/i);
    expect(text).not.toMatch(/reset/i);
    expect(text).not.toMatch(/mark.{0,3}success/i);
    expect(text).not.toMatch(/reveal/i);
    expect(text).not.toMatch(/show.{0,12}password/i);
  });

  it("renders a legacy row with no recovery exactly as today", () => {
    const { container } = renderCard(decidedCard(null));
    expect(container.querySelector(".confirm-execution-recovery")).toBeNull();
    expect(screen.queryByText("dispatch claimed")).toBeNull();
    expect(screen.queryByText("outcome unknown")).toBeNull();
    // The presentation receipt is untouched.
    expect(screen.getAllByText("k8s.restart_pod").length).toBeGreaterThan(0);
  });
});
