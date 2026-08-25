// Approvals inbox API client (SPEC-031 R-3 surface, consumed per R-5).
// Metadata only — the inbox never carries owner transcript text
// (SPEC-030 Q-1 posture); the gateway re-enforces approvals:list.
import { requestJson } from "./client";
import type { ConfirmationRecord } from "./sessions";

export interface ApprovalsInboxResponse {
  confirmations: ConfirmationRecord[];
}

export async function getApprovalsInbox(
  signal?: AbortSignal,
): Promise<ConfirmationRecord[]> {
  const response = await requestJson<ApprovalsInboxResponse>(
    "/api/v1/approvals/inbox",
    { signal },
  );
  return response.confirmations ?? [];
}
