// Role sets ported 1:1 from the legacy portal (app.js). Client-side
// gating is a convenience only — the gateway re-enforces the matching
// policy action on every request regardless (SPEC-019 R-1).
export const AUDIT_ROLES = new Set(["auditor", "platform-admin"]);

export const INCIDENT_VIEW_ROLES = new Set([
  "platform-admin",
  "approver",
  "operator",
  "developer",
  "read-only-observer",
]);

// Reporting and triage need the write vocabulary (incident:create /
// incident:triage); read-only-observer can look but not act.
export const INCIDENT_ACT_ROLES = new Set([
  "platform-admin",
  "approver",
  "operator",
  "developer",
]);

// SPEC-020 R-4: the gateway re-enforces chat:confirm on every decision.
export const CHAT_CONFIRM_ROLES = new Set([
  "platform-admin",
  "approver",
  "operator",
  "developer",
]);

// SPEC-030 R-5: parked batches whose highest action is tools:mutate are
// tier_2 approvals decided by designated approvers. Display hint only —
// the gateway approval-tier bridge stays authoritative and 403s anyway;
// mirror of the shipped bundle's decided_by_roles.
export const APPROVAL_DECIDER_ROLES = new Set(["approver", "platform-admin"]);

// SPEC-039 R-2: documents:create/documents:read are granted to the
// operational authoring roles only — developer and observer hold neither.
// Client-side mirror of the allow-operators-documents bundle rule; the
// gateway re-enforces both actions on every request.
export const DOCUMENT_ROLES = new Set([
  "platform-admin",
  "approver",
  "operator",
]);

// SPEC-044 R-5: session:skill_draft follows the documents-create grant
// pattern — drafting skills from a session is an operational act, so
// developer and observer hold it not. Client-side mirror of the
// allow-operators-skill-draft bundle rule; the gateway re-enforces the
// action on every request.
export const SKILL_DRAFT_ROLES = new Set([
  "platform-admin",
  "approver",
  "operator",
]);

// SPEC-045 R-4: incident:skill_draft follows the same operational
// grant (bundled with incident:read, which observer roles hold) —
// drafting a skill from an incident's validated triage is an
// operational act, so developer and observer hold it not. Client-side
// mirror of allow-operators-incident-skill-draft; the gateway
// re-enforces both actions on every request.
export const INCIDENT_SKILL_DRAFT_ROLES = new Set([
  "platform-admin",
  "approver",
  "operator",
]);

// SPEC-055 R-4/OQ-3: session:skill_graduate is a *higher* trust level
// than the two draft grants — its artifact declares risk_class: write and
// a machine-readable replay step list rather than knowledge prose — so it
// is separately authorized. Same operational-role posture, and it gates
// the mid-session target declaration too (one capability, one action).
// Client-side mirror of allow-operators-skill-graduate; the gateway
// re-enforces the action on every request.
export const SKILL_GRADUATE_ROLES = new Set([
  "platform-admin",
  "approver",
  "operator",
]);

// SPEC-056 R-2/R-6: Studio is exactly the authoring power — the roles that
// hold session:skill_graduate. Defined *equal to* SKILL_GRADUATE_ROLES (not a
// re-typed literal) so the two sets cannot drift: the gateway dual-gates
// opening a `development` session on session:skill_graduate beside
// session:create (R-6), and this client nav gate mirrors that exact set.
// developer / read-only-observer / auditor hold session:create but not
// session:skill_graduate, so they keep Chat only and never see Studio.
export const STUDIO_ROLES = SKILL_GRADUATE_ROLES;

export function hasAnyRole(roles: string[], allowed: Set<string>): boolean {
  return roles.some((role) => allowed.has(role));
}
