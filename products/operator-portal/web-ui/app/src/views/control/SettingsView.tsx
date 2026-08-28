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
import { PLATFORM_VERSION } from "../../version";

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
        message="You are signed out"
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

// v0.23.3: live component inventory. /health/ready and /api/v1/runtime
// are unauthenticated by design (health probes and runtime metadata only),
// so the pane can read them directly; every row degrades to "unavailable"
// when a probe fails rather than showing stale or guessed values.

interface AgentServiceHealth {
  status?: string;
  runtime_mode?: string;
  session_store?: string | null;
  session_store_ready?: boolean | null;
  agent_state?: string | null;
  agent_state_ready?: boolean | null;
}

interface GatewayReadyStatus {
  status?: string;
  version?: string;
  agent_service?: AgentServiceHealth;
  policy_rules?: number;
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
  version: string;
  status: ReactNode;
}

const TAG_FLAT = { margin: 0 };

function readyTag(ready: boolean | null | undefined): ReactNode {
  if (ready === true) {
    return <Tag color="success" style={TAG_FLAT}>ready</Tag>;
  }
  if (ready === false) {
    return <Tag color="error" style={TAG_FLAT}>not ready</Tag>;
  }
  return <Typography.Text type="secondary">unknown</Typography.Text>;
}

function unavailable(): ReactNode {
  return <Typography.Text type="secondary">unavailable</Typography.Text>;
}

function checking(): ReactNode {
  return <Typography.Text type="secondary">checking…</Typography.Text>;
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
    return [
      {
        key: "portal",
        component: "Operator portal",
        version: PLATFORM_VERSION,
        status: <Tag color="success" style={TAG_FLAT}>loaded</Tag>,
      },
      {
        key: "gateway",
        component: "Platform gateway",
        version: ready?.version ?? "—",
        status:
          readyFailed || gatewayStatus === undefined ? (
            readyFailed ? unavailable() : checking()
          ) : gatewayStatus === "ok" ? (
            <Tag color="success" style={TAG_FLAT}>ok</Tag>
          ) : (
            <Tag color="warning" style={TAG_FLAT}>{gatewayStatus}</Tag>
          ),
      },
      {
        key: "agent-service",
        component: "Agent service",
        version: agent?.runtime_mode ?? "—",
        status:
          readyFailed || agent === undefined ? (
            readyFailed ? unavailable() : checking()
          ) : agent.status === "ready" ? (
            <Tag color="success" style={TAG_FLAT}>ready</Tag>
          ) : (
            <Tag color="error" style={TAG_FLAT}>not ready</Tag>
          ),
      },
      {
        key: "agent-runtime",
        component: "Agent runtime (LLM)",
        version: runtime?.model_name ?? runtime?.provider ?? "—",
        status:
          runtimeFailed || runtimeState === undefined ? (
            runtimeFailed ? unavailable() : checking()
          ) : runtimeState === "ready" ? (
            <Tag color="success" style={TAG_FLAT}>ready</Tag>
          ) : runtimeState === "provider_error" ? (
            <Tag color="error" style={TAG_FLAT}>provider error</Tag>
          ) : (
            <Tag style={TAG_FLAT}>not configured</Tag>
          ),
      },
      {
        key: "session-store",
        component: "Session store",
        version: agent?.session_store ?? "—",
        status:
          readyFailed || agent === undefined
            ? readyFailed
              ? unavailable()
              : checking()
            : readyTag(agent.session_store_ready),
      },
      {
        key: "agent-state",
        component: "Agent state store",
        version: agent?.agent_state ?? "—",
        status:
          readyFailed || agent === undefined
            ? readyFailed
              ? unavailable()
              : checking()
            : readyTag(agent.agent_state_ready),
      },
      {
        key: "policy",
        component: "Policy bundle",
        version:
          ready?.policy_rules !== undefined
            ? `${ready.policy_rules} rule(s)`
            : "—",
        status:
          readyFailed || ready === null ? (
            readyFailed ? unavailable() : checking()
          ) : (
            <Tag color="success" style={TAG_FLAT}>loaded</Tag>
          ),
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
        Live read from the gateway&apos;s health and runtime endpoints —
        component versions and readiness at this moment.
      </Typography.Paragraph>
      <Table<ComponentRow>
        size="small"
        pagination={false}
        rowKey="key"
        columns={[
          { title: "Component", dataIndex: "component", key: "component" },
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
