// Documents view tests (SPEC-039 R-6, Workspace placement per SPEC-040
// R-3): Mine/Published split with state badges, cross-owner attribution,
// draft publish affordance, the create dialog, and the Markdown export
// (SPEC-040 R-4). The API module is mocked; the gateway re-enforces the
// role matrix server-side regardless of these client gates.
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

const { mockListDocuments, mockGetDocument, mockCurrentUser } = vi.hoisted(
  () => ({
    mockListDocuments: vi.fn(),
    mockGetDocument: vi.fn(),
    mockCurrentUser: vi.fn(),
  }),
);

vi.mock("../../../api/documents", () => ({
  listDocuments: mockListDocuments,
  getDocument: mockGetDocument,
  createDocument: vi.fn(),
  publishDocument: vi.fn(),
  deleteDocument: vi.fn(),
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
  // The drawer fetches the full document through the audited single
  // read (list rows are envelope-only); default resolves the owner draft.
  mockGetDocument.mockImplementation(async (id: string) =>
    id === "doc-2" ? foreignPublished : ownDraft,
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
    fireEvent.click(screen.getByText("New shift summary"));
    expect(screen.getByText("Your sessions")).toBeTruthy();
    expect(screen.getByText(/Foreign session ids/)).toBeTruthy();
    // Opening the picker offers the workspace sessions.
    fireEvent.mouseDown(screen.getByRole("combobox"));
    await flush();
    expect(screen.getByText(/check the pods \(ses-1\)/)).toBeTruthy();
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
    // Cross-owner attribution rides the list row and the drawer alike.
    expect(
      screen.getAllByText(/created by other\.operator/).length,
    ).toBeGreaterThanOrEqual(2);
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
    // SPEC-040 R-1: the handover skeleton leads the digest surface.
    expect(screen.getByText("Handover")).toBeTruthy();
    expect(screen.getByText(/covered_session_count/)).toBeTruthy();
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
