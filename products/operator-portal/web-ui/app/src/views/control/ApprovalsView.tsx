// Approvals inbox view (SPEC-031 R-5): the designated approver's
// cross-session queue of parked confirmations plus the 30-day decision
// history. Reuses ConfirmationCardView so inbox cards render identically
// to the owner-transcript cards; decisions ride the same POST
// /api/v1/chat/confirm surface the chat uses, with the structured
// already_resolved 409 flipping the card to the winner's outcome.
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Pagination, Spin, Tabs, Tag, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { getApprovalsInbox } from "../../api/approvals";
import type { ConfirmationRecord } from "../../api/sessions";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmationCardView } from "../../chat/ChatView";
import { confirmationRecordToCard } from "../../chat/transcript";
import { CHAT_CONFIRM_ROLES, hasAnyRole } from "../../roles";
import {
  StreamOpenError,
  alreadyResolvedDetail,
  consumeStream,
  openStream,
} from "../../stream/transport";
import type { ConfirmationDecision } from "../../stream/useChatStream";

dayjs.extend(relativeTime);

const POLL_INTERVAL_MS = 30_000;

// SPEC-035 R-7: entries per page in the History tab.
const HISTORY_PAGE_SIZE = 10;

function recordStatus(raw: string | undefined): ConfirmationRecord["status"] | undefined {
  return raw === "pending" ||
    raw === "approved" ||
    raw === "denied" ||
    raw === "expired"
    ? raw
    : undefined;
}

export interface ApprovalsInboxState {
  records: ConfirmationRecord[];
  loading: boolean;
  error: string | null;
  pendingCount: number;
  busyConfirmId: string | null;
  refresh: () => Promise<void>;
  decide: (confirmId: string, decision: ConfirmationDecision) => Promise<void>;
}

// One inbox per signed-in decider: App owns the hook so the sidebar
// badge and the view share a single poll (30s + window focus), and a
// decision made in either surface stays consistent.
//
// SPEC-034 R-2: onDecisionApplied fires the moment a decision becomes
// true (successful decide or a 409 race patch) so App can refresh the
// session panel immediately instead of at the next 30s poll tick.
export function useApprovalsInbox(
  enabled: boolean,
  onDecisionApplied?: () => void,
): ApprovalsInboxState {
  const { username } = useAuth();
  const [records, setRecords] = useState<ConfirmationRecord[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [busyConfirmId, setBusyConfirmId] = useState<string | null>(null);
  const recordsRef = useRef<ConfirmationRecord[]>([]);
  recordsRef.current = records;
  const loadedOnceRef = useRef(false);
  const decisionAppliedRef = useRef(onDecisionApplied);
  decisionAppliedRef.current = onDecisionApplied;

  const refresh = useCallback(async () => {
    try {
      const items = await getApprovalsInbox();
      setRecords(items);
      setError(null);
    } catch (err) {
      // Keep the last good list on transient failures; a transport
      // error can never mean "inbox empty" (gateway maps that to 502).
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      loadedOnceRef.current = true;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setRecords([]);
      setLoading(false);
      return;
    }
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [enabled, refresh]);

  const patchRecord = useCallback(
    (confirmId: string, patch: Partial<ConfirmationRecord>) => {
      setRecords((current) =>
        current.map((record) =>
          record.confirm_id === confirmId ? { ...record, ...patch } : record,
        ),
      );
    },
    [],
  );

  const decide = useCallback(
    async (confirmId: string, decision: ConfirmationDecision) => {
      const record = recordsRef.current.find(
        (entry) =>
          entry.confirm_id === confirmId && entry.status === "pending",
      );
      if (!record || busyConfirmId) return;
      setBusyConfirmId(confirmId);
      try {
        const opened = await openStream("/api/v1/chat/confirm", {
          method: "POST",
          body: {
            session_id: record.session_id,
            confirm_id: confirmId,
            decision,
          },
        });
        // The response is the owner's resumed stream; the inbox only
        // needs the confirmation_result outcome (deltas are ignored).
        let outcome: string | undefined;
        await consumeStream(opened.chunks, (event) => {
          const frame = event.frame;
          if (frame && frame.kind === "confirmation_result") {
            outcome = frame.status;
          }
        });
        patchRecord(confirmId, {
          status:
            recordStatus(outcome) && recordStatus(outcome) !== "pending"
              ? (recordStatus(outcome) as ConfirmationRecord["status"])
              : decision === "approve"
                ? "approved"
                : "denied",
          decider_user_id: username ?? null,
          decision,
          decided_at: new Date().toISOString(),
        });
        decisionAppliedRef.current?.();
        // Resync with the durable store so attribution and ordering
        // follow the server's truth once it settles.
        void refresh();
      } catch (err) {
        if (err instanceof StreamOpenError && err.status === 409) {
          // SPEC-031 R-4 race: another decider won. Flip the card to
          // the winner's outcome instead of leaving a doomed retry.
          const race = alreadyResolvedDetail(err.detail);
          if (race) {
            patchRecord(confirmId, {
              status: recordStatus(race.status) ?? "expired",
              decider_user_id: race.decider_user_id ?? null,
              decision: race.decision ?? null,
              decided_at: race.decided_at ?? null,
            });
            decisionAppliedRef.current?.();
          } else {
            setError(`Confirm request failed (409).`);
          }
        } else if (err instanceof StreamOpenError && err.status === 410) {
          patchRecord(confirmId, { status: "expired" });
        } else if (err instanceof StreamOpenError && err.status === 401) {
          setError("Not authenticated. Please sign in from the sidebar first.");
        } else if (!(err instanceof Error && err.name === "AbortError")) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        setBusyConfirmId(null);
      }
    },
    [busyConfirmId, patchRecord, refresh, username],
  );

  return {
    records,
    loading: loading && !loadedOnceRef.current,
    error,
    pendingCount: records.filter((record) => record.status === "pending")
      .length,
    busyConfirmId,
    refresh,
    decide,
  };
}

// One inbox entry: a separated card with a structured provenance header
// (SPEC-034 R-4) above the shared confirmation card. Metadata only —
// SPEC-030 Q-1.
function InboxEntry({
  record,
  inbox,
  canDecide,
}: {
  record: ConfirmationRecord;
  inbox: ApprovalsInboxState;
  canDecide: boolean;
}) {
  const decided = record.status !== "pending";
  return (
    <div className="approvals-entry">
      <div className="approvals-entry-header">
        <div className="approvals-entry-title">
          <Typography.Text strong ellipsis>
            {record.session_title ?? record.session_id}
          </Typography.Text>
          {decided ? (
            <Tag
              color={
                record.status === "approved"
                  ? "success"
                  : record.status === "denied"
                    ? "error"
                    : "default"
              }
            >
              {record.status}
            </Tag>
          ) : null}
        </div>
        <div className="approvals-entry-sub">
          <span>owner: {record.owner_user_id}</span>
          {record.parked_at ? (
            <span>parked {dayjs(record.parked_at).fromNow()}</span>
          ) : null}
          {decided && record.decided_at ? (
            <span>
              decided {dayjs(record.decided_at).fromNow()}
              {record.decider_user_id ? ` by ${record.decider_user_id}` : ""}
            </span>
          ) : null}
        </div>
      </div>
      <ConfirmationCardView
        card={confirmationRecordToCard(record)}
        canDecide={canDecide && record.status === "pending"}
        busy={inbox.busyConfirmId === record.confirm_id}
        onDecide={(confirmId, decision) => void inbox.decide(confirmId, decision)}
      />
    </div>
  );
}

export default function ApprovalsView({
  inbox,
}: {
  inbox: ApprovalsInboxState;
}) {
  const { roles } = useAuth();
  const canDecide = hasAnyRole(roles, CHAT_CONFIRM_ROLES);
  const pending = inbox.records.filter((record) => record.status === "pending");
  const history = inbox.records.filter(
    (record) => record.status !== "pending",
  );
  // SPEC-035 R-7: the 30-day decision history is paginated client-side —
  // the server already caps the payload, this only keeps the tab legible
  // as the record count grows. The page clamps when the list shrinks
  // (e.g. retention eviction lands on a refresh).
  const [historyPage, setHistoryPage] = useState(1);
  const historyPages = Math.max(1, Math.ceil(history.length / HISTORY_PAGE_SIZE));
  const clampedPage = Math.min(historyPage, historyPages);
  const historySlice = history.slice(
    (clampedPage - 1) * HISTORY_PAGE_SIZE,
    clampedPage * HISTORY_PAGE_SIZE,
  );

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <Typography.Title level={4} style={{ margin: 0 }}>
          Approvals
        </Typography.Title>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={() => void inbox.refresh()}
          aria-label="Refresh inbox"
        >
          Refresh
        </Button>
      </div>
      {/* SPEC-035 R-6: the info banner sits on its own line under the
          title row instead of crowding it. The timeout is
          AGENT_HITL_CONFIRM_TIMEOUT (600s default). */}
      <Typography.Text
        type="secondary"
        style={{ display: "block", margin: "4px 0 12px" }}
      >
        Pending confirmations park here until decided — unanswered
        requests expire after the confirmation timeout (10 minutes by
        default). History keeps decisions for 30 days.
      </Typography.Text>
      {inbox.error ? (
        <Alert
          type="warning"
          showIcon
          message={inbox.error}
          style={{ marginBottom: 12 }}
        />
      ) : null}
      <Spin spinning={inbox.loading}>
        {/* SPEC-034 R-3: Pending is the actionable queue and the default
            tab; History holds decided records out of the way. */}
        <Tabs
          defaultActiveKey="pending"
          items={[
            {
              key: "pending",
              label: `Pending (${pending.length})`,
              children:
                pending.length === 0 ? (
                  <div style={{ padding: "8px 0" }}>
                    <Typography.Text type="secondary">
                      No confirmations are waiting for a decision.
                    </Typography.Text>
                  </div>
                ) : (
                  pending.map((record) => (
                    <InboxEntry
                      key={record.confirm_id}
                      record={record}
                      inbox={inbox}
                      canDecide={canDecide}
                    />
                  ))
                ),
            },
            {
              key: "history",
              label: `History (${history.length})`,
              children:
                history.length === 0 ? (
                  <div style={{ padding: "8px 0" }}>
                    <Typography.Text type="secondary">
                      No decisions in the last 30 days.
                    </Typography.Text>
                  </div>
                ) : (
                  <>
                    {historySlice.map((record) => (
                      <InboxEntry
                        key={record.confirm_id}
                        record={record}
                        inbox={inbox}
                        canDecide={canDecide}
                      />
                    ))}
                    {historyPages > 1 ? (
                      <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <Pagination
                          size="small"
                          current={clampedPage}
                          pageSize={HISTORY_PAGE_SIZE}
                          total={history.length}
                          showSizeChanger={false}
                          onChange={(page) => setHistoryPage(page)}
                          aria-label="Decision history pages"
                        />
                      </div>
                    ) : null}
                  </>
                ),
            },
          ]}
        />
      </Spin>
    </div>
  );
}
