"""JSON-serializable coercion for kernel payloads.

Extracted verbatim from ``runtime_kernel`` during the AgentKernel
decomposition (Stage 1) so the kernel module and its ``KernelStatus``
status-projection collaborator share one implementation without a circular
import. Pure and dependency-free.
"""


def make_serializable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [make_serializable(item) for item in value]
    if isinstance(value, tuple):
        return [make_serializable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): make_serializable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return make_serializable(value.model_dump())
    if hasattr(value, "__dict__"):
        return make_serializable(
            {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        )
    return str(value)
