// Display-name alignment for gateway tools (v0.27.4, broadened in v0.27.5):
// the model writes the sanitized tool names it sees in its function-calling
// schema (dots become underscores to satisfy provider name constraints),
// but the registry's canonical name is dotted. Every rendered surface —
// prose, inline code spans, fenced blocks — maps sanitized names back to
// the dotted canonical form at render time. Copy-paste stays safe: the
// sanitized form has no external consumer besides the model schema, and the
// one configuration surface that lists tool names
// (AGENT_GATEWAY_TOOL_AUTO_ALLOW) normalizes dots to underscores on input.
// The durable transcript keeps the model's original words, so the rewrite
// re-applies to historical sessions on re-render with no migration.

/** AgentScope sanitizes tool names for function-calling: dots become underscores. */
export function sanitizeToolName(canonical: string): string {
  return canonical.replace(/\./g, "_");
}

/**
 * Build a sanitized-name → dotted-canonical-name map from the tool catalog.
 *
 * Names without dots sanitize to themselves (nothing to map). A sanitized
 * collision (two canonical names flattening to the same string) cannot
 * happen while function-calling requires unique names; if one ever appears
 * the map skips the ambiguous entry rather than guessing.
 */
export function canonicalToolNames(
  catalog: Array<{ name?: unknown }>,
): Map<string, string> {
  const map = new Map<string, string>();
  const skipped = new Set<string>();
  for (const tool of catalog) {
    const canonical = typeof tool.name === "string" ? tool.name : "";
    if (!canonical.includes(".")) continue;
    const sanitized = sanitizeToolName(canonical);
    if (skipped.has(sanitized)) continue;
    const existing = map.get(sanitized);
    if (existing && existing !== canonical) {
      map.delete(sanitized);
      skipped.add(sanitized);
      continue;
    }
    map.set(sanitized, canonical);
  }
  return map;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Rewrite sanitized tool names to their dotted canonical form, everywhere.
 *
 * Replacement runs on raw text before markdown escaping; canonical names
 * introduce no markup, so output stays safe by construction. Longest-
 * match-first ordering keeps shared prefixes (k8s_get_pods vs
 * k8s_get_pod_logs) unambiguous, and the leading boundary also excludes
 * dots: an already-dotted mention (k8s.get_pod_logs) must not re-match a
 * suffix key should the registry ever contain one. The trailing boundary
 * stays word-only so names ending a sentence ("called k8s_get_pods.")
 * still rewrite.
 */
export function displayToolNames(
  text: string,
  names: Map<string, string>,
): string {
  if (!names.size) return text;
  const pattern = [...names.keys()]
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
    .join("|");
  return text.replace(
    new RegExp(`(?<![\\w.])(${pattern})(?!\\w)`, "g"),
    (match) => names.get(match) ?? match,
  );
}
