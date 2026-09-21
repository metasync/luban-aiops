// TurnGroup render-order test (#3): after a remote approval lands, the
// post-approval "working" indicator must appear under the reply and ABOVE
// the tool-evidence panel, so the operator reads "the agent resumed" before
// the still-growing evidence below it. Also asserts the indicator is
// clearly labelled and absent when the turn is not settling.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
import { CopyPasswordControl, TurnGroup } from "../ChatView";
import { saveAuthSession } from "../../auth/storage";
import type { SecretDeliveryFrame } from "../../stream/models";

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
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("Copy password (SPEC-062)", () => {
  const delivery: SecretDeliveryFrame = { kind: "secret_delivery", channel: "portal_copy",
    deliveryId: "11111111-1111-4111-8111-111111111111", expiresAt: "2030-01-01T00:00:00Z" };
  const value = "test-only-generated-secret!";
  function prepare(copyFails = false) {
    saveAuthSession({ access_token: "test-token" });
    const writeText = copyFails ? vi.fn().mockRejectedValue(new Error(value)) : vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const payload = { value: value as string | undefined };
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
    vi.stubGlobal("fetch", fetcher);
    return { fetcher, writeText, payload };
  }

  it("redeems on click only, copies once, and never retains plaintext", async () => {
    const { fetcher, writeText, payload } = prepare();
    const view = render(<CopyPasswordControl delivery={delivery} />);
    expect(fetcher).not.toHaveBeenCalled();
    const button = screen.getByRole("button", { name: /Copy password/ });
    fireEvent.click(button);
    fireEvent.click(button);
    await screen.findByRole("button", { name: /Password copied/ });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][1]).toMatchObject({ cache: "no-store", redirect: "error",
      headers: { authorization: "Bearer test-token" } });
    expect(writeText).toHaveBeenCalledExactlyOnceWith(value);
    expect(payload.value).toBeUndefined();
    expect(view.container.innerHTML).not.toContain(value);
    expect(JSON.stringify(sessionStorage)).not.toContain(value);
    expect(JSON.stringify(localStorage)).not.toContain(value);
    view.unmount();
    render(<CopyPasswordControl delivery={delivery} />);
    expect(screen.getByRole("button", { name: /Password unavailable/ })).toHaveProperty("disabled", true);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("does not redeem expired handles", () => {
    const { fetcher } = prepare();
    render(<CopyPasswordControl delivery={{ ...delivery, expiresAt: "2000-01-01T00:00:00Z" }} />);
    expect(screen.getByRole("button", { name: /Password expired/ })).toHaveProperty("disabled", true);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("treats clipboard rejection as spent and never shows its error text", async () => {
    const { writeText } = prepare(true);
    const view = render(<CopyPasswordControl delivery={delivery} />);
    fireEvent.click(screen.getByRole("button", { name: /Copy password/ }));
    await screen.findByRole("button", { name: /Password unavailable/ });
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(view.container.innerHTML).not.toContain(value);
  });

  it.each(["authentication", "clipboard"])("does not redeem without %s", async (missing) => {
    const { fetcher } = prepare();
    if (missing === "authentication") sessionStorage.clear();
    else vi.stubGlobal("navigator", {});
    render(<CopyPasswordControl delivery={delivery} />);
    fireEvent.click(screen.getByRole("button", { name: /Copy password/ }));
    await screen.findByRole("button", { name: /Password unavailable/ });
    expect(fetcher).not.toHaveBeenCalled();
  });
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
