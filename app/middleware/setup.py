"""Application middleware configuration."""

import os
from starlette.middleware.sessions import SessionMiddleware
from app.middleware.https_redirect import HTTPSRedirectMiddleware


def setup_middleware(app):
    """Configure all application middleware."""
    # This key signs the session cookie, and that cookie is the only thing
    # standing between an anonymous request and a logged-in one. There used to
    # be a fallback of "your-fallback-secret-key" here, which meant a tenant
    # deployed without FLASK_SECRET_KEY would happily accept a session cookie
    # forged by anyone who had read this file. Fail to start instead.
    secret_key = os.getenv("FLASK_SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "FLASK_SECRET_KEY is not set. It signs the session cookie that "
            "carries the logged-in user, so there is no safe default. "
            "Generate one with "
            '`python -c "import secrets; print(secrets.token_urlsafe(32))"` '
            "and add it to .env."
        )

    # Add session middleware first
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
    )

    # Add other middleware as needed
    # app.add_middleware(HTTPSRedirectMiddleware)  # Uncomment if needed

    return app
