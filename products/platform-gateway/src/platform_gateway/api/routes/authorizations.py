"""Secret-safe SPEC-070 portal edges; callbacks never enter a chat execution."""
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.services import target_authorization as edge

router = APIRouter(prefix=edge.BASE, tags=["target-authorizations"])


@router.get("/callback")
async def callback(request: Request, settings: PlatformGatewaySettings = Depends(get_settings)):
    # Raw Request is intentional: framework query-validation bodies can echo codes.
    return await edge.callback(request, settings)


@router.get("/start/{start_token}")
async def provider_navigation(start_token: str, request: Request,
                              settings: PlatformGatewaySettings = Depends(get_settings)):
    return await edge.provider_navigation(request, settings, start_token)


@router.post("/browser-reset", status_code=204)
async def browser_reset(request: Request, settings: PlatformGatewaySettings = Depends(get_settings)):
    await edge.no_body(request)
    jar = edge.browser_bindings(request)
    _, bearer, _ = await edge.human(request, settings)
    reply = await edge._request(settings, "/browser-reset", bearer, body={"browser_bindings": jar})
    if (not isinstance(reply, dict) or set(reply) != {"canceled"}
            or type(reply["canceled"]) is not int or not 0 <= reply["canceled"] <= len(jar)):
        edge._fail(502)
    response = Response(status_code=204, headers=edge.NO_STORE)
    for key in jar:
        edge.clear_cookie(response, key)
    return response


@router.post("/{challenge_id}/start")
async def start(challenge_id: str, request: Request,
                settings: PlatformGatewaySettings = Depends(get_settings)):
    return await edge.start(request, settings, challenge_id)


@router.get("/{challenge_id}")
async def status(challenge_id: str, request: Request,
                 settings: PlatformGatewaySettings = Depends(get_settings)):
    key = edge.challenge_id(challenge_id)
    await edge.no_body(request)
    identity, bearer, request_id = await edge.human(request, settings)
    raw, _ = await edge.owned_status(settings, key, identity, bearer, request_id)
    return JSONResponse(raw, headers=edge.NO_STORE)


@router.post("/{challenge_id}/cancel", status_code=204)
async def cancel(challenge_id: str, request: Request,
                 settings: PlatformGatewaySettings = Depends(get_settings)):
    key = edge.challenge_id(challenge_id)
    await edge.no_body(request)
    jar = edge.browser_bindings(request)
    _, bearer, _ = await edge.human(request, settings)
    await edge._request(settings, "/" + key + "/cancel", bearer, expected_status=204)
    response = Response(status_code=204, headers=edge.NO_STORE)
    if key in jar:
        edge.clear_cookie(response, key)
    return response
