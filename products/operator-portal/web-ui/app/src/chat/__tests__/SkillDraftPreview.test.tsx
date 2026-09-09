// Shared skill-draft preview tests (SPEC-045 R-5, extended by SPEC-055 R-4):
// the read-only modal all three entry points route through. The rendered view
// strips the YAML
// frontmatter fence and the provenance HTML comment (display-only —
// the raw view and the download keep the full markdown), the mode
// badge distinguishes generated from facts-only skeleton from graduated
// executable flow, Download .md
// hands over the raw markdown via the SPEC-040 R-4 Blob pattern, and
// Discard drops the response without downloading.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SkillDraftPreviewModal } from "../SkillDraftPreview";
import type {
  SkillDraftResponse,
  SkillGraduationResponse,
} from "../../api/sessions";

const MARKDOWN =
  '---\ntitle: "Restart checkout"\n---\n' +
  "<!-- skill-draft provenance\ngenerated-by: luban-agent-platform\n" +
  "session: ses-1\n-->\n# Restart checkout\n\nBody text.\n";

const DRAFT: SkillDraftResponse = {
  markdown: MARKDOWN,
  mode: "generated",
  validation: "passed",
  suggested_filename: "restart-checkout.md",
};

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SkillDraftPreviewModal (SPEC-045 R-5)", () => {
  it("stays closed without a draft", () => {
    render(<SkillDraftPreviewModal draft={null} onClose={() => {}} />);
    expect(screen.queryByText("Skill draft preview")).toBeNull();
  });

  it("shows the generated badge, filename, and rendered body", () => {
    render(<SkillDraftPreviewModal draft={DRAFT} onClose={() => {}} />);
    expect(screen.getByText("Skill draft preview")).toBeTruthy();
    expect(screen.getByText("generated")).toBeTruthy();
    expect(screen.getByText("validation: passed")).toBeTruthy();
    expect(screen.getByText("restart-checkout.md")).toBeTruthy();
    const body = screen.getByTestId("skill-draft-preview-body");
    expect(body.textContent).toContain("Restart checkout");
    expect(body.textContent).toContain("Body text.");
    // Display-only strips: frontmatter and provenance never surface in
    // the rendered view.
    expect(body.textContent).not.toContain("generated-by");
    expect(body.textContent).not.toContain("session: ses-1");
  });

  it("badges the facts-only skeleton mode", () => {
    render(
      <SkillDraftPreviewModal
        draft={{ ...DRAFT, mode: "skeleton" }}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("facts-only skeleton")).toBeTruthy();
  });

  it("keeps the full markdown (frontmatter and provenance) in the raw view", async () => {
    render(<SkillDraftPreviewModal draft={DRAFT} onClose={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByText("Raw"));
    });
    const body = screen.getByTestId("skill-draft-preview-body");
    expect(body.textContent).toContain('title: "Restart checkout"');
    expect(body.textContent).toContain("generated-by: luban-agent-platform");
    expect(body.textContent).toContain("session: ses-1");
    // Switching back resets to the stripped rendered view.
    await act(async () => {
      fireEvent.click(screen.getByText("Rendered"));
    });
    expect(
      screen.getByTestId("skill-draft-preview-body").textContent,
    ).not.toContain("generated-by");
  });

  it("downloads the raw markdown under the suggested filename and closes", async () => {
    const onClose = vi.fn();
    let downloaded: string | null = null;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      function (this: HTMLAnchorElement) {
        downloaded = this.download;
      },
    );
    render(<SkillDraftPreviewModal draft={DRAFT} onClose={onClose} />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Download skill draft markdown"));
    });
    expect(downloaded).toBe("restart-checkout.md");
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("discards without downloading", async () => {
    const onClose = vi.fn();
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    render(<SkillDraftPreviewModal draft={DRAFT} onClose={onClose} />);
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Discard skill draft"));
    });
    expect(clickSpy).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

// SPEC-055 R-4: the same modal serves a graduated executable flow, which is
// a different artifact class rather than a better draft — the badge must not
// read as the generated draft's success state, and the blast-radius facts a
// prose draft cannot carry (how many approved mutations replay, the scope
// they bind to, and whether that scope was in force before the first of them
// ran) have to be on screen before anyone merges the file.
const GRADUATED_MARKDOWN =
  '---\ntitle: "Reset a user\'s password on the admin portal"\n' +
  'description: "Replays 4 approved mutating step(s)."\n' +
  'tags: ["executable-flow", "graduated"]\n' +
  'web_target: "https://admin.internal/login"\n' +
  "risk_class: write\nkind: executable_flow\nsteps:\n" +
  '  - tool: "web.click"\n    args: {"selector": "#users"}\n' +
  '  - tool: "web.type"\n    args: {"selector": "#search", "text": "alice"}\n' +
  "---\n\n" +
  "<!--\nSkill draft generated by the Luban AIOps platform.\n" +
  "session: ses-grad-1\nmode: graduated\n-->\n\n" +
  "## Replay runbook\n\n- Session: `ses-grad-1`\n" +
  "- Steps: 4 of a 20-step replay budget\n";

const GRADUATION: SkillGraduationResponse = {
  markdown: GRADUATED_MARKDOWN,
  mode: "graduated",
  validation: "passed",
  suggested_filename: "reset-a-users-password-on-the-admin-portal.md",
  step_count: 4,
  web_target: "https://admin.internal/login",
  declaration: "preceded",
};

describe("SkillDraftPreviewModal — graduated flow (SPEC-055 R-4)", () => {
  it("badges the graduation and reports its blast-radius facts", () => {
    render(<SkillDraftPreviewModal draft={GRADUATION} onClose={() => {}} />);
    expect(screen.getByText("Executable-flow draft preview")).toBeTruthy();
    // Blue, and worded so it cannot be mistaken for a generated draft.
    expect(screen.getByText("graduated · no model")).toBeTruthy();
    expect(screen.queryByText("generated")).toBeNull();
    const facts = screen.getByTestId("graduation-facts");
    expect(facts.textContent).toContain("4 replay steps");
    expect(facts.textContent).toContain(
      "bound to https://admin.internal/login",
    );
    expect(facts.textContent).toContain(
      "target declared before the first captured step",
    );
    // Merging is a human act and nothing was published to get there.
    expect(document.body.textContent).toContain("nothing is published");
    expect(document.body.textContent).toContain("risk_class: write");
  });

  it("surfaces a postdated declaration as a warning but still hands over the draft", () => {
    render(
      <SkillDraftPreviewModal
        draft={{ ...GRADUATION, declaration: "postdated" }}
        onClose={() => {}}
      />,
    );
    const facts = screen.getByTestId("graduation-facts");
    expect(facts.textContent).toContain(
      "target declared after the first captured step — a scope fitted to the trace",
    );
    // A report, never a gate: the draft is still downloadable.
    expect(screen.getByLabelText("Download skill draft markdown")).toBeTruthy();
  });

  it("warns on an ordering value it does not recognize", () => {
    // A backend that grows a fourth answer must not have it rendered as if it
    // were `preceded`.
    render(
      <SkillDraftPreviewModal
        draft={{ ...GRADUATION, declaration: "sideways" }}
        onClose={() => {}}
      />,
    );
    expect(screen.getByTestId("graduation-facts").textContent).toContain(
      "declaration: sideways",
    );
  });

  it("reports an infrastructure flow that carries no web target", () => {
    render(
      <SkillDraftPreviewModal
        draft={{ ...GRADUATION, web_target: null, step_count: 1 }}
        onClose={() => {}}
      />,
    );
    const facts = screen.getByTestId("graduation-facts");
    expect(facts.textContent).toContain("1 replay step");
    expect(facts.textContent).toContain("infrastructure flow — no web target");
  });

  it("keeps the executable step list in the raw view and downloads it", async () => {
    const onClose = vi.fn();
    let downloaded: string | null = null;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      function (this: HTMLAnchorElement) {
        downloaded = this.download;
      },
    );
    render(<SkillDraftPreviewModal draft={GRADUATION} onClose={onClose} />);
    // The rendered view is the runbook, not the machine-readable frontmatter.
    const rendered = screen.getByTestId("skill-draft-preview-body");
    expect(rendered.textContent).toContain("Replay runbook");
    expect(rendered.textContent).not.toContain("kind: executable_flow");
    await act(async () => {
      fireEvent.click(screen.getByText("Raw"));
    });
    const raw = screen.getByTestId("skill-draft-preview-body");
    expect(raw.textContent).toContain("kind: executable_flow");
    expect(raw.textContent).toContain('  - tool: "web.click"');
    expect(raw.textContent).toContain("mode: graduated");
    // The download is the full raw file, frontmatter and provenance included.
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Download skill draft markdown"));
    });
    expect(downloaded).toBe("reset-a-users-password-on-the-admin-portal.md");
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
