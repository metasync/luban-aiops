// Tools catalog view (SPEC-019 R-4, SPEC-023 R-5): the risk-tiered tool
// registry as reported by the tool gateway.  Client-side filters (name,
// category, risk) narrow the table as the catalog grows.
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Input,
  Select,
  Spin,
  Table,
  Typography,
  type TableColumnsType,
} from "antd";
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

  // Client-side filter state.
  const [nameFilter, setNameFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [riskFilter, setRiskFilter] = useState("");

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

  // Derive unique filter options from the loaded catalog.
  const categoryOptions = useMemo(() => {
    if (!tools) return [];
    const unique = [...new Set(tools.map((t) => t.category).filter(Boolean))]
      .sort() as string[];
    return unique.map((c) => ({ value: c, label: c }));
  }, [tools]);

  const riskOptions = useMemo(() => {
    if (!tools) return [];
    const unique = [...new Set(tools.map((t) => t.risk_level).filter(Boolean))]
      .sort() as string[];
    return unique.map((r) => ({ value: r, label: r }));
  }, [tools]);

  // Apply client-side filters.
  const filteredTools = useMemo(() => {
    if (!tools) return null;
    return tools.filter((tool) => {
      if (
        nameFilter.trim() &&
        !(tool.name ?? "").toLowerCase().includes(nameFilter.trim().toLowerCase())
      ) {
        return false;
      }
      if (categoryFilter && tool.category !== categoryFilter) return false;
      if (riskFilter && tool.risk_level !== riskFilter) return false;
      return true;
    });
  }, [tools, nameFilter, categoryFilter, riskFilter]);

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

  const anyFilterActive =
    nameFilter.trim() !== "" || categoryFilter !== "" || riskFilter !== "";

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        Tools
      </Typography.Title>
      <div className="view-toolbar">
        <Input
          placeholder="search name"
          value={nameFilter}
          onChange={(event) => setNameFilter(event.target.value)}
          style={{ width: 180 }}
          aria-label="Filter by name"
          allowClear
        />
        <Select
          value={categoryFilter}
          onChange={(value) => setCategoryFilter(value)}
          style={{ width: 180 }}
          aria-label="Filter by category"
          options={[
            { value: "", label: "all categories" },
            ...categoryOptions,
          ]}
        />
        <Select
          value={riskFilter}
          onChange={(value) => setRiskFilter(value)}
          style={{ width: 160 }}
          aria-label="Filter by risk level"
          options={[
            { value: "", label: "all risk levels" },
            ...riskOptions,
          ]}
        />
      </div>
      <Spin spinning={loading}>
        {filteredTools && filteredTools.length === 0 ? (
          <Typography.Text type="secondary">
            {tools && tools.length === 0
              ? "No tools are registered in this workspace."
              : "No tools match the current filters."}
          </Typography.Text>
        ) : null}
        {filteredTools && filteredTools.length > 0 ? (
          <>
            <Table<CatalogTool>
              size="small"
              rowKey={(tool) => tool.name ?? JSON.stringify(tool)}
              columns={columns}
              dataSource={filteredTools}
              pagination={false}
            />
            <Typography.Text type="secondary">
              {anyFilterActive
                ? `${filteredTools.length} of ${tools!.length} tool${tools!.length === 1 ? "" : "s"} shown`
                : `${filteredTools.length} tool${filteredTools.length === 1 ? "" : "s"} registered`}{" "}
              · risk-tiered catalog
            </Typography.Text>
          </>
        ) : null}
      </Spin>
    </div>
  );
}
