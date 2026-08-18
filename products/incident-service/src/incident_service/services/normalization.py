"""Alertmanager v4 webhook normalization (SPEC-015 R-2).

Pure function mapping an Alertmanager webhook payload onto the canonical
incident input. The normalization layer isolates alert dialects: Alertmanager
v4 is the first and only one in R3, and future formats get their own
normalizer feeding the same intake path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


class NormalizationError(Exception):
    """Raised when a webhook payload cannot be normalized (maps to 400)."""


_SEVERITY_MAP = {"critical": "critical", "warning": "warning", "info": "info"}

MAX_LABELS = 32
MAX_LABEL_LENGTH = 256


@dataclass(frozen=True)
class IncidentInput:
    """Normalized intake input shared by webhook and manual paths."""

    fingerprint: str
    severity: str
    title: str
    summary: str
    labels: dict[str, str] = field(default_factory=dict)
    resolved: bool = False


def _map_severity(raw: str) -> str:
    """critical passes through; warning/absent default to warning; else info."""
    return _SEVERITY_MAP.get(raw.strip().lower(), "info") if raw else "warning"


def _string_map(raw: object, what: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise NormalizationError(f"{what} must be an object")
    labels: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, (str, int, float, bool)):
            raise NormalizationError(f"{what} entries must be string pairs")
        labels[str(key)] = str(value)
    if len(labels) > MAX_LABELS:
        raise NormalizationError(f"{what} exceeds {MAX_LABELS} entries")
    for key, value in labels.items():
        if len(key) > MAX_LABEL_LENGTH or len(value) > MAX_LABEL_LENGTH:
            raise NormalizationError(f"{what} entry too long")
    return labels


def _label_fingerprint(labels: dict[str, str]) -> str:
    """Stable hash over the sorted label set (fallback when groupKey absent)."""
    digest = hashlib.sha256()
    for key in sorted(labels):
        digest.update(f"{key}={labels[key]}\n".encode())
    return digest.hexdigest()[:32]


def normalize_alertmanager(payload: object) -> IncidentInput:
    """Normalize one Alertmanager v4 webhook payload into an IncidentInput.

    One alert group becomes one incident: ``groupKey`` is the preferred
    fingerprint (a stable hash of the common labels when absent),
    ``commonLabels``/``commonAnnotations`` feed labels/title/summary, and
    ``status == "resolved"`` marks the intake as a resolution.
    """
    if not isinstance(payload, dict):
        raise NormalizationError("payload must be a JSON object")

    status = payload.get("status")
    if status not in {"firing", "resolved"}:
        raise NormalizationError("payload.status must be 'firing' or 'resolved'")

    labels = _string_map(payload.get("commonLabels"), "commonLabels")
    annotations = _string_map(payload.get("commonAnnotations"), "commonAnnotations")

    group_key = payload.get("groupKey")
    if isinstance(group_key, str) and group_key.strip():
        fingerprint = group_key.strip()[:256]
    else:
        if not labels:
            raise NormalizationError(
                "payload needs groupKey or non-empty commonLabels"
            )
        fingerprint = _label_fingerprint(labels)

    alert_name = labels.get("alertname", "")
    title = annotations.get("summary") or alert_name or fingerprint
    summary = annotations.get("description") or (
        ", ".join(f"{k}={v}" for k, v in sorted(labels.items()))
    )

    return IncidentInput(
        fingerprint=fingerprint,
        severity=_map_severity(labels.get("severity", "")),
        title=title[:200],
        summary=summary[:2000],
        labels=labels,
        resolved=status == "resolved",
    )
