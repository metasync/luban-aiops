// Tools catalog view (SPEC-019 R-4, SPEC-023 R-5): the risk-tiered tool
// registry as reported by the tool gateway.
import { useEffect, useState } from "react";
import { Alert, Spin, Table, Typography, type TableColumnsType } from "antd";
import { requestJson } from "../../api/client";

interface CatalogTool {
  name?: string;
  description?: string;
  category?: string;
  risk_level?: string;
}

export default function ToolsView() {
  const [tools, setTools] = useState<CatalogTool[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    requestJson<unknown>("/api/v1/tools", { signal: controller.signal })
      .then((payload) => {
        setTools(Array.isArray(payload) ? (payload as CatalogTool[]) : []);
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
    return <Alert type="error" showIcon title={error} />;
  }

  const columns: TableColumnsType<CatalogTool> = [
    { title: "name", dataIndex: "name", render: (v) => v ?? "—" },
    { title: "description", dataIndex: "description", render: (v) => v ?? "—" },
    { title: "category", dataIndex: "category", render: (v) => v ?? "—" },
    { title: "risk", dataIndex: "risk_level", render: (v) => v ?? "—" },
    {
      // SPEC-021 R-3: non-read tools can never auto-execute — confirmation
      // is mandatory. Read tools follow the agent auto-allow list.
      title: "confirmation",
      render: (_value, tool) =>
        tool.risk_level && tool.risk_level !== "read"
          ? "required"
          : "auto-allow list",
    },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        Tools
      </Typography.Title>
      <Spin spinning={loading}>
        {tools && tools.length === 0 ? (
          <Typography.Text type="secondary">
            No tools are registered in this workspace.
          </Typography.Text>
        ) : null}
        {tools && tools.length > 0 ? (
          <>
            <Table<CatalogTool>
              size="small"
              rowKey={(tool) => tool.name ?? JSON.stringify(tool)}
              columns={columns}
              dataSource={tools}
              pagination={false}
            />
            <Typography.Text type="secondary">
              {tools.length} tool{tools.length === 1 ? "" : "s"} registered ·
              risk-tiered catalog
            </Typography.Text>
          </>
        ) : null}
      </Spin>
    </div>
  );
}
