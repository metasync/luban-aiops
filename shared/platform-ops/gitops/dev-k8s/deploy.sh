#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RECONCILE_OIDC_PORTAL_CLIENT=${RECONCILE_OIDC_PORTAL_CLIENT:-true}
NAMESPACE=${NAMESPACE:-dev-luban-aiops}

"$SCRIPT_DIR/../deploy-overlay.sh" "$SCRIPT_DIR"

# Provision token-delegation secrets (SPEC-008) unless skipped.
# Set SKIP_DELEGATION_SECRETS=true when secrets are injected externally (e.g. CI).
"$SCRIPT_DIR/../sync-delegation-secrets.sh" "$NAMESPACE"

# Provision durable-audit-trail ingest secrets (SPEC-013) unless skipped.
# Set SKIP_AUDIT_SECRETS=true when secrets are injected externally (e.g. CI).
"$SCRIPT_DIR/../sync-audit-secrets.sh" "$NAMESPACE"

# Provision the execution-request signing key (SPEC-037) unless skipped.
# Set SKIP_EXECUTION_SIGNING_SECRET=true when secrets are injected
# externally (e.g. CI). Without a key the platform fails closed on
# approved mutating executions (audited signing_unavailable rejection).
"$SCRIPT_DIR/../sync-execution-signing-secret.sh" "$NAMESPACE"

# Provision the execution handoff token (SPEC-038) unless skipped.
# Set SKIP_EXECUTION_HANDOFF_SECRET=true when secrets are injected
# externally (e.g. CI). Without a token mutating resumes fail closed
# (audited worker_unavailable rejection).
"$SCRIPT_DIR/../sync-execution-handoff-secret.sh" "$NAMESPACE"

# Provision skills query credentials (SPEC-014) unless skipped.
# Set SKIP_SKILLS_SECRETS=true when secrets are injected externally (e.g. CI).
"$SCRIPT_DIR/../sync-skills-secrets.sh" "$NAMESPACE"

# Provision incident intake/query credentials (SPEC-015) unless skipped.
# Set SKIP_INCIDENT_SECRETS=true when secrets are injected externally (e.g. CI).
"$SCRIPT_DIR/../sync-incident-secrets.sh" "$NAMESPACE"

# Provision the sessions database for the agent-platform session store
# (SPEC-016). Idempotent; no secrets involved.
"$SCRIPT_DIR/../sync-sessions-db.sh" "$NAMESPACE"

# Provision OTel ingest credentials for the OpenObserve backend (SPEC-005
# completion) unless skipped. Requires OO_ROOT_USER_EMAIL/OO_ROOT_USER_PASSWORD
# exported; otherwise it skips and push fails open. SKIP_OTEL_SECRETS=true for CI.
"$SCRIPT_DIR/../sync-otel-secrets.sh" "$NAMESPACE"

if [ "$RECONCILE_OIDC_PORTAL_CLIENT" = "true" ]; then
  # Self-contained realm (groups + test users) before the portal client, so
  # the client's `groups` scope resolves in the new realm.
  "$SCRIPT_DIR/../reconcile-luban-realm.sh"
  "$SCRIPT_DIR/reconcile-portal-oidc-client.sh"
else
  echo "Skipping browser portal Keycloak client reconciliation."
fi
