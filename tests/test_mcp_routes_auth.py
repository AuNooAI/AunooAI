"""Every route under app/mcp_access is either behind a session dependency or on a
short, named list of endpoints that authenticate inside the handler."""

import pytest
from fastapi.routing import APIRoute

from app.security.session import require_admin, verify_session, verify_session_api

# Reachable without a session on purpose. Each authenticates inside or is
# a public discovery document.
OPEN = {
    ("POST", "/mcp"),          # bearer key / OAuth JWT checked inside, 401 otherwise
    ("GET", "/mcp"),           # 405, no data
    ("DELETE", "/mcp"),        # 204, no data
    ("GET", "/.well-known/oauth-protected-resource"),
    ("GET", "/.well-known/oauth-authorization-server"),
    ("POST", "/oauth/register"),   # RFC 7591 is anonymous by design; rate limited
    ("GET", "/oauth/authorize"),   # redirects to /login when signed out
    ("POST", "/oauth/token"),      # client secret + PKCE checked inside
}


def _dependency_calls(route):
    seen = set()

    def walk(dependant):
        for sub in dependant.dependencies:
            if sub.call is not None:
                seen.add(sub.call)
            walk(sub)

    walk(route.dependant)
    return seen


def _routes():
    from app.mcp_access import router
    return [r for r in router.routes if isinstance(r, APIRoute)]


def _method_paths(route):
    return [(m, route.path) for m in sorted(route.methods) if m != "HEAD"]


def test_open_set_is_exact():
    found = {mp for r in _routes() for mp in _method_paths(r)
             if not ({verify_session, verify_session_api, require_admin} & _dependency_calls(r))}
    assert found == OPEN, f"open routes changed: +{found - OPEN} -{OPEN - found}"


def test_consent_pages_require_a_session():
    for r in _routes():
        if r.path == "/oauth/consent":
            assert verify_session in _dependency_calls(r), r.path


def test_admin_routes_require_admin_and_401_first():
    admin_routes = [r for r in _routes() if r.path.startswith("/api/mcp-keys")]
    assert admin_routes
    for r in admin_routes:
        calls = _dependency_calls(r)
        assert require_admin in calls, r.path
        assert verify_session_api in calls, r.path


def test_self_service_routes_require_a_session():
    mine = [r for r in _routes() if r.path.startswith("/api/mcp/me")]
    assert len(mine) >= 6, [r.path for r in mine]
    for r in mine:
        assert verify_session_api in _dependency_calls(r), r.path
