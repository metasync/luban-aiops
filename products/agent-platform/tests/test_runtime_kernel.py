import asyncio

from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings


def test_placeholder_reply_without_credentials():
    kernel = AgentKernel(settings=RuntimeSettings(dashscope_api_key=None))

    result = asyncio.run(
        kernel.reply_text(
            message="hello",
            session_id="ses-123",
            user_name="alice",
        )
    )

    assert "placeholder response" in result
    assert "ses-123" in result


def test_placeholder_stream_without_credentials():
    kernel = AgentKernel(settings=RuntimeSettings(dashscope_api_key=None))

    async def collect_events():
        return [
            event
            async for event in kernel.stream_events(
                message="hello",
                request_id="req-123",
                session_id="ses-123",
                user_name="alice",
            )
        ]

    events = asyncio.run(collect_events())

    assert [event["event"] for event in events] == [
        "message_start",
        "message_delta",
        "message_end",
    ]
    assert events[1]["request_id"] == "req-123"
    assert "placeholder response" in events[1]["delta"]
