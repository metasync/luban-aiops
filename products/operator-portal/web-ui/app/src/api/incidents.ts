// Incident intake/triage API client (SPEC-015 surface, consumed per
// SPEC-023 R-5). Shapes mirror the incident-service gateway contracts.
import { requestJson } from "./client";

export interface IncidentSummary {
  incident_id: string;
  title: string;
  severity: string;
  status: string;
  source: string;
  created_at: string;
}

export interface IncidentListResponse {
  incidents: IncidentSummary[];
  total: number;
}

export interface TriageEvidenceRef {
  source: string;
  description: string;
}

export interface TriageNextStep {
  title: string;
  priority: string;
  rationale: string;
}

export interface TriageReport {
  severity_assessment: string;
  generated_by: string;
  generated_at: string;
  session_id: string;
  summary: string;
  evidence?: TriageEvidenceRef[];
  hypotheses?: string[];
  next_steps?: TriageNextStep[];
  skills_cited?: string[];
}

export interface ConnectorDispatch {
  connector: string;
  status: string;
  reference?: string | null;
  error?: string | null;
  created_at: string;
}

export interface IncidentDetailRecord extends IncidentSummary {
  fingerprint: string;
  updated_at: string;
  reported_by?: string | null;
  resolved_at?: string | null;
  labels?: Record<string, string>;
  summary?: string | null;
  session_id?: string | null;
  triage_raw?: string | null;
}

export interface IncidentDetailPayload {
  incident: IncidentDetailRecord;
  report: TriageReport | null;
  dispatches: ConnectorDispatch[];
}

export interface IncidentFilters {
  status?: string;
  severity?: string;
  source?: string;
}

export async function listIncidents(
  filters: IncidentFilters,
  signal?: AbortSignal,
): Promise<IncidentListResponse> {
  const params = new URLSearchParams({ limit: "50" });
  if (filters.status) params.set("status", filters.status);
  if (filters.severity) params.set("severity", filters.severity);
  if (filters.source) params.set("source", filters.source);
  return requestJson<IncidentListResponse>(
    `/api/v1/incidents?${params.toString()}`,
    { signal },
  );
}

export async function getIncident(
  incidentId: string,
  signal?: AbortSignal,
): Promise<IncidentDetailPayload> {
  return requestJson<IncidentDetailPayload>(
    `/api/v1/incidents/${encodeURIComponent(incidentId)}`,
    { signal },
  );
}

// Blocks until the agent turn and connector dispatches complete; callers
// keep the trigger disabled while in flight (legacy parity).
export async function runTriage(
  incidentId: string,
): Promise<IncidentDetailPayload> {
  return requestJson<IncidentDetailPayload>(
    `/api/v1/incidents/${encodeURIComponent(incidentId)}/triage`,
    { method: "POST" },
  );
}

export interface IncidentReportInput {
  title: string;
  summary: string;
  severity: string;
  labels: Record<string, string>;
}

export async function reportIncident(
  input: IncidentReportInput,
): Promise<IncidentSummary> {
  return requestJson<IncidentSummary>("/api/v1/incidents", {
    method: "POST",
    body: input,
  });
}
