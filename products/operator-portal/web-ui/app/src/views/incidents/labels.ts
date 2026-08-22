// Manual intake labels parsing (SPEC-015 R-2 parity): "key=value,
// key2=value2"; empty entries are skipped and anything without a
// non-empty key is a client-side rejection.
export function parseLabelsInput(raw: string): Record<string, string> {
  const labels: Record<string, string> = {};
  for (const part of raw.split(",")) {
    const entry = part.trim();
    if (!entry) continue;
    const separator = entry.indexOf("=");
    if (separator <= 0) throw new Error("Labels must be key=value pairs.");
    labels[entry.slice(0, separator).trim()] = entry.slice(separator + 1).trim();
  }
  return labels;
}
