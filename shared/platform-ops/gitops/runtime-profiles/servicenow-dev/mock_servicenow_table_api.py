#!/usr/bin/env python3
"""Thin mock ServiceNow Table-API + OAuth token responder (SPEC-067 R-6).

This is a *stand-in* for a real ServiceNow instance's REST surface — the
``/api/now/table/...`` Table API and the ``/oauth_token.do`` OAuth2
``client_credentials`` token endpoint (OQ-1's pinned scheme). It exists so the
dev-k8s overlay can exercise the tool-gateway's native ``servicenow_native``
connector end to end **without a licensed PDI and without any live external
call** (OQ-5): CI validates the connector against a real HTTP target it fully
controls.

It is deliberately thin, and faithful on the three things that actually matter:

* **OAuth2 ``client_credentials``** — ``POST /oauth_token.do`` accepts the
  ``application/x-www-form-urlencoded`` grant the gateway's SPEC-068 token client
  sends (``grant_type=client_credentials`` + HTTP-Basic ``client_id:client_secret``)
  and returns ``{"access_token", "token_type": "bearer", "expires_in"}``. This is
  the deployed counterpart to the in-process token-client tests.
* **Table API** — ``GET /api/now/table/{table}[/{sys_id}]`` returns the canned
  ``{"result": ...}`` envelope the connector parses: a list for a collection read,
  a single object for a ``sys_id`` read. The six admitted tables
  (``incident``/``change_request``/``sys_user``/``cmdb_ci``) resolve unchanged
  against this mock and against a real instance; swapping the mock for a live PDI
  is an overlay-config change (a new ``GATEWAY_SERVICENOW_BASE_URL`` +
  ``token_url``), never a connector-code change.
* **Bearer gate** — every Table-API request must carry
  ``Authorization: Bearer <access_token>``, the very token ``/oauth_token.do``
  issued, mirroring production so the connector's credential path is exercised
  for real.

Everything returned is canned and secret-free: a couple of incidents, change
requests, a user, and a CMDB CI. It mutates nothing — no POST/PUT/PATCH/DELETE
route exists, mirroring the read-only binding — and it fabricates no record: an
unknown table or ``sys_id`` is a real ``404`` (which the connector maps to a
failed outcome, never an empty success — R-5's inverse-of-``http.get`` rule).

Auth fails closed. ``client_id``/``client_secret``/``access_token`` are read from
the ``servicenow-mock-credentials`` secret that ``sync-servicenow-credentials.sh``
writes (one generator / two sinks — the gateway's credential-set file carries the
same client_id/client_secret/token_url). If those files are absent the server
still starts but adopts unguessable random values, so every call fails closed
(401) until the credential is provisioned; it never runs open.

This file is mounted into the tool-gateway image (which already ships
``starlette``/``uvicorn`` as runtime deps) as a ConfigMap and run as a separate
Deployment, so the gateway connects to it over the Service network exactly as it
would a real external ServiceNow instance. It is dev infrastructure and is not
part of the gateway's own request surface.
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

# --- canned records: the "mock tenant" the read tools return ----------------
# Static, secret-free data with realistic 32-char hex sys_ids so a list read
# yields an id a subsequent get read can resolve. Nothing here is a real
# credential, so a redaction assertion in the live-check is about the *client
# secret / access token never leaking back*, not about masking these values.

_INCIDENTS = [
    {
        "sys_id": "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
        "number": "INC0010001", "short_description": "Mock: DB latency spike",
        "state": "2", "priority": "2", "severity": "2", "impact": "2",
        "urgency": "2", "category": "database",
        "assignment_group": "DB Support", "assigned_to": "Mock Operator",
        "opened_at": "2026-10-01 08:00:00", "updated_at": "2026-10-01 09:30:00",
        "closed_at": "", "cmdb_ci": "Mock DB Cluster",
    },
    {
        "sys_id": "b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2",
        "number": "INC0010002", "short_description": "Mock: portal 502s",
        "state": "1", "priority": "1", "severity": "1", "impact": "1",
        "urgency": "1", "category": "network",
        "assignment_group": "Network Ops", "assigned_to": "Mock Net Eng",
        "opened_at": "2026-10-02 10:15:00", "updated_at": "2026-10-02 10:20:00",
        "closed_at": "", "cmdb_ci": "Mock Edge LB",
    },
]

_CHANGE_REQUESTS = [
    {
        "sys_id": "c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3",
        "number": "CHG0020001", "short_description": "Mock: DB failover drill",
        "state": "-5", "type": "standard", "priority": "3", "risk": "low",
        "impact": "low", "start_date": "2026-10-05 02:00:00",
        "end_date": "2026-10-05 04:00:00", "requested_by": "Mock Change Mgr",
        "assignment_group": "DB Support", "cmdb_ci": "Mock DB Cluster",
    },
]

_USERS = [
    {
        "sys_id": "d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4",
        "user_name": "mock.operator", "name": "Mock Operator",
        "email": "mock.operator@example.com", "title": "Site Reliability Eng",
        "department": "Operations", "active": "true", "manager": "Mock Manager",
        # Deliberately carries credential columns the binding's _USER_FIELDS
        # allowlist omits. The mock ignores sysparm_fields and returns them, so
        # the connector's post-response projection is what strips them — the
        # live-check asserts neither key survives into a tool result, proving the
        # allowlist is defense-in-depth and not merely a request hint.
        "password": "mock-never-returned-1",
        "user_password": "mock-never-returned-2",
    },
]

_CMDB_CIS = [
    {
        "sys_id": "e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5",
        "name": "Mock DB Cluster", "sys_class_name": "cmdb_ci_db_instance",
        "ci_class_id": "db", "operational_status": "1", "install_status": "1",
        "ip_address": "10.0.0.21", "mac_address": "",
        "support_group": "DB Support", "assigned_to": "Mock Operator",
    },
]

_TABLES: dict[str, list[dict]] = {
    "incident": _INCIDENTS,
    "change_request": _CHANGE_REQUESTS,
    "sys_user": _USERS,
    "cmdb_ci": _CMDB_CIS,
}


def _read_secret(name: str, fallback: str) -> str:
    """Read one credential from the mounted secret dir; fail closed if absent.

    An absent/empty/unreadable file yields an unguessable random value, so no
    caller can authenticate until ``sync-servicenow-credentials.sh`` provisions
    the secret and the pod restarts — the mock never silently runs open.
    """
    directory = os.getenv("SERVICENOW_MOCK_CRED_DIR", "/etc/luban/servicenow-mock")
    path = os.path.join(directory, name)
    try:
        with open(path, encoding="utf-8") as handle:
            value = handle.read().strip()
        if value:
            return value
    except OSError:
        pass
    return fallback


# Resolved once at startup (the sync script restarts the pod to rotate them).
_CLIENT_ID = _read_secret("client-id", "mock-client-" + secrets.token_hex(8))
_CLIENT_SECRET = _read_secret("client-secret", secrets.token_urlsafe(32))
_ACCESS_TOKEN = _read_secret("access-token", secrets.token_urlsafe(32))


def _basic_credentials(request: Request) -> tuple[str, str] | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    client_id, _, client_secret = decoded.partition(":")
    return client_id, client_secret


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


async def oauth_token(request: Request) -> Response:
    """OAuth2 ``client_credentials`` grant (mirrors ``/oauth_token.do``)."""
    form = await request.form()
    if form.get("grant_type") != "client_credentials":
        return JSONResponse(
            {"error": "unsupported_grant_type"}, status_code=400
        )
    creds = _basic_credentials(request)
    # client_secret_post is also accepted so either SPEC-068 variant works.
    if creds is None:
        posted_id = form.get("client_id")
        posted_secret = form.get("client_secret")
        creds = (posted_id, posted_secret) if posted_id else None
    if creds is None or creds[0] != _CLIENT_ID or creds[1] != _CLIENT_SECRET:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    return JSONResponse({
        "access_token": _ACCESS_TOKEN,
        "token_type": "bearer",
        "expires_in": 1799,
        "scope": "useraccount",
    })


async def _require_bearer(request: Request) -> Response | None:
    if _bearer(request) != _ACCESS_TOKEN:
        return JSONResponse(
            {"error": {"message": "Unauthorized", "status": "failed"}},
            status_code=401,
        )
    return None


async def list_table(request: Request) -> Response:
    """``GET /api/now/table/{table}`` — a bounded collection read."""
    denied = await _require_bearer(request)
    if denied is not None:
        return denied
    table = request.path_params["table"]
    records = _TABLES.get(table)
    if records is None:
        return JSONResponse(
            {"error": {"message": f"No such table: {table}"}}, status_code=404
        )
    limit_raw = request.query_params.get("sysparm_limit")
    try:
        limit = int(limit_raw) if limit_raw else len(records)
    except ValueError:
        limit = len(records)
    return JSONResponse({"result": records[: max(0, limit)]})


async def get_table_record(request: Request) -> Response:
    """``GET /api/now/table/{table}/{sys_id}`` — one record by sys_id."""
    denied = await _require_bearer(request)
    if denied is not None:
        return denied
    table = request.path_params["table"]
    sys_id = request.path_params["sys_id"]
    records = _TABLES.get(table)
    if records is None:
        return JSONResponse(
            {"error": {"message": f"No such table: {table}"}}, status_code=404
        )
    record = next((r for r in records if r.get("sys_id") == sys_id), None)
    if record is None:
        return JSONResponse(
            {"error": {"message": "No Record found"}}, status_code=404
        )
    return JSONResponse({"result": record})


def build_app() -> Starlette:
    return Starlette(routes=[
        Route("/oauth_token.do", oauth_token, methods=["POST"]),
        Route("/api/now/table/{table}", list_table, methods=["GET"]),
        Route("/api/now/table/{table}/{sys_id}", get_table_record, methods=["GET"]),
    ])


def main() -> None:
    host = os.getenv("SERVICENOW_MOCK_HOST", "0.0.0.0")
    port = int(os.getenv("SERVICENOW_MOCK_PORT", "8000"))
    uvicorn.run(build_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
