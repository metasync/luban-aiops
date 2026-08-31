// SPEC-047 Summary tab (R-3…R-6), hardened in v0.29.1: a headline
// statistic row (total + the four SPEC-037 decision-chain steps), the
// four bucket tables in collapsible sections, a one-decimal share
// column per bucket row (the v0.29.0 progress bar wrapped at live
// table widths and was retired on operator review), and drill-down
// from every aggregate value into the Events tab under merged
// filters. Facts only: no prose, no charts, zeros as 0.
import { Button, Col, Collapse, Row, Statistic, Table, Typography, type TableColumnsType } from "antd";

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

// The drill-down target is always one dimension of the shared toolbar
// filters (R-2): the patch merges into them, never resets (Q-3).
export interface DrilldownPatch {
  eventType?: string;
  outcome?: string;
  service?: string;
  username?: string;
}

const DECISION_CHAIN_ORDER = [
  "confirmation_decided",
  "execution_requested",
  "execution_completed",
  "execution_rejected",
] as const;

// One shared formatter (plan.md risk posture): one decimal place,
// deterministic rounding, no per-call inline math. Zero total never
// divides — the panel shows its empty posture instead.
export function sharePercent(count: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((count / total) * 1000) / 10;
}

function sectionTotal(buckets: SummaryBucket[]): number {
  return buckets.reduce((sum, bucket) => sum + bucket.count, 0);
}

function BucketTable({
  buckets,
  total,
  targetFor,
  onDrilldown,
}: {
  buckets: SummaryBucket[];
  total: number;
  targetFor: (name: string) => DrilldownPatch;
  onDrilldown: (patch: DrilldownPatch) => void;
}) {
  const columns: TableColumnsType<SummaryBucket> = [
    {
      title: "name",
      dataIndex: "name",
      render: (name: string) => (
        <Button
          type="link"
          size="small"
          style={{ padding: 0 }}
          aria-label={`Drill into ${name}`}
          onClick={() => onDrilldown(targetFor(name))}
        >
          {name}
        </Button>
      ),
    },
    // v0.29.1: fixed narrow tracks for the two numeric columns so the
    // name column absorbs the width — the share cell is a single
    // right-aligned percentage and can never wrap.
    { title: "count", dataIndex: "count", width: 88, align: "right" },
    {
      title: "share",
      width: 88,
      align: "right",
      render: (_value, bucket) => (
        <Typography.Text type="secondary" style={{ whiteSpace: "nowrap" }}>
          {sharePercent(bucket.count, total).toFixed(1)}%
        </Typography.Text>
      ),
    },
  ];
  return (
    <Table<SummaryBucket>
      size="small"
      tableLayout="fixed"
      rowKey={(bucket) => bucket.name}
      columns={columns}
      dataSource={buckets}
      pagination={false}
    />
  );
}

export default function AuditSummaryPanel({
  summary,
  onDrilldown,
}: {
  summary: AuditSummary;
  onDrilldown: (patch: DrilldownPatch) => void;
}) {
  const total = summary.total_events;

  if (total === 0) {
    // Zero-total guard: empty posture, no division attempted.
    return (
      <Typography.Paragraph>
        <Typography.Text strong>0</Typography.Text> events match the current
        filters.
      </Typography.Paragraph>
    );
  }

  const sections = [
    {
      key: "by_event_type",
      title: "By event type",
      buckets: summary.by_event_type,
      targetFor: (name: string): DrilldownPatch => ({ eventType: name }),
    },
    {
      key: "by_outcome",
      title: "By outcome",
      buckets: summary.by_outcome,
      targetFor: (name: string): DrilldownPatch => ({ outcome: name }),
    },
    {
      key: "by_service",
      title: "By service",
      buckets: summary.by_service,
      targetFor: (name: string): DrilldownPatch => ({ service: name }),
    },
    {
      key: "top_actors",
      title: "Top actors",
      buckets: summary.top_actors,
      targetFor: (name: string): DrilldownPatch => ({ username: name }),
    },
  ];

  return (
    <div data-audit-drilldown>
      {/* R-6 headline statistic row: total + decision chain, zeros as 0.
          Every chain step drills into its own event type (R-3). */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col>
          <Statistic title="Total events" value={total} />
        </Col>
        {DECISION_CHAIN_ORDER.map((step) => (
          <Col key={step}>
            <Button
              type="text"
              style={{ textAlign: "left", height: "auto" }}
              aria-label={`Drill into ${step}`}
              onClick={() => onDrilldown({ eventType: step })}
            >
              <Statistic title={step} value={summary.decision_chain[step]} />
            </Button>
          </Col>
        ))}
      </Row>

      {/* R-5: the four bucket tables fold per render; all expanded by
          default, header = title + section total. */}
      <Collapse
        defaultActiveKey={sections.map((section) => section.key)}
        items={sections.map((section) => ({
          key: section.key,
          label: (
            <span>
              {section.title}{" "}
              <Typography.Text type="secondary">
                ({sectionTotal(section.buckets)})
              </Typography.Text>
            </span>
          ),
          children: (
            <BucketTable
              buckets={section.buckets}
              total={total}
              targetFor={section.targetFor}
              onDrilldown={onDrilldown}
            />
          ),
        }))}
      />
    </div>
  );
}
