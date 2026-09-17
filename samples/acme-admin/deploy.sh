#!/bin/sh

# Build, deploy and ASSERT the `acme-admin` sample application (SPEC-059 R-6).
#
# Invoked by `make deploy-sample-app` / `make undeploy-sample-app`. This is a
# deploy AND an assertion: it does not exit 0 unless the app is reachable from
# inside the cluster, serving the health payload the skills read, and refusing
# unauthenticated callers. A deploy that quietly produced a broken tutorial
# target wastes the operator's next hour, so every claim the walkthroughs make
# about the app is checked here first.
#
# Steps, in order:
#   1. pre-flight   kustomize render, required secrets, required base image
#   2. build        `make -C app build` with the coordinated IMAGE_TAG
#   3. load         `kind load docker-image` under the root build's conditions
#   4. apply        kubectl apply + set image + rollout status
#   5. assert       nine checks, each failing loudly and by name
#   6. follow-ups   the two commands the operator still has to run
#
# IMAGE_TAG resolution mirrors deploy-overlay.sh: `.images.env` (written by
# `make build`) wins, so the sample image carries the same coordinated tag as
# the platform images already running. Only when that file is absent is the tag
# computed here, with the same expression the root Makefile uses.
#
# Usage:
#   samples/acme-admin/deploy.sh [namespace]                  # deploy + assert
#   ACTION=undeploy samples/acme-admin/deploy.sh [namespace]   # remove
#
# Environment overrides:
#   NAMESPACE / $1    (default dev-luban-aiops)
#   ACTION            (deploy | undeploy; default deploy)
#   IMAGE_PLATFORM    (default linux/amd64, as mk/defaults.mk)
#   AUTO_LOAD_KIND    (default false; KIND_CLUSTER_NAME required when true)
#   SKIP_BUILD        (true = reuse the image already built/loaded)

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
GITOPS_DIR="$REPO_ROOT/shared/platform-ops/gitops"
STATE_FILE="${STATE_FILE:-$GITOPS_DIR/dev-k8s/.images.env}"

NAMESPACE="${1:-${NAMESPACE:-dev-luban-aiops}}"
ACTION="${ACTION:-deploy}"

APP_DIR="$SCRIPT_DIR/app"
DEPLOY_DIR="$SCRIPT_DIR/deploy"
IMAGE_NAME="acme-admin"
IMAGE_PLATFORM="${IMAGE_PLATFORM:-linux/amd64}"
BASE_UV_IMAGE="${BASE_UV_IMAGE:-luban-aiops/base-uv}"
BASE_UV_TAG="${BASE_UV_TAG:-al2023}"

SECRET_NAME="acme-admin-credentials"
APP_SERVICE="acme-admin"
ORIGIN="http://acme-admin:8080"
# The app's operator account (acme_admin.auth.ADMIN_USERNAME). Its password is
# the `acme-admin` credential set, written by sync-browser-credentials.sh.
ADMIN_USERNAME="admin"

# Probes run inside the tool-gateway pod rather than in a throwaway
# `kubectl run` pod, for three reasons: the base-uv image already ships curl,
# so nothing has to be pulled; the pod is labelled `app: tool-gateway`, which
# is exactly the origin the app's NetworkPolicy admits, so an assertion
# traverses the same ingress rule real traffic does instead of needing a hole
# punched for itself; and it is the pod the http.* and web.* tools actually
# call from.
PROBE_DEPLOYMENT="tool-gateway"
PROBE_CONTAINER="tool-gateway"
# A pod the NetworkPolicy does NOT admit, used for the informational deny check.
FOREIGN_PROBE_DEPLOYMENT="audit-service"

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

fail() {
  echo "" >&2
  echo "ASSERTION FAILED: $1" >&2
  echo "deploy-sample-app did not complete; see the check marked above." >&2
  exit 1
}

check() {
  echo "  ok: $1"
}

# --- undeploy ---------------------------------------------------------------
if [ "$ACTION" = "undeploy" ]; then
  echo "==> undeploy-sample-app: removing acme-admin from namespace '$NAMESPACE'"
  # Deployment, Service and NetworkPolicy come from the kustomization, so the
  # render stays the single source of truth for what "everything" means.
  kubectl delete -k "$DEPLOY_DIR" -n "$NAMESPACE" --ignore-not-found
  # The app-side secret is this sample's, so it goes too. The shared
  # tool-gateway-browser-credentials secret and every platform resource are
  # deliberately left alone: the browser credential sets are platform state,
  # and the allowlist entries are GitOps state, not script state.
  kubectl -n "$NAMESPACE" delete secret "$SECRET_NAME" --ignore-not-found
  echo "acme-admin removed. Left untouched: tool-gateway-browser-credentials,"
  echo "every platform resource, and the GATEWAY_*_ALLOW_ORIGINS entries (GitOps state)."
  exit 0
fi

if [ "$ACTION" != "deploy" ]; then
  echo "unknown ACTION='$ACTION' (expected deploy|undeploy)" >&2
  exit 2
fi

# --- 1. pre-flight ----------------------------------------------------------
echo "==> deploy-sample-app: namespace '$NAMESPACE'"

command -v kubectl >/dev/null 2>&1 || fail "kubectl not found on PATH"
command -v make >/dev/null 2>&1 || fail "make not found on PATH"
command -v docker >/dev/null 2>&1 || fail "docker not found on PATH"

kubectl -n "$NAMESPACE" get "deployment/$PROBE_DEPLOYMENT" >/dev/null 2>&1 || {
  echo "tool-gateway deployment not found in namespace '$NAMESPACE'." >&2
  echo "Run 'make deploy' first — the sample app is a tutorial target for a" >&2
  echo "running platform, and the assertions probe from the gateway pod." >&2
  exit 1
}

# Render the manifests before building anything: a broken kustomization should
# fail in a second, not after a two-minute image build. `make overlays` cannot
# cover this directory — that loop prefixes $(GITOPS_DIR)/ — so the render
# check lives here.
kubectl kustomize --load-restrictor LoadRestrictionsNone "$DEPLOY_DIR" \
  > "$WORK_DIR/rendered.yaml" || fail "kustomize could not render $DEPLOY_DIR"
grep -q "kind: Deployment" "$WORK_DIR/rendered.yaml" \
  || fail "rendered manifests contain no Deployment"
grep -q "kind: Service" "$WORK_DIR/rendered.yaml" \
  || fail "rendered manifests contain no Service"
grep -q "kind: NetworkPolicy" "$WORK_DIR/rendered.yaml" \
  || fail "rendered manifests contain no NetworkPolicy"
echo "  ok: kustomize renders Deployment + Service + NetworkPolicy"

# The app fails closed without this secret, so refuse to deploy a pod that
# could only ever land in CreateContainerConfigError. It is written by
# sync-browser-credentials.sh, which `make deploy` calls.
kubectl -n "$NAMESPACE" get secret "$SECRET_NAME" >/dev/null 2>&1 || {
  echo "secret '$SECRET_NAME' not found in namespace '$NAMESPACE'." >&2
  echo "Run 'make deploy' (or the sync script directly) to generate it:" >&2
  echo "  $GITOPS_DIR/sync-browser-credentials.sh $NAMESPACE" >&2
  echo "The same random value also lands in the 'acme-admin' browser" >&2
  echo "credential set, which is what the skills resolve at call time." >&2
  exit 1
}
check "secret $SECRET_NAME exists"

# The allowlist entries are GitOps state the walkthroughs depend on; asserting
# them here turns "the skill denies every request" into a named pre-flight
# failure instead of a mystery an operator debugs mid-chat.
RENDERED_HTTP_ORIGINS=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o go-template='{{index .data "GATEWAY_HTTP_ALLOW_ORIGINS"}}' 2>/dev/null || echo "")
case ",$RENDERED_HTTP_ORIGINS," in
  *",$ORIGIN,"*) ;;
  *)
    echo "GATEWAY_HTTP_ALLOW_ORIGINS in the live platform-runtime-config does not" >&2
    echo "list $ORIGIN (found: '${RENDERED_HTTP_ORIGINS:-<unset>}')." >&2
    echo "Apply the browser-dev runtime profile: 'make deploy'." >&2
    exit 1
    ;;
esac
check "GATEWAY_HTTP_ALLOW_ORIGINS lists $ORIGIN"

# --- 2. resolve the coordinated tag and build -------------------------------
if [ -f "$STATE_FILE" ]; then
  # shellcheck disable=SC1090
  . "$STATE_FILE"
fi
IMAGE_TAG="${IMAGE_TAG:-}"
if [ -z "$IMAGE_TAG" ]; then
  # Same expression as the root Makefile: <semver>-<prefix>[-<profile>]-<sha>,
  # with -dirty-<timestamp> appended when the tree has uncommitted changes.
  PLATFORM_VERSION=$(cat "$REPO_ROOT/VERSION" 2>/dev/null || echo "")
  IMAGE_TAG_PREFIX="${IMAGE_TAG_PREFIX:-dev-k8s}"
  IMAGE_TAG_PROFILE="${IMAGE_TAG_PROFILE:-}"
  tag_base="${PLATFORM_VERSION:+$PLATFORM_VERSION-}${IMAGE_TAG_PREFIX}${IMAGE_TAG_PROFILE:+-$IMAGE_TAG_PROFILE}"
  git_sha=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo manual)
  if [ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]; then
    IMAGE_TAG="$tag_base-$git_sha-dirty-$(date +%Y%m%d%H%M%S)"
  else
    IMAGE_TAG="$tag_base-$git_sha"
  fi
  echo "  (no $STATE_FILE; computed IMAGE_TAG=$IMAGE_TAG)"
fi
IMAGE_REF="luban-aiops/$IMAGE_NAME:$IMAGE_TAG"
echo "==> IMAGE_TAG=$IMAGE_TAG"

docker image inspect "$BASE_UV_IMAGE:$BASE_UV_TAG" >/dev/null 2>&1 || {
  echo "base image $BASE_UV_IMAGE:$BASE_UV_TAG not found locally." >&2
  echo "Run 'make base-images' first." >&2
  exit 1
}

if [ "${SKIP_BUILD:-}" = "true" ]; then
  echo "==> SKIP_BUILD=true; reusing $IMAGE_REF"
  docker image inspect "$IMAGE_REF" >/dev/null 2>&1 \
    || fail "SKIP_BUILD=true but $IMAGE_REF does not exist locally"
else
  echo "==> building $IMAGE_REF (platform $IMAGE_PLATFORM)"
  make -C "$APP_DIR" build IMAGE_TAG="$IMAGE_TAG" IMAGE_PLATFORM="$IMAGE_PLATFORM" \
    || fail "image build failed"
fi

# --- 3. load into a local kind cluster --------------------------------------
# Same conditions as the root build: opt-in, and the cluster name is required
# so an image is never loaded into the wrong cluster.
if [ "${AUTO_LOAD_KIND:-false}" = "true" ]; then
  if [ -z "${KIND_CLUSTER_NAME:-}" ]; then
    fail "KIND_CLUSTER_NAME is required when AUTO_LOAD_KIND=true"
  fi
  kind load docker-image --name "$KIND_CLUSTER_NAME" "$IMAGE_REF" \
    || fail "kind load docker-image failed"
  check "image loaded into kind cluster '$KIND_CLUSTER_NAME'"
fi

# --- 4. apply and roll out --------------------------------------------------
# apply-then-set-image is deploy-overlay.sh's pattern: the manifest carries a
# placeholder tag and the coordinated tag is applied over it, so the tag stays
# a deploy-time input rather than something the committed manifest has to know.
kubectl apply -n "$NAMESPACE" -f "$WORK_DIR/rendered.yaml" >/dev/null \
  || fail "kubectl apply failed"
kubectl -n "$NAMESPACE" set image "deployment/$APP_SERVICE" \
  "$APP_SERVICE=$IMAGE_REF" >/dev/null || fail "kubectl set image failed"
echo "==> applied; waiting for rollout (strategy: Recreate)"
kubectl -n "$NAMESPACE" rollout status "deployment/$APP_SERVICE" --timeout=180s \
  || fail "rollout did not complete within 180s (kubectl -n $NAMESPACE logs deployment/$APP_SERVICE)"
check "rollout completed"

# --- 5. assert --------------------------------------------------------------
# Every probe runs inside the tool-gateway pod. `probe_exec` forwards stdin so
# a curl config can be piped in; `</dev/null` where none is needed, because
# -i would otherwise leave the exec attached to the terminal.
probe_exec() {
  kubectl -n "$NAMESPACE" exec -i "deployment/$PROBE_DEPLOYMENT" \
    -c "$PROBE_CONTAINER" -- "$@"
}

# get_probe <path>: one GET from inside the cluster. Sets PROBE_CODE to the
# HTTP status and PROBE_BODY to the response body.
get_probe() {
  raw=$(probe_exec curl -sS -w '\n%{http_code}' "$ORIGIN$1" </dev/null) \
    || fail "in-cluster GET $1 did not complete (is the Service up?)"
  PROBE_CODE=$(printf '%s\n' "$raw" | tail -n 1)
  PROBE_BODY=$(printf '%s\n' "$raw" | sed '$d')
}

echo "==> asserting from inside the cluster (pod: $PROBE_DEPLOYMENT)"

# 5.1 the running pod is the image just built — a stale tag cannot pass.
RUNNING_IMAGE=$(kubectl -n "$NAMESPACE" get "deployment/$APP_SERVICE" \
  -o go-template='{{range .spec.template.spec.containers}}{{if eq .name "acme-admin"}}{{.image}}{{end}}{{end}}')
[ "$RUNNING_IMAGE" = "$IMAGE_REF" ] \
  || fail "deployed image is '$RUNNING_IMAGE', expected '$IMAGE_REF'"
check "deployed image tag matches the built tag ($IMAGE_REF)"

# 5.2 GET /healthz: 200 and all eight R-1 keys. A bare 200 is not a health
# check; the skills assert on these fields.
get_probe /healthz
[ "$PROBE_CODE" = "200" ] || fail "GET /healthz returned $PROBE_CODE, expected 200"
for key in status service version hostname uptime_seconds started_at \
  users_seeded store_revision; do
  printf '%s' "$PROBE_BODY" | grep -q "\"$key\"" \
    || fail "GET /healthz payload has no '$key' key (body: $PROBE_BODY)"
done
check "GET /healthz -> 200 with all eight keys"

# 5.3 GET /api/hello?name=luban: the echo proves round-trip correctness, not
# just reachability.
get_probe '/api/hello?name=luban'
[ "$PROBE_CODE" = "200" ] || fail "GET /api/hello returned $PROBE_CODE, expected 200"
printf '%s' "$PROBE_BODY" | grep -q 'hello, luban!' \
  || fail "GET /api/hello?name=luban did not echo the greeting (body: $PROBE_BODY)"
check "GET /api/hello?name=luban -> 200 and echoes the name"

# 5.4 GET /api/users unauthenticated: 401. The skills' HTTP surface is
# admin-only, and a target that answered without credentials would teach that
# authentication is decorative.
get_probe /api/users
[ "$PROBE_CODE" = "401" ] || fail "GET /api/users without credentials returned $PROBE_CODE, expected 401"
check "GET /api/users without credentials -> 401"

# 5.5 GET /api/users with the synced credential: 200 and the seeded set. The
# password crosses on stdin as a curl config file rather than in argv, so it
# never appears in a process listing on either side of the exec, and it is
# decoded by kubectl rather than by a base64 flag that differs per platform.
ADMIN_PASSWORD=$(kubectl -n "$NAMESPACE" get secret "$SECRET_NAME" \
  -o go-template='{{index .data "ACME_ADMIN_PASSWORD" | base64decode}}')
[ -n "$ADMIN_PASSWORD" ] || fail "secret $SECRET_NAME has an empty ACME_ADMIN_PASSWORD"
# curl's config parser understands \" and \\ inside a double-quoted value;
# dev passwords are alphanumeric, but an operator-supplied set need not be.
ADMIN_PASSWORD_ESCAPED=$(printf '%s' "$ADMIN_PASSWORD" \
  | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
authed_raw=$(printf 'user = "%s:%s"\n' "$ADMIN_USERNAME" "$ADMIN_PASSWORD_ESCAPED" \
  | probe_exec curl -sS -K - -w '\n%{http_code}' "$ORIGIN/api/users") \
  || fail "authenticated GET /api/users did not complete"
PROBE_CODE=$(printf '%s\n' "$authed_raw" | tail -n 1)
PROBE_BODY=$(printf '%s\n' "$authed_raw" | sed '$d')
[ "$PROBE_CODE" = "200" ] \
  || fail "GET /api/users with the synced credential returned $PROBE_CODE, expected 200 — the app's admin password and the '$APP_SERVICE' credential set disagree; re-run sync-browser-credentials.sh and restart both deployments"
for user in alice bob carol dave; do
  printf '%s' "$PROBE_BODY" | grep -q "\"$user\"" \
    || fail "seeded user '$user' missing from GET /api/users (body: $PROBE_BODY)"
done
check "GET /api/users with the synced credential -> 200 and the four seeded users"

# 5.6 the two sinks of the one generated password agree, which is the whole
# point of R-3. The gateway's mounted sets file must carry an `acme-admin`
# entry, or web.fill_credential and http.post fail closed for every skill in
# this suite even though the app itself is healthy. Checked in-pod by name so
# no value is printed and nothing has to be copied out.
CREDS_PATH=$(kubectl -n "$NAMESPACE" get "deployment/$PROBE_DEPLOYMENT" \
  -o go-template='{{range .spec.template.spec.containers}}{{if eq .name "tool-gateway"}}{{range .env}}{{if eq .name "GATEWAY_BROWSER_CREDENTIAL_SETS"}}{{.value}}{{end}}{{end}}{{end}}{{end}}')
CREDS_PATH="${CREDS_PATH:-/etc/luban/browser-credentials/credential-sets.json}"
if probe_exec test -f "$CREDS_PATH" </dev/null >/dev/null 2>&1; then
  if probe_exec grep -q "\"$APP_SERVICE\"" "$CREDS_PATH" </dev/null >/dev/null 2>&1; then
    check "credential set '$APP_SERVICE' present in the gateway's mounted sets file"
  else
    echo "  WARN: no '$APP_SERVICE' entry in $CREDS_PATH — web.fill_credential and"
    echo "        http.post will fail closed for the browser/HTTP skills. Re-run"
    echo "        $GITOPS_DIR/sync-browser-credentials.sh $NAMESPACE"
  fi
else
  echo "  WARN: $CREDS_PATH not readable from the gateway pod; skipped the"
  echo "        credential-set cross-check."
fi

# 5.7 the browser allowlist carries the origin too, so both halves of a
# walkthrough run against one profile.
RENDERED_BROWSER_ORIGINS=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o go-template='{{index .data "GATEWAY_BROWSER_ALLOW_ORIGINS"}}' 2>/dev/null || echo "")
case ",$RENDERED_BROWSER_ORIGINS," in
  *",$ORIGIN,"*) check "GATEWAY_BROWSER_ALLOW_ORIGINS lists $ORIGIN" ;;
  *) fail "GATEWAY_BROWSER_ALLOW_ORIGINS does not list $ORIGIN (found: '${RENDERED_BROWSER_ORIGINS:-<unset>}') — apply the browser-dev profile with 'make deploy'" ;;
esac

# 5.8 the HTTP connector is actually switched on in the live config; SPEC-058
# keeps the base at false, so a profile that failed to merge would leave every
# http.* skill returning TOOL_NOT_FOUND.
RENDERED_HTTP_ENABLED=$(kubectl -n "$NAMESPACE" get configmap platform-runtime-config \
  -o go-template='{{index .data "GATEWAY_HTTP_ENABLED"}}' 2>/dev/null || echo "")
[ "$RENDERED_HTTP_ENABLED" = "true" ] \
  || fail "GATEWAY_HTTP_ENABLED is '${RENDERED_HTTP_ENABLED:-<unset>}' in the live config, expected true — apply the browser-dev profile with 'make deploy'"
check "GATEWAY_HTTP_ENABLED=true in the live runtime config"

# 5.9 informational: is the NetworkPolicy enforced? Deliberately NOT a hard
# assertion, because enforcement is a property of the cluster's CNI rather than
# of these manifests — a local cluster whose CNI ignores NetworkPolicy would
# otherwise fail an otherwise perfect deploy. The result is printed so an
# operator knows which posture they are demoing.
#
# The classification has to be on the *status code*, not on curl's exit status:
# `curl -w '%{http_code}'` prints `000` when it never got an HTTP response, and
# it still exits non-zero, so an `|| echo blocked` fallback concatenates into
# `000blocked` and the denied case reads as a reached one. A code of `000` is
# the deny (curl ran, nothing answered); an *empty* code means the probe itself
# could not run, which is reported as undetermined rather than claimed either way.
echo "==> NetworkPolicy probe (informational)"
if kubectl -n "$NAMESPACE" get "deployment/$FOREIGN_PROBE_DEPLOYMENT" >/dev/null 2>&1; then
  foreign_code=""
  if foreign_code=$(kubectl -n "$NAMESPACE" exec -i "deployment/$FOREIGN_PROBE_DEPLOYMENT" -- \
      curl -sS --max-time 5 -o /dev/null -w '%{http_code}' "$ORIGIN/healthz" \
      </dev/null 2>/dev/null); then
    foreign_rc=0
  else
    foreign_rc=$?
  fi
  case "$foreign_code" in
    "")
      echo "  (undetermined: the probe from $FOREIGN_PROBE_DEPLOYMENT produced no"
      echo "   status code — exit $foreign_rc. That pod may not ship curl.)"
      ;;
    000)
      check "a curl from a non-tool-gateway pod ($FOREIGN_PROBE_DEPLOYMENT) is denied (no HTTP response)"
      ;;
    *)
      echo "  WARN: a curl from $FOREIGN_PROBE_DEPLOYMENT reached the app (HTTP $foreign_code)."
      echo "        The NetworkPolicy is applied but this CNI does not enforce it."
      echo "        The manifests are still correct; the deny is just not active here."
      ;;
  esac
else
  echo "  (skipped: no $FOREIGN_PROBE_DEPLOYMENT deployment to probe from)"
fi

# --- 6. follow-ups ----------------------------------------------------------
echo ""
echo "acme-admin deployed and asserted in namespace '$NAMESPACE' (image $IMAGE_REF)."
echo "Two things this script deliberately does not do for you:"
echo "  1. install the four skills that target it:"
echo "       make deploy-samples"
echo "  2. expose the human surface for the walkthroughs (leave running):"
echo "       kubectl -n $NAMESPACE port-forward svc/$APP_SERVICE 8080:8080"
echo "     then open http://localhost:8080/admin/"
