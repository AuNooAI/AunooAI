"""The route table must not drift open again.

Between January 2025 and August 2026 this app accumulated 216 routes that
answered anonymous requests, 87 of them state-changing, and nothing noticed.
The cause was not one bad commit. It was that a route is unprotected unless its
author remembers a dependency, so the unsafe path was silence and the safe path
required vigilance across 1,000+ routes and 19 months.

Nothing in the product can reveal that. Every page requires a login, so a
browser always sends a cookie and every response looks correct. Nothing logs it
either: a route that never refuses produces no errors. The only thing that finds
this class of bug is asking the route table directly, which is what this does.

Adding a route needs no change here. Adding an *unprotected* route fails this
test, and the only way to pass is to declare an auth dependency or to add the
path to PUBLIC_PATHS below with a reason. That is the point: opening a route to
the internet becomes a visible, reviewable edit instead of an omission.
"""
import json
import os
import subprocess
import sys

try:
    import pytest
except ImportError:  # pragma: no cover
    # The nine deploy trees have no pytest in their venv, and installing it
    # there would pull a test runner into production for one file. The checks
    # themselves need nothing but the standard library, so this shims the two
    # pytest names used below and the file stays runnable as a script:
    #     python tests/test_auth_surface.py
    import types

    pytest = types.ModuleType('pytest')

    class _Failed(AssertionError):
        pass

    def _fail(msg):
        raise _Failed(msg)

    def _fixture(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn

    pytest.fail = _fail
    pytest.fixture = _fixture
    pytest.Failed = _Failed
    sys.modules['pytest'] = pytest

# Any of these as a dependency counts as protecting a route.
AUTH_DEPENDENCIES = {
    'verify_session',            # 307 redirect to the login page
    'verify_session_api',        # 401, for XHR callers
    'verify_session_optional',   # signed-link or public-object routes
    'get_current_user',
    'get_current_active_user',
    'get_current_user_optional',
    'require_admin',
    'verify_admin',
}

# Reachable without a session ON PURPOSE. Adding a line here is a security
# decision — say why, and never add a state-changing route (a separate test
# below enforces that).
PUBLIC_PATHS = {
    '/health':                                    'liveness probe',
    '/health/live':                               'liveness probe',
    '/health/ready':                              'readiness probe',
    '/health/startup':                            'startup probe',
    '/api/health':                                'liveness probe',
    '/api/sio/health':                            'liveness probe',
    '/api/eos/health':                            'liveness probe',
    '/auth/login/{provider}':                     'starts the OAuth flow, pre-session by definition',
    '/auth/providers':                            'which OAuth buttons to render on the login page',
    '/api/news-feed/shared/{share_token}':        'share link; the token is the credential',
    '/api/news-feed/api/shared/{share_token}':    'share link; the token is the credential',
}

# Endpoints that authenticate inside the handler rather than via a dependency.
# Named individually and deliberately: pattern-matching the body for
# "request.session" would let a route pass merely by mentioning it. Each of
# these was read and confirmed to refuse unauthenticated callers.
SELF_GUARDED = {
    'app.main::api_change_password',                              # 401 when no session user
    'app.routes.auth_routes::login',                              # the login form itself
    'app.routes.auth_routes::login_page',
    'app.routes.auth_routes::logout',
    'app.routes.auth_routes::reset_password_page',                # HMAC token, expiring, single-use
    'app.routes.auth_routes::reset_password_submit',              # same token check before any write
    'app.routes.oauth_routes::oauth_callback',                    # provider redirect target
    'app.routes.oauth_routes::oauth_logout',
    'app.routes.oauth_routes::oauth_status',
    'app.routes.onboarding_routes::complete_onboarding',          # 401 when no session user
    'app.routes.onboarding_routes::reset_onboarding',             # 401 when no session user
    'app.routes.market_monitor_routes::brightdata_linkedin_callback',  # shared secret, fail-closed
}

WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


# The route table is read in a CHILD process on purpose.
#
# Importing app.main builds the whole application: it opens database
# connections, configures logging and instantiates provider clients. Doing that
# inside the pytest session leaked global state into unrelated tests and turned
# 98 pre-existing failures into 165. The child prints JSON and exits, so this
# test can inspect the assembled app without the session inheriting any of it.
_READER = r"""
import json, logging, sys, warnings
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import app.main
from fastapi.routing import APIRoute

AUTH = set(json.loads(sys.argv[1]))

def dependency_names(dependant):
    names, stack = set(), [dependant]
    while stack:
        node = stack.pop()
        call = getattr(node, 'call', None)
        if call is not None:
            names.add(getattr(call, '__name__', str(call)))
        stack.extend(getattr(node, 'dependencies', []) or [])
    return names

out = []
for route in app.main.app.routes:
    if not isinstance(route, APIRoute):
        continue
    out.append({
        'path': route.path,
        'methods': sorted(route.methods - {'HEAD', 'OPTIONS'}),
        'endpoint': route.endpoint.__module__ + '::' + route.endpoint.__name__,
        'protected': bool(dependency_names(route.dependant) & AUTH),
    })
sys.stdout.write('@@ROUTES@@' + json.dumps(out))
"""


@pytest.fixture(scope='module')
def routes():
    """Every API route, in registration order, with its auth status.

    Read from the built app rather than by parsing source, because a dependency
    can be attached at the decorator, on the router, or at include_router time,
    and only the assembled app knows about all three.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=root)
    proc = subprocess.run(
        [sys.executable, '-c', _READER, json.dumps(sorted(AUTH_DEPENDENCIES))],
        cwd=root, env=env, capture_output=True, text=True, timeout=600,
    )
    if '@@ROUTES@@' not in proc.stdout:
        pytest.fail(
            "could not read the route table; the app failed to import.\n"
            f"exit={proc.returncode}\nstderr tail:\n{proc.stderr[-2000:]}"
        )
    payload = proc.stdout.split('@@ROUTES@@', 1)[1]
    return [
        {**r, 'methods': tuple(r['methods'])}
        for r in json.loads(payload)
    ]


def _live(routes):
    """Only the registration that actually serves each path+method.

    FastAPI matches the first, and this app registers 225 path+method pairs more
    than once. A later copy is dead code, so judging it would report holes that
    are unreachable and — worse — miss that a protected copy is shadowed.
    """
    first = {}
    for i, r in enumerate(routes):
        first.setdefault((r['path'], r['methods']), i)
    return [r for i, r in enumerate(routes)
            if first[(r['path'], r['methods'])] == i]


def test_no_route_is_open_to_anonymous_callers(routes):
    offenders = [
        r for r in _live(routes)
        if not r['protected']
        and r['path'] not in PUBLIC_PATHS
        and r['endpoint'] not in SELF_GUARDED
    ]
    if offenders:
        lines = '\n'.join(
            f"    {','.join(r['methods']):7} {r['path']}\n"
            f"    {'':7} {r['endpoint']}"
            for r in sorted(offenders, key=lambda r: r['path'])
        )
        pytest.fail(
            f"{len(offenders)} route(s) answer anonymous requests:\n{lines}\n\n"
            "Add an auth dependency to each, e.g.\n"
            "    @router.get('/thing', dependencies=[Depends(verify_session_api)])\n"
            "Use verify_session_api for XHR callers (401) and verify_session for\n"
            "pages and browser-navigated downloads (307 to the login page).\n"
            "If a route is genuinely meant to be public, add its path to\n"
            "PUBLIC_PATHS in this file with a reason."
        )


def test_no_open_registration_shadows_a_protected_one(routes):
    """A duplicate registration must not undo an auth fix.

    This app registers many paths twice. If the first copy is open and a later
    one is protected, the protected copy never runs, so a fix applied to it
    looks correct in the diff and changes nothing at runtime. That is the
    hardest version of this bug to spot by reading code.
    """
    groups = {}
    for r in routes:
        groups.setdefault((r['path'], r['methods']), []).append(r)

    shadowed = []
    for (path, methods), copies in groups.items():
        if len(copies) > 1 and not copies[0]['protected'] \
                and any(c['protected'] for c in copies[1:]):
            shadowed.append((path, methods, copies))

    if shadowed:
        lines = '\n'.join(
            f"    {','.join(mm):7} {path}\n" + '\n'.join(
                f"    {'':7}   {'protected' if c['protected'] else 'OPEN     '}  {c['endpoint']}"
                for c in copies)
            for path, mm, copies in sorted(shadowed)
        )
        pytest.fail(
            "An open registration is shadowing a protected one, so the "
            f"protected copy never serves a request:\n{lines}\n\n"
            "Protect the FIRST registration, or remove the duplicate."
        )


def test_nothing_state_changing_is_allowlisted_as_public(routes):
    """PUBLIC_PATHS is for reads. A public write is almost never intended."""
    bad = [r for r in _live(routes)
           if r['path'] in PUBLIC_PATHS and set(r['methods']) & WRITE_METHODS]
    assert not bad, (
        "state-changing route(s) allowlisted as public: "
        + ', '.join(f"{','.join(r['methods'])} {r['path']}" for r in bad)
    )


def test_the_allowlists_have_no_dead_entries(routes):
    """Keep the allowlists honest, so they cannot quietly grow stale cover.

    Entries for a module this tenant does not have are ignored rather than
    failed. The same file ships to ten tenants with different feature sets — a
    site without Market Monitor has no BrightData webhook to guard, and that is
    not a stale allowlist. An entry whose module IS present but whose function
    is gone is stale, and does fail.
    """
    live_paths = {r['path'] for r in routes}
    live_endpoints = {r['endpoint'] for r in routes}
    live_modules = {e.split('::')[0] for e in live_endpoints}

    stale_paths = set(PUBLIC_PATHS) - live_paths
    stale_endpoints = {
        e for e in SELF_GUARDED - live_endpoints
        if e.split('::')[0] in live_modules
    }
    assert not stale_paths, (
        f"PUBLIC_PATHS lists paths that no longer exist: {sorted(stale_paths)}")
    assert not stale_endpoints, (
        "SELF_GUARDED lists endpoints whose module is present but whose "
        f"function is gone: {sorted(stale_endpoints)}")


# The security invariants. A failure here is a hole and exits non-zero.
CHECKS = (
    'test_no_route_is_open_to_anonymous_callers',
    'test_no_open_registration_shadows_a_protected_one',
    'test_nothing_state_changing_is_allowlisted_as_public',
)

# Hygiene, not security. Reported but not fatal in script mode, because the
# deploy trees run older feature sets: pearson's auth_routes has no
# reset_password_submit, so the allowlist names a function that is absent there.
# An entry for a function that does not exist grants no cover, so it cannot
# hide a hole — it is only worth failing in canonical, where a stale entry
# could mask a rename. Under pytest, which runs in canonical, it is strict.
ADVISORY_CHECKS = (
    'test_the_allowlists_have_no_dead_entries',
)


def main():
    """Run the same four checks without a test runner.

    Exists so the invariant is enforceable on the deploy trees, which have no
    pytest. Exits non-zero if any check fails, so it can gate a deploy script
    or a cron job. Under pytest this is not used.
    """
    try:
        table = routes.__wrapped__() if hasattr(routes, '__wrapped__') else routes()
    except AssertionError as exc:
        # Most likely this tenant has no readable .env, so the app refuses to
        # import. Report it as a failure to CHECK rather than a clean pass —
        # an unverifiable route table is not a verified one.
        print(f'ERROR could not read the route table\n{exc}')
        return 2
    failures = 0
    for name in CHECKS:
        try:
            globals()[name](table)
            print(f'PASS  {name}')
        except AssertionError as exc:
            failures += 1
            print(f'FAIL  {name}\n{exc}')
    for name in ADVISORY_CHECKS:
        try:
            globals()[name](table)
            print(f'PASS  {name}')
        except AssertionError as exc:
            print(f'NOTE  {name} (advisory, not a hole)\n{exc}')
    print(f'\n{len(CHECKS) - failures}/{len(CHECKS)} security checks passed '
          f'over {len(table)} registered routes')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
