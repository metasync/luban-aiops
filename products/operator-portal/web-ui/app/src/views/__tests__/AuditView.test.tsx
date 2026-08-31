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

  it("renders summary sections and decision-chain zeros", async () => {
    render(<AuditView />);
    await waitFor(() => expect(mockRequestJson).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Summary"));

    await waitFor(() =>
      expect(screen.getByText("2", { selector: "strong" })).toBeTruthy(),
    );
    // Sections present.
    expect(screen.getByText("By event type")).toBeTruthy();
    expect(screen.getByText("By outcome")).toBeTruthy();
    expect(screen.getByText("By service")).toBeTruthy();
    expect(screen.getByText("Top actors")).toBeTruthy();
    expect(screen.getByText("Decision chain")).toBeTruthy();
    // Zeros render as 0, not as an error or a gap.
    const zeros = screen.getAllByText("0");
    expect(zeros.length).toBeGreaterThanOrEqual(2);
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
