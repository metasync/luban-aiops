import logging

from fastapi import APIRouter, Depends, Header, Query, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.schemas.api import DocumentCreateRequest
from platform_gateway.services.gateway_service import (
    create_document,
    delete_document,
    enforce_policy,
    fetch_document,
    list_documents,
    publish_document,
    resolve_request_identity,
)
from platform_gateway.services.policy_engine import (
    ACTION_APPROVALS_LIST,
    ACTION_DOCUMENTS_CREATE,
    ACTION_DOCUMENTS_READ,
    evaluate,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/api/v1/documents", status_code=201)
async def create_document_route(
    request: Request,
    body: DocumentCreateRequest,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Create an operations document draft (SPEC-039 R-1).

    Foreign-session coverage is a derived capability: the gateway
    evaluates ``approvals:list`` against the caller's roles and forwards
    the outcome as the trusted internal ``X-Foreign-Coverage`` header;
    the agent layer fails closed on any value other than ``allowed``.
    """
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_DOCUMENTS_CREATE, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    foreign_decision = evaluate(settings, identity.roles, ACTION_APPROVALS_LIST)  # type: ignore[union-attr]
    foreign_coverage = (
        "allowed" if foreign_decision.decision == "allow" else "denied"
    )
    response = await create_document(
        settings,
        request_id,
        user_id,
        body.model_dump(),
        foreign_coverage,
    )
    log_event(
        LOGGER,
        "document_created",
        request_id=request_id,
        document_id=response.get("document_id"),
        document_type=response.get("document_type"),
        user_id=user_id,
        foreign_coverage=foreign_coverage,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.get("/api/v1/documents")
async def list_documents_route(
    request: Request,
    scope: str = Query(default="mine", pattern="^(mine|published)$"),
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """List documents (SPEC-039 R-2): ``mine`` includes the caller's drafts."""
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_DOCUMENTS_READ, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await list_documents(settings, request_id, user_id, scope)
    log_event(
        LOGGER,
        "documents_listed",
        request_id=request_id,
        scope=scope,
        document_count=len(response.get("documents", [])),
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.get("/api/v1/documents/{document_id}")
async def fetch_document_route(
    request: Request,
    document_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Fetch one document; foreign drafts read as 404 (SPEC-039 R-2)."""
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_DOCUMENTS_READ, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await fetch_document(settings, request_id, document_id, user_id)
    log_event(
        LOGGER,
        "document_retrieved",
        request_id=request_id,
        document_id=document_id,
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.post("/api/v1/documents/{document_id}/publish")
async def publish_document_route(
    request: Request,
    document_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """One-way owner publish; already-published answers 409 (SPEC-039 R-1)."""
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_DOCUMENTS_CREATE, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await publish_document(settings, request_id, document_id, user_id)
    log_event(
        LOGGER,
        "document_published",
        request_id=request_id,
        document_id=document_id,
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.delete("/api/v1/documents/{document_id}")
async def delete_document_route(
    request: Request,
    document_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Owner-only document delete (SPEC-039 R-1)."""
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_DOCUMENTS_CREATE, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await delete_document(settings, request_id, document_id, user_id)
    log_event(
        LOGGER,
        "document_deleted",
        request_id=request_id,
        document_id=document_id,
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response
