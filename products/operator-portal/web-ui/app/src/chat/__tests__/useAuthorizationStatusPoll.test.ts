// SPEC-070 portal proof (plan line 148): the inline Authorize/status/Cancel
// control polls a pending challenge's owner status every two seconds while it is
// visible, stops the moment the challenge reaches a terminal state or its expiry
// lapses, refreshes immediately on focus/visibility, keeps the last-good status
// across a transient transport error, and never polls a disabled card. The hook
// is the status half of the control; it owns no navigation and no mutation.
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthorizationStatus } from "../../api/authorizations";
import {
  AUTHORIZATION_POLL_INTERVAL_MS,
  useAuthorizationStatusPoll,
} from "../useAuthorizationStatusPoll";

const { mockAuthorizationStatus } = vi.hoisted(() => ({
  mockAuthorizationStatus: vi.fn(),
}));

vi.mock("../../api/authorizations", () => ({
  authorizationStatus: mockAuthorizationStatus,
}));

const CHALLENGE = "11111111-1111-4111-8111-111111111111";

// A far-future expiry by default so a pending challenge is not treated as
// lapsed during a test; individual cases override it.
function statusOf(overrides: Partial<AuthorizationStatus> = {}): AuthorizationStatus {
  return {
    challenge_id: CHALLENGE,
    status: "pending",
    target: "Automation",
    session_id: "ses-1",
    updated_at: "2030-01-01T00:00:00Z",
    expires_at: "2030-01-01T00:10:00Z",
    ...overrides,
  };
}

function renderPoll(options: { challengeId?: string | null; enabled?: boolean } = {}) {
  // An explicit null must stay null (a `?? CHALLENGE` fallback would silently
  // turn the "no challenge" case into a live poll against an unconfigured mock).
  const challengeId = "challengeId" in options ? options.challengeId : CHALLENGE;
  return renderHook(
    (props: { challengeId: string | null; enabled?: boolean }) =>
      useAuthorizationStatusPoll(props.challengeId, { enabled: props.enabled }),
    {
      initialProps: {
        challengeId: challengeId ?? null,
        enabled: options.enabled,
      },
    },
  );
}

// Flush the initial (non-timer) fetch a mount triggers.
async function flush() {
  await act(async () => {});
}

async function tick(times = 1) {
  await act(async () => {
    vi.advanceTimersByTime(AUTHORIZATION_POLL_INTERVAL_MS * times);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  mockAuthorizationStatus.mockReset();
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "visible",
  });
});

afterEach(() => {
  // Vitest globals are off: unmount explicitly so leftover focus/visibility
  // kick listeners never count into a later test's shared mock.
  cleanup();
  vi.useRealTimers();
});

describe("useAuthorizationStatusPoll (SPEC-070)", () => {
  it("fetches the initial status and polls every two seconds while pending", async () => {
    mockAuthorizationStatus.mockResolvedValue(statusOf());
    const { result } = renderPoll();
    await flush();
    expect(mockAuthorizationStatus).toHaveBeenCalledTimes(1);
    expect(mockAuthorizationStatus).toHaveBeenLastCalledWith(CHALLENGE, expect.any(AbortSignal));
    expect(result.current.status?.status).toBe("pending");
    expect(result.current.polling).toBe(true);
    await tick();
    expect(mockAuthorizationStatus).toHaveBeenCalledTimes(2);
    // One interval per awaited tick: the in-flight guard deliberately drops an
    // overlapping read, so advancing two intervals inside a single batch would
    // fire only once. Tick separately to observe each cadence.
    await tick();
    expect(mockAuthorizationStatus).toHaveBeenCalledTimes(3);
    expect(result.current.polling).toBe(true);
  });

  it("stops polling once the status is terminal", async () => {
    mockAuthorizationStatus.mockResolvedValue(statusOf({ status: "authorized" }));
    const { result } = renderPoll();
    await flush();
    expect(mockAuthorizationStatus).toHaveBeenCalledTimes(1);
    expect(result.current.status?.status).toBe("authorized");
    expect(result.current.polling).toBe(false);
    await tick(3);
    // The interval self-clears on the terminal status: no further fetches.
    expect(mockAuthorizationStatus).toHaveBeenCalledTimes(1);
  });

  it("treats a lapsed expiry as terminal and stops", async () => {
    mockAuthorizationStatus.mockResolvedValue(
      statusOf({ status: "pending", expires_at: "2000-01-01T00:00:00Z" }),
    );
    const { result } = renderPoll();
    await flush();
    expect(result.current.polling).toBe(false);
    await tick(3);
    expect(mockAuthorizationStatus).toHaveBeenCalledTimes(1);
  });

  it("refreshes immediately on focus while pending", async () => {
    mockAuthorizationStatus.mockResolvedValue(statusOf());
    renderPoll();
    await flush();
    expect(mockAuthorizationStatus).toHaveBeenCalledTimes(1);
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    expect(mockAuthorizationStatus).toHaveBeenCalledTimes(2);
  });

  it("does not poll a disabled card beyond its initial read", async () => {
    mockAuthorizationStatus.mockResolvedValue(statusOf());
    const { result } = renderPoll({ enabled: false });
    await flush();
    expect(mockAuthorizationStatus).toHaveBeenCalledTimes(1);
    expect(result.current.polling).toBe(false);
    await tick(3);
    expect(mockAuthorizationStatus).toHaveBeenCalledTimes(1);
  });

  it("keeps the last-good status across a transient error and retries", async () => {
    mockAuthorizationStatus
      .mockResolvedValueOnce(statusOf())
      .mockRejectedValueOnce(new Error("transient"))
      .mockResolvedValueOnce(statusOf({ status: "authorized" }));
    const { result } = renderPoll();
    await flush();
    expect(result.current.status?.status).toBe("pending");
    await tick();
    // A transport error never means "resolved": the pending view is retained.
    expect(result.current.status?.status).toBe("pending");
    expect(result.current.polling).toBe(true);
    await tick();
    expect(result.current.status?.status).toBe("authorized");
    expect(result.current.polling).toBe(false);
  });

  it("does nothing without a challenge id", async () => {
    const { result } = renderPoll({ challengeId: null });
    await flush();
    await tick(2);
    expect(mockAuthorizationStatus).not.toHaveBeenCalled();
    expect(result.current.status).toBeNull();
    expect(result.current.polling).toBe(false);
  });
});
