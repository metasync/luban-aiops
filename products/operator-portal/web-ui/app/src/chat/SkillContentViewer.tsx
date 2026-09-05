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
              <div
                className="md-content"
                // Safe by construction: renderMarkdown escapes every source
                // character before introducing markup and only renders
                // http(s) links — the shared chat/draft-preview renderer, so
                // no new HTML-producing path is introduced (SPEC-052 R-3).
                dangerouslySetInnerHTML={{ __html: renderMarkdown(body) }}
              />
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
