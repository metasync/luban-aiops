"""Password-strength policy: the contract loader and the CSPRNG generator.

SPEC-062 R-2 makes ``shared/shared-contracts/policies/password-policy.yaml`` the
single source of truth for generated-password strength. This module is the
tool-gateway consumer of that contract and the only place the generation
algorithm lives, so ``secrets.generate_password`` (``secrets_connector.py``) and
the config tightening guard (``core/config.py``) both read the floor from here
rather than re-declaring it.

Two copies of the ``default`` floor exist on purpose and are pinned to the
contract by the ``validate-password-policy`` leg of ``make verify``:

- ``DEFAULT_POLICY_FLOOR`` / ``DEFAULT_POLICY_CLASSES`` below — minimum
  constraints on every loaded policy; an unreadable or corrupt policy refuses
  generation rather than substituting these values;
- the YAML contract itself.

The store mirrors ``credential_sets.py``: lazy, mtime-refreshed (secret rotation
needs no restart), fail-closed on an unreadable/invalid file, and it never logs
policy *contents* — only the failure class and the loaded policy count.
"""

from __future__ import annotations

import logging
import math
import os
import secrets
import string
from dataclasses import dataclass
from importlib import resources

import yaml

LOGGER = logging.getLogger(__name__)

# The fail-closed ``default`` floor, pinned to the contract by
# ``validate_password_policy.py`` (extracted textually). Tuple order is
# ``(min_length, hard_floor, entropy_floor_bits)``.
DEFAULT_POLICY_FLOOR = (16, 12, 64)
# The required character classes for the ``default`` policy, pinned likewise.
DEFAULT_POLICY_CLASSES = ("upper", "lower", "digit", "symbol")

# The packaged contract resource, synced beside ``policy-default.yaml`` by the
# ``sync-policy`` Makefile target.
_PACKAGED_POLICY_RESOURCE = "password-policy.yaml"

# Hard bound on a requested length so a model cannot ask for an unbounded
# allocation; well above any realistic password and far above the floor.
MAX_PASSWORD_LENGTH = 128

# Character-class alphabets. The symbol set deliberately omits quote, backslash
# and slash characters (shell/JSON-hostile and paste-fragile) and the ambiguous
# set removes the visually-confusable glyphs when ``exclude_ambiguous`` is on.
_CLASS_ALPHABETS: dict[str, str] = {
    "upper": string.ascii_uppercase,
    "lower": string.ascii_lowercase,
    "digit": string.digits,
    "symbol": "!@#$%^&*()-_=+[]{};:,.?",
}
_AMBIGUOUS_CHARS = frozenset("Il1O0o")
KNOWN_CLASSES = frozenset(_CLASS_ALPHABETS)


@dataclass(frozen=True)
class PasswordPolicy:
    """One named policy entry from the contract."""

    min_length: int
    hard_floor: int
    required_classes: tuple[str, ...]
    entropy_floor_bits: int
    exclude_ambiguous: bool


# The built-in floor, constructed from the pinned constants so the fallback and
# the validator target cannot diverge within this module either.
DEFAULT_POLICY = PasswordPolicy(
    min_length=DEFAULT_POLICY_FLOOR[0],
    hard_floor=DEFAULT_POLICY_FLOOR[1],
    required_classes=DEFAULT_POLICY_CLASSES,
    entropy_floor_bits=DEFAULT_POLICY_FLOOR[2],
    exclude_ambiguous=False,
)


class PasswordPolicyError(Exception):
    """Raised when a password cannot be generated to the effective policy."""


def class_alphabet(policy: PasswordPolicy, char_class: str) -> str:
    """The alphabet for one required class, honoring ``exclude_ambiguous``."""
    alphabet = _CLASS_ALPHABETS[char_class]
    if policy.exclude_ambiguous:
        alphabet = "".join(c for c in alphabet if c not in _AMBIGUOUS_CHARS)
    return alphabet


def full_alphabet(policy: PasswordPolicy) -> str:
    """The union alphabet across the policy's required classes."""
    return "".join(
        class_alphabet(policy, char_class)
        for char_class in policy.required_classes
    )


def reconcile_length(policy: PasswordPolicy, requested: int | None) -> int:
    """Resolve a requested length against the policy, tightening only.

    ``None`` uses the policy minimum. A value below the minimum is raised to it
    (longer is stronger, so this is a tightening correction, never a weakening).
    A value above ``MAX_PASSWORD_LENGTH`` or below the number of required classes
    (one character per class cannot be seeded) is a fail-closed refusal.
    """
    if requested is not None and requested < len(policy.required_classes):
        raise PasswordPolicyError("requested length cannot carry every required class")
    length = max(policy.min_length, requested or policy.min_length)
    if length > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"requested length {length} exceeds the maximum "
            f"{MAX_PASSWORD_LENGTH}"
        )
    if length < policy.min_length:
        length = policy.min_length
    if length < policy.hard_floor:
        raise PasswordPolicyError(
            f"effective length {length} is below the hard floor "
            f"{policy.hard_floor}"
        )
    if length < len(policy.required_classes):
        raise PasswordPolicyError(
            f"length {length} cannot carry one character per required class "
            f"({len(policy.required_classes)} classes)"
        )
    return length


def generate_password(policy: PasswordPolicy, length: int) -> str:
    """Generate a password of ``length`` conforming to ``policy``.

    The value comes from ``secrets`` (a CSPRNG) — never the model. One character
    per required class is seeded first so every class is guaranteed present, the
    remainder is drawn from the full alphabet, and the result is shuffled with a
    Fisher-Yates pass driven by ``secrets.randbelow`` so the class positions are
    unbiased and the whole generation flows through the monkeypatchable
    ``secrets`` module. Entropy is asserted against the floor; a policy the
    alphabet cannot satisfy fails closed rather than emitting a weak value.
    """
    alphabet = full_alphabet(policy)
    if not alphabet:
        raise PasswordPolicyError("policy has an empty alphabet")
    if length < len(policy.required_classes) or length > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError("length is outside generation bounds")
    # Conservative entropy before shuffling; guaranteed-class seeds are drawn
    # from smaller alphabets, so n*log2(full alphabet) would overstate it.
    entropy_bits = (length - len(policy.required_classes)) * math.log2(len(alphabet))
    entropy_bits += sum(math.log2(len(class_alphabet(policy, c))) for c in policy.required_classes)
    if entropy_bits < policy.entropy_floor_bits:
        raise PasswordPolicyError(
            f"length {length} over a {len(alphabet)}-character alphabet yields "
            f"{entropy_bits:.1f} bits, below the floor "
            f"{policy.entropy_floor_bits}"
        )
    chars = [secrets.choice(class_alphabet(policy, c)) for c in policy.required_classes]
    chars.extend(secrets.choice(alphabet) for _ in range(length - len(chars)))
    # Fisher-Yates via the CSPRNG (``secrets`` has no ``shuffle``).
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def apply_overrides(
    policy: PasswordPolicy,
    min_length: int | None,
    required_classes: tuple[str, ...] | None,
    exclude_ambiguous: bool,
) -> PasswordPolicy:
    """Tighten a loaded policy with the env overrides.

    ``core/config.py``'s ``__post_init__`` has already refused any override that
    would weaken the contract floor, so this only ever ratchets upward: the
    larger minimum length, the union of required classes, and an exclusion that
    can only be added.
    """
    effective_min = policy.min_length
    if min_length is not None:
        effective_min = max(effective_min, min_length)
    effective_classes = policy.required_classes
    if required_classes is not None:
        merged = list(policy.required_classes)
        merged.extend(c for c in required_classes if c not in merged)
        effective_classes = tuple(merged)
    return PasswordPolicy(
        min_length=effective_min,
        hard_floor=policy.hard_floor,
        required_classes=effective_classes,
        entropy_floor_bits=policy.entropy_floor_bits,
        exclude_ambiguous=policy.exclude_ambiguous or exclude_ambiguous,
    )


def _parse_policy(name: str, raw: object) -> PasswordPolicy | None:
    """Build one ``PasswordPolicy`` from a contract entry; None when invalid."""
    if not isinstance(raw, dict):
        LOGGER.warning("password policy %r ignored: not a mapping", name)
        return None
    min_length = raw.get("min_length")
    hard_floor = raw.get("hard_floor")
    entropy_floor_bits = raw.get("entropy_floor_bits")
    classes = raw.get("required_classes")
    exclude_ambiguous = raw.get("exclude_ambiguous")
    if (
        any(type(v) is not int for v in (min_length, hard_floor, entropy_floor_bits))
        or type(exclude_ambiguous) is not bool
        or not isinstance(classes, list)
        or not all(isinstance(c, str) and c in KNOWN_CLASSES for c in classes)
    ):
        return None
    if (
        not DEFAULT_POLICY_FLOOR[0] <= min_length <= MAX_PASSWORD_LENGTH
        or not DEFAULT_POLICY_FLOOR[1] <= hard_floor <= min_length
        or entropy_floor_bits < DEFAULT_POLICY_FLOOR[2]
        or len(classes) != len(set(classes))
        or not set(DEFAULT_POLICY_CLASSES).issubset(classes)
    ):
        return None
    classes = tuple(classes)
    return PasswordPolicy(
        min_length=min_length,
        hard_floor=hard_floor,
        required_classes=classes,
        entropy_floor_bits=entropy_floor_bits,
        exclude_ambiguous=exclude_ambiguous,
    )


class PasswordPolicyStore:
    """Lazy, mtime-refreshed, fail-closed view of the password-policy contract.

    An empty path loads the packaged contract synced into the image. Any
    unreadable or invalid file clears the active policies and refuses generation.
    Neither stale policies nor built-in defaults replace an unavailable contract.
    Contents are never logged.
    """

    def __init__(self, path: str = "") -> None:
        self._path = path
        self._mtime: float | None = None
        self._policies: dict[str, PasswordPolicy] = {}
        self._loaded = False

    @property
    def configured(self) -> bool:
        """True when an explicit contract path is set (vs. the packaged one)."""
        return bool(self._path)

    def names(self) -> list[str]:
        """Policy names are safe to surface (names are not secrets)."""
        self._maybe_reload()
        return sorted(self._policies)

    def get(self, name: str = "default") -> PasswordPolicy | None:
        """Resolve one named policy; ``None`` when the name is unknown."""
        self._maybe_reload()
        return self._policies.get(name)

    def default(self) -> PasswordPolicy:
        """Return the active default or refuse an unavailable contract."""
        policy = self.get("default")
        if policy is None:
            raise PasswordPolicyError("Password policy is unavailable")
        return policy

    def _maybe_reload(self) -> None:
        try:
            if self._path:
                mtime = os.stat(self._path).st_mtime
            else:
                # A packaged resource has no meaningful mtime; load it once.
                if self._loaded:
                    return
                mtime = None
        except OSError:
            self._policies = {}
            self._loaded = False
            return
        if self._loaded and mtime is not None and mtime == self._mtime:
            return
        self._reload(mtime)

    def _read_text(self) -> str | None:
        try:
            if self._path:
                with open(self._path, encoding="utf-8") as handle:
                    return handle.read()
            return (
                resources.files("tool_gateway.policies")
                .joinpath(_PACKAGED_POLICY_RESOURCE)
                .read_text(encoding="utf-8")
            )
        except (OSError, ValueError, ModuleNotFoundError) as exc:
            # Log the failure class only — never the file contents.
            LOGGER.warning(
                "password policy contract unreadable (%s); generation refused",
                exc.__class__.__name__,
            )
            return None

    def _reload(self, mtime: float | None) -> None:
        self._policies = {}
        text = self._read_text()
        if text is None:
            self._loaded = True
            return
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            LOGGER.warning(
                "password policy contract unparseable (%s); generation refused",
                exc.__class__.__name__,
            )
            self._loaded = True
            return
        policies = raw.get("policies") if isinstance(raw, dict) else None
        if (not isinstance(policies, dict) or "default" not in policies
                or type(raw.get("version")) is not int or raw["version"] != 1):
            LOGGER.warning("password policy contract has invalid structure")
            self._loaded = True
            return
        parsed: dict[str, PasswordPolicy] = {}
        for name, entry in policies.items():
            policy = _parse_policy(str(name), entry)
            if policy is None:
                self._loaded = False
                return
            parsed[str(name)] = policy
        if not parsed:
            LOGGER.warning("password policy contract yielded no valid policies")
            self._loaded = True
            return
        self._policies = parsed
        self._mtime = mtime
        self._loaded = True
        LOGGER.info("password policies loaded: %d policy(ies)", len(parsed))
