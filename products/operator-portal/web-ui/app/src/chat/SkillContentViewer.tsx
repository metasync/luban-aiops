// Read-only skill content viewer (SPEC-052 R-3): the Skills inventory view
// opens an ingested skill's full record here so an operator can read what a
// skill actually does — its declared steps and narrative — before trusting it
// to drive tool behaviour and HITL gates. It mirrors the SPEC-045 draft
// preview (a Rendered/Raw Segmented toggle over a bounded pane, using the same
// escape-first renderer) but is strictly read-only: the header carries skill
// metadata rather than draft-generation state, and there is no
// download-as-contribution or discard. Ingested skills live in the team's Git
// repository; authoring/export stays on the SPEC-044/045 path.
import { useEffect, useState } from "react";
import { Button, Modal, Segmented, Tag, Typography } from "antd";
import { renderMarkdown } from "./markdown";

// One sub-skill of a composition, as projected by skills-hub's get_skill read
// path (SPEC-057 R-6). The authored/stored item carries just skill_id + note;
// the resolved_* fields are a read-path enrichment (each sub-skill's own title
// and declared target) so a reviewer sees what each segment was scoped to.
export interface SubSkillView {
  skill_id: string;
  note?: string;
  resolved_title?: string;
  resolved_web_target?: string;
}

// The single-skill detail shape returned by the gateway proxy (SPEC-052 R-1),
// which forwards skills-hub's full record. `body` travels only here — the list
// payload omits it by contract (skill.schema.json).
export interface SkillDetail {
  skill_id: string;
  title?: string;
  description?: string;
  source_id?: string;
  tags?: string[];
  version?: string;
  updated_at?: string;
  web_target?: string;
  // SPEC-057 R-1/R-7: a composition's ordered sub-skill reference list and
  // its derived display-only risk_class. Present only for kind=composition.
  kind?: string;
  risk_class?: string;
  sub_skills?: SubSkillView[];
  body?: string;
}

export function SkillContentViewer({
  skill,
  onClose,
}: {
  skill: SkillDetail | null;
  onClose: () => void;
}) {
  const [view, setView] = useState<"rendered" | "raw">("rendered");

  // Every freshly opened skill starts on the rendered view.
  useEffect(() => {
    if (skill) setView("rendered");
  }, [skill]);

  const body = skill?.body ?? "";
  // SPEC-057 R-7: a composition's ordered sub-skill list, as projected by
  // skills-hub's read path (R-6). Rendered-only structured guidance — the Raw
  // view keeps showing the authored body verbatim. Order is the declared runbook
  // sequence; each item names its own sub-skill's title and declared target so a
  // reviewer sees what each segment was scoped to. Display only: nothing here
  // gates, pre-binds a sub-skill, or enforces the order (ADR-0011).
  const subSkills = skill?.sub_skills ?? [];

  return (
    <Modal
      open={skill !== null}
      title={skill?.title || skill?.skill_id || "Skill"}
      width={760}
      onCancel={onClose}
      footer={
        <Button onClick={onClose} aria-label="Close skill viewer">
          Close
        </Button>
      }
    >
      {skill ? (
        <div>
          <div
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              flexWrap: "wrap",
              marginBottom: 8,
            }}
          >
            {skill.source_id ? (
              <Typography.Text type="secondary">
                source: {skill.source_id}
              </Typography.Text>
            ) : null}
            {skill.version ? (
              <Typography.Text type="secondary">v{skill.version}</Typography.Text>
            ) : null}
            {(skill.tags ?? []).map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
            {skill.web_target ? (
              <Typography.Text type="secondary">
                target: {skill.web_target}
              </Typography.Text>
            ) : null}
            <Segmented
              size="small"
              style={{ marginLeft: "auto" }}
              aria-label="Skill view"
              value={view}
              onChange={(value) => setView(value as "rendered" | "raw")}
              options={[
                { label: "Rendered", value: "rendered" },
                { label: "Raw", value: "raw" },
              ]}
            />
          </div>
          <div
            data-testid="skill-content-body"
            style={{
              maxHeight: "55vh",
              overflowY: "auto",
              border: "1px solid rgba(128, 128, 128, 0.25)",
              borderRadius: 6,
              padding: 12,
            }}
          >
            {view === "rendered" ? (
              <>
                {subSkills.length > 0 ? (
                  <div
                    data-testid="skill-sub-skills"
                    style={{ marginBottom: 12 }}
                  >
                    <Typography.Text strong>
                      Runbook · {subSkills.length} sub-skill
                      {subSkills.length === 1 ? "" : "s"}
                    </Typography.Text>
                    <ol style={{ margin: "8px 0 0", paddingLeft: 20 }}>
                      {subSkills.map((sub, index) => (
                        <li
                          key={`${sub.skill_id}-${index}`}
                          data-testid="skill-sub-skill"
                          style={{ marginBottom: 6 }}
                        >
                          <Typography.Text strong>
                            {sub.resolved_title || sub.skill_id}
                          </Typography.Text>
                          {sub.resolved_web_target ? (
                            <Typography.Text type="secondary">
                              {" · target: "}
                              {sub.resolved_web_target}
                            </Typography.Text>
                          ) : null}
                          {sub.note ? (
                            <div>
                              <Typography.Text type="secondary">
                                {sub.note}
                              </Typography.Text>
                            </div>
                          ) : null}
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
                <div
                  className="md-content"
                  // Safe by construction: renderMarkdown escapes every source
                  // character before introducing markup and only renders
                  // http(s) links — the shared chat/draft-preview renderer, so
                  // no new HTML-producing path is introduced (SPEC-052 R-3).
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(body) }}
                />
              </>
            ) : (
              <pre className="evidence-pre">{body}</pre>
            )}
          </div>
          <Typography.Paragraph
            type="secondary"
            style={{ marginTop: 8, marginBottom: 0 }}
          >
            Read-only view of an ingested skill. Skills are authored in the
            team&apos;s Git repository; this viewer stores nothing.
          </Typography.Paragraph>
        </div>
      ) : null}
    </Modal>
  );
}
