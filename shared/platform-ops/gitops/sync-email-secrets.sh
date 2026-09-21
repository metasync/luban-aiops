#!/bin/sh
# SPEC-062: opt-in SMTP authentication provisioning; never called by deploy.
# Export GATEWAY_EMAIL_PASSWORD securely, then run this script [namespace].
# No credentials in argv, temporary files, ConfigMaps, or printed output.
# Does not enable SMTP or restart workloads; apply reviewed runtime config and
# restart tool-gateway separately when ready. Requires python3 and kubectl.
set -eu
set +x
if [ "${SKIP_EMAIL_SECRETS:-}" = "true" ]; then
  echo "Email secret provisioning skipped."
  exit 0
fi
export EMAIL_SECRET_NAMESPACE="${1:-dev-luban-aiops}"
python3 - <<'PY'
import base64
import json
import os
import subprocess
import sys

password = os.environ.get("GATEWAY_EMAIL_PASSWORD", "")
if not password:
    sys.exit("GATEWAY_EMAIL_PASSWORD must be provided securely in the environment.")
namespace = os.environ["EMAIL_SECRET_NAMESPACE"]
payload = {
    "apiVersion": "v1", "kind": "Secret",
    "metadata": {"name": "tool-gateway-email-secrets", "namespace": namespace},
    "type": "Opaque",
    "data": {"GATEWAY_EMAIL_PASSWORD": base64.b64encode(password.encode()).decode()},
}
try:
    result = subprocess.run(
        ["kubectl", "apply", "--server-side", "--field-manager=luban-email-secret-sync", "-f", "-"],
        input=json.dumps(payload), text=True, capture_output=True, timeout=60,
    )
    if result.returncode:
        sys.exit("Email secret provisioning failed; check cluster access and field ownership.")
except (OSError, subprocess.TimeoutExpired):
    sys.exit("Email secret provisioning failed; check kubectl and cluster connectivity.")
print("SMTP secret provisioned. Email enablement and workload restart remain explicit steps.")
PY
