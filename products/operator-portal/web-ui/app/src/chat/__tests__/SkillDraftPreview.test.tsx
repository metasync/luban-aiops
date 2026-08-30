// Shared skill-draft preview tests (SPEC-045 R-5): the read-only modal
// both entry points route through. The rendered view strips the YAML
// frontmatter fence and the provenance HTML comment (display-only —
// the raw view and the download keep the full markdown), the mode
// badge distinguishes generated from facts-only skeleton, Download .md
// hands over the raw markdown via the SPEC-040 R-4 Blob pattern, and
// Discard drops the response without downloading.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SkillDraftPreviewModal } from "../SkillDraftPreview";
import type { SkillDraftResponse } from "../../api/sessions";

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
