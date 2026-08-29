// Documents view (SPEC-039 R-6, moved to Workspace per SPEC-040 R-3):
// create, manage, publish, and read operations documents. The digest
// renders as the primary surface; the AI narrative panel is labeled
// unmistakably as digest-anchored (SPEC-040 R-2). Cross-owner reads
// attribute the creator prominently (R-5 audit rides the agent layer;
// the view only renders). Export (SPEC-040 R-4) serializes the
// already-fetched document client-side — no new gateway call.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  Collapse,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Modal,
  Radio,
  Select,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import type { TabsProps } from "antd";
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
  type DocumentType,
  type OperationDocument,
} from "../../api/documents";
import { listIncidents, type IncidentSummary } from "../../api/incidents";
import type { SessionWorkspace } from "../../sessions/useSessionWorkspace";

dayjs.extend(relativeTime);

const MAX_SESSION_IDS = 20;

// SPEC-041 R-1: the operator-facing digest reference lives in the
// repository guides; the drawer's Learn more link opens it directly
// because the portal does not host the docs itself.
const DIGEST_REFERENCE_URL =
  "https://github.com/metasync/luban-aiops/blob/main/docs/guides/documents-digest-reference.md";

function createFailureMessage(err: unknown, documentType: DocumentType): string {
  if (err instanceof ApiError) {
    if (err.status === 403) {
      return documentType === "incident_report"
        ? "Your role cannot create incident reports: both documents " +
            "access and incident read are required."
        : "Foreign sessions are not covered by your role: only designated " +
            "approvers may include other operators' sessions.";
    }
    // SPEC-043 creation-time posture: unknown id, not-configured, and
    // unreachable incident facts each carry their structured answer.
    if (err.status === 404 && documentType === "incident_report") {
      return "The incident was not found — check the selected incident.";
    }
    if (err.status === 503) {
      return "Incident reporting is not configured on this deployment.";
    }
    if (err.status === 502 && documentType === "incident_report") {
      return (
        "The incident facts are unreachable right now; the report was " +
        "not created. Try again shortly."
      );
    }
    if (err.status === 400) {
      return documentType === "incident_report"
        ? "The document was rejected: check the label and the incident."
        : "The document was rejected: check the label and session ids.";
    }
  }
  return err instanceof Error ? err.message : String(err);
}

// --- Digest rendering (SPEC-041 R-2) ----------------------------------------

// The digest is typed-but-open: the shift-summary builder owns its
// section shapes, so the Digest data tab degrades to labeled JSON
// lines for anything the structured tabs do not recognize.
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

// The drawer renders the digest as per-concern tabs with table-shaped
// content (SPEC-041 R-2). Shapes below mirror the shift-summary
// builder; anything unrecognized degrades to the Digest data tab.
//
// Tab content follows one layout rule set (documents-digest-reference
// "How the tabs lay out content"): repeated records sharing scalar
// fields render as tables; a single object renders as a description
// list; heterogeneous or long-text items render as bullets or chips.

type DigestMap = Record<string, unknown>;

function asMap(value: unknown): DigestMap | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as DigestMap)
    : null;
}

function asList(value: unknown): DigestMap[] {
  return Array.isArray(value) ? (value as DigestMap[]) : [];
}

function textOrDash(value: unknown): string {
  return typeof value === "string" && value.length > 0 ? value : "—";
}

function countText(value: unknown): string {
  return typeof value === "number" ? String(value) : "unavailable";
}

interface ConfirmationRow {
  key: string;
  sessionId: string;
  action: string;
  status: string;
  decision: ReactNode;
  decider: string;
  decidedAt: string;
}

// Owner sessions contribute full confirmation records; foreign sessions
// contribute the metadata-only confirmation_decisions tier. Unavailable
// sections (string sentinel) are skipped here and labeled as such on
// the Sessions tab.
function collectConfirmationRows(sessions: DigestMap[]): ConfirmationRow[] {
  const rows: ConfirmationRow[] = [];
  for (const entry of sessions) {
    const sessionId = textOrDash(entry.session_id);
    const foreign = entry.coverage === "foreign";
    const records = foreign ? entry.confirmation_decisions : entry.confirmations;
    if (!Array.isArray(records)) {
      continue;
    }
    for (const record of records as DigestMap[]) {
      const pending = record.status === "pending";
      rows.push({
        key: `${sessionId}:${textOrDash(record.confirm_id)}:${rows.length}`,
        sessionId,
        action: textOrDash(record.action),
        status: textOrDash(record.status),
        decision:
          typeof record.decision === "string" && record.decision ? (
            record.decision
          ) : pending ? (
            <Tag color="orange">pending</Tag>
          ) : (
            "—"
          ),
        decider: textOrDash(record.decider_user_id),
        decidedAt:
          typeof record.decided_at === "string" && record.decided_at
            ? dayjs(record.decided_at).fromNow()
            : "—",
      });
    }
  }
  return rows;
}

interface ExecutionRow {
  key: string;
  sessionId: string;
  tool: string;
  status: string;
  receipt: ReactNode;
  completedAt: string;
}

function collectExecutionRows(sessions: DigestMap[]): ExecutionRow[] {
  const rows: ExecutionRow[] = [];
  for (const entry of sessions) {
    const sessionId = textOrDash(entry.session_id);
    const foreign = entry.coverage === "foreign";
    const records = foreign ? entry.execution_receipts : entry.executions;
    if (!Array.isArray(records)) {
      continue;
    }
    for (const record of records as DigestMap[]) {
      rows.push({
        key: `${sessionId}:${textOrDash(record.execution_id)}:${rows.length}`,
        sessionId,
        tool: textOrDash(record.tool_name),
        status: textOrDash(record.status),
        receipt:
          record.digest_match === false ? (
            <span>
              {textOrDash(record.receipt_status)}{" "}
              <Tag color="warning">digest mismatch</Tag>
            </span>
          ) : (
            textOrDash(record.receipt_status)
          ),
        completedAt:
          typeof record.completed_at === "string" && record.completed_at
            ? dayjs(record.completed_at).fromNow()
            : "—",
      });
    }
  }
  return rows;
}

function HandoverTab({ handover }: { handover: DigestMap }) {
  const openItems = asMap(handover.open_items) ?? {};
  const openSessions = asList(handover.open_sessions).map((id) => String(id));
  return (
    <div>
      {handover.quiet ? (
        <Alert
          type="info"
          showIcon
          title="Quiet shift"
          description="No decisions or executions were recorded across this document's coverage."
          style={{ marginBottom: 12 }}
        />
      ) : null}
      <Descriptions
        size="small"
        column={2}
        items={[
          {
            key: "covered",
            label: "Covered sessions",
            children: `${countText(handover.covered_session_count)} (own ${countText(
              handover.own_session_count,
            )} · foreign ${countText(handover.foreign_session_count)})`,
          },
          {
            key: "decisions",
            label: "Decisions",
            children: countText(handover.decision_count),
          },
          {
            key: "executions",
            label: "Executions",
            children: countText(handover.execution_count),
          },
          {
            key: "pending",
            label: "Pending confirmations",
            children: countText(openItems.pending_confirmations),
          },
          {
            key: "requested",
            label: "Requested executions",
            children: countText(openItems.requested_executions),
          },
        ]}
      />
      {openSessions.length > 0 ? (
        <div style={{ marginTop: 8 }}>
          <Typography.Text type="secondary">Open sessions: </Typography.Text>
          {openSessions.map((sessionId) => (
            <Tag key={sessionId}>{sessionId}</Tag>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SessionsTab({ sessions }: { sessions: DigestMap[] }) {
  if (sessions.length === 0) {
    return (
      <Typography.Text type="secondary">
        No session entries in this digest.
      </Typography.Text>
    );
  }
  return (
    <div>
      {sessions.map((entry, index) => {
        const sessionId = textOrDash(entry.session_id);
        if (entry.coverage === "foreign") {
          // Metadata tier: never render owner-tier fields as empty.
          const counts = asMap(entry.record_counts) ?? {};
          return (
            <div
              key={`${sessionId}:${index}`}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: 12,
                marginBottom: 8,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  flexWrap: "wrap",
                  marginBottom: 4,
                }}
              >
                <Tag color="purple">foreign session — metadata only</Tag>
                <Typography.Text type="secondary" copyable={{ text: sessionId }}>
                  {sessionId}
                </Typography.Text>
              </div>
              <Typography.Text type="secondary">
                confirmations: {countText(counts.confirmations)} · executions:{" "}
                {countText(counts.executions)}
              </Typography.Text>
            </div>
          );
        }
        const unavailableSections = [
          "confirmations",
          "executions",
          "transcript",
          "evidence",
        ].filter((section) => entry[section] === "unavailable");
        return (
          <div
            key={`${sessionId}:${index}`}
            style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 12,
              marginBottom: 8,
            }}
          >
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <Typography.Text strong>{textOrDash(entry.title)}</Typography.Text>
              <Typography.Text type="secondary" copyable={{ text: sessionId }}>
                {sessionId}
              </Typography.Text>
              {unavailableSections.map((section) => (
                <Tag key={section} color="warning">
                  {section} unavailable
                </Tag>
              ))}
            </div>
            {typeof entry.created_at === "string" ? (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                created {dayjs(entry.created_at).fromNow()}
              </Typography.Text>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function EvidenceTab({ sessions }: { sessions: DigestMap[] }) {
  const ownerEntries = sessions.filter((entry) => entry.coverage !== "foreign");
  const foreignCount = sessions.length - ownerEntries.length;
  const rows = ownerEntries.map((entry, index) => {
    const transcript = asMap(entry.transcript);
    const evidence = asMap(entry.evidence);
    return {
      key: `${textOrDash(entry.session_id)}:${index}`,
      sessionId: textOrDash(entry.session_id),
      transcript: transcript
        ? transcript.available === false
          ? "not available"
          : `${countText(transcript.turn_count)} turns (${countText(
              transcript.user_turn_count,
            )} user)`
        : entry.transcript === "unavailable"
          ? "unavailable"
          : "—",
      frames: evidence
        ? `${countText(evidence.total_frame_count)} frames`
        : entry.evidence === "unavailable"
          ? "unavailable"
          : "—",
    };
  });
  return (
    <div>
      <Table
        size="small"
        rowKey="key"
        pagination={false}
        dataSource={rows}
        locale={{ emptyText: "No owner-covered sessions in this digest." }}
        columns={[
          { title: "Session", dataIndex: "sessionId" },
          { title: "Transcript", dataIndex: "transcript" },
          { title: "Evidence", dataIndex: "frames" },
        ]}
      />
      {foreignCount > 0 ? (
        <Typography.Text type="secondary" style={{ display: "block", marginTop: 8 }}>
          {foreignCount} foreign session(s) contribute metadata only — no
          transcript or evidence counts.
        </Typography.Text>
      ) : null}
    </div>
  );
}

function OpenItemsTab({ handover }: { handover: DigestMap | null }) {
  if (!handover) {
    return (
      <Typography.Text type="secondary">
        This document predates the handover skeleton, so shift-level open
        items are not available.
      </Typography.Text>
    );
  }
  const openItems = asMap(handover.open_items) ?? {};
  const openSessions = asList(handover.open_sessions).map((id) => String(id));
  const pending = openItems.pending_confirmations;
  const requested = openItems.requested_executions;
  if (
    pending === 0 &&
    requested === 0 &&
    openSessions.length === 0
  ) {
    return (
      <Typography.Text type="secondary">
        Nothing is open — every confirmation was decided and every
        execution closed during this shift.
      </Typography.Text>
    );
  }
  return (
    <div>
      <Descriptions
        size="small"
        column={2}
        items={[
          {
            key: "pending",
            label: "Pending confirmations",
            children: countText(pending),
          },
          {
            key: "requested",
            label: "Requested executions",
            children: countText(requested),
          },
        ]}
      />
      {openSessions.length > 0 ? (
        <div style={{ marginTop: 8 }}>
          <Typography.Text type="secondary">Sessions with open items: </Typography.Text>
          {openSessions.map((sessionId) => (
            <Tag key={sessionId}>{sessionId}</Tag>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// --- Incident report digest rendering (SPEC-043 R-6) ------------------------

// Incident digests carry four deterministic sections — incident,
// triage, dispatches, session — assembled verbatim from the incident
// bundle plus the linked triage session. Coverage markers
// (not_triaged / foreign_denied / missing / unavailable) render as
// Alert notes; anything unrecognized degrades to the Digest data tab.

const INCIDENT_SEVERITY_COLOR: Record<string, string> = {
  critical: "red",
  warning: "orange",
  info: "blue",
};

const INCIDENT_STATUS_COLOR: Record<string, string> = {
  new: "default",
  triaging: "processing",
  triaged: "green",
  triage_failed: "red",
  resolved: "default",
};

function IncidentTab({ incident }: { incident: DigestMap }) {
  const labels = asMap(incident.labels) ?? {};
  const labelEntries = Object.entries(labels);
  return (
    <div>
      <Descriptions
        size="small"
        column={1}
        items={[
          {
            key: "id",
            label: "Incident id",
            children: (
              <Typography.Text copyable={{ text: textOrDash(incident.incident_id) }}>
                {textOrDash(incident.incident_id)}
              </Typography.Text>
            ),
          },
          {
            key: "severity",
            label: "Severity",
            children: (
              <Tag
                color={
                  INCIDENT_SEVERITY_COLOR[textOrDash(incident.severity)] ?? "default"
                }
              >
                {textOrDash(incident.severity)}
              </Tag>
            ),
          },
          {
            key: "status",
            label: "Status",
            children: (
              <Tag
                color={
                  INCIDENT_STATUS_COLOR[textOrDash(incident.status)] ?? "default"
                }
              >
                {textOrDash(incident.status)}
              </Tag>
            ),
          },
          { key: "source", label: "Source", children: textOrDash(incident.source) },
          { key: "title", label: "Title", children: textOrDash(incident.title) },
          { key: "summary", label: "Summary", children: textOrDash(incident.summary) },
          {
            key: "reported",
            label: "Reported by",
            children: textOrDash(incident.reported_by),
          },
          { key: "created", label: "Created", children: textOrDash(incident.created_at) },
          {
            key: "resolved",
            label: "Resolved",
            children: textOrDash(incident.resolved_at),
          },
        ]}
      />
      {labelEntries.length > 0 ? (
        <div style={{ marginTop: 8 }}>
          <Typography.Text type="secondary">Labels: </Typography.Text>
          {labelEntries.map(([key, value]) => (
            <Tag key={key}>{`${key}=${value}`}</Tag>
          ))}
        </div>
      ) : null}
      {incident.has_triage_raw ? (
        <Typography.Text type="secondary" style={{ display: "block", marginTop: 8 }}>
          Raw triage text was present at creation; it never rides the
          digest (only this presence marker).
        </Typography.Text>
      ) : null}
    </div>
  );
}

function TriageTab({ triage }: { triage: DigestMap }) {
  if (triage.status === "not_triaged") {
    return (
      <Alert
        type="info"
        showIcon
        title="Not triaged"
        description="This incident has no triage report — triage was never run, so the incident facts above stand alone."
      />
    );
  }
  // Repeated records with shared fields ride tables; free-text lists
  // stay bullets; identifiers render as chips (house layout rule).
  const evidenceRows = asList(triage.evidence).map((row, index) => ({
    key: String(index),
    source: textOrDash(row.source),
    description: textOrDash(row.description),
  }));
  const stepRows = asList(triage.next_steps).map((row, index) => ({
    key: String(index),
    title: textOrDash(row.title),
    rationale: textOrDash(row.rationale),
    priority: textOrDash(row.priority),
  }));
  const hypotheses = asList(triage.hypotheses).map((entry) => String(entry));
  const skillsCited = asList(triage.skills_cited).map((entry) => String(entry));
  return (
    <div>
      <Descriptions
        size="small"
        column={1}
        items={[
          {
            key: "severity",
            label: "Severity assessment",
            children: textOrDash(triage.severity_assessment),
          },
          { key: "summary", label: "Summary", children: textOrDash(triage.summary) },
          {
            key: "generated-by",
            label: "Generated by",
            children: textOrDash(triage.generated_by),
          },
          {
            key: "generated-at",
            label: "Generated",
            children: textOrDash(triage.generated_at),
          },
        ]}
      />
      {evidenceRows.length > 0 ? (
        <div style={{ marginTop: 8 }}>
          <Typography.Text strong>Evidence</Typography.Text>
          <Table
            size="small"
            rowKey="key"
            pagination={false}
            dataSource={evidenceRows}
            columns={[
              { title: "Source", dataIndex: "source" },
              { title: "Finding", dataIndex: "description" },
            ]}
          />
        </div>
      ) : null}
      {hypotheses.length > 0 ? (
        <div style={{ marginTop: 8 }}>
          <Typography.Text strong>Hypotheses</Typography.Text>
          <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
            {hypotheses.map((entry, index) => (
              <li key={index}>
                <Typography.Text>{entry}</Typography.Text>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {stepRows.length > 0 ? (
        <div style={{ marginTop: 8 }}>
          <Typography.Text strong>Next steps</Typography.Text>
          <Table
            size="small"
            rowKey="key"
            pagination={false}
            dataSource={stepRows}
            columns={[
              { title: "Action", dataIndex: "title" },
              { title: "Rationale", dataIndex: "rationale" },
              { title: "Priority", dataIndex: "priority" },
            ]}
          />
        </div>
      ) : null}
      {skillsCited.length > 0 ? (
        <div style={{ marginTop: 8 }}>
          <Typography.Text type="secondary">Skills cited: </Typography.Text>
          {skillsCited.map((skillId) => (
            <Tag key={skillId}>{skillId}</Tag>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function DispatchesTab({ dispatches }: { dispatches: DigestMap[] }) {
  if (dispatches.length === 0) {
    return (
      <Typography.Text type="secondary">
        No connector dispatches were recorded for this incident.
      </Typography.Text>
    );
  }
  const rows = dispatches.map((row, index) => ({
    key: `${textOrDash(row.connector)}:${index}`,
    connector: textOrDash(row.connector),
    status: textOrDash(row.status),
    reference: textOrDash(row.reference),
    error: textOrDash(row.error),
    createdAt:
      typeof row.created_at === "string" && row.created_at
        ? dayjs(row.created_at).fromNow()
        : "—",
  }));
  return (
    <Table
      size="small"
      rowKey="key"
      pagination={false}
      dataSource={rows}
      columns={[
        { title: "Connector", dataIndex: "connector" },
        { title: "Status", dataIndex: "status" },
        { title: "Reference", dataIndex: "reference" },
        { title: "Error", dataIndex: "error" },
        { title: "Created", dataIndex: "createdAt" },
      ]}
    />
  );
}

function IncidentSessionTab({ session }: { session: DigestMap }) {
  const status = typeof session.status === "string" ? session.status : "";
  if (status === "missing") {
    return (
      <Alert
        type="info"
        showIcon
        title="No linked session"
        description="This incident was not triaged through a platform session; the incident, triage, and dispatch facts above stand alone."
      />
    );
  }
  if (status === "foreign_denied") {
    return (
      <Alert
        type="warning"
        showIcon
        title="Session not covered by your role"
        description="The linked triage session belongs to another operator and foreign coverage is not granted to your role. The incident facts above remain complete."
      />
    );
  }
  if (status === "unavailable") {
    return (
      <Alert
        type="warning"
        showIcon
        title="Session unavailable"
        description="The linked triage session could not be covered at creation (retired or unreadable). The incident facts above remain complete."
      />
    );
  }
  // Covered tiers reuse the shift-summary session renderers: the entry
  // shape underneath is identical (owner full / foreign metadata).
  const entries = [session];
  return (
    <div>
      {status === "foreign" ? (
        <Alert
          type="info"
          showIcon
          title="Foreign session — metadata only"
          description="The linked triage session belongs to another operator; only the approver metadata tier is covered."
          style={{ marginBottom: 12 }}
        />
      ) : null}
      <SessionsTab sessions={entries} />
      {status === "owner" ? (
        <div style={{ marginTop: 12 }}>
          <Typography.Text strong>Confirmations</Typography.Text>
          <Table<ConfirmationRow>
            size="small"
            rowKey="key"
            pagination={false}
            dataSource={collectConfirmationRows(entries)}
            locale={{ emptyText: "No confirmation decisions recorded." }}
            columns={[
              { title: "Action", dataIndex: "action" },
              { title: "Status", dataIndex: "status" },
              { title: "Decision", dataIndex: "decision" },
              { title: "Decider", dataIndex: "decider" },
              { title: "Decided", dataIndex: "decidedAt" },
            ]}
          />
          <Typography.Text strong style={{ display: "block", marginTop: 8 }}>
            Executions
          </Typography.Text>
          <Table<ExecutionRow>
            size="small"
            rowKey="key"
            pagination={false}
            dataSource={collectExecutionRows(entries)}
            locale={{ emptyText: "No executions recorded." }}
            columns={[
              { title: "Tool", dataIndex: "tool" },
              { title: "Status", dataIndex: "status" },
              { title: "Receipt", dataIndex: "receipt" },
              { title: "Completed", dataIndex: "completedAt" },
            ]}
          />
        </div>
      ) : null}
    </div>
  );
}

function IncidentDigestPanel({ document }: { document: OperationDocument }) {
  const digest = (document.digest ?? {}) as DigestMap;
  const incident = asMap(digest.incident) ?? {};
  const triage = asMap(digest.triage) ?? {};
  const dispatches = asList(digest.dispatches);
  const session = asMap(digest.session) ?? {};
  const items = [
    {
      key: "incident",
      label: "Incident",
      children: <IncidentTab incident={incident} />,
    },
    {
      key: "triage",
      label: "Triage",
      children: <TriageTab triage={triage} />,
    },
    {
      key: "dispatches",
      label: "Dispatches",
      children: <DispatchesTab dispatches={dispatches} />,
    },
    {
      key: "session",
      label: "Session",
      children: <IncidentSessionTab session={session} />,
    },
    {
      key: "raw",
      label: "Digest data",
      children: (
        <div>
          <Typography.Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
            The complete stored digest, field by field — the artifact of
            record.
          </Typography.Text>
          <DigestValue value={digest} />
        </div>
      ),
    },
  ];
  return (
    <div>
      <div style={{ display: "flex", gap: 16, marginBottom: 4, flexWrap: "wrap" }}>
        <Typography.Text type="secondary">
          Generated {dayjs(String(digest.generated_at ?? document.created_at)).fromNow()}
        </Typography.Text>
        <Typography.Text type="secondary">
          Requested by {String(digest.requester_user_id ?? document.owner_user_id)}
        </Typography.Text>
      </div>
      <BoundedDigestTabs defaultActiveKey="incident" items={items} />
    </div>
  );
}

function DigestPanel({ document }: { document: OperationDocument }) {
  if (document.document_type === "incident_report") {
    return <IncidentDigestPanel document={document} />;
  }
  const digest = (document.digest ?? {}) as DigestMap;
  const sessions = asList(digest.sessions);
  const handover = asMap(digest.handover);
  const items = [];
  if (handover) {
    // SPEC-040 R-1: the shift story leads the digest so the relieving
    // operator sees what happened before the receipts.
    items.push({
      key: "handover",
      label: "Handover",
      children: <HandoverTab handover={handover} />,
    });
  }
  items.push({
    key: "sessions",
    label: "Sessions",
    children: <SessionsTab sessions={sessions} />,
  });
  items.push({
    key: "confirmations",
    label: "Confirmations",
    children: (
      <Table<ConfirmationRow>
        size="small"
        rowKey="key"
        pagination={false}
        dataSource={collectConfirmationRows(sessions)}
        locale={{ emptyText: "No confirmation decisions recorded." }}
        columns={[
          { title: "Session", dataIndex: "sessionId" },
          { title: "Action", dataIndex: "action" },
          { title: "Status", dataIndex: "status" },
          { title: "Decision", dataIndex: "decision" },
          { title: "Decider", dataIndex: "decider" },
          { title: "Decided", dataIndex: "decidedAt" },
        ]}
      />
    ),
  });
  items.push({
    key: "executions",
    label: "Executions",
    children: (
      <Table<ExecutionRow>
        size="small"
        rowKey="key"
        pagination={false}
        dataSource={collectExecutionRows(sessions)}
        locale={{ emptyText: "No executions recorded." }}
        columns={[
          { title: "Session", dataIndex: "sessionId" },
          { title: "Tool", dataIndex: "tool" },
          { title: "Status", dataIndex: "status" },
          { title: "Receipt", dataIndex: "receipt" },
          { title: "Completed", dataIndex: "completedAt" },
        ]}
      />
    ),
  });
  items.push({
    key: "evidence",
    label: "Evidence & transcript",
    children: <EvidenceTab sessions={sessions} />,
  });
  items.push({
    key: "open-items",
    label: "Open items",
    children: <OpenItemsTab handover={handover} />,
  });
  items.push({
    key: "raw",
    label: "Digest data",
    children: (
      <div>
        <Typography.Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
          The complete stored digest, field by field — the artifact of
          record.
        </Typography.Text>
        <DigestValue value={digest} />
      </div>
    ),
  });
  return (
    <div>
      <div style={{ display: "flex", gap: 16, marginBottom: 4, flexWrap: "wrap" }}>
        <Typography.Text type="secondary">
          Generated {dayjs(String(digest.generated_at ?? document.created_at)).fromNow()}
        </Typography.Text>
        <Typography.Text type="secondary">
          Requested by {String(digest.requester_user_id ?? document.owner_user_id)}
        </Typography.Text>
      </div>
      <BoundedDigestTabs
        defaultActiveKey={handover ? "handover" : "sessions"}
        items={items}
      />
    </div>
  );
}

function ProsePanel({ document }: { document: OperationDocument }) {
  // The collapse header stays pinned; only the narrative body scrolls
  // inside the bound (global.css `.prose-bounded` rule).
  const [measureTick, setMeasureTick] = useState(0);
  const { wrapperRef, expanded, setExpanded, overflows } = useBoundedRegion(
    ".ant-collapse-body",
    measureTick,
  );
  if (document.prose_status === "included" && document.prose) {
    return (
      <div ref={wrapperRef} className={expanded ? undefined : "prose-bounded"}>
        <Collapse
          size="small"
          // The narrative is the relieving operator's entry point: it opens
          // expanded by default and stays collapsible to the header alone.
          defaultActiveKey={["prose"]}
          onChange={() => setMeasureTick((tick) => tick + 1)}
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
        {overflows || expanded ? (
          <ExpandAffordance expanded={expanded} onChange={setExpanded} />
        ) : null}
      </div>
    );
  }
  if (document.prose_status === "failed") {
    return (
      <Alert
        type="warning"
        showIcon
        title="Narrative generation failed"
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

// --- Bounded panes (SPEC-041 R-3) -------------------------------------------

// Digest and prose are the longest blocks in the drawer; each renders
// bounded with internal scrolling and an expand affordance so nothing
// is ever trapped. The bound applies to the content region only —
// the tab content for digests, the collapse body for the narrative —
// so the tab bar and the collapse header stay pinned while content
// scrolls underneath them (v0.25.1 live-check polish). Bounding is
// presentation only — content, export, and the stored document are
// untouched.

const BOUNDED_PANE_MAX_HEIGHT = 320;

// antd's tab/collapse enter motion commits before the pane is laid
// out, so a measurement taken at the moment of the switch can read
// the pre-motion height; a short re-measure after the motion settles
// keeps `overflows` honest on first reveal.
const BOUNDED_MEASURE_DELAY_MS = 300;

// Measures the bounded region inside `wrapperRef` (found via `selector`)
// and reports whether it overflows the bound; `measureTick` re-runs the
// measurement after the user switches tabs or toggles the panel.
function useBoundedRegion(selector: string, measureTick: number) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);
  useEffect(() => {
    const measure = () => {
      const region =
        wrapperRef.current?.querySelector<HTMLElement>(selector) ?? null;
      setOverflows(
        region !== null && region.scrollHeight > BOUNDED_PANE_MAX_HEIGHT + 1,
      );
      return region !== null;
    };
    measure();
    const timer = window.setTimeout(measure, BOUNDED_MEASURE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [selector, measureTick, expanded]);
  return { wrapperRef, expanded, setExpanded, overflows };
}

function ExpandAffordance({
  expanded,
  onChange,
}: {
  expanded: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <Button
      type="link"
      size="small"
      style={{ padding: 0, height: "auto" }}
      onClick={() => onChange(!expanded)}
    >
      {expanded ? "Collapse to bounded height" : "Expand to full height"}
    </Button>
  );
}

// The digest's tab bar stays pinned; only the active tab's content
// scrolls inside the bound (global.css `.digest-bounded` rule).
function BoundedDigestTabs({
  defaultActiveKey,
  items,
}: {
  defaultActiveKey: string;
  items: NonNullable<TabsProps["items"]>;
}) {
  const [measureTick, setMeasureTick] = useState(0);
  const { wrapperRef, expanded, setExpanded, overflows } = useBoundedRegion(
    ".ant-tabs-body-holder",
    measureTick,
  );
  return (
    <div ref={wrapperRef} className={expanded ? undefined : "digest-bounded"}>
      <Tabs
        size="small"
        defaultActiveKey={defaultActiveKey}
        items={items}
        onChange={() => setMeasureTick((tick) => tick + 1)}
      />
      {overflows || expanded ? (
        <ExpandAffordance expanded={expanded} onChange={setExpanded} />
      ) : null}
    </div>
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

function CreateDocumentDialog({
  open,
  workspace,
  onClose,
  onCreated,
}: CreateDialogProps) {
  // SPEC-043 R-6: the type radio leads the dialog; shift summary stays
  // the default so the existing muscle memory holds.
  const [docType, setDocType] = useState<DocumentType>("shift_summary");
  const [label, setLabel] = useState("");
  const [ownIds, setOwnIds] = useState<string[]>([]);
  const [foreignRaw, setForeignRaw] = useState("");
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [incidentsLoading, setIncidentsLoading] = useState(false);
  const [incidentsError, setIncidentsError] = useState<string | null>(null);
  // Narrative is the default since SPEC-040 R-2; the switch is the opt-out.
  const [includeProse, setIncludeProse] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The incident picker reuses the incidents list surface — the same
  // gateway route the Incidents view reads (incident:read already
  // held by the creating roles).
  useEffect(() => {
    if (!open || docType !== "incident_report") {
      return;
    }
    const controller = new AbortController();
    setIncidentsLoading(true);
    setIncidentsError(null);
    listIncidents({}, controller.signal)
      .then((result) => setIncidents(result.incidents ?? []))
      .catch((err) => {
        if (!controller.signal.aborted) {
          setIncidentsError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIncidentsLoading(false);
        }
      });
    return () => controller.abort();
  }, [open, docType]);

  const reset = () => {
    setLabel("");
    setOwnIds([]);
    setForeignRaw("");
    setIncidentId(null);
    setIncludeProse(true);
  };

  const submit = async () => {
    const trimmedLabel = label.trim();
    if (!trimmedLabel) {
      setError("A label is required.");
      return;
    }
    let payload: Parameters<typeof createDocument>[0];
    if (docType === "incident_report") {
      if (!incidentId) {
        setError("Select an incident.");
        return;
      }
      payload = {
        document_type: "incident_report",
        incident_id: incidentId,
        label: trimmedLabel,
        include_prose: includeProse,
      };
    } else {
      const foreignIds = parseForeignIds(foreignRaw);
      const sessionIds = [...new Set([...ownIds, ...foreignIds])];
      if (sessionIds.length === 0) {
        setError("Select at least one session.");
        return;
      }
      if (sessionIds.length > MAX_SESSION_IDS) {
        setError(`A shift summary covers at most ${MAX_SESSION_IDS} sessions.`);
        return;
      }
      payload = {
        document_type: "shift_summary",
        session_ids: sessionIds,
        label: trimmedLabel,
        include_prose: includeProse,
      };
    }
    setBusy(true);
    setError(null);
    try {
      await createDocument(payload);
      message.success(
        docType === "incident_report"
          ? "Incident report draft created."
          : "Shift summary draft created.",
      );
      reset();
      onCreated();
      onClose();
    } catch (err) {
      setError(createFailureMessage(err, docType));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="New operations document"
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
          title={error}
          style={{ marginBottom: 12 }}
        />
      ) : null}
      <Radio.Group
        value={docType}
        onChange={(event) => {
          setDocType(event.target.value);
          setError(null);
        }}
        style={{ marginBottom: 12 }}
        options={[
          { value: "shift_summary", label: "Shift summary" },
          { value: "incident_report", label: "Incident report" },
        ]}
      />
      {docType === "incident_report" ? (
        <Typography.Paragraph type="secondary">
          Captures an immutable digest of one incident — the envelope,
          the triage report, connector dispatches, and the incident's
          linked triage session (coverage is server-derived).
        </Typography.Paragraph>
      ) : (
        <Typography.Paragraph type="secondary">
          Captures an immutable digest of up to {MAX_SESSION_IDS} sessions:
          your own sessions in full, foreign sessions at the approver
          metadata level only (denied otherwise).
        </Typography.Paragraph>
      )}
      <div style={{ marginBottom: 12 }}>
        <Typography.Text strong>Label</Typography.Text>
        <Input
          value={label}
          maxLength={120}
          placeholder={
            docType === "incident_report"
              ? "e.g. inc-abc123 post-mortem pack"
              : "e.g. Night shift 2026-08-26"
          }
          onChange={(event) => setLabel(event.target.value)}
        />
      </div>
      {docType === "incident_report" ? (
        <div style={{ marginBottom: 12 }}>
          <Typography.Text strong>Incident</Typography.Text>
          <Select
            showSearch
            style={{ width: "100%" }}
            loading={incidentsLoading}
            placeholder="Pick the covered incident"
            value={incidentId}
            onChange={(value) => setIncidentId(value)}
            options={incidents.map((incident) => ({
              value: incident.incident_id,
              label: `${incident.title} — ${incident.incident_id} (${incident.severity}, ${incident.status})`,
            }))}
            optionFilterProp="label"
          />
          {incidentsError ? (
            <Typography.Text type="danger" style={{ fontSize: 12 }}>
              Loading incidents failed: {incidentsError}
            </Typography.Text>
          ) : (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Creating an incident report requires both documents access
              and incident read.
            </Typography.Text>
          )}
        </div>
      ) : (
        <>
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
        </>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Switch checked={includeProse} onChange={setIncludeProse} />
        <Typography.Text>
          Include AI narrative (anchored to the digest facts, labeled)
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
  if (document.blurb) {
    // v0.23.3: the AI one-liner leads the export too.
    lines.push(`> ${document.blurb}`);
    lines.push("");
  }
  lines.push("## Provenance");
  lines.push("");
  if (document.provenance?.incident_id) {
    // SPEC-043: the covered incident anchors incident reports.
    lines.push(`- Incident \`${document.provenance.incident_id}\``);
  }
  for (const session of document.provenance?.sessions ?? []) {
    lines.push(
      `- \`${session.session_id}\` — ${session.coverage} coverage`,
    );
  }
  if (
    (document.provenance?.sessions ?? []).length === 0 &&
    !document.provenance?.incident_id
  ) {
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
          {document.blurb ?? document.summary ? (
            // v0.23.3: the AI one-liner (extracted from the narrative's
            // SUMMARY marker) gives the list the shift's story at a
            // glance; documents without it degrade to the SPEC-041
            // counts-only summary, then to label-only rows.
            <Typography.Text
              type="secondary"
              style={{ display: "block", fontSize: 12 }}
            >
              {document.blurb ?? document.summary}
            </Typography.Text>
          ) : null}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {dayjs(document.created_at).fromNow()}
            {!own ? ` · created by ${document.owner_user_id}` : ""}
            {document.document_type === "incident_report"
              ? ` · incident ${document.provenance?.incident_id ?? "—"}`
              : ` · ${document.provenance?.sessions?.length ?? 0} session(s)`}
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
        <Tooltip title="Create a shift summary or incident report draft">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateOpen(true)}
          >
            New document
          </Button>
        </Tooltip>
      </div>
      <Typography.Paragraph type="secondary">
        Immutable snapshots — shift summaries of covered sessions and
        incident reports of single incidents: your drafts are private
        until published; published documents are readable by everyone
        with documents access, and cross-owner reads are audited.
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
        <Alert type="warning" showIcon title={error} style={{ marginBottom: 8 }} />
      ) : null}
      {loading && documents.length === 0 ? (
        <div style={{ padding: 24, textAlign: "center" }}>
          <Spin />
        </div>
      ) : documents.length === 0 ? (
        <Empty
          description={
            scope === "mine"
              ? "No documents yet. Summarize your sessions or capture an incident report."
              : "Nothing published yet."
          }
        />
      ) : (
        items
      )}
      <CreateDocumentDialog
        open={createOpen}
        workspace={workspace}
        onClose={() => setCreateOpen(false)}
        onCreated={() => void refresh(scope)}
      />
      <Drawer
        title={selected ? selected.label : "Document"}
        open={selectedId !== null}
        onClose={() => setSelectedId(null)}
        size={560}
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
            {selected.blurb ?? selected.summary ? (
              // v0.23.3: the one-line story rides the detail card too —
              // the AI blurb when the narrative carried one, else the
              // deterministic counts-only summary.
              <Typography.Paragraph
                type="secondary"
                italic
                style={{ marginBottom: 12 }}
              >
                {selected.blurb ?? selected.summary}
              </Typography.Paragraph>
            ) : null}
            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <Typography.Title level={5} style={{ margin: 0 }}>
                Digest
              </Typography.Title>
              <Tooltip title="What digests, frames, and coverage tiers mean">
                <Typography.Link href={DIGEST_REFERENCE_URL} target="_blank">
                  Learn more
                </Typography.Link>
              </Tooltip>
            </div>
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
