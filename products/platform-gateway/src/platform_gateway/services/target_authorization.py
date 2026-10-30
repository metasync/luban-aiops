"""Browser-bound target authorization. No tool dispatch or retained human tokens."""
from __future__ import annotations

import asyncio
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

import httpx
from fastapi import HTTPException, Request, Response
from opentelemetry.instrumentation.utils import suppress_http_instrumentation
from pydantic import AwareDatetime, BaseModel, ConfigDict, SecretStr

from platform_gateway.core.config import PlatformGatewaySettings
from platform_gateway.schemas.authorization import (
    AuthorizationStartResponse, AuthorizationStatusResponse, UUID4_PATTERN,
)
from platform_gateway.services.delegation_client import obtain_delegated_token
from platform_gateway.services.gateway_service import enforce_policy, get_session
from platform_gateway.services.token_verifier import (
    HumanIdentityRequired, TokenVerificationError, verify_token,
)

BASE = "/api/v1/targets/authorizations"
INTERNAL = "/api/v2/targets/authorizations"
COOKIE_PREFIX = "__Host-luban-oauth-"
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}
_UUID = re.compile(UUID4_PATTERN)
_COOKIE_SECRET = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_DENIALS = frozenset({"access_denied", "interaction_required", "login_required", "consent_required",
    "invalid_request", "invalid_scope", "unauthorized_client", "unsupported_response_type",
    "server_error", "temporarily_unavailable"})


class _Start(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    start_token: SecretStr
    expires_at: AwareDatetime


class _Provider(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    provider_url: SecretStr
    expires_at: AwareDatetime


def _fail(status: int = 400) -> None:
    raise HTTPException(status, "Target authorization unavailable", headers=NO_STORE)


def require_enabled(settings: PlatformGatewaySettings) -> None:
    if not settings.target_authorization_enabled:
        _fail(403)
    try:
        url = urlsplit(settings.tool_gateway_url)
        if (not settings.require_auth or settings.delegation_audience != "tool-gateway"
                or not Path(settings.authorization_workload_token_path).is_absolute()
                or url.scheme not in {"http", "https"} or not url.hostname
                or url.username is not None or url.password is not None
                or url.query or url.fragment or url.path not in {"", "/"}):
            _fail(503)
    except ValueError:
        _fail(503)


def challenge_id(value: str) -> str:
    if not _UUID.fullmatch(value):
        _fail(404)
    return value


async def no_body(request: Request, *, allow_query: bool = False) -> None:
    if not allow_query and request.scope.get("query_string"):
        _fail()
    async for chunk in request.stream():
        if chunk:
            _fail()


def browser_bindings(request: Request, *, required: bool = False) -> dict[str, str]:
    """Parse raw headers; a cookie dictionary would already have lost duplicates."""
    headers = request.headers.getlist("cookie")
    if len(headers) > 1 or sum(len(h) for h in headers) > 8192:
        _fail()
    jar: dict[str, str] = {}
    seen: set[str] = set()
    raw = headers[0] if headers else ""
    parts = raw.split(";") if raw else []
    if len(parts) > 64:
        _fail()
    for part in parts:
        name, sep, value = part.strip().partition("=")
        if not sep or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or name in seen:
            _fail()
        seen.add(name)
        if any(ord(c) < 33 or ord(c) > 126 for c in value):
            _fail()
        if name.startswith(COOKIE_PREFIX):
            key = name[len(COOKIE_PREFIX):]
            if not _UUID.fullmatch(key) or not _COOKIE_SECRET.fullmatch(value):
                _fail()
            jar[key] = value
    if len(jar) > 8 or (required and not jar):
        _fail()
    return jar


def callback_input(request: Request) -> dict[str, str]:
    raw = request.scope.get("query_string", b"")
    if not raw or len(raw) > 16384:
        _fail()
    try:
        text = raw.decode("ascii")
        if re.search(r"%(?![0-9A-Fa-f]{2})", text):
            _fail()
        pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=True,
                          encoding="utf-8", errors="strict", max_num_fields=8)
    except (ValueError, UnicodeError):
        _fail()
    values: dict[str, str] = {}
    for key, value in pairs:
        if key not in {"state", "code", "error", "error_description", "error_uri"} or key in values:
            _fail()
        if len(value) > (8192 if key == "code" else 4096) or any(ord(c) < 32 or ord(c) == 127 for c in value):
            _fail()
        if key in {"state", "code"} and (not value or any(ord(c) < 33 or ord(c) > 126 for c in value)):
            _fail()
        values[key] = value
    if not values.get("state") or (("code" in values) == ("error" in values)):
        _fail()
    result = {"state": values["state"]}
    if "code" in values:
        if not values["code"].strip():
            _fail()
        result["code"] = values["code"]
    else:
        if not values["error"].strip():
            _fail()
        result["denial"] = values["error"] if values["error"] in _DENIALS else "server_error"
    return result


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid backend response")
        result[key] = value
    return result


async def _request(settings, suffix, bearer, *, method="POST", body=None, expected_status=200):
    """One bounded internal request; never retry, reflect errors, or export secrets."""
    try:
        with suppress_http_instrumentation():
            async with asyncio.timeout(10), _http_client() as client:
                async with client.stream(method, settings.tool_gateway_url.rstrip("/") + INTERNAL + suffix,
                        headers={"Authorization": "Bearer " + bearer, "Accept": "application/json"}, json=body) as response:
                    if response.status_code != expected_status:
                        _fail(response.status_code if response.status_code in {401, 403, 404, 409} else 502)
                    if expected_status == 204:
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                _fail(502)
                        return None
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > 65536:
                            _fail(502)
                        data.extend(chunk)
                    result = json.loads(data, object_pairs_hook=_unique_object)
                    if not isinstance(result, dict):
                        _fail(502)
                    return result
    except HTTPException:
        raise
    except Exception:
        _fail(502)


def _workload(settings) -> str:
    try:
        with Path(settings.authorization_workload_token_path).open("rb") as mount:
            raw = mount.read(16385)
        token = raw.decode("ascii").strip()
        if len(raw) > 16384 or not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            _fail(503)
        return token
    except (OSError, UnicodeError):
        _fail(503)


async def human(request, settings):
    require_enabled(settings)
    headers = request.headers.getlist("authorization")
    if len(headers) != 1 or len(headers[0]) > 16384:
        _fail(401)
    scheme, _, token = headers[0].partition(" ")
    if scheme.lower() != "bearer" or not token or any(c.isspace() for c in token):
        _fail(401)
    try:
        identity = verify_token(settings, token, require_human=True)
    except HumanIdentityRequired:
        _fail(403)
    except (TokenVerificationError, ValueError):
        _fail(401)
    request_id = "req-" + str(uuid4())
    enforce_policy(settings, identity, "targets:authorize", request_id)
    with suppress_http_instrumentation():
        delegated = await obtain_delegated_token(settings, identity.subject, token)
    if not delegated:
        _fail(503)
    return identity, delegated, request_id


async def owned_status(settings, key, identity, bearer, request_id):
    raw = await _request(settings, "/" + key, bearer, method="GET")
    try:
        status = AuthorizationStatusResponse.model_validate(raw)
    except ValueError:
        _fail(502)
    if status.challenge_id != key:
        _fail(404)
    enforce_policy(settings, identity, "session:read", request_id)
    detail = await get_session(settings, request_id, status.session_id, identity.username)
    if detail.get("session_id") != status.session_id or detail.get("user_id") != identity.username:
        _fail(404)
    turns = detail.get("evidence_turns") or []
    if not any(isinstance(frame, dict) and frame.get("type") == "authorization_required"
               and frame.get("auth_challenge_id") == key and frame.get("target") == status.target
               for turn in turns if isinstance(turn, dict)
               for frame in (turn.get("frames") or [])):
        _fail(404)
    return raw, status


def clear_cookie(response: Response, key: str) -> None:
    response.delete_cookie(COOKIE_PREFIX + key, path="/", secure=True, httponly=True, samesite="lax")


def redirect(location: str = "/") -> Response:
    return Response(status_code=302, headers={**NO_STORE, "Location": location})


async def start(request, settings, key):
    key = challenge_id(key)
    await no_body(request)
    jar = browser_bindings(request)
    if key not in jar and len(jar) >= 8:
        _fail(409)
    identity, bearer, request_id = await human(request, settings)
    _, status = await owned_status(settings, key, identity, bearer, request_id)
    remaining = int((status.expires_at - datetime.now(timezone.utc)).total_seconds())
    if remaining <= 0:
        _fail(404)
    if status.status != "pending":
        _fail(409)
    secret = secrets.token_urlsafe(32)
    try:
        reply = _Start.model_validate(await _request(settings, "/" + key + "/start", bearer,
                                                     body={"browser_secret": secret}))
        handle = challenge_id(reply.start_token.get_secret_value())
        if not datetime.now(timezone.utc) < reply.expires_at <= status.expires_at:
            _fail(502)
        public = AuthorizationStartResponse(start_url=BASE + "/start/" + handle, expires_at=reply.expires_at)
    except ValueError:
        _fail(502)
    response = Response(public.model_dump_json(), media_type="application/json", headers=NO_STORE)
    # Account for transport time; never extend the authoritative challenge deadline.
    remaining = min(600, int((status.expires_at - datetime.now(timezone.utc)).total_seconds()))
    if remaining <= 0:
        _fail(404)
    response.set_cookie(COOKIE_PREFIX + key, secret, max_age=remaining,
                        path="/", secure=True, httponly=True, samesite="lax")
    return response


async def provider_navigation(request, settings, handle):
    try:
        require_enabled(settings)
        challenge_id(handle)
        await no_body(request)
        jar = browser_bindings(request, required=True)
        reply = _Provider.model_validate(await _request(settings, "/provider-url", _workload(settings),
                                        body={"start_token": handle, "browser_bindings": jar}))
        url = reply.provider_url.get_secret_value()
        parsed = urlsplit(url)
        if (len(url) > 16384 or any(ord(c) < 33 or ord(c) > 126 for c in url)
                or parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or reply.expires_at <= datetime.now(timezone.utc)):
            return redirect()
        return redirect(url)
    except Exception:
        return redirect()


async def callback(request, settings):
    try:
        require_enabled(settings)
        await no_body(request, allow_query=True)
        body = callback_input(request)
        jar = browser_bindings(request, required=True)
        reply = await _request(settings, "/callback", _workload(settings), body={**body, "browser_bindings": jar})
        if not isinstance(reply, dict) or set(reply) != {"status", "return_url"} or reply["status"] not in {
                "authorized", "canceled", "failed", "expired"}:
            return redirect()
        path = reply["return_url"]
        prefix = "/authorizations/return/"
        if isinstance(path, str) and path.startswith(prefix) and path[len(prefix):] in jar:
            response = redirect(path)
            clear_cookie(response, path[len(prefix):])
            return response
    except Exception:
        # No raw exceptions, provider values, or implied rollback of a committed grant.
        pass
    return redirect()
