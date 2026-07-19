import os
from uuid import uuid4

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse


AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "http://agent-service:8000")
IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://identity-service:8000")

app = FastAPI(title="api-gateway", version="0.1.0")


def resolve_request_id(request_id: str | None) -> str:
    return request_id or f"req-{uuid4()}"


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": "api-gateway", "version": "0.1.0"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    return {"status": "ok", "service": "api-gateway", "version": "0.1.0"}


@app.get("/api/v1/auth/login-url")
async def login_url(x_request_id: str | None = Header(default=None)) -> dict:
    headers = {"x-request-id": resolve_request_id(x_request_id)}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{IDENTITY_SERVICE_URL}/api/v1/auth/login-url",
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


@app.post("/api/v1/identity/normalize")
async def normalize_identity(
    request: Request,
    x_request_id: str | None = Header(default=None),
) -> dict:
    headers = {"x-request-id": resolve_request_id(x_request_id)}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{IDENTITY_SERVICE_URL}/api/v1/identity/normalize",
            json=await request.json(),
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


@app.post("/api/v1/sessions")
async def create_session(
    request: Request,
    x_request_id: str | None = Header(default=None),
) -> dict:
    headers = {"x-request-id": resolve_request_id(x_request_id)}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{AGENT_SERVICE_URL}/api/v1/sessions",
            json=await request.json(),
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


@app.get("/api/v1/sessions/{session_id}")
async def get_session(session_id: str, x_request_id: str | None = Header(default=None)) -> dict:
    headers = {"x-request-id": resolve_request_id(x_request_id)}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{AGENT_SERVICE_URL}/api/v1/sessions/{session_id}",
            headers=headers,
        )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="session not found")
    response.raise_for_status()
    return response.json()


@app.post("/api/v1/chat")
async def chat(request: Request, x_request_id: str | None = Header(default=None)) -> dict:
    headers = {"x-request-id": resolve_request_id(x_request_id)}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{AGENT_SERVICE_URL}/api/v1/chat",
            json=await request.json(),
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


@app.get("/api/v1/chat/stream")
async def chat_stream(
    message: str,
    session_id: str | None = None,
    user_id: str | None = None,
    x_request_id: str | None = Header(default=None),
) -> StreamingResponse:
    params = {"message": message}
    if session_id:
        params["session_id"] = session_id
    if user_id:
        params["user_id"] = user_id
    headers = {"x-request-id": resolve_request_id(x_request_id)}

    async def stream() -> bytes:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET",
                f"{AGENT_SERVICE_URL}/api/v1/chat/stream",
                params=params,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream")


def run() -> None:
    uvicorn.run("api_gateway.main:app", host="0.0.0.0", port=8000)
