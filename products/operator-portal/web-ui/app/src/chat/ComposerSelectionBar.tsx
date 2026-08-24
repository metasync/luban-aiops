// Composer selection bar — the extensible control strip rendered under
// the message input (the Sender footer slot). Hosts the SPEC-024 model
// selector today and is the designated mount point for future per-turn
// selections; it collapses entirely when there is nothing to select.
import { Typography } from "antd";
import type { ModelCatalogResponse } from "../api/models";
import { ModelSelect } from "./ModelSelect";

export interface ComposerSelectionBarProps {
  catalog: ModelCatalogResponse | null;
  model: string | null;
  onModelChange: (modelId: string) => void;
  disabled?: boolean;
}

export function ComposerSelectionBar({
  catalog,
  model,
  onModelChange,
  disabled,
}: ComposerSelectionBarProps) {
  if (!catalog || catalog.models.length === 0) {
    // Catalog fetch failed or the runtime has no configured model: the
    // bar collapses so the composer keeps its compact shape; turns keep
    // resolving to the deploy-time default server-side.
    return null;
  }
  return (
    <div className="composer-selection-bar">
      <div className="composer-selection-item">
        <Typography.Text
          type="secondary"
          className="composer-selection-label"
        >
          Model
        </Typography.Text>
        <ModelSelect
          catalog={catalog}
          value={model}
          onChange={onModelChange}
          disabled={disabled}
        />
      </div>
      {/* Future per-turn selections mount here as further items. */}
    </div>
  );
}
