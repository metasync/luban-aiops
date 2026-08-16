"""Frozen skills-hub settings loaded from environment variables (SPEC-014 R-2).

Mirrors the audit-service settings vocabulary (SPEC-013 precedent) with a
deliberately distinct query-credential registry from day one.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class SettingsError(Exception):
    """Raised when a SKILLS_* setting is malformed (fail startup fast)."""


@dataclass(frozen=True)
class SourceSpec:
    """One admitted skill source (SPEC-014 R-2 federation entry)."""

    source_id: str
    type: str  # "git" | "local"
    path: str = ""  # local: directory path; git: optional subpath of checkout
    url: str = ""  # git sources: clone URL
    ref: str = "HEAD"  # git sources: branch/tag to track


@dataclass(frozen=True)
class QueryClient:
    """Registered static query credential (distinct registry, SPEC-014 R-3)."""

    client_id: str
    secret: str


@dataclass(frozen=True)
class WorkloadClient:
    """Projected-token subject to registered client mapping (SPEC-009 R-3)."""

    workload_subject: str
    client_id: str


def parse_sources(raw: str) -> tuple[SourceSpec, ...]:
    """Parse ``SKILLS_SOURCES`` (JSON list of source entries).

    Unknown types, duplicate ``source_id`` values, malformed ids, and missing
    type-specific fields all fail fast — a bad federation entry must never
    surface later as a silent sync failure.
    """
    raw = raw.strip()
    if not raw:
        return tuple()
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SettingsError(f"SKILLS_SOURCES is not valid JSON: {exc}") from exc
    if not isinstance(entries, list):
        raise SettingsError("SKILLS_SOURCES must be a JSON list")
    sources: list[SourceSpec] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SettingsError(f"SKILLS_SOURCES[{index}] must be an object")
        source_id = str(entry.get("source_id", "")).strip()
        if not SOURCE_ID_PATTERN.match(source_id):
            raise SettingsError(
                f"SKILLS_SOURCES[{index}].source_id must match "
                "[a-z0-9][a-z0-9-]*"
            )
        if source_id in seen:
            raise SettingsError(f"duplicate source_id: {source_id}")
        seen.add(source_id)
        source_type = str(entry.get("type", "")).strip().lower()
        if source_type == "local":
            path = str(entry.get("path", "")).strip()
            if not path:
                raise SettingsError(
                    f"source {source_id}: local sources require 'path'"
                )
            sources.append(SourceSpec(source_id=source_id, type="local", path=path))
        elif source_type == "git":
            url = str(entry.get("url", "")).strip()
            if not url:
                raise SettingsError(
                    f"source {source_id}: git sources require 'url'"
                )
            ref = str(entry.get("ref", "HEAD")).strip() or "HEAD"
            path = str(entry.get("path", "")).strip().rstrip("/")
            if path:
                if path.startswith("/") or ".." in Path(path).parts:
                    raise SettingsError(
                        f"source {source_id}: git 'path' must be a relative "
                        "subdirectory within the checkout"
                    )
            sources.append(
                SourceSpec(
                    source_id=source_id,
                    type="git",
                    url=url,
                    ref=ref,
                    path=path,
                )
            )
        else:
            raise SettingsError(
                f"source {source_id}: unknown type {source_type!r} "
                "(expected 'git' or 'local')"
            )
    return tuple(sources)


def parse_git_tokens(raw: str) -> dict[str, str]:
    """Parse ``SKILLS_GIT_TOKENS`` (JSON map source_id -> token)."""
    raw = raw.strip()
    if not raw:
        return {}
    try:
        tokens = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SettingsError(f"SKILLS_GIT_TOKENS is not valid JSON: {exc}") from exc
    if not isinstance(tokens, dict):
        raise SettingsError("SKILLS_GIT_TOKENS must be a JSON object")
    return {str(k): str(v) for k, v in tokens.items() if k and v}


def parse_query_clients(raw: str) -> tuple[QueryClient, ...]:
    """Parse ``SKILLS_QUERY_CLIENTS`` (``client_id=secret,client_id=secret``)."""
    clients: list[QueryClient] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        client_id, _, secret = entry.partition("=")
        if client_id and secret:
            clients.append(QueryClient(client_id=client_id, secret=secret))
    return tuple(clients)


def parse_workload_clients(raw: str) -> tuple[WorkloadClient, ...]:
    """Parse ``SKILLS_WORKLOAD_CLIENTS`` (``subject=client_id,...``)."""
    mappings: list[WorkloadClient] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        subject, _, client_id = entry.partition("=")
        if subject and client_id:
            mappings.append(
                WorkloadClient(workload_subject=subject, client_id=client_id)
            )
    return tuple(mappings)


@dataclass(frozen=True)
class SkillsSettings:
    """Frozen settings loaded from environment variables (SPEC-014 R-2/R-3)."""

    sources: tuple[SourceSpec, ...] = field(default_factory=tuple)
    git_tokens: dict[str, str] = field(default_factory=dict)
    sync_interval_seconds: int = 300
    data_path: str = "/var/lib/skills-hub"
    store_backend: str = "memory"
    db_url: str = ""
    query_clients: tuple[QueryClient, ...] = field(default_factory=tuple)
    workload_issuer_url: str = ""
    workload_audience: str = "skills-hub"
    workload_clients: tuple[WorkloadClient, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls) -> "SkillsSettings":
        return cls(
            sources=parse_sources(os.getenv("SKILLS_SOURCES", "")),
            git_tokens=parse_git_tokens(os.getenv("SKILLS_GIT_TOKENS", "")),
            sync_interval_seconds=int(
                os.getenv("SKILLS_SYNC_INTERVAL_SECONDS", "300")
            ),
            data_path=os.getenv("SKILLS_DATA_PATH", "/var/lib/skills-hub"),
            store_backend=os.getenv("SKILLS_STORE_BACKEND", "memory").strip().lower(),
            db_url=os.getenv("SKILLS_DB_URL", ""),
            query_clients=parse_query_clients(
                os.getenv("SKILLS_QUERY_CLIENTS", "")
            ),
            workload_issuer_url=os.getenv("SKILLS_WORKLOAD_ISSUER_URL", ""),
            workload_audience=os.getenv(
                "SKILLS_WORKLOAD_AUDIENCE", "skills-hub"
            ),
            workload_clients=parse_workload_clients(
                os.getenv("SKILLS_WORKLOAD_CLIENTS", "")
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> SkillsSettings:
    return SkillsSettings.from_env()
