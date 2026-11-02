// Settings ▸ Platform feature-flags panel tests (SPEC-072 R-6): the
// authenticated runtime:flags inventory renders each flag's label with an
// on/off state for a granted role (F8), degrades to "unavailable" on a
// 403/error while the unauthenticated component-health rows persist (F9), and
// never renders a secret value that rides the payload. The API client is
// mocked; the gateway re-enforces runtime:flags server-side regardless of
// these client gates.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { ApiError } from "../../../api/client";
import type { SessionWorkspace } from "../../../sessions/useSessionWorkspace";
import SettingsView from "../SettingsView";

const { mockUseAuth, mockRequestJson } = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockRequestJson: vi.fn(),
}));

vi.mock("../../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));
// Keep the real ApiError/currentGateway exports; only requestJson is faked, so
// getRuntimeFlags (which rides requestJson) is exercised end to end.
vi.mock("../../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/client")>();
  return {
    ...actual,
    requestJson: mockRequestJson,
    currentGateway: () => "http://gateway.test",
    buildRequestId: () => "req-test",
    authHeaders: () => ({ authorization: "Bearer test-token" }),
  };
});

// antd's Tabs/Table probe matchMedia through the responsive observer, which
// jsdom lacks; shim it so the panes mount (mirrors ApprovalsView.test.tsx).
beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});

// The unauthenticated health probes always resolve with a complete payload so
// the component rows stay healthy; only the flags fetch varies per test.
const READY = {
  status: "ok",
  version: "0.52.0",
  policy_rules: 21,
  python_version: "3.12.0",
  fastapi_version: "0.115.0",
  agent_service: {
    status: "ready",
    agentscope_version: "0.1.0",
    fastapi_version: "0.115.0",
    session_store: "postgres",
    session_store_ready: true,
    session_store_version: "16.4",
    agent_state: "redis",
    agent_state_ready: true,
    agent_state_version: "7.2",
  },
};
const RUNTIME = {
  runtime_mode: "live",
  runtime_state: "ready",
  provider: "dashscope",
  model_name: "qwen-max",
};

// A representative slice of the curated nine: routing off, the rest on.
const FLAGS = {
  feature_flags: [
    { name: "model_routing", enabled: false, label: "Per-turn model routing" },
    { name: "model_discovery", enabled: true, label: "Live model discovery" },
    { name: "signed_execution", enabled: true, label: "Signed execution" },
  ],
};

const WORKSPACE = {
  activeSessionId: null,
  sessions: [],
} as unknown as SessionWorkspace;

// Route each PlatformPane fetch by path. The flags path is supplied per test;
// the two health probes always resolve so the component rows never degrade.
function mockPlatformFetches(flagsImpl: () => Promise<unknown>) {
  mockRequestJson.mockImplementation((path: string) => {
    if (path === "/health/ready") return Promise.resolve(READY);
    if (path === "/api/v1/runtime") return Promise.resolve(RUNTIME);
    if (path === "/api/v1/runtime/flags") return flagsImpl();
    return Promise.reject(new Error(`unexpected fetch ${path}`));
  });
}

// The Platform pane mounts lazily on tab activation (rc-tabs), which is what
// fires its health + flags fetches — so activate it before asserting.
async function openPlatformPane() {
  render(<SettingsView workspace={WORKSPACE} />);
  fireEvent.click(screen.getByRole("tab", { name: "Platform" }));
}

beforeEach(() => {
  mockUseAuth.mockReset();
  mockUseAuth.mockReturnValue({
    session: null,
    username: "luban-operator",
    roles: ["operator"],
    login: vi.fn(),
  });
  mockRequestJson.mockReset();
});

// Vitest globals are off, so testing-library's auto-cleanup never registers;
// unmount explicitly to keep renders isolated (antd portals included).
afterEach(() => {
  cleanup();
});

describe("SettingsView ▸ Platform feature flags (SPEC-072 R-6)", () => {
  it("renders each flag label with its on/off state for a granted role", async () => {
    // F8: an operator holds runtime:flags, so the inventory renders read-only.
    mockPlatformFetches(() => Promise.resolve(FLAGS));
    await openPlatformPane();
    await waitFor(() =>
      expect(screen.getByText("Per-turn model routing")).toBeTruthy(),
    );

    expect(screen.getByText("Feature flags")).toBeTruthy();
    expect(screen.getByText("Live model discovery")).toBeTruthy();

    // Each row's state cell carries exactly one on/off tag.
    const routingRow = screen
      .getByText("Per-turn model routing")
      .closest("tr");
    expect(routingRow?.querySelector(".ant-tag")?.textContent).toBe("off");
    const discoveryRow = screen
      .getByText("Live model discovery")
      .closest("tr");
    expect(discoveryRow?.querySelector(".ant-tag")?.textContent).toBe("on");
  });

  it("degrades the section to unavailable on a 403 while health rows persist", async () => {
    // F9: an observer lacks runtime:flags; the gateway 403s the flags fetch.
    mockUseAuth.mockReturnValue({
      session: null,
      username: "observer.user",
      roles: ["read-only-observer"],
      login: vi.fn(),
    });
    mockPlatformFetches(() =>
      Promise.reject(new ApiError(403, "Request failed: 403 Forbidden")),
    );
    await openPlatformPane();
    await waitFor(() => expect(screen.getByText("unavailable")).toBeTruthy());

    // No flag rows render, yet the unauthenticated component-health rows do.
    expect(screen.queryByText("Per-turn model routing")).toBeNull();
    expect(screen.getByText("Operator portal")).toBeTruthy();
    expect(screen.getByText("Platform gateway")).toBeTruthy();
  });

  it("never renders a secret value that rides the payload", async () => {
    // The inventory is names + booleans; the pane renders label/name + on/off
    // only, so a stray secret field can never reach the DOM.
    mockPlatformFetches(() =>
      Promise.resolve({
        feature_flags: [
          {
            name: "signed_execution",
            enabled: true,
            label: "Signed execution",
            signing_key: "hmac-SUPERSECRET-do-not-render",
          },
        ],
      }),
    );
    await openPlatformPane();
    await waitFor(() =>
      expect(screen.getByText("Signed execution")).toBeTruthy(),
    );

    expect(screen.queryByText(/SUPERSECRET/)).toBeNull();
    expect(document.body.textContent).not.toContain("hmac-SUPERSECRET");
  });
});
