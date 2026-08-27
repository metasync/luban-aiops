// Documents view (SPEC-039 R-6, moved to Workspace per SPEC-040 R-3):
// create, manage, publish, and read operations documents. The digest
// renders as the primary surface; the AI narrative panel is labeled
// unmistakably as digest-anchored (SPEC-040 R-2). Cross-owner reads
// attribute the creator prominently (R-5 audit rides the agent layer;
// the view only renders). Export (SPEC-040 R-4) serializes the
// already-fetched document client-side — no new gateway call.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  Collapse,
  Drawer,
  Empty,
  Input,
  Modal,
  Select,
  Spin,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  DownloadOutlined,
  FileTextOutlined,
  PlusOutlined,
  SendOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { ApiError, currentAuthenticatedUser } from "../../api/client";
import {
  createDocument,
  deleteDocument,
  getDocument,
  listDocuments,
  publishDocument,
  type DocumentListRow,
  type OperationDocument,
} from "../../api/documents";
import type { SessionWorkspace } from "../../sessions/useSessionWorkspace";

dayjs.extend(relativeTime);

const MAX_SESSION_IDS = 20;

function createFailureMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 403) {
    return (
      "Foreign sessions are not covered by your role: only designated " +
      "approvers may include other operators' sessions."
    );
  }
  if (err instanceof ApiError && err.status === 400) {
    return "The document was rejected: check the label and session ids.";
  }
  return err instanceof Error ? err.message : String(err);
}

// --- Digest rendering ------------------------------------------------------

// The digest is typed-but-open: the shift-summary builder owns its
// section shapes, so the renderer degrades to labeled JSON lines for
// anything it does not recognize.
function primitiveText(value: unknown): string | null {
  if (value === null) return "null";
  const type = typeof value;
  if (type === "string" || type === "number" || type === "boolean") {
    return String(value);
  }
  return null;
}

function DigestValue({ value, depth = 0 }: { value: unknown; depth?: number }): ReactNode {
  const primitive = primitiveText(value);
  if (primitive !== null) {
    return <Typography.Text>{primitive}</Typography.Text>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <Typography.Text type="secondary">none</Typography.Text>;
    }
    return (
      <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
        {value.map((entry, index) => (
          <li key={index} style={{ marginBottom: 2 }}>
            <DigestValue value={entry} depth={depth + 1} />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <div style={{ paddingLeft: depth > 0 ? 8 : 0 }}>
        {entries.map(([key, entry]) => {
          const entryPrimitive = primitiveText(entry);
          return (
            <div key={key} style={{ marginBottom: 2 }}>
              <Typography.Text type="secondary">{key}: </Typography.Text>
              {entryPrimitive !== null ? (
                <Typography.Text>{entryPrimitive}</Typography.Text>
              ) : (
                <DigestValue value={entry} depth={depth + 1} />
              )}
            </div>
          );
        })}
      </div>
    );
  }
  return <Typography.Text type="secondary">unavailable</Typography.Text>;
}

function DigestSessionEntry({ entry }: { entry: Record<string, unknown> }) {
  const sessionId = typeof entry.session_id === "string" ? entry.session_id : "unknown";
  const title = typeof entry.title === "string" ? entry.title : null;
  const sections = Object.entries(entry).filter(
    ([key]) => key !== "session_id" && key !== "title",
  );
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 12,
        marginBottom: 8,
      }}
    >
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <Typography.Text strong>{title ?? sessionId}</Typography.Text>
        {title ? (
          <Typography.Text type="secondary" copyable={{ text: sessionId }}>
            {sessionId}
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary" copyable>
            {sessionId}
          </Typography.Text>
        )}
      </div>
      {sections.map(([key, value]) => (
        <div key={key} style={{ marginTop: 8 }}>
          <Typography.Text strong style={{ display: "block", fontSize: 12, textTransform: "uppercase", letterSpacing: 0.4 }}>
            {key.replace(/_/g, " ")}
          </Typography.Text>
          <DigestValue value={value} />
        </div>
      ))}
    </div>
  );
}

function DigestPanel({ document }: { document: OperationDocument }) {
  const digest = document.digest ?? {};
  const sessions = Array.isArray((digest as Record<string, unknown>).sessions)
    ? ((digest as Record<string, unknown>).sessions as Record<string, unknown>[])
    : [];
  const handover =
    typeof (digest as Record<string, unknown>).handover === "object" &&
    (digest as Record<string, unknown>).handover !== null
      ? ((digest as Record<string, unknown>).handover as Record<string, unknown>)
      : null;
  const coverageBySession = new Map(
    (document.provenance?.sessions ?? []).map((entry) => [
      entry.session_id,
      entry.coverage,
    ]),
  );
  return (
    <div>
      <div style={{ display: "flex", gap: 16, marginBottom: 12, flexWrap: "wrap" }}>
        <Typography.Text type="secondary">
          Generated {dayjs(String(digest.generated_at ?? document.created_at)).fromNow()}
        </Typography.Text>
        <Typography.Text type="secondary">
          Requested by {String(digest.requester_user_id ?? document.owner_user_id)}
        </Typography.Text>
      </div>
      {handover ? (
        // SPEC-040 R-1: the shift story leads the digest so the
        // relieving operator sees what happened before the receipts.
        <div style={{ marginBottom: 12 }}>
          <Typography.Text
            strong
            style={{ display: "block", fontSize: 12, textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 4 }}
          >
            Handover
          </Typography.Text>
          <DigestValue value={handover} />
        </div>
      ) : null}
      {sessions.map((entry, index) => {
        const sessionId = typeof entry.session_id === "string" ? entry.session_id : "";
        const coverage = coverageBySession.get(sessionId);
        return (
          <div key={sessionId || index}>
            {coverage === "foreign" ? (
              <Tag color="purple" style={{ marginBottom: 4 }}>
                foreign session — metadata only
              </Tag>
            ) : null}
            <DigestSessionEntry entry={entry} />
          </div>
        );
      })}
    </div>
  );
}

function ProsePanel({ document }: { document: OperationDocument }) {
  if (document.prose_status === "included" && document.prose) {
    return (
      <Collapse
        size="small"
        items={[
          {
            key: "prose",
            label: (
              <Typography.Text strong>
                AI-generated narrative — from this document's digest facts
              </Typography.Text>
            ),
            children: (
              <Typography.Paragraph style={{ whiteSpace: "pre-wrap", margin: 0 }}>
                {document.prose}
              </Typography.Paragraph>
            ),
          },
        ]}
      />
    );
  }
  if (document.prose_status === "failed") {
    return (
      <Alert
        type="warning"
        showIcon
        message="Narrative generation failed"
        description="The digest above is the complete record; the generated handover narrative could not be produced."
      />
    );
  }
  return (
    <Typography.Text type="secondary">
      No narrative prose was requested for this document.
    </Typography.Text>
  );
}

// --- Create dialog ----------------------------------------------------------

interface CreateDialogProps {
  open: boolean;
  workspace: SessionWorkspace;
  onClose: () => void;
  onCreated: () => void;
}

function parseForeignIds(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function CreateShiftSummaryDialog({
  open,
  workspace,
  onClose,
  onCreated,
}: CreateDialogProps) {
  const [label, setLabel] = useState("");
  const [ownIds, setOwnIds] = useState<string[]>([]);
  const [foreignRaw, setForeignRaw] = useState("");
  // Narrative is the default since SPEC-040 R-2; the switch is the opt-out.
  const [includeProse, setIncludeProse] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const trimmedLabel = label.trim();
    const foreignIds = parseForeignIds(foreignRaw);
    const sessionIds = [...new Set([...ownIds, ...foreignIds])];
    if (!trimmedLabel) {
      setError("A label is required.");
      return;
    }
    if (sessionIds.length === 0) {
      setError("Select at least one session.");
      return;
    }
    if (sessionIds.length > MAX_SESSION_IDS) {
      setError(`A shift summary covers at most ${MAX_SESSION_IDS} sessions.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createDocument({
        document_type: "shift_summary",
        session_ids: sessionIds,
        label: trimmedLabel,
        include_prose: includeProse,
      });
      message.success("Shift summary draft created.");
      setLabel("");
      setOwnIds([]);
      setForeignRaw("");
      setIncludeProse(true);
      onCreated();
      onClose();
    } catch (err) {
      setError(createFailureMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="New shift summary"
      open={open}
      okText="Create draft"
      confirmLoading={busy}
      onOk={() => void submit()}
      onCancel={onClose}
      destroyOnHidden
    >
      {error ? (
        <Alert
          type="error"
          showIcon
          message={error}
          style={{ marginBottom: 12 }}
        />
      ) : null}
      <Typography.Paragraph type="secondary">
        Captures an immutable digest of up to {MAX_SESSION_IDS} sessions:
        your own sessions in full, foreign sessions at the approver
        metadata level only (denied otherwise).
      </Typography.Paragraph>
      <div style={{ marginBottom: 12 }}>
        <Typography.Text strong>Label</Typography.Text>
        <Input
          value={label}
          maxLength={120}
          placeholder="e.g. Night shift 2026-08-26"
          onChange={(event) => setLabel(event.target.value)}
        />
      </div>
      <div style={{ marginBottom: 12 }}>
        <Typography.Text strong>Your sessions</Typography.Text>
        <Select
          mode="multiple"
          style={{ width: "100%" }}
          placeholder="Pick sessions from your workspace"
          value={ownIds}
          onChange={setOwnIds}
          options={workspace.sessions.map((session) => ({
            value: session.session_id,
            label: `${session.title ?? session.session_id} (${session.session_id})`,
          }))}
          optionFilterProp="label"
        />
      </div>
      <div style={{ marginBottom: 12 }}>
        <Typography.Text strong>Foreign session ids (optional)</Typography.Text>
        <Input.TextArea
          value={foreignRaw}
          autoSize={{ minRows: 1, maxRows: 3 }}
          placeholder="ses-… (space or comma separated)"
          onChange={(event) => setForeignRaw(event.target.value)}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Other operators' sessions are covered only for designated
          approvers and contribute metadata only.
        </Typography.Text>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Switch checked={includeProse} onChange={setIncludeProse} />
        <Typography.Text>
          Include AI handover narrative (anchored to the digest facts,
          labeled)
        </Typography.Text>
      </div>
    </Modal>
  );
}

// --- Export (SPEC-040 R-4) ---------------------------------------------------

// Client-side Markdown serialization of the document the drawer already
// fetched through the audited single-read surface. Export is a rendering
// act, not a new read path: no gateway call, no policy action, and no
// new audit event (the content access was audited at fetch time).

function slugifyLabel(label: string): string {
  const slug = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "document";
}

export function buildDocumentMarkdown(document: OperationDocument): string {
  const lines: string[] = [];
  lines.push(`# ${document.label}`);
  lines.push("");
  lines.push("| Field | Value |");
  lines.push("| --- | --- |");
  lines.push(`| Document id | \`${document.document_id}\` |`);
  lines.push(`| Type | ${document.document_type.replace(/_/g, " ")} |`);
  lines.push(`| State | ${document.state} |`);
  lines.push(`| Owner | ${document.owner_user_id} |`);
  lines.push(`| Created | ${document.created_at} |`);
  if (document.published_at) {
    lines.push(`| Published | ${document.published_at} |`);
  }
  lines.push("");
  lines.push("## Provenance");
  lines.push("");
  for (const session of document.provenance?.sessions ?? []) {
    lines.push(
      `- \`${session.session_id}\` — ${session.coverage} coverage`,
    );
  }
  if ((document.provenance?.sessions ?? []).length === 0) {
    lines.push("- none recorded");
  }
  lines.push("");
  lines.push("## Digest (deterministic facts)");
  lines.push("");
  lines.push("```json");
  lines.push(JSON.stringify(document.digest ?? {}, null, 2));
  lines.push("```");
  if (document.prose_status === "included" && document.prose) {
    lines.push("");
    lines.push(
      "## Handover narrative (AI-generated, anchored to the digest facts)",
    );
    lines.push("");
    lines.push(document.prose);
  } else if (document.prose_status === "failed") {
    lines.push("");
    lines.push(
      "_Narrative generation failed for this document; the digest above " +
        "is the complete record._",
    );
  }
  lines.push("");
  lines.push("---");
  lines.push(
    `Exported ${new Date().toISOString()} from the Luban AIOps operator ` +
      `portal · document ${document.document_id}`,
  );
  return `${lines.join("\n")}\n`;
}

function downloadDocumentMarkdown(document: OperationDocument): void {
  const shortId = document.document_id.slice(-6);
  const filename = `${slugifyLabel(document.label)}-doc-${shortId}.md`;
  const blob = new Blob([buildDocumentMarkdown(document)], {
    type: "text/markdown;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  window.document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

// --- View -------------------------------------------------------------------

export default function DocumentsView({
  workspace,
}: {
  workspace: SessionWorkspace;
}) {
  const [scope, setScope] = useState<"mine" | "published">("mine");
  const [documents, setDocuments] = useState<DocumentListRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<OperationDocument | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const username = currentAuthenticatedUser();

  const refresh = useCallback(async (activeScope: "mine" | "published") => {
    setLoading(true);
    try {
      const result = await listDocuments(activeScope);
      setDocuments(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh(scope);
  }, [scope, refresh]);

  // List rows are envelope-only; the full document (digest + prose)
  // comes from the single fetch, which is the audited read surface.
  useEffect(() => {
    if (selectedId === null) {
      setSelected(null);
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    getDocument(selectedId, controller.signal)
      .then(setSelected)
      .catch((err) => {
        if (controller.signal.aborted) {
          return;
        }
        message.error(err instanceof Error ? err.message : String(err));
        setSelected(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setDetailLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedId]);

  const publish = async (document: DocumentListRow) => {
    try {
      await publishDocument(document.document_id);
      message.success("Document published.");
      await refresh(scope);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        message.warning("Already published.");
      } else {
        message.error(err instanceof Error ? err.message : String(err));
      }
      await refresh(scope);
    }
  };

  const remove = (document: DocumentListRow) => {
    Modal.confirm({
      title: "Delete this document?",
      content: `“${document.label}” will be removed for everyone.`,
      okText: "Delete",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteDocument(document.document_id);
          message.success("Document deleted.");
        } catch (err) {
          message.error(err instanceof Error ? err.message : String(err));
        }
        await refresh(scope);
      },
    });
  };

  const items = documents.map((document) => {
    const own = username !== null && document.owner_user_id === username;
    const actions = [
      <Button key="view" size="small" onClick={() => setSelectedId(document.document_id)}>
        View
      </Button>,
    ];
    if (own && document.state === "draft") {
      actions.push(
        <Button
          key="publish"
          size="small"
          icon={<SendOutlined />}
          onClick={() => void publish(document)}
        >
          Publish
        </Button>,
      );
    }
    if (own) {
      actions.push(
        <Button
          key="delete"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={() => remove(document)}
        >
          Delete
        </Button>,
      );
    }
    return (
      <div
        key={document.document_id}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 12px",
          border: "1px solid var(--border)",
          borderRadius: 8,
          marginBottom: 8,
          flexWrap: "wrap",
        }}
      >
        <FileTextOutlined />
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <Typography.Text strong>{document.label}</Typography.Text>
            <Tag>{document.document_type.replace(/_/g, " ")}</Tag>
            <Tag color={document.state === "published" ? "green" : "blue"}>
              {document.state}
            </Tag>
          </div>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {dayjs(document.created_at).fromNow()}
            {!own ? ` · created by ${document.owner_user_id}` : ""}
            {` · ${document.provenance?.sessions?.length ?? 0} session(s)`}
          </Typography.Text>
        </div>
        <div style={{ display: "flex", gap: 8 }}>{actions}</div>
      </div>
    );
  });

  return (
    <div className="view-inner">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 8,
        }}
      >
        <Typography.Title level={4} style={{ margin: 0 }}>
          Documents
        </Typography.Title>
        <Tooltip title="Create a shift summary draft">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateOpen(true)}
          >
            New shift summary
          </Button>
        </Tooltip>
      </div>
      <Typography.Paragraph type="secondary">
        Immutable shift snapshots: your drafts are private until
        published; published documents are readable by everyone with
        documents access, and cross-owner reads are audited.
      </Typography.Paragraph>
      <Tabs
        activeKey={scope}
        onChange={(key) => setScope(key as "mine" | "published")}
        items={[
          { key: "mine", label: "Mine" },
          { key: "published", label: "Published" },
        ]}
      />
      {error ? (
        <Alert type="warning" showIcon message={error} style={{ marginBottom: 8 }} />
      ) : null}
      {loading && documents.length === 0 ? (
        <div style={{ padding: 24, textAlign: "center" }}>
          <Spin />
        </div>
      ) : documents.length === 0 ? (
        <Empty
          description={
            scope === "mine"
              ? "No documents yet. Create a shift summary from your sessions."
              : "Nothing published yet."
          }
        />
      ) : (
        items
      )}
      <CreateShiftSummaryDialog
        open={createOpen}
        workspace={workspace}
        onClose={() => setCreateOpen(false)}
        onCreated={() => void refresh(scope)}
      />
      <Drawer
        title={selected ? selected.label : "Document"}
        open={selectedId !== null}
        onClose={() => setSelectedId(null)}
        width={560}
        extra={
          selected ? (
            <Tooltip title="Download this document as Markdown for offline use">
              <Button
                icon={<DownloadOutlined />}
                onClick={() => {
                  downloadDocumentMarkdown(selected);
                  message.success("Exported as Markdown.");
                }}
              >
                Export .md
              </Button>
            </Tooltip>
          ) : null
        }
      >
        {detailLoading || selected === null ? (
          <div style={{ padding: 24, textAlign: "center" }}>
            <Spin />
          </div>
        ) : (
          <div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
              <Tag>{selected.document_type.replace(/_/g, " ")}</Tag>
              <Tag color={selected.state === "published" ? "green" : "blue"}>
                {selected.state}
              </Tag>
              <Typography.Text type="secondary">
                created by {selected.owner_user_id}
              </Typography.Text>
            </div>
            {selected.state === "published" && selected.published_at ? (
              <Typography.Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
                Published {dayjs(selected.published_at).fromNow()}
              </Typography.Text>
            ) : null}
            <Typography.Title level={5}>Digest</Typography.Title>
            <DigestPanel document={selected} />
            <Typography.Title level={5} style={{ marginTop: 16 }}>
              Prose
            </Typography.Title>
            <ProsePanel document={selected} />
          </div>
        )}
      </Drawer>
    </div>
  );
}
