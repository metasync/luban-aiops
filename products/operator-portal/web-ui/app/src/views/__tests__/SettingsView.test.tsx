// Settings view tests (SPEC-030 R-6): the three read-only panes render
// from client-side state — signed-in identity claims, the workspace's
// selected session (including the explicit no-session state), and the
// platform surface — and the signed-out state degrades to a prompt.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
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
});

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
    mockUseAuth.mockReturnValue({
      session: null,
      username: "luban-operator",
      roles: ["operator"],
      login: async () => {},
    });
    render(<SettingsView workspace={workspaceOf()} />);

    openTab("Platform");
    expect(screen.getByText("Platform version")).toBeTruthy();
    expect(screen.getByText("API origin")).toBeTruthy();
    expect(screen.getByText("Last request id")).toBeTruthy();
  });
});
