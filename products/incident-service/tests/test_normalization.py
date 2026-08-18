"""Alertmanager normalization tests (SPEC-015 R-2)."""

from __future__ import annotations

import unittest

from incident_service.services.normalization import (
    NormalizationError,
    normalize_alertmanager,
)


def _payload(**overrides) -> dict:
    payload = {
        "version": "4",
        "groupKey": "{}:{alertname=KubePodNotReady}",
        "status": "firing",
        "commonLabels": {"alertname": "KubePodNotReady", "severity": "critical"},
        "commonAnnotations": {
            "summary": "Pod stuck not ready",
            "description": "Pod default/web-1 not ready for 15m.",
        },
    }
    payload.update(overrides)
    return payload


class NormalizationTests(unittest.TestCase):
    def test_full_payload_maps_to_canonical_input(self) -> None:
        normalized = normalize_alertmanager(_payload())
        self.assertEqual(normalized.fingerprint, "{}:{alertname=KubePodNotReady}")
        self.assertEqual(normalized.severity, "critical")
        self.assertEqual(normalized.title, "Pod stuck not ready")
        self.assertEqual(normalized.summary, "Pod default/web-1 not ready for 15m.")
        self.assertEqual(normalized.labels["alertname"], "KubePodNotReady")
        self.assertFalse(normalized.resolved)

    def test_missing_severity_label_defaults_to_warning(self) -> None:
        payload = _payload(commonLabels={"alertname": "SomethingElse"})
        self.assertEqual(normalize_alertmanager(payload).severity, "warning")

    def test_unknown_severity_label_maps_to_info(self) -> None:
        payload = _payload(
            commonLabels={"alertname": "X", "severity": "bogus"}
        )
        self.assertEqual(normalize_alertmanager(payload).severity, "info")

    def test_resolved_status_is_flagged(self) -> None:
        self.assertTrue(normalize_alertmanager(_payload(status="resolved")).resolved)

    def test_title_falls_back_to_alertname_then_fingerprint(self) -> None:
        payload = _payload(commonAnnotations={}, commonLabels={"alertname": "HighCPU"})
        self.assertEqual(normalize_alertmanager(payload).title, "HighCPU")
        payload = _payload(commonAnnotations={}, commonLabels={"team": "core"})
        normalized = normalize_alertmanager(payload)
        self.assertEqual(normalized.title, normalized.fingerprint)

    def test_summary_falls_back_to_sorted_label_pairs(self) -> None:
        payload = _payload(commonAnnotations={})
        normalized = normalize_alertmanager(payload)
        self.assertIn("alertname=KubePodNotReady", normalized.summary)

    def test_fingerprint_derived_from_labels_without_group_key(self) -> None:
        payload = _payload(groupKey=None)
        first = normalize_alertmanager(payload)
        second = normalize_alertmanager(_payload(groupKey=""))
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(len(first.fingerprint), 32)

    def test_rejects_missing_status(self) -> None:
        with self.assertRaises(NormalizationError):
            normalize_alertmanager(_payload(status="pending"))

    def test_rejects_non_object_payload(self) -> None:
        with self.assertRaises(NormalizationError):
            normalize_alertmanager(["not", "an", "object"])

    def test_rejects_payload_without_group_key_or_labels(self) -> None:
        with self.assertRaises(NormalizationError):
            normalize_alertmanager(_payload(groupKey=None, commonLabels={}))

    def test_rejects_non_string_label_values(self) -> None:
        with self.assertRaises(NormalizationError):
            normalize_alertmanager(
                _payload(commonLabels={"alertname": {"nested": "bad"}})
            )

    def test_rejects_oversize_label_maps(self) -> None:
        labels = {f"label{i}": "v" for i in range(33)}
        with self.assertRaises(NormalizationError):
            normalize_alertmanager(_payload(commonLabels=labels))


if __name__ == "__main__":
    unittest.main()
