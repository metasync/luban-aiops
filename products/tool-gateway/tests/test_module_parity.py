"""Cross-product drift guards for intentionally duplicated modules.

Several small modules are deliberately copied between products instead of
being extracted into a shared package (extraction is deferred by decision).
These tests pin the copies together: when one copy changes, every sibling
copy must change in the same commit or this suite fails.

Families and their allowed divergence:

- ``core/telemetry.py``        — byte-identical across all eight services.
- ``core/observability.py``    — identical except docstrings (each service
  names its own examples of what the audit trail contains).
- ``services/token_verifier.py`` — identical except the service package and
  settings class names (platform-gateway / tool-gateway).
- ``services/audit_emitter.py``  — identical except docstrings and the
  package / settings class names (platform-gateway / tool-gateway /
  identity-broker / skills-hub / agent-platform / execution-runtime).
  incident-service also
  has an
  ``audit_emitter.py`` but it
  is a different design (a triage ``AuditConnector``), intentionally excluded.
- ``services/ingest_auth.py`` (audit-service) / ``services/query_auth.py``
  (incident-service) — identical except docstrings and the package /
  settings / error class / registry attribute names. The canonical workload
  ladder lives in identity-broker's ``exchange_service.py``, which has a
  different shape and is covered by its own tests.

``policy_engine.py`` is NOT parity-tested: the two gateways share the
evaluation core but own different action vocabularies by design.
"""

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"

# product directory -> python package name
SERVICE_PACKAGES = {
    "agent-platform": "agent_service",
    "audit-service": "audit_service",
    "execution-runtime": "execution_runtime",
    "identity-broker": "identity_service",
    "incident-service": "incident_service",
    "platform-gateway": "platform_gateway",
    "skills-hub": "skills_hub",
    "tool-gateway": "tool_gateway",
}

DRIFT_HINT = (
    "This module is intentionally duplicated across products; apply the "
    "change to every copy listed in test_module_parity.py (or update the "
    "guard if the divergence is deliberate)."
)


def _module_path(product: str, subpackage: str, module: str) -> Path:
    return (
        PRODUCTS_DIR
        / product
        / "src"
        / SERVICE_PACKAGES[product]
        / subpackage
        / f"{module}.py"
    )


def _read(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"expected duplicated module missing: {path}")
    return path.read_text(encoding="utf-8")


def _strip_docstrings(source: str) -> str:
    """Return the source normalized via AST with all docstrings blanked."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body[0].value = ast.Constant(value="")
    return ast.unparse(tree)


def _normalize_identifiers(source: str, package: str, settings_class: str) -> str:
    """Map the per-service package and settings class to fixed placeholders."""
    return source.replace(settings_class, "<SETTINGS>").replace(package, "<PACKAGE>")


def _apply_placeholders(source: str, mapping: dict[str, str]) -> str:
    """Replace each service-specific name with its placeholder, in order."""
    for name, placeholder in mapping.items():
        source = source.replace(name, placeholder)
    return source


class TelemetryParityTest(unittest.TestCase):
    def test_telemetry_copies_are_byte_identical(self) -> None:
        reference = _read(_module_path("agent-platform", "core", "telemetry"))
        for product in SERVICE_PACKAGES:
            with self.subTest(product=product):
                self.assertEqual(
                    _read(_module_path(product, "core", "telemetry")),
                    reference,
                    msg=f"core/telemetry.py drifted in {product}. {DRIFT_HINT}",
                )


class ObservabilityParityTest(unittest.TestCase):
    def test_observability_copies_match_ignoring_docstrings(self) -> None:
        reference = _strip_docstrings(
            _read(_module_path("agent-platform", "core", "observability"))
        )
        for product in SERVICE_PACKAGES:
            with self.subTest(product=product):
                self.assertEqual(
                    _strip_docstrings(
                        _read(_module_path(product, "core", "observability"))
                    ),
                    reference,
                    msg=f"core/observability.py drifted in {product}. {DRIFT_HINT}",
                )


class TokenVerifierParityTest(unittest.TestCase):
    def test_gateway_token_verifiers_match(self) -> None:
        platform = _normalize_identifiers(
            _read(_module_path("platform-gateway", "services", "token_verifier")),
            "platform_gateway",
            "PlatformGatewaySettings",
        )
        tool = _normalize_identifiers(
            _read(_module_path("tool-gateway", "services", "token_verifier")),
            "tool_gateway",
            "GatewaySettings",
        )
        self.assertEqual(
            tool,
            platform,
            msg=f"services/token_verifier.py drifted between gateways. {DRIFT_HINT}",
        )


class AuditEmitterParityTest(unittest.TestCase):
    # incident-service is deliberately absent: its audit_emitter.py is a
    # triage connector, not a copy of the fire-and-forget emitter.
    EMITTERS = {
        "platform-gateway": ("platform_gateway", "PlatformGatewaySettings"),
        "tool-gateway": ("tool_gateway", "GatewaySettings"),
        "identity-broker": ("identity_service", "IdentitySettings"),
        "skills-hub": ("skills_hub", "SkillsSettings"),
        "agent-platform": ("agent_service", "RuntimeSettings"),
        "execution-runtime": ("execution_runtime", "ExecutionSettings"),
    }

    def test_fire_and_forget_emitters_match(self) -> None:
        def canonical(product: str) -> str:
            package, settings_class = self.EMITTERS[product]
            source = _read(_module_path(product, "services", "audit_emitter"))
            # Docstrings must be stripped first: the placeholder substitution
            # produces source that no longer parses as Python.
            return _normalize_identifiers(
                _strip_docstrings(source), package, settings_class
            )

        reference = canonical("tool-gateway")
        for product in self.EMITTERS:
            with self.subTest(product=product):
                self.assertEqual(
                    canonical(product),
                    reference,
                    msg=f"services/audit_emitter.py drifted in {product}. {DRIFT_HINT}",
                )


class ServiceAuthParityTest(unittest.TestCase):
    def test_ingest_and_query_auth_match(self) -> None:
        audit = _apply_placeholders(
            _strip_docstrings(
                _read(_module_path("audit-service", "services", "ingest_auth"))
            ),
            {
                "IngestAuthError": "<ERROR>",
                "AuditSettings": "<SETTINGS>",
                "ingest_clients": "<REGISTRY>",
                "audit_service": "<PACKAGE>",
            },
        )
        incident = _apply_placeholders(
            _strip_docstrings(
                _read(_module_path("incident-service", "services", "query_auth"))
            ),
            {
                "QueryAuthError": "<ERROR>",
                "IncidentSettings": "<SETTINGS>",
                "query_clients": "<REGISTRY>",
                "incident_service": "<PACKAGE>",
            },
        )
        self.assertEqual(
            incident,
            audit,
            msg=f"ingest_auth.py / query_auth.py drifted apart. {DRIFT_HINT}",
        )


if __name__ == "__main__":
    unittest.main()
