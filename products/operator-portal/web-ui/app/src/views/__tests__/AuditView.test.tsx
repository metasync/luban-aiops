// Audit view tests (SPEC-046 R-5): the shared filter toolbar drives both
// tabs and the export; the Summary tab renders the deterministic
// aggregates (decision-chain zeros included); Export CSV rides the
// SPEC-040 R-4 Blob posture with the server filename and surfaces the
// truncation notice; 403/502/503 get structured messages.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import AuditView from "../audit/AuditView";

const { mockUseAuth, mockRequestJson } = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockRequestJson: vi.fn(),
}));

vi.mock("../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));
vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    requestJson: mockRequestJson,
    currentGateway: () => "http://gateway.test",
    buildRequestId: () => "req-test",
    authHeaders: () => ({ authorization: "Bearer test-token" }),
  };
});

const SUMMARY_FIXTURE = {
  total_events: 2,
  window: {},
  by_event_type: [
    { name: "tool_invoked", count: 1 },
    { name: "execution_completed", count: 1 },
  ],
  by_outcome: [{ name: "success", count: 2 }],
  by_service: [
    { name: "execution-runtime", count: 1 },
    { name: "tool-gateway", count: 1 },
  ],
  top_actors: [{ name: "alice", count: 2 }],
  decision_chain: {
    confirmation_decided: 0,
    execution_requested: 1,
    execution_completed: 1,
    execution_rejected: 0,
  },
};

function jsonResponse(url: string) {
  if (url.includes("/api/v1/audit/summary")) {
    return Promise.resolve(SUMMARY_FIXTURE);
  }
  // Events tab: one empty page, end of trail.
  return Promise.resolve({ events: [], next_cursor: null });
}

beforeEach(() => {
  mockUseAuth.mockReset();
  mockUseAuth.mockReturnValue({ username: "luban-auditor", roles: ["auditor"] });
  mockRequestJson.mockReset();
  mockRequestJson.mockImplementation((url: string) => jsonResponse(url));
  URL.createObjectURL = vi.fn(() => "blob:mock");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("role gate", () => {
  it("blocks roles without audit access", () => {
    mockUseAuth.mockReturnValue({
      username: "luban-operator",
      roles: ["operator"],
    });
    render(<AuditView />);
    expect(
      screen.getByText(/requires the auditor or platform-admin role/),
    ).toBeTruthy();
    expect(mockRequestJson).not.toHaveBeenCalled();
  });

  it("keeps the hook order when the role gate flips while mounted (v0.29.2)", async () => {
    const { rerender } = render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());

    // Sign-out and scheduled token refresh can flip the gate while this
    // view stays mounted; the hook sequence must stay identical across
    // the flip or React unmounts the whole shell.
    mockUseAuth.mockReturnValue({ username: null, roles: [] });
    expect(() => rerender(<AuditView />)).not.toThrow();
    expect(
      screen.getByText(/requires the auditor or platform-admin role/),
    ).toBeTruthy();
  });

  it("recovers the initial load when the session lifecycle moves (v0.29.3)", async () => {
    // Stale-session boot window: the shell renders signed-in under an
    // expired stored session, so the first auto-load can hit a 401.
    const stale = { access_token: "stale-token" };
    const fresh = { access_token: "fresh-token" };
    mockUseAuth.mockReturnValue({
      username: "luban-auditor",
      roles: ["auditor"],
      session: stale,
    });
    mockRequestJson.mockImplementation(() =>
      Promise.reject(new ApiError(401, "Request failed: 401 Unauthorized")),
    );
    const { rerender } = render(<AuditView />);
    await waitFor(() =>
      expect(screen.getByText(/Audit request failed: 401/)).toBeTruthy(),
    );

    // Fresh sign-in swaps the session object; the view must clear the
    // latched failure and retry without a manual Refresh.
    mockRequestJson.mockImplementation((url: string) => jsonResponse(url));
    mockUseAuth.mockReturnValue({
      username: "luban-auditor",
      roles: ["auditor"],
      session: fresh,
    });
    rerender(<AuditView />);
    await waitFor(() =>
      expect(
        screen.getByText(/No audit events match these filters/),
      ).toBeTruthy(),
    );
    expect(screen.queryByText(/Audit request failed: 401/)).toBeNull();
  });
});

describe("tabs and shared filters", () => {
  it("switching to Summary fetches with the current filters", async () => {
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());

    const usernameInput = screen.getByLabelText("Filter by username");
    fireEvent.change(usernameInput, { target: { value: "alice" } });

    fireEvent.click(screen.getByText("Summary"));
    await waitFor(() =>
      expect(mockRequestJson).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/audit/summary?username=alice"),
      ),
    );
    // Filters survive the tab switch.
    expect((usernameInput as HTMLInputElement).value).toBe("alice");
  });

  it("renders the statistic row, collapsible sections, and chain zeros", async () => {
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Summary"));

    // R-6 statistic row: total + the four chain steps, zeros as 0.
    await waitFor(() =>
      expect(screen.getByText("Total events")).toBeTruthy(),
    );
    expect(screen.getByText("confirmation_decided")).toBeTruthy();
    expect(screen.getByText("execution_requested")).toBeTruthy();
    // Also a bucket name in the fixture — the chain step and the
    // "By event type" row both render it.
    expect(screen.getAllByText("execution_completed").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("execution_rejected")).toBeTruthy();
    const zeros = screen.getAllByText("0");
    expect(zeros.length).toBeGreaterThanOrEqual(2);

    // R-5 sections render expanded by default — bucket rows visible
    // without any interaction.
    expect(screen.getByText("By event type")).toBeTruthy();
    expect(screen.getByText("By outcome")).toBeTruthy();
    expect(screen.getByText("By service")).toBeTruthy();
    expect(screen.getByText("Top actors")).toBeTruthy();
    expect(screen.getByText("execution-runtime")).toBeTruthy();
    expect(screen.getByText("alice")).toBeTruthy();

    // R-4 proportion math: 1 of 2 events → 50.0%.
    expect(screen.getAllByText("50.0%").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("100.0%").length).toBeGreaterThanOrEqual(2);
  });

  it("outcome select rides the shared toolbar", async () => {
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());
    expect(screen.getByLabelText("Filter by outcome")).toBeTruthy();
  });

  it("summary surfaces structured 502 message", async () => {
    mockRequestJson.mockImplementation((url: string) => {
      if (url.includes("/summary")) {
        return Promise.reject(
          new ApiError(502, "Request failed: 502 Bad Gateway"),
        );
      }
      return Promise.resolve({ events: [], next_cursor: null });
    });
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Summary"));
    await waitFor(() =>
      expect(
        screen.getByText(/audit service is unavailable right now/),
      ).toBeTruthy(),
    );
  });
});

describe("summary drill-down (SPEC-047 R-3)", () => {
  it("bucket drill-down merges the filter, keeping other dimensions", async () => {
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());

    // Set two unrelated dimensions first.
    fireEvent.change(screen.getByLabelText("Filter by username"), {
      target: { value: "alice" },
    });
    fireEvent.change(screen.getByLabelText("Since"), {
      target: { value: "2026-08-01T00:00" },
    });

    fireEvent.click(screen.getByText("Summary"));
    await waitFor(() =>
      expect(screen.getByLabelText("Drill into execution-runtime")).toBeTruthy(),
    );
    fireEvent.click(screen.getByLabelText("Drill into execution-runtime"));

    // Lands on the Events tab under merged filters: the targeted
    // dimension is set, username and the time range survive (Q-3).
    await waitFor(() => {
      const calls = mockRequestJson.mock.calls.map((call) => call[0] as string);
      const landing = calls.filter((url) =>
        url.includes("/api/v1/audit/events?"),
      );
      const last = landing[landing.length - 1];
      expect(last).toContain("service=execution-runtime");
      expect(last).toContain("username=alice");
      expect(last).toContain("since=");
    });
  });

  it("chain-step drill-down targets its event type, even at zero", async () => {
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Summary"));
    await waitFor(() =>
      expect(screen.getByLabelText("Drill into confirmation_decided")).toBeTruthy(),
    );
    // confirmation_decided is 0 in the fixture — zero-count buckets
    // still navigate.
    fireEvent.click(screen.getByLabelText("Drill into confirmation_decided"));
    await waitFor(() => {
      const calls = mockRequestJson.mock.calls.map((call) => call[0] as string);
      expect(
        calls.some((url) =>
          url.includes("/api/v1/audit/events?") &&
          url.includes("event_type=confirmation_decided"),
        ),
      ).toBe(true);
    });
  });

  it("zero-total summary renders the empty posture without division", async () => {
    mockRequestJson.mockImplementation((url: string) => {
      if (url.includes("/summary")) {
        return Promise.resolve({
          ...SUMMARY_FIXTURE,
          total_events: 0,
          by_event_type: [],
          by_outcome: [],
          by_service: [],
          top_actors: [],
          decision_chain: {
            confirmation_decided: 0,
            execution_requested: 0,
            execution_completed: 0,
            execution_rejected: 0,
          },
        });
      }
      return Promise.resolve({ events: [], next_cursor: null });
    });
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Summary"));
    await waitFor(() =>
      expect(
        screen.getByText(/events match the current filters/),
      ).toBeTruthy(),
    );
    // Zero renders as 0 — no division, no NaN.
    expect(screen.getByText("0", { selector: "strong" })).toBeTruthy();
  });
});

describe("export", () => {
  function mockExportFetch(headers: Record<string, string>) {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      blob: async () => new Blob(["occurred_at\r\n"], { type: "text/csv" }),
      headers: new Headers(headers),
    })) as unknown as typeof fetch;
  }

  it("downloads the Blob under the server filename", async () => {
    mockExportFetch({
      "content-disposition":
        'attachment; filename="audit-export-20260831T120000Z.csv"',
      "x-audit-export-truncated": "false",
      "x-audit-export-rows": "1",
    });
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());

    fireEvent.click(screen.getByText("Export CSV"));
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("http://gateway.test/api/v1/audit/export"),
      expect.objectContaining({
        headers: expect.objectContaining({ authorization: "Bearer test-token" }),
      }),
    );
    // Not truncated: no warning notice.
    expect(screen.queryByText(/Export truncated/)).toBeNull();
  });

  it("shows the truncation notice when the cap bites", async () => {
    mockExportFetch({
      "content-disposition":
        'attachment; filename="audit-export-20260831T120000Z.csv"',
      "x-audit-export-truncated": "true",
      "x-audit-export-rows": "10000",
    });
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());

    fireEvent.click(screen.getByText("Export CSV"));
    await waitFor(() =>
      expect(screen.getByText(/Export truncated at 10000 rows/)).toBeTruthy(),
    );
  });

  it("surfaces structured 403 message on export denial", async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      headers: new Headers(),
    })) as unknown as typeof fetch;
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());

    fireEvent.click(screen.getByText("Export CSV"));
    await waitFor(() =>
      expect(screen.getByText(/requires the audit:read policy action/)).toBeTruthy(),
    );
  });
});
