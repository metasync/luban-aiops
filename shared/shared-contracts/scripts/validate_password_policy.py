#!/usr/bin/env python3
"""Validate the password-strength policy contract and pin the connector to it.

SPEC-062 R-2 makes ``password-policy.yaml`` the single source of truth for
generated-password strength. Two things can drift from it, and this script fails
the build on either (the ``validate-password-policy`` leg of ``make verify``,
mirroring ``validate-secret-vocabulary``):

1. **The contract is malformed.** ``version`` must be integer 1 and
   ``policies`` a non-empty map whose entries each carry the five required keys
   with sane types and internally-consistent values (``hard_floor`` no greater
   than ``min_length``, ``required_classes`` a subset of the known vocabulary, a
   positive ``entropy_floor_bits``). This check is always available.

2. **The enforced floor diverges from the contract.** The password-policy module
   that ``secrets.generate_password`` reads declares the ``default`` floor it
   enforces as module constants (``DEFAULT_POLICY_FLOOR`` /
   ``DEFAULT_POLICY_CLASSES``) — minimum constraints on every loaded policy,
   not fallback generation values. An unavailable policy refuses generation.
   These constants and the packaged YAML copy must agree with the canonical
   contract; missing consumers also fail validation.

Usage:
    python validate_password_policy.py [repo-root]

Defaults to the repository containing this script. Exits 0 when the contract is
well-formed and every present copy agrees, 1 on any problem.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    sys.exit("PyYAML is required: pip install pyyaml")

CONTRACT_REL = "shared/shared-contracts/policies/password-policy.yaml"

# The policy module that hardcodes the ``default`` floor it enforces, and the
# two module-level tuples this script pins to the contract.
CONNECTOR_REL = (
    "products/tool-gateway/src/tool_gateway/tools/password_policy.py"
)
CONNECTOR_FLOOR_VAR = "DEFAULT_POLICY_FLOOR"  # (min_length, hard_floor, entropy_floor_bits)
CONNECTOR_CLASSES_VAR = "DEFAULT_POLICY_CLASSES"  # ("upper", "lower", "digit", "symbol")

REQUIRED_KEYS = (
    "min_length",
    "hard_floor",
    "required_classes",
    "entropy_floor_bits",
    "exclude_ambiguous",
)
KNOWN_CLASSES = {"upper", "lower", "digit", "symbol"}


def repo_root() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    # shared/shared-contracts/scripts/validate_password_policy.py -> repo root
    return Path(__file__).resolve().parents[3]


def _tuple_body(var_name: str, text: str) -> str | None:
    """Return the body of a module-level ``VAR[: ann] = ( ... )`` tuple literal.

    The floor tuples hold only int/string literals (no nested parens), so the
    body is captured up to the first ``)`` — the same boundary
    ``validate_secret_vocabulary._tuple_pattern`` relies on.
    """
    match = re.search(
        rf"^{re.escape(var_name)}\s*(?::[^=]+)?=\s*\(([^)]*)\)",
        text,
        re.MULTILINE,
    )
    return match.group(1) if match else None


def validate_contract(errors: list[str], path: Path) -> dict | None:
    """Load the contract and assert its structure; return the ``default`` policy."""
    if not path.is_file():
        errors.append(f"contract: missing file: {path}")
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        errors.append(f"contract: unparseable YAML: {exc.__class__.__name__}")
        return None
    if not isinstance(raw, dict):
        errors.append("contract: top level must be a mapping")
        return None

    version = raw.get("version")
    if type(version) is not int or version != 1:
        errors.append("contract: version must be integer 1")

    policies = raw.get("policies")
    if not isinstance(policies, dict) or not policies:
        errors.append("contract: 'policies' must be a non-empty map")
        return None

    for name, policy in policies.items():
        if not isinstance(policy, dict):
            errors.append(f"contract: policy {name!r} must be a mapping")
            continue
        missing = [k for k in REQUIRED_KEYS if k not in policy]
        if missing:
            errors.append(f"contract: policy {name!r} missing keys: {missing}")
            continue
        min_length = policy["min_length"]
        hard_floor = policy["hard_floor"]
        entropy = policy["entropy_floor_bits"]
        classes = policy["required_classes"]
        ambiguous = policy["exclude_ambiguous"]
        for label, value in (
            ("min_length", min_length),
            ("hard_floor", hard_floor),
            ("entropy_floor_bits", entropy),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                errors.append(
                    f"contract: policy {name!r} {label} must be a positive int, "
                    f"got {value!r}"
                )
        if not isinstance(ambiguous, bool):
            errors.append(
                f"contract: policy {name!r} exclude_ambiguous must be a bool, "
                f"got {ambiguous!r}"
            )
        if (
            isinstance(min_length, int)
            and isinstance(hard_floor, int)
            and hard_floor > min_length
        ):
            errors.append(
                f"contract: policy {name!r} hard_floor ({hard_floor}) exceeds "
                f"min_length ({min_length})"
            )
        if not isinstance(classes, list) or not classes:
            errors.append(
                f"contract: policy {name!r} required_classes must be a non-empty list"
            )
        else:
            unknown = [c for c in classes if not isinstance(c, str) or c not in KNOWN_CLASSES]
            if not unknown and len(classes) != len(set(classes)):
                errors.append(f"contract: policy {name!r} has duplicate required_classes")
            if unknown:
                errors.append(
                    f"contract: policy {name!r} required_classes has unknown "
                    f"entries {unknown} (known: {sorted(KNOWN_CLASSES)})"
                )

    default = policies.get("default")
    if not isinstance(default, dict):
        errors.append("contract: v1 must ship a 'default' policy")
        return None
    return default


def validate_connector(
    errors: list[str], notes: list[str], root: Path, default_policy: dict
) -> None:
    """Pin the connector's hardcoded ``default`` floor to the contract."""
    path = root / CONNECTOR_REL
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        errors.append(f"connector: missing or unreadable module {CONNECTOR_REL}")
        return

    floor_body = _tuple_body(CONNECTOR_FLOOR_VAR, text)
    if floor_body is None:
        errors.append(f"connector: {CONNECTOR_FLOOR_VAR} tuple not found in {path}")
        connector_floor = None
    else:
        try:
            connector_floor = ast.literal_eval(f"({floor_body})")
            if not isinstance(connector_floor, tuple) or any(type(n) is not int for n in connector_floor):
                raise ValueError
        except (ValueError, SyntaxError):
            errors.append("connector: floor must contain only integer literals")
            connector_floor = None

    classes_body = _tuple_body(CONNECTOR_CLASSES_VAR, text)
    if classes_body is None:
        errors.append(f"connector: {CONNECTOR_CLASSES_VAR} tuple not found in {path}")
        connector_classes = None
    else:
        try:
            connector_classes = ast.literal_eval(f"({classes_body})")
            if not isinstance(connector_classes, tuple) or any(type(c) is not str for c in connector_classes):
                raise ValueError
        except (ValueError, SyntaxError):
            errors.append("connector: classes must contain only string literals")
            connector_classes = None

    contract_floor = (
        default_policy.get("min_length"),
        default_policy.get("hard_floor"),
        default_policy.get("entropy_floor_bits"),
    )
    contract_classes = tuple(default_policy.get("required_classes") or ())

    if connector_floor is not None and connector_floor != contract_floor:
        errors.append(
            f"connector floor differs from contract default: "
            f"{CONNECTOR_FLOOR_VAR}={connector_floor} (min_length, hard_floor, "
            f"entropy_floor_bits) vs contract {contract_floor}"
        )
    if connector_classes is not None and connector_classes != contract_classes:
        errors.append(
            f"connector required classes differ from contract default: "
            f"{CONNECTOR_CLASSES_VAR}={connector_classes} vs contract "
            f"{contract_classes}"
        )


def main() -> int:
    root = repo_root()
    errors: list[str] = []
    notes: list[str] = []

    default_policy = validate_contract(errors, root / CONTRACT_REL)
    if default_policy is not None and not errors:
        validate_connector(errors, notes, root, default_policy)
    packaged = root / "products/tool-gateway/src/tool_gateway/policies/password-policy.yaml"
    try:
        if packaged.read_bytes() != (root / CONTRACT_REL).read_bytes():
            errors.append("packaged policy differs from canonical contract; run make sync-policy")
    except OSError:
        errors.append("canonical or packaged password policy is missing or unreadable")

    if errors:
        print("FAIL: password-policy contract/connector drift:")
        for e in errors:
            print(f"  - {e}")
        return 1

    for note in notes:
        print(f"NOTE: {note}")
    classes = default_policy.get("required_classes") if default_policy else []
    print(
        "OK: password-policy contract well-formed "
        f"(default: min_length={default_policy.get('min_length')}, "
        f"hard_floor={default_policy.get('hard_floor')}, "
        f"classes={len(classes)}, "
        f"entropy_floor_bits={default_policy.get('entropy_floor_bits')})"
    )
    if not notes:
        print("OK: connector default floor agrees with the contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
