// Transcript seeding tests (SPEC-023 R-3): the SPEC-022 transcript shape
// must map into turn pairs that render like live turns.
// SPEC-025 R-3: persisted evidence groups attach by turn_index so replay
// renders the same evidence card the live stream showed.
import { describe, expect, it } from "vitest";
import type { EvidenceTurn, TranscriptTurn } from "../../api/sessions";
import { transcriptToTurns } from "../transcript";

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
  it("attaches a group to the assistant turn at its turn_index", () => {
    const turns = transcriptToTurns(TWO_TURNS, [evidenceGroup(1)]);
    expect(turns[0].toolCalls).toEqual([]);
    expect(turns[1].toolCalls).toHaveLength(1);
    expect(turns[1].toolResults).toHaveLength(1);
    expect(turns[1].requestId).toBe("req-1");
  });

  it("maps frames to the exact live-stream frame shape", () => {
    // Prop-identical to what the SSE decoder produces for the same
    // frames — one component renders both, so the shapes must match.
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
