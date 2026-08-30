// Display-name alignment for gateway tools (v0.27.4): the model writes the
// sanitized tool names it sees in its function-calling schema (dots become
// underscores to satisfy provider name constraints), but the registry's
// canonical name is dotted. Chat prose and triage summaries map sanitized
// names back to the dotted canonical form at render time; the durable
// transcript keeps the model's original words, and code regions keep the
// sanitized form that configuration surfaces (AGENT_GATEWAY_TOOL_AUTO_ALLOW)
// expect.

const FENCE_SENTINEL = "\u0000F";
const FENCE_CLOSE = "\u0000";
const SPAN_SENTINEL = "\u0000S";

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
 * Rewrite sanitized tool names to their dotted canonical form in prose.
 *
 * Code regions (fenced blocks and inline spans) are shielded: the sanitized
 * form is the one configuration surfaces expect, so copy-paste out of a code
 * block must keep it. Replacement runs on raw text before markdown escaping;
 * canonical names introduce no markup, so output stays safe by construction.
 * Text that is mid-stream (an unclosed fence) is left untouched rather than
 * half-rewritten.
 */
export function displayToolNames(
  text: string,
  names: Map<string, string>,
): string {
  if (!names.size) return text;
  const fences: string[] = [];
  const spans: string[] = [];
  let shielded = text.replace(/\u0000/g, "");
  shielded = shielded.replace(/```[\s\S]*?```/g, (block) => {
    fences.push(block);
    return `${FENCE_SENTINEL}${fences.length - 1}${FENCE_CLOSE}`;
  });
  shielded = shielded.replace(/`[^`\n]+`/g, (span) => {
    spans.push(span);
    return `${SPAN_SENTINEL}${spans.length - 1}${FENCE_CLOSE}`;
  });
  // Longest first so a shared prefix (k8s_get_pods vs k8s_get_pod_logs)
  // resolves to the most specific registered name.
  const pattern = [...names.keys()]
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
    .join("|");
  const rewritten = shielded.replace(
    new RegExp(`\\b(${pattern})\\b`, "g"),
    (match) => names.get(match) ?? match,
  );
  return rewritten
    .replace(/\u0000S(\d+)\u0000/g, (_m, index: string) => spans[Number(index)] ?? "")
    .replace(/\u0000F(\d+)\u0000/g, (_m, index: string) => fences[Number(index)] ?? "");
}
