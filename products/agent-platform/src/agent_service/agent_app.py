from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent_service.runtime_kernel import AgentKernel, extract_text


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


def build_agent_app():
    if AgentApp is None or Msg is None:
        raise RuntimeError(
            "AgentScope runtime dependencies are unavailable. "
            "Install agentscope-runtime to use the native agent service entrypoint."
        )

    kernel = AgentKernel()
    agent_app = AgentApp(
        app_name="LubanOpsRuntime",
        app_description="Native AgentScope runtime service for the Luban AIOps platform.",
        lifespan=lifespan,
    )

    @agent_app.query(framework="agentscope")
    async def query_func(self, msgs, request: AgentRequest = None, **kwargs):
        if not kernel.is_configured():
            content = kernel.build_placeholder_message(
                message=extract_text(msgs),
                session_id=request.session_id if request else "adhoc-session",
            )
            yield Msg(name=kernel.settings.agent_name, content=content, role="assistant"), True
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

        reply_msg = await agent(msgs)
        yield reply_msg, True

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
