// Durable audit trail view (SPEC-013 R-5, SPEC-023 R-5): auditor and
// platform-admin only. Filters + cursor pagination + expandable verbatim
// envelopes. The gateway re-enforces audit:read on every query.
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Input,
  Select,
  Spin,
  Table,
  Tag,
  Typography,
  type TableColumnsType,
} from "antd";
import { requestJson } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { AUDIT_ROLES, hasAnyRole } from "../../roles";
import { formatTimestamp } from "../format";

const EVENT_TYPES = [
  "tool_invoked",
  "policy_decision",
  "token_exchange",
  "session_created",
  "chat_started",
  "chat_completed",
  "incident_triaged",
];

const SERVICES = [
  "tool-gateway",
  "platform-gateway",
  "identity-service",
  "incident-service",
];

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
  service: string;
  since: string;
  until: string;
}

const EMPTY_FILTERS: Filters = {
  username: "",
  eventType: "",
  service: "",
  since: "",
  until: "",
};

export default function AuditView() {
  const { roles } = useAuth();
  const allowed = hasAnyRole(roles, AUDIT_ROLES);

  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(
    async (append: boolean) => {
      if (!allowed) return;
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({ limit: "50" });
        if (filters.username.trim()) params.set("username", filters.username.trim());
        if (filters.eventType) params.set("event_type", filters.eventType);
        if (filters.service) params.set("service", filters.service);
        if (filters.since) params.set("since", new Date(filters.since).toISOString());
        if (filters.until) params.set("until", new Date(filters.until).toISOString());
        if (append && cursor) params.set("cursor", cursor);
        const payload = await requestJson<AuditPage>(
          `/api/v1/audit/events?${params.toString()}`,
        );
        const page = payload.events ?? [];
        setEvents((current) => (append ? [...current, ...page] : page));
        setCursor(payload.next_cursor ?? null);
        setLoaded(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [allowed, filters, cursor],
  );

  // Initial load on first entry (role gate re-checked server-side).
  useEffect(() => {
    if (allowed && !loaded && !loading && !error) {
      void load(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed]);

  if (!allowed) {
    return (
      <Alert
        type="info"
        showIcon
        title="The audit trail requires the auditor or platform-admin role."
      />
    );
  }

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
          style={{ width: 180 }}
          aria-label="Filter by event type"
          options={[
            { value: "", label: "all event types" },
            ...EVENT_TYPES.map((type) => ({ value: type, label: type })),
          ]}
        />
        <Select
          value={filters.service}
          onChange={(value) => setFilters((f) => ({ ...f, service: value }))}
          style={{ width: 180 }}
          aria-label="Filter by service"
          options={[
            { value: "", label: "all services" },
            ...SERVICES.map((service) => ({ value: service, label: service })),
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
        <Button onClick={() => void load(false)}>Refresh</Button>
      </div>
      {error ? (
        <Alert type="error" showIcon title={error} style={{ marginBottom: 12 }} />
      ) : null}
      <Spin spinning={loading}>
        {loaded && events.length === 0 ? (
          <Typography.Text type="secondary">
            No audit events match these filters.
          </Typography.Text>
        ) : (
          <Table<AuditEvent>
            size="small"
            rowKey={(event) => `${event.request_id}-${event.occurred_at}-${event.event_type}`}
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
    </div>
  );
}
