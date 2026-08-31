import { describe, expect, it } from "vitest";
import {
  canonicalToolNames,
  displayToolNames,
  sanitizeToolName,
} from "../toolNames";

describe("sanitizeToolName", () => {
  it("maps dots to underscores (AgentScope function-calling rule)", () => {
    expect(sanitizeToolName("k8s.get_pods")).toBe("k8s_get_pods");
    expect(sanitizeToolName("k8s.delete_pod")).toBe("k8s_delete_pod");
  });
});

describe("canonicalToolNames", () => {
  it("maps sanitized names to dotted canonical names", () => {
    const map = canonicalToolNames([
      { name: "k8s.get_pods" },
      { name: "k8s.get_pod_logs" },
    ]);
    expect(map.get("k8s_get_pods")).toBe("k8s.get_pods");
    expect(map.get("k8s_get_pod_logs")).toBe("k8s.get_pod_logs");
  });

  it("skips names without dots and entries with no usable name", () => {
    const map = canonicalToolNames([
      { name: "plain_tool" },
      { name: undefined },
      {},
      { name: 42 },
    ]);
    expect(map.size).toBe(0);
  });

  it("skips ambiguous sanitized collisions instead of guessing", () => {
    const map = canonicalToolNames([
      { name: "k8s.get_pods" },
      { name: "k8s_get.pods" },
    ]);
    expect(map.size).toBe(0);
  });

  it("keeps skipping a collision even when a third entry repeats it", () => {
    const map = canonicalToolNames([
      { name: "k8s.get_pods" },
      { name: "k8s_get.pods" },
      { name: "k8s.get.pods" },
    ]);
    expect(map.size).toBe(0);
  });
});

const NAMES = canonicalToolNames([
  { name: "k8s.get_pods" },
  { name: "k8s.get_pod_logs" },
]);

describe("displayToolNames", () => {
  it("rewrites sanitized names to dotted canonical form in prose", () => {
    expect(displayToolNames("I ran k8s_get_pods for you.", NAMES)).toBe(
      "I ran k8s.get_pods for you.",
    );
  });

  it("returns text unchanged with an empty map", () => {
    expect(displayToolNames("call k8s_get_pods", new Map())).toBe(
      "call k8s_get_pods",
    );
  });

  it("does not touch text without mapped names", () => {
    expect(displayToolNames("no tools mentioned here", NAMES)).toBe(
      "no tools mentioned here",
    );
  });

  it("resolves shared prefixes to the most specific name", () => {
    expect(
      displayToolNames("logs via k8s_get_pod_logs and k8s_get_pods", NAMES),
    ).toBe("logs via k8s.get_pod_logs and k8s.get_pods");
  });

  it("keeps word boundaries — a longer token is not rewritten piecemeal", () => {
    const onlyPods = canonicalToolNames([{ name: "k8s.get_pods" }]);
    expect(displayToolNames("see k8s_get_pod_logs output", onlyPods)).toBe(
      "see k8s_get_pod_logs output",
    );
  });

  it("keeps the leading boundary — an embedded token is untouched", () => {
    expect(displayToolNames("xk8s_get_pods and my_k8s_get_pods", NAMES)).toBe(
      "xk8s_get_pods and my_k8s_get_pods",
    );
  });

  it("rewrites a name that ends a sentence", () => {
    expect(displayToolNames("I called k8s_get_pods.", NAMES)).toBe(
      "I called k8s.get_pods.",
    );
  });

  it("does not re-match a suffix key inside an already-dotted name", () => {
    // Pathological registry: get.pod_logs sanitizes to a suffix of the
    // dotted canonical name k8s.get_pod_logs.
    const suffixKey = canonicalToolNames([{ name: "get.pod_logs" }]);
    expect(
      displayToolNames("see k8s.get_pod_logs output", suffixKey),
    ).toBe("see k8s.get_pod_logs output");
  });

  it("rewrites names inside inline code spans too (v0.27.5)", () => {
    expect(
      displayToolNames("prose k8s_get_pods and `k8s_get_pods` in code", NAMES),
    ).toBe("prose k8s.get_pods and `k8s.get_pods` in code");
  });

  it("rewrites names inside fenced blocks too (v0.27.5)", () => {
    const text = "ran k8s_get_pods\n```bash\nAGENT_GATEWAY_TOOL_AUTO_ALLOW=k8s_get_pods\n```\nthen k8s_get_pod_logs";
    expect(displayToolNames(text, NAMES)).toBe(
      "ran k8s.get_pods\n```bash\nAGENT_GATEWAY_TOOL_AUTO_ALLOW=k8s.get_pods\n```\nthen k8s.get_pod_logs",
    );
  });
});
