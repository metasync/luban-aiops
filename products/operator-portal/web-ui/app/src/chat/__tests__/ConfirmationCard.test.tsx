// Confirmation card tests (SPEC-030 R-5): the tier badge distinguishes
// tier_1 "operator confirmation" from tier_2 "approver required", and
// users without a designated decider role see a read-only card (no
// approve/deny buttons) while the gateway bridge stays authoritative.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PendingCall } from "../../stream/models";
import type { ConfirmationCard } from "../../stream/useChatStream";
import { ConfirmationCardView } from "../ChatView";

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }));
vi.mock("../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));

function cardOf(pendingCalls: PendingCall[]): ConfirmationCard {
  return {
    confirmId: "cf-1",
    message: "Approve the restart?",
    pendingCalls,
    mutating: pendingCalls.some(
      (call) => Boolean(call.riskLevel) && call.riskLevel !== "read",
    ),
    status: "pending",
    sessionId: "s-1",
  };
}

const tier2Card = cardOf([
  { callId: "c-1", toolName: "k8s.restart_pod", riskLevel: "write", action: "tools:mutate" },
]);
const tier1Card = cardOf([
  { callId: "c-1", toolName: "k8s.get_pod_logs", riskLevel: "read", action: "tools:invoke" },
]);

function renderCard(card: ConfirmationCard, canDecide = true) {
  return render(
    <ConfirmationCardView
      card={card}
      canDecide={canDecide}
      busy={false}
      onDecide={() => {}}
    />,
  );
}

beforeEach(() => {
  mockUseAuth.mockReset();
});

// Vitest globals are off, so testing-library's auto-cleanup never
// registers; unmount explicitly to keep renders isolated.
afterEach(() => {
  cleanup();
});

describe("ConfirmationCardView approval tiers (SPEC-030 R-5)", () => {
  it("shows the approver-required badge for a tools:mutate batch", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    renderCard(tier2Card);
    expect(screen.getByText("approver required")).toBeTruthy();
    expect(screen.queryByText("operator confirmation")).toBeNull();
  });

  it("shows the operator-confirmation badge when no call is tools:mutate", () => {
    mockUseAuth.mockReturnValue({ roles: ["operator"] });
    renderCard(tier1Card);
    expect(screen.getByText("operator confirmation")).toBeTruthy();
    expect(screen.queryByText("approver required")).toBeNull();
  });

  it("renders tier_2 read-only for a non-decider chat:confirm holder", () => {
    mockUseAuth.mockReturnValue({ roles: ["operator"] });
    renderCard(tier2Card);
    expect(screen.queryByText("Approve")).toBeNull();
    expect(screen.queryByText("Deny")).toBeNull();
    expect(
      screen.getByText(/needs a designated approver/),
    ).toBeTruthy();
  });

  it("keeps tier_2 actionable for a designated approver", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    renderCard(tier2Card);
    expect(screen.getByText("Approve")).toBeTruthy();
    expect(screen.getByText("Deny")).toBeTruthy();
  });

  it("keeps tier_1 actionable for an operator", () => {
    mockUseAuth.mockReturnValue({ roles: ["operator"] });
    renderCard(tier1Card);
    expect(screen.getByText("Approve")).toBeTruthy();
    expect(screen.getByText("Deny")).toBeTruthy();
  });

  it("stays read-only without a chat:confirm role regardless of tier", () => {
    mockUseAuth.mockReturnValue({ roles: ["read-only-observer"] });
    renderCard(tier1Card, false);
    expect(screen.queryByText("Approve")).toBeNull();
    expect(screen.queryByText("Deny")).toBeNull();
    expect(
      screen.getByText("Your current role cannot approve or deny this request."),
    ).toBeTruthy();
  });
});

describe("ConfirmationCardView execution receipts (SPEC-037 R-6)", () => {
  function decidedCard(
    executions: ConfirmationCard["executions"],
  ): ConfirmationCard {
    return {
      ...cardOf([
        {
          callId: "c-1",
          toolName: "k8s.restart_pod",
          riskLevel: "write",
          action: "tools:mutate",
        },
      ]),
      status: "approved",
      note: "Approved by luban-approver at 2026-08-27T10:05:00Z.",
      deciderUserId: "luban-approver",
      decidedAt: "2026-08-27T10:05:00Z",
      executions,
    };
  }

  it("renders the receipt badge and digest-match state on decided cards", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    renderCard(
      decidedCard([
        {
          executionId: "exec-1",
          callId: "c-1",
          toolName: "k8s.restart_pod",
          status: "succeeded",
          digestMatch: true,
        },
      ]),
    );
    expect(screen.getByText("succeeded")).toBeTruthy();
    expect(
      screen.getByText("arguments matched the signed request"),
    ).toBeTruthy();
  });

  it("shows failed and timeout receipts with their digest state", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    renderCard(
      decidedCard([
        {
          executionId: "exec-1",
          callId: "c-1",
          toolName: "k8s.restart_pod",
          status: "failed",
          digestMatch: true,
        },
        {
          executionId: "exec-2",
          callId: "c-2",
          toolName: "k8s.scale_deployment",
          status: "timeout",
          digestMatch: true,
        },
      ]),
    );
    expect(screen.getByText("failed")).toBeTruthy();
    expect(screen.getByText("timeout")).toBeTruthy();
  });

  it("surfaces a rejection with its reason", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    renderCard(
      decidedCard([
        {
          executionId: "exec-1",
          callId: "c-1",
          toolName: "k8s.restart_pod",
          status: "rejected",
          digestMatch: false,
          rejectReason: "args_digest_mismatch",
        },
      ]),
    );
    expect(screen.getByText("rejected")).toBeTruthy();
    expect(
      screen.getByText("rejected: args_digest_mismatch"),
    ).toBeTruthy();
  });

  it("renders legacy decided cards without receipts exactly as today", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    const { container } = renderCard(decidedCard(undefined));
    expect(container.querySelector(".confirm-executions")).toBeNull();
    expect(screen.queryByText("succeeded")).toBeNull();
    expect(screen.queryByText("rejected")).toBeNull();
    // The decided attribution stays the card's only footnote.
    expect(
      screen.getByText(/Approved by luban-approver/),
    ).toBeTruthy();
  });
});
