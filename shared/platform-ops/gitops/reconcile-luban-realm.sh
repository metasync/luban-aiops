#!/bin/sh

# Reconcile the self-contained Luban AIOps identity on the shared dev Keycloak:
# a dedicated realm, a `groups` client scope (group membership -> `groups` claim),
# the six role groups expected by identity-broker ROLE_MAPPINGS, and one test
# user per group for live testing.
#
# Idempotent: safe to re-run; existing resources are left in place and only
# the test users' passwords are kept in sync.
#
# DEV ONLY: the test users carry a shared, non-secret development password
# (LUBAN_TEST_USER_PASSWORD). Never reuse this setup for real environments.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME_CONFIG_FILE=${RUNTIME_CONFIG_FILE:-"$SCRIPT_DIR/dev-k8s/base/identity-broker/runtime-config.env"}

KUBECTL_BIN=${KUBECTL:-kubectl}
KEYCLOAK_NAMESPACE=${KEYCLOAK_NAMESPACE:-keycloak}
KEYCLOAK_SERVICE_NAME=${KEYCLOAK_SERVICE_NAME:-keycloak-service}
KEYCLOAK_SERVICE_PORT=${KEYCLOAK_SERVICE_PORT:-8080}
KEYCLOAK_ADMIN_SECRET_NAME=${KEYCLOAK_ADMIN_SECRET_NAME:-keycloak-bootstrap-admin}
KEYCLOAK_ADMIN_SECRET_USERNAME_KEY=${KEYCLOAK_ADMIN_SECRET_USERNAME_KEY:-username}
KEYCLOAK_ADMIN_SECRET_PASSWORD_KEY=${KEYCLOAK_ADMIN_SECRET_PASSWORD_KEY:-password}
KEYCLOAK_LOCAL_PORT=${KEYCLOAK_LOCAL_PORT:-18082}
STRICT_KEYCLOAK_RECONCILE=${STRICT_KEYCLOAK_RECONCILE:-false}
KEYCLOAK_SERVER_URL=${KEYCLOAK_SERVER_URL:-}
LUBAN_TEST_USER_PASSWORD=${LUBAN_TEST_USER_PASSWORD:-luban-dev-2026}

command -v "$KUBECTL_BIN" >/dev/null 2>&1 || {
  echo "Error: missing required command '$KUBECTL_BIN'" >&2
  exit 1
}
command -v curl >/dev/null 2>&1 || {
  echo "Error: missing required command 'curl'" >&2
  exit 1
}
command -v jq >/dev/null 2>&1 || {
  echo "Error: missing required command 'jq'" >&2
  exit 1
}

if echo Zg== | base64 -D >/dev/null 2>&1; then
  BASE64_DECODE_CMD='base64 -D'
else
  BASE64_DECODE_CMD='base64 -d'
fi

log() {
  printf '%s\n' "$*"
}

warn_or_fail() {
  message=$1
  if [ "$STRICT_KEYCLOAK_RECONCILE" = "true" ]; then
    echo "Error: $message" >&2
    exit 1
  fi
  echo "Skipping Luban realm reconcile: $message" >&2
  exit 0
}

resource_exists() {
  kind=$1
  name=$2
  "$KUBECTL_BIN" -n "$KEYCLOAK_NAMESPACE" get "$kind" "$name" >/dev/null 2>&1
}

decode_secret_key() {
  secret_name=$1
  secret_key=$2
  "$KUBECTL_BIN" -n "$KEYCLOAK_NAMESPACE" get secret "$secret_name" \
    -o "jsonpath={.data.${secret_key}}" | sh -c "$BASE64_DECODE_CMD"
}

read_env_value() {
  key=$1
  file_path=$2
  awk -F= -v key="$key" '
    $1 == key {
      sub(/^[^=]*=/, "", $0)
      print $0
      exit
    }
  ' "$file_path"
}

if [ ! -f "$RUNTIME_CONFIG_FILE" ]; then
  echo "Error: runtime config file not found: $RUNTIME_CONFIG_FILE" >&2
  exit 1
fi

KEYCLOAK_REALM=$(read_env_value KEYCLOAK_REALM "$RUNTIME_CONFIG_FILE")
[ -n "$KEYCLOAK_REALM" ] || {
  echo "Error: KEYCLOAK_REALM is required in $RUNTIME_CONFIG_FILE" >&2
  exit 1
}

# username:group — one test user per platform role group.
TEST_USERS="luban-admin:ops-admins
luban-approver:ops-approvers
luban-operator:ops-operators
luban-observer:ops-observers
luban-auditor:ops-auditors
luban-developer:ops-developers"

if ! "$KUBECTL_BIN" get namespace "$KEYCLOAK_NAMESPACE" >/dev/null 2>&1; then
  warn_or_fail "namespace '$KEYCLOAK_NAMESPACE' does not exist"
fi
if ! resource_exists service "$KEYCLOAK_SERVICE_NAME"; then
  warn_or_fail "service '$KEYCLOAK_SERVICE_NAME' does not exist in namespace '$KEYCLOAK_NAMESPACE'"
fi
if ! resource_exists secret "$KEYCLOAK_ADMIN_SECRET_NAME"; then
  warn_or_fail "secret '$KEYCLOAK_ADMIN_SECRET_NAME' does not exist in namespace '$KEYCLOAK_NAMESPACE'"
fi

KEYCLOAK_ADMIN_USERNAME=$(decode_secret_key "$KEYCLOAK_ADMIN_SECRET_NAME" "$KEYCLOAK_ADMIN_SECRET_USERNAME_KEY")
KEYCLOAK_ADMIN_PASSWORD=$(decode_secret_key "$KEYCLOAK_ADMIN_SECRET_NAME" "$KEYCLOAK_ADMIN_SECRET_PASSWORD_KEY")

TMP_DIR=$(mktemp -d)
PORT_FORWARD_PID=""

cleanup() {
  if [ -n "$PORT_FORWARD_PID" ]; then
    kill "$PORT_FORWARD_PID" >/dev/null 2>&1 || true
    wait "$PORT_FORWARD_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

if [ -z "$KEYCLOAK_SERVER_URL" ]; then
  KEYCLOAK_SERVER_URL="http://127.0.0.1:${KEYCLOAK_LOCAL_PORT}"
  "$KUBECTL_BIN" -n "$KEYCLOAK_NAMESPACE" port-forward \
    "service/${KEYCLOAK_SERVICE_NAME}" \
    "${KEYCLOAK_LOCAL_PORT}:${KEYCLOAK_SERVICE_PORT}" \
    >"$TMP_DIR/port-forward.log" 2>&1 &
  PORT_FORWARD_PID=$!

  ready=false
  attempt=0
  while [ "$attempt" -lt 30 ]; do
    if curl -fsS "${KEYCLOAK_SERVER_URL}/realms/master" >/dev/null 2>&1; then
      ready=true
      break
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
  if [ "$ready" != "true" ]; then
    warn_or_fail "could not connect to Keycloak admin endpoint via port-forward"
  fi
fi

TOKEN_ENDPOINT="${KEYCLOAK_SERVER_URL}/realms/master/protocol/openid-connect/token"

TOKEN_RESPONSE=$(
  curl -fsS -X POST "$TOKEN_ENDPOINT" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode 'client_id=admin-cli' \
    --data-urlencode "username=${KEYCLOAK_ADMIN_USERNAME}" \
    --data-urlencode "password=${KEYCLOAK_ADMIN_PASSWORD}" \
    --data-urlencode 'grant_type=password'
) || {
  echo "Error: failed to obtain Keycloak admin access token" >&2
  exit 1
}

ACCESS_TOKEN=$(printf '%s' "$TOKEN_RESPONSE" | jq -r '.access_token')
[ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ] || {
  echo "Error: failed to obtain Keycloak admin access token" >&2
  exit 1
}

request_json() {
  method=$1
  url=$2
  data_file=${3:-}
  response_file="$TMP_DIR/response.json"

  if [ -n "$data_file" ]; then
    http_status=$(
      curl -sS -o "$response_file" -w '%{http_code}' \
        -X "$method" "$url" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        --data-binary "@${data_file}"
    )
  else
    http_status=$(
      curl -sS -o "$response_file" -w '%{http_code}' \
        -X "$method" "$url" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}"
    )
  fi

  case "$method:$http_status" in
    GET:200|POST:201|PUT:204|DELETE:204)
      cat "$response_file" 2>/dev/null || true
      ;;
    *)
      echo "Keycloak API request failed: ${method} ${url} -> HTTP ${http_status}" >&2
      cat "$response_file" >&2 || true
      exit 1
      ;;
  esac
}

http_status_of() {
  method=$1
  url=$2
  curl -sS -o /dev/null -w '%{http_code}' \
    -X "$method" "$url" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}"
}

REALMS_ENDPOINT="${KEYCLOAK_SERVER_URL}/admin/realms"

# --- Realm -------------------------------------------------------------------

realm_status=$(http_status_of GET "${REALMS_ENDPOINT}/${KEYCLOAK_REALM}")
if [ "$realm_status" = "404" ]; then
  log "Creating realm ${KEYCLOAK_REALM}..."
  jq -n --arg realm "$KEYCLOAK_REALM" '
    {
      realm: $realm,
      enabled: true,
      registrationAllowed: false,
      resetPasswordAllowed: false,
      editUsernameAllowed: false
    }
  ' >"$TMP_DIR/create-realm.json"
  request_json POST "$REALMS_ENDPOINT" "$TMP_DIR/create-realm.json" >/dev/null
elif [ "$realm_status" != "200" ]; then
  echo "Error: could not read realm ${KEYCLOAK_REALM} (HTTP ${realm_status})" >&2
  exit 1
fi

REALM_ENDPOINT="${REALMS_ENDPOINT}/${KEYCLOAK_REALM}"

# --- `groups` client scope ----------------------------------------------------
# Maps Keycloak group membership into the `groups` token claim consumed by
# identity-broker ROLE_MAPPINGS.

SCOPES_ENDPOINT="${REALM_ENDPOINT}/client-scopes"
GROUPS_SCOPE_ID=$(
  request_json GET "$SCOPES_ENDPOINT" \
    | jq -r '.[] | select(.name == "groups") | .id' | head -n 1
)

if [ -z "$GROUPS_SCOPE_ID" ]; then
  log "Creating client scope 'groups'..."
  jq -n '
    {
      name: "groups",
      protocol: "openid-connect",
      description: "Luban AIOps group membership claim",
      attributes: {
        "include.in.token.scope": "false",
        "display.on.consent.screen": "false"
      }
    }
  ' >"$TMP_DIR/groups-scope.json"
  request_json POST "$SCOPES_ENDPOINT" "$TMP_DIR/groups-scope.json" >/dev/null
  GROUPS_SCOPE_ID=$(
    request_json GET "$SCOPES_ENDPOINT" \
      | jq -r '.[] | select(.name == "groups") | .id' | head -n 1
  )
fi

[ -n "$GROUPS_SCOPE_ID" ] || {
  echo "Error: could not resolve client scope 'groups' in realm ${KEYCLOAK_REALM}" >&2
  exit 1
}

MAPPERS_ENDPOINT="${SCOPES_ENDPOINT}/${GROUPS_SCOPE_ID}/protocol-mappers/models"
GROUP_MAPPER_ID=$(
  request_json GET "$MAPPERS_ENDPOINT" \
    | jq -r '.[] | select(.name == "groups") | .id' | head -n 1
)

if [ -z "$GROUP_MAPPER_ID" ]; then
  log "Creating group-membership protocol mapper..."
  jq -n '
    {
      name: "groups",
      protocol: "openid-connect",
      protocolMapper: "oidc-group-membership-mapper",
      consentRequired: false,
      config: {
        "claim.name": "groups",
        "full.path": "false",
        "id.token.claim": "true",
        "access.token.claim": "true",
        "userinfo.token.claim": "true"
      }
    }
  ' >"$TMP_DIR/groups-mapper.json"
  request_json POST "$MAPPERS_ENDPOINT" "$TMP_DIR/groups-mapper.json" >/dev/null
fi

# --- Role groups ---------------------------------------------------------------

GROUPS_ENDPOINT="${REALM_ENDPOINT}/groups"

ensure_group() {
  group_name=$1
  group_id=$(
    request_json GET "${GROUPS_ENDPOINT}?search=${group_name}" \
      | jq -r --arg group_name "$group_name" \
          '.[] | select(.name == $group_name) | .id' | head -n 1
  )
  if [ -z "$group_id" ]; then
    jq -n --arg group_name "$group_name" '{name: $group_name}' \
      >"$TMP_DIR/group-${group_name}.json"
    request_json POST "$GROUPS_ENDPOINT" "$TMP_DIR/group-${group_name}.json" >/dev/null
    group_id=$(
      request_json GET "${GROUPS_ENDPOINT}?search=${group_name}" \
        | jq -r --arg group_name "$group_name" \
            '.[] | select(.name == $group_name) | .id' | head -n 1
    )
    log "Created group ${group_name}"
  fi
  [ -n "$group_id" ] || {
    echo "Error: could not resolve group ${group_name}" >&2
    exit 1
  }
  printf '%s' "$group_id"
}

# --- Test users -----------------------------------------------------------------

USERS_ENDPOINT="${REALM_ENDPOINT}/users"

ensure_user() {
  username=$1
  group_name=$2
  group_id=$3

  user_id=$(
    request_json GET "${USERS_ENDPOINT}?username=${username}&exact=true" \
      | jq -r --arg username "$username" \
          '.[] | select(.username == $username) | .id' | head -n 1
  )

  if [ -z "$user_id" ]; then
    jq -n \
      --arg username "$username" \
      --arg email "${username}@luban-aiops.local" \
      --arg first_name "Luban" \
      --arg last_name "$username" \
      '
        {
          username: $username,
          enabled: true,
          email: $email,
          emailVerified: true,
          firstName: $first_name,
          lastName: $last_name
        }
      ' >"$TMP_DIR/user-${username}.json"
    request_json POST "$USERS_ENDPOINT" "$TMP_DIR/user-${username}.json" >/dev/null
    user_id=$(
      request_json GET "${USERS_ENDPOINT}?username=${username}&exact=true" \
        | jq -r --arg username "$username" \
            '.[] | select(.username == $username) | .id' | head -n 1
    )
    log "Created user ${username} (group: ${group_name})"
  fi

  [ -n "$user_id" ] || {
    echo "Error: could not resolve user ${username}" >&2
    exit 1
  }

  # Keep the credential in sync (idempotent reset; dev-only shared password).
  jq -n --arg password "$LUBAN_TEST_USER_PASSWORD" '
    {type: "password", value: $password, temporary: false}
  ' >"$TMP_DIR/user-${username}-credential.json"
  request_json PUT \
    "${USERS_ENDPOINT}/${user_id}/reset-password" \
    "$TMP_DIR/user-${username}-credential.json" >/dev/null

  # Group membership (PUT /users/{id}/groups/{groupId} is idempotent).
  request_json PUT \
    "${USERS_ENDPOINT}/${user_id}/groups/${group_id}" >/dev/null
}

OPS_ADMINS_ID=$(ensure_group ops-admins)
OPS_APPROVERS_ID=$(ensure_group ops-approvers)
OPS_OPERATORS_ID=$(ensure_group ops-operators)
OPS_OBSERVERS_ID=$(ensure_group ops-observers)
OPS_AUDITORS_ID=$(ensure_group ops-auditors)
OPS_DEVELOPERS_ID=$(ensure_group ops-developers)

ensure_user luban-admin ops-admins "$OPS_ADMINS_ID"
ensure_user luban-approver ops-approvers "$OPS_APPROVERS_ID"
ensure_user luban-operator ops-operators "$OPS_OPERATORS_ID"
ensure_user luban-observer ops-observers "$OPS_OBSERVERS_ID"
ensure_user luban-auditor ops-auditors "$OPS_AUDITORS_ID"
ensure_user luban-developer ops-developers "$OPS_DEVELOPERS_ID"

log "Reconciled realm ${KEYCLOAK_REALM} with groups client scope and 6 test users"
