"""Supervised F-35 campaign controller; failures remain failures, never retried."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from uuid import uuid4
import xml.etree.ElementTree as ET

from execution_acceptance import PATHS, ROOT, Refused

# Independent target HTTP reads run inside the target pod, not through the
# platform. Only revision/state metadata leaves it; Basic auth stays in memory.
TARGET_READ = '''
import base64,json,os,sys,urllib.request
name=sys.argv[1]
base="http://127.0.0.1:8080"
header="Basic "+base64.b64encode(("admin:"+os.environ["ACME_ADMIN_PASSWORD"]).encode()).decode()
def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path,headers={"Authorization":header}),timeout=10) as r:
        return json.load(r)
h=get("/healthz")
u=get("/api/users/"+name)
peers=get("/api/users")["users"]
print(json.dumps({"started_at":h["started_at"],"hostname":h["hostname"],"store_revision":h["store_revision"],
 "user":{k:u[k] for k in ("username","revision","locked","password_changed_at")},
 "peers":[p for p in peers if p["username"]!=name]}))
'''


def need(condition, reason):
    if not condition:
        raise Refused(reason)


def target(cluster):
    raw = cluster.command("exec", "deployment/acme-admin", "--", "/app/.venv/bin/python", "-c", TARGET_READ,
                          cluster.args.target_user)
    try:
        return json.loads(raw)
    except ValueError:
        raise Refused("independent target read failed") from None


def check_target(before, after, delta):
    need(before["started_at"] == after["started_at"] and before["hostname"] == after["hostname"],
         "sample target restarted between observations")
    need(before["peers"] == after["peers"], "a non-throwaway target user changed")
    need(after["store_revision"] - before["store_revision"] == delta, "unexpected target store revision delta")
    need(after["user"]["revision"] - before["user"]["revision"] == delta, "unexpected throwaway revision delta")


def wire_delta(before, after, expected):
    need(before["boot_id"] == after["boot_id"], "wire witness restarted")
    need(after["attempts"] - before["attempts"] == expected, "unexpected gateway attempt count")
    need(after["completed"] - before["completed"] == expected, "unexpected gateway response count")


def interrupt(cluster, prepared):
    cluster.probe("wire", control="/control/block")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(cluster.probe, "invoke", **prepared)
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                if cluster.probe("wire")["held"]:
                    break
                need(not future.done(), "worker completed before interruption barrier")
                time.sleep(0.2)
            else:
                raise Refused("gateway-response barrier was not reached")
            # The response is held by a separate process: the worker cannot
            # commit its result before the explicitly authorized hard stop.
            pods = json.loads(cluster.command("get", "pods", "-l", "app=execution-runtime", "-o", "json"))["items"]
            need(len(pods) == 1, "ambiguous execution-worker inventory")
            victim = pods[0]["metadata"]["name"]
            need(pods[0]["metadata"]["namespace"] == cluster.args.namespace, "worker namespace mismatch")
            cluster.command("delete", "pod", victim, "--grace-period=0", "--force", "--wait=true", timeout=45)
            result = future.result(timeout=125)
    finally:
        cluster.probe("wire", control="/control/release")
    cluster.command("rollout", "status", "deployment/execution-runtime", "--timeout=120s", timeout=135)
    cluster.probe("ready")
    return result


def run_campaign(cluster, authorization_digest):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:10]
    directory = ROOT / ".workspaces/spec063-evidence" / ("s6-" + stamp)
    directory.mkdir(parents=True, exist_ok=False)
    report = {"scenario": "F-35", "authorization_sha256": authorization_digest,
              "delivery_complete": False, "acceptance_passed": False, "results": [],
              "namespace": cluster.args.namespace, "context": cluster.args.context,
              "target_user": cluster.args.target_user, "epoch": cluster.args.epoch,
              "keycloak_changes": [], "harness": "deterministic product seams, not portal UI"}
    suite = ET.Element("testsuite", name="SPEC-063-F-35", tests=str(len(PATHS)))
    active = None
    journey = None
    try:
        report["driver_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in Path(__file__).parent.glob("execution_acceptance*.py")}
        cluster.assert_isolation()
        cluster.probe("ready")
        report["namespace_uid"] = cluster.namespace_uid
        report["images"] = {name: [c["image"] for c in cluster.get("deployment", name)["spec"]["template"]["spec"]["containers"]]
                            for name in ("agent-service", "execution-runtime", "tool-gateway", "acme-admin")}
        initial = previous = target(cluster)
        report["initial_target"] = initial
        need(initial["user"]["username"] == cluster.args.target_user, "target identity mismatch")
        for path in PATHS:
            active = ET.SubElement(suite, "testcase", classname="F-35", name=path)
            journey = {"path": path, "status": "running"}
            report["results"].append(journey)
            cluster.assert_isolation()
            before = target(cluster)
            check_target(previous, before, 0)
            wire_before = cluster.probe("wire")
            journey.update(before=before, wire_before=wire_before)
            if path == "held-secret":
                result = cluster.probe("held-secret", path=path)
                delta = 1
                need(result["redeemed_once"] and result["replay_release_count"] == 0, "secret single-use proof")
            else:
                action = "unlock" if before["user"]["locked"] else "lock"
                prepared = cluster.probe("prepare", path=path, action=action)
                prepared.pop("ok")
                result = interrupt(cluster, prepared) if path == "interrupted" else cluster.probe("invoke", **prepared)
                delta = 0 if path == "denied-expired" else 1
                need(result["release_count"] == 0, "non-secret path emitted a secret")
                if path == "normal":
                    need(result["state"] == "result_recorded" and "response_accepted" in result["observation_kinds"], "normal acceptance")
                if path == "denied-expired":
                    need(result["claims"] == 0 and "pre_dispatch_refused" in result["observation_kinds"], "expired authority refusal")
                if path == "interrupted":
                    need(result["state"] == "outcome_unknown" and result["receipt_status"] is None, "interrupted outcome must stay unknown")
                if path in {"interrupted", "owner-reload"}:
                    recovered = cluster.probe("recover", **prepared)
                    need(recovered["run_stopped"] and recovered["metadata_only"], "stopped owner recovery")
                    need("response_accepted" not in recovered["observation_kinds"], "withheld response became accepted")
                    replay = cluster.probe("invoke", **{**prepared, "path": "replay"})
                    need(replay["release_count"] == 0 and replay["claims"] == 1, "replay changed dispatch authority")
                    result["recovered"] = recovered
            need(result["claims"] == delta, "claim count does not match this journey")
            need(result["card_status"] == "approved" and result["card_decider"] == cluster.args.approver, "durable card identity")
            after = target(cluster)
            check_target(before, after, delta)
            if path == "held-secret":
                need(after["user"]["password_changed_at"] is not None and
                     after["user"]["password_changed_at"] != before["user"]["password_changed_at"], "password was not changed")
                need(after["user"]["locked"] == before["user"]["locked"], "password reset changed lock state")
            else:
                need(after["user"]["locked"] == (before["user"]["locked"] if delta == 0 else action == "lock"), "lock-state reconciliation failed")
                need(after["user"]["password_changed_at"] == before["user"]["password_changed_at"], "non-password path changed password")
            wire_after = cluster.probe("wire")
            wire_delta(wire_before, wire_after, delta)
            journey.update(status="passed", after=after, wire_after=wire_after, facts=result)
            print("F-35 passed: " + path, flush=True)
            previous = after
            active = None
            journey = None
        report["final_target"] = target(cluster)
        check_target(previous, report["final_target"], 0)
        report["acceptance_passed"] = len(report["results"]) == len(PATHS)
        return 0
    except Exception as exc:
        # Do not retain raw subprocess/HTTP exceptions or tool payloads.
        reason = str(exc) if isinstance(exc, Refused) else "acceptance controller failed"
        report["failure"] = reason
        if journey is not None:
            journey.update(status="failed", failure=reason)
        for key, reader in (("target_after_failure", lambda: target(cluster)), ("wire_after_failure", lambda: cluster.probe("wire"))):
            try:
                report[key] = reader()
            except Exception:
                report[key] = {"available": False}
        if active is None:
            active = ET.SubElement(suite, "testcase", classname="F-35", name="preflight-or-finalization")
        ET.SubElement(active, "failure", message=reason)
        print("F-35 failed: " + reason, flush=True)
        return 1
    finally:
        executed = {case.get("name") for case in suite}
        for path in PATHS:
            if path not in executed:
                case = ET.SubElement(suite, "testcase", classname="F-35", name=path)
                ET.SubElement(case, "skipped", message="campaign stopped; not executed")
                report["results"].append({"path": path, "status": "not_run"})
        suite.set("tests", str(len(suite)))
        suite.set("failures", str(sum(c.find("failure") is not None for c in suite)))
        suite.set("skipped", str(sum(c.find("skipped") is not None for c in suite)))
        directory.joinpath("evidence.json").write_text(json.dumps(report, indent=2) + "\n")
        ET.ElementTree(suite).write(directory / "junit.xml", encoding="unicode", xml_declaration=True)
        print(f"F-35 evidence: {directory}; acceptance_passed={report['acceptance_passed']}; delivery_complete=false")
