import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useAuthorizationReturn } from "../useAuthorizationReturn";
import { authorizationStatus, authorizationSession } from "../../api/authorizations";

vi.mock("../../api/authorizations", () => ({ authorizationStatus: vi.fn(), authorizationSession: vi.fn() }));
const id = "11111111-1111-4111-8111-111111111111";
const status = { challenge_id: id, target: "Automation", session_id: "ses-1", status: "authorized" };
const detail = { session_id: "ses-1", user_id: "alice", session_type: "operation", evidence_turns: [
  { frames: [{ type: "authorization_required", auth_challenge_id: id, target: "Automation" }] },
] };
const selectOperation = vi.fn();
const selectDevelopment = vi.fn();
const navigate = vi.fn();
const options = { booting: false, username: "alice" as string | null, studioAllowed: true,
  selectOperation, selectDevelopment, navigate };

beforeEach(() => {
  vi.clearAllMocks();
  history.replaceState({}, "", `/authorizations/return/${id}`);
  vi.mocked(authorizationStatus).mockResolvedValue(structuredClone(status) as never);
  vi.mocked(authorizationSession).mockResolvedValue(structuredClone(detail) as never);
});
afterEach(() => { cleanup(); history.replaceState({}, "", "/"); });

it.each(["pending", "authorized", "canceled", "expired", "failed"])("returns %s to its owned conversation without dispatch", async (outcome) => {
  vi.mocked(authorizationStatus).mockResolvedValue({ ...status, status: outcome } as never);
  renderHook(() => useAuthorizationReturn(options));
  await waitFor(() => expect(selectOperation).toHaveBeenCalledWith("ses-1"));
  expect(selectDevelopment).not.toHaveBeenCalled();
  expect(navigate).toHaveBeenCalledWith("chat");
  expect(location.pathname).toBe("/");
  expect(authorizationStatus).toHaveBeenCalledTimes(1);
  expect(authorizationSession).toHaveBeenCalledTimes(1);
});

it("selects Studio only using the owned session's backend type", async () => {
  vi.mocked(authorizationSession).mockResolvedValue({ ...detail, session_type: "development" } as never);
  renderHook(() => useAuthorizationReturn(options));
  await waitFor(() => expect(selectDevelopment).toHaveBeenCalledWith("ses-1"));
  expect(navigate).toHaveBeenCalledWith("studio");
  expect(selectOperation).not.toHaveBeenCalled();
});

it.each(["foreign", "missing-evidence", "wrong-target", "studio-denied"])("does not select a session for %s", async (problem) => {
  const bad = structuredClone(detail);
  if (problem === "foreign") bad.user_id = "mallory";
  if (problem === "missing-evidence") bad.evidence_turns = [];
  if (problem === "wrong-target") bad.evidence_turns[0].frames[0].target = "Other";
  if (problem === "studio-denied") bad.session_type = "development";
  vi.mocked(authorizationSession).mockResolvedValue(bad as never);
  const { result } = renderHook(() => useAuthorizationReturn({ ...options, studioAllowed: false }));
  await waitFor(() => expect(result.current).toContain("unavailable"));
  expect(selectOperation).not.toHaveBeenCalled();
  expect(selectDevelopment).not.toHaveBeenCalled();
  expect(location.pathname).toBe("/");
});

it("waits for authenticated startup and ignores an old user's delayed reply", async () => {
  let resolve!: (value: never) => void;
  vi.mocked(authorizationStatus).mockReturnValue(new Promise((r) => { resolve = r; }));
  const { rerender } = renderHook((props) => useAuthorizationReturn(props), { initialProps: { ...options, booting: true } });
  expect(authorizationStatus).not.toHaveBeenCalled();
  rerender({ ...options, booting: false });
  expect(authorizationStatus).toHaveBeenCalledTimes(1);
  rerender({ ...options, booting: false, username: null });
  await act(async () => resolve(status as never));
  expect(authorizationSession).not.toHaveBeenCalled();
  expect(selectOperation).not.toHaveBeenCalled();
});

it("rejects a query-bearing return path without forwarding any values", async () => {
  history.replaceState({}, "", `/authorizations/return/${id}?code=canary&state=canary`);
  renderHook(() => useAuthorizationReturn(options));
  expect(authorizationStatus).not.toHaveBeenCalled();
  expect(location.pathname).toBe("/");
  expect(location.search).toBe("");
});
