// Shared skill-draft preview (SPEC-045 R-5): both entry points — the
// chat header session action (SPEC-044) and the incident detail action
// (SPEC-045 R-4) — route their validated draft response through this
// read-only modal before the client-side download. The rendered view
// uses the escape-first chat renderer with the YAML frontmatter fence
// and the provenance HTML comment stripped for display (they are file
// metadata for the skills repo, not narrative — the raw view shows
// them); Download .md always hands over the full raw markdown via the
// SPEC-040 R-4 Blob pattern, Discard drops the in-memory response.
// Nothing is persisted on either path — the preview never becomes a
// durable draft record.
import { useEffect, useState } from "react";
import { Button, Modal, Segmented, Tag, Typography } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import type { SkillDraftResponse } from "../api/sessions";
import { renderMarkdown } from "./markdown";

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

export function SkillDraftPreviewModal({
  draft,
  onClose,
}: {
  draft: SkillDraftResponse | null;
  onClose: () => void;
}) {
  const [view, setView] = useState<"rendered" | "raw">("rendered");

  // Every fresh draft opens on the rendered view.
  useEffect(() => {
    if (draft) setView("rendered");
  }, [draft]);

  return (
    <Modal
      open={draft !== null}
      title="Skill draft preview"
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
            <Tag color={draft.mode === "skeleton" ? "orange" : "green"}>
              {draft.mode === "skeleton" ? "facts-only skeleton" : "generated"}
            </Tag>
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
            Read-only preview — the platform stores nothing. Download the
            markdown to contribute it to the team&apos;s skills repository,
            or discard it.
          </Typography.Paragraph>
        </div>
      ) : null}
    </Modal>
  );
}
