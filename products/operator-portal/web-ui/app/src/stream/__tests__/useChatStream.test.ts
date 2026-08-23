// useChatStream tests (SPEC-023 R-2): turn accumulation, HITL park/resume,
// card locking semantics, and session-switch abort. fetch is stubbed with
// canned SSE bodies; nothing here touches a real gateway.
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useChatStream } from "../useChatStream";

const encoder = new TextEncoder();

function sse(...payloads: Record<string, unknown>[]): string {
  return payloads
    .map((payload) => `data: ${JSON.stringify(payload)}\n\n`)
    .join("");
}

function streamBody(text: string): AsyncGenerator<Uint8Array> {
  return (async function* () {
    yield encoder.encode(text);
  })();
}

interface FakeResponse {
  ok: boolean;
  status: number;
  body: AsyncGenerator<Uint8Array> | null;
}

function queueFetch(...responses: FakeResponse[]) {
  const calls: { url: string; init?: RequestInit }[] = [];
  let index = 0;
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const response = responses[index] ?? responses[responses.length - 1];
    index += 1;
    return Promise.resolve(response);
  });
  return calls;
}

const okStream = (text: string): FakeResponse => ({
  ok: true,
  status: 200,
  body: streamBody(text),
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useChatStream", () => {
  it("accumulates deltas, learns the session id, and marks completion", async () => {
    queueFetch(
      okStream(
        sse(
          { type: "message_start", session_id: "s-1" },
          { type: "message_delta", delta: "Hello ", session_id: "s-1" },
          { type: "message_delta", delta: "world", session_id: "s-1" },
          { type: "message_end", session_id: "s-1" },
        ),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send("hi there", { userId: "amy" });
    });

    expect(result.current.sessionId).toBe("s-1");
    expect(result.current.streaming).toBe(false);
    const turn = result.current.turns[0];
    expect(turn?.userMessage).toBe("hi there");
    expect(turn?.replyText).toBe("Hello world");
    expect(turn?.completed).toBe(true);
  });

  it("completes a turn when the stream closes without a terminal frame", async () => {
    // Live dev-k8s capture (SPEC-023 walkthrough): the kernel may emit
    // empty message_delta frames and close the stream right after the
    // last delta, with no message_end. The turn must still complete so
    // the bubble stops loading (legacy parity).
    queueFetch(
      okStream(
        sse(
          { type: "message_delta", session_id: "s-1" },
          { type: "message_delta", delta: "p", session_id: "s-1" },
          { type: "message_delta", delta: "ong", session_id: "s-1" },
          { type: "message_delta", session_id: "s-1" },
        ),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send("ping", { userId: "amy" });
    });

    expect(result.current.streaming).toBe(false);
    const turn = result.current.turns[0];
    expect(turn?.replyText).toBe("pong");
    expect(turn?.completed).toBe(true);
    expect(turn?.confirmationPending).toBe(false);
  });

  it("parks on confirmation_request and resumes via POST confirm", async () => {
    const calls = queueFetch(
      okStream(
        sse(
          { type: "message_delta", delta: "Checking… ", session_id: "s-1" },
          {
            type: "confirmation_request",
            confirm_id: "cf-1",
            message: "Restart the pod?",
            session_id: "s-1",
            pending_calls: [
              {
                tool_name: "k8s.restart_pod",
                call_id: "c-2",
                risk_level: "write",
              },
            ],
          },
        ),
      ),
      okStream(
        sse(
          { type: "confirmation_result", confirm_id: "cf-1", status: "approved" },
          { type: "tool_call", call_id: "c-2", tool_name: "k8s.restart_pod" },
          {
            type: "tool_result",
            call_id: "c-2",
            tool_name: "k8s.restart_pod",
            status: "success",
            session_id: "s-1",
          },
          { type: "message_delta", delta: "Done.", session_id: "s-1" },
          { type: "message_end", session_id: "s-1" },
        ),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send("restart it", { userId: "amy" });
    });

    const turn = result.current.turns[0];
    expect(turn?.confirmationPending).toBe(true);
    expect(turn?.completed).toBe(false);
    expect(turn?.confirmations[0]).toMatchObject({
      confirmId: "cf-1",
      status: "pending",
      mutating: true,
      sessionId: "s-1",
    });

    await act(async () => {
      await result.current.decide("cf-1", "approve");
    });

    // The confirm call POSTs the parked session/confirm ids.
    const confirmCall = calls[1];
    expect(confirmCall?.url).toContain("/api/v1/chat/confirm");
    expect(JSON.parse(String(confirmCall?.init?.body))).toEqual({
      session_id: "s-1",
      confirm_id: "cf-1",
      decision: "approve",
    });

    const after = result.current.turns[0];
    expect(after?.confirmations[0]).toMatchObject({
      status: "approved",
      note: "Approved — the parked reply resumed.",
    });
    // Resumed frames attach to the same turn (parked-turn restoration).
    expect(after?.replyText).toBe("Checking… Done.");
    expect(after?.toolCalls).toHaveLength(1);
    expect(after?.toolResults).toHaveLength(1);
    expect(after?.completed).toBe(true);
  });

  it("locks the card as expired on HTTP 410", async () => {
    queueFetch(
      okStream(
        sse({
          type: "confirmation_request",
          confirm_id: "cf-1",
          session_id: "s-1",
          pending_calls: [],
        }),
      ),
      { ok: false, status: 410, body: null },
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send("restart it", { userId: "amy" });
    });
    await act(async () => {
      await result.current.decide("cf-1", "deny");
    });

    expect(result.current.turns[0]?.confirmations[0]).toMatchObject({
      status: "expired",
      note: "This confirmation expired before a decision was applied.",
    });
  });

  it("locks the card as error when the resumed stream ends without confirmation_result", async () => {
    queueFetch(
      okStream(
        sse({
          type: "confirmation_request",
          confirm_id: "cf-1",
          session_id: "s-1",
          pending_calls: [],
        }),
      ),
      okStream(
        sse({ type: "message_delta", delta: "partial", session_id: "s-1" }),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send("restart it", { userId: "amy" });
    });
    await act(async () => {
      await result.current.decide("cf-1", "approve");
    });

    expect(result.current.turns[0]?.confirmations[0]).toMatchObject({
      status: "error",
      note: "The confirmation stream ended unexpectedly.",
    });
  });

  it("locks the card from a mid-stream error frame", async () => {
    queueFetch(
      okStream(
        sse({
          type: "confirmation_request",
          confirm_id: "cf-1",
          session_id: "s-1",
          pending_calls: [],
        }),
      ),
      okStream(
        sse({
          type: "error",
          error: { code: "confirmation_owner_mismatch", message: "wrong owner" },
        }),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send("restart it", { userId: "amy" });
    });
    await act(async () => {
      await result.current.decide("cf-1", "approve");
    });

    expect(result.current.turns[0]?.confirmations[0]).toMatchObject({
      status: "error",
      note: "wrong owner",
    });
  });

  it("keeps the card pending and retryable on a non-terminal confirm failure", async () => {
    queueFetch(
      okStream(
        sse({
          type: "confirmation_request",
          confirm_id: "cf-1",
          session_id: "s-1",
          pending_calls: [],
        }),
      ),
      { ok: false, status: 502, body: null },
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send("restart it", { userId: "amy" });
    });
    await act(async () => {
      await result.current.decide("cf-1", "approve");
    });

    expect(result.current.turns[0]?.confirmations[0]).toMatchObject({
      status: "pending",
      note: "Confirm request failed (502).",
    });
  });

  it("clears turns and repoints the session on setSession (switch abort)", async () => {
    queueFetch(
      okStream(
        sse(
          { type: "message_delta", delta: "first", session_id: "s-1" },
          { type: "message_end", session_id: "s-1" },
        ),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send("hi", { userId: "amy" });
    });
    expect(result.current.turns).toHaveLength(1);

    act(() => {
      result.current.setSession("s-2");
    });
    expect(result.current.turns).toHaveLength(0);
    expect(result.current.sessionId).toBe("s-2");
    expect(result.current.streaming).toBe(false);
  });

  it("maps a 401 stream open to the sign-in message", async () => {
    queueFetch({ ok: false, status: 401, body: null });

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send("hi", { userId: "amy" });
    });

    expect(result.current.turns[0]?.error).toBe(
      "Not authenticated. Please sign in from the sidebar first.",
    );
  });

  // SPEC-023 R-4 invariant II: a voice-composed turn can park a
  // confirmation, but the decision surface stays pure — POST confirm
  // carries only {session_id, confirm_id, decision}, never a modality.
  it("keeps input_modality off the confirmation decision surface", async () => {
    const calls = queueFetch(
      okStream(
        sse({
          type: "confirmation_request",
          confirm_id: "cf-v",
          session_id: "s-v",
          pending_calls: [
            { tool_name: "k8s.restart_pod", call_id: "c-v", risk_level: "write" },
          ],
        }),
      ),
      okStream(
        sse(
          { type: "confirmation_result", confirm_id: "cf-v", status: "approved" },
          { type: "message_end", session_id: "s-v" },
        ),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send("restart it", {
        userId: "amy",
        inputModality: "voice",
      });
    });
    expect(calls[0]?.url).toContain("input_modality=voice");

    await act(async () => {
      await result.current.decide("cf-v", "approve");
    });

    const confirmCall = calls[1];
    expect(confirmCall?.url).toContain("/api/v1/chat/confirm");
    expect(JSON.parse(String(confirmCall?.init?.body))).toEqual({
      session_id: "s-v",
      confirm_id: "cf-v",
      decision: "approve",
    });
  });

  // Live-walkthrough defect: a stale workspace pointer (deleted session)
  // rode along on the stream request and the gateway answered with an
  // empty stream, rendering "(no response received)". With the gateway
  // now answering 404 eagerly, send must self-heal: drop the pointer and
  // retry once with server-side auto-creation.
  it("retries without the session id after a 404 stale-session open", async () => {
    const calls = queueFetch(
      { ok: false, status: 404, body: null },
      okStream(
        sse(
          { type: "message_start", session_id: "s-new" },
          { type: "message_delta", delta: "recovered", session_id: "s-new" },
          { type: "message_end", session_id: "s-new" },
        ),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.setSession("s-deleted", []);
    });
    await act(async () => {
      await result.current.send("list pods running", { userId: "amy" });
    });

    expect(calls[0]?.url).toContain("session_id=s-deleted");
    expect(calls[1]?.url).not.toContain("session_id=");
    expect(result.current.sessionId).toBe("s-new");
    const turn = result.current.turns[0];
    expect(turn?.replyText).toBe("recovered");
    expect(turn?.completed).toBe(true);
    expect(turn?.error).toBeUndefined();
  });

  it("surfaces the error when the retry after a 404 also fails", async () => {
    queueFetch(
      { ok: false, status: 404, body: null },
      { ok: false, status: 502, body: null },
    );

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.setSession("s-deleted", []);
    });
    await act(async () => {
      await result.current.send("hi", { userId: "amy" });
    });

    expect(result.current.sessionId).toBeNull();
    const turn = result.current.turns[0];
    expect(turn?.error).toContain("502");
    expect(turn?.completed).toBe(false);
  });
});
