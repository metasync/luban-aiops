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

export function hasAnyRole(roles: string[], allowed: Set<string>): boolean {
  return roles.some((role) => allowed.has(role));
}
