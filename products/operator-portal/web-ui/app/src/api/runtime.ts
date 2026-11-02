// Runtime feature-flag inventory client (SPEC-072 R-6). The gateway serves
// the curated opt-in flag list behind the authenticated `runtime:flags`
// action, so this call carries the session bearer (requestJson attaches it)
// and throws ApiError on any non-2xx — a 403 for an ungranted role included.
// The inventory is names + booleans only; a flag value is never a secret.
// The Platform pane treats every failure as "flags unavailable" and keeps
// rendering the unauthenticated component-health rows beside it.
import { requestJson } from "./client";

export interface FeatureFlag {
  name: string;
  enabled: boolean;
  // Human-readable caption; the pane falls back to `name` when absent.
  label?: string;
}

export interface RuntimeFlagsResponse {
  feature_flags: FeatureFlag[];
}

// Mirrors getModelCatalog: normalize the envelope so an absent field reads
// as an empty inventory rather than undefined.
export async function getRuntimeFlags(
  signal?: AbortSignal,
): Promise<RuntimeFlagsResponse> {
  const response = await requestJson<RuntimeFlagsResponse>(
    "/api/v1/runtime/flags",
    { signal },
  );
  return { feature_flags: response.feature_flags ?? [] };
}
