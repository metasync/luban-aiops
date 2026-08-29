// Documents view tests (SPEC-039 R-6, Workspace placement per SPEC-040
// R-3): Mine/Published split with state badges, cross-owner attribution,
// draft publish affordance, the create dialog (both document types per
// SPEC-043 R-6), and the Markdown export (SPEC-040 R-4). The API module
// is mocked; the gateway re-enforces the role matrix server-side
// regardless of these client gates.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import type { OperationDocument } from "../../../api/documents";
import type { SessionWorkspace } from "../../../sessions/useSessionWorkspace";
import DocumentsView, { buildDocumentMarkdown } from "../DocumentsView";

const {
  mockListDocuments,
  mockGetDocument,
  mockCreateDocument,
  mockListIncidents,
  mockCurrentUser,
} = vi.hoisted(() => ({
  mockListDocuments: vi.fn(),
  mockGetDocument: vi.fn(),
  mockCreateDocument: vi.fn(),
  mockListIncidents: vi.fn(),
  mockCurrentUser: vi.fn(),
}));

vi.mock("../../../api/documents", () => ({
  listDocuments: mockListDocuments,
  getDocument: mockGetDocument,
  createDocument: mockCreateDocument,
  publishDocument: vi.fn(),
  deleteDocument: vi.fn(),
}));

vi.mock("../../../api/incidents", () => ({
  listIncidents: mockListIncidents,
}));

vi.mock("../../../api/client", () => ({
  ApiError: class ApiError extends Error {
    constructor(public readonly status: number, message: string) {
      super(message);
    }
  },
  currentAuthenticatedUser: mockCurrentUser,
}));

// jsdom lacks matchMedia, which antd's responsive observers probe.
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

const ownDraft: OperationDocument = {
  document_id: "doc-1",
  document_type: "shift_summary",
  state: "draft",
  owner_user_id: "luban-operator",
  label: "Night shift 2026-08-26",
  created_at: new Date(Date.now() - 30 * 60_000).toISOString(),
  provenance: {
    sessions: [
      { session_id: "ses-1", coverage: "owner", cited_record_ids: [] },
    ],
  },
  digest: { session_count: 1, sessions: [] },
  prose_status: "not_requested",
};

const foreignPublished: OperationDocument = {
  document_id: "doc-2",
  document_type: "shift_summary",
  state: "published",
  owner_user_id: "other.operator",
  label: "Day handover",
  created_at: new Date(Date.now() - 3 * 60 * 60_000).toISOString(),
  published_at: new Date(Date.now() - 2 * 60 * 60_000).toISOString(),
  provenance: {
    sessions: [
      { session_id: "ses-9", coverage: "owner", cited_record_ids: [] },
    ],
  },
  digest: {
    session_count: 1,
    sessions: [],
    // SPEC-040 R-1: the deterministic shift-story skeleton.
    handover: {
      covered_session_count: 1,
      own_session_count: 1,
      foreign_session_count: 0,
      decision_count: 0,
      execution_count: 0,
      open_items: { pending_confirmations: 0, requested_executions: 0 },
      open_sessions: [],
      quiet: true,
      decisions: [],
      executions: [],
    },
  },
  prose: "All quiet during the day shift.",
  prose_status: "included",
  // SPEC-041 R-4: the creation-time counts-only list summary.
  summary: "Quiet shift — no recorded decisions or executions.",
};

// A busy owner document exercising the full digest shape: transcript
// and evidence counts, a decided confirmation, and a completed
// execution — the raw material for the structured tabs (SPEC-041 R-2).
const busyOwn: OperationDocument = {
  document_id: "doc-3",
  document_type: "shift_summary",
  state: "draft",
  owner_user_id: "luban-operator",
  label: "Busy night",
  created_at: new Date(Date.now() - 60 * 60_000).toISOString(),
  provenance: {
    sessions: [
      { session_id: "ses-1", coverage: "owner", cited_record_ids: [] },
    ],
  },
  digest: {
    generated_at: new Date(Date.now() - 60 * 60_000).toISOString(),
    requester_user_id: "luban-operator",
    session_count: 1,
    sessions: [
      {
        session_id: "ses-1",
        coverage: "owner",
        title: "restart investigation",
        created_at: new Date(Date.now() - 3 * 60 * 60_000).toISOString(),
        transcript: { available: true, turn_count: 4, user_turn_count: 2 },
        evidence: {
          total_frame_count: 3,
          turns: [
            { turn_index: 1, frame_count: 2 },
            { turn_index: 2, frame_count: 1 },
          ],
        },
        confirmations: [
          {
            confirm_id: "cf-1",
            action: "restart_service",
            status: "decided",
            decision: "approved",
            decider_user_id: "luban-operator",
            parked_at: new Date(Date.now() - 2 * 60 * 60_000).toISOString(),
            decided_at: new Date(Date.now() - 90 * 60_000).toISOString(),
            pending_call_count: 1,
            turn_index: 2,
          },
        ],
        executions: [
          {
            execution_id: "exec-1",
            call_id: "call-1",
            tool_name: "restart_service",
            status: "completed",
            digest_match: true,
            receipt_status: "succeeded",
            completed_at: new Date(Date.now() - 80 * 60_000).toISOString(),
          },
        ],
        open_items: { pending_confirmations: 0, requested_executions: 0 },
      },
    ],
    handover: {
      covered_session_count: 1,
      own_session_count: 1,
      foreign_session_count: 0,
      decision_count: 1,
      execution_count: 1,
      open_items: { pending_confirmations: 0, requested_executions: 0 },
      open_sessions: [],
      quiet: false,
      decisions: [
        {
          session_id: "ses-1",
          confirm_id: "cf-1",
          action: "restart_service",
          decision: "approved",
          decider_user_id: "luban-operator",
          decided_at: new Date(Date.now() - 90 * 60_000).toISOString(),
        },
      ],
      executions: [
        {
          session_id: "ses-1",
          execution_id: "exec-1",
          tool_name: "restart_service",
          receipt_status: "succeeded",
          completed_at: new Date(Date.now() - 80 * 60_000).toISOString(),
        },
      ],
    },
  },
  prose_status: "not_requested",
  summary: "1 session · 1 decision · 1 execution",
};

// Foreign-coverage entries contribute the metadata-only tier: no
// title, transcript, or evidence — decisions and receipts only.
const foreignCoveredDoc: OperationDocument = {
  document_id: "doc-4",
  document_type: "shift_summary",
  state: "draft",
  owner_user_id: "luban-operator",
  label: "Cross-owner handover",
  created_at: new Date(Date.now() - 45 * 60_000).toISOString(),
  provenance: {
    sessions: [
      { session_id: "ses-9", coverage: "foreign", cited_record_ids: [] },
    ],
  },
  digest: {
    session_count: 1,
    sessions: [
      {
        session_id: "ses-9",
        coverage: "foreign",
        confirmation_decisions: [
          {
            confirm_id: "cf-9",
            action: "scale_up",
            status: "pending",
            decision: null,
            decider_user_id: null,
            parked_at: new Date(Date.now() - 40 * 60_000).toISOString(),
            decided_at: null,
          },
        ],
        execution_receipts: [],
        record_counts: { confirmations: 1, executions: 0 },
      },
    ],
    handover: {
      covered_session_count: 1,
      own_session_count: 0,
      foreign_session_count: 1,
      decision_count: 0,
      execution_count: 0,
      open_items: { pending_confirmations: 1, requested_executions: 0 },
      open_sessions: [],
      quiet: true,
      decisions: [],
      executions: [],
    },
  },
  prose_status: "not_requested",
  summary: "1 session · 0 decisions · 0 executions · 1 open item",
};

// SPEC-043 fixtures: the incident-report digest carries the four
// deterministic sections assembled verbatim from the incident bundle.
const incidentReportDoc: OperationDocument = {
  document_id: "doc-6",
  document_type: "incident_report",
  state: "draft",
  owner_user_id: "luban-operator",
  label: "Payment latency post-mortem",
  created_at: new Date(Date.now() - 20 * 60_000).toISOString(),
  provenance: {
    incident_id: "inc-abc123",
    sessions: [
      { session_id: "ses-1", coverage: "owner", cited_record_ids: [] },
    ],
  },
  digest: {
    generated_at: new Date(Date.now() - 20 * 60_000).toISOString(),
    requester_user_id: "luban-operator",
    incident: {
      incident_id: "inc-abc123",
      severity: "critical",
      status: "triaged",
      source: "webhook",
      title: "Payment API latency",
      summary: "p99 latency spike on the payment API",
      reported_by: "alertmanager",
      created_at: new Date(Date.now() - 60 * 60_000).toISOString(),
      has_triage_raw: true,
    },
    triage: {
      severity_assessment: "critical",
      summary: "Database pool exhaustion on the payment service",
      generated_by: "triage-agent",
      generated_at: new Date(Date.now() - 55 * 60_000).toISOString(),
      evidence: [{ source: "metrics", description: "pool saturation" }],
      hypotheses: ["connection pool exhaustion"],
      next_steps: [{ title: "raise pool size", priority: "immediate", rationale: "saturation" }],
      skills_cited: ["sre-database"],
    },
    dispatches: [
      {
        connector: "pagerduty",
        status: "sent",
        reference: "PD-1",
        created_at: new Date(Date.now() - 58 * 60_000).toISOString(),
      },
    ],
    session: {
      status: "owner",
      session_id: "ses-1",
      coverage: "owner",
      title: "triage inc-abc123",
      created_at: new Date(Date.now() - 50 * 60_000).toISOString(),
      transcript: { available: true, turn_count: 2, user_turn_count: 1 },
      evidence: { total_frame_count: 1 },
      confirmations: [],
      executions: [],
      open_items: { pending_confirmations: 0, requested_executions: 0 },
    },
  },
  prose_status: "not_requested",
  summary: "critical · triaged · triage report present · 1 dispatch · own session",
};

// Marker paths: an incident that never triaged carries the
// not_triaged digest marker and no linked session (missing).
const notTriagedDoc: OperationDocument = {
  document_id: "doc-7",
  document_type: "incident_report",
  state: "draft",
  owner_user_id: "luban-operator",
  label: "Untriaged intake",
  created_at: new Date(Date.now() - 15 * 60_000).toISOString(),
  provenance: { incident_id: "inc-def456", sessions: [] },
  digest: {
    generated_at: new Date(Date.now() - 15 * 60_000).toISOString(),
    requester_user_id: "luban-operator",
    incident: {
      incident_id: "inc-def456",
      severity: "info",
      status: "new",
      source: "manual",
      title: "Disk warning",
      has_triage_raw: false,
    },
    triage: { status: "not_triaged" },
    dispatches: [],
    session: { status: "missing" },
  },
  prose_status: "not_requested",
};

// Foreign linked session without approvals:list coverage rides the
// digest as the foreign_denied marker (creation still succeeds).
const foreignDeniedDoc: OperationDocument = {
  document_id: "doc-8",
  document_type: "incident_report",
  state: "draft",
  owner_user_id: "luban-operator",
  label: "Cross-owner triage",
  created_at: new Date(Date.now() - 10 * 60_000).toISOString(),
  provenance: { incident_id: "inc-ghi789", sessions: [] },
  digest: {
    generated_at: new Date(Date.now() - 10 * 60_000).toISOString(),
    requester_user_id: "luban-operator",
    incident: {
      incident_id: "inc-ghi789",
      severity: "warning",
      status: "triaged",
      source: "webhook",
      title: "Queue backlog",
    },
    triage: {
      severity_assessment: "warning",
      summary: "Consumer lag on the events queue",
      generated_by: "triage-agent",
      generated_at: new Date(Date.now() - 30 * 60_000).toISOString(),
    },
    dispatches: [],
    session: { status: "foreign_denied", session_id: "ses-9" },
  },
  prose_status: "not_requested",
};

const workspaceStub = {
  sessions: [
    {
      session_id: "ses-1",
      title: "check the pods",
      created_at: new Date().toISOString(),
      last_active_at: null,
      pending_confirmation: false,
    },
  ],
  loading: false,
  error: null,
  activeSessionId: null,
  setActiveSessionId: vi.fn(),
  refresh: vi.fn(async () => {}),
  createAndOpen: vi.fn(async () => "ses-new"),
  remove: vi.fn(async () => ({ ok: true })),
  rename: vi.fn(async () => ({ ok: true })),
  pinned: [],
  pinIncidentSession: vi.fn(() => "incident-1"),
} as unknown as SessionWorkspace;

beforeEach(() => {
  mockListDocuments.mockReset();
  mockGetDocument.mockReset();
  mockCreateDocument.mockReset();
  mockListIncidents.mockReset();
  mockListIncidents.mockResolvedValue({ incidents: [], total: 0 });
  // The drawer fetches the full document through the audited single
  // read (list rows are envelope-only); default resolves the owner draft.
  mockGetDocument.mockImplementation(async (id: string) =>
    id === "doc-2"
      ? foreignPublished
      : id === "doc-3"
        ? busyOwn
        : id === "doc-4"
          ? foreignCoveredDoc
          : id === "doc-6"
            ? incidentReportDoc
            : id === "doc-7"
              ? notTriagedDoc
              : id === "doc-8"
                ? foreignDeniedDoc
                : ownDraft,
  );
  mockCurrentUser.mockReset();
  mockCurrentUser.mockReturnValue("luban-operator");
});

afterEach(() => {
  cleanup();
});

async function flush() {
  // Let the initial list fetch settle before asserting.
  await new Promise((resolve) => window.setTimeout(resolve, 0));
}

describe("DocumentsView list (SPEC-039 R-6)", () => {
  it("renders the Mine scope with draft affordances", async () => {
    mockListDocuments.mockResolvedValue([ownDraft]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    expect(screen.getByText("Night shift 2026-08-26")).toBeTruthy();
    expect(screen.getByText("draft")).toBeTruthy();
    // Own drafts carry Publish and Delete; the list fetched scope=mine.
    expect(screen.getByText("Publish")).toBeTruthy();
    expect(screen.getByText("Delete")).toBeTruthy();
    expect(mockListDocuments).toHaveBeenCalledWith("mine");
  });

  it("attributes cross-owner published documents", async () => {
    mockListDocuments.mockImplementation(async (scope: string) =>
      scope === "published" ? [foreignPublished] : [],
    );
    render(<DocumentsView workspace={workspaceStub} />);
    fireEvent.click(screen.getByText("Published"));
    await flush();
    expect(screen.getByText("Day handover")).toBeTruthy();
    expect(screen.getByText(/created by other\.operator/)).toBeTruthy();
    // Foreign documents carry no management affordances.
    expect(screen.queryByText("Publish")).toBeNull();
    expect(screen.queryByText("Delete")).toBeNull();
  });

  it("opens the create dialog from the header action", async () => {
    mockListDocuments.mockResolvedValue([]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("New document"));
    // Shift summary stays the default type.
    expect(screen.getByText("Your sessions")).toBeTruthy();
    expect(screen.getByText(/Foreign session ids/)).toBeTruthy();
    expect(screen.getByText("Incident report")).toBeTruthy();
    // Opening the picker offers the workspace sessions.
    fireEvent.mouseDown(screen.getByRole("combobox"));
    await flush();
    expect(screen.getByText(/check the pods \(ses-1\)/)).toBeTruthy();
  });

  it("switches the create dialog to the incident report type (SPEC-043 R-6)", async () => {
    mockListDocuments.mockResolvedValue([]);
    mockListIncidents.mockResolvedValue({
      incidents: [
        {
          incident_id: "inc-abc123",
          title: "Payment API latency",
          severity: "critical",
          status: "triaged",
          source: "webhook",
          created_at: new Date().toISOString(),
        },
      ],
      total: 1,
    });
    mockCreateDocument.mockResolvedValue(incidentReportDoc);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("New document"));
    fireEvent.click(screen.getByText("Incident report"));
    await flush();
    // The incident picker replaces the session inputs and feeds from
    // the incidents list surface.
    expect(screen.queryByText("Your sessions")).toBeNull();
    expect(screen.getByText("Incident")).toBeTruthy();
    expect(mockListIncidents).toHaveBeenCalled();
    fireEvent.mouseDown(screen.getByRole("combobox"));
    await flush();
    fireEvent.click(
      screen.getByText(/Payment API latency — inc-abc123 \(critical, triaged\)/),
    );
    fireEvent.change(screen.getByPlaceholderText(/post-mortem pack/), {
      target: { value: "Payment latency post-mortem" },
    });
    fireEvent.click(screen.getByText("Create draft"));
    await flush();
    expect(mockCreateDocument).toHaveBeenCalledWith({
      document_type: "incident_report",
      incident_id: "inc-abc123",
      label: "Payment latency post-mortem",
      include_prose: true,
    });
  });

  it("labels the narrative panel unmistakably in the document drawer", async () => {
    mockListDocuments.mockResolvedValue([foreignPublished]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("View"));
    await flush();
    expect(
      screen.getByText(/AI-generated narrative — from this document's digest facts/),
    ).toBeTruthy();
    // The narrative opens expanded by default: the relieving operator
    // reads the story without an extra click, and can still collapse it.
    expect(screen.getByText("All quiet during the day shift.")).toBeTruthy();
    // Cross-owner attribution rides the list row and the drawer alike.
    expect(
      screen.getAllByText(/created by other\.operator/).length,
    ).toBeGreaterThanOrEqual(2);
    // SPEC-041 R-1: the digest reference is one link away.
    expect(screen.getByText("Learn more")).toBeTruthy();
  });

  it("offers the Markdown export from the drawer (SPEC-040 R-4)", async () => {
    mockListDocuments.mockResolvedValue([foreignPublished]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("View"));
    await flush();
    // Export renders the already-fetched document client-side: no new
    // gateway call beyond the audited single fetch.
    expect(screen.getByText("Export .md")).toBeTruthy();
    expect(mockGetDocument).toHaveBeenCalledWith("doc-2", expect.anything());
    // SPEC-041 R-2: the digest renders as tabs; the handover skeleton
    // leads as the default tab and reports the honest quiet state.
    expect(screen.getByText("Handover")).toBeTruthy();
    expect(screen.getByText("Digest data")).toBeTruthy();
    expect(screen.getAllByText(/Quiet shift/).length).toBeGreaterThanOrEqual(1);
  });
});

describe("DocumentsView digest tabs (SPEC-041 R-2)", () => {
  it("renders decisions and executions as table rows", async () => {
    mockListDocuments.mockResolvedValue([busyOwn]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("View"));
    await flush();
    // Every concern gets a tab, plus the artifact of record.
    for (const label of [
      "Handover",
      "Sessions",
      "Confirmations",
      "Executions",
      "Evidence & transcript",
      "Open items",
      "Digest data",
    ]) {
      expect(screen.getByRole("tab", { name: label })).toBeTruthy();
    }
    fireEvent.click(screen.getByRole("tab", { name: "Confirmations" }));
    expect(screen.getByText("restart_service")).toBeTruthy();
    expect(screen.getByText("approved")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Executions" }));
    expect(screen.getByText("succeeded")).toBeTruthy();
  });

  it("labels foreign sessions as the metadata-only tier", async () => {
    mockListDocuments.mockResolvedValue([foreignCoveredDoc]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("View"));
    await flush();
    fireEvent.click(screen.getByRole("tab", { name: "Sessions" }));
    // The metadata tier is labeled as metadata — never empty fields.
    expect(screen.getByText("foreign session — metadata only")).toBeTruthy();
    expect(screen.getByText(/confirmations: 1 · executions: 0/)).toBeTruthy();
    // Foreign rows still flow into the confirmations table; the
    // undecided state rides both the status cell and the tag.
    fireEvent.click(screen.getByRole("tab", { name: "Confirmations" }));
    expect(screen.getByText("scale_up")).toBeTruthy();
    expect(screen.getAllByText("pending").length).toBeGreaterThanOrEqual(2);
  });

  it("degrades documents without a handover skeleton", async () => {
    mockListDocuments.mockResolvedValue([ownDraft]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("View"));
    await flush();
    // Pre-SPEC-040 documents carry no handover tab but keep the
    // artifact of record inspectable.
    expect(screen.queryByText("Handover")).toBeNull();
    expect(screen.getByRole("tab", { name: "Digest data" })).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Digest data" }));
    expect(screen.getByText(/session_count/)).toBeTruthy();
  });
});

describe("DocumentsView incident reports (SPEC-043 R-6)", () => {
  it("renders the four-section incident digest with a type badge", async () => {
    mockListDocuments.mockResolvedValue([incidentReportDoc]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    // The list row distinguishes the type and anchors the incident.
    expect(screen.getByText("incident report")).toBeTruthy();
    expect(screen.getByText(/incident inc-abc123/)).toBeTruthy();
    fireEvent.click(screen.getByText("View"));
    await flush();
    for (const label of ["Incident", "Triage", "Dispatches", "Session", "Digest data"]) {
      expect(screen.getByRole("tab", { name: label })).toBeTruthy();
    }
    // The Incident tab leads and renders the envelope facts.
    expect(screen.getByText("Payment API latency")).toBeTruthy();
    expect(screen.getByText("critical")).toBeTruthy();
    // The raw-triage presence marker rides the incident section.
    expect(
      screen.getByText(/Raw triage text was present at creation/),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Triage" }));
    expect(
      screen.getByText("Database pool exhaustion on the payment service"),
    ).toBeTruthy();
    // The triage report follows the house layout rule: repeated records
    // with shared fields (evidence, next steps) ride tables, free-text
    // hypotheses stay bullets, and cited skills render as chips.
    expect(screen.getByText("pool saturation")).toBeTruthy();
    expect(screen.getByText("raise pool size")).toBeTruthy();
    expect(screen.getByText("connection pool exhaustion")).toBeTruthy();
    expect(screen.getByText("sre-database")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Dispatches" }));
    expect(screen.getByText("pagerduty")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Session" }));
    expect(screen.getByText("triage inc-abc123")).toBeTruthy();
  });

  it("renders not_triaged and missing-session markers as alerts", async () => {
    mockListDocuments.mockResolvedValue([notTriagedDoc]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("View"));
    await flush();
    fireEvent.click(screen.getByRole("tab", { name: "Triage" }));
    expect(screen.getByText("Not triaged")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Session" }));
    expect(screen.getByText("No linked session")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Dispatches" }));
    expect(
      screen.getByText("No connector dispatches were recorded for this incident."),
    ).toBeTruthy();
  });

  it("renders the foreign_denied session marker", async () => {
    mockListDocuments.mockResolvedValue([foreignDeniedDoc]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("View"));
    await flush();
    fireEvent.click(screen.getByRole("tab", { name: "Session" }));
    expect(
      screen.getByText("Session not covered by your role"),
    ).toBeTruthy();
  });

  it("exports incident provenance in the Markdown download", () => {
    const markdown = buildDocumentMarkdown(incidentReportDoc);
    expect(markdown).toContain("# Payment latency post-mortem");
    expect(markdown).toContain("| Type | incident report |");
    expect(markdown).toContain("- Incident `inc-abc123`");
    expect(markdown).toContain("`ses-1` — owner coverage");
    // The digest JSON carries the incident sections verbatim.
    expect(markdown).toContain('"incident_id": "inc-abc123"');
  });
});

describe("DocumentsView list summaries and bounded panes (SPEC-041 R-3, R-4)", () => {
  it("shows the counts-only summary on list rows", async () => {
    mockListDocuments.mockResolvedValue([busyOwn]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    expect(screen.getByText("1 session · 1 decision · 1 execution")).toBeTruthy();
  });

  it("keeps pre-SPEC-041 rows label-only", async () => {
    mockListDocuments.mockResolvedValue([ownDraft]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    expect(screen.queryByText(/decision/)).toBeNull();
  });

  it("bounds long panes and offers expansion", async () => {
    // jsdom reports zero layout; force overflow to exercise the
    // expand affordance.
    const scrollSpy = vi
      .spyOn(Element.prototype, "scrollHeight", "get")
      .mockReturnValue(2000);
    mockListDocuments.mockResolvedValue([foreignPublished]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("View"));
    await flush();
    // The digest and prose panes each offer expansion.
    const expandButtons = screen.getAllByText("Expand to full height");
    expect(expandButtons.length).toBe(2);
    fireEvent.click(expandButtons[0].closest("button") as HTMLElement);
    expect(
      screen.getAllByText("Collapse to bounded height").length,
    ).toBeGreaterThanOrEqual(1);
    scrollSpy.mockRestore();
  });
});

describe("DocumentsView AI one-liner blurb (v0.23.3)", () => {
  // The prose SUMMARY marker yields a bounded blurb that rides the
  // envelope-only list rows and the full document alike.
  const blurbedDoc: OperationDocument = {
    ...foreignPublished,
    document_id: "doc-5",
    blurb: "A quiet day shift — monitoring only, nothing to inherit.",
  };

  it("shows the AI blurb in the list row ahead of the counts-only summary", async () => {
    mockListDocuments.mockResolvedValue([blurbedDoc]);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    expect(
      screen.getByText("A quiet day shift — monitoring only, nothing to inherit."),
    ).toBeTruthy();
    expect(
      screen.queryByText("Quiet shift — no recorded decisions or executions."),
    ).toBeNull();
  });

  it("shows the blurb on the detail card", async () => {
    mockListDocuments.mockResolvedValue([blurbedDoc]);
    mockGetDocument.mockResolvedValue(blurbedDoc);
    render(<DocumentsView workspace={workspaceStub} />);
    await flush();
    fireEvent.click(screen.getByText("View"));
    await flush();
    expect(
      screen.getAllByText("A quiet day shift — monitoring only, nothing to inherit.")
        .length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("leads the Markdown export with the blurb", () => {
    const markdown = buildDocumentMarkdown(blurbedDoc);
    expect(markdown).toContain(
      "> A quiet day shift — monitoring only, nothing to inherit.",
    );
  });
});

describe("buildDocumentMarkdown (SPEC-040 R-4)", () => {
  it("serializes metadata, provenance, digest, and narrative", () => {
    const markdown = buildDocumentMarkdown(foreignPublished);
    expect(markdown).toContain("# Day handover");
    expect(markdown).toContain("`doc-2`");
    expect(markdown).toContain("other.operator");
    expect(markdown).toContain("`ses-9` — owner coverage");
    expect(markdown).toContain("## Digest (deterministic facts)");
    // The handover skeleton rides the exported digest JSON.
    expect(markdown).toContain("\"covered_session_count\": 1");
    expect(markdown).toContain("All quiet during the day shift.");
    expect(markdown).toContain("Exported ");
  });

  it("exports the digest alone when narrative generation failed", () => {
    const failed: OperationDocument = { ...ownDraft, prose_status: "failed" };
    const markdown = buildDocumentMarkdown(failed);
    expect(markdown).toContain("## Digest (deterministic facts)");
    expect(markdown).toContain("Narrative generation failed");
    expect(markdown).not.toContain("## Handover narrative");
  });
});
