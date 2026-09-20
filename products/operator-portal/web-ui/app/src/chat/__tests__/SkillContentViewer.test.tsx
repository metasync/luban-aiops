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

// A composition as skills-hub's get_skill read path projects it (SPEC-057 R-6):
// the authored item carries skill_id + note; resolved_title/resolved_web_target
// are the read-path enrichment. The second sub-skill is an infra write with no
// declared target, so it renders no target line.
const COMPOSITION: SkillDetail = {
  skill_id: "samples/composition-account-recovery",
  title: "Account Recovery Runbook",
  source_id: "samples",
  kind: "composition",
  risk_class: "write",
  sub_skills: [
    {
      skill_id: "samples/password-reset-resetacmepassword",
      note: "Reset the password on the admin portal first.",
      resolved_title: "Reset ACME Password",
      resolved_web_target: "http://acme-admin:8080/admin/",
    },
    {
      skill_id: "samples/lock-unlock-user-lockunlockuser",
      note: "Then unlock the account via the infra API.",
      resolved_title: "Lock/Unlock User",
    },
  ],
  body: "On failure, report which sub-skill failed and stop.",
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

describe("SkillContentViewer composition (SPEC-057 R-7)", () => {
  it("renders sub_skills as an ordered list (title, target, note)", () => {
    render(<SkillContentViewer skill={COMPOSITION} onClose={() => {}} />);
    const items = screen
      .getByTestId("skill-sub-skills")
      .querySelectorAll("ol li");
    expect(items).toHaveLength(2);
    // Order is the declared runbook sequence; each item names its own
    // sub-skill's resolved title, declared target and note.
    expect(items[0].textContent).toContain("Reset ACME Password");
    expect(items[0].textContent).toContain(
      "target: http://acme-admin:8080/admin/",
    );
    expect(items[0].textContent).toContain(
      "Reset the password on the admin portal first.",
    );
    // The infra sub-skill declares no web_target, so it renders no target line.
    expect(items[1].textContent).toContain("Lock/Unlock User");
    expect(items[1].textContent).toContain(
      "Then unlock the account via the infra API.",
    );
    expect(items[1].textContent).not.toContain("target:");
    // The authored body prose still renders beneath the list.
    expect(screen.getByTestId("skill-content-body").textContent).toContain(
      "report which sub-skill failed and stop",
    );
  });

  it("falls back to the skill_id when a sub-skill title is unresolved", () => {
    // A sub-skill missing at read time degrades to its authored item (R-6): the
    // list still names the reference rather than dropping the segment.
    const degraded: SkillDetail = {
      ...COMPOSITION,
      sub_skills: [{ skill_id: "samples/missing-sub-skill" }],
    };
    render(<SkillContentViewer skill={degraded} onClose={() => {}} />);
    expect(screen.getByTestId("skill-sub-skill").textContent).toContain(
      "samples/missing-sub-skill",
    );
  });

  it("shows the body verbatim and no structured list in the Raw view", async () => {
    render(<SkillContentViewer skill={COMPOSITION} onClose={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByText("Raw"));
    });
    // The ordered list is Rendered-only; Raw shows the authored body verbatim.
    expect(screen.queryByTestId("skill-sub-skills")).toBeNull();
    const pre = screen
      .getByTestId("skill-content-body")
      .querySelector("pre.evidence-pre");
    expect(pre?.textContent).toContain("report which sub-skill failed and stop");
  });

  it("renders no sub-skill list for a non-composition skill", () => {
    render(<SkillContentViewer skill={SKILL} onClose={() => {}} />);
    expect(screen.queryByTestId("skill-sub-skills")).toBeNull();
  });
});
