// App nav and view-wiring tests (SPEC-056 R-2 / R-4 / R-5).
//
// Studio is a peer top-level nav entry beside Chat, gated on STUDIO_ROLES —
// the authoring set, so `developer` / `read-only-observer` / `auditor` keep
// Chat only and Chat's own (broad) gating is unchanged. App owns TWO
// mode-scoped workspaces and renders ONE ChatView parameterized by `mode`;
// the development workspace's polling is gated on a Studio role, and Documents
// — home of the shift-summary picker — is wired to the *operation* workspace.
//
// Every view is replaced by a marker reporting what it was handed: this suite
// asserts App's wiring, not the views' internals (those have their own).
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App, { type ViewId } from "../App";
import type { SessionWorkspace } from "../sessions/useSessionWorkspace";

const { mockUseAuth, mockUseSessionWorkspace, inboxCallback } = vi.hoisted(
  () => ({
    mockUseAuth: vi.fn(),
    mockUseSessionWorkspace: vi.fn(),
    // SPEC-034 R-2's callback: App owns it, and it is what must refresh the
    // session panel the moment a decision lands. Captured here so the wiring
    // test can invoke it without rendering the real inbox.
    inboxCallback: { current: undefined as (() => void) | undefined },
  }),
);

vi.mock("../auth/AuthContext", () => ({ useAuth: mockUseAuth }));

vi.mock("../sessions/useSessionWorkspace", () => ({
  useSessionWorkspace: mockUseSessionWorkspace,
}));

vi.mock("../views/control/ApprovalsView", () => ({
  default: () => <div data-testid="approvals-view" />,
  // The inbox poll is App-owned; stub the count so the badge is inert and keep
  // the decision callback for the refresh-wiring test.
  useApprovalsInbox: (_enabled: boolean, onDecisionApplied?: () => void) => {
    inboxCallback.current = onDecisionApplied;
    return { pendingCount: 0 };
  },
}));

vi.mock("../chat/ChatView", () => ({
  default: ({
    workspace,
    mode,
  }: {
    workspace?: { tag?: string };
    mode?: string;
  }) => (
    <div
      data-testid="chat-view"
      data-mode={mode ?? "(unset)"}
      data-workspace={workspace?.tag ?? "(untagged)"}
    />
  ),
}));

vi.mock("../views/workspace/DocumentsView", () => ({
  default: ({ workspace }: { workspace?: { tag?: string } }) => (
    <div
      data-testid="documents-view"
      data-workspace={workspace?.tag ?? "(untagged)"}
    />
  ),
}));

vi.mock("../views/audit/AuditView", () => ({
  default: () => <div data-testid="audit-view" />,
}));
vi.mock("../views/control/PermissionsView", () => ({
  default: () => <div data-testid="permissions-view" />,
}));
vi.mock("../views/control/SettingsView", () => ({
  default: ({ workspace }: { workspace?: { tag?: string } }) => (
    <div
      data-testid="settings-view"
      data-workspace={workspace?.tag ?? "(untagged)"}
    />
  ),
}));
vi.mock("../views/control/SkillsView", () => ({
  default: () => <div data-testid="skills-view" />,
}));
vi.mock("../views/control/ToolsView", () => ({
  default: () => <div data-testid="tools-view" />,
}));
vi.mock("../views/incidents/IncidentsView", () => ({
  default: ({ workspace }: { workspace?: { tag?: string } }) => (
    <div
      data-testid="incidents-view"
      data-workspace={workspace?.tag ?? "(untagged)"}
    />
  ),
}));

// Pinned as literals rather than imported from roles.ts: if STUDIO_ROLES were
// re-pointed at a different set these expectations would have to be argued
// about, not silently re-derived from the code under test (R-6's mirror).
const STUDIO_ROLES = ["platform-admin", "approver", "operator"];
const NON_STUDIO_ROLES = ["developer", "read-only-observer", "auditor"];

function workspaceStub(tag: string): SessionWorkspace {
  return {
    // Not part of SessionWorkspace — the marker views read it to report which
    // instance App handed them.
    tag,
    sessions: [],
    loading: false,
    error: null,
    activeSessionId: null,
    setActiveSessionId: vi.fn(),
    refresh: vi.fn(async () => {}),
    createAndOpen: vi.fn(async () => null),
    createDevelopmentSession: vi.fn(async () => ({ ok: true, sessionId: null })),
    remove: vi.fn(async () => ({ ok: true })),
    rename: vi.fn(async () => ({ ok: true })),
    pinned: [],
    pinIncidentSession: vi.fn(() => "incident-1"),
  } as unknown as SessionWorkspace;
}

const operationStub = workspaceStub("operation");
const developmentStub = workspaceStub("development");

function signIn(roles: string[], username: string | null = "op-one") {
  mockUseAuth.mockReturnValue({
    booting: false,
    session: username ? { access_token: "token" } : null,
    authError: null,
    username,
    roles,
    login: vi.fn(async () => {}),
    logout: vi.fn(async () => {}),
  });
}

// The sidebar renders once in the Sider and again in the off-canvas drawer, so
// nav assertions count occurrences rather than querying a single node.
function navHas(label: string): boolean {
  return screen.queryAllByText(label).length > 0;
}

async function navigateTo(label: string) {
  await act(async () => {
    fireEvent.click(screen.getByText(label));
  });
}

beforeEach(() => {
  mockUseAuth.mockReset();
  mockUseSessionWorkspace.mockReset();
  inboxCallback.current = undefined;
  mockUseSessionWorkspace.mockImplementation(
    (_authenticated: boolean, mode?: string) =>
      mode === "development" ? developmentStub : operationStub,
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("App nav — the Studio entry (SPEC-056 R-2)", () => {
  it.each(STUDIO_ROLES.map((role) => [role]))(
    "shows Studio to %s",
    (role) => {
      signIn([role]);
      render(<App />);
      expect(navHas("Studio")).toBe(true);
    },
  );

  it.each(NON_STUDIO_ROLES.map((role) => [role]))(
    "hides Studio from %s",
    (role) => {
      signIn([role]);
      render(<App />);
      expect(navHas("Studio")).toBe(false);
    },
  );

  it.each([...STUDIO_ROLES, ...NON_STUDIO_ROLES].map((role) => [role]))(
    "keeps Chat for every signed-in role (%s) — gating unchanged",
    (role) => {
      signIn([role]);
      render(<App />);
      expect(navHas("Chat")).toBe(true);
    },
  );

  it("hides Studio while signed out but keeps Chat", () => {
    signIn([], null);
    render(<App />);
    expect(navHas("Studio")).toBe(false);
    // Chat's entry has never been role-gated — it is the first item and the
    // signed-out placeholder lives inside it.
    expect(navHas("Chat")).toBe(true);
  });

  it("widens ViewId rather than forking the shell", () => {
    // Compile-time half of R-2: `studio` is a member of the same union the
    // other entries use, so the one shell navigates to it.
    const studio: ViewId = "studio";
    const chat: ViewId = "chat";
    expect([chat, studio]).toEqual(["chat", "studio"]);
  });
});

describe("App workspaces — two mode-scoped instances (SPEC-056 R-2, plan §7)", () => {
  it("owns an operation and a development workspace for a Studio role", () => {
    signIn(["operator"]);
    render(<App />);
    expect(mockUseSessionWorkspace).toHaveBeenCalledWith(true, "operation");
    expect(mockUseSessionWorkspace).toHaveBeenCalledWith(true, "development");
  });

  it("gates the development workspace's polling on a Studio role", () => {
    signIn(["read-only-observer"]);
    render(<App />);
    // The operation workspace still polls for an observer; the development one
    // is handed `authenticated=false`, so a role that could never populate the
    // list never fetches it (and could never open a development session — the
    // gateway dual-gates that on session:skill_graduate, R-6).
    expect(mockUseSessionWorkspace).toHaveBeenCalledWith(true, "operation");
    expect(mockUseSessionWorkspace).toHaveBeenCalledWith(false, "development");
  });

  it("never enables the development workspace while signed out", () => {
    signIn([], null);
    render(<App />);
    expect(mockUseSessionWorkspace).toHaveBeenCalledWith(false, "operation");
    expect(mockUseSessionWorkspace).toHaveBeenCalledWith(false, "development");
  });
});

// SPEC-034 R-2 predates the split, when one workspace covered every session.
// Since SPEC-056 there are two, so "refresh the session panel immediately" has
// to name both — otherwise a decision on a development session leaves the
// Studio panel's "awaiting approval" tag stale until the next 30s poll. The
// decider roles are exactly a subset of the Studio roles, and tier_1 permits
// self-approval (tier_2 forbids it), so an approver can resolve a card on a
// development session of their own: the path is reachable, not theoretical.
describe("App inbox wiring — a decision refreshes BOTH workspaces (SPEC-034 R-2)", () => {
  it.each(["approver", "platform-admin"])(
    "refreshes the operation and the development workspace for %s",
    (role) => {
      signIn([role]);
      render(<App />);
      expect(inboxCallback.current).toBeTypeOf("function");
      // The stubs are module-level, so clear whatever earlier renders left on
      // them and assert on this invocation alone.
      vi.mocked(operationStub.refresh).mockClear();
      vi.mocked(developmentStub.refresh).mockClear();

      act(() => {
        inboxCallback.current?.();
      });

      expect(operationStub.refresh).toHaveBeenCalledTimes(1);
      expect(developmentStub.refresh).toHaveBeenCalledTimes(1);
    },
  );
});

describe("App view wiring (SPEC-056 R-2 / R-4 / R-5)", () => {
  it("renders ONE ChatView in operation mode against the operation workspace", () => {
    signIn(["operator"]);
    render(<App />);
    const view = screen.getByTestId("chat-view");
    expect(view.getAttribute("data-mode")).toBe("operation");
    expect(view.getAttribute("data-workspace")).toBe("operation");
  });

  it("renders the SAME ChatView in development mode for Studio", async () => {
    signIn(["operator"]);
    render(<App />);
    await navigateTo("Studio");
    const view = screen.getByTestId("chat-view");
    // One component, parameterized — not a second chat surface.
    expect(view.getAttribute("data-mode")).toBe("development");
    expect(view.getAttribute("data-workspace")).toBe("development");
  });

  it("hides Studio's route from a role that cannot see the entry", () => {
    signIn(["auditor"]);
    render(<App />);
    expect(navHas("Studio")).toBe(false);
    expect(screen.getByTestId("chat-view").getAttribute("data-mode")).toBe(
      "operation",
    );
  });

  it("applies the flush content className to studio exactly as chat", async () => {
    signIn(["operator"]);
    const { container } = render(<App />);
    const contentClass = () =>
      container.querySelector(".view-container")?.className ?? "";
    expect(contentClass()).toContain("view-container-flush");
    await navigateTo("Studio");
    expect(contentClass()).toContain("view-container-flush");
    await navigateTo("Settings");
    expect(contentClass()).not.toContain("view-container-flush");
  });

  it("wires Documents — the shift-summary picker's home — to the operation workspace", async () => {
    signIn(["operator"]);
    render(<App />);
    await navigateTo("Documents");
    // R-4: the picker lists `workspace.sessions`, so handing Documents the
    // development workspace would let a Studio session be picked into shift
    // material. The scope itself is the server's (`?session_type=operation`).
    expect(
      screen.getByTestId("documents-view").getAttribute("data-workspace"),
    ).toBe("operation");
  });

  it("wires Incidents and Settings to the operation workspace too", async () => {
    signIn(["operator"]);
    render(<App />);
    await navigateTo("Incidents");
    expect(
      screen.getByTestId("incidents-view").getAttribute("data-workspace"),
    ).toBe("operation");
    await navigateTo("Settings");
    expect(
      screen.getByTestId("settings-view").getAttribute("data-workspace"),
    ).toBe("operation");
    // No view other than Studio is ever handed the development instance.
    expect(screen.queryByTestId("chat-view")).toBeNull();
  });
});
