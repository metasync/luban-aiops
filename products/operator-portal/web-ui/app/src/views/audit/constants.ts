// Pinned audit filter vocabulary (SPEC-046 R-4, SPEC-047 R-1).
//
// EVENT_TYPES mirrors the shared audit-event.schema.json enum exactly —
// the vitest drift guard (__tests__/constants.test.ts) reads the schema
// and asserts equality so a new event type can never silently drop out
// of the portal filter selects again (the stale 7-of-20 lists were the
// defect SPEC-046 exists to remediate).
//
// EMITTER_SERVICES lists the seven services that emit audit envelopes by
// SERVICE_NAME; audit-service never emits into its own store, so it is
// not an emitter.
//
// OUTCOMES mirrors the schema's outcome enum — the additive SPEC-047
// dimension behind the Summary drill-down; the same drift guard pins it.
export const EVENT_TYPES = [
  "tool_invoked",
  "policy_decision",
  "token_exchange",
  "session_created",
  "session_deleted",
  "chat_started",
  "chat_completed",
  "confirmation_decided",
  "incident_triaged",
  "skill_searched",
  "skill_retrieved",
  "skills_synced",
  "execution_requested",
  "execution_completed",
  "execution_rejected",
  "document_created",
  "document_published",
  "document_read",
  "skill_draft_generated",
  "incident_skill_draft_generated",
] as const;

export const EMITTER_SERVICES = [
  "agent-service",
  "execution-runtime",
  "identity-service",
  "incident-service",
  "platform-gateway",
  "skills-hub",
  "tool-gateway",
] as const;

export const OUTCOMES = ["allow", "deny", "success", "error"] as const;
