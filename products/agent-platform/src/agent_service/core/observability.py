from __future__ import annotations

import json
import logging
import os
from typing import Any


def configure_logging() -> None:
    """Raise the root logger so INFO-level structured events survive.

    Uvicorn starts the app with the root logger at WARNING, which silently
    discards every ``log_event`` record (http_request, toolkit registration)
    — i.e. the audit trail. Configure the root level explicitly; override
    via LOG_LEVEL.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, force=True)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, default=str, sort_keys=True))
