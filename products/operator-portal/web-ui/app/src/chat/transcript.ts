// Transcript seeding (SPEC-023 R-3): map the SPEC-022 transcript shape
// into the chat turn model so a resumed session renders like a live one.
import type { TranscriptTurn } from "../api/sessions";
import type { ChatTurn } from "../stream/useChatStream";

export function transcriptToTurns(transcript: TranscriptTurn[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  const makeTurn = (userMessage: string): ChatTurn => ({
    id: `history-${crypto.randomUUID()}`,
    userMessage,
    replyText: "",
    completed: true,
    confirmationPending: false,
    toolCalls: [],
    toolResults: [],
    confirmations: [],
    history: true,
  });

  for (const turn of transcript) {
    if (turn.role === "user") {
      turns.push(makeTurn(turn.content));
      continue;
    }
    const current = turns[turns.length - 1];
    if (current) {
      current.replyText += (current.replyText ? "\n\n" : "") + turn.content;
    } else {
      // Assistant turn without a preceding user turn — keep it visible.
      const orphan = makeTurn("");
      orphan.replyText = turn.content;
      turns.push(orphan);
    }
  }
  return turns;
}
