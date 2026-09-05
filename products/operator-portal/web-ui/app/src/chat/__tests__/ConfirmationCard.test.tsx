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

describe("ConfirmationCardView technical-detail expander (#2c)", () => {
  // A browser write action: the parsed element label (displayHint) is the
  // one human-readable line, and the raw arguments are audit detail that
  // should fold behind an expander instead of dominating the card.
  const browserCard = cardOf([
    {
      callId: "c-1",
      toolName: "web.click",
      riskLevel: "write",
      action: "tools:mutate",
      displayHint: "Reset password button",
      parameters: { ref: "e42", origin: "https://admin.example.com" },
    },
  ]);

  it("keeps the tool name and risk tier on the card face", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    renderCard(browserCard);
    expect(screen.getByText("web.click")).toBeTruthy();
    expect(screen.getByText("write")).toBeTruthy();
  });

  it("renders the element label as prose, not a raw code block", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    renderCard(browserCard);
    const hint = screen.getByText("Reset password button");
    expect(hint.classList.contains("confirm-call-hint")).toBe(true);
    // A <pre> reads as technical; the hint is now a plain prose line.
    expect(hint.tagName).not.toBe("PRE");
  });

  it("folds the raw arguments behind a 'Technical details' expander", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    const { container } = renderCard(browserCard);
    const summary = screen.getByText("Technical details");
    expect(summary.tagName).toBe("SUMMARY");
    const details = summary.closest("details");
    expect(details).toBeTruthy();
    // The full parameters survive inside the expander — never dropped, so
    // the audit detail stays one click away.
    const pre = details!.querySelector("pre.evidence-pre");
    expect(pre).toBeTruthy();
    expect(pre!.textContent).toContain("e42");
    expect(pre!.textContent).toContain("https://admin.example.com");
    // No raw <pre> sits directly on the card face anymore: both the hint
    // (prose) and the arguments (expander) moved off the always-visible
    // code-block presentation.
    expect(
      container.querySelectorAll(".confirm-call > pre.evidence-pre").length,
    ).toBe(0);
  });
});

describe("ConfirmationCardView flow-intent lead line (SPEC-053 R-3)", () => {
  // A bound browser write flow whose skill declares a ``flow_intent``: the
  // card leads with the plain, author-written decision line (what approving
  // this flow actually does) above the muted DOM-level per-call detail.
  function flowCard(
    flowSummary: ConfirmationCard["flowSummary"],
  ): ConfirmationCard {
    return {
      ...cardOf([
        {
          callId: "c-1",
          toolName: "web.click",
          riskLevel: "write",
          action: "tools:mutate",
          displayHint: "Reset password button",
        },
      ]),
      flowSummary,
    };
  }

  it("renders the skill-authored intent as the lead decision line", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    const { container } = renderCard(
      flowCard({
        title: "Reset User Password",
        description: "Click the submit button on the reset form",
        flowIntent: "Submit the password reset for the user.",
        riskClass: "write",
      }),
    );
    const intent = container.querySelector(".confirm-flow-intent");
    expect(intent).toBeTruthy();
    expect(intent!.textContent).toBe("Submit the password reset for the user.");
    // The intent sits between the bold title and the muted description.
    expect(screen.getByText("Reset User Password")).toBeTruthy();
    expect(
      screen.getByText("Click the submit button on the reset form"),
    ).toBeTruthy();
  });

  it("renders the flow frame when only flow_intent is present (widened guard)", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    const { container } = renderCard(
      flowCard({ flowIntent: "Submit the password reset for the user." }),
    );
    // SPEC-053 R-3: the guard admits a flow that carries an intent but no
    // title/origin, so the decision line is never dropped.
    expect(container.querySelector(".confirm-flow")).toBeTruthy();
    expect(container.querySelector(".confirm-flow-intent")!.textContent).toBe(
      "Submit the password reset for the user.",
    );
  });

  it("omits the intent node when the skill declares none (renders as pre-SPEC-053)", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    const { container } = renderCard(
      flowCard({
        title: "Reset User Password",
        origin: "http://admin.local",
        riskClass: "write",
      }),
    );
    // The flow frame still headlines the card, but there is no intent line —
    // the change is strictly additive for skills without a flow_intent.
    expect(container.querySelector(".confirm-flow")).toBeTruthy();
    expect(container.querySelector(".confirm-flow-intent")).toBeNull();
  });

  it("escapes markup in the intent so it can never inject HTML", () => {
    mockUseAuth.mockReturnValue({ roles: ["approver"] });
    const { container } = renderCard(
      flowCard({
        flowIntent: "<img src=x onerror=alert(1)> Submit the reset",
      }),
    );
    const intent = container.querySelector(".confirm-flow-intent");
    expect(intent).toBeTruthy();
    // JSX text interpolation escapes the author string: it shows verbatim...
    expect(intent!.textContent).toBe(
      "<img src=x onerror=alert(1)> Submit the reset",
    );
    // ...and no <img> element is ever constructed from it (display-only, never
    // dangerouslySetInnerHTML).
    expect(intent!.querySelector("img")).toBeNull();
  });
});
