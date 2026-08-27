// Operations document repository API client (SPEC-039 R-6 surface).
// All shapes mirror operation-document.schema.json via the gateway.
import { requestJson } from "./client";

export type DocumentType = "shift_summary";
export type DocumentState = "draft" | "published";
export type ProseStatus = "included" | "failed" | "not_requested";

export interface DocumentProvenanceSession {
  session_id: string;
  coverage: "owner" | "foreign";
  cited_record_ids: string[];
}

// The digest is a typed-but-open object: the shift-summary builder owns
// its section shapes, and the view renders whatever arrives per entry.
export interface OperationDocument {
  document_id: string;
  document_type: DocumentType;
  state: DocumentState;
  owner_user_id: string;
  label: string;
  created_at: string;
  published_at?: string | null;
  provenance: { sessions: DocumentProvenanceSession[] };
  digest: Record<string, unknown>;
  prose?: string | null;
  prose_status: ProseStatus;
}

export interface DocumentListResponse {
  documents: OperationDocument[];
}

export interface DocumentCreateRequest {
  document_type: DocumentType;
  session_ids: string[];
  label: string;
  include_prose: boolean;
}

export async function listDocuments(
  scope: "mine" | "published",
  signal?: AbortSignal,
): Promise<OperationDocument[]> {
  const response = await requestJson<DocumentListResponse>(
    `/api/v1/documents?scope=${scope}`,
    { signal },
  );
  return response.documents ?? [];
}

export async function getDocument(
  documentId: string,
  signal?: AbortSignal,
): Promise<OperationDocument> {
  return requestJson<OperationDocument>(
    `/api/v1/documents/${encodeURIComponent(documentId)}`,
    { signal },
  );
}

// Throws ApiError 400 (validation / unknown session ids), 403 (foreign
// sessions without approvals:list coverage), or 502 (agent outage).
export async function createDocument(
  payload: DocumentCreateRequest,
): Promise<OperationDocument> {
  return requestJson<OperationDocument>("/api/v1/documents", {
    method: "POST",
    body: payload,
  });
}

// One-way: repeat publishing answers ApiError 409.
export async function publishDocument(
  documentId: string,
): Promise<OperationDocument> {
  return requestJson<OperationDocument>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/publish`,
    { method: "POST" },
  );
}

export async function deleteDocument(documentId: string): Promise<void> {
  await requestJson(`/api/v1/documents/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
  });
}
