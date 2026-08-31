// Incident triage view (SPEC-015 R-6, SPEC-023 R-5): role-gated list with
// filters + 15s auto-refresh, manual intake form, detail with triage
// report, connector dispatches, and the chat deep-link that pins the
// incident's session into the chat workspace (SPEC-023 R-3). The gateway
// re-enforces incident:* policy on every request regardless.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Input,
  Select,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
  type TableColumnsType,
} from "antd";
import {
  ArrowLeftOutlined,
  FileTextOutlined,
  MessageOutlined,
} from "@ant-design/icons";
import { ApiError } from "../../api/client";
import {
  createIncidentSkillDraft,
  getIncident,
  listIncidents,
  reportIncident,
  runTriage,
  type ConnectorDispatch,
  type IncidentDetailPayload,
  type IncidentFilters,
  type IncidentSummary,
  type SkillDraftResponse,
  type TriageReport,
} from "../../api/incidents";
import { useAuth } from "../../auth/AuthContext";
import { renderMarkdown } from "../../chat/markdown";
import { displayToolNames } from "../../chat/toolNames";
import { useToolNameMap } from "../../chat/useToolNames";
import { SkillDraftPreviewModal } from "../../chat/SkillDraftPreview";
import {
  INCIDENT_ACT_ROLES,
  INCIDENT_SKILL_DRAFT_ROLES,
  INCIDENT_VIEW_ROLES,
  hasAnyRole,
} from "../../roles";
import { formatTimestamp } from "../format";
import type { SessionWorkspace } from "../../sessions/useSessionWorkspace";
import { parseLabelsInput } from "./labels";

const AUTO_REFRESH_MS = 15_000;

const SEVERITY_COLOR: Record<string, string> = {
  critical: "red",
  warning: "orange",
  info: "blue",
};

const STATUS_COLOR: Record<string, string> = {
  new: "default",
  triaging: "processing",
  triaged: "green",
  triage_failed: "red",
  resolved: "default",
};

const DISPATCH_COLOR: Record<string, string> = {
  pending: "processing",
  sent: "blue",
  succeeded: "green",
  failed: "red",
};

const PRIORITY_COLOR: Record<string, string> = {
  immediate: "red",
  soon: "orange",
  later: "default",
};

function SeverityBadge({ value }: { value: string }) {
  return <Tag color={SEVERITY_COLOR[value] ?? "default"}>{value}</Tag>;
}

function StatusBadge({ value }: { value: string }) {
  return <Tag color={STATUS_COLOR[value] ?? "default"}>{value}</Tag>;
}

export interface IncidentsViewProps {
  // Chat deep-link: pins incident-<id> into the session panel and opens
  // the chat view (SPEC-023 R-3 deep links).
  onOpenIncidentSession: (incident: IncidentSummary) => void;
  // The caller's own session list (server-scoped, 30s poll): an
  // incident's triage session is continuable only while it appears
  // here. Sessions expire after an idle TTL and are single-owner, so
  // a stale or foreign session id on the incident gates the deep link
  // at render time instead of surfacing a confusing 404 on click.
  workspace: SessionWorkspace;
}

export default function IncidentsView({
  onOpenIncidentSession,
  workspace,
}: IncidentsViewProps) {
  const { roles } = useAuth();
  const canView = hasAnyRole(roles, INCIDENT_VIEW_ROLES);
  const canAct = hasAnyRole(roles, INCIDENT_ACT_ROLES);
  const canDraft = hasAnyRole(roles, INCIDENT_SKILL_DRAFT_ROLES);

  const [filters, setFilters] = useState<IncidentFilters>({});
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Detail mode state.
  const [detail, setDetail] = useState<IncidentDetailPayload | null>(null);
  const [triaging, setTriaging] = useState(false);

  // Manual intake form state.
  const [formOpen, setFormOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [severity, setSeverity] = useState("warning");
  const [labelsInput, setLabelsInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadInFlightRef = useRef(false);

  const loadList = useCallback(
    async (activeFilters: IncidentFilters) => {
      if (!canView || loadInFlightRef.current) return;
      loadInFlightRef.current = true;
      setLoading(true);
      try {
        const payload = await listIncidents(activeFilters);
        setIncidents(payload.incidents ?? []);
        setTotal(payload.total ?? 0);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        loadInFlightRef.current = false;
        setLoading(false);
      }
    },
    [canView],
  );

  // Initial + filter-driven load.
  useEffect(() => {
    if (!canView) return;
    setDetail(null);
    void loadList(filters);
  }, [canView, filters, loadList]);

  // 15s auto-refresh while the list is showing (legacy parity).
  useEffect(() => {
    if (!canView || detail) return;
    const timer = window.setInterval(() => void loadList(filters), AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [canView, detail, filters, loadList]);

  const openDetail = useCallback(async (incidentId: string) => {
    setLoading(true);
    try {
      const payload = await getIncident(incidentId);
      setDetail(payload);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const backToList = () => {
    setDetail(null);
    void loadList(filters);
  };

  const triggerTriage = async (incidentId: string) => {
    setTriaging(true);
    setError(null);
    try {
      const payload = await runTriage(incidentId);
      setDetail(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setTriaging(false);
    }
  };

  const submitReport = async () => {
    setFormError(null);
    let labels: Record<string, string>;
    try {
      labels = parseLabelsInput(labelsInput);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
      return;
    }
    setSubmitting(true);
    try {
      const created = await reportIncident({
        title: title.trim(),
        summary: summary.trim(),
        severity,
        labels,
      });
      setFormOpen(false);
      setTitle("");
      setSummary("");
      setSeverity("warning");
      setLabelsInput("");
      await openDetail(created.incident_id);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  if (!canView) {
    return (
      <Alert
        type="info"
        showIcon
        title="The incidents view requires an incident-visible role."
      />
    );
  }

  if (detail) {
    // The deep link is live only while the incident's triage session
    // is one of the caller's own sessions (expired or foreign-owned
    // ids fall out of the workspace list).
    const chatAvailable =
      Boolean(detail.incident.session_id) &&
      workspace.sessions.some(
        (entry) => entry.session_id === detail.incident.session_id,
      );
    return (
      <IncidentDetail
        payload={detail}
        triaging={triaging}
        canAct={canAct}
        canDraft={canDraft}
        chatAvailable={chatAvailable}
        error={error}
        onBack={backToList}
        onTriage={() => void triggerTriage(detail.incident.incident_id)}
        onOpenChat={() => onOpenIncidentSession(detail.incident)}
      />
    );
  }

  const columns: TableColumnsType<IncidentSummary> = [
    {
      title: "opened",
      dataIndex: "created_at",
      render: (value: string) => formatTimestamp(value),
    },
    { title: "title", dataIndex: "title" },
    {
      title: "severity",
      dataIndex: "severity",
      render: (value: string) => <SeverityBadge value={value} />,
    },
    {
      title: "status",
      dataIndex: "status",
      render: (value: string) => <StatusBadge value={value} />,
    },
    { title: "source", dataIndex: "source" },
    { title: "id", dataIndex: "incident_id" },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        Incidents
      </Typography.Title>
      <div className="view-toolbar">
        <Select
          value={filters.status ?? ""}
          onChange={(value) =>
            setFilters((f) => ({ ...f, status: value || undefined }))
          }
          style={{ width: 160 }}
          aria-label="Filter by status"
          options={[
            { value: "", label: "all statuses" },
            ...["new", "triaging", "triaged", "triage_failed", "resolved"].map(
              (status) => ({ value: status, label: status }),
            ),
          ]}
        />
        <Select
          value={filters.severity ?? ""}
          onChange={(value) =>
            setFilters((f) => ({ ...f, severity: value || undefined }))
          }
          style={{ width: 160 }}
          aria-label="Filter by severity"
          options={[
            { value: "", label: "all severities" },
            ...["critical", "warning", "info"].map((sev) => ({
              value: sev,
              label: sev,
            })),
          ]}
        />
        <Select
          value={filters.source ?? ""}
          onChange={(value) =>
            setFilters((f) => ({ ...f, source: value || undefined }))
          }
          style={{ width: 160 }}
          aria-label="Filter by source"
          options={[
            { value: "", label: "all sources" },
            { value: "alertmanager", label: "alertmanager" },
            { value: "manual", label: "manual" },
          ]}
        />
        <Button onClick={() => void loadList(filters)}>Refresh</Button>
        {canAct ? (
          <Button onClick={() => setFormOpen((open) => !open)}>
            Report incident
          </Button>
        ) : null}
      </div>
      {formOpen && canAct ? (
        <div className="report-form">
          <Typography.Text strong>Report an incident</Typography.Text>
          <Input
            placeholder="Short incident title"
            maxLength={200}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            aria-label="Incident title"
          />
          <Input.TextArea
            placeholder="What is happening, where, since when?"
            rows={3}
            maxLength={2000}
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            aria-label="Incident summary"
          />
          <div className="view-toolbar">
            <Select
              value={severity}
              onChange={setSeverity}
              style={{ width: 140 }}
              aria-label="Incident severity"
              options={[
                { value: "warning", label: "warning" },
                { value: "critical", label: "critical" },
                { value: "info", label: "info" },
              ]}
            />
            <Input
              placeholder="team=payments, cluster=dev-k8s"
              value={labelsInput}
              onChange={(event) => setLabelsInput(event.target.value)}
              aria-label="Labels"
            />
          </div>
          {formError ? (
            <Alert type="error" showIcon title={formError} />
          ) : null}
          <div className="view-toolbar">
            <Button
              type="primary"
              loading={submitting}
              disabled={!title.trim()}
              onClick={() => void submitReport()}
            >
              Submit report
            </Button>
            <Button onClick={() => setFormOpen(false)}>Cancel</Button>
          </div>
        </div>
      ) : null}
      {error ? (
        <Alert type="error" showIcon title={error} style={{ marginBottom: 12 }} />
      ) : null}
      <Spin spinning={loading}>
        {incidents.length === 0 && !loading ? (
          <Typography.Text type="secondary">
            No incidents match these filters.
          </Typography.Text>
        ) : (
          <Table<IncidentSummary>
            size="small"
            rowKey="incident_id"
            columns={columns}
            dataSource={incidents}
            pagination={false}
            onRow={(incident) => ({
              onClick: () => void openDetail(incident.incident_id),
              style: { cursor: "pointer" },
            })}
          />
        )}
      </Spin>
      <Typography.Text type="secondary">
        {incidents.length} incident{incidents.length === 1 ? "" : "s"} shown ·{" "}
        {total} total
      </Typography.Text>
    </div>
  );
}

function IncidentDetail({
  payload,
  triaging,
  canAct,
  canDraft,
  chatAvailable,
  error,
  onBack,
  onTriage,
  onOpenChat,
}: {
  payload: IncidentDetailPayload;
  triaging: boolean;
  canAct: boolean;
  canDraft: boolean;
  chatAvailable: boolean;
  error: string | null;
  onBack: () => void;
  onTriage: () => void;
  onOpenChat: () => void;
}) {
  const { incident, report, dispatches } = payload;
  const labels = incident.labels ?? {};

  // SPEC-045 R-4: incident-anchored draft — generated from the
  // incident's validated triage, never from anyone's session. The
  // response opens in the shared read-only preview (SPEC-045 R-5);
  // the gateway re-enforces incident:skill_draft + incident:read.
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<SkillDraftResponse | null>(null);
  const requestDraft = async () => {
    if (drafting) return;
    setDrafting(true);
    try {
      const result = await createIncidentSkillDraft(incident.incident_id);
      setDraft(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        message.error("Your role cannot draft skills from incidents.");
      } else if (err instanceof ApiError && err.status === 404) {
        message.error("Incident not found.");
      } else if (err instanceof ApiError && err.status === 409) {
        message.error(
          "No validated triage report yet — run triage first, then " +
            "draft the skill.",
        );
      } else if (err instanceof ApiError && err.status === 503) {
        message.error("Skill validation is not configured right now.");
      } else if (err instanceof ApiError && err.status === 502) {
        message.error("Skill validation is unreachable — no draft returned.");
      } else {
        message.error(
          err instanceof Error ? err.message : "Skill draft failed.",
        );
      }
    } finally {
      setDrafting(false);
    }
  };

  const dispatchColumns: TableColumnsType<ConnectorDispatch> = [
    { title: "connector", dataIndex: "connector" },
    {
      title: "status",
      dataIndex: "status",
      render: (value: string, dispatch) => (
        <Tag
          color={DISPATCH_COLOR[value] ?? "default"}
          title={value === "failed" ? dispatch.error ?? undefined : undefined}
        >
          {value}
        </Tag>
      ),
    },
    {
      title: "reference",
      dataIndex: "reference",
      render: (value) => value || "—",
    },
    {
      title: "dispatched",
      dataIndex: "created_at",
      render: (value: string) => formatTimestamp(value),
    },
  ];

  return (
    <div>
      <Button
        size="small"
        icon={<ArrowLeftOutlined />}
        onClick={onBack}
        style={{ marginBottom: 12 }}
      >
        All incidents
      </Button>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        {incident.title}{" "}
        <SeverityBadge value={incident.severity} />
        <StatusBadge value={incident.status} />
        <Tag>{incident.source}</Tag>
      </Typography.Title>
      <div className="evidence-meta">
        <span>id: {incident.incident_id}</span>
        <span>fingerprint: {incident.fingerprint}</span>
        <span>opened: {formatTimestamp(incident.created_at)}</span>
        <span>updated: {formatTimestamp(incident.updated_at)}</span>
        {incident.reported_by ? (
          <span>reported by: {incident.reported_by}</span>
        ) : null}
        {incident.resolved_at ? (
          <span>resolved: {formatTimestamp(incident.resolved_at)}</span>
        ) : null}
      </div>
      {Object.keys(labels).length > 0 ? (
        <div style={{ marginTop: 8 }}>
          {Object.entries(labels).map(([key, value]) => (
            <Tag key={key}>
              {key}={value}
            </Tag>
          ))}
        </div>
      ) : null}
      {incident.summary ? (
        <Typography.Paragraph style={{ marginTop: 12 }}>
          {incident.summary}
        </Typography.Paragraph>
      ) : null}
      {error ? (
        <Alert type="error" showIcon title={error} style={{ marginBottom: 12 }} />
      ) : null}
      <div className="view-toolbar" style={{ marginTop: 12 }}>
        {canAct ? (
          <Button
            type="primary"
            loading={triaging}
            disabled={incident.status === "triaging"}
            onClick={onTriage}
          >
            {report ? "Re-run triage" : "Run triage"}
          </Button>
        ) : null}
        {canDraft ? (
          <Button
            icon={<FileTextOutlined />}
            loading={drafting}
            aria-label="Draft as skill"
            onClick={() => void requestDraft()}
          >
            Draft as skill
          </Button>
        ) : null}
        <Tooltip
          title={
            chatAvailable
              ? undefined
              : "This incident's triage session is not available to you (expired, not yet visible, or owned by another operator). Draft a skill from the incident instead."
          }
        >
          <Button
            icon={<MessageOutlined />}
            onClick={onOpenChat}
            disabled={!chatAvailable}
          >
            Continue in chat
          </Button>
        </Tooltip>
      </div>
      <SkillDraftPreviewModal draft={draft} onClose={() => setDraft(null)} />
      {report ? (
        <TriageReportSection report={report} />
      ) : incident.status === "triage_failed" && incident.triage_raw ? (
        // Failed triage keeps the raw agent output for inspection.
        <details style={{ marginTop: 12 }}>
          <summary>Raw triage output (validation failed)</summary>
          <pre className="evidence-pre">{incident.triage_raw}</pre>
        </details>
      ) : incident.status === "new" ? (
        <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
          No triage report yet — run triage to let the agent gather evidence.
        </Typography.Paragraph>
      ) : null}
      <Typography.Title level={5} style={{ marginTop: 20 }}>
        Connector dispatch
      </Typography.Title>
      {dispatches.length === 0 ? (
        <Typography.Text type="secondary">
          No connector dispatches yet.
        </Typography.Text>
      ) : (
        <Table<ConnectorDispatch>
          size="small"
          rowKey={(dispatch) => `${dispatch.connector}-${dispatch.created_at}`}
          columns={dispatchColumns}
          dataSource={dispatches}
          pagination={false}
        />
      )}
    </div>
  );
}

function TriageReportSection({ report }: { report: TriageReport }) {
  // v0.27.4 (broadened v0.27.5): every rendered surface shows the
  // registry's dotted canonical tool names (see chat/toolNames.ts).
  const toolNames = useToolNameMap();
  return (
    <div className="incident-section">
      <Typography.Title level={5} style={{ marginTop: 20 }}>
        Triage report
      </Typography.Title>
      <div className="view-toolbar">
        <SeverityBadge value={report.severity_assessment} />
        <Typography.Text type="secondary">
          {report.generated_by} · {formatTimestamp(report.generated_at)} ·
          session {report.session_id}
        </Typography.Text>
      </div>
      <div
        className="md-content"
        // Safe by construction: renderMarkdown escapes every source
        // character (including quotes) before introducing markup and
        // only renders http(s) links.
        dangerouslySetInnerHTML={{
          __html: renderMarkdown(displayToolNames(report.summary, toolNames)),
        }}
      />
      {(report.evidence ?? []).length > 0 ? (
        <>
          <Typography.Title level={5}>Evidence</Typography.Title>
          <ul>
            {(report.evidence ?? []).map((ref, index) => (
              <li key={index}>
                {ref.source}: {ref.description}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {(report.hypotheses ?? []).length > 0 ? (
        <>
          <Typography.Title level={5}>Hypotheses</Typography.Title>
          <ul>
            {(report.hypotheses ?? []).map((hypothesis, index) => (
              <li key={index}>{hypothesis}</li>
            ))}
          </ul>
        </>
      ) : null}
      {(report.next_steps ?? []).length > 0 ? (
        <>
          <Typography.Title level={5}>Next steps (advisory)</Typography.Title>
          <ol>
            {(report.next_steps ?? []).map((step, index) => (
              <li key={index}>
                <strong>{step.title}</strong>{" "}
                <Tag color={PRIORITY_COLOR[step.priority] ?? "default"}>
                  {step.priority}
                </Tag>
                <p>{step.rationale}</p>
              </li>
            ))}
          </ol>
        </>
      ) : null}
      {(report.skills_cited ?? []).length > 0 ? (
        <>
          <Typography.Title level={5}>Cited guidance</Typography.Title>
          <div>
            {(report.skills_cited ?? []).map((skillId) => (
              <Tag key={skillId}>{skillId}</Tag>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
