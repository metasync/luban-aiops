"""Named credential sets for browser login flows (SPEC-049 R-5).

Credentials are platform configuration, never skill content: the connector
resolves a named set from a secret-mounted JSON file at call time. The
knob accepts a file path only (no inline values), unknown set names are a
structured error rather than a crash, and set values are never logged or
serialized into tool results — they only ever flow into a Playwright
``fill`` call. The file reloads on mtime change so secret rotation needs
no gateway restart.

Expected file shape::

    {
      "inventory-app": {"username": "svc-check", "password": "..."},
      "legacy-crm": {"username": "checker", "password": "..."}
    }
"""

from __future__ import annotations

import json
import logging
import os

LOGGER = logging.getLogger(__name__)

REQUIRED_FIELDS = ("username", "password")


class CredentialSetStore:
    """Lazy, mtime-refreshed view of the credential-set secret file."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._mtime: float | None = None
        self._sets: dict[str, dict[str, str]] = {}

    @property
    def configured(self) -> bool:
        return bool(self._path)

    def names(self) -> list[str]:
        """Set names are safe to surface (names are not secrets)."""
        self._maybe_reload()
        return sorted(self._sets)

    def get(self, name: str) -> dict[str, str] | None:
        """Resolve one named set; None when unconfigured or unknown."""
        self._maybe_reload()
        return self._sets.get(name)

    def _maybe_reload(self) -> None:
        if not self._path:
            return
        try:
            mtime = os.stat(self._path).st_mtime
        except OSError:
            if self._sets:
                LOGGER.warning(
                    "credential sets file disappeared; keeping last good load"
                )
            return
        if mtime == self._mtime:
            return
        self._reload(mtime)

    def _reload(self, mtime: float) -> None:
        try:
            with open(self._path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as exc:
            # Log the failure class only — never the file contents.
            LOGGER.warning(
                "credential sets file unreadable (%s); keeping last good "
                "load",
                exc.__class__.__name__,
            )
            return
        if not isinstance(raw, dict):
            LOGGER.warning("credential sets file must be a JSON object")
            return
        parsed: dict[str, dict[str, str]] = {}
        for name, value in raw.items():
            if (
                not isinstance(value, dict)
                or any(
                    not isinstance(value.get(field), str) or not value.get(field)
                    for field in REQUIRED_FIELDS
                )
            ):
                LOGGER.warning(
                    "credential set %r ignored: each set needs non-empty "
                    "username and password strings",
                    name,
                )
                continue
            parsed[str(name)] = {
                field: value[field] for field in REQUIRED_FIELDS
            }
        self._sets = parsed
        self._mtime = mtime
        LOGGER.info("credential sets loaded: %d set(s)", len(parsed))
