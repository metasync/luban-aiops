import { useEffect, useMemo, useState } from "react";
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
  ToolOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { useAuth } from "./auth/AuthContext";
import ChatView from "./chat/ChatView";
import { AUDIT_ROLES, INCIDENT_VIEW_ROLES, hasAnyRole } from "./roles";
import { useSessionWorkspace } from "./sessions/useSessionWorkspace";
import AuditView from "./views/audit/AuditView";
import PermissionsView from "./views/control/PermissionsView";
import SettingsView from "./views/control/SettingsView";
import SkillsView from "./views/control/SkillsView";
import ToolsView from "./views/control/ToolsView";
import IncidentsView from "./views/incidents/IncidentsView";
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

// Tracks the antd Sider lg breakpoint (992px): below it the inline sidebar
// auto-collapses and navigation moves into the drawer.
function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = useState(
    () => window.matchMedia("(max-width: 991px)").matches,
  );
  useEffect(() => {
    const query = window.matchMedia("(max-width: 991px)");
    const update = (event: MediaQueryListEvent) => setNarrow(event.matches);
    setNarrow(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return narrow;
}

function SidebarContent({
  active,
  onNavigate,
  collapsed,
}: {
  active: ViewId;
  onNavigate: (view: ViewId) => void;
  collapsed: boolean;
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
      {collapsed ? (
        // Folded rail: the brand shrinks to a spacer keeping the icon
        // menu clear of the pinned trigger; the version tag returns
        // with the expanded brand below.
        <div className="sidebar-brand-spacer" aria-hidden="true" />
      ) : (
        <div className="sidebar-brand" style={{ padding: "12px 16px" }}>
          {/* Title and version share one line so the brand block stays as
              compact as the session-panel header it visually parallels. */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Typography.Title level={5} style={{ margin: 0, whiteSpace: "nowrap" }}>
              Luban AIOps
            </Typography.Title>
            <Tag style={{ margin: 0 }}>{PLATFORM_VERSION}</Tag>
          </div>
        </div>
      )}
      <Menu
        mode="inline"
        theme="dark"
        selectedKeys={[active]}
        items={items}
        onClick={({ key }) => onNavigate(key as ViewId)}
        style={{ flex: 1, borderInlineEnd: "none" }}
      />
      <div
        className={
          collapsed
            ? "sidebar-footer sidebar-footer-collapsed"
            : "sidebar-footer"
        }
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Avatar size="small">
            {username ? userInitials(username) : "?"}
          </Avatar>
          {!collapsed && (
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
          )}
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
        {authError && !collapsed ? (
          <Alert type="error" showIcon message={authError} />
        ) : null}
      </div>
    </>
  );
}

export default function App() {
  const [active, setActive] = useState<ViewId>("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Desktop sidebar fold state; below the lg breakpoint the Sider
  // auto-collapses (onBreakpoint) and the drawer takes over.
  const [siderCollapsed, setSiderCollapsed] = useState(false);
  const narrow = useNarrowViewport();
  const { booting, username } = useAuth();
  // The session workspace lives here so the incidents view can pin
  // incident sessions into the chat panel (SPEC-023 R-3 deep links).
  const workspace = useSessionWorkspace(Boolean(username));

  const navigate = (view: ViewId) => {
    setActive(view);
    setDrawerOpen(false);
  };

  const openIncidentSession = (incident: {
    incident_id: string;
    session_id?: string | null;
  }) => {
    workspace.pinIncidentSession(
      incident.incident_id,
      incident.session_id ?? undefined,
    );
    navigate("chat");
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
        // Folded keeps a 64px icon rail (antd renders the inline menu
        // icon-only with tooltips) so navigation stays reachable and every
        // view aligns uniformly to the right of the rail.
        collapsedWidth={64}
        trigger={null}
        collapsible
        collapsed={siderCollapsed}
        onBreakpoint={(broken) => setSiderCollapsed(broken)}
        style={{ borderInlineEnd: "1px solid var(--border)" }}
      >
        <SidebarContent
          active={active}
          onNavigate={navigate}
          collapsed={siderCollapsed}
        />
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
            <ChatView workspace={workspace} />
          ) : active === "incidents" ? (
            <IncidentsView onOpenIncidentSession={openIncidentSession} />
          ) : active === "audit" ? (
            <AuditView />
          ) : active === "permissions" ? (
            <PermissionsView />
          ) : active === "tools" ? (
            <ToolsView />
          ) : active === "skills" ? (
            <SkillsView />
          ) : (
            <SettingsView workspace={workspace} />
          )}
        </Layout.Content>
      </Layout>
      {/* Off-canvas sidebar for narrow viewports: the folded 64px icon
          rail stays visible at every width for one-tap navigation, and
          the drawer adds the full labeled menu on demand. */}
      <Drawer
        placement="left"
        width={260}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        styles={{ body: { padding: 0 } }}
      >
        <SidebarContent active={active} onNavigate={navigate} collapsed={false} />
      </Drawer>
      <Button
        className="mobile-menu-button"
        type="text"
        icon={<MenuOutlined />}
        aria-label={
          narrow
            ? "Open navigation"
            : siderCollapsed
              ? "Show navigation"
              : "Hide navigation"
        }
        onClick={() =>
          narrow ? setDrawerOpen(true) : setSiderCollapsed(!siderCollapsed)
        }
      />
    </Layout>
  );
}
