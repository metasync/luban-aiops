"""Local refusal tests: no subprocess/cluster calls may precede authorization."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "execution_acceptance.py"
spec = importlib.util.spec_from_file_location("execution_acceptance", SOURCE)
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


@pytest.fixture
def scope(tmp_path, monkeypatch):
    def no_cluster(*args, **kwargs):
        pytest.fail("authorization check contacted a subprocess")
    monkeypatch.setattr(subprocess, "run", no_cluster)
    values = dict(context="orbstack", namespace="spec063-acceptance", origin="http://acme-admin:8080",
                  target_user="spec063-accept", operator="luban-operator", approver="luban-approver",
                  epoch="01960c63-0001-4000-8000-000000000001")
    record = dict(values, authorized=True, scenario="F-35", paths=list(acceptance.PATHS),
                  actions=["lock", "unlock", "password-reset", "interrupt-worker", "withhold-acceptance"],
                  target_restart_allowed=False, keycloak_reconciliation_allowed=False)
    path = tmp_path / "authorization.txt"
    path.write_text("```json\n" + json.dumps(record) + "\n```\n")
    return SimpleNamespace(**values, authorization=str(path)), record


def test_valid_scope_check_is_local_only(scope):
    args, _ = scope
    assert len(acceptance.authorize(args)) == 64
    argv = ["--check-authorization", "--authorization", args.authorization]
    for key in acceptance.FIELDS:
        argv.extend(["--" + key.replace("_", "-"), getattr(args, key)])
    assert acceptance.main(argv) == 0


@pytest.mark.parametrize("key", ("authorization",) + acceptance.FIELDS)
def test_every_explicit_field_is_mandatory(scope, key):
    args, _ = scope
    setattr(args, key, "")
    with pytest.raises(acceptance.Refused):
        acceptance.authorize(args)


@pytest.mark.parametrize("namespace", ["dev-luban-aiops", "default", "kube-system", "", "--all-namespaces", "spec063-x/dev"])
def test_shared_or_malformed_namespace_refused(scope, namespace):
    args, _ = scope
    args.namespace = namespace
    with pytest.raises(acceptance.Refused):
        acceptance.authorize(args)


@pytest.mark.parametrize("key,value", [
    ("origin", "http://acme-admin.dev-luban-aiops:8080"), ("target_user", "carol"),
    ("approver", "luban-operator"), ("context", "another-cluster"),
    ("epoch", "spec063-acceptance-e1"),
])
def test_scope_drift_refused(scope, key, value):
    args, _ = scope
    setattr(args, key, value)
    with pytest.raises(acceptance.Refused):
        acceptance.authorize(args)


@pytest.mark.parametrize("key,value", [
    ("authorized", False), ("authorized", "true"), ("paths", ["normal"]),
    ("actions", ["lock"]), ("target_restart_allowed", True),
    ("keycloak_reconciliation_allowed", True), ("scenario", "F-01"),
])
def test_authorization_constraints_are_typed_and_exact(scope, key, value):
    args, record = scope
    record[key] = value
    Path(args.authorization).write_text("```json\n" + json.dumps(record) + "\n```\n")
    with pytest.raises(acceptance.Refused):
        acceptance.authorize(args)


@pytest.mark.parametrize("raw", ["", "not-json", "```json\n[]\n```", "```json\nnull\n```", "x" * 65537])
def test_missing_or_malformed_record_refused(scope, raw):
    args, _ = scope
    Path(args.authorization).write_text(raw)
    with pytest.raises(acceptance.Refused):
        acceptance.authorize(args)


@pytest.fixture
def setup_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "execution_acceptance", acceptance)
    spec = importlib.util.spec_from_file_location("acceptance_setup", SOURCE.with_name("execution_acceptance_setup.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_secrets_are_fresh_namespaced_and_cross_hop_consistent(setup_module):
    first = setup_module.make_secrets("spec063-acceptance")
    second = setup_module.make_secrets("spec063-acceptance")
    assert first != second
    assert all(o["metadata"]["namespace"] == "spec063-acceptance" for o in first)
    values = {o["metadata"]["name"]: o["stringData"] for o in first}
    creds = json.loads(values["tool-gateway-browser-credentials"]["credential-sets.json"])
    assert creds["acme-admin"]["password"] == values["acme-admin-credentials"]["ACME_ADMIN_PASSWORD"]
    agent = values["agent-platform-runtime-secrets"]
    assert agent["AGENT_EXECUTION_STATE_DB_URL"] == values["execution-runtime-runtime-secrets"]["EXECUTION_STATE_DB_URL"]
    assert agent["ACCEPTANCE_DELEGATION_CLIENT_SECRET"] in values["identity-service-runtime-secrets"]["IDENTITY_SERVICE_CLIENTS"]
    assert not any("OIDC" in k or "KEYCLOAK" in k for obj in values.values() for k in obj)


@pytest.mark.parametrize("kind,name,namespace", [
    ("Namespace", "dev-luban-aiops", None), ("ClusterRole", "shared-role", None),
    ("HTTPRoute", "web-ui", "spec063-acceptance"), ("ConfigMap", "config", "dev-luban-aiops"),
])
def test_render_refuses_shared_resources(scope, setup_module, monkeypatch, kind, name, namespace):
    args, _ = scope
    args.image_tag = "0.42.0-spec063-test"
    args.overlay = str(setup_module.ROOT / ".workspaces/spec063-acceptance/gitops")
    obj = {"kind": kind, "metadata": {"name": name, "namespace": namespace}}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(obj)))
    with pytest.raises(acceptance.Refused):
        setup_module.render(args)


@pytest.fixture
def live_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "execution_acceptance", acceptance)
    spec = importlib.util.spec_from_file_location("acceptance_live", SOURCE.with_name("execution_acceptance_live.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("field,value", [("started_at", "changed"), ("hostname", "restarted"),
                                         ("store_revision", 2), ("peers", ["changed"])])
def test_independent_target_reconciliation_rejects_drift(live_module, field, value):
    before = {"started_at": "initial", "hostname": "one-pod", "peers": [], "store_revision": 0,
              "user": {"revision": 0}}
    after = {**before, "store_revision": 1, "user": {"revision": 1}, field: value}
    with pytest.raises(acceptance.Refused):
        live_module.check_target(before, after, 1)


def test_preflight_failure_retains_evidence_and_unexecuted_paths(live_module, scope, monkeypatch, tmp_path):
    args, _ = scope
    monkeypatch.setattr(live_module, "ROOT", tmp_path)

    def fail(*a, **k):
        raise acceptance.Refused("injected preflight failure")

    cluster = SimpleNamespace(args=args, assert_isolation=fail, command=fail, probe=fail)
    assert live_module.run_campaign(cluster, "authorization-digest") == 1
    evidence = next(tmp_path.glob(".workspaces/spec063-evidence/s6-*/evidence.json"))
    report = json.loads(evidence.read_text())
    assert not report["acceptance_passed"] and not report["delivery_complete"]
    assert len(report["results"]) == 5
    assert {r["status"] for r in report["results"]} == {"not_run"}
    assert "injected preflight failure" == report["failure"]


@pytest.fixture
def held_probe(monkeypatch):
    """Run the probe's exact function with product buffer semantics, no cluster."""
    import ast
    import asyncio

    path = acceptance.ROOT / "products/tool-gateway/src/tool_gateway/tools/secret_delivery.py"
    spec = importlib.util.spec_from_file_location("acceptance_test_buffer", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    buffer = module.InMemorySecretDeliveryBuffer()
    events, generated = [], []
    faults = {}

    def response(status, body):
        return SimpleNamespace(status_code=status, json=lambda: body)

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, *, headers, json):
            assert json["tool_name"] == "secrets.generate_password"
            value = "fixture-only-" + str(len(generated))
            handle = buffer.stash(value, "operator", None, 900)
            generated.append((handle, value))
            return response(200, {"status": "success", "data": {
                "generated_password": value, "delivery_id": handle,
                "channel": "portal_copy", "expires_at": "fixture-expiry"}})

        def get(self, url, *, headers):
            handle, owner = url.rsplit("/", 1)[1], headers["Authorization"].split()[1]
            events.append((handle, owner))
            value = buffer.redeem(handle, owner)
            if faults.get("wrong_owner") and owner == "approver":
                return response(200, {"value": "unexpected"})
            if faults.get("replay") and value is None and owner == "operator":
                return response(200, {"value": "unexpected"})
            if value is not None and faults.get("http"):
                return response(503, {})
            if value is not None and faults.get("value"):
                value = "mismatched"
            return response(404 if value is None else 200, {"value": value})

        def delete(self, url, *, headers):
            buffer.discard(url.rsplit("/", 1)[1], "operator")
            return response(204, {})

    async def invoke(data, envelope, attempt, args, held):
        return {"release_count": 0 if data["path"] == "replay" else 1, "second_release": False}

    namespace = {"asyncio": asyncio, "json": json, "httpx": SimpleNamespace(Client=Client),
                 "token": lambda username, role: role,
                 "parameters": lambda data, value: {"body": {"password": value}},
                 "prepare": lambda data, args: ({}, "attempt"), "invoke": invoke}
    tree = ast.parse(SOURCE.with_name("execution_acceptance_probe.py").read_text())
    selected = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
                               and n.name in {"require", "held_secret"}], type_ignores=[])
    exec(compile(selected, str(SOURCE.with_name("execution_acceptance_probe.py")), "exec"), namespace)
    data = {"operator": "operator", "approver": "approver", "path": "held-secret"}
    return SimpleNamespace(run=lambda: namespace["held_secret"](data), events=events,
                           generated=generated, buffer=buffer, faults=faults)


def test_held_secret_uses_distinct_owner_and_destructive_probe_handles(held_probe):
    result = held_probe.run()
    assert result["redeemed_once"] and result["wrong_owner_burned"]
    assert result["replay_release_count"] == 0
    first, second = [h for h, _ in held_probe.generated]
    assert first != second
    assert held_probe.events == [(first, "operator"), (first, "operator"),
                                 (second, "approver"), (second, "operator")]
    assert len(held_probe.buffer) == 0
    assert all(value not in json.dumps(result) and handle not in json.dumps(result)
               for handle, value in held_probe.generated)


@pytest.mark.parametrize("fault,code", [("wrong_owner", "secret_owner"), ("replay", "secret_spent"),
                                       ("http", "secret_redemption_http_503"), ("value", "secret_redemption_value")])
def test_held_secret_detects_redemption_failures(held_probe, fault, code):
    held_probe.faults[fault] = True
    with pytest.raises(AssertionError, match=code):
        held_probe.run()
    assert len(held_probe.buffer) == 0


@pytest.mark.parametrize("drift", [None, "target", "wire", "claim"])
def test_reconciliation_preserves_failed_campaign_and_rejects_drift(
        setup_module, live_module, scope, monkeypatch, tmp_path, drift):
    args, _ = scope
    monkeypatch.setitem(sys.modules, "execution_acceptance_live", live_module)
    monkeypatch.setattr(setup_module, "ROOT", tmp_path)
    state_path = tmp_path / "setup.json"
    monkeypatch.setattr(setup_module, "STATE", state_path)
    state_path.write_text(json.dumps({"namespace": args.namespace, "context": args.context,
                                     "authorization_sha256": "digest", "namespace_uid": "owned",
                                     "keycloak_changes": []}))

    def target(revision):
        return {"started_at": "same", "hostname": "same", "peers": [], "store_revision": revision,
                "user": {"revision": revision}}

    def wire(count):
        return {"boot_id": "same", "attempts": count, "completed": count,
                "held": False, "block_next": False}

    files = {}
    for number, passed in enumerate((False, True)):
        directory = tmp_path / ".workspaces/spec063-evidence" / ("s6-" + str(number))
        directory.mkdir(parents=True)
        row = {"path": "held-secret", "status": "passed" if passed else "failed",
               "wire_before": wire(number), "wire_after": wire(number + 1)}
        if passed:
            row["facts"] = {"execution_id": "execution-1"}
        report = {"namespace_uid": "owned", "authorization_sha256": "digest",
                  "acceptance_passed": passed, "initial_target": target(number), "results": [row],
                  "final_target" if passed else "target_after_failure": target(number + 1)}
        if not passed:
            report["wire_after_failure"] = wire(number + 1)
        for name, text in (("evidence.json", json.dumps(report)), ("junit.xml", "<testsuite/>")):
            file = directory / name
            file.write_text(text)
            files[file] = file.read_bytes()
    inventory = [{"execution_id": "execution-" + str(i), "claims": 1,
                  "card_status": "approved", "card_decider": args.approver} for i in range(2)]
    if drift == "claim":
        inventory[0]["claims"] = 2
    cluster = SimpleNamespace(namespace_uid="owned", assert_isolation=lambda: None,
                              probe=lambda op: wire(3 if drift == "wire" else 2) if op == "wire"
                              else {"executions": inventory})
    monkeypatch.setattr(setup_module, "Cluster", lambda args: cluster)
    monkeypatch.setattr(live_module, "target", lambda cluster: target(3 if drift == "target" else 2))
    if drift:
        with pytest.raises(acceptance.Refused):
            setup_module.reconcile(args, "digest")
    else:
        setup_module.reconcile(args, "digest")
        result = json.loads((tmp_path / ".workspaces/spec063-evidence/s6-reconciliation-owned.json").read_text())
        assert [c["acceptance_passed"] for c in result["campaigns"]] == [False, True]
        assert result["total_claims"] == 2 and result["counts_reconciled"]
        assert result["supplemental_execution_ids"] == ["execution-0"]
        assert not result["delivery_complete"]
    assert all(file.read_bytes() == contents for file, contents in files.items())
