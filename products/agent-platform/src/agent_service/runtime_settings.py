import os
from dataclasses import dataclass


DEFAULT_SYSTEM_PROMPT = (
    "You are the runtime kernel for the Luban AIOps platform. "
    "Answer clearly and concisely, and keep the response grounded in the current platform state."
)


@dataclass(frozen=True)
class RuntimeSettings:
    agent_name: str = "LubanOpsRuntime"
    model_name: str = "qwen-plus"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    dashscope_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        return cls(
            agent_name=os.getenv("AGENTSCOPE_AGENT_NAME", "LubanOpsRuntime"),
            model_name=os.getenv("AGENTSCOPE_MODEL_NAME", "qwen-plus"),
            system_prompt=os.getenv("AGENTSCOPE_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY"),
        )

    def is_configured(self) -> bool:
        return bool(self.dashscope_api_key)
