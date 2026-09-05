// Transcript seeding tests (SPEC-023 R-3): the SPEC-022 transcript shape
// must map into turn pairs that render like live turns.
// SPEC-025 R-3: persisted evidence groups attach by turn_index so replay
// renders the same evidence card the live stream showed.
import { describe, expect, it } from "vitest";
import type {
  ConfirmationRecord,
  EvidenceTurn,
  TranscriptTurn,
} from "../../api/sessions";
import type { ChatTurn } from "../../stream/useChatStream";
import { detectArrivalSpan, transcriptToTurns } from "../transcript";

function turnOf(replyText: string, userMessage = "run it"): ChatTurn {
  return {
    id: `t-${replyText.length}`,
    userMessage,
    replyText,
    completed: true,
    confirmationPending: false,
    toolCalls: [],
    toolResults: [],
    confirmations: [],
    history: true,
  };
}

describe("transcriptToTurns", () => {
  it("pairs a user turn with the following assistant reply", () => {
    const transcript: TranscriptTurn[] = [
      { role: "user", content: "status please" },
      { role: "assistant", content: "All systems nominal." },
    ];
    const turns = transcriptToTurns(transcript);
    expect(turns).toHaveLength(1);
    expect(turns[0].userMessage).toBe("status please");
    expect(turns[0].replyText).toBe("All systems nominal.");
    expect(turns[0].history).toBe(true);
    expect(turns[0].completed).toBe(true);
  });

  it("merges consecutive assistant replies into one turn", () => {
    const transcript: TranscriptTurn[] = [
      { role: "user", content: "explain" },
      { role: "assistant", content: "Part one." },
      { role: "assistant", content: "Part two." },
    ];
    const turns = transcriptToTurns(transcript);
    expect(turns).toHaveLength(1);
    expect(turns[0].replyText).toBe("Part one.\n\nPart two.");
  });

  it("keeps an orphan assistant turn visible", () => {
    const transcript: TranscriptTurn[] = [
      { role: "assistant", content: "Welcome back." },
    ];
    const turns = transcriptToTurns(transcript);
    expect(turns).toHaveLength(1);
    expect(turns[0].userMessage).toBe("");
    expect(turns[0].replyText).toBe("Welcome back.");
  });

  it("handles multiple exchanges in order", () => {
    const transcript: TranscriptTurn[] = [
      { role: "user", content: "first" },
      { role: "assistant", content: "one" },
      { role: "user", content: "second" },
      { role: "assistant", content: "two" },
    ];
    const turns = transcriptToTurns(transcript);
    expect(turns.map((t) => t.userMessage)).toEqual(["first", "second"]);
    expect(turns.map((t) => t.replyText)).toEqual(["one", "two"]);
  });

  it("returns no turns for an empty transcript", () => {
    expect(transcriptToTurns([])).toEqual([]);
  });

  it("never carries tool frames — evidence stays off for history turns", () => {
    const turns = transcriptToTurns([
      { role: "user", content: "run it" },
      { role: "assistant", content: "done" },
    ]);
    expect(turns[0].toolCalls).toEqual([]);
    expect(turns[0].toolResults).toEqual([]);
    expect(turns[0].confirmations).toEqual([]);
  });
});

// --- Persisted evidence replay (SPEC-025 R-3) ---

const TWO_TURNS: TranscriptTurn[] = [
  { role: "user", content: "check the pods" },
  { role: "assistant", content: "all pods running." },
  { role: "user", content: "and the events?" },
  { role: "assistant", content: "no recent warnings." },
];

function evidenceGroup(turnIndex: number): EvidenceTurn {
  return {
    turn_index: turnIndex,
    request_id: "req-1",
    created_at: "2026-08-23T10:00:00Z",
    frames: [
      {
        type: "tool_call",
        call_id: "call-1",
        tool_name: "k8s.list_pods",
        parameters: { namespace: "dev-luban-aiops" },
      },
      {
        type: "tool_result",
        call_id: "call-1",
        tool_name: "k8s.list_pods",
        status: "success",
        evidence: {
          executed_at: "2026-08-23T10:00:00Z",
          duration_ms: 42,
          risk_level: "read",
          source_system: "kubernetes",
        },
        data: { count: 3 },
      },
    ],
  };
}

describe("transcriptToTurns evidence replay", () => {
  it("attaches a group to the ChatTurn at its turn_index", () => {
    // Backend turn_index is the exchange ordinal: 0 → ChatTurn 0.
    const turns = transcriptToTurns(TWO_TURNS, [evidenceGroup(0)]);
    expect(turns[0].toolCalls).toHaveLength(1);
    expect(turns[0].toolResults).toHaveLength(1);
    expect(turns[0].requestId).toBe("req-1");
    expect(turns[1].toolCalls).toEqual([]);
  });

  it("maps frames to the exact live-stream frame shape", () => {
    // Prop-identical to what the SSE decoder produces for the same
    // frames — one component renders both, so the shapes must match.
    // Backend turn_index 1 → ChatTurn 1 (second exchange).
    const [, replayed] = transcriptToTurns(TWO_TURNS, [evidenceGroup(1)]);
    expect(replayed.toolCalls[0]).toEqual({
      kind: "tool_call",
      callId: "call-1",
      toolName: "k8s.list_pods",
      parameters: { namespace: "dev-luban-aiops" },
    });
    expect(replayed.toolResults[0]).toEqual({
      kind: "tool_result",
      callId: "call-1",
      toolName: "k8s.list_pods",
      status: "success",
      evidence: {
        executedAt: "2026-08-23T10:00:00Z",
        durationMs: 42,
        riskLevel: "read",
        sourceSystem: "kubernetes",
      },
      data: { count: 3 },
      dataSummary: undefined,
      error: undefined,
      truncated: undefined,
    });
  });

  it("drops out-of-range groups instead of crashing", () => {
    const turns = transcriptToTurns(TWO_TURNS, [
      evidenceGroup(5),
      evidenceGroup(-1),
    ]);
    for (const turn of turns) {
      expect(turn.toolCalls).toEqual([]);
      expect(turn.toolResults).toEqual([]);
      expect(turn.requestId).toBeUndefined();
    }
  });

  it("keeps the store-added truncation marker visible", () => {
    const group = evidenceGroup(0);
    group.frames[1].truncated = { reason: "session_budget" };
    group.frames[1].data = null;
    const [turn] = transcriptToTurns(TWO_TURNS, [group]);
    expect(turn.toolResults[0].truncated).toEqual({
      reason: "session_budget",
      originalChars: undefined,
    });
    expect(turn.toolResults[0].data).toBeNull();
  });

  it("ignores frames that are not tool evidence", () => {
    const group = evidenceGroup(0);
    group.frames.push({ type: "thinking_block" });
    const [turn] = transcriptToTurns(TWO_TURNS, [group]);
    expect(turn.toolCalls).toHaveLength(1);
    expect(turn.toolResults).toHaveLength(1);
  });

  it("treats null and absent evidence as none stored", () => {
    expect(transcriptToTurns(TWO_TURNS, null)).toHaveLength(2);
    expect(transcriptToTurns(TWO_TURNS, [])).toHaveLength(2);
    expect(transcriptToTurns(TWO_TURNS)[0].toolCalls).toEqual([]);
  });
});

// --- Durable confirmation replay (SPEC-031 R-2) ---

function recordOf(
  overrides: Partial<ConfirmationRecord> = {},
): ConfirmationRecord {
  return {
    confirm_id: "cf-9",
    session_id: "s-1",
    owner_user_id: "luban-operator",
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

describe("transcriptToTurns confirmation replay (SPEC-031 R-2)", () => {
  it("attaches a pending record to the last turn as an actionable card", () => {
    const turns = transcriptToTurns(TWO_TURNS, null, [recordOf()]);
    expect(turns).toHaveLength(2);
    // The card anchors to the turn that parked it — the last one.
    expect(turns[0].confirmations).toEqual([]);
    const card = turns[1].confirmations[0];
    expect(card).toMatchObject({
      confirmId: "cf-9",
      status: "pending",
      sessionId: "s-1",
      mutating: true,
    });
    expect(card.pendingCalls[0]).toEqual({
      callId: "c-1",
      toolName: "k8s.restart_pod",
      parameters: { pod: "api" },
      riskLevel: "write",
      action: "tools:mutate",
    });
    expect(turns[1].confirmationPending).toBe(true);
    // Pending cards carry no attribution note.
    expect(card.note).toBeUndefined();
  });

  it("renders all four durable states with decided cards read-only", () => {
    const decidedAt = "2026-08-25T10:05:00Z";
    const approved = transcriptToTurns(
      TWO_TURNS,
      null,
      [
        recordOf({
          status: "approved",
          decider_user_id: "luban-approver",
          decision: "approve",
          decided_at: decidedAt,
        }),
      ],
    )[1].confirmations[0];
    expect(approved.status).toBe("approved");
    expect(approved.note).toBe(
      `Approved by luban-approver at ${decidedAt}.`,
    );
    expect(approved.deciderUserId).toBe("luban-approver");
    expect(approved.decidedAt).toBe(decidedAt);

    const denied = transcriptToTurns(
      TWO_TURNS,
      null,
      [recordOf({ status: "denied", decider_user_id: "luban-admin", decided_at: decidedAt })],
    )[1].confirmations[0];
    expect(denied.note).toBe(`Denied by luban-admin at ${decidedAt}.`);

    const expired = transcriptToTurns(
      TWO_TURNS,
      null,
      [recordOf({ status: "expired" })],
    )[1].confirmations[0];
    expect(expired.note).toBe(
      "This confirmation expired before a decision was applied.",
    );

    // Pending stays unannotated (covered above) — four states, one mapper.
    const pending = transcriptToTurns(TWO_TURNS, null, [recordOf()])[1]
      .confirmations[0];
    expect(pending.status).toBe("pending");
  });

  it("keeps a card visible even when the transcript is empty", () => {
    // Unrecoverable/empty transcripts still surface parked requests via
    // a synthetic turn.
    const turns = transcriptToTurns([], null, [recordOf()]);
    expect(turns).toHaveLength(1);
    expect(turns[0].userMessage).toBe("");
    expect(turns[0].confirmations).toHaveLength(1);
    expect(turns[0].confirmationPending).toBe(true);
  });

  it("falls back to the record-level action for the tier badge", () => {
    const record = recordOf({
      pending_calls: [
        { call_id: "c-1", tool_name: "k8s.restart_pod", risk_level: "write" },
      ],
      action: "tools:mutate",
    });
    const card = transcriptToTurns(TWO_TURNS, null, [record])[1]
      .confirmations[0];
    expect(card.pendingCalls[0].action).toBe("tools:mutate");
  });

  it("treats null and absent confirmations as none stored", () => {
    expect(transcriptToTurns(TWO_TURNS, null, null)).toHaveLength(2);
    expect(transcriptToTurns(TWO_TURNS, null, [])[0].confirmations).toEqual(
      [],
    );
  });
});

// --- Browser-flow headline replay (SPEC-051 R-6) ---

describe("transcriptToTurns browser-flow headline (SPEC-051 R-6)", () => {
  it("replays the durable flow_summary onto the card as camelCase", () => {
    const card = transcriptToTurns(TWO_TURNS, null, [
      recordOf({
        flow_summary: {
          skill_id: "samples/password-reset",
          origin: "http://admin.local",
          title: "Reset User Password",
          description: "Reset a user's password in the admin portal",
          flow_intent: "Submit the password reset for the user.",
          risk_class: "write",
        },
      }),
    ])[1].confirmations[0];
    expect(card.flowSummary).toEqual({
      skillId: "samples/password-reset",
      origin: "http://admin.local",
      title: "Reset User Password",
      description: "Reset a user's password in the admin portal",
      flowIntent: "Submit the password reset for the user.",
      riskClass: "write",
    });
  });

  it("leaves flowSummary undefined for a non-browser or pre-spec record", () => {
    // recordOf() carries no flow_summary — a plain k8s card, and the shape
    // every record parked before SPEC-051 has. The card falls back to
    // tool-action rendering.
    const card = transcriptToTurns(TWO_TURNS, null, [recordOf()])[1]
      .confirmations[0];
    expect(card.flowSummary).toBeUndefined();
    // An explicit null (the durable column's default) maps the same way.
    const nullCard = transcriptToTurns(TWO_TURNS, null, [
      recordOf({ flow_summary: null }),
    ])[1].confirmations[0];
    expect(nullCard.flowSummary).toBeUndefined();
  });
});

// --- Turn-anchored cards (SPEC-033 R-3) ---

describe("transcriptToTurns card turn anchoring (SPEC-033 R-3)", () => {
  it("anchors each record under the turn that parked it", () => {
    const turns = transcriptToTurns(TWO_TURNS, null, [
      recordOf({
        confirm_id: "cf-first",
        status: "approved",
        decider_user_id: "luban-approver",
        decided_at: "2026-08-25T10:05:00Z",
        turn_index: 0,
      }),
      recordOf({
        confirm_id: "cf-second",
        status: "approved",
        decider_user_id: "luban-approver",
        decided_at: "2026-08-25T11:05:00Z",
        turn_index: 1,
      }),
    ]);
    // No stacking under the newest turn — one card per parking exchange.
    expect(turns[0].confirmations.map((c) => c.confirmId)).toEqual([
      "cf-first",
    ]);
    expect(turns[1].confirmations.map((c) => c.confirmId)).toEqual([
      "cf-second",
    ]);
  });

  it("anchors a pending record to its parking turn", () => {
    const turns = transcriptToTurns(TWO_TURNS, null, [
      recordOf({ turn_index: 0 }),
    ]);
    expect(turns[0].confirmations).toHaveLength(1);
    expect(turns[0].confirmationPending).toBe(true);
    expect(turns[1].confirmationPending).toBe(false);
    expect(turns[1].confirmations).toEqual([]);
  });

  it("falls back to the newest turn without a usable ordinal", () => {
    const turns = transcriptToTurns(TWO_TURNS, null, [
      recordOf({ confirm_id: "cf-null", turn_index: null }),
      recordOf({ confirm_id: "cf-absent" }),
      recordOf({ confirm_id: "cf-stale", turn_index: 7 }),
    ]);
    expect(turns[0].confirmations).toEqual([]);
    expect(turns[1].confirmations.map((c) => c.confirmId)).toEqual([
      "cf-null",
      "cf-absent",
      "cf-stale",
    ]);
  });
});

// --- Signed-execution receipts on decided cards (SPEC-037 R-6) ---

function executionOf(overrides = {}) {
  return {
    execution_id: "exec-1",
    call_id: "c-1",
    confirm_id: "cf-9",
    session_id: "s-1",
    tool_name: "k8s.restart_pod",
    status: "succeeded" as const,
    digest_match: true,
    reject_reason: null,
    ...overrides,
  };
}

describe("transcriptToTurns execution receipts (SPEC-037 R-6)", () => {
  it("maps session-detail executions onto decided cards", () => {
    const card = transcriptToTurns(TWO_TURNS, null, [
      recordOf({
        status: "approved",
        decider_user_id: "luban-approver",
        decided_at: "2026-08-27T10:05:00Z",
        executions: [
          executionOf(),
          executionOf({
            execution_id: "exec-2",
            status: "rejected",
            digest_match: false,
            reject_reason: "args_digest_mismatch",
          }),
        ],
      }),
    ])[1].confirmations[0];
    expect(card.executions).toEqual([
      {
        executionId: "exec-1",
        callId: "c-1",
        toolName: "k8s.restart_pod",
        status: "succeeded",
        digestMatch: true,
        rejectReason: undefined,
      },
      {
        executionId: "exec-2",
        callId: "c-1",
        toolName: "k8s.restart_pod",
        status: "rejected",
        digestMatch: false,
        rejectReason: "args_digest_mismatch",
      },
    ]);
  });

  it("keeps legacy decided rows and pending cards receipt-free", () => {
    // Records predating the field (and inbox-shaped records) map to a
    // card without an executions surface.
    const legacy = transcriptToTurns(TWO_TURNS, null, [
      recordOf({ status: "approved", decider_user_id: "luban-approver" }),
    ])[1].confirmations[0];
    expect(legacy.executions).toBeUndefined();

    const pending = transcriptToTurns(TWO_TURNS, null, [
      recordOf({ executions: [executionOf()] }),
    ])[1].confirmations[0];
    expect(pending.executions).toBeUndefined();

    const emptyList = transcriptToTurns(TWO_TURNS, null, [
      recordOf({ status: "approved", executions: [] }),
    ])[1].confirmations[0];
    expect(emptyList.executions).toBeUndefined();
  });
});

describe("detectArrivalSpan (SPEC-034 R-1 / SPEC-035 R-4)", () => {
  it("returns null when the reseed changed no content", () => {
    const previous = [turnOf("Done.")];
    const next = [turnOf("Done.")];
    expect(detectArrivalSpan(previous, next)).toBeNull();
  });

  it("returns null for a card-only flip (deny/expiry, no resumed reply)", () => {
    const previous = [turnOf("Parked.")];
    const next = [turnOf("Parked.")];
    next[0].confirmations = [
      {
        confirmId: "cf-1",
        message: "",
        pendingCalls: [],
        mutating: false,
        status: "denied",
        sessionId: "s-1",
      },
    ];
    expect(detectArrivalSpan(previous, next)).toBeNull();
  });

  it("points at the turn whose reply grew, keeping the seen prefix", () => {
    const parked = "Asking for approval…";
    const previous = [turnOf(parked)];
    const next = [turnOf(`${parked}\n\nRestarted the pod.`)];
    // The reveal starts where the operator stopped reading.
    expect(detectArrivalSpan(previous, next)).toEqual({
      from: 0,
      prevReplyChars: parked.length,
    });
  });

  it("points at appended turns when the resume started a new exchange", () => {
    const previous = [turnOf("First.")];
    const next = [turnOf("First."), turnOf("Second.")];
    expect(detectArrivalSpan(previous, next)).toEqual({
      from: 1,
      prevReplyChars: 0,
    });
  });

  it("points at the earliest changed turn when both grew", () => {
    const previous = [turnOf("One."), turnOf("Two.")];
    const next = [turnOf("One."), turnOf("Two. More."), turnOf("Three.")];
    expect(detectArrivalSpan(previous, next)).toEqual({
      from: 1,
      prevReplyChars: "Two.".length,
    });
  });
});
