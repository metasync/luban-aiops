// TurnGroup render-order test (#3): after a remote approval lands, the
// post-approval "working" indicator must appear under the reply and ABOVE
// the tool-evidence panel, so the operator reads "the agent resumed" before
// the still-growing evidence below it. Also asserts the indicator is
// clearly labelled and absent when the turn is not settling.
import { cleanup, render, screen } from "@testing-library/react";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import type { ChatTurn } from "../../stream/useChatStream";
import { TurnGroup } from "../ChatView";

// TurnGroup installs an IntersectionObserver for the sticky request banner;
// jsdom does not provide one, so stub it (mirrors the ResizeObserver stub in
// src/test/setup.ts). These tests assert DOM order, not visibility geometry.
class IntersectionObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): [] {
    return [];
  }
}

// useToolNameMap fetches the tool catalog on mount; stub it to an empty map
// so the test never touches the network and renders deterministically.
vi.mock("../useToolNames", () => ({ useToolNameMap: () => new Map() }));

const installedObserver = globalThis.IntersectionObserver;

beforeAll(() => {
  globalThis.IntersectionObserver =
    IntersectionObserverStub as unknown as typeof IntersectionObserver;
});

afterAll(() => {
  globalThis.IntersectionObserver = installedObserver;
});

// Vitest globals are off, so testing-library's auto-cleanup never registers;
// unmount explicitly to keep renders isolated.
afterEach(() => {
  cleanup();
});

function turnOf(overrides: Partial<ChatTurn> = {}): ChatTurn {
  return {
    id: "t-1",
    userMessage: "Reset the password for ana@example.com",
    replyText: "Resuming the reset flow now.",
    completed: false,
    confirmationPending: false,
    toolCalls: [],
    // One landed tool frame is enough to render the evidence panel, which
    // is what the indicator must sit above.
    toolResults: [
      {
        kind: "tool_result",
        callId: "c-1",
        toolName: "web.snapshot",
        status: "success",
      },
    ],
    confirmations: [],
    ...overrides,
  };
}

function renderTurn(agentWorking: boolean) {
  return render(
    <TurnGroup
      turn={turnOf()}
      canDecide={false}
      busy={false}
      onDecide={() => {}}
      agentWorking={agentWorking}
    />,
  );
}

describe("TurnGroup post-approval indicator (#3)", () => {
  it("renders a labelled working indicator above the tool evidence", () => {
    const { container } = renderTurn(true);
    const indicator = screen.getByTestId("agent-working-indicator");
    expect(screen.getByText("Agent is working…")).toBeTruthy();

    // The evidence panel (a Collapse rooted at .evidence-turn) must come
    // AFTER the indicator in document order — the whole point of #3.
    const evidence = container.querySelector(".evidence-turn");
    expect(evidence).toBeTruthy();
    const position = indicator.compareDocumentPosition(evidence!);
    // Node.DOCUMENT_POSITION_FOLLOWING === 4: evidence follows indicator.
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("omits the indicator when the turn is not settling", () => {
    renderTurn(false);
    expect(screen.queryByTestId("agent-working-indicator")).toBeNull();
    expect(screen.queryByText("Agent is working…")).toBeNull();
  });
});
