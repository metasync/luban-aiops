// Permissions matrix view (SPEC-019 R-3, SPEC-023 R-5): renders the live
// role × action matrix from the gateway's policy matrix endpoint. Rows
// arrive scoped server-side; the view displays them verbatim. Sign-in
// gated in the sidebar; the gateway re-enforces policy:read per request.
import { useEffect, useState } from "react";
import { Alert, Spin, Table, Tag, Typography } from "antd";
import { requestJson } from "../../api/client";

interface PolicyMatrixPayload {
  version: string;
  source: string;
  scope: string;
  actions: string[];
  roles: string[];
  matrix: Record<string, Record<string, boolean>>;
}

export default function PermissionsView() {
  const [payload, setPayload] = useState<PolicyMatrixPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    requestJson<PolicyMatrixPayload>("/api/v1/policy/matrix", {
      signal: controller.signal,
    })
      .then((result) => {
        setPayload(result);
        setError(null);
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  if (error) {
    return <Alert type="error" showIcon message={error} />;
  }

  const actions = payload?.actions ?? [];
  const roles = payload?.roles ?? [];

  const columns = [
    { title: "role", dataIndex: "role", key: "role", fixed: "left" as const },
    ...actions.map((action) => ({
      title: action,
      key: action,
      render: (_: unknown, row: { role: string }) => {
        const allowed = Boolean(payload?.matrix?.[row.role]?.[action]);
        return (
          <Tag color={allowed ? "success" : "error"}>
            {allowed ? "allow" : "deny"}
          </Tag>
        );
      },
    })),
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        Permissions
      </Typography.Title>
      {payload ? (
        <Typography.Paragraph type="secondary">
          Policy bundle v{payload.version} · {payload.source} · scope:{" "}
          {payload.scope}
        </Typography.Paragraph>
      ) : null}
      <Spin spinning={loading}>
        {payload ? (
          <Table
            size="small"
            rowKey="role"
            columns={columns}
            dataSource={roles.map((role) => ({ role }))}
            pagination={false}
            scroll={{ x: "max-content" }}
          />
        ) : null}
      </Spin>
      {payload ? (
        <Typography.Text type="secondary">
          {roles.length} role{roles.length === 1 ? "" : "s"} ×{" "}
          {actions.length} actions · evaluated from the enforced bundle
        </Typography.Text>
      ) : null}
    </div>
  );
}
