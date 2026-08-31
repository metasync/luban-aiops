// Filter vocabulary drift guard (SPEC-046 R-4, SPEC-047 R-1).
//
// Reads the shared audit-event.schema.json and asserts the portal's
// pinned constants equal the contract exactly — the SPEC-029
// parity-guard lesson applied to the portal surface. A future event
// type added to the contract without updating constants.ts fails here
// loudly instead of silently dropping out of the filter selects (the
// stale 7-of-20 / 4-of-7 defect SPEC-046 remediates). The same guard
// pins OUTCOMES, the SPEC-047 drill-down dimension.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { EMITTER_SERVICES, EVENT_TYPES, OUTCOMES } from "../constants";

// __tests__ -> audit -> views -> src -> app -> web-ui -> operator-portal
// -> products -> repo root.
const SCHEMA_PATH = path.resolve(
  fileURLToPath(import.meta.url),
  "..",
  "..",
  "..",
  "..",
  "..",
  "..",
  "..",
  "..",
  "..",
  "shared",
  "shared-contracts",
  "schemas",
  "audit-event.schema.json",
);

describe("audit filter vocabulary drift guard", () => {
  it("EVENT_TYPES mirrors the shared audit-event schema enum", () => {
    const schema = JSON.parse(readFileSync(SCHEMA_PATH, "utf-8")) as {
      properties: { event_type: { enum: string[] } };
    };
    const contractEnum = schema.properties.event_type.enum;
    // Exact set equality…
    expect([...EVENT_TYPES].sort()).toEqual([...contractEnum].sort());
    // …and the schema enum's order is the display order.
    expect([...EVENT_TYPES]).toEqual(contractEnum);
  });

  it("EMITTER_SERVICES lists the seven emitter services", () => {
    // audit-service never emits into its own store, so it stays absent.
    expect([...EMITTER_SERVICES]).toEqual([
      "agent-service",
      "execution-runtime",
      "identity-service",
      "incident-service",
      "platform-gateway",
      "skills-hub",
      "tool-gateway",
    ]);
    expect([...EMITTER_SERVICES]).not.toContain("audit-service");
  });

  it("OUTCOMES mirrors the shared audit-event schema outcome enum", () => {
    const schema = JSON.parse(readFileSync(SCHEMA_PATH, "utf-8")) as {
      properties: { outcome: { enum: string[] } };
    };
    const contractEnum = schema.properties.outcome.enum;
    expect([...OUTCOMES].sort()).toEqual([...contractEnum].sort());
    expect([...OUTCOMES]).toEqual(contractEnum);
  });
});
