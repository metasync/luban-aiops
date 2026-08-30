// Draft-as-skill session action tests (SPEC-044 R-5, rewired by
// SPEC-045 R-5): role-matrix visibility (client-side mirror of
// allow-operators-skill-draft; the gateway re-enforces
// session:skill_draft regardless), the busy state, the shared preview
// modal opening with the mode badge instead of a blind download, and
// the structured 403/502/503 error toasts.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DraftAsSkillButton } from "../ChatView";

const { mockUseAuth, mockCreateSkillDraft } = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockCreateSkillDraft: vi.fn(),
}));

vi.mock("../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));
vi.mock("../../api/sessions", () => ({
  createSkillDraft: mockCreateSkillDraft,
  // ChatView imports the session fetch too; keep the binding present.
  getSession: vi.fn(),
}));

const DRAFT_RESPONSE = {
  markdown: "---\ntitle: \"Restart checkout\"\n---\n\nBody\n",
  mode: "generated",
  validation: "passed",
  suggested_filename: "restart-checkout.md",
};

function useRoles(roles: string[]) {
  mockUseAuth.mockReturnValue({ roles });
}

beforeEach(() => {
  // Call counts must not leak between tests (restoreAllMocks does not
  // clear vi.fn instances created in vi.hoisted).
  mockCreateSkillDraft.mockReset();
  mockUseAuth.mockReset();
  // jsdom lacks the Blob-URL surface the SPEC-040 R-4 download uses.
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("DraftAsSkillButton (SPEC-044 R-5)", () => {
  it.each([["operator"], ["approver"], ["platform-admin"]])(
    "renders for %s",
    (role) => {
      useRoles([role]);
      render(<DraftAsSkillButton sessionId="ses-1" />);
      expect(screen.getByLabelText("Draft as skill")).toBeTruthy();
    },
  );

  it.each([["read-only-observer"], ["developer"], ["auditor"]])(
    "stays hidden for %s",
    (role) => {
      useRoles([role]);
      render(<DraftAsSkillButton sessionId="ses-1" />);
      expect(screen.queryByLabelText("Draft as skill")).toBeNull();
    },
  );

  it("opens the preview modal with the generated badge and no download", async () => {
    useRoles(["operator"]);
    mockCreateSkillDraft.mockResolvedValue(DRAFT_RESPONSE);
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    render(<DraftAsSkillButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(mockCreateSkillDraft).toHaveBeenCalledWith("ses-1");
    // Preview first: nothing downloads until the modal's Download .md.
    expect(clickSpy).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(await screen.findByText("Skill draft preview")).toBeTruthy();
    expect(screen.getByText("generated")).toBeTruthy();
    expect(screen.getByText("restart-checkout.md")).toBeTruthy();
    expect(
      screen.getByLabelText("Download skill draft markdown"),
    ).toBeTruthy();
  });

  it("badges the facts-only skeleton mode in the preview modal", async () => {
    useRoles(["operator"]);
    mockCreateSkillDraft.mockResolvedValue({
      ...DRAFT_RESPONSE,
      mode: "skeleton",
      suggested_filename: "session-skill-draft.md",
    });
    render(<DraftAsSkillButton sessionId="ses-quiet" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(await screen.findByText("Skill draft preview")).toBeTruthy();
    expect(screen.getByText("facts-only skeleton")).toBeTruthy();
  });

  it("shows the busy state while generation runs", async () => {
    useRoles(["operator"]);
    let release: (value: typeof DRAFT_RESPONSE) => void = () => {};
    mockCreateSkillDraft.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    render(<DraftAsSkillButton sessionId="ses-1" />);
    const button = screen.getByLabelText("Draft as skill");
    await act(async () => {
      fireEvent.click(button);
    });
    // The antd loading state disables re-entry while generation runs.
    expect(button.closest("button")?.className).toContain("ant-btn-loading");
    fireEvent.click(button);
    expect(mockCreateSkillDraft).toHaveBeenCalledTimes(1);
    await act(async () => {
      release(DRAFT_RESPONSE);
    });
    expect(button.closest("button")?.className).not.toContain(
      "ant-btn-loading",
    );
  });

  it("maps a 403 to the role-denial toast without opening the preview", async () => {
    useRoles(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockCreateSkillDraft.mockRejectedValue(
      new ApiError(403, "Request failed: 403 Forbidden"),
    );
    render(<DraftAsSkillButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(screen.queryByText("Skill draft preview")).toBeNull();
    expect(
      await screen.findByText("Your role cannot draft skills from sessions."),
    ).toBeTruthy();
  });

  it("maps a 503 to the not-configured toast", async () => {
    useRoles(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockCreateSkillDraft.mockRejectedValue(
      new ApiError(503, "Request failed: 503 Service Unavailable"),
    );
    render(<DraftAsSkillButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(
      await screen.findByText("Skill validation is not configured right now."),
    ).toBeTruthy();
  });

  it("maps a 502 to the unreachable toast", async () => {
    useRoles(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockCreateSkillDraft.mockRejectedValue(
      new ApiError(502, "Request failed: 502 Bad Gateway"),
    );
    render(<DraftAsSkillButton sessionId="ses-1" />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(
      await screen.findByText(
        "Skill validation is unreachable — no draft returned.",
      ),
    ).toBeTruthy();
  });
});
