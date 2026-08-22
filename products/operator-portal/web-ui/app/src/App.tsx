import { useMemo, useState } from "react";
import {
  Alert,
  Avatar,
  Button,
  Drawer,
  Layout,
  Menu,
  Spin,
  Tag,
  Typography,
  type MenuProps,
} from "antd";
import {
  AuditOutlined,
  BulbOutlined,
  LoginOutlined,
  LogoutOutlined,
  MenuOutlined,
  MessageOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { useAuth } from "./auth/AuthContext";
import ChatView from "./chat/ChatView";
import { AUDIT_ROLES, INCIDENT_VIEW_ROLES, hasAnyRole } from "./roles";
import { PLATFORM_VERSION } from "./version";

export type ViewId =
  | "chat"
  | "incidents"
  | "audit"
  | "permissions"
  | "tools"
  | "skills"
  | "settings";

// Initials for the user-card avatar: up to two letters from the username,
// split on non-alphanumerics ("luban-admin" -> "LA").
export function userInitials(username: string): string {
  const parts = username.split(/[^a-zA-Z0-9]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2);
  return parts[0][0] + parts[1][0];
}

function SidebarContent({
  active,
  onNavigate,
}: {
  active: ViewId;
  onNavigate: (view: ViewId) => void;
}) {
  const { username, roles, session, login, logout, authError } = useAuth();
  const signedIn = Boolean(username);

  // Section wrappers (SPEC-019 R-1): a group header hides automatically
  // when every entry in its section is hidden.
  const controlVisible = {
    incidents: hasAnyRole(roles, INCIDENT_VIEW_ROLES),
    audit: hasAnyRole(roles, AUDIT_ROLES),
    permissions: signedIn,
  };
  const workspaceVisible = {
    tools: signedIn,
    skills: signedIn,
    settings: true,
  };

  const items = useMemo<MenuProps["items"]>(() => {
    const entries: MenuProps["items"] = [
      { key: "chat", icon: <MessageOutlined />, label: "Chat" },
    ];
    const controlItems: NonNullable<MenuProps["items"]> = [];
    if (controlVisible.incidents) {
      controlItems.push({
        key: "incidents",
        icon: <WarningOutlined />,
        label: "Incidents",
      });
    }
    if (controlVisible.audit) {
      controlItems.push({
        key: "audit",
        icon: <AuditOutlined />,
        label: "Audit trail",
      });
    }
    if (controlVisible.permissions) {
      controlItems.push({
        key: "permissions",
        icon: <SafetyCertificateOutlined />,
        label: "Permissions",
      });
    }
    if (controlItems.length > 0) {
      entries.push({
        key: "section-control",
        type: "group",
        label: "Control",
        children: controlItems,
      });
    }
    const workspaceItems: NonNullable<MenuProps["items"]> = [];
    if (workspaceVisible.tools) {
      workspaceItems.push({
        key: "tools",
        icon: <ToolOutlined />,
        label: "Tools",
      });
    }
    if (workspaceVisible.skills) {
      workspaceItems.push({
        key: "skills",
        icon: <BulbOutlined />,
        label: "Skills",
      });
    }
    if (workspaceVisible.settings) {
      workspaceItems.push({
        key: "settings",
        icon: <SettingOutlined />,
        label: "Settings",
      });
    }
    if (workspaceItems.length > 0) {
      entries.push({
        key: "section-workspace",
        type: "group",
        label: "Workspace",
        children: workspaceItems,
      });
    }
    return entries;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles, signedIn]);

  return (
    <>
      <div style={{ padding: "12px 16px" }}>
        <Typography.Title level={5} style={{ margin: 0 }}>
          Luban AIOps
        </Typography.Title>
        <Tag style={{ marginTop: 8 }}>{PLATFORM_VERSION}</Tag>
      </div>
      <Menu
        mode="inline"
        theme="dark"
        selectedKeys={[active]}
        items={items}
        onClick={({ key }) => onNavigate(key as ViewId)}
        style={{ flex: 1, borderInlineEnd: "none" }}
      />
      <div className="sidebar-footer">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Avatar size="small">
            {username ? userInitials(username) : "?"}
          </Avatar>
          <div style={{ minWidth: 0, flex: 1 }}>
            <Typography.Text ellipsis style={{ display: "block" }}>
              {username || "Not signed in"}
            </Typography.Text>
            <Typography.Text
              type="secondary"
              ellipsis
              style={{ display: "block", fontSize: 12 }}
            >
              {roles.length > 0 ? roles.join(", ") : "no role"}
            </Typography.Text>
          </div>
          {session ? (
            <Button
              type="text"
              size="small"
              icon={<LogoutOutlined />}
              aria-label="Sign out"
              onClick={() => void logout()}
            />
          ) : (
            <Button
              type="text"
              size="small"
              icon={<LoginOutlined />}
              aria-label="Sign in"
              onClick={() => void login()}
            />
          )}
        </div>
        {authError ? (
          <Alert type="error" showIcon message={authError} />
        ) : null}
      </div>
    </>
  );
}

export default function App() {
  const [active, setActive] = useState<ViewId>("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { booting } = useAuth();

  const navigate = (view: ViewId) => {
    setActive(view);
    setDrawerOpen(false);
  };

  if (booting) {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Spin size="large" tip="Starting portal…" />
      </div>
    );
  }

  return (
    <Layout className="app-shell">
      <Layout.Sider
        theme="dark"
        width={230}
        breakpoint="lg"
        collapsedWidth={0}
        trigger={null}
        style={{ borderInlineEnd: "1px solid var(--border)" }}
      >
        <SidebarContent active={active} onNavigate={navigate} />
      </Layout.Sider>
      <Layout>
        <Layout.Content
          className={
            active === "chat"
              ? "view-container view-container-flush"
              : "view-container"
          }
        >
          {active === "chat" ? (
            <ChatView />
          ) : (
            <ViewPlaceholder view={active} />
          )}
        </Layout.Content>
      </Layout>
      {/* Off-canvas sidebar for narrow viewports (legacy drawer parity). */}
      <Drawer
        placement="left"
        width={260}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        styles={{ body: { padding: 0 } }}
      >
        <SidebarContent active={active} onNavigate={navigate} />
      </Drawer>
      <Button
        className="mobile-menu-button"
        type="text"
        icon={<MenuOutlined />}
        aria-label="Open navigation"
        onClick={() => setDrawerOpen(true)}
      />
    </Layout>
  );
}

// Stage-1 shell placeholder: the remaining views land in stage 5
// (control/workspace parity). Chat is wired up in stage 3.
function ViewPlaceholder({ view }: { view: ViewId }) {
  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        <ThunderboltOutlined /> {view}
      </Typography.Title>
      <Typography.Text type="secondary">
        This view is part of the SPEC-023 rebuild and is being wired up in a
        later stage.
      </Typography.Text>
    </div>
  );
}
