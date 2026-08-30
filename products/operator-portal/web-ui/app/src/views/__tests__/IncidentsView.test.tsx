// Incident-anchored "Draft as skill" tests (SPEC-045 R-4/R-5): the
// detail toolbar button's role visibility (client-side mirror of
// allow-operators-incident-skill-draft; the gateway re-enforces
// incident:skill_draft + incident:read regardless), the busy state,
// the structured 403/404/409/502/503 toasts — 409 names the missing
// validated triage report — and the shared preview modal opening on
// success instead of a blind download.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import IncidentsView from "../incidents/IncidentsView";
import type { IncidentDetailPayload } from "../../api/incidents";

const { mockUseAuth, mockListIncidents, mockGetIncident, mockCreateDraft } =
  vi.hoisted(() => ({
    mockUseAuth: vi.fn(),
    mockListIncidents: vi.fn(),
    mockGetIncident: vi.fn(),
    mockCreateDraft: vi.fn(),
  }));

vi.mock("../../auth/AuthContext", () => ({ useAuth: mockUseAuth }));
vi.mock("../../api/incidents", () => ({
  listIncidents: mockListIncidents,
  getIncident: mockGetIncident,
  reportIncident: vi.fn(),
  runTriage: vi.fn(),
  createIncidentSkillDraft: mockCreateDraft,
}));

const SUMMARY = {
  incident_id: "inc-1",
  title: "Checkout down",
  severity: "critical",
  status: "triaged",
  source: "alertmanager",
  created_at: "2026-08-30T00:00:00Z",
};

const TRIAGED_DETAIL: IncidentDetailPayload = {
  incident: {
    ...SUMMARY,
    fingerprint: "fp-1",
    updated_at: "2026-08-30T00:05:00Z",
    reported_by: null,
    resolved_at: null,
    labels: {},
    summary: "checkout pods crash-looping",
    session_id: "ses-triage",
    triage_raw: null,
  },
  report: {
    severity_assessment: "critical",
    generated_by: "luban-agent-platform",
    generated_at: "2026-08-30T00:05:00Z",
    session_id: "ses-triage",
    summary: "Checkout pods crash-loop after deploy.",
  },
  dispatches: [],
};

const DRAFT_RESPONSE = {
  markdown: "---\ntitle: \"Triage runbook: Checkout down\"\n---\n\nBody\n",
  mode: "generated",
  validation: "passed",
  suggested_filename: "triage-runbook-checkout-down.md",
};

function useRoles(roles: string[]) {
  mockUseAuth.mockReturnValue({ roles });
}

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

async function openIncidentDetail(roles: string[], detail = TRIAGED_DETAIL) {
  useRoles(roles);
  mockListIncidents.mockResolvedValue({ incidents: [SUMMARY], total: 1 });
  mockGetIncident.mockResolvedValue(detail);
  render(<IncidentsView onOpenIncidentSession={() => {}} />);
  // Let the initial list load settle before driving the row click.
  await screen.findByText("Checkout down");
  await act(async () => {
    fireEvent.click(screen.getByText("Checkout down"));
  });
  // The detail toolbar is showing once the triage action resolved.
  await screen.findByText("Continue in chat");
}

beforeEach(() => {
  mockUseAuth.mockReset();
  mockListIncidents.mockReset();
  mockGetIncident.mockReset();
  mockCreateDraft.mockReset();
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("IncidentsView draft-as-skill (SPEC-045 R-4)", () => {
  it.each([["operator"], ["approver"], ["platform-admin"]])(
    "shows the button for %s",
    async (role) => {
      await openIncidentDetail([role]);
      expect(screen.getByLabelText("Draft as skill")).toBeTruthy();
    },
  );

  it.each([["read-only-observer"], ["developer"]])(
    "hides the button for %s (view keeps working where granted)",
    async (role) => {
      await openIncidentDetail([role]);
      expect(screen.queryByLabelText("Draft as skill")).toBeNull();
    },
  );

  it("hides the button for auditor (the view itself is denied)", async () => {
    useRoles(["auditor"]);
    mockListIncidents.mockResolvedValue({ incidents: [SUMMARY], total: 1 });
    render(<IncidentsView onOpenIncidentSession={() => {}} />);
    expect(
      await screen.findByText(
        "The incidents view requires an incident-visible role.",
      ),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Draft as skill")).toBeNull();
  });

  it("opens the shared preview modal with the generated badge", async () => {
    await openIncidentDetail(["operator"]);
    mockCreateDraft.mockResolvedValue(DRAFT_RESPONSE);
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(mockCreateDraft).toHaveBeenCalledWith("inc-1");
    // Preview first: nothing downloads until the modal's Download .md.
    expect(clickSpy).not.toHaveBeenCalled();
    expect(await screen.findByText("Skill draft preview")).toBeTruthy();
    expect(screen.getByText("generated")).toBeTruthy();
    expect(
      screen.getByText("triage-runbook-checkout-down.md"),
    ).toBeTruthy();
  });

  it("shows the busy state while generation runs", async () => {
    await openIncidentDetail(["operator"]);
    let release: (value: typeof DRAFT_RESPONSE) => void = () => {};
    mockCreateDraft.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    const button = screen.getByLabelText("Draft as skill");
    await act(async () => {
      fireEvent.click(button);
    });
    expect(button.closest("button")?.className).toContain("ant-btn-loading");
    fireEvent.click(button);
    expect(mockCreateDraft).toHaveBeenCalledTimes(1);
    await act(async () => {
      release(DRAFT_RESPONSE);
    });
    expect(button.closest("button")?.className).not.toContain(
      "ant-btn-loading",
    );
  });

  it("maps a 409 to the run-triage-first toast", async () => {
    await openIncidentDetail(["operator"], {
      ...TRIAGED_DETAIL,
      report: null,
      incident: { ...TRIAGED_DETAIL.incident, status: "new" },
    });
    const { ApiError } = await import("../../api/client");
    mockCreateDraft.mockRejectedValue(new ApiError(409, "conflict"));
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(
      await screen.findByText(
        "No validated triage report yet — run triage first, then draft the skill.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Skill draft preview")).toBeNull();
  });

  it("maps a 403 to the role-denial toast", async () => {
    await openIncidentDetail(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockCreateDraft.mockRejectedValue(new ApiError(403, "forbidden"));
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(
      await screen.findByText(
        "Your role cannot draft skills from incidents.",
      ),
    ).toBeTruthy();
  });

  it("maps a 404 to the not-found toast", async () => {
    await openIncidentDetail(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockCreateDraft.mockRejectedValue(new ApiError(404, "not found"));
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(await screen.findByText("Incident not found.")).toBeTruthy();
  });

  it("maps a 503 to the not-configured toast", async () => {
    await openIncidentDetail(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockCreateDraft.mockRejectedValue(new ApiError(503, "unavailable"));
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(
      await screen.findByText("Skill validation is not configured right now."),
    ).toBeTruthy();
  });

  it("maps a 502 to the unreachable toast", async () => {
    await openIncidentDetail(["operator"]);
    const { ApiError } = await import("../../api/client");
    mockCreateDraft.mockRejectedValue(new ApiError(502, "bad gateway"));
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Draft as skill"));
    });
    expect(
      await screen.findByText(
        "Skill validation is unreachable — no draft returned.",
      ),
    ).toBeTruthy();
  });
});
