"""SPEC-069 R-6 Layer-2: real streamable-HTTP wire fidelity (no fake opener).

The unit tests in ``test_ansible_mcp_ingestion.py`` inject a *fake* session
opener, so they prove the adapter's logic (admission, argument validation,
fail-closed mapping, redaction, audit) but never touch the real MCP transport.
This module closes the one gap the thin in-cluster mock cannot: it stands up a
**real ``mcp`` SDK server** (``MCPServer`` over ``streamable_http_app``) on a
loopback port and drives the connector's **production** ``_open_mcp_session``
against it — the same code path that talks to ``ansible/aap-mcp-server``.

What this proves that a fake opener cannot:

* the streamable-HTTP handshake + ``initialize`` + ``call_tool`` round-trip
  works against an independently-run MCP server implementation;
* the bearer token actually rides the wire in the ``Authorization`` header (and
  never appears in the tool result);
* gateway-owned argument projection reaches the server's real input schema;
* a missing bearer, an unreachable endpoint, and a tool the server does not
  expose all **fail closed** as a structured error — never a fabricated success.

Everything is loopback-only and in-process, so CI still makes no live *external*
call (OQ-5). The server speaks the read tools the Ansible binding dispatches to
(``controller.inventories_list`` / ``controller.ping_list``), so the *same*
``ANSIBLE_ADMITTED_TOOLS`` config is exercised end to end.
"""

from __future__ import annotations

import asyncio
import json
import socket
import tempfile
import threading
import time
import unittest

import uvicorn
from mcp.server import MCPServer

from tool_gateway.ingestion.ansible_binding import ANSIBLE_ADMITTED_TOOLS
from tool_gateway.ingestion.mcp_adapter import McpIngestionConnector, McpTransport
from tool_gateway.tools.registry import ToolRegistry

# A fixed loopback bearer the mock server requires; the credential set below
# resolves to it through the SPEC-068 seam, exactly as production would.
_TOKEN = "L2-mock-bearer-xyz"
# Authorization headers the server actually saw, so a test can assert the token
# rode the real wire. Cleared per test; appended from the server thread.
_SEEN_AUTH: list[str] = []


def _free_port() -> int:
    """Grab an ephemeral loopback port (bind-then-release)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_mock_server() -> MCPServer:
    """A real MCP server exposing the two read tools the binding dispatches to.

    The tool names mirror AAP's ``controller.*`` OpenAPI operationIds so the
    production ``ANSIBLE_ADMITTED_TOOLS`` binding resolves unchanged.
    """
    server = MCPServer("ansible-mock")

    @server.tool(name="controller.inventories_list",
                 description="List Ansible inventories.")
    def _inventories(limit: int = 100, name_filter: str = "") -> dict:
        # Echo ``limit`` so the test can assert argument projection over the wire.
        return {"inventories": ["demo", "prod"], "echo_limit": limit}

    @server.tool(name="controller.ping_list",
                 description="Report control-plane health.")
    def _ping() -> dict:
        return {"status": "healthy", "instances": 1}

    return server


class _BearerGate:
    """Pure-ASGI wrapper requiring ``Authorization: Bearer <token>`` on HTTP.

    Records every Authorization header seen. Non-HTTP scopes (``lifespan``) pass
    through untouched so uvicorn still runs the session-manager lifespan.
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
        _SEEN_AUTH.append(auth)
        if auth != f"Bearer {self._token}":
            await send({
                "type": "http.response.start", "status": 401,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({"type": "http.response.body", "body": b"unauthorized"})
            return
        await self._app(scope, receive, send)


def _payload(data) -> dict:
    """Unwrap a result envelope to the server's dict, structured or text-JSON."""
    if not isinstance(data, dict):
        return {}
    text = data.get("text")
    if isinstance(text, str):
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return data
        if isinstance(parsed, dict):
            return parsed
    return data


def _cred_file(payload: dict) -> str:
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(payload, handle)
    handle.close()
    return handle.name


def _run(coro):
    return asyncio.run(coro)


class StreamableHttpWireTests(unittest.TestCase):
    """Drive the connector's real transport against a real MCP server."""

    @classmethod
    def setUpClass(cls) -> None:
        app = _BearerGate(
            _build_mock_server().streamable_http_app(
                streamable_http_path="/mcp", host="127.0.0.1"),
            _TOKEN,
        )
        cls._port = _free_port()
        config = uvicorn.Config(
            app, host="127.0.0.1", port=cls._port, log_level="warning")
        cls._server = uvicorn.Server(config)
        cls._thread = threading.Thread(target=cls._server.run, daemon=True)
        cls._thread.start()
        deadline = time.time() + 15
        while not cls._server.started and time.time() < deadline:
            time.sleep(0.05)
        if not cls._server.started:  # pragma: no cover - startup failure
            raise RuntimeError("mock MCP server did not start")
        cls._url = f"http://127.0.0.1:{cls._port}/mcp"
        cls._cred_path = _cred_file(
            {"ansible-mock": {"scheme": "bearer", "token": _TOKEN}})

    @classmethod
    def tearDownClass(cls) -> None:
        cls._server.should_exit = True
        cls._thread.join(timeout=15)

    def setUp(self) -> None:
        _SEEN_AUTH.clear()

    def _connector(self, *, with_token: bool, url: str | None = None):
        kwargs = {}
        if with_token:
            kwargs = {"credential_set": "ansible-mock",
                      "credential_sets_path": self._cred_path}
        return McpIngestionConnector(
            transport=McpTransport(
                kind="streamable_http", url=url or self._url, timeout_ms=8000),
            admitted=ANSIBLE_ADMITTED_TOOLS,
            source_system="ansible",
            **kwargs,
        )

    def _registry(self, connector) -> ToolRegistry:
        registry = ToolRegistry()
        connector.register_tools(registry)
        return registry

    def test_real_roundtrip_returns_server_data_and_bearer_rides_wire(self) -> None:
        registry = self._registry(self._connector(with_token=True))
        result = _run(registry.invoke("ansible.list_inventories", {}, {}))
        self.assertEqual(result.status, "success", result.error)
        self.assertIn("demo", _payload(result.data).get("inventories", []))
        # The bearer reached the server over the real transport...
        self.assertIn(f"Bearer {_TOKEN}", _SEEN_AUTH)
        # ...and never leaked into the tool-result envelope.
        self.assertNotIn(_TOKEN, json.dumps(result.to_dict()))

    def test_argument_projection_reaches_the_real_server_schema(self) -> None:
        registry = self._registry(self._connector(with_token=True))
        result = _run(registry.invoke("ansible.list_inventories", {"limit": 5}, {}))
        self.assertEqual(result.status, "success", result.error)
        self.assertEqual(_payload(result.data).get("echo_limit"), 5)

    def test_second_admitted_tool_dispatches_to_its_own_server_name(self) -> None:
        registry = self._registry(self._connector(with_token=True))
        result = _run(registry.invoke("ansible.get_environment_health", {}, {}))
        self.assertEqual(result.status, "success", result.error)
        self.assertEqual(_payload(result.data).get("status"), "healthy")

    def test_missing_bearer_fails_closed_not_a_success(self) -> None:
        registry = self._registry(self._connector(with_token=False))
        result = _run(registry.invoke("ansible.list_inventories", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "MCP_TRANSPORT_ERROR")

    def test_unreachable_endpoint_fails_closed_not_a_success(self) -> None:
        dead = f"http://127.0.0.1:{_free_port()}/mcp"
        registry = self._registry(self._connector(with_token=True, url=dead))
        result = _run(registry.invoke("ansible.list_inventories", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "MCP_TRANSPORT_ERROR")

    def test_admitted_tool_absent_on_server_is_a_structured_error(self) -> None:
        # ``ansible.get_job`` -> ``controller.jobs_read``, which the mock does not
        # expose: over the real wire this is a structured error, never a success.
        registry = self._registry(self._connector(with_token=True))
        result = _run(registry.invoke("ansible.get_job", {"job_id": "1"}, {}))
        self.assertEqual(result.status, "error")
        self.assertIn(
            result.error["code"], {"MCP_TOOL_ERROR", "MCP_TRANSPORT_ERROR"})


if __name__ == "__main__":
    unittest.main()
