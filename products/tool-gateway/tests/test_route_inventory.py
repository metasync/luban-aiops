"""Route inventory (SPEC-010 R-2).

Guards the post-split surface: tool-gateway must expose only health/metrics and
the tool API. Any portal-facing route (chat, sessions, auth, identity,
runtime) belongs to platform-gateway and must not reappear here.
"""

import unittest

from tool_gateway.app import create_app

EXPECTED_ROUTES = {
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/metrics"),
    ("GET", "/api/v2/tools"),
    ("POST", "/api/v2/tools/invoke"),
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

    def test_tool_surface_routes_present(self) -> None:
        for route in EXPECTED_ROUTES:
            self.assertIn(route, self.routes)

    def test_portal_facing_routes_absent(self) -> None:
        for method, path in self.routes:
            self.assertFalse(
                path.startswith("/api/v1/"),
                f"portal-facing route leaked into tool-gateway: {method} {path}",
            )


if __name__ == "__main__":
    unittest.main()
