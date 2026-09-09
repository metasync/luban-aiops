// Shared skill-draft preview (SPEC-045 R-5): all three entry points — the
// chat header session action (SPEC-044), the incident detail action
// (SPEC-045 R-4) and the session graduation action (SPEC-055 R-4) — route
// their validated response through this read-only modal before the
// client-side download. The rendered view
// uses the escape-first chat renderer with the YAML frontmatter fence
// and the provenance HTML comment stripped for display (they are file
// metadata for the skills repo, not narrative — the raw view shows
// them); Download .md always hands over the full raw markdown via the
// SPEC-040 R-4 Blob pattern, Discard drops the in-memory response.
// Nothing is persisted on any path — the preview never becomes a
// durable draft record, and a graduation publishes nothing either.
import { useEffect, useState } from "react";
import { Button, Modal, Segmented, Tag, Typography } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import type {
  SkillDraftResponse,
  SkillGraduationResponse,
} from "../api/sessions";
import { renderMarkdown } from "./markdown";

// SPEC-055 R-4: the graduation response is field-compatible with the draft
// response by design, so one modal serves both artifacts and the operator
// learns which one they hold from the badge and the metadata row rather than
// from a second component that would drift. Discriminated on `mode`, never on
// the presence of a field: a draft that grew a `step_count` one day must not
// start claiming to be executable.
//
// The union is spelled out rather than left to `SkillDraftResponse` (which a
// graduation is assignable to) so a caller can hand over either shape —
// including a literal carrying the graduation-only fields.
export type SkillPreviewDraft = SkillDraftResponse | SkillGraduationResponse;

function isGraduation(
  draft: SkillPreviewDraft,
): draft is SkillGraduationResponse {
  return draft.mode === "graduated";
}

// The ordering report, in the operator's terms. It is a report and never a
// gate — `postdated` still hands over the draft, because corroboration of
// every observed origin against the declared one is the control — but it is
// surfaced rather than swallowed: a scope fitted to a trace that had already
// begun is weaker evidence than one the session acted under, and the person
// deciding whether to merge the flow is entitled to know which they have.
const DECLARATION_LABELS: Record<string, { text: string; warn: boolean }> = {
  preceded: {
    text: "target declared before the first captured step",
    warn: false,
  },
  postdated: {
    text: "target declared after the first captured step — a scope fitted to the trace",
    warn: true,
  },
  indeterminate: {
    text: "declaration order indeterminate (both stamps are second-precision)",
    warn: true,
  },
};

// SPEC-040 R-4 client-side Blob download of the raw validated markdown.
export function downloadSkillDraft(result: SkillDraftResponse): void {
  const blob = new Blob([result.markdown], {
    type: "text/markdown;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = url;
  anchor.download = result.suggested_filename;
  window.document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

// Display-only strips: the leading YAML frontmatter fence (ingestion
// metadata) and HTML comments (the deterministic provenance block).
// renderMarkdown escapes every source character, so a comment would
// otherwise surface as literal "&lt;!--" text instead of hiding.
const FRONTMATTER_FENCE = /^---\n[\s\S]*?\n---\n*/;
const HTML_COMMENTS = /<!--[\s\S]*?-->/g;

function renderedView(markdown: string): string {
  return renderMarkdown(
    markdown.replace(FRONTMATTER_FENCE, "").replace(HTML_COMMENTS, ""),
  );
}

// The mode badge vocabulary. `graduated` is blue rather than green on
// purpose: a graduated flow is not a better draft, it is a different artifact
// class — executable, write-risk, replayed under one gate — and reusing the
// success colour would let it read as the same thing's happy state.
const MODE_BADGES: Record<string, { color: string; label: string }> = {
  skeleton: { color: "orange", label: "facts-only skeleton" },
  generated: { color: "green", label: "generated" },
  graduated: { color: "blue", label: "graduated · no model" },
};

export function SkillDraftPreviewModal({
  draft,
  onClose,
}: {
  draft: SkillPreviewDraft | null;
  onClose: () => void;
}) {
  const [view, setView] = useState<"rendered" | "raw">("rendered");

  // Every fresh draft opens on the rendered view.
  useEffect(() => {
    if (draft) setView("rendered");
  }, [draft]);

  const graduation = draft && isGraduation(draft) ? draft : null;
  const badge = draft
    ? MODE_BADGES[draft.mode] ?? { color: "default", label: draft.mode }
    : null;
  // An unrecognized ordering value warns rather than reassuring: a backend that
  // grows a fourth answer must not have it rendered as if it were `preceded`.
  const declaration = graduation
    ? DECLARATION_LABELS[graduation.declaration] ?? {
        text: `declaration: ${graduation.declaration}`,
        warn: true,
      }
    : null;

  return (
    <Modal
      open={draft !== null}
      title={
        draft && isGraduation(draft)
          ? "Executable-flow draft preview"
          : "Skill draft preview"
      }
      width={760}
      onCancel={onClose}
      footer={
        draft ? (
          <>
            <Button onClick={onClose} aria-label="Discard skill draft">
              Discard
            </Button>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              aria-label="Download skill draft markdown"
              onClick={() => {
                downloadSkillDraft(draft);
                onClose();
              }}
            >
              Download .md
            </Button>
          </>
        ) : null
      }
    >
      {draft ? (
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
            <Tag color={badge?.color}>{badge?.label}</Tag>
            <Typography.Text type="secondary">
              validation: {draft.validation}
            </Typography.Text>
            <Typography.Text type="secondary">
              {draft.suggested_filename}
            </Typography.Text>
            <Segmented
              size="small"
              style={{ marginLeft: "auto" }}
              aria-label="Preview view"
              value={view}
              onChange={(value) => setView(value as "rendered" | "raw")}
              options={[
                { label: "Rendered", value: "rendered" },
                { label: "Raw", value: "raw" },
              ]}
            />
          </div>
          {graduation && declaration ? (
            // The blast-radius facts a graduated draft carries and a prose
            // draft cannot: how many approved mutations replay, the scope
            // they are bound to, and whether that scope was in force before
            // the first of them ran.
            <div
              data-testid="graduation-facts"
              style={{ marginBottom: 8, lineHeight: 1.6 }}
            >
              <Typography.Text type="secondary">
                {graduation.step_count} replay step
                {graduation.step_count === 1 ? "" : "s"} ·{" "}
                {graduation.web_target
                  ? `bound to ${graduation.web_target}`
                  : "infrastructure flow — no web target"}
              </Typography.Text>
              <br />
              <Typography.Text type={declaration.warn ? "warning" : "secondary"}>
                {declaration.text}
              </Typography.Text>
            </div>
          ) : null}
          <div
            data-testid="skill-draft-preview-body"
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
                // Safe by construction: renderMarkdown escapes every
                // source character before introducing markup and only
                // renders http(s) links.
                dangerouslySetInnerHTML={{
                  __html: renderedView(draft.markdown),
                }}
              />
            ) : (
              <pre className="evidence-pre">{draft.markdown}</pre>
            )}
          </div>
          <Typography.Paragraph
            type="secondary"
            style={{ marginTop: 8, marginBottom: 0 }}
          >
            {graduation ? (
              <>
                Read-only preview — nothing is published and the platform
                stores no copy. This draft declares{" "}
                <code>risk_class: write</code> and an executable step list
                built only from mutations a human already approved, so
                merging it into the team&apos;s skills repository is a
                deliberate human act: once it is a skill, a replay runs the
                whole flow under one gate.
              </>
            ) : (
              <>
                Read-only preview — the platform stores nothing. Download the
                markdown to contribute it to the team&apos;s skills
                repository, or discard it.
              </>
            )}
          </Typography.Paragraph>
        </div>
      ) : null}
    </Modal>
  );
}
