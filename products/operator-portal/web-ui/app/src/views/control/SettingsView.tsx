// Settings view (SPEC-030 R-6): a read-only Session & Identity panel
// replacing the SPEC-023 placeholder. Built as an extensible container —
// each pane is a self-contained component registered in SETTINGS_PANES,
// so future settings functions (display preferences, per-user default
// model, notification defaults) ship as new panes without restructuring
// the view. No mutable controls in this slice: everything renders from
// existing client-side state.
import {
  Alert,
  Button,
  Descriptions,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { LoginOutlined, UserOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  currentGateway,
  lastApiRequestId,
  requestJson,
} from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import type { SessionWorkspace } from "../../sessions/useSessionWorkspace";
import { PLATFORM_VERSION, REACT_VERSION, ANTD_VERSION } from "../../version";

// --- Identity pane --------------------------------------------------------

function IdentityPane() {
  const { session, username, roles, login } = useAuth();

  if (!username) {
    // Signed-out degrades to a prompt, never stale identity data.
    return (
      <Alert
        type="info"
        showIcon
        icon={<UserOutlined />}
        title="You are signed out"
        description="Sign in to see the identity claims carried by your auth session."
        action={
          <Button
            type="primary"
            icon={<LoginOutlined />}
            onClick={() => void login()}
          >
            Sign in
          </Button>
        }
      />
    );
  }

  const identity = session?.identity;
  return (
    <Descriptions column={1} size="small" bordered>
      <Descriptions.Item label="Sign-in state">
        <Tag color="success">signed in</Tag>
      </Descriptions.Item>
      <Descriptions.Item label="Username">{username}</Descriptions.Item>
      <Descriptions.Item label="Roles">
        {roles.length > 0
          ? roles.map((role) => <Tag key={role}>{role}</Tag>)
          : "none reported"}
      </Descriptions.Item>
      {identity?.subject ? (
        <Descriptions.Item label="Subject">{identity.subject}</Descriptions.Item>
      ) : null}
      {identity?.groups && identity.groups.length > 0 ? (
        <Descriptions.Item label="Groups">
          {identity.groups.map((group) => (
            <Tag key={group}>{group}</Tag>
          ))}
        </Descriptions.Item>
      ) : null}
    </Descriptions>
  );
}

// --- Session pane ---------------------------------------------------------

function SessionPane({ workspace }: { workspace: SessionWorkspace }) {
  const { activeSessionId, sessions } = workspace;
  const active = sessions.find((s) => s.session_id === activeSessionId);
  return (
    <Descriptions column={1} size="small" bordered>
      <Descriptions.Item label="Selected session">
        {activeSessionId ?? (
          <Typography.Text type="secondary">no session selected</Typography.Text>
        )}
      </Descriptions.Item>
      {activeSessionId ? (
        <Descriptions.Item label="Session title">
          {active?.title ?? "—"}
        </Descriptions.Item>
      ) : null}
      <Descriptions.Item label="Workspace sessions">
        {sessions.length}
      </Descriptions.Item>
    </Descriptions>
  );
}

// --- Platform pane --------------------------------------------------------

// v0.23.3 live component inventory, reworked in v0.23.4: every component
// follows the platform version (shown above), so the table instead names
// the tech stack underneath each component — framework and server
// versions. /health/ready and /api/v1/runtime are unauthenticated by
// design (health probes and runtime metadata only), so the pane can read
// them directly; every row degrades to "unavailable" when a probe fails
// rather than showing stale or guessed values. Status uses one
// vocabulary — ready / degraded / not ready / unavailable — because the
// interesting cases are exactly the ones that leave this page loadable
// (the portal is a static bundle) while breaking the actual work.

interface AgentServiceHealth {
  status?: string;
  runtime_mode?: string;
  session_store?: string | null;
  session_store_ready?: boolean | null;
  agent_state?: string | null;
  agent_state_ready?: boolean | null;
  python_version?: string | null;
  fastapi_version?: string | null;
  agentscope_version?: string | null;
  session_store_version?: string | null;
  agent_state_version?: string | null;
}

interface GatewayReadyStatus {
  status?: string;
  version?: string;
  agent_service?: AgentServiceHealth;
  policy_rules?: number;
  python_version?: string;
  fastapi_version?: string;
}

interface RuntimeMetadata {
  runtime_mode?: string;
  runtime_state?: string;
  provider?: string;
  model_name?: string | null;
}

interface ComponentRow {
  key: string;
  component: string;
  technology: string;
  version: string;
  status: ReactNode;
}

const TAG_FLAT = { margin: 0 };

// One status vocabulary across every row.
function statusTag(kind: "ready" | "degraded" | "not ready"): ReactNode {
  if (kind === "ready") {
    return <Tag color="success" style={TAG_FLAT}>ready</Tag>;
  }
  if (kind === "degraded") {
    return <Tag color="warning" style={TAG_FLAT}>degraded</Tag>;
  }
  return <Tag color="error" style={TAG_FLAT}>not ready</Tag>;
}

function readyStatus(ready: boolean | null | undefined): ReactNode {
  if (ready === true) return statusTag("ready");
  if (ready === false) return statusTag("not ready");
  return <Typography.Text type="secondary">unknown</Typography.Text>;
}

function unavailable(): ReactNode {
  return <Typography.Text type="secondary">unavailable</Typography.Text>;
}

function checking(): ReactNode {
  return <Typography.Text type="secondary">checking…</Typography.Text>;
}

function backendLabel(backend: string | null | undefined): string {
  if (backend === "postgres") return "PostgreSQL";
  if (backend === "redis") return "Redis";
  if (backend === "memory") return "In-memory";
  return backend || "—";
}

function labeled(value: string | null | undefined): string {
  return value ? value : "—";
}

function PlatformPane() {
  const [ready, setReady] = useState<GatewayReadyStatus | null>(null);
  const [readyFailed, setReadyFailed] = useState(false);
  const [runtime, setRuntime] = useState<RuntimeMetadata | null>(null);
  const [runtimeFailed, setRuntimeFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    requestJson<GatewayReadyStatus>("/health/ready")
      .then((data) => {
        if (!cancelled) setReady(data);
      })
      .catch(() => {
        if (!cancelled) setReadyFailed(true);
      });
    requestJson<RuntimeMetadata>("/api/v1/runtime")
      .then((data) => {
        if (!cancelled) setRuntime(data);
      })
      .catch(() => {
        if (!cancelled) setRuntimeFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = useMemo<ComponentRow[]>(() => {
    const agent = ready?.agent_service;
    const gatewayStatus = ready?.status;
    const runtimeState = runtime?.runtime_state;
    const provider = runtime?.provider?.trim();
    return [
      {
        key: "portal",
        component: "Operator portal",
        technology: "React · Ant Design",
        version: `React ${REACT_VERSION} · Ant Design ${ANTD_VERSION}`,
        status: statusTag("ready"),
      },
      {
        key: "gateway",
        component: "Platform gateway",
        technology: "FastAPI · Python",
        version:
          ready === null || readyFailed
            ? "—"
            : `FastAPI ${labeled(ready.fastapi_version)} · Python ${labeled(ready.python_version)}`,
        status:
          readyFailed || gatewayStatus === undefined
            ? readyFailed
              ? unavailable()
              : checking()
            : statusTag(gatewayStatus === "ok" ? "ready" : "degraded"),
      },
      {
        key: "agent-service",
        component: "Agent service",
        technology: "AgentScope · FastAPI",
        version:
          readyFailed || agent === undefined
            ? "—"
            : `AgentScope ${labeled(agent.agentscope_version)} · FastAPI ${labeled(agent.fastapi_version)}`,
        status:
          readyFailed || agent === undefined
            ? readyFailed
              ? unavailable()
              : checking()
            : statusTag(agent.status === "ready" ? "ready" : "not ready"),
      },
      {
        key: "agent-runtime",
        component: "Agent runtime (LLM)",
        technology: provider
          ? `${provider.charAt(0).toUpperCase()}${provider.slice(1)} API`
          : "—",
        version: runtime?.model_name ?? "—",
        status:
          runtimeFailed || runtimeState === undefined
            ? runtimeFailed
              ? unavailable()
              : checking()
            : statusTag(runtimeState === "ready" ? "ready" : "not ready"),
      },
      {
        key: "session-store",
        component: "Session store",
        technology: backendLabel(agent?.session_store),
        version: readyFailed || agent === undefined ? "—" : labeled(agent.session_store_version),
        status:
          readyFailed || agent === undefined
            ? readyFailed
              ? unavailable()
              : checking()
            : readyStatus(agent.session_store_ready),
      },
      {
        key: "agent-state",
        component: "Agent state store",
        technology: backendLabel(agent?.agent_state),
        version: readyFailed || agent === undefined ? "—" : labeled(agent.agent_state_version),
        status:
          readyFailed || agent === undefined
            ? readyFailed
              ? unavailable()
              : checking()
            : readyStatus(agent.agent_state_ready),
      },
      {
        key: "policy",
        component: "Policy bundle",
        technology: "JSON policy rules",
        version:
          ready?.policy_rules !== undefined
            ? `${ready.policy_rules} rule(s)`
            : "—",
        status:
          readyFailed || ready === null
            ? readyFailed
              ? unavailable()
              : checking()
            : statusTag("ready"),
      },
    ];
  }, [ready, readyFailed, runtime, runtimeFailed]);

  return (
    <div>
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="Platform version">
          <Tag style={TAG_FLAT}>{PLATFORM_VERSION}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="API origin">{currentGateway()}</Descriptions.Item>
        <Descriptions.Item label="Last request id">
          {lastApiRequestId() ?? (
            <Typography.Text type="secondary">
              no request yet this tab
            </Typography.Text>
          )}
        </Descriptions.Item>
      </Descriptions>
      <Typography.Text strong style={{ display: "block", marginTop: 16 }}>
        Key platform components
      </Typography.Text>
      <Typography.Paragraph type="secondary" style={{ margin: "4px 0 8px" }}>
        All components follow the platform version above; this table lists
        the tech stack underneath each one, read live from the
        gateway&apos;s health and runtime endpoints.
      </Typography.Paragraph>
      <Table<ComponentRow>
        size="small"
        pagination={false}
        rowKey="key"
        columns={[
          { title: "Component", dataIndex: "component", key: "component" },
          { title: "Technology", dataIndex: "technology", key: "technology" },
          { title: "Version", dataIndex: "version", key: "version" },
          { title: "Status", dataIndex: "status", key: "status" },
        ]}
        dataSource={rows}
      />
    </div>
  );
}

// --- Pane registry ---------------------------------------------------------

interface SettingsPaneDefinition {
  key: string;
  label: string;
  render: (workspace: SessionWorkspace) => ReactNode;
}

// Future panes (display preferences, per-user default model, confirmation
// / notification defaults) append here — recorded in SPEC-030 R-6 but
// deliberately not committed in this slice.
const SETTINGS_PANES: SettingsPaneDefinition[] = [
  { key: "identity", label: "Identity", render: () => <IdentityPane /> },
  {
    key: "session",
    label: "Session",
    render: (workspace) => <SessionPane workspace={workspace} />,
  },
  { key: "platform", label: "Platform", render: () => <PlatformPane /> },
];

export default function SettingsView({
  workspace,
}: {
  workspace: SessionWorkspace;
}) {
  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        Settings
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        Read-only view of the portal&apos;s session and identity state; the
        gateway stays the authority for every authorization decision.
      </Typography.Paragraph>
      <Tabs
        defaultActiveKey={SETTINGS_PANES[0]?.key}
        items={SETTINGS_PANES.map((pane) => ({
          key: pane.key,
          label: pane.label,
          children: pane.render(workspace),
        }))}
      />
    </div>
  );
}
