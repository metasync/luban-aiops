// useSessionWorkspace mode tests (SPEC-056 R-1 / R-2): one hook, two scoped
// instances. The `mode` parameter fixes exactly three things — the birth
// `session_type` written on create, the list scope (`?session_type=<mode>`),
// and the active-session key namespace — so Chat (operation) and Studio
// (development) never fight over the active pointer, and a pinned incident
// entry stays operational work regardless of the mode that pinned it.
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionSummary } from "../../api/sessions";
import { useSessionWorkspace } from "../useSessionWorkspace";

const { mockListSessions, mockCreateSession, mockDeleteSession, mockRenameSession } =
  vi.hoisted(() => ({
    mockListSessions: vi.fn(),
    mockCreateSession: vi.fn(),
    mockDeleteSession: vi.fn(),
    mockRenameSession: vi.fn(),
  }));

vi.mock("../../api/sessions", () => ({
  listSessions: mockListSessions,
  createSession: mockCreateSession,
  deleteSession: mockDeleteSession,
  renameSession: mockRenameSession,
}));

const OPERATION_KEY = "luban.portal.activeSessionId.operation";
const DEVELOPMENT_KEY = "luban.portal.activeSessionId.development";

function summaryOf(
  id: string,
  type: "operation" | "development",
): SessionSummary {
  return {
    session_id: id,
    title: null,
    created_at: "2026-09-01T00:00:00Z",
    last_active_at: null,
    pending_confirmation: false,
    session_type: type,
  };
}

beforeEach(() => {
  window.sessionStorage.clear();
  mockListSessions.mockReset();
  mockCreateSession.mockReset();
  mockDeleteSession.mockReset();
  mockRenameSession.mockReset();
  mockListSessions.mockResolvedValue([]);
});

afterEach(() => {
  // Vitest globals are off, so unmount explicitly: a mounted workspace keeps
  // a 30s poll interval that would otherwise outlive the test.
  cleanup();
});

describe("useSessionWorkspace list scoping (SPEC-056 R-2 / R-4)", () => {
  it("scopes listSessions to development in development mode", async () => {
    mockListSessions.mockResolvedValue([summaryOf("ses-dev", "development")]);
    const { result } = renderHook(() =>
      useSessionWorkspace(true, "development"),
    );
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));
    expect(mockListSessions).toHaveBeenCalledWith(undefined, "development");
  });

  it("defaults to the operation scope (Chat and the shared instances)", async () => {
    const { result } = renderHook(() => useSessionWorkspace(true));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockListSessions).toHaveBeenCalledWith(undefined, "operation");
  });

  it("does not list when unauthenticated", async () => {
    const { result } = renderHook(() =>
      useSessionWorkspace(false, "development"),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockListSessions).not.toHaveBeenCalled();
    expect(result.current.sessions).toEqual([]);
  });
});

describe("useSessionWorkspace namespaced active-session key (SPEC-056 R-2)", () => {
  it("persists the active id under the operation key, leaving development untouched", async () => {
    const { result } = renderHook(() => useSessionWorkspace(true, "operation"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setActiveSessionId("ses-op"));
    expect(window.sessionStorage.getItem(OPERATION_KEY)).toBe("ses-op");
    expect(window.sessionStorage.getItem(DEVELOPMENT_KEY)).toBeNull();
  });

  it("persists the active id under the development key, leaving operation untouched", async () => {
    const { result } = renderHook(() =>
      useSessionWorkspace(true, "development"),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setActiveSessionId("ses-dev"));
    expect(window.sessionStorage.getItem(DEVELOPMENT_KEY)).toBe("ses-dev");
    expect(window.sessionStorage.getItem(OPERATION_KEY)).toBeNull();
  });

  it("restores its own mode's saved active id on mount", () => {
    window.sessionStorage.setItem(DEVELOPMENT_KEY, "ses-dev-saved");
    const { result } = renderHook(() =>
      useSessionWorkspace(true, "development"),
    );
    expect(result.current.activeSessionId).toBe("ses-dev-saved");
  });

  it("ignores the other mode's saved active id (the pointers never cross)", () => {
    window.sessionStorage.setItem(DEVELOPMENT_KEY, "ses-dev-saved");
    const { result } = renderHook(() => useSessionWorkspace(true, "operation"));
    expect(result.current.activeSessionId).toBeNull();
  });

  it("clears only its own mode's key on deselect", async () => {
    window.sessionStorage.setItem(OPERATION_KEY, "ses-op");
    window.sessionStorage.setItem(DEVELOPMENT_KEY, "ses-dev");
    const { result } = renderHook(() => useSessionWorkspace(true, "operation"));
    act(() => result.current.setActiveSessionId(null));
    expect(window.sessionStorage.getItem(OPERATION_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(DEVELOPMENT_KEY)).toBe("ses-dev");
  });
});

describe("useSessionWorkspace birth session_type (SPEC-056 R-1)", () => {
  it("createDevelopmentSession writes session_type=development in Studio", async () => {
    mockCreateSession.mockResolvedValue({ session_id: "ses-dev" });
    const { result } = renderHook(() =>
      useSessionWorkspace(true, "development"),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.createDevelopmentSession(
        "https://admin.internal/login",
      );
    });
    expect(mockCreateSession).toHaveBeenCalledWith(
      undefined,
      "https://admin.internal/login",
      "development",
    );
    // The new session becomes active under the development key.
    expect(window.sessionStorage.getItem(DEVELOPMENT_KEY)).toBe("ses-dev");
  });

  it("createAndOpen writes session_type=operation in Chat", async () => {
    mockCreateSession.mockResolvedValue({ session_id: "ses-op" });
    const { result } = renderHook(() => useSessionWorkspace(true, "operation"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.createAndOpen();
    });
    expect(mockCreateSession).toHaveBeenCalledWith(
      undefined,
      undefined,
      "operation",
    );
  });
});

describe("useSessionWorkspace pinned incident entry (SPEC-056 R-1)", () => {
  it("is typed operation even when pinned from a development workspace", async () => {
    const { result } = renderHook(() =>
      useSessionWorkspace(true, "development"),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => {
      result.current.pinIncidentSession("inc-1", "incident-1");
    });
    expect(result.current.pinned).toHaveLength(1);
    // An incident triage session is operational work, so the synthetic
    // entry is typed operation regardless of the mode that pinned it.
    expect(result.current.pinned[0].session_type).toBe("operation");
    expect(result.current.pinned[0].session_id).toBe("incident-1");
  });
});
