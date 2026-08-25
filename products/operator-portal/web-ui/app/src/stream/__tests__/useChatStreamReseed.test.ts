// useChatStream re-seed tests (SPEC-032 v0.14.1 fix): setSession called
// for the session already on screen stashes the current turns and then
// restores that same cache entry, so a passed-in history never applies —
// the pending-decision poll's apply was silently shadowed by the stale
// cached turns and the owner window stayed deaf after an external
// decision. reseedTurns is the authoritative same-session re-seed: it
// replaces the live turns AND the cache entry, and it is a no-op for any
// session other than the one on screen.
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ChatTurn } from "../useChatStream";
import { useChatStream } from "../useChatStream";

function turnOf(id: string, overrides: Partial<ChatTurn> = {}): ChatTurn {
  return {
    id,
    userMessage: `message ${id}`,
    replyText: "",
    completed: false,
    confirmationPending: false,
    toolCalls: [],
    toolResults: [],
    confirmations: [],
    ...overrides,
  };
}

describe("useChatStream same-session re-seed (SPEC-032)", () => {
  it("documents the setSession cache shadow it must not rely on", () => {
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.setSession("s-1", [turnOf("t-stale")]));
    expect(result.current.turns.map((turn) => turn.id)).toEqual(["t-stale"]);

    // A same-session setSession with fresh history hands back the stale
    // cached turns: the stash-then-restore cache hit wins over history.
    act(() => result.current.setSession("s-1", [turnOf("t-fresh")]));
    expect(result.current.turns.map((turn) => turn.id)).toEqual(["t-stale"]);
  });

  it("reseedTurns replaces the live turns and the cache entry", () => {
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.setSession("s-1", [turnOf("t-stale")]));

    act(() => result.current.reseedTurns("s-1", [turnOf("t-fresh")]));
    expect(result.current.turns.map((turn) => turn.id)).toEqual(["t-fresh"]);

    // Switching away and back restores the reseeded timeline, not the
    // shadowed stale one.
    act(() => result.current.setSession("s-2", [turnOf("t-other")]));
    act(() => result.current.setSession("s-1"));
    expect(result.current.turns.map((turn) => turn.id)).toEqual(["t-fresh"]);
  });

  it("reseedTurns is a no-op for a session not on screen", () => {
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.setSession("s-1", [turnOf("t-1")]));

    act(() => result.current.reseedTurns("s-2", [turnOf("t-intruder")]));
    expect(result.current.turns.map((turn) => turn.id)).toEqual(["t-1"]);
    expect(result.current.sessionId).toBe("s-1");

    // The rejected re-seed also never poisoned the other session's cache.
    act(() => result.current.setSession("s-2"));
    expect(result.current.turns).toEqual([]);
  });
});
