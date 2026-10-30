// SPEC-070 (plan lines 148–149): the inline Authorize/status/Cancel control.
// These tests pin the requester-facing behaviour of AuthorizationCardView —
// Authorize hands off to the same-browser start URL, Cancel retires the
// challenge, Continue appears only once the challenge is authorized and fires a
// fresh explicit turn, and terminal / lapsed states drop every action so the
// card can never dispatch on a challenge that cannot complete.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthorizationRequiredFrame } from "../../stream/models";
import type {
  AuthorizationState,
  AuthorizationStatus,
} from "../../api/authorizations";
import { AuthorizationCardView } from "../ChatView";

const {
  mockAuthorizationStatus,
  mockStartAuthorization,
  mockCancelAuthorization,
} = vi.hoisted(() => ({
  mockAuthorizationStatus: vi.fn(),
  mockStartAuthorization: vi.fn(),
  mockCancelAuthorization: vi.fn(),
}));
vi.mock("../../api/authorizations", () => ({
  authorizationStatus: mockAuthorizationStatus,
  startAuthorization: mockStartAuthorization,
  cancelAuthorization: mockCancelAuthorization,
  resetAuthorizationBrowser: vi.fn(),
  authorizationSession: vi.fn(),
}));

const CHALLENGE = "11111111-1111-4111-8111-111111111111";
const START_URL =
  "/api/v1/targets/authorizations/start/22222222-2222-4222-8222-222222222222";

function statusOf(
  overrides: Partial<AuthorizationStatus> = {},
): AuthorizationStatus {
  return {
    challenge_id: CHALLENGE,
    status: "pending",
    target: "Automation",
    session_id: "ses-1",
    updated_at: "2026-01-01T00:00:00Z",
    expires_at: "2030-01-01T00:00:00Z",
    ...overrides,
  };
}

function frameOf(
  overrides: Partial<AuthorizationRequiredFrame> = {},
): AuthorizationRequiredFrame {
  return {
    kind: "authorization_required",
    authChallengeId: CHALLENGE,
    target: "Automation",
    ...overrides,
  };
}

// jsdom does not implement navigation; stub `assign` so Authorize's handoff is
// observable without a real page load (the return path is tested separately in
// useAuthorizationReturn).
const locationAssign = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: { href: "http://localhost/", assign: locationAssign, replace: vi.fn() },
  });
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "visible",
  });
  mockAuthorizationStatus.mockResolvedValue(statusOf());
  mockStartAuthorization.mockResolvedValue({
    start_url: START_URL,
    expires_at: "2030-01-01T00:00:00Z",
  });
  mockCancelAuthorization.mockResolvedValue(undefined);
});

// Vitest globals are off, so testing-library's auto-cleanup never registers;
// unmount explicitly to keep renders (and their poll intervals) isolated.
afterEach(() => {
  cleanup();
});

describe("AuthorizationCardView (SPEC-070)", () => {
  it("offers Authorize and Cancel while pending, with no Continue", async () => {
    mockAuthorizationStatus.mockResolvedValue(statusOf({ status: "pending" }));
    render(<AuthorizationCardView authorization={frameOf()} />);
    expect(
      await screen.findByRole("button", { name: /Authorize/i }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /Cancel/i })).toBeTruthy();
    expect(screen.getByText("Automation")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Continue/i })).toBeNull();
    expect(mockAuthorizationStatus).toHaveBeenCalledWith(
      CHALLENGE,
      expect.any(AbortSignal),
    );
  });

  it("hands off to the same-browser start URL on Authorize", async () => {
    mockAuthorizationStatus.mockResolvedValue(statusOf({ status: "pending" }));
    render(<AuthorizationCardView authorization={frameOf()} />);
    fireEvent.click(await screen.findByRole("button", { name: /Authorize/i }));
    await waitFor(() =>
      expect(mockStartAuthorization).toHaveBeenCalledWith(CHALLENGE),
    );
    await waitFor(() => expect(locationAssign).toHaveBeenCalledWith(START_URL));
    expect(mockCancelAuthorization).not.toHaveBeenCalled();
  });

  it("retires the challenge on Cancel without navigating", async () => {
    mockAuthorizationStatus.mockResolvedValue(statusOf({ status: "pending" }));
    render(<AuthorizationCardView authorization={frameOf()} />);
    fireEvent.click(await screen.findByRole("button", { name: /Cancel/i }));
    await waitFor(() =>
      expect(mockCancelAuthorization).toHaveBeenCalledWith(CHALLENGE),
    );
    expect(locationAssign).not.toHaveBeenCalled();
  });

  it("reveals Continue only once authorized and fires a fresh turn", async () => {
    mockAuthorizationStatus.mockResolvedValue(statusOf({ status: "authorized" }));
    const onContinue = vi.fn();
    render(
      <AuthorizationCardView
        authorization={frameOf()}
        busy={false}
        onContinue={onContinue}
      />,
    );
    const cont = await screen.findByRole("button", { name: /Continue/i });
    expect(screen.queryByRole("button", { name: /Authorize/i })).toBeNull();
    fireEvent.click(cont);
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("keeps Continue disabled while the agent is busy", async () => {
    mockAuthorizationStatus.mockResolvedValue(statusOf({ status: "authorized" }));
    const onContinue = vi.fn();
    render(
      <AuthorizationCardView authorization={frameOf()} busy onContinue={onContinue} />,
    );
    const cont = await screen.findByRole("button", { name: /Continue/i });
    expect((cont as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(cont);
    expect(onContinue).not.toHaveBeenCalled();
  });

  it("omits Continue when authorized but no continuation is wired", async () => {
    mockAuthorizationStatus.mockResolvedValue(statusOf({ status: "authorized" }));
    render(<AuthorizationCardView authorization={frameOf()} />);
    expect(await screen.findByText(/Approved\./)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Continue/i })).toBeNull();
  });

  it.each<[AuthorizationState, RegExp]>([
    ["canceled", /Canceled\./],
    ["expired", /Expired\./],
    ["failed", /Authorization failed\./],
  ])("drops every action for a %s challenge", async (state, guidance) => {
    mockAuthorizationStatus.mockResolvedValue(statusOf({ status: state }));
    render(
      <AuthorizationCardView authorization={frameOf()} onContinue={vi.fn()} />,
    );
    expect(await screen.findByText(guidance)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Authorize/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Cancel/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Continue/i })).toBeNull();
  });

  it("treats a lapsed expiry as expired even while the row reads pending", async () => {
    mockAuthorizationStatus.mockResolvedValue(
      statusOf({ status: "pending", expires_at: "2000-01-01T00:00:00Z" }),
    );
    render(
      <AuthorizationCardView authorization={frameOf()} onContinue={vi.fn()} />,
    );
    expect(await screen.findByText(/Expired\./)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Authorize/i })).toBeNull();
  });
});
