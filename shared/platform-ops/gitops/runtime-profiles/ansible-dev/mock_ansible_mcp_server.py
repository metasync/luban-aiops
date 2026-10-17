#!/usr/bin/env python3
"""Thin mock Ansible MCP server (SPEC-069 R-6) — the in-cluster dev/CI target.

This is a *stand-in* for the production Ansible MCP server
(``ansible/aap-mcp-server``, Apache-2.0; streamable-HTTP at ``/mcp`` +
``Authorization: Bearer``). It exists so the dev-k8s overlay can exercise the
tool-gateway's server-agnostic MCP-ingestion connector end to end **without a
licensed AAP instance and without any live external call** (OQ-5): CI validates
the connector against a real ``mcp`` SDK server it fully controls.

It is deliberately thin, and faithful on the two things that actually matter:

* **Transport** — a real ``mcp`` SDK ``MCPServer`` served over streamable-HTTP
  at ``/mcp``, the same wire the connector speaks to production AAP. This is the
  deployed counterpart to the in-process Layer-2 wire test
  (``products/tool-gateway/tests/test_ansible_mcp_streamable_http.py``).
* **Tool surface** — the ``controller.*`` read tools the gateway's Ansible
  binding (``ingestion/ansible_binding.py``) dispatches to, so the *same*
  ``ANSIBLE_ADMITTED_TOOLS`` config resolves unchanged against this mock and
  against real AAP. Swapping the mock for ``aap-mcp-server`` (production) or
  ``lycorp-jp/awx-mcp`` (open-source AWX) is an overlay-config change — a new
  ``GATEWAY_ANSIBLE_MCP_URL`` and, where the server's tool names differ, a new
  ``server_name``/``argument_map`` binding — never an adapter-code change.

Everything returned is canned: a small inventory with two **mock managed
hosts**, one job template, and one completed job. It mutates nothing — no
launch/update tool is exposed, mirroring the binding, which admits read tools
only — and it gathers no real facts, mirroring the binding's honest "no
host-facts tool admitted" gap rather than faking one (OQ-5 "defer, don't fake").

Auth mirrors production: every HTTP request must carry
``Authorization: Bearer <token>``, where ``<token>`` is read from the file named
by ``ANSIBLE_MOCK_BEARER_FILE`` (mounted from the ``ansible-mock-credentials``
secret that ``sync-ansible-credentials.sh`` writes, one generator / two sinks —
the gateway's credential-set file carries the same token). If that file is
absent or empty the server still starts but adopts an unguessable random token,
so every call fails closed (401) until the credential is provisioned; it never
runs open.

DNS-rebinding protection (a browser-oriented ``Host``/``Origin`` control in the
``mcp`` SDK) is disabled explicitly: this mock is cluster-internal, reachable
only through a NetworkPolicy that admits the tool-gateway pod, and guarded by
the bearer gate above — the relevant controls here, not ``Host`` validation.

This file is mounted into the tool-gateway image (which already ships
``mcp``/``starlette``/``uvicorn`` as runtime deps) as a ConfigMap and run as a
separate Deployment, so the gateway connects to it over the Service network
exactly as it would a real external MCP server. It is dev infrastructure and is
not part of the gateway's own request surface.
"""

from __future__ import annotations

import os
import secrets

import uvicorn
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

# --- canned topology: the "mock managed host" the read tools return ---------
# Static, secret-free data. Nothing here is a real credential, so a redaction
# assertion in the live-check is about the *bearer never leaking back*, not
# about masking these values.

_INVENTORIES = [
    {"id": 1, "name": "demo", "organization": "Default", "total_hosts": 2},
    {"id": 2, "name": "prod", "organization": "Default", "total_hosts": 0},
]

_INVENTORY_DETAIL = {
    "demo": {
        "id": 1,
        "name": "demo",
        "organization": "Default",
        "groups": ["webservers", "db"],
        "hosts": [
            {"name": "mock-host-01", "groups": ["webservers"],
             "ansible_host": "10.0.0.11", "managed": True},
            {"name": "mock-host-02", "groups": ["db"],
             "ansible_host": "10.0.0.12", "managed": True},
        ],
    },
    "prod": {
        "id": 2, "name": "prod", "organization": "Default",
        "groups": [], "hosts": [],
    },
}

_JOB_TEMPLATES = [
    {"id": 10, "name": "Deploy App", "project": "demo-project",
     "playbook": "deploy.yml"},
    {"id": 11, "name": "Health Check", "project": "demo-project",
     "playbook": "health.yml"},
]

_JOBS = {
    "1": {"id": 1, "name": "Deploy App", "status": "successful",
          "job_template": 10, "inventory": "demo"},
}

_JOB_STDOUT = {
    "1": [
        "PLAY [Deploy App] ***************************************",
        "TASK [Gathering Facts] **********************************",
        "ok: [mock-host-01]",
        "TASK [Install package] **********************************",
        "changed: [mock-host-01]",
        "PLAY RECAP **********************************************",
        "mock-host-01 : ok=2 changed=1 unreachable=0 failed=0",
    ],
}


def _filter(items: list[dict], name_filter: str, limit: int) -> list[dict]:
    """Apply the binding's optional ``name_filter``/``limit`` to a canned list."""
    if name_filter:
        needle = name_filter.lower()
        items = [i for i in items if needle in str(i.get("name", "")).lower()]
    if limit and limit > 0:
        items = items[:limit]
    return items


def build_server() -> MCPServer:
    """Expose the six ``controller.*`` read tools the Ansible binding admits.

    Tool names and argument names match ``ANSIBLE_ADMITTED_TOOLS`` exactly
    (``argument_map`` is empty for every entry), so the gateway projects its
    validated parameters straight onto these signatures.
    """
    server = MCPServer("ansible-mock-mcp")

    @server.tool(name="controller.inventories_list",
                 description="List Ansible inventories.")
    def inventories_list(name_filter: str = "", limit: int = 100) -> dict:
        results = _filter(_INVENTORIES, name_filter, limit)
        return {"count": len(results), "results": results}

    @server.tool(name="controller.inventories_read",
                 description="Get one inventory's hosts and groups.")
    def inventories_read(inventory: str) -> dict:
        detail = _INVENTORY_DETAIL.get(inventory) or next(
            (d for d in _INVENTORY_DETAIL.values()
             if str(d["id"]) == str(inventory)), None)
        if detail is None:
            return {"error": "not_found", "inventory": inventory}
        return detail

    @server.tool(name="controller.job_templates_list",
                 description="List Ansible job templates.")
    def job_templates_list(name_filter: str = "", limit: int = 100) -> dict:
        results = _filter(_JOB_TEMPLATES, name_filter, limit)
        return {"count": len(results), "results": results}

    @server.tool(name="controller.jobs_read",
                 description="Get one job's details and status.")
    def jobs_read(job_id: str) -> dict:
        job = _JOBS.get(str(job_id))
        return job if job is not None else {"error": "not_found", "job_id": job_id}

    @server.tool(name="controller.jobs_stdout_retrieve",
                 description="Retrieve a job's stdout, optionally tail-bounded.")
    def jobs_stdout_retrieve(job_id: str, tail: int = 0) -> dict:
        lines = _JOB_STDOUT.get(str(job_id))
        if lines is None:
            return {"error": "not_found", "job_id": job_id}
        if tail and tail > 0:
            lines = lines[-tail:]
        return {"job_id": job_id, "stdout": "\n".join(lines)}

    @server.tool(name="controller.ping_list",
                 description="Report control-plane health.")
    def ping_list() -> dict:
        return {"status": "healthy",
                "instances": [{"node": "ansible-mock-mcp", "heartbeat": "ok"}]}

    return server


class BearerGate:
    """Pure-ASGI wrapper requiring ``Authorization: Bearer <token>`` on HTTP.

    Non-HTTP scopes (``lifespan``) pass through untouched so uvicorn still runs
    the session-manager lifespan. Mirrors the production server's bearer
    requirement so the connector's credential path is exercised for real.
    """

    def __init__(self, app, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if auth != f"Bearer {self._token}":
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"unauthorized"})
            return
        await self._app(scope, receive, send)


def _read_token() -> str:
    """Read the required bearer from the mounted secret; fail closed if absent.

    An absent/empty/unreadable file yields an unguessable random token, so no
    caller can authenticate until ``sync-ansible-credentials.sh`` provisions the
    secret and the pod restarts — the mock never silently runs open.
    """
    path = os.getenv("ANSIBLE_MOCK_BEARER_FILE", "")
    if path:
        try:
            with open(path, encoding="utf-8") as handle:
                token = handle.read().strip()
            if token:
                return token
        except OSError:
            pass
    return secrets.token_urlsafe(32)


def main() -> None:
    host = os.getenv("ANSIBLE_MOCK_HOST", "0.0.0.0")
    port = int(os.getenv("ANSIBLE_MOCK_PORT", "8000"))
    app = BearerGate(
        build_server().streamable_http_app(
            streamable_http_path="/mcp",
            host=host,
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=False),
        ),
        _read_token(),
    )
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
