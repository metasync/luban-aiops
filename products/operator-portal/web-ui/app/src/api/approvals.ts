// Approvals inbox API client (SPEC-031 R-3 surface, consumed per R-5).
// Metadata only — the inbox never carries owner transcript text
// (SPEC-030 Q-1 posture); the gateway re-enforces approvals:list.
// SPEC-036 R-5: the pending queue arrives complete while the resolved
// history pages server-side (offset + total).
import { requestJson } from "./client";
import type { ConfirmationRecord } from "./sessions";

export interface ApprovalsInboxResponse {
  confirmations: ConfirmationRecord[];
  history: ConfirmationRecord[];
  history_total: number;
}

export interface ApprovalsInboxQuery {
  historyLimit?: number;
  historyOffset?: number;
  signal?: AbortSignal;
}

export async function getApprovalsInbox(
  query: ApprovalsInboxQuery = {},
): Promise<ApprovalsInboxResponse> {
  const params = new URLSearchParams({
    history_limit: String(query.historyLimit ?? 10),
    history_offset: String(query.historyOffset ?? 0),
  });
  const response = await requestJson<ApprovalsInboxResponse>(
    `/api/v1/approvals/inbox?${params.toString()}`,
    { signal: query.signal },
  );
  return {
    confirmations: response.confirmations ?? [],
    history: response.history ?? [],
    history_total: response.history_total ?? 0,
  };
}
