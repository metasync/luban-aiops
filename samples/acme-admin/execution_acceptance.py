"""Explicitly authorized F-35 entry point; no implicit live environment defaults.

The authorization record is data, never sourced as shell. --check-authorization
is strictly local and is not an acceptance pass. Live runs retain failure evidence
and never retry a failed journey or reseed/restart the sample target.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
PATHS = ("normal", "denied-expired", "interrupted", "owner-reload", "held-secret")
FIELDS = ("context", "namespace", "origin", "target_user", "operator", "approver", "epoch")


class Refused(Exception):
    """A safe, fixed diagnostic suitable for retained evidence."""


def authorize(args):
    if not args.authorization or any(not getattr(args, key, None) for key in FIELDS):
        raise Refused("explicit authorization, context, namespace, origin, actors, target and epoch required")
    if not re.fullmatch(r"spec063-[a-z0-9](?:[a-z0-9-]{0,44}[a-z0-9])?", args.namespace):
        raise Refused("only an explicitly isolated spec063- namespace is permitted")
    if not re.fullmatch(r"spec063-[a-z0-9][a-z0-9-]{0,23}", args.target_user):
        raise Refused("a dedicated spec063- throwaway target user is required")
    if args.origin != "http://acme-admin:8080" or args.operator == args.approver:
        raise Refused("same-namespace acme-admin origin and distinct actors required")
    try:
        if str(UUID(args.epoch)) != args.epoch:
            raise ValueError
        raw = Path(args.authorization).read_bytes()
        if len(raw) > 65536:
            raise ValueError
        blocks = re.findall(rb"```json\n(.*?)\n```", raw, re.S)
        if len(blocks) != 1:
            raise ValueError
        record = json.loads(blocks[0])
        if not isinstance(record, dict):
            raise ValueError
    except (OSError, ValueError, TypeError):
        raise Refused("authorization record missing, malformed, or epoch is not a canonical UUID") from None
    if any(record.get(key) != getattr(args, key) for key in FIELDS):
        raise Refused("requested environment does not match the authorization record")
    if (record.get("authorized") is not True or record.get("scenario") != "F-35"
            or record.get("paths") != list(PATHS) or record.get("target_restart_allowed") is not False
            or record.get("keycloak_reconciliation_allowed") is not False
            or record.get("actions") != ["lock", "unlock", "password-reset", "interrupt-worker", "withhold-acceptance"]):
        raise Refused("authorization lacks the exact journey, action, or isolation constraints")
    return hashlib.sha256(raw).hexdigest()


class Cluster:
    def __init__(self, args):
        self.args = args
        self.prefix = ["kubectl", "--context", args.context, "-n", args.namespace]
        self.namespace_uid = None

    def command(self, *arguments, payload=None, timeout=45):
        try:
            result = subprocess.run(self.prefix + [f"--request-timeout={timeout}s"] + list(arguments), input=payload, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise Refused("bounded cluster command failed or timed out") from None
        if result.returncode:
            raise Refused("cluster command refused; no raw payload retained")
        return result.stdout

    def get(self, kind, name):
        try:
            return json.loads(self.command("get", kind, name, "-o", "json"))
        except (ValueError, TypeError):
            raise Refused("invalid cluster metadata") from None

    def assert_isolation(self):
        namespace = self.get("namespace", self.args.namespace)
        meta = namespace["metadata"]
        if meta.get("labels", {}).get("luban.aiops/acceptance") != "spec063":
            raise Refused("namespace lacks the explicit spec063 acceptance label")
        if self.namespace_uid and meta["uid"] != self.namespace_uid:
            raise Refused("acceptance namespace was recreated during observations")
        self.namespace_uid = meta["uid"]
        nodes = json.loads(self.command("get", "nodes", "-o", "json"))["items"]
        if not nodes or any(any(c["status"] != ("True" if c["type"] == "Ready" else "False")
                               for c in node["status"]["conditions"]
                               if c["type"] in {"Ready", "MemoryPressure", "DiskPressure", "PIDPressure"})
                            for node in nodes):
            raise Refused("cluster readiness or resource pressure guard failed")
        for name in ("acme-admin", "execution-runtime", "agent-service", "tool-gateway"):
            deployment = self.get("deployment", name)
            if deployment["metadata"]["namespace"] != self.args.namespace:
                raise Refused("deployment namespace mismatch")
            if deployment["spec"].get("replicas", 1) != 1:
                raise Refused("acceptance requires one replica per execution component")
        config = self.get("configmap", "platform-runtime-config")["data"]
        for prefix in ("EXECUTION", "AGENT_EXECUTION"):
            if config.get(prefix + "_ADMISSION_ENABLED") != "true" or config.get(prefix + "_ADMISSION_EPOCH") != self.args.epoch:
                raise Refused("durable admission is not enabled at the authorized epoch")

    def probe(self, operation, **extra):
        source = Path(__file__).with_name("execution_acceptance_probe.py").read_text()
        data = {key: getattr(self.args, key) for key in FIELDS}
        data.update(operation=operation, **extra)
        payload = json.dumps({"source": source, "data": data})
        raw = self.command("exec", "-i", "deployment/agent-service", "--", "/app/.venv/bin/python", "-c",
                           "import json,sys; p=json.load(sys.stdin); exec(compile(p['source'],'acceptance-probe','exec')); print(json.dumps(main(p['data'])))",
                           payload=payload, timeout=150)
        try:
            if len(raw) > 1048576:
                raise ValueError
            result = json.loads(raw)
        except (ValueError, TypeError):
            raise Refused("acceptance probe returned invalid bounded facts") from None
        if not result.get("ok"):
            code = result.get("failure", "unknown")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_:.-]{1,120}", code):
                code = "unknown"
            raise Refused("acceptance probe failed: " + code + "; raw responses suppressed")
        return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--authorization", default=os.environ.get("EXECUTION_ACCEPTANCE_AUTHORIZATION"))
    for key in FIELDS:
        p.add_argument("--" + key.replace("_", "-"), default=os.environ.get("EXECUTION_ACCEPTANCE_" + key.upper()))
    p.add_argument("--check-authorization", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        digest = authorize(args)
        if args.check_authorization:
            print("Authorization valid (local check only; live acceptance NOT executed).")
            return 0
        from execution_acceptance_live import run_campaign
        return run_campaign(Cluster(args), digest)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.modules["execution_acceptance"] = sys.modules[__name__]
    sys.exit(main())
