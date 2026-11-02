// Model selector for the chat composer (SPEC-024 R-4, D-7; SPEC-026 R-2).
//
// Renders from the credential-gated catalog fetched via GET
// /api/v1/models: an antd Select with the deploy-time default
// pre-selected, options grouped by provider (each provider now exposes
// its full model series), a fixed label when exactly one model is
// configured, and nothing at all when the catalog is unavailable
// (endpoint error or an unconfigured runtime) — chat keeps working
// either way.
import { Select, Typography } from "antd";
import type { ModelCatalogResponse } from "../api/models";

// SPEC-072 R-3: the reserved sentinel the runtime resolves as "route this turn"
// (never a catalog model id), rendered as a first-class "Auto (routed)" choice
// in its own group at the top of the dropdown when routing is available.
const AUTO_MODEL_ID = "auto";
const AUTO_OPTION_LABEL = "Auto (routed)";
const AUTO_GROUP_LABEL = "routing";

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
  // SPEC-072 R-3: "Auto (routed)" is a first-class choice whenever the catalog
  // reports routing is available; when it is not, the component is unchanged.
  const routingAvailable = catalog.routing_available === true;
  if (catalog.models.length === 1 && !routingAvailable) {
    // Nothing to choose: show the single serving model as a fixed label. With
    // routing available there are two choices (the model + Auto), so fall
    // through to the dropdown instead of the fixed label.
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
  const fallback =
    catalog.models.find((entry) => entry.default) ?? catalog.models[0];
  // A pinned "auto" is a known value only while routing is available.
  const known =
    catalog.models.some((entry) => entry.id === value) ||
    (routingAvailable && value === AUTO_MODEL_ID);
  // Group the series by provider, preserving catalog order, with the Auto group
  // pinned at the top when routing is available.
  const groups: {
    label: string;
    options: { value: string; label: string }[];
  }[] = [];
  if (routingAvailable) {
    groups.push({
      label: AUTO_GROUP_LABEL,
      options: [{ value: AUTO_MODEL_ID, label: AUTO_OPTION_LABEL }],
    });
  }
  for (const entry of catalog.models) {
    let group = groups.find((g) => g.label === entry.provider);
    if (!group) {
      group = { label: entry.provider, options: [] };
      groups.push(group);
    }
    group.options.push({ value: entry.id, label: entry.label });
  }
  return (
    <Select
      size="small"
      variant="borderless"
      aria-label="Model"
      value={known && value ? value : fallback.id}
      onChange={onChange}
      disabled={disabled}
      options={groups}
      popupMatchSelectWidth={false}
    />
  );
}
