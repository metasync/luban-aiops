"""Source-level safeguards for authorization request diagnostics."""
import logging
from urllib.parse import unquote


def authorization_log_path(path: str) -> str:
    """Closed route templates, including unmatched/encoded capability paths."""
    base = "/api/v1/targets/authorizations"
    path = unquote(path.split("?", 1)[0])
    if not path.startswith(base):
        return "/{path}"
    suffix = path[len(base):]
    if suffix in {"/callback", "/browser-reset"}:
        return base + suffix
    if suffix.startswith("/start/"):
        return base + "/start/{start_token}"
    if suffix.endswith("/start") or suffix.endswith("/cancel"):
        return base + "/{challenge_id}/" + suffix.rsplit("/", 1)[-1]
    return base + "/{challenge_id}"


def protect_http_records() -> None:
    # Sanitize at record creation, before ANY handler (including OTLP) sees it.
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_luban_safe_http", False):
        return

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        if record.name == "httpx" or record.name.startswith("httpcore"):
            record.msg, record.args = "HTTP transport diagnostic omitted", ()
            record.exc_info = record.exc_text = record.stack_info = None
        elif record.name == "uvicorn.access":
            values = record.args
            if isinstance(values, tuple) and len(values) == 5:
                client, method, path, version, status = values
                record.args = (client, method, authorization_log_path(str(path)), version, status)
            else:
                record.msg, record.args = "HTTP access diagnostic omitted", ()
            record.exc_info = record.exc_text = record.stack_info = None
        return record

    factory._luban_safe_http = True
    logging.setLogRecordFactory(factory)
