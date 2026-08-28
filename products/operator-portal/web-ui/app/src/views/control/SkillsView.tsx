// Skills inventory view (SPEC-019 R-4, SPEC-023 R-5): the skills-hub
// inventory with source/tag filters.
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Input,
  Spin,
  Table,
  Typography,
  type TableColumnsType,
} from "antd";
import { requestJson } from "../../api/client";
import { formatTimestamp } from "../format";

interface SkillRecord {
  skill_id: string;
  title?: string;
  source_id?: string;
  tags?: string[];
  version?: string;
  updated_at?: string;
}

interface SkillsPayload {
  skills: SkillRecord[];
  total: number;
}

export default function SkillsView() {
  const [source, setSource] = useState("");
  const [tag, setTag] = useState("");
  const [payload, setPayload] = useState<SkillsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (sourceFilter: string, tagFilter: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (sourceFilter.trim()) params.set("source", sourceFilter.trim());
      if (tagFilter.trim()) params.set("tag", tagFilter.trim());
      const result = await requestJson<SkillsPayload>(
        `/api/v1/skills?${params.toString()}`,
      );
      setPayload({ skills: result.skills ?? [], total: result.total ?? 0 });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load("", "");
  }, [load]);

  const skills = payload?.skills ?? [];
  const total = payload?.total ?? 0;

  const columns: TableColumnsType<SkillRecord> = [
    {
      title: "title",
      render: (_value, skill) => skill.title || skill.skill_id,
    },
    { title: "source", dataIndex: "source_id", render: (v) => v ?? "—" },
    {
      title: "tags",
      render: (_value, skill) => (skill.tags ?? []).join(", ") || "—",
    },
    { title: "version", dataIndex: "version", render: (v) => v ?? "—" },
    {
      title: "updated",
      dataIndex: "updated_at",
      render: (value: string) => formatTimestamp(value),
    },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        Skills
      </Typography.Title>
      <div className="view-toolbar">
        <Input
          placeholder="source"
          value={source}
          onChange={(event) => setSource(event.target.value)}
          onPressEnter={() => void load(source, tag)}
          style={{ width: 180 }}
          aria-label="Filter by source"
        />
        <Input
          placeholder="tag"
          value={tag}
          onChange={(event) => setTag(event.target.value)}
          onPressEnter={() => void load(source, tag)}
          style={{ width: 180 }}
          aria-label="Filter by tag"
        />
        <Button onClick={() => void load(source, tag)}>Apply</Button>
      </div>
      {error ? (
        <Alert type="error" showIcon title={error} style={{ marginBottom: 12 }} />
      ) : null}
      <Spin spinning={loading}>
        {payload && skills.length === 0 ? (
          <Typography.Text type="secondary">
            No skills match these filters.
          </Typography.Text>
        ) : null}
        {payload && skills.length > 0 ? (
          <>
            <Table<SkillRecord>
              size="small"
              rowKey="skill_id"
              columns={columns}
              dataSource={skills}
              pagination={false}
            />
            <Typography.Text type="secondary">
              {skills.length} skill{skills.length === 1 ? "" : "s"} shown ·{" "}
              {total} total
            </Typography.Text>
          </>
        ) : null}
      </Spin>
    </div>
  );
}
