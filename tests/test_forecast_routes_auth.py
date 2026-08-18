"""Every Forecast Tracker, Topic Report and candidate-triage endpoint must be
behind authentication.

Before 2026-08-18 none of them were. All three routers were built as a bare
``APIRouter()``, and nothing in the deployed stack made up the difference:
``app/server_run.py`` imports ``app/main.py``, which calls ``create_app()``,
whose only middleware is Starlette's ``SessionMiddleware`` (cookie handling,
not authentication). An anonymous ``GET https://<tenant>/api/forecast/topics``
returned 200 with the customer's tracked topics on every deployed tenant.

These tests read the real router objects and assert the dependency is present
on every route, so a route added later without auth fails the suite rather than
shipping open. They deliberately do not build a database or an app: importing
these route modules is safe because their DB imports are function-local, and
this repo has no test database — see tests/conftest.py for what happened the
last time a test touched live state.
"""

import pytest
from fastapi.routing import APIRoute

from app.security.session import require_admin, verify_session_api

# Routers whose every endpoint is private.
ROUTER_MODULES = [
    "app.routes.forecast_assessment_routes",
    "app.routes.topic_report_routes",
    "app.routes.wiley_candidates_routes",
]

# Operations that need more than a logged-in user: they email customers,
# replace a production overlay file, or release content for delivery.
ADMIN_ONLY = {
    ("PATCH", "/api/forecast/topics/{topic}/delivery"),
    ("POST", "/api/forecast/topics/{topic}/overlay/approve"),
    ("POST", "/api/forecast/deliverables/send"),
    ("POST", "/api/forecast/deliverables/review/approve"),
}


def _load_router(module_path):
    import importlib

    return importlib.import_module(module_path).router


def _dependency_calls(route):
    """Every callable FastAPI will invoke as a dependency for this route."""
    seen = set()

    def walk(dependant):
        for sub in dependant.dependencies:
            if sub.call is not None:
                seen.add(sub.call)
            walk(sub)

    walk(route.dependant)
    return seen


def _routes(module_path):
    return [r for r in _load_router(module_path).routes if isinstance(r, APIRoute)]


def _method_paths(route):
    return [(m, route.path) for m in sorted(route.methods) if m != "HEAD"]


@pytest.mark.parametrize("module_path", ROUTER_MODULES)
def test_every_route_requires_authentication(module_path):
    """No endpoint on these routers may be reachable anonymously."""
    routes = _routes(module_path)
    assert routes, f"{module_path} exposed no routes — the check would pass vacuously"

    unprotected = [
        f"{m} {p}"
        for route in routes
        for (m, p) in _method_paths(route)
        if verify_session_api not in _dependency_calls(route)
    ]
    assert not unprotected, (
        f"{module_path} has endpoints without verify_session_api: {unprotected}"
    )


def test_privileged_operations_additionally_require_admin():
    """Sending email, replacing a production overlay, and approving a bundle
    for delivery are admin-only, not merely logged-in."""
    found = {}
    for module_path in ROUTER_MODULES:
        for route in _routes(module_path):
            for key in _method_paths(route):
                found[key] = _dependency_calls(route)

    missing_route = [k for k in ADMIN_ONLY if k not in found]
    assert not missing_route, (
        f"these privileged routes no longer exist under the expected method+path "
        f"(update ADMIN_ONLY if they moved): {missing_route}"
    )

    not_admin_gated = [f"{m} {p}" for (m, p) in ADMIN_ONLY if require_admin not in found[(m, p)]]
    assert not not_admin_gated, (
        f"privileged endpoints missing require_admin: {not_admin_gated}"
    )


def test_admin_routes_are_also_session_checked():
    """require_admin calls verify_session, which 307-redirects to /login rather
    than returning 401. Router-level verify_session_api must therefore still be
    present on the admin routes so an anonymous API caller gets a 401 first."""
    for module_path in ROUTER_MODULES:
        for route in _routes(module_path):
            calls = _dependency_calls(route)
            if require_admin in calls:
                assert verify_session_api in calls, (
                    f"{route.path} is admin-gated but not session-checked, so an "
                    f"anonymous caller would get a login redirect instead of 401"
                )
