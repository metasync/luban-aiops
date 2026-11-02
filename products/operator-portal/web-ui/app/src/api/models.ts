// Model catalog API client (SPEC-024 R-4). Discovery is safe by
// construction: the gateway only ever returns id/label/provider/default —
// credentials and base URLs never leave the runtime.
import { requestJson } from "./client";

export interface ModelInfo {
  id: string;
  label: string;
  provider: string;
  default: boolean;
}

export interface ModelCatalogResponse {
  models: ModelInfo[];
  default: string | null;
  // SPEC-072 R-1/R-3: additive — true when per-turn model routing is configured
  // so the selector may offer an "Auto (routed)" choice. Absent on a v0.52.0
  // gateway response; treated as false.
  routing_available?: boolean;
}

// Throws ApiError on any non-2xx; the composer treats every failure as
// "selector hidden, chat still works" (fail-open UX, SPEC-024 D-7).
export async function getModelCatalog(
  signal?: AbortSignal,
): Promise<ModelCatalogResponse> {
  const response = await requestJson<ModelCatalogResponse>("/api/v1/models", {
    signal,
  });
  return {
    models: response.models ?? [],
    default: response.default ?? null,
    routing_available: response.routing_available ?? false,
  };
}
