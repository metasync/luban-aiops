#!/usr/bin/env python3
"""Validate the canonical policy bundle against policy-rule.schema.json.

Usage:
    python validate_policy.py [path-to-bundle]

Defaults to shared/shared-contracts/policies/policy-default.yaml when no
path is given. Exits 0 on success, 1 on any validation error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:
    sys.exit("jsonschema is required: pip install jsonschema")

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE = CONTRACTS_DIR / "policies" / "policy-default.yaml"
RULE_SCHEMA = CONTRACTS_DIR / "schemas" / "policy-rule.schema.json"


def main() -> int:
    bundle_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BUNDLE

    if not bundle_path.is_file():
        print(f"error: bundle not found: {bundle_path}", file=sys.stderr)
        return 1
    if not RULE_SCHEMA.is_file():
        print(f"error: schema not found: {RULE_SCHEMA}", file=sys.stderr)
        return 1

    with open(bundle_path) as f:
        bundle = yaml.safe_load(f)

    with open(RULE_SCHEMA) as f:
        schema = json.load(f)

    if not isinstance(bundle, dict):
        print(f"error: bundle must be a YAML mapping, got {type(bundle).__name__}", file=sys.stderr)
        return 1

    version = bundle.get("version")
    if version != 1:
        print(f"error: unsupported bundle version: {version!r} (expected 1)", file=sys.stderr)
        return 1

    rules = bundle.get("rules")
    if not isinstance(rules, list) or not rules:
        print("error: bundle must contain a non-empty 'rules' list", file=sys.stderr)
        return 1

    validator = Draft202012Validator(schema)
    errors: list[str] = []
    ids_seen: set[str] = set()

    for i, rule in enumerate(rules):
        rule_id = rule.get("id", f"<rule-{i}>")

        # Duplicate ID check.
        if rule_id in ids_seen:
            errors.append(f"rule {rule_id!r}: duplicate id")
        ids_seen.add(rule_id)

        # Schema validation.
        for err in validator.iter_errors(rule):
            path = ".".join(str(p) for p in err.absolute_path) or "<root>"
            errors.append(f"rule {rule_id!r}: {path}: {err.message}")

    if errors:
        print(f"FAIL: {len(errors)} validation error(s) in {bundle_path}:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK: {len(rules)} rule(s) validated against {RULE_SCHEMA.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
