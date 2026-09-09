// Skill-graduation session action tests (SPEC-055 R-4): role-matrix
// visibility (client-side mirror of allow-operators-skill-graduate; the
// gateway re-enforces session:skill_graduate regardless), the shared preview
// opening on the graduated badge rather than downloading blind, the
// blast-radius refusal surfaced with the server's own explanation instead of
// a bare status, and the mid-session target declaration the graduation
// refusal sends an operator to.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Modal } from "antd";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DeclareSkillTargetButton, GraduateAsSkillButton } from "../ChatView";

const { mockUseAuth, mockGraduate, mockDeclare } = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockGraduate: vi.fn(),
  mockDeclare: vi.fn(),
}));

vi.mock("../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));
vi.mock("../../api/sessions", () => ({
  graduateSessionSkill: mockGraduate,
  declareSkillTarget: mockDeclare,
  // ChatView imports the draft action and the session fetch too; keep every
  // binding present or the module mock breaks the import graph.
  createSkillDraft: vi.fn(),
  getSession: vi.fn(),
}));

const GRADUATION_RESPONSE = {
  markdown:
    '---\ntitle: "Reset a password"\nrisk_class: write\n' +
    "kind: executable_flow\n---\n\n## Replay runbook\n\n- Steps: 3\n",
  mode: "graduated",
  validation: "passed",
  suggested_filename: "reset-a-password.md",
  step_count: 3,
  web_target: "https://admin.internal/login",
  declaration: "preceded",
};

// The refusal the agent's re-validation produces: every guard the trace
// failed, naming the steps responsible. This text *is* the operator's remedy.
const REFUSAL_DETAIL =
  "this session cannot be graduated: step(s) 2, 4 have no observed origin, " +
  "so nothing proves the mutation landed inside the declared target";

function useRoles(roles: string[]) {
  mockUseAuth.mockReturnValue({ roles });
}

beforeEach(() => {
  mockGraduate.mockReset();
  mockDeclare.mockReset();
  mockUseAuth.mockReset();
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  // The graduation refusal is an imperative Modal.warning, which RTL's
  // cleanup does not own — destroy it or the next test queries a stale dialog.
  Modal.destroyAll();
  vi.restoreAllMocks();
});

describe("GraduateAsSkillButton (SPEC-055 R-4)", () => {
  it.each([["operator"], ["approver"], ["platform-admin"]])(
    "renders for %s",
    (role) => {
      useRoles([role]);
      render(<GraduateAsSkillButton sessionId="ses-1" />);
      expect(screen.getByLabelText("Graduate as skill")).toBeTruthy();
    },
  );

  it.each([["read-only-observer"], ["developer"], ["auditor"]])(
    "stays hidden for %s",
    (role) => {
      useRoles([role]);
      render(<GraduateAsSkillButton sessionId="ses-1" />);
      expect(screen.queryByLabelText("Graduate as skill")).toBeNull();
    },
  );

  it("opens the preview on the graduated badge and downloads nothing yet", async () => {
    useRoles(["operator"]);
    mockGraduate.mockResolvedValue(GRADUATION_RESPONSE);
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    render(<GraduateAsSkillButton sessionId="ses-dev-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Graduate as skill"));
    });
    expect(mockGraduate).toHaveBeenCalledWith("ses-dev-1");
    expect(clickSpy).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(await screen.findByText("Executable-flow draft preview")).toBeTruthy();
    expect(screen.getByText("graduated · no model")).toBeTruthy();
    expect(screen.getByTestId("graduation-facts").textContent).toContain(
      "3 replay steps",
    );
    expect(screen.getByLabelText("Download skill draft markdown")).toBeTruthy();
  });

  it("shows the busy state while graduation runs", async () => {
    useRoles(["operator"]);
    let release: (value: typeof GRADUATION_RESPONSE) => void = () => {};
    mockGraduate.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    render(<GraduateAsSkillButton sessionId="ses-1" />);
    const button = screen.getByLabelText("Graduate as skill");
    await act(async () => {
      fireEvent.click(button);
    });
    expect(button.closest("button")?.className).toContain("ant-btn-loading");
    fireEvent.click(button);
    expect(mockGraduate).toHaveBeenCalledTimes(1);
    await act(async () => {
      release(GRADUATION_RESPONSE);
    });
    expect(button.closest("button")?.className).not.toContain(
      "ant-btn-loading",
    );
  });

  it("surfaces a 409 blast-radius refusal with the server's own explanation", async () => {
    useRoles(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockGraduate.mockRejectedValue(
      new ApiError(409, "Request failed: 409 Conflict", REFUSAL_DETAIL),
    );
    render(<GraduateAsSkillButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Graduate as skill"));
    });
    // A modal, not a self-dismissing toast: the refusal names step positions
    // and is the only answer the operator gets. antd renders a confirm dialog's
    // title and content in more than one node, so both are counted rather than
    // uniquely queried.
    const titles = await screen.findAllByText("This session cannot be graduated");
    expect(titles.length).toBeGreaterThan(0);
    expect(screen.getAllByText(REFUSAL_DETAIL).length).toBeGreaterThan(0);
    expect(screen.queryByText("Executable-flow draft preview")).toBeNull();
  });

  it("falls back to a generic refusal when the 409 carries no detail", async () => {
    useRoles(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockGraduate.mockRejectedValue(
      new ApiError(409, "Request failed: 409 Conflict"),
    );
    render(<GraduateAsSkillButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Graduate as skill"));
    });
    expect(
      await screen.findByText(
        "Its authoring trace failed blast-radius re-validation.",
      ),
    ).toBeTruthy();
  });

  it("maps a 403 to the role-denial toast", async () => {
    useRoles(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockGraduate.mockRejectedValue(
      new ApiError(403, "Request failed: 403 Forbidden"),
    );
    render(<GraduateAsSkillButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Graduate as skill"));
    });
    expect(
      await screen.findByText("Your role cannot graduate sessions into skills."),
    ).toBeTruthy();
    expect(screen.queryByText("Executable-flow draft preview")).toBeNull();
  });

  it("maps a 404 to the session-unavailable toast", async () => {
    useRoles(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockGraduate.mockRejectedValue(
      new ApiError(404, "Request failed: 404 Not Found"),
    );
    render(<GraduateAsSkillButton sessionId="ses-gone" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Graduate as skill"));
    });
    expect(
      await screen.findByText(
        "This session is no longer available to you (expired or owned by another operator).",
      ),
    ).toBeTruthy();
  });

  it("maps a 503 to the not-configured toast", async () => {
    useRoles(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockGraduate.mockRejectedValue(
      new ApiError(503, "Request failed: 503 Service Unavailable"),
    );
    render(<GraduateAsSkillButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Graduate as skill"));
    });
    expect(
      await screen.findByText("Skill validation is not configured right now."),
    ).toBeTruthy();
  });

  it("maps a 502 to the withheld-draft toast, preferring the server's reason", async () => {
    useRoles(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockGraduate.mockRejectedValue(
      new ApiError(
        502,
        "Request failed: 502 Bad Gateway",
        "graduated draft failed format validation: steps must be a list",
      ),
    );
    render(<GraduateAsSkillButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Graduate as skill"));
    });
    expect(
      await screen.findByText(
        "graduated draft failed format validation: steps must be a list",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Executable-flow draft preview")).toBeNull();
  });
});

describe("DeclareSkillTargetButton (SPEC-055 R-4)", () => {
  it.each([["operator"], ["approver"], ["platform-admin"]])(
    "renders for %s",
    (role) => {
      useRoles([role]);
      render(<DeclareSkillTargetButton sessionId="ses-1" />);
      expect(screen.getByLabelText("Declare skill target")).toBeTruthy();
    },
  );

  it("stays hidden for a read-only-observer", () => {
    useRoles(["read-only-observer"]);
    render(<DeclareSkillTargetButton sessionId="ses-1" />);
    expect(screen.queryByLabelText("Declare skill target")).toBeNull();
  });

  it("reports the target in force rather than an echo of the field", async () => {
    useRoles(["operator"]);
    mockDeclare.mockResolvedValue({
      session_id: "ses-1",
      // Scoped by the agent: origin and path kept, the query dropped.
      target: "https://admin.internal/login",
      already_declared: false,
    });
    render(<DeclareSkillTargetButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Declare skill target"));
    });
    const field = await screen.findByLabelText("Skill target");
    await act(async () => {
      fireEvent.change(field, {
        target: { value: "https://admin.internal/login?token=abc" },
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Declare"));
    });
    expect(mockDeclare).toHaveBeenCalledWith(
      "ses-1",
      "https://admin.internal/login?token=abc",
    );
    expect(
      await screen.findByText("Target in force: https://admin.internal/login"),
    ).toBeTruthy();
  });

  it("warns when a different target is already in force", async () => {
    useRoles(["operator"]);
    mockDeclare.mockResolvedValue({
      session_id: "ses-1",
      target: "https://admin.internal/login",
      already_declared: true,
    });
    render(<DeclareSkillTargetButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Declare skill target"));
    });
    await act(async () => {
      fireEvent.change(await screen.findByLabelText("Skill target"), {
        target: { value: "https://other.internal/console" },
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Declare"));
    });
    // First declaration wins: the field cannot widen a scope already set.
    expect(
      await screen.findByText(
        "A different target is already in force for this session: https://admin.internal/login",
      ),
    ).toBeTruthy();
  });

  it("keeps the dialog open and shows the 422 detail inline", async () => {
    useRoles(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockDeclare.mockRejectedValue(
      new ApiError(
        422,
        "Request failed: 422 Unprocessable Entity",
        "skill target must be an absolute http(s) URL",
      ),
    );
    render(<DeclareSkillTargetButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Declare skill target"));
    });
    await act(async () => {
      fireEvent.change(await screen.findByLabelText("Skill target"), {
        target: { value: "admin.internal" },
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Declare"));
    });
    expect(
      await screen.findByText("skill target must be an absolute http(s) URL"),
    ).toBeTruthy();
    expect(screen.getByText("Declare skill-development target")).toBeTruthy();
  });

  it("will not submit a blank target", async () => {
    useRoles(["operator"]);
    render(<DeclareSkillTargetButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Declare skill target"));
    });
    const declare = await screen.findByText("Declare");
    await act(async () => {
      fireEvent.click(declare);
    });
    expect(mockDeclare).not.toHaveBeenCalled();
  });
});
