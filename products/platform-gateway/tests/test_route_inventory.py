"""Route inventory (SPEC-010 R-1).

Guards the extracted edge surface: platform-gateway owns the portal-facing
routes (health/metrics, auth, identity, runtime, sessions, chat). The tool
API belongs to tool-gateway and must not reappear here.
"""

import unittest

from platform_gateway.app import create_app

EXPECTED_ROUTES = {
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/metrics"),
    ("GET", "/api/v1/runtime"),
    ("GET", "/api/v1/auth/login-url"),
    ("GET", "/api/v1/auth/login"),
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/callback"),
    ("POST", "/api/v1/auth/logout-url"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/identity/normalize"),
    ("POST", "/api/v1/sessions"),
    # Session workspace lifecycle (SPEC-022 R-1): caller-scoped list and
    # owner-only delete ride the same session surface.
    ("GET", "/api/v1/sessions"),
    ("GET", "/api/v1/sessions/{session_id}"),
    ("DELETE", "/api/v1/sessions/{session_id}"),
    ("POST", "/api/v1/chat"),
    ("GET", "/api/v1/chat/stream"),
    # HITL confirmation bridging (SPEC-020): answers a parked kernel ASK.
    ("POST", "/api/v1/chat/confirm"),
    ("GET", "/api/v1/audit/events"),
    ("GET", "/api/v1/incidents"),
    ("POST", "/api/v1/incidents"),
    ("GET", "/api/v1/incidents/{incident_id}"),
    ("GET", "/api/v1/incidents/{incident_id}/report"),
    ("POST", "/api/v1/incidents/{incident_id}/triage"),
    # Portal transparency surfaces (SPEC-019): the live policy matrix and
    # read-only workspace inventories. The tool *API* still lives on
    # tool-gateway; these are v1 portal-facing proxies.
    ("GET", "/api/v1/policy/matrix"),
    ("GET", "/api/v1/tools"),
    ("GET", "/api/v1/skills"),
    # Model catalog discovery (SPEC-024 R-2): credential-gated catalog
    # pass-through, discovery-safe payload.
    ("GET", "/api/v1/models"),
    # Approval inbox (SPEC-031 R-3): cross-session confirmation discovery
    # for the designated decider roles.
    ("GET", "/api/v1/approvals/inbox"),
}


def _iter_routes(routes):
    """Yield endpoint routes, descending into included-router containers."""
    for route in routes:
        container = getattr(route, "original_router", None)
        nested = (
            container.routes
            if container is not None
            else getattr(route, "routes", None)
        )
        if nested is not None:
            yield from _iter_routes(nested)
        elif getattr(route, "methods", None):
            yield route


class RouteInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.routes = {
            (method, route.path)
            for route in _iter_routes(self.app.routes)
            for method in route.methods
        }

    def test_edge_surface_routes_present(self) -> None:
        for route in EXPECTED_ROUTES:
            self.assertIn(route, self.routes)

    def test_tool_routes_absent(self) -> None:
        for method, path in self.routes:
            self.assertFalse(
                path.startswith("/api/v2/"),
                f"tool route leaked into platform-gateway: {method} {path}",
            )


if __name__ == "__main__":
    unittest.main()
