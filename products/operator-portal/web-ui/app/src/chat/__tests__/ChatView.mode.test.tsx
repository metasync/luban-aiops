// ChatView mode tests (SPEC-056 R-2 / R-3 / R-5).
//
// R-3 — the authoring controls split by mode: Chat (operation) keeps Draft-as-
// skill and loses both develop-as-you-go controls; Studio (development) keeps
// Declare-target + Graduate-as-skill and loses Draft. Neither mode offers a
// conversion, because an operation session's trace is multi-origin and
// graduating it would deterministically refuse.
//
// R-5 — the blast-radius control: `mode` may select the visible controls, the
// birth `session_type` and the list scope, and NOTHING in the trust path. The
// last test feeds both modes one fixed transcript and compares the rendered
// message area byte-for-byte; a fork of the SSE projection, the secret-masking
// renderer or the HITL card makes the two strings differ and fails the suite.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Modal } from "antd";
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import type { ChatTurn } from "../../stream/useChatStream";
import type {
  SessionMode,
  SessionWorkspace,
} from "../../sessions/useSessionWorkspace";
import ChatView from "../ChatView";

const {
  mockUseAuth,
  mockUseChatStream,
  mockCreateDevelopmentSession,
  mockCreateAndOpen,
} = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockUseChatStream: vi.fn(),
  mockCreateDevelopmentSession: vi.fn(),
  mockCreateAndOpen: vi.fn(),
}));

vi.mock("../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));

// The stream adapter is the trust core under test, so it is driven rather than
// exercised: both modes get the same fixed timeline and the assertion is that
// the projection is identical.
vi.mock("../../stream/useChatStream", () => ({
  useChatStream: mockUseChatStream,
}));

vi.mock("../../api/sessions", () => ({
  getSession: vi.fn(async () => ({
    session_id: "ses-fixed",
    transcript: [],
    transcript_available: false,
  })),
  createSkillDraft: vi.fn(),
  declareSkillTarget: vi.fn(),
  graduateSessionSkill: vi.fn(),
}));

vi.mock("../../api/models", () => ({
  getModelCatalog: vi.fn(async () => ({ models: [], default: null })),
}));

// Fetches the tool catalog on mount; stubbed so the suite never touches the
// network and renders deterministically (mirrors TurnGroup.test.tsx).
vi.mock("../useToolNames", () => ({ useToolNameMap: () => new Map() }));

// The bounded re-seed poll would otherwise fire on its own cadence; the
// arrival/settling state it owns is not what this suite asserts.
vi.mock("../usePendingDecisionPoll", () => ({
  usePendingDecisionPoll: () => ({ settling: false }),
}));

vi.mock("../../voice/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    supported: false,
    listening: false,
    error: null,
    start: vi.fn(),
    stop: vi.fn(),
  }),
}));

// TurnGroup installs an IntersectionObserver for the sticky request banner;
// jsdom does not provide one.
class IntersectionObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): [] {
    return [];
  }
}

const installedObserver = globalThis.IntersectionObserver;

beforeAll(() => {
  globalThis.IntersectionObserver =
    IntersectionObserverStub as unknown as typeof IntersectionObserver;
});

afterAll(() => {
  globalThis.IntersectionObserver = installedObserver;
});

// Vitest globals are off, so testing-library's auto-cleanup never registers.
afterEach(() => {
  cleanup();
  Modal.destroyAll();
  vi.restoreAllMocks();
});

function signIn(roles: string[] = ["operator"]) {
  mockUseAuth.mockReturnValue({
    booting: false,
    session: { access_token: "token" },
    authError: null,
    username: "op-one",
    roles,
    login: vi.fn(async () => {}),
    logout: vi.fn(async () => {}),
  });
}

function sessionIdOf(mode: SessionMode): string {
  return mode === "development" ? "ses-dev-1" : "ses-op-1";
}

function workspaceOf(mode: SessionMode): SessionWorkspace {
  const sessionId = sessionIdOf(mode);
  return {
    // The list itself is already mode-scoped server-side
    // (`?session_type=<mode>`), so what arrives here is homogeneous by
    // construction — a Studio session can never appear in Chat's panel.
    sessions: [
      {
        session_id: sessionId,
        title: mode === "development" ? "reset a password" : "check the pods",
        created_at: new Date().toISOString(),
        last_active_at: null,
        pending_confirmation: false,
        session_type: mode,
      },
    ],
    loading: false,
    error: null,
    activeSessionId: sessionId,
    setActiveSessionId: vi.fn(),
    refresh: vi.fn(async () => {}),
    createAndOpen: mockCreateAndOpen,
    createDevelopmentSession: mockCreateDevelopmentSession,
    remove: vi.fn(async () => ({ ok: true })),
    rename: vi.fn(async () => ({ ok: true })),
    pinned: [],
    pinIncidentSession: vi.fn(() => "incident-1"),
  };
}

function streamOf(turns: ChatTurn[], sessionId: string | null) {
  mockUseChatStream.mockReturnValue({
    turns,
    sessionId,
    streaming: false,
    lastRequestId: null,
    send: vi.fn(async () => {}),
    decide: vi.fn(async () => {}),
    setSession: vi.fn(),
    reseedTurns: vi.fn(),
  });
}

beforeEach(() => {
  mockUseAuth.mockReset();
  mockUseChatStream.mockReset();
  mockCreateDevelopmentSession.mockReset();
  mockCreateAndOpen.mockReset();
  mockCreateAndOpen.mockResolvedValue("ses-new");
  mockCreateDevelopmentSession.mockResolvedValue({
    ok: true,
    sessionId: "ses-dev-2",
  });
  signIn();
  streamOf([], null);
});

describe("ChatView authoring controls by mode (SPEC-056 R-3)", () => {
  it("renders Draft-as-skill only in operation mode", () => {
    render(<ChatView workspace={workspaceOf("operation")} mode="operation" />);
    expect(screen.getByLabelText("Draft as skill")).toBeTruthy();
    expect(screen.queryByLabelText("Declare skill target")).toBeNull();
    expect(screen.queryByLabelText("Graduate as skill")).toBeNull();
  });

  it("renders Declare-target + Graduate-as-skill only in development mode", () => {
    render(
      <ChatView workspace={workspaceOf("development")} mode="development" />,
    );
    expect(screen.getByLabelText("Declare skill target")).toBeTruthy();
    expect(screen.getByLabelText("Graduate as skill")).toBeTruthy();
    expect(screen.queryByLabelText("Draft as skill")).toBeNull();
  });

  it("defaults to operation mode when no prop is given", () => {
    render(<ChatView workspace={workspaceOf("operation")} />);
    expect(screen.getByLabelText("Draft as skill")).toBeTruthy();
    expect(screen.queryByLabelText("Declare skill target")).toBeNull();
    expect(screen.queryByLabelText("Graduate as skill")).toBeNull();
  });

  it.each<[SessionMode]>([["operation"], ["development"]])(
    "offers no conversion control in %s mode",
    (mode) => {
      render(<ChatView workspace={workspaceOf(mode)} mode={mode} />);
      // R-3 trust invariant: an operation session is multi-origin, so
      // "Move to Studio" would only manufacture a graduation refusal.
      expect(screen.queryByText(/move to studio/i)).toBeNull();
      expect(screen.queryByText(/convert/i)).toBeNull();
    },
  );
});

describe("ChatView create affordance by mode (SPEC-056 R-3)", () => {
  it("keeps only the one-click New in Chat, with no develop-as-you-go opener", async () => {
    const workspace = workspaceOf("operation");
    render(<ChatView workspace={workspace} mode="operation" />);
    expect(screen.getByLabelText("New session")).toBeTruthy();
    expect(screen.queryByLabelText("New skill development session")).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByLabelText("New session"));
    });
    expect(mockCreateAndOpen).toHaveBeenCalled();
    // Nothing in Chat can mint a development session.
    expect(mockCreateDevelopmentSession).not.toHaveBeenCalled();
    expect(screen.queryByText("New skill-development session")).toBeNull();
  });

  it("keeps only the develop-as-you-go opener in Studio", () => {
    render(
      <ChatView workspace={workspaceOf("development")} mode="development" />,
    );
    expect(screen.getByLabelText("New skill development session")).toBeTruthy();
    expect(screen.queryByLabelText("New session")).toBeNull();
  });

  it("treats the birth target as optional (R-2)", async () => {
    render(
      <ChatView workspace={workspaceOf("development")} mode="development" />,
    );
    await act(async () => {
      fireEvent.click(screen.getByLabelText("New skill development session"));
    });
    expect(await screen.findByText("New skill-development session")).toBeTruthy();
    // The submit stays enabled with the field blank: the type is fixed by the
    // mode, never inferred from whether a target happened to be named.
    const open = screen.getByText("Open session");
    expect((open.closest("button") as HTMLButtonElement).disabled).toBe(false);
    await act(async () => {
      fireEvent.click(open);
    });
    expect(mockCreateDevelopmentSession).toHaveBeenCalledWith(undefined);
  });

  it("forwards a target named at birth", async () => {
    render(
      <ChatView workspace={workspaceOf("development")} mode="development" />,
    );
    await act(async () => {
      fireEvent.click(screen.getByLabelText("New skill development session"));
    });
    await act(async () => {
      fireEvent.change(await screen.findByLabelText("Skill development target"), {
        target: { value: "https://admin.internal/login" },
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Open session"));
    });
    expect(mockCreateDevelopmentSession).toHaveBeenCalledWith(
      "https://admin.internal/login",
    );
  });

  it("reports a refused create inline and keeps the dialog open", async () => {
    mockCreateDevelopmentSession.mockResolvedValue({
      ok: false,
      sessionId: null,
      // The gateway's dual-gate refusal (R-6) is the operator's to read.
      message: "Your role cannot open a skill-development session.",
    });
    render(
      <ChatView workspace={workspaceOf("development")} mode="development" />,
    );
    await act(async () => {
      fireEvent.click(screen.getByLabelText("New skill development session"));
    });
    await act(async () => {
      fireEvent.click(await screen.findByText("Open session"));
    });
    expect(
      await screen.findByText("Your role cannot open a skill-development session."),
    ).toBeTruthy();
    expect(screen.getByText("New skill-development session")).toBeTruthy();
  });
});

describe("ChatView shared core is mode-invariant (SPEC-056 R-5)", () => {
  // One fixed transcript exercising every trust-path surface at once: markdown
  // reply rendering, tool evidence, the change-request projection with a
  // kernel-masked secret value, and a pending HITL confirmation card.
  const FIXED_TURNS: ChatTurn[] = [
    {
      id: "t-1",
      userMessage: "Reset the password for ana@example.com",
      replyText:
        "I opened the admin console and **parked** the reset for approval.",
      completed: false,
      confirmationPending: true,
      history: true,
      toolCalls: [
        {
          kind: "tool_call",
          callId: "c-1",
          toolName: "web.type",
          parameters: { ref: "e12", text: "***" },
        },
      ],
      toolResults: [
        {
          kind: "tool_result",
          callId: "c-1",
          toolName: "web.type",
          status: "success",
        },
      ],
      confirmations: [
        {
          confirmId: "cf-1",
          message: "Approve this change before the agent continues?",
          mutating: true,
          status: "pending",
          sessionId: "ses-fixed",
          approvalKind: "action",
          pendingCalls: [
            {
              callId: "c-2",
              toolName: "web.type",
              riskLevel: "write",
              action: "tools:mutate",
              displayHint: "Password field on the user detail form",
              changeRequest: {
                summary: "Set a new password for ana@example.com",
                fields: [
                  { label: "Account", value: "ana@example.com" },
                  { label: "New password", value: "***", masked: true },
                ],
              },
              parameters: { ref: "e13", text: "***" },
            },
          ],
        },
      ],
    },
  ];

  function renderMessages(mode: SessionMode): string {
    // Both modes are pointed at the same session so the ONLY difference
    // between the two renders is `mode` itself.
    streamOf(FIXED_TURNS, "ses-fixed");
    const workspace = workspaceOf(mode);
    workspace.activeSessionId = "ses-fixed";
    workspace.sessions = [
      {
        session_id: "ses-fixed",
        title: "reset a password",
        created_at: new Date().toISOString(),
        last_active_at: null,
        pending_confirmation: true,
        session_type: mode,
      },
    ];
    const { container } = render(<ChatView workspace={workspace} mode={mode} />);
    const messages = container.querySelector(".chat-messages");
    expect(messages).toBeTruthy();
    return (messages as HTMLElement).innerHTML;
  }

  it("renders the transcript surface identically in both modes", () => {
    const operationHtml = renderMessages("operation");
    cleanup();
    Modal.destroyAll();
    const developmentHtml = renderMessages("development");

    // Non-vacuous: the trust path really rendered — the change-request
    // summary, the kernel-masked secret value and its `masked` tag are all
    // inside the compared container.
    expect(operationHtml).toContain("Set a new password for ana@example.com");
    expect(operationHtml).toContain("***");
    expect(operationHtml).toContain("masked");
    expect(operationHtml.length).toBeGreaterThan(500);

    // The invariant: one projection, not two. Any divergence in the stream
    // adapter, the secret masking, the change-request rendering or the
    // confirmation card makes these two strings differ and fails.
    expect(developmentHtml).toBe(operationHtml);
  });

  it("differs only in the mode-specific controls around that core", () => {
    streamOf(FIXED_TURNS, "ses-fixed");
    const { container: operationContainer } = render(
      <ChatView workspace={workspaceOf("operation")} mode="operation" />,
    );
    const operationHeader = operationContainer.querySelector(
      ".chat-session-header",
    )?.textContent;
    cleanup();
    Modal.destroyAll();

    streamOf(FIXED_TURNS, "ses-fixed");
    const { container: developmentContainer } = render(
      <ChatView workspace={workspaceOf("development")} mode="development" />,
    );
    const developmentHeader = developmentContainer.querySelector(
      ".chat-session-header",
    )?.textContent;

    expect(operationHeader).toContain("Draft as skill");
    expect(operationHeader).not.toContain("Graduate as skill");
    expect(developmentHeader).toContain("Graduate as skill");
    expect(developmentHeader).toContain("Declare target");
    expect(developmentHeader).not.toContain("Draft as skill");
    expect(developmentHeader).not.toBe(operationHeader);
  });
});
