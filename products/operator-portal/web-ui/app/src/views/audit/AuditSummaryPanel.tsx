// Summary tab renderer (SPEC-046 R-5): deterministic envelope-column
// aggregates from GET /api/v1/audit/summary — a total line, the
// type/outcome/service bucket tables, the top-actors table, and the
// SPEC-037 decision-chain strip. Facts only: no prose, no charts.
import { Table, Typography, type TableColumnsType } from "antd";

export interface SummaryBucket {
  name: string;
  count: number;
}

export interface AuditSummary {
  total_events: number;
  window: Record<string, string>;
  by_event_type: SummaryBucket[];
  by_outcome: SummaryBucket[];
  by_service: SummaryBucket[];
  top_actors: SummaryBucket[];
  decision_chain: {
    confirmation_decided: number;
    execution_requested: number;
    execution_completed: number;
    execution_rejected: number;
  };
}

const BUCKET_COLUMNS: TableColumnsType<SummaryBucket> = [
  { title: "name", dataIndex: "name" },
  { title: "count", dataIndex: "count" },
];

function BucketTable({ buckets }: { buckets: SummaryBucket[] }) {
  return (
    <Table<SummaryBucket>
      size="small"
      rowKey={(bucket) => bucket.name}
      columns={BUCKET_COLUMNS}
      dataSource={buckets}
      pagination={false}
    />
  );
}

const DECISION_CHAIN_ORDER = [
  "confirmation_decided",
  "execution_requested",
  "execution_completed",
  "execution_rejected",
] as const;

export default function AuditSummaryPanel({
  summary,
}: {
  summary: AuditSummary;
}) {
  return (
    <div>
      <Typography.Paragraph>
        <Typography.Text strong>{summary.total_events}</Typography.Text>{" "}
        event{summary.total_events === 1 ? "" : "s"} match the current
        filters.
      </Typography.Paragraph>

      {/* SPEC-037 lineage strip: decision → request → terminal outcome.
          Zeros render as 0 — an absent event type is a fact, not an
          error. */}
      <Typography.Title level={5}>Decision chain</Typography.Title>
      <div className="view-toolbar" style={{ flexWrap: "wrap" }}>
        {DECISION_CHAIN_ORDER.map((step, index) => (
          <span key={step} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            {index > 0 ? (
              <Typography.Text type="secondary" aria-hidden>
                →
              </Typography.Text>
            ) : null}
            <span>
              <Typography.Text code>{step}</Typography.Text>{" "}
              <Typography.Text strong>
                {summary.decision_chain[step]}
              </Typography.Text>
            </span>
          </span>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
        <section>
          <Typography.Title level={5}>By event type</Typography.Title>
          <BucketTable buckets={summary.by_event_type} />
        </section>
        <section>
          <Typography.Title level={5}>By outcome</Typography.Title>
          <BucketTable buckets={summary.by_outcome} />
        </section>
        <section>
          <Typography.Title level={5}>By service</Typography.Title>
          <BucketTable buckets={summary.by_service} />
        </section>
        <section>
          <Typography.Title level={5}>Top actors</Typography.Title>
          <BucketTable buckets={summary.top_actors} />
        </section>
      </div>
    </div>
  );
}
