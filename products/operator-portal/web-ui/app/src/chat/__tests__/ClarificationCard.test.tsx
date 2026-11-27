// SPEC-080 R-7 (plan lines 107–117): the owner-answerable clarification card.
// These tests pin the requester-facing behaviour of ClarificationCardView —
// a pending park renders its projected questions (single-select radios /
// multi-select checkboxes / an optional "Other" free text), Submit stays gated
// until EVERY question carries an answer, and posting hands the owner's
// selections to onAnswer. The client gate mirrors the composer (canAnswer),
// never the chat:confirm decision gate. A resolved card replays read-only from
// clarification_result (with answers) or the durable record on re-login (which
// persists no selections, so it degrades to the status label — never an
// invented answer). There is NO approver surface and NO approve/deny.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ClarificationQuestion } from "../../stream/models";
import type { ClarificationCard } from "../../stream/useChatStream";
import { ClarificationCardView } from "../ChatView";

// ChatView imports useAuth at module scope; ClarificationCardView itself takes
// its gate as a prop (canAnswer) and never calls the hook, but the mock keeps
// the module load identical to the sibling card test.
const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }));
vi.mock("../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));

function questionOf(
  overrides: Partial<ClarificationQuestion> = {},
): ClarificationQuestion {
  return {
    question: "Which environment should I target?",
    header: "Environment",
    multiSelect: false,
    options: [
      { label: "staging", description: "non-production" },
      { label: "production", description: "customer-facing" },
    ],
    ...overrides,
  };
}

function cardOf(
  questions: ClarificationQuestion[],
  overrides: Partial<ClarificationCard> = {},
): ClarificationCard {
  return {
    clarificationId: "cl-1",
    questions,
    status: "pending",
    sessionId: "s-1",
    ...overrides,
  };
}

function renderCard(
  card: ClarificationCard,
  {
    canAnswer = true,
    busy = false,
    onAnswer = () => {},
  }: {
    canAnswer?: boolean;
    busy?: boolean;
    onAnswer?: (clarificationId: string, answers: unknown[]) => void;
  } = {},
) {
  return render(
    <ClarificationCardView
      card={card}
      canAnswer={canAnswer}
      busy={busy}
      onAnswer={onAnswer}
    />,
  );
}

const OTHER_PLACEHOLDER = /Other \(optional\)/;

beforeEach(() => {
  mockUseAuth.mockReset();
});

// Vitest globals are off, so testing-library's auto-cleanup never registers;
// unmount explicitly to keep renders isolated.
afterEach(() => {
  cleanup();
});

describe("ClarificationCardView pending single-select (SPEC-080 R-7)", () => {
  it("renders the prompt, its options as radios, and a gated Submit", () => {
    renderCard(cardOf([questionOf()]));
    expect(screen.getByTestId("clarification-card")).toBeTruthy();
    expect(screen.getByText("Clarification requested")).toBeTruthy();
    expect(screen.getByText("Pending")).toBeTruthy();
    expect(screen.getByText("you answer")).toBeTruthy();
    expect(
      screen.getByText("Which environment should I target?"),
    ).toBeTruthy();
    expect(screen.getByText("Environment")).toBeTruthy();
    // A single-select question renders radios, never the multi-select hint.
    expect(screen.getAllByRole("radio").length).toBe(2);
    expect(screen.queryByText("Select all that apply")).toBeNull();
    const submit = screen.getByRole("button", {
      name: /Submit answer/,
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("enables Submit once an option is chosen and posts the selected label", () => {
    const onAnswer = vi.fn();
    renderCard(cardOf([questionOf()]), { onAnswer });
    const submit = screen.getByRole("button", {
      name: /Submit answer/,
    }) as HTMLButtonElement;
    fireEvent.click(screen.getAllByRole("radio")[0]);
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);
    expect(onAnswer).toHaveBeenCalledWith("cl-1", [
      { question: "Which environment should I target?", selected: ["staging"] },
    ]);
  });
});

describe("ClarificationCardView multi-select (SPEC-080 R-7)", () => {
  it("renders checkboxes with the hint and posts every chosen label", () => {
    const onAnswer = vi.fn();
    renderCard(
      cardOf([
        questionOf({
          question: "Which steps should I run?",
          header: "Steps",
          multiSelect: true,
          options: [
            { label: "build", description: "compile" },
            { label: "test", description: "unit + e2e" },
            { label: "deploy", description: "ship it" },
          ],
        }),
      ]),
      { onAnswer },
    );
    expect(screen.getByText("Select all that apply")).toBeTruthy();
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes.length).toBe(3);
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[2]);
    const submit = screen.getByRole("button", {
      name: /Submit answer/,
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);
    expect(onAnswer).toHaveBeenCalledWith("cl-1", [
      { question: "Which steps should I run?", selected: ["build", "deploy"] },
    ]);
  });
});

describe("ClarificationCardView 'Other' free text (SPEC-080 R-7)", () => {
  it("accepts a custom answer alone and rides it on `other`", () => {
    const onAnswer = vi.fn();
    renderCard(cardOf([questionOf()]), { onAnswer });
    const submit = screen.getByRole("button", {
      name: /Submit answer/,
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText(OTHER_PLACEHOLDER), {
      target: { value: "qa namespace" },
    });
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);
    expect(onAnswer).toHaveBeenCalledWith("cl-1", [
      {
        question: "Which environment should I target?",
        selected: [],
        other: "qa namespace",
      },
    ]);
  });

  it("trims the free text and combines it with a chosen option", () => {
    const onAnswer = vi.fn();
    renderCard(cardOf([questionOf()]), { onAnswer });
    fireEvent.click(screen.getAllByRole("radio")[1]);
    fireEvent.change(screen.getByPlaceholderText(OTHER_PLACEHOLDER), {
      target: { value: "  and qa  " },
    });
    fireEvent.click(screen.getByRole("button", { name: /Submit answer/ }));
    expect(onAnswer).toHaveBeenCalledWith("cl-1", [
      {
        question: "Which environment should I target?",
        selected: ["production"],
        other: "and qa",
      },
    ]);
  });

  it("keeps Submit gated on whitespace-only free text with no selection", () => {
    renderCard(cardOf([questionOf()]));
    const submit = screen.getByRole("button", {
      name: /Submit answer/,
    }) as HTMLButtonElement;
    fireEvent.change(screen.getByPlaceholderText(OTHER_PLACEHOLDER), {
      target: { value: "   " },
    });
    expect(submit.disabled).toBe(true);
  });
});

describe("ClarificationCardView multi-question gating (SPEC-080 R-7)", () => {
  it("keeps Submit disabled until every question carries an answer", () => {
    const onAnswer = vi.fn();
    renderCard(
      cardOf([
        questionOf(),
        questionOf({
          question: "How verbose should the run be?",
          header: "Verbosity",
          options: [
            { label: "quiet", description: "errors only" },
            { label: "verbose", description: "everything" },
          ],
        }),
      ]),
      { onAnswer },
    );
    const radios = screen.getAllByRole("radio");
    expect(radios.length).toBe(4);
    const submit = screen.getByRole("button", {
      name: /Submit answer/,
    }) as HTMLButtonElement;
    // Answering only the first question is not enough.
    fireEvent.click(radios[0]);
    expect(submit.disabled).toBe(true);
    // Answering the second unlocks Submit and posts both answers in order.
    fireEvent.click(radios[2]);
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);
    expect(onAnswer).toHaveBeenCalledWith("cl-1", [
      { question: "Which environment should I target?", selected: ["staging"] },
      { question: "How verbose should the run be?", selected: ["quiet"] },
    ]);
  });
});

describe("ClarificationCardView client gate (SPEC-080 R-7)", () => {
  it("shows the sign-in prompt and disables input when the owner cannot answer", () => {
    renderCard(cardOf([questionOf()]), { canAnswer: false });
    expect(
      screen.queryByRole("button", { name: /Submit answer/ }),
    ).toBeNull();
    expect(
      screen.getByText("Sign in to answer this clarification."),
    ).toBeTruthy();
    expect(
      (screen.getAllByRole("radio")[0] as HTMLInputElement).disabled,
    ).toBe(true);
  });

  it("keeps Submit disabled while the agent is busy even when answerable", () => {
    const onAnswer = vi.fn();
    renderCard(cardOf([questionOf()]), { busy: true, onAnswer });
    fireEvent.click(screen.getAllByRole("radio")[0]);
    const submit = screen.getByRole("button", {
      name: /Submit answer/,
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.click(submit);
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("reads 'Submitting…' while the answer is in flight", () => {
    renderCard(cardOf([questionOf()], { note: "Submitting…" }));
    expect(
      screen.getByRole("button", { name: /Submitting/ }),
    ).toBeTruthy();
  });
});

describe("ClarificationCardView read-only replay (SPEC-080 R-7)", () => {
  it("replays an answered card from clarification_result with the selections", () => {
    const { container } = renderCard(
      cardOf([questionOf()], {
        status: "answered",
        answers: [
          {
            question: "Which environment should I target?",
            selected: ["staging"],
            other: "and qa",
          },
        ],
        note: "Answered — the parked reply resumed.",
      }),
    );
    expect(screen.getByText("Answered")).toBeTruthy();
    expect(screen.queryAllByRole("radio").length).toBe(0);
    expect(screen.queryAllByRole("checkbox").length).toBe(0);
    expect(
      screen.queryByRole("button", { name: /Submit answer/ }),
    ).toBeNull();
    expect(screen.queryByPlaceholderText(OTHER_PLACEHOLDER)).toBeNull();
    const hint = container.querySelector(".confirm-call-hint");
    expect(hint).toBeTruthy();
    expect(hint!.textContent).toContain("Selected: staging");
    expect(hint!.textContent).toContain("Other: and qa");
    expect(
      screen.getByText(/Answered — the parked reply resumed\./),
    ).toBeTruthy();
  });

  it("degrades to the status label when the durable record persisted no selections", () => {
    // SPEC-080 R-7: a re-login re-renders from the durable record, which stores
    // the questions + status + attribution but NOT the owner's specific picks.
    // The card must never invent an answer — it falls back to the status label.
    const { container } = renderCard(
      cardOf([questionOf()], {
        status: "answered",
        note: "Answered by alice at 2026-01-01T00:00:00Z.",
      }),
    );
    expect(screen.queryAllByRole("radio").length).toBe(0);
    const hint = container.querySelector(".confirm-call-hint");
    expect(hint!.textContent).toBe("Answered");
    expect(screen.getByText(/Answered by alice/)).toBeTruthy();
  });

  it("renders an expired clarification read-only with its note", () => {
    const { container } = renderCard(
      cardOf([questionOf()], {
        status: "expired",
        note: "This clarification expired before an answer was applied.",
      }),
    );
    expect(screen.queryAllByRole("radio").length).toBe(0);
    expect(
      screen.queryByRole("button", { name: /Submit answer/ }),
    ).toBeNull();
    // No selections are persisted for an expiry, so the read-only hint falls
    // back to the status label (the tag carries the same word — scope to the
    // hint node rather than a bare getByText).
    const hint = container.querySelector(".confirm-call-hint");
    expect(hint!.textContent).toBe("Expired");
    expect(
      screen.getByText(
        /This clarification expired before an answer was applied\./,
      ),
    ).toBeTruthy();
  });

  it("renders no approver surface (no approve/deny affordance)", () => {
    // SPEC-080: a clarification is owner-answered in-line; the card must never
    // grow an approve/deny control or route to an approver inbox.
    renderCard(cardOf([questionOf()]));
    expect(screen.queryByRole("button", { name: /Approve/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Deny/i })).toBeNull();
    expect(screen.queryByText("approver required")).toBeNull();
  });
});
