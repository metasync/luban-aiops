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
  Tabs,
  Tag,
  Typography,
} from "antd";
import { LoginOutlined, UserOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";
import { currentGateway, lastApiRequestId } from "../../api/client";
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

function PlatformPane() {
  return (
    <Descriptions column={1} size="small" bordered>
      <Descriptions.Item label="Platform version">
        <Tag style={{ margin: 0 }}>{PLATFORM_VERSION}</Tag>
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
