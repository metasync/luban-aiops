// Manual intake labels parsing tests (SPEC-015 R-2 parity).
import { describe, expect, it } from "vitest";
import { parseLabelsInput } from "../labels";

describe("parseLabelsInput", () => {
  it("parses comma-separated key=value pairs", () => {
    expect(parseLabelsInput("team=payments, cluster=dev-k8s")).toEqual({
      team: "payments",
      cluster: "dev-k8s",
    });
  });

  it("skips empty entries", () => {
    expect(parseLabelsInput("a=1,, b=2 ,")).toEqual({ a: "1", b: "2" });
  });

  it("keeps values containing equals signs", () => {
    expect(parseLabelsInput("filter=a=b")).toEqual({ filter: "a=b" });
  });

  it("returns an empty map for blank input", () => {
    expect(parseLabelsInput("")).toEqual({});
    expect(parseLabelsInput(" , ")).toEqual({});
  });

  it("rejects entries without a non-empty key", () => {
    expect(() => parseLabelsInput("=value")).toThrow(
      "Labels must be key=value pairs.",
    );
    expect(() => parseLabelsInput("team")).toThrow(
      "Labels must be key=value pairs.",
    );
  });
});
