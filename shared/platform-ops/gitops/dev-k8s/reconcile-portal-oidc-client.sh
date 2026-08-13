#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME_CONFIG_FILE=${RUNTIME_CONFIG_FILE:-"$SCRIPT_DIR/base/identity-broker/runtime-config.env"}

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
  echo "Skipping Keycloak portal client reconcile: $message" >&2
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
OIDC_CLIENT_ID=$(read_env_value OIDC_CLIENT_ID "$RUNTIME_CONFIG_FILE")
OIDC_REDIRECT_URI=$(read_env_value OIDC_REDIRECT_URI "$RUNTIME_CONFIG_FILE")
OIDC_POST_LOGOUT_REDIRECT_URI=$(read_env_value OIDC_POST_LOGOUT_REDIRECT_URI "$RUNTIME_CONFIG_FILE")
# Optional comma-separated extras kept alongside the primary URIs (e.g. the
# localhost port-forward callback for direct service debugging).
OIDC_EXTRA_REDIRECT_URIS=$(read_env_value OIDC_EXTRA_REDIRECT_URIS "$RUNTIME_CONFIG_FILE")
OIDC_EXTRA_POST_LOGOUT_REDIRECT_URIS=$(read_env_value OIDC_EXTRA_POST_LOGOUT_REDIRECT_URIS "$RUNTIME_CONFIG_FILE")

[ -n "${KEYCLOAK_REALM:-}" ] || {
  echo "Error: KEYCLOAK_REALM is required in $RUNTIME_CONFIG_FILE" >&2
  exit 1
}
[ -n "${OIDC_CLIENT_ID:-}" ] || {
  echo "Error: OIDC_CLIENT_ID is required in $RUNTIME_CONFIG_FILE" >&2
  exit 1
}
[ -n "${OIDC_REDIRECT_URI:-}" ] || {
  echo "Error: OIDC_REDIRECT_URI is required in $RUNTIME_CONFIG_FILE" >&2
  exit 1
}
[ -n "${OIDC_POST_LOGOUT_REDIRECT_URI:-}" ] || {
  echo "Error: OIDC_POST_LOGOUT_REDIRECT_URI is required in $RUNTIME_CONFIG_FILE" >&2
  exit 1
}

WEB_ORIGIN=${OIDC_REDIRECT_URI%/*}
CLIENT_NAME=${CLIENT_NAME:-"Luban AiOps Portal"}
CLIENT_DESCRIPTION=${CLIENT_DESCRIPTION:-"Luban AiOps browser portal (OIDC Authorization Code + PKCE)"}

origin_of() {
  # https://host/path -> https://host
  printf '%s' "$1" | awk -F/ '{print $1 "//" $3}'
}

EXTRA_WEB_ORIGINS=""
if [ -n "$OIDC_EXTRA_REDIRECT_URIS" ]; then
  EXTRA_WEB_ORIGINS=$(printf '%s' "$OIDC_EXTRA_REDIRECT_URIS" | tr ',' '\n' | while read -r uri; do
    [ -n "$uri" ] && origin_of "$uri"
  done | paste -sd, -)
fi

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
CLIENTS_ENDPOINT="${KEYCLOAK_SERVER_URL}/admin/realms/${KEYCLOAK_REALM}/clients"

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

get_client_internal_id() {
  request_json GET "${CLIENTS_ENDPOINT}?clientId=${OIDC_CLIENT_ID}" | jq -r '.[0].id // empty'
}

CLIENT_INTERNAL_ID=$(get_client_internal_id)

if [ -z "$CLIENT_INTERNAL_ID" ]; then
  log "Creating browser portal client ${KEYCLOAK_REALM}/${OIDC_CLIENT_ID}..."
  jq -n \
    --arg client_id "$OIDC_CLIENT_ID" \
    --arg client_name "$CLIENT_NAME" \
    --arg client_description "$CLIENT_DESCRIPTION" \
    --arg redirect_uri "$OIDC_REDIRECT_URI" \
    --arg extra_redirect_uris "$OIDC_EXTRA_REDIRECT_URIS" \
    --arg web_origin "$WEB_ORIGIN" \
    --arg extra_web_origins "$EXTRA_WEB_ORIGINS" \
    --arg post_logout_redirect_uri "$OIDC_POST_LOGOUT_REDIRECT_URI" \
    --arg extra_post_logout_redirect_uris "$OIDC_EXTRA_POST_LOGOUT_REDIRECT_URIS" \
    '
      def split_csv($s): ($s | split(",") | map(select(length > 0)));
      {
        clientId: $client_id,
        name: $client_name,
        description: $client_description,
        enabled: true,
        protocol: "openid-connect",
        publicClient: true,
        bearerOnly: false,
        standardFlowEnabled: true,
        implicitFlowEnabled: false,
        directAccessGrantsEnabled: true,
        serviceAccountsEnabled: false,
        rootUrl: $web_origin,
        baseUrl: $web_origin,
        redirectUris: ([$redirect_uri] + split_csv($extra_redirect_uris)),
        webOrigins: ([$web_origin] + split_csv($extra_web_origins)),
        defaultClientScopes: ["groups"],
        attributes: {
          "pkce.code.challenge.method": "S256",
          "post.logout.redirect.uris": (
            [$post_logout_redirect_uri] + split_csv($extra_post_logout_redirect_uris)
            | unique | join("##")
          )
        }
      }
    ' >"$TMP_DIR/create-client.json"

  request_json POST "$CLIENTS_ENDPOINT" "$TMP_DIR/create-client.json" >/dev/null
  CLIENT_INTERNAL_ID=$(get_client_internal_id)
fi

[ -n "$CLIENT_INTERNAL_ID" ] || {
  echo "Error: could not resolve Keycloak client ${KEYCLOAK_REALM}/${OIDC_CLIENT_ID}" >&2
  exit 1
}

request_json GET "${CLIENTS_ENDPOINT}/${CLIENT_INTERNAL_ID}" >"$TMP_DIR/client.json"

jq \
  --arg client_name "$CLIENT_NAME" \
  --arg client_description "$CLIENT_DESCRIPTION" \
  --arg redirect_uri "$OIDC_REDIRECT_URI" \
  --arg extra_redirect_uris "$OIDC_EXTRA_REDIRECT_URIS" \
  --arg web_origin "$WEB_ORIGIN" \
  --arg extra_web_origins "$EXTRA_WEB_ORIGINS" \
  --arg post_logout_redirect_uri "$OIDC_POST_LOGOUT_REDIRECT_URI" \
  --arg extra_post_logout_redirect_uris "$OIDC_EXTRA_POST_LOGOUT_REDIRECT_URIS" \
  '
    def split_csv($s): ($s | split(",") | map(select(length > 0)));
    .name = $client_name
    | .description = $client_description
    | .enabled = true
    | .protocol = "openid-connect"
    | .publicClient = true
    | .bearerOnly = false
    | .standardFlowEnabled = true
    | .implicitFlowEnabled = false
    | .directAccessGrantsEnabled = true
    | .serviceAccountsEnabled = false
    | .rootUrl = $web_origin
    | .baseUrl = $web_origin
    | .redirectUris = (((.redirectUris // []) + [$redirect_uri] + split_csv($extra_redirect_uris)) | unique)
    | .webOrigins = (((.webOrigins // []) + [$web_origin] + split_csv($extra_web_origins)) | unique)
    | .defaultClientScopes = (((.defaultClientScopes // []) + ["groups"]) | unique)
    | .attributes = (.attributes // {})
    | .attributes["pkce.code.challenge.method"] = "S256"
    | .attributes["post.logout.redirect.uris"] = (
        (
          if (.attributes["post.logout.redirect.uris"] // "") == "+" then
            []
          else
            (.attributes["post.logout.redirect.uris"] // "") | split("##")
          end
        )
        + [$post_logout_redirect_uri]
        + split_csv($extra_post_logout_redirect_uris)
        | map(select(length > 0))
        | unique
        | join("##")
      )
  ' "$TMP_DIR/client.json" >"$TMP_DIR/client-updated.json"

request_json PUT "${CLIENTS_ENDPOINT}/${CLIENT_INTERNAL_ID}" "$TMP_DIR/client-updated.json" >/dev/null

request_json GET "${CLIENTS_ENDPOINT}/${CLIENT_INTERNAL_ID}/protocol-mappers/models" >"$TMP_DIR/mappers.json"

upsert_mapper() {
  mapper_name=$1
  user_attribute=$2
  claim_name=$3

  jq -n \
    --arg mapper_name "$mapper_name" \
    --arg user_attribute "$user_attribute" \
    --arg claim_name "$claim_name" \
    '
      {
        name: $mapper_name,
        protocol: "openid-connect",
        protocolMapper: "oidc-usermodel-property-mapper",
        consentRequired: false,
        config: {
          "user.attribute": $user_attribute,
          "claim.name": $claim_name,
          "jsonType.label": "String",
          "access.token.claim": "true",
          "id.token.claim": "true",
          "userinfo.token.claim": "true"
        }
      }
    ' >"$TMP_DIR/mapper-${mapper_name}.json"

  mapper_matches=$(
    jq -r \
      --arg mapper_name "$mapper_name" \
      --arg user_attribute "$user_attribute" \
      --arg claim_name "$claim_name" \
      '
        any(
          .[];
          .name == $mapper_name
          and .protocolMapper == "oidc-usermodel-property-mapper"
          and .config["user.attribute"] == $user_attribute
          and .config["claim.name"] == $claim_name
          and .config["jsonType.label"] == "String"
          and .config["access.token.claim"] == "true"
          and .config["id.token.claim"] == "true"
          and .config["userinfo.token.claim"] == "true"
        )
      ' "$TMP_DIR/mappers.json"
  )

  if [ "$mapper_matches" = "true" ]; then
    return
  fi

  mapper_id=$(jq -r --arg mapper_name "$mapper_name" '.[] | select(.name == $mapper_name) | .id' "$TMP_DIR/mappers.json" | head -n 1)

  if [ -n "$mapper_id" ]; then
    request_json DELETE "${CLIENTS_ENDPOINT}/${CLIENT_INTERNAL_ID}/protocol-mappers/models/${mapper_id}" >/dev/null
  fi

  request_json POST "${CLIENTS_ENDPOINT}/${CLIENT_INTERNAL_ID}/protocol-mappers/models" "$TMP_DIR/mapper-${mapper_name}.json" >/dev/null
  request_json GET "${CLIENTS_ENDPOINT}/${CLIENT_INTERNAL_ID}/protocol-mappers/models" >"$TMP_DIR/mappers.json"
}

upsert_mapper preferred_username username preferred_username
upsert_mapper email email email

FINAL_MAPPERS=$(
  request_json GET "${CLIENTS_ENDPOINT}/${CLIENT_INTERNAL_ID}/protocol-mappers/models" \
    | jq -r '[.[].name] | sort | join(", ")'
)

log "Reconciled browser portal client ${KEYCLOAK_REALM}/${OIDC_CLIENT_ID}"
log "  redirect_uri: ${OIDC_REDIRECT_URI}"
log "  web_origin:   ${WEB_ORIGIN}"
log "  mappers:      ${FINAL_MAPPERS}"
