// Settings view tests (SPEC-030 R-6): the three read-only panes render
// from client-side state — signed-in identity claims, the workspace's
// selected session (including the explicit no-session state), and the
// platform surface — and the signed-out state degrades to a prompt.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionWorkspace } from "../../sessions/useSessionWorkspace";
import SettingsView from "../control/SettingsView";

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }));
vi.mock("../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));

// jsdom lacks matchMedia/ResizeObserver, which rc-tabs probes while
// measuring the tab bar; shim them so the tab strip mounts.
beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
  if (!(window as unknown as { ResizeObserver?: unknown }).ResizeObserver) {
    class ResizeObserverShim {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver =
      ResizeObserverShim;
  }
});

afterEach(() => {
  cleanup();
  mockUseAuth.mockReset();
  vi.unstubAllGlobals();
});

// The Platform pane probes /health/ready and /api/v1/runtime; stub fetch
// globally so jsdom never attempts a real network call. Tests opt into
// fixtures; the default rejects so probes degrade to "unavailable".
const mockFetch = vi.fn();

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockRejectedValue(new Error("network down"));
  vi.stubGlobal("fetch", mockFetch);
});

function stubProbes(ready: unknown, runtime: unknown) {
  mockFetch.mockImplementation(async (url: string) => {
    const path = String(url);
    if (path.includes("/health/ready")) {
      return { ok: true, status: 200, statusText: "OK", json: async () => ready };
    }
    if (path.includes("/api/v1/runtime")) {
      return { ok: true, status: 200, statusText: "OK", json: async () => runtime };
    }
    return { ok: false, status: 404, statusText: "Not Found", json: async () => ({}) };
  });
}

function signedOutAuth() {
  mockUseAuth.mockReturnValue({
    session: null,
    username: "luban-operator",
    roles: ["operator"],
    login: async () => {},
  });
}

function workspaceOf(
  overrides: Partial<SessionWorkspace> = {},
): SessionWorkspace {
  return {
    sessions: [],
    loading: false,
    error: null,
    activeSessionId: null,
    setActiveSessionId: () => {},
    refresh: async () => {},
    createAndOpen: async () => null,
    ...overrides,
  } as unknown as SessionWorkspace;
}

function openTab(label: string) {
  fireEvent.click(screen.getByRole("tab", { name: label }));
}

describe("SettingsView (SPEC-030 R-6)", () => {
  it("renders the signed-in identity pane with claims and roles", () => {
    mockUseAuth.mockReturnValue({
      session: {
        access_token: "token",
        identity: {
          username: "luban-operator",
          subject: "sub-123",
          roles: ["operator"],
          groups: ["ops-operators"],
        },
      },
      username: "luban-operator",
      roles: ["operator"],
      login: async () => {},
    });
    render(<SettingsView workspace={workspaceOf()} />);

    expect(screen.getByText("Settings")).toBeTruthy();
    expect(screen.getByText("signed in")).toBeTruthy();
    expect(screen.getByText("luban-operator")).toBeTruthy();
    expect(screen.getByText("operator")).toBeTruthy();
    expect(screen.getByText("sub-123")).toBeTruthy();
    expect(screen.getByText("ops-operators")).toBeTruthy();
  });

  it("degrades to a sign-in prompt when signed out", () => {
    mockUseAuth.mockReturnValue({
      session: null,
      username: null,
      roles: [],
      login: async () => {},
    });
    render(<SettingsView workspace={workspaceOf()} />);

    expect(screen.getByText("You are signed out")).toBeTruthy();
    expect(screen.getByText("Sign in")).toBeTruthy();
    expect(screen.queryByText("signed in")).toBeNull();
  });

  it("shows the explicit no-session-selected state on the Session pane", () => {
    mockUseAuth.mockReturnValue({
      session: null,
      username: "luban-operator",
      roles: ["operator"],
      login: async () => {},
    });
    render(<SettingsView workspace={workspaceOf()} />);

    openTab("Session");
    expect(screen.getByText("no session selected")).toBeTruthy();
    expect(screen.getByText("Workspace sessions")).toBeTruthy();
  });

  it("shows the selected session id when one is active", () => {
    mockUseAuth.mockReturnValue({
      session: null,
      username: "luban-operator",
      roles: ["operator"],
      login: async () => {},
    });
    render(
      <SettingsView
        workspace={workspaceOf({
          activeSessionId: "sess-42",
          sessions: [
            { session_id: "sess-42", title: "Triage the API" },
          ] as SessionWorkspace["sessions"],
        })}
      />,
    );

    openTab("Session");
    expect(screen.getByText("sess-42")).toBeTruthy();
    expect(screen.getByText("Triage the API")).toBeTruthy();
  });

  it("renders the platform pane with version, origin, and request-id state", () => {
    signedOutAuth();
    render(<SettingsView workspace={workspaceOf()} />);

    openTab("Platform");
    expect(screen.getByText("Platform version")).toBeTruthy();
    expect(screen.getByText("API origin")).toBeTruthy();
    expect(screen.getByText("Last request id")).toBeTruthy();
  });

  it("lists key platform components from the live health probes", async () => {
    signedOutAuth();
    stubProbes(
      {
        status: "ok",
        service: "platform-gateway",
        version: "0.23.4",
        python_version: "3.12.9",
        fastapi_version: "0.139.2",
        agent_service: {
          status: "ready",
          runtime_mode: "agentscope",
          configured: true,
          session_store: "postgres",
          session_store_ready: true,
          session_store_version: "16.4",
          agent_state: "postgres",
          agent_state_ready: true,
          agent_state_version: "16.4",
          python_version: "3.12.9",
          fastapi_version: "0.139.2",
          agentscope_version: "2.0.6",
        },
        policy_rules: 12,
      },
      {
        runtime_mode: "agentscope",
        runtime_state: "ready",
        provider: "deepseek",
        model_name: "deepseek-v4-flash",
      },
    );
    render(<SettingsView workspace={workspaceOf()} />);
    openTab("Platform");

    await screen.findByText("Key platform components");
    await waitFor(() => {
      expect(screen.getByText("AgentScope 2.0.6 · FastAPI 0.139.2")).toBeTruthy();
    });
    // v0.23.4: the table names the tech stack, not the component version.
    expect(screen.getByText("Platform gateway")).toBeTruthy();
    expect(screen.getByText("FastAPI · Python")).toBeTruthy();
    expect(screen.getByText("FastAPI 0.139.2 · Python 3.12.9")).toBeTruthy();
    expect(screen.getByText("AgentScope · FastAPI")).toBeTruthy();
    expect(screen.getByText("Deepseek API")).toBeTruthy();
    expect(screen.getByText("deepseek-v4-flash")).toBeTruthy();
    expect(screen.getAllByText("PostgreSQL").length).toBe(2);
    expect(screen.getAllByText("16.4").length).toBe(2);
    expect(screen.getByText("12 rule(s)")).toBeTruthy();
    // One unified status vocabulary: every live row reports "ready".
    expect(screen.getAllByText("ready").length).toBeGreaterThanOrEqual(7);
  });

  it("degrades the component table to unavailable when probes fail", async () => {
    signedOutAuth();
    // Default mockFetch rejects — both probes fail.
    render(<SettingsView workspace={workspaceOf()} />);
    openTab("Platform");

    await screen.findByText("Key platform components");
    await waitFor(() => {
      expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);
    });
  });
});
