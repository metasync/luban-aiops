from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent_service.metadata import RUNTIME_APP_DESCRIPTION
from agent_service.runtime_kernel import extract_text
from agent_service.services.runtime_dependencies import get_runtime_kernel


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


try:
    from agentscope.message import Msg
    from agentscope_runtime.engine.app import AgentApp
    from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest
except ImportError:  # pragma: no cover - import is validated in the target environment
    Msg = None
    AgentApp = None
    AgentRequest = None


def build_runtime_message(name: str, reply_id: str, content_blocks: list[dict[str, str]]):
    # The current AgentScope Runtime adapter expects dict-like blocks on Msg.content.
    msg = Msg(name=name, content=[], role="assistant", id=reply_id)
    object.__setattr__(msg, "content", content_blocks)
    return msg


def build_content_blocks(
    block_sequence: list[tuple[str, str]],
    text_blocks: dict[str, str],
    thinking_blocks: dict[str, str],
) -> list[dict[str, str]]:
    content_blocks: list[dict[str, str]] = []
    for block_type, block_id in block_sequence:
        if block_type == "thinking" and block_id in thinking_blocks:
            content_blocks.append(
                {
                    "type": "thinking",
                    "thinking": thinking_blocks[block_id],
                }
            )
            continue
        if block_type == "text" and block_id in text_blocks:
            content_blocks.append(
                {
                    "type": "text",
                    "text": text_blocks[block_id],
                }
            )
    return content_blocks


async def stream_agent_reply(agent, agent_name: str, msgs):
    text_blocks: dict[str, str] = {}
    thinking_blocks: dict[str, str] = {}
    block_sequence: list[tuple[str, str]] = []
    last_msg = None

    async for event in agent.reply_stream(msgs):
        event_type = str(getattr(event, "type", "")).upper()
        reply_id = getattr(event, "reply_id", None)
        if reply_id is None:
            continue

        if event_type == "TEXT_BLOCK_DELTA":
            block_id = getattr(event, "block_id", "text")
            text_blocks[block_id] = text_blocks.get(block_id, "") + getattr(event, "delta", "")
            if ("text", block_id) not in block_sequence:
                block_sequence.append(("text", block_id))
            last_msg = build_runtime_message(
                name=agent_name,
                reply_id=reply_id,
                content_blocks=build_content_blocks(
                    block_sequence,
                    text_blocks,
                    thinking_blocks,
                ),
            )
            yield last_msg, False
            continue

        if event_type == "THINKING_BLOCK_DELTA":
            block_id = getattr(event, "block_id", "thinking")
            thinking_blocks[block_id] = thinking_blocks.get(block_id, "") + getattr(event, "delta", "")
            if ("thinking", block_id) not in block_sequence:
                block_sequence.append(("thinking", block_id))
            last_msg = build_runtime_message(
                name=agent_name,
                reply_id=reply_id,
                content_blocks=build_content_blocks(
                    block_sequence,
                    text_blocks,
                    thinking_blocks,
                ),
            )
            yield last_msg, False
            continue

        if event_type == "REPLY_END" and last_msg is not None:
            yield last_msg, True
            return

    if last_msg is not None:
        yield last_msg, True


def build_agent_app():
    if AgentApp is None or Msg is None:
        raise RuntimeError(
            "AgentScope runtime dependencies are unavailable. "
            "Install agentscope-runtime to use the native agent service entrypoint."
        )

    kernel = get_runtime_kernel()
    agent_app = AgentApp(
        app_name=kernel.settings.agent_name,
        app_description=RUNTIME_APP_DESCRIPTION,
        lifespan=lifespan,
    )

    @agent_app.query(framework="agentscope")
    async def query_func(self, msgs, request: AgentRequest = None, **kwargs):
        if not kernel.is_configured():
            content = kernel.build_unconfigured_message(
                message=extract_text(msgs),
                session_id=request.session_id if request else "adhoc-session",
            )
            yield build_runtime_message(
                name=kernel.settings.agent_name,
                reply_id=request.session_id if request else "adhoc-session",
                content_blocks=[{"type": "text", "text": content}],
            ), True
            return

        agent, _ = kernel.ensure_agent()
        if hasattr(agent, "set_console_output_enabled"):
            agent.set_console_output_enabled(False)

        session_manager = getattr(agent_app.state, "session", None)
        if session_manager is not None and request is not None:
            await session_manager.load_session_state(
                session_id=request.session_id,
                user_id=request.user_id,
                agent=agent,
            )

        try:
            async for msg, last in stream_agent_reply(agent, kernel.settings.agent_name, msgs):
                kernel.clear_error()
                yield msg, last
        except Exception as exc:  # pragma: no cover - defensive fallback
            kernel.remember_error(exc)
            content = kernel.build_provider_error_message(
                message=extract_text(msgs),
                session_id=request.session_id if request else "adhoc-session",
            )
            yield build_runtime_message(
                name=kernel.settings.agent_name,
                reply_id=request.session_id if request else "adhoc-session",
                content_blocks=[{"type": "text", "text": content}],
            ), True
        else:
            if session_manager is not None and request is not None:
                await session_manager.save_session_state(
                    session_id=request.session_id,
                    user_id=request.user_id,
                    agent=agent,
                )

    return agent_app


agent_app = build_agent_app()


def run() -> None:
    agent_app.run()
