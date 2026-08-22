// Transcript seeding tests (SPEC-023 R-3): the SPEC-022 transcript shape
// must map into turn pairs that render like live turns.
import { describe, expect, it } from "vitest";
import type { TranscriptTurn } from "../../api/sessions";
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
