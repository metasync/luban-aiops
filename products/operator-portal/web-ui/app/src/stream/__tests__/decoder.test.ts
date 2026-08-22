// Fixture tests for the SSE decoder (SPEC-023 R-2). The fixtures cover the
// full stream schema v6 vocabulary the legacy app.js dispatched on.
import { describe, expect, it } from "vitest";
import { SseLineDecoder, decodeEventBlock } from "../decoder";

function sseBlock(payload: Record<string, unknown>): string {
  return `data: ${JSON.stringify(payload)}`;
}

describe("decodeEventBlock", () => {
  it("maps message_delta frames with a truthy delta to delta frames", () => {
    const decoded = decodeEventBlock(
      sseBlock({ type: "message_delta", delta: "hello", session_id: "s-1" }),
    );
    expect(decoded).toEqual({
      sessionId: "s-1",
      frame: { kind: "delta", text: "hello" },
    });
  });

  it("accepts text_block_start and text_block_delta delta carriers", () => {
    for (const type of ["text_block_start", "text_block_delta"]) {
      const decoded = decodeEventBlock(sseBlock({ type, delta: "x" }));
      expect(decoded?.frame).toEqual({ kind: "delta", text: "x" });
    }
  });

  it("ignores delta-bearing frames outside the type whitelist", () => {
    const decoded = decodeEventBlock(
      sseBlock({ type: "message_start", delta: "nope" }),
    );
    expect(decoded?.frame).toBeNull();
  });

  it("ignores whitelisted types with an empty or missing delta", () => {
    expect(
      decodeEventBlock(sseBlock({ type: "message_delta" }))?.frame,
    ).toBeNull();
    expect(
      decodeEventBlock(sseBlock({ type: "message_delta", delta: "" }))?.frame,
    ).toBeNull();
  });

  it("maps message_end and reply_end to the terminal frame", () => {
    expect(
      decodeEventBlock(sseBlock({ type: "message_end" }))?.frame,
    ).toEqual({ kind: "terminal" });
    expect(
      decodeEventBlock(sseBlock({ type: "reply_end" }))?.frame,
    ).toEqual({ kind: "terminal" });
  });

  it("reads the event kind case-insensitively from type or event", () => {
    const viaType = decodeEventBlock(sseBlock({ type: "Message_END" }));
    expect(viaType?.frame).toEqual({ kind: "terminal" });
    const viaEvent = decodeEventBlock(sseBlock({ event: "Reply_End" }));
    expect(viaEvent?.frame).toEqual({ kind: "terminal" });
  });

  it("maps tool_call frames", () => {
    const decoded = decodeEventBlock(
      sseBlock({
        type: "tool_call",
        call_id: "call-1",
        tool_name: "k8s.get_pods",
        parameters: { namespace: "prod" },
        session_id: "s-1",
      }),
    );
    expect(decoded?.frame).toEqual({
      kind: "tool_call",
      callId: "call-1",
      toolName: "k8s.get_pods",
      parameters: { namespace: "prod" },
    });
  });

  it("maps tool_result frames including evidence, data, and error", () => {
    const decoded = decodeEventBlock(
      sseBlock({
        type: "tool_result",
        call_id: "call-1",
        tool_name: "k8s.get_pod_logs",
        status: "error",
        evidence: {
          executed_at: "2026-08-22T00:00:00Z",
          duration_ms: 412,
          risk_level: "read",
          source_system: "tool-gateway",
        },
        data: { logs: "line-1\nline-2" },
        error: { code: "TOOL_TIMEOUT", message: "deadline exceeded" },
      }),
    );
    expect(decoded?.frame).toEqual({
      kind: "tool_result",
      callId: "call-1",
      toolName: "k8s.get_pod_logs",
      status: "error",
      evidence: {
        executedAt: "2026-08-22T00:00:00Z",
        durationMs: 412,
        riskLevel: "read",
        sourceSystem: "tool-gateway",
      },
      data: { logs: "line-1\nline-2" },
      dataSummary: undefined,
      error: { code: "TOOL_TIMEOUT", message: "deadline exceeded" },
    });
  });

  it("keeps data=null distinct from absent data (expander parity)", () => {
    const withNull = decodeEventBlock(
      sseBlock({ type: "tool_result", status: "success", data: null }),
    );
    const withSummary = decodeEventBlock(
      sseBlock({
        type: "tool_result",
        status: "success",
        data_summary: "3 pods",
      }),
    );
    expect(withNull?.frame).toMatchObject({ kind: "tool_result", data: null });
    expect(withSummary?.frame).toMatchObject({
      kind: "tool_result",
      data: undefined,
      dataSummary: "3 pods",
    });
  });

  it("marks a confirmation_request mutating when any call is non-read", () => {
    const mutating = decodeEventBlock(
      sseBlock({
        type: "confirmation_request",
        confirm_id: "cf-1",
        message: "Approve the restart?",
        pending_calls: [
          { tool_name: "k8s.get_pods", call_id: "c-1", risk_level: "read" },
          {
            tool_name: "k8s.restart_pod",
            call_id: "c-2",
            parameters: { pod: "api-1" },
            risk_level: "write",
          },
        ],
      }),
    );
    expect(mutating?.frame).toMatchObject({
      kind: "confirmation_request",
      confirmId: "cf-1",
      mutating: true,
      pendingCalls: [
        { toolName: "k8s.get_pods", riskLevel: "read" },
        { toolName: "k8s.restart_pod", riskLevel: "write" },
      ],
    });

    const readOnly = decodeEventBlock(
      sseBlock({
        type: "confirmation_request",
        confirm_id: "cf-2",
        pending_calls: [{ tool_name: "k8s.get_pods", risk_level: "read" }],
      }),
    );
    expect(readOnly?.frame).toMatchObject({
      kind: "confirmation_request",
      mutating: false,
    });
  });

  it("maps confirmation_result frames", () => {
    const decoded = decodeEventBlock(
      sseBlock({ type: "confirmation_result", confirm_id: "cf-1", status: "approved" }),
    );
    expect(decoded?.frame).toEqual({
      kind: "confirmation_result",
      confirmId: "cf-1",
      status: "approved",
    });
  });

  it("maps error frames preferring error.message, then message", () => {
    const nested = decodeEventBlock(
      sseBlock({
        type: "error",
        error: { code: "confirmation_owner_mismatch", message: "wrong owner" },
      }),
    );
    expect(nested?.frame).toEqual({ kind: "error", message: "wrong owner" });

    const flat = decodeEventBlock(
      sseBlock({ type: "error", message: "upstream failed" }),
    );
    expect(flat?.frame).toEqual({ kind: "error", message: "upstream failed" });

    const bare = decodeEventBlock(sseBlock({ type: "error" }));
    expect(bare?.frame).toEqual({
      kind: "error",
      message: "The stream reported an error.",
    });
  });

  it("skips non-data blocks and malformed JSON instead of throwing", () => {
    expect(decodeEventBlock(": keep-alive")).toBeNull();
    expect(decodeEventBlock("event: ping")).toBeNull();
    expect(decodeEventBlock("data: {not json")).toBeNull();
    expect(decodeEventBlock("data: [1,2,3]")).toBeNull();
  });
});

describe("SseLineDecoder", () => {
  it("emits events only once their separator arrives", () => {
    const decoder = new SseLineDecoder();
    const first = decoder.push(
      sseBlock({ type: "message_delta", delta: "he", session_id: "s-1" }),
    );
    expect(first).toEqual([]);

    const second = decoder.push(
      `\n\n${sseBlock({ type: "message_delta", delta: "llo" })}\n\n`,
    );
    expect(second.map((event) => event.frame)).toEqual([
      { kind: "delta", text: "he" },
      { kind: "delta", text: "llo" },
    ]);
    expect(second[0]?.sessionId).toBe("s-1");
  });

  it("surfaces session_id even for unmodeled frames", () => {
    const decoder = new SseLineDecoder();
    const events = decoder.push(
      `${sseBlock({ type: "message_start", session_id: "s-9" })}\n\n`,
    );
    expect(events).toHaveLength(1);
    expect(events[0]?.sessionId).toBe("s-9");
    expect(events[0]?.frame).toBeNull();
  });

  it("drops a trailing partial block (legacy parity)", () => {
    const decoder = new SseLineDecoder();
    decoder.push(sseBlock({ type: "message_delta", delta: "partial" }));
    expect(decoder.push("")).toEqual([]);
  });
});
