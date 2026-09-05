// Skill content viewer tests (SPEC-052 R-3): the read-only rendered/raw modal
// the Skills inventory opens for an ingested skill. It reuses the escape-first
// renderer (a hostile body is escaped, never executed), shows skill metadata
// rather than draft-generation state, and offers no download/discard — viewing
// an ingested skill is distinct from the SPEC-044/045 authoring export flow.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SkillContentViewer, type SkillDetail } from "../SkillContentViewer";

const SKILL: SkillDetail = {
  skill_id: "sre-alerting/reset-password",
  title: "Reset password",
  source_id: "sre-alerting",
  version: "1.2.0",
  tags: ["browser", "identity"],
  web_target: "https://admin.example.com",
  body: "# Steps\n\n1. Open the console.\n2. Click **Confirm reset**.",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SkillContentViewer (SPEC-052 R-3)", () => {
  it("stays closed without a skill", () => {
    render(<SkillContentViewer skill={null} onClose={() => {}} />);
    expect(screen.queryByTestId("skill-content-body")).toBeNull();
  });

  it("opens on the rendered view with skill metadata, not draft state", () => {
    render(<SkillContentViewer skill={SKILL} onClose={() => {}} />);
    expect(screen.getByText("Reset password")).toBeTruthy(); // modal title
    expect(screen.getByText("source: sre-alerting")).toBeTruthy();
    expect(screen.getByText("v1.2.0")).toBeTruthy();
    expect(screen.getByText("browser")).toBeTruthy();
    expect(screen.getByText("target: https://admin.example.com")).toBeTruthy();
    // Draft-only concepts never leak into the ingested-skill viewer.
    expect(screen.queryByText("Download .md")).toBeNull();
    expect(screen.queryByText("Discard")).toBeNull();
    // Rendered by default: the markdown became structured HTML.
    const body = screen.getByTestId("skill-content-body");
    expect(body.querySelector("h1")?.textContent).toContain("Steps");
    expect(body.querySelector("strong")?.textContent).toBe("Confirm reset");
  });

  it("switches to the raw view showing the markdown body and back", async () => {
    render(<SkillContentViewer skill={SKILL} onClose={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByText("Raw"));
    });
    const pre = screen
      .getByTestId("skill-content-body")
      .querySelector("pre.evidence-pre");
    expect(pre?.textContent).toContain("# Steps");
    expect(pre?.textContent).toContain("Confirm reset");
    await act(async () => {
      fireEvent.click(screen.getByText("Rendered"));
    });
    expect(
      screen.getByTestId("skill-content-body").querySelector("pre.evidence-pre"),
    ).toBeNull();
  });

  it("escapes a hostile body rather than executing it", () => {
    const hostile: SkillDetail = {
      ...SKILL,
      body: "Hi <script>window.__pwned = 1</script> <img src=x onerror=alert(1)>",
    };
    render(<SkillContentViewer skill={hostile} onClose={() => {}} />);
    const body = screen.getByTestId("skill-content-body");
    // No live script/img elements are created from the raw body.
    expect(body.querySelector("script")).toBeNull();
    expect(body.querySelector("img")).toBeNull();
    // The escaped markup surfaces as literal text.
    expect(body.textContent).toContain("<script>");
  });

  it("closes via the Close control", () => {
    const onClose = vi.fn();
    render(<SkillContentViewer skill={SKILL} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText("Close skill viewer"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
