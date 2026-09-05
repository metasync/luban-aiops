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
import {
  SkillContentViewer,
  type SkillDetail,
} from "../../chat/SkillContentViewer";

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
  // SPEC-052 R-2: the skill whose full record is open in the viewer, and the
  // row currently fetching its detail. The body is fetched lazily, only when
  // View is invoked — the list payload omits it by contract.
  const [viewing, setViewing] = useState<SkillDetail | null>(null);
  const [viewLoadingId, setViewLoadingId] = useState<string | null>(null);

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

  // SPEC-052 R-2: fetch one skill's full record (the list omits body by
  // contract) only when View is invoked. The namespaced id keeps its slashes
  // for the gateway's {skill_id:path} proxy; each segment is percent-encoded.
  const openSkill = useCallback(async (skillId: string) => {
    setViewLoadingId(skillId);
    setError(null);
    try {
      const encoded = skillId.split("/").map(encodeURIComponent).join("/");
      const detail = await requestJson<SkillDetail>(`/api/v1/skills/${encoded}`);
      setViewing(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setViewLoadingId(null);
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
    {
      // SPEC-052 R-2: open the read-only content viewer for this skill.
      title: "",
      key: "actions",
      render: (_value, skill) => (
        <Button
          size="small"
          loading={viewLoadingId === skill.skill_id}
          aria-label={`View ${skill.title || skill.skill_id}`}
          onClick={() => void openSkill(skill.skill_id)}
        >
          View
        </Button>
      ),
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
      {/* SPEC-052 R-3: read-only rendered/raw viewer for the opened skill. */}
      <SkillContentViewer skill={viewing} onClose={() => setViewing(null)} />
    </div>
  );
}
