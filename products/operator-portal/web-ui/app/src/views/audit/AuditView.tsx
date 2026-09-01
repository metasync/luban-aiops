// Durable audit trail view (SPEC-013 R-5, SPEC-023 R-5, SPEC-046 R-5):
// auditor and platform-admin only. One shared filter toolbar drives both
// tabs — Events (cursor pagination + expandable verbatim envelopes) and
// Summary (deterministic envelope-column aggregates) — plus the bounded
// CSV export. The filter vocabulary is pinned to the shared audit-event
// schema by constants.ts and its drift guard. The gateway re-enforces
// audit:read on every request.
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Input,
  Select,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
  type TableColumnsType,
} from "antd";
import {
  ApiError,
  authHeaders,
  buildRequestId,
  currentGateway,
  requestJson,
} from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { AUDIT_ROLES, hasAnyRole } from "../../roles";
import { formatTimestamp } from "../format";
import AuditSummaryPanel, {
  type AuditSummary,
  type DrilldownPatch,
} from "./AuditSummaryPanel";
import { EMITTER_SERVICES, EVENT_TYPES, OUTCOMES } from "./constants";

interface AuditEvent {
  occurred_at: string;
  event_type: string;
  service: string;
  outcome: string;
  username?: string;
  actor?: string;
  subject?: string;
  request_id: string;
  [key: string]: unknown;
}

interface AuditPage {
  events: AuditEvent[];
  next_cursor?: string | null;
}

interface Filters {
  username: string;
  eventType: string;
  outcome: string;
  service: string;
  since: string;
  until: string;
}

const EMPTY_FILTERS: Filters = {
  username: "",
  eventType: "",
  outcome: "",
  service: "",
  since: "",
  until: "",
};

// Structured error surfaces (R-5): the three upstream postures get
// distinct, operator-actionable messages instead of raw status text.
function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "Access denied: the audit surface requires the audit:read policy action.";
    }
    if (error.status === 503) {
      return "The audit service is not configured on this gateway.";
    }
    if (error.status === 502) {
      return "The audit service is unavailable right now.";
    }
    return `Audit request failed: ${error.status} ${error.message}`;
  }
  return error instanceof Error ? error.message : String(error);
}

function filterParams(filters: Filters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.username.trim()) params.set("username", filters.username.trim());
  if (filters.eventType) params.set("event_type", filters.eventType);
  if (filters.outcome) params.set("outcome", filters.outcome);
  if (filters.service) params.set("service", filters.service);
  if (filters.since) params.set("since", new Date(filters.since).toISOString());
  if (filters.until) params.set("until", new Date(filters.until).toISOString());
  return params;
}

export default function AuditView() {
  const { roles } = useAuth();
  const allowed = hasAnyRole(roles, AUDIT_ROLES);

  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [activeTab, setActiveTab] = useState<"events" | "summary">("events");

  // Events tab state (the SPEC-013 table, moved intact).
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Summary tab state; fetched lazily on tab activation and on Refresh
  // while active, keyed off the applied filters.
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [summaryKey, setSummaryKey] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  // Export state.
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [truncatedRows, setTruncatedRows] = useState<string | null>(null);

  const loadEvents = useCallback(
    async (current: Filters, append: boolean) => {
      if (!allowed) return;
      setLoading(true);
      setError(null);
      try {
        const params = filterParams(current);
        params.set("limit", "50");
        if (append && cursor) params.set("cursor", cursor);
        const payload = await requestJson<AuditPage>(
          `/api/v1/audit/events?${params.toString()}`,
        );
        const page = payload.events ?? [];
        setEvents((events) => (append ? [...events, ...page] : page));
        setCursor(payload.next_cursor ?? null);
        setLoaded(true);
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [allowed, cursor],
  );

  const load = useCallback(
    async (append: boolean) => loadEvents(filters, append),
    [filters, loadEvents],
  );

  const fetchSummary = useCallback(
    async (current: Filters) => {
      if (!allowed) return;
      setSummaryLoading(true);
      setSummaryError(null);
      try {
        const params = filterParams(current);
        const data = await requestJson<AuditSummary>(
          `/api/v1/audit/summary?${params.toString()}`,
        );
        setSummary(data);
        setSummaryKey(JSON.stringify(current));
      } catch (err) {
        setSummaryError(errorMessage(err));
      } finally {
        setSummaryLoading(false);
      }
    },
    [allowed],
  );

  // Initial events load on first entry (role gate re-checked server-side).
  useEffect(() => {
    if (allowed && !loaded && !loading && !error) {
      void load(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed]);

  // SPEC-040 R-4 Blob download posture: the server-side export streams
  // into a client-side download under the server's Content-Disposition
  // filename.
  const handleExport = useCallback(async () => {
    if (!allowed) return;
    setExporting(true);
    setExportError(null);
    setTruncatedRows(null);
    try {
      const params = filterParams(filters);
      const response = await fetch(
        `${currentGateway()}/api/v1/audit/export?${params.toString()}`,
        {
          headers: { "x-request-id": buildRequestId(), ...authHeaders() },
        },
      );
      if (!response.ok) {
        throw new ApiError(response.status, response.statusText);
      }
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") ?? "";
      const filename =
        /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? "audit-export.csv";
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      window.document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      if (response.headers.get("x-audit-export-truncated") === "true") {
        setTruncatedRows(response.headers.get("x-audit-export-rows") ?? "");
      }
    } catch (err) {
      setExportError(errorMessage(err));
    } finally {
      setExporting(false);
    }
  }, [allowed, filters]);

  // SPEC-047 R-3: Summary drill-down merges the patch into the current
  // filters (merge, never reset — Q-3), lands on the Events tab, and
  // triggers one refresh under the merged filters. Hook order is
  // load-bearing (v0.29.2): every hook must run before the `!allowed`
  // early return below, because sign-out and token refresh can flip the
  // role gate while this view stays mounted.
  const handleDrilldown = useCallback(
    (patch: DrilldownPatch) => {
      if (!allowed) return;
      const merged = { ...filters, ...patch };
      setFilters(merged);
      setActiveTab("events");
      setCursor(null);
      void loadEvents(merged, false);
    },
    [allowed, filters, loadEvents],
  );

  if (!allowed) {
    return (
      <Alert
        type="info"
        showIcon
        title="The audit trail requires the auditor or platform-admin role."
      />
    );
  }

  const onTabChange = (key: string) => {
    const tab = key === "summary" ? "summary" : "events";
    setActiveTab(tab);
    // One fetch per apply: leaving a tab never invalidates it; entering
    // the Summary tab re-fetches only when the filters moved.
    if (tab === "summary" && summaryKey !== JSON.stringify(filters)) {
      void fetchSummary(filters);
    }
  };

  const refresh = () => {
    if (activeTab === "summary") {
      void fetchSummary(filters);
    } else {
      void load(false);
    }
  };

  const columns: TableColumnsType<AuditEvent> = [
    {
      title: "occurred at",
      dataIndex: "occurred_at",
      render: (value: string) => formatTimestamp(value),
    },
    { title: "type", dataIndex: "event_type" },
    { title: "service", dataIndex: "service" },
    {
      title: "outcome",
      dataIndex: "outcome",
      render: (value: string) =>
        value === "deny" || value === "error" ? (
          <Tag color="error">{value}</Tag>
        ) : (
          <span>{value}</span>
        ),
    },
    {
      title: "actor",
      render: (_value, event) =>
        event.username || event.actor || event.subject || "—",
    },
    { title: "request", dataIndex: "request_id" },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        Audit trail (durable)
      </Typography.Title>
      {/* One shared toolbar drives both tabs and the export (Q-6). */}
      <div className="view-toolbar">
        <Input
          placeholder="username"
          value={filters.username}
          onChange={(event) =>
            setFilters((f) => ({ ...f, username: event.target.value }))
          }
          style={{ width: 160 }}
          aria-label="Filter by username"
        />
        <Select
          value={filters.eventType}
          onChange={(value) => setFilters((f) => ({ ...f, eventType: value }))}
          style={{ width: 240 }}
          aria-label="Filter by event type"
          options={[
            { value: "", label: "all event types" },
            ...EVENT_TYPES.map((type) => ({ value: type, label: type })),
          ]}
        />
        <Select
          value={filters.outcome}
          onChange={(value) => setFilters((f) => ({ ...f, outcome: value }))}
          style={{ width: 160 }}
          aria-label="Filter by outcome"
          options={[
            { value: "", label: "all outcomes" },
            ...OUTCOMES.map((outcome) => ({ value: outcome, label: outcome })),
          ]}
        />
        <Select
          value={filters.service}
          onChange={(value) => setFilters((f) => ({ ...f, service: value }))}
          style={{ width: 200 }}
          aria-label="Filter by service"
          options={[
            { value: "", label: "all services" },
            ...EMITTER_SERVICES.map((service) => ({ value: service, label: service })),
          ]}
        />
        <Input
          type="datetime-local"
          value={filters.since}
          onChange={(event) =>
            setFilters((f) => ({ ...f, since: event.target.value }))
          }
          style={{ width: 200 }}
          aria-label="Since"
        />
        <Input
          type="datetime-local"
          value={filters.until}
          onChange={(event) =>
            setFilters((f) => ({ ...f, until: event.target.value }))
          }
          style={{ width: 200 }}
          aria-label="Until"
        />
        <Button onClick={refresh}>Refresh</Button>
        <Button loading={exporting} onClick={() => void handleExport()}>
          Export CSV
        </Button>
      </div>
      {exportError ? (
        <Alert
          type="error"
          showIcon
          title={exportError}
          style={{ marginBottom: 12 }}
        />
      ) : null}
      {truncatedRows ? (
        <Alert
          type="warning"
          showIcon
          title={`Export truncated at ${truncatedRows} rows (AUDIT_EXPORT_MAX_ROWS). Narrow the filters for a complete export.`}
          style={{ marginBottom: 12 }}
        />
      ) : null}
      <Tabs
        activeKey={activeTab}
        onChange={onTabChange}
        items={[
          {
            key: "events",
            label: "Events",
            children: (
              <>
                {error ? (
                  <Alert
                    type="error"
                    showIcon
                    title={error}
                    style={{ marginBottom: 12 }}
                  />
                ) : null}
                <Spin spinning={loading}>
                  {loaded && events.length === 0 ? (
                    <Typography.Text type="secondary">
                      No audit events match these filters.
                    </Typography.Text>
                  ) : (
                    <Table<AuditEvent>
                      size="small"
                      rowKey={(event) =>
                        `${event.request_id}-${event.occurred_at}-${event.event_type}`
                      }
                      columns={columns}
                      dataSource={events}
                      pagination={false}
                      expandable={{
                        // Verbatim event envelope (legacy parity: click row to toggle).
                        expandedRowRender: (event) => (
                          <pre className="evidence-pre">
                            {JSON.stringify(event, null, 2)}
                          </pre>
                        ),
                      }}
                    />
                  )}
                </Spin>
                <div className="view-toolbar" style={{ marginTop: 12 }}>
                  <Typography.Text type="secondary">
                    {events.length} event{events.length === 1 ? "" : "s"} shown ·{" "}
                    {cursor ? "more available" : "end of trail"}
                  </Typography.Text>
                  {cursor ? (
                    <Button size="small" loading={loading} onClick={() => void load(true)}>
                      Load more
                    </Button>
                  ) : null}
                </div>
              </>
            ),
          },
          {
            key: "summary",
            label: "Summary",
            children: (
              <>
                {summaryError ? (
                  <Alert
                    type="error"
                    showIcon
                    title={summaryError}
                    style={{ marginBottom: 12 }}
                  />
                ) : null}
                <Spin spinning={summaryLoading}>
                  {summary ? (
                    <AuditSummaryPanel
                      summary={summary}
                      onDrilldown={handleDrilldown}
                    />
                  ) : null}
                </Spin>
              </>
            ),
          },
        ]}
      />
    </div>
  );
}
