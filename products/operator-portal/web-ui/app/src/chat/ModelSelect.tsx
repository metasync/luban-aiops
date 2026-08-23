// Model selector for the chat composer (SPEC-024 R-4, D-7).
//
// Renders from the credential-gated catalog fetched via GET
// /api/v1/models: an antd Select with the deploy-time default
// pre-selected, a fixed label when exactly one model is configured, and
// nothing at all when the catalog is unavailable (endpoint error or an
// unconfigured runtime) — chat keeps working either way.
import { Select, Typography } from "antd";
import type { ModelCatalogResponse } from "../api/models";

export interface ModelSelectProps {
  catalog: ModelCatalogResponse | null;
  value: string | null;
  onChange: (modelId: string) => void;
  disabled?: boolean;
}

export function ModelSelect({
  catalog,
  value,
  onChange,
  disabled,
}: ModelSelectProps) {
  if (!catalog || catalog.models.length === 0) {
    // Fetch failed or the runtime has no configured model: the selector
    // hides and turns resolve server-side to the deploy-time default.
    return null;
  }
  if (catalog.models.length === 1) {
    // Nothing to choose: show the single serving model as a fixed label.
    return (
      <Typography.Text
        type="secondary"
        className="model-fixed-label"
        aria-label="Model"
      >
        {catalog.models[0].label}
      </Typography.Text>
    );
  }
  const known = catalog.models.some((entry) => entry.id === value);
  return (
    <Select
      size="small"
      variant="borderless"
      aria-label="Model"
      value={known && value ? value : catalog.models[0].id}
      onChange={onChange}
      disabled={disabled}
      options={catalog.models.map((entry) => ({
        value: entry.id,
        label: entry.label,
      }))}
      popupMatchSelectWidth={false}
    />
  );
}
