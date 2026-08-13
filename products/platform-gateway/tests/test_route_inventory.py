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
    ("GET", "/api/v1/sessions/{session_id}"),
    ("POST", "/api/v1/chat"),
    ("GET", "/api/v1/chat/stream"),
    ("GET", "/api/v1/audit/events"),
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
