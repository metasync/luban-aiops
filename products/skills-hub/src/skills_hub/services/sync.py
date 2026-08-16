"""Per-source sync engine (SPEC-014 R-2).

One asyncio task per configured source, each running an independent loop:
materialize the source (git checkout or local directory), ingest + validate
every document, then swap the validated snapshot into the store atomically.
A failed cycle keeps the previously served snapshot and is recorded in the
per-source status plus the ``skills_syncs_total`` counter — one source's
failure never disturbs another source.
"""

from __future__ import annotations

import asyncio
import logging
import random
import shutil
import subprocess
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from skills_hub.core import metrics
from skills_hub.core.config import SkillsSettings, SourceSpec
from skills_hub.services.ingestion import Rejection, ingest_directory
from skills_hub.services.skill_store import SkillStore

LOGGER = logging.getLogger(__name__)

MAX_REPORTED_REJECTIONS = 50
GIT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class SourceStatus:
    """Last sync outcome for one source (served by the status endpoint)."""

    source_id: str
    source_type: str
    last_sync_at: datetime | None = None
    last_error: str | None = None
    ref: str | None = None
    accepted: int = 0
    rejections: tuple[Rejection, ...] = field(default_factory=tuple)


def _rejection_category(reason: str) -> str:
    """Bounded label for the rejection counter (cardinality guard)."""
    lowered = reason.lower()
    if lowered.startswith("duplicate"):
        return "duplicate_slug"
    if "body exceeds" in lowered:
        return "size"
    if "unreadable" in lowered:
        return "unreadable"
    if "slug" in lowered:
        return "path"
    if "not found" in lowered:
        return "missing_source"
    return "frontmatter"


# --- Git materialization ------------------------------------------------------


def _with_token(url: str, token: str | None) -> str:
    """Inject an x-access-token into an https clone URL (pod-local only)."""
    if not token or not url.startswith("https://"):
        return url
    parts = urlsplit(url)
    netloc = f"x-access-token:{token}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _git(args: list[str]) -> None:
    subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )


def _git_checkout(url: str, ref: str, dest: Path, token: str | None) -> str:
    """Clone or update a disposable checkout; return the resolved commit SHA.

    Any corruption is unrecoverable by design: the directory is a cache, so
    failures fall back to a fresh clone on the next cycle.
    """
    auth_url = _with_token(url, token)
    if (dest / ".git").is_dir():
        _git(["-C", str(dest), "fetch", "--depth", "1", "origin", ref])
        _git(["-C", str(dest), "reset", "--hard", "FETCH_HEAD"])
    else:
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        clone_args = ["clone", "--depth", "1"]
        if ref != "HEAD":
            clone_args += ["--branch", ref]
        _git([*clone_args, auth_url, str(dest)])
    result = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    return result.stdout.strip()


# --- Sync manager --------------------------------------------------------------


class SyncManager:
    """Owns the per-source sync loops and the status registry."""

    def __init__(self, settings: SkillsSettings, store: SkillStore) -> None:
        self._settings = settings
        self._store = store
        self._statuses: dict[str, SourceStatus] = {
            spec.source_id: SourceStatus(
                source_id=spec.source_id, source_type=spec.type
            )
            for spec in settings.sources
        }
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        for spec in self._settings.sources:
            self._tasks.append(
                asyncio.create_task(self._loop(spec), name=f"sync-{spec.source_id}")
            )

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _loop(self, spec: SourceSpec) -> None:
        while True:
            await self.sync_once(spec)
            # Small jitter so multiple sources never stampede together.
            jitter = random.uniform(-0.05, 0.05)
            interval = max(1.0, self._settings.sync_interval_seconds * (1 + jitter))
            await asyncio.sleep(interval)

    async def sync_once(self, spec: SourceSpec) -> SourceStatus:
        """Run one sync cycle for a source; never raises."""
        now = datetime.now(timezone.utc)
        try:
            root, ref = await self._materialize(spec)
            result = await asyncio.to_thread(
                ingest_directory, spec.source_id, root, ref, now
            )
            await self._store.replace_source(spec.source_id, result.records)
            status = SourceStatus(
                source_id=spec.source_id,
                source_type=spec.type,
                last_sync_at=now,
                last_error=None,
                ref=ref,
                accepted=len(result.records),
                rejections=tuple(result.rejections[:MAX_REPORTED_REJECTIONS]),
            )
            metrics.record_sync(spec.source_id, "ok")
            metrics.set_source_size(spec.source_id, status.accepted)
            for rejection in result.rejections:
                metrics.record_rejected(_rejection_category(rejection.reason))
            LOGGER.info(
                "source synced",
                extra={
                    "source_id": spec.source_id,
                    "ref": ref,
                    "accepted": status.accepted,
                    "rejected": len(result.rejections),
                },
            )
        except Exception as exc:  # noqa: BLE001 - a cycle must never die
            previous = self._statuses[spec.source_id]
            # A failed `git clone` quotes its argv verbatim in the exception,
            # which includes the token-injected URL; error messages reach the
            # auth-exempt status endpoint and the logs, so the credential
            # must never appear in them.
            message = str(exc)
            token = self._settings.git_tokens.get(spec.source_id)
            if token:
                message = message.replace(token, "***")
            status = replace(previous, last_sync_at=now, last_error=message)
            metrics.record_sync(spec.source_id, "error")
            LOGGER.error(
                "source sync failed; keeping previous snapshot",
                extra={"source_id": spec.source_id, "error": message},
            )
        self._statuses[spec.source_id] = status
        return status

    async def _materialize(self, spec: SourceSpec) -> tuple[Path, str]:
        """Return (readable root directory, ref marker) for one source."""
        if spec.type == "local":
            return Path(spec.path), "local"
        dest = Path(self._settings.data_path) / "sources" / spec.source_id
        token = self._settings.git_tokens.get(spec.source_id)
        sha = await asyncio.to_thread(
            _git_checkout, spec.url, spec.ref, dest, token
        )
        return dest, sha

    def status_report(self) -> list[dict]:
        """JSON-ready per-source report (bounded rejection lists)."""
        report = []
        for source_id in sorted(self._statuses):
            status = self._statuses[source_id]
            report.append(
                {
                    "source_id": status.source_id,
                    "type": status.source_type,
                    "last_sync_at": (
                        status.last_sync_at.isoformat()
                        if status.last_sync_at
                        else None
                    ),
                    "last_error": status.last_error,
                    "ref": status.ref,
                    "accepted": status.accepted,
                    "rejections": [
                        {"path": r.path, "reason": r.reason}
                        for r in status.rejections
                    ],
                }
            )
        return report
