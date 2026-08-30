"""Federated source ingestion: document parsing and validation (SPEC-014 R-1/R-2).

Walks a checked-out source directory, parses and validates every Markdown
document against the skill contract (``shared/shared-contracts/skill-format.md``),
and returns the validated records plus a per-document rejection list. A source
with zero valid documents still produces an (empty) snapshot — "reject the
document, keep the source healthy".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from skills_hub.schemas.skill import Skill

LOGGER = logging.getLogger(__name__)

MAX_BODY_BYTES = 65536
MAX_TITLE_CHARS = 200
MAX_DESCRIPTION_CHARS = 500
MAX_TAG_CHARS = 64
MAX_TAGS = 10
MAX_VERSION_CHARS = 64
MAX_SOURCE_URL_CHARS = 2048
ALLOWED_KEYS = {"title", "description", "tags", "version", "source_url"}
SKIPPED_BASENAMES = {"readme.md", "notice", "notice.md"}
_SEGMENT_CLEANUP = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Rejection:
    """One validation failure, exposed verbatim via the status endpoint."""

    source_id: str
    path: str
    reason: str


@dataclass
class IngestResult:
    records: list[Skill] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)


def slug_from_path(rel_path: str) -> str | None:
    """Derive the slug from the document's relative path.

    ``alerts/KubePodNotReady.md`` -> ``alerts/kubepodnotready``. Segments are
    lowercased and every run of non-alphanumeric characters collapses to a
    single ``-``; a segment that sanitizes to nothing invalidates the path.
    """
    rel = rel_path[:-3] if rel_path.lower().endswith(".md") else rel_path
    segments: list[str] = []
    for part in rel.split("/"):
        cleaned = _SEGMENT_CLEANUP.sub("-", part.lower()).strip("-")
        if not cleaned:
            return None
        segments.append(cleaned)
    return "/".join(segments) if segments else None


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Split a document into (frontmatter_yaml, body).

    Returns None when the document does not open with a ``---`` fence or the
    fence is never closed — both are validation failures.
    """
    if not text.startswith("---"):
        return None
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    return None


def _validate_frontmatter(
    source_id: str, rel_path: str, raw: str
) -> tuple[dict, str] | Rejection:
    """Validate the frontmatter mapping; return fields or a rejection."""
    parts = split_frontmatter(raw)
    if parts is None:
        return Rejection(source_id, rel_path, "missing or unterminated frontmatter")
    frontmatter_raw, body = parts
    try:
        frontmatter = yaml.safe_load(frontmatter_raw)
    except yaml.YAMLError as exc:
        return Rejection(source_id, rel_path, f"frontmatter is not valid YAML: {exc}")
    if not isinstance(frontmatter, dict):
        return Rejection(source_id, rel_path, "frontmatter must be a YAML mapping")

    unknown = sorted(set(frontmatter) - ALLOWED_KEYS)
    if unknown:
        return Rejection(
            source_id, rel_path, f"unknown frontmatter keys: {', '.join(unknown)}"
        )

    title = frontmatter.get("title")
    if not isinstance(title, str) or not title.strip():
        return Rejection(source_id, rel_path, "frontmatter 'title' is required")
    if len(title) > MAX_TITLE_CHARS:
        return Rejection(source_id, rel_path, "title exceeds 200 chars")

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        return Rejection(source_id, rel_path, "frontmatter 'description' is required")
    if len(description) > MAX_DESCRIPTION_CHARS:
        return Rejection(source_id, rel_path, "description exceeds 500 chars")

    tags = frontmatter.get("tags")
    if tags is not None:
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) and tag.strip() for tag in tags
        ):
            return Rejection(
                source_id, rel_path, "tags must be a list of non-empty strings"
            )
        if len(tags) > MAX_TAGS:
            return Rejection(source_id, rel_path, f"more than {MAX_TAGS} tags")
        if any(len(tag) > MAX_TAG_CHARS for tag in tags):
            return Rejection(source_id, rel_path, "tag exceeds 64 chars")

    version = frontmatter.get("version")
    if version is not None and (
        not isinstance(version, str) or len(version) > MAX_VERSION_CHARS
    ):
        return Rejection(source_id, rel_path, "version must be a string ≤ 64 chars")

    source_url = frontmatter.get("source_url")
    if source_url is not None and (
        not isinstance(source_url, str) or len(source_url) > MAX_SOURCE_URL_CHARS
    ):
        return Rejection(
            source_id, rel_path, "source_url must be a string ≤ 2048 chars"
        )

    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        return Rejection(source_id, rel_path, "body exceeds 64 KiB")

    return frontmatter, body


def validate_document(raw: str) -> tuple[bool, str | None]:
    """Validate one candidate skill document against the skill contract.

    Same code path ``ingest_directory`` uses at sync time (single source of
    truth for Skill Format v1 — SPEC-044 R-2). Returns ``(valid, reason)``
    where ``reason`` uses the ingestion report vocabulary verbatim.
    """
    validated = _validate_frontmatter("validate", "draft.md", raw)
    if isinstance(validated, Rejection):
        return False, validated.reason
    return True, None


def ingest_directory(
    source_id: str,
    root: Path,
    source_ref: str,
    updated_at: datetime,
) -> IngestResult:
    """Validate every skill document under ``root`` into one snapshot.

    Deterministic by construction: files are visited in sorted path order, so
    duplicate-slug resolution (first occurrence wins) is stable across runs.
    """
    result = IngestResult()
    if not root.is_dir():
        result.rejections.append(
            Rejection(source_id, ".", f"source directory not found: {root}")
        )
        return result
    projected = root / "..data"
    if projected.is_dir():
        # Kubernetes projected volumes (ConfigMap/Secret mounts) keep the
        # canonical content in a timestamped directory exposed through a
        # ``..data`` symlink; walk that directly instead of the symlink farm.
        root = projected
    seen_slugs: dict[str, str] = {}
    for path in sorted(root.rglob("*.md")):
        rel_path = path.relative_to(root).as_posix()
        # Skip hidden path segments: Kubernetes ConfigMap/Secret volumes expose
        # atomic-writer artifacts (..data symlink, ..<timestamp> dirs) that
        # would otherwise be ingested with polluted slugs.
        if any(part.startswith(".") for part in rel_path.split("/")):
            continue
        if path.name.lower() in SKIPPED_BASENAMES:
            continue
        slug = slug_from_path(rel_path)
        if slug is None:
            result.rejections.append(
                Rejection(source_id, rel_path, "path does not produce a slug")
            )
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            result.rejections.append(
                Rejection(source_id, rel_path, f"unreadable document: {exc}")
            )
            continue
        validated = _validate_frontmatter(source_id, rel_path, raw)
        if isinstance(validated, Rejection):
            result.rejections.append(validated)
            continue
        frontmatter, body = validated
        if slug in seen_slugs:
            result.rejections.append(
                Rejection(
                    source_id,
                    rel_path,
                    f"duplicate slug '{slug}' (already defined by "
                    f"{seen_slugs[slug]})",
                )
            )
            continue
        seen_slugs[slug] = rel_path
        result.records.append(
            Skill(
                skill_id=f"{source_id}/{slug}",
                source_id=source_id,
                source_path=rel_path,
                source_ref=source_ref,
                title=frontmatter["title"].strip(),
                description=frontmatter["description"].strip(),
                tags=frontmatter.get("tags"),
                version=frontmatter.get("version"),
                source_url=frontmatter.get("source_url"),
                updated_at=updated_at,
                body=body.lstrip("\n"),
            )
        )
    return result
