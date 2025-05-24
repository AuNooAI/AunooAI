"""Application middleware configuration."""

import os
from starlette.middleware.sessions import SessionMiddleware
from app.middleware.https_redirect import HTTPSRedirectMiddleware


def setup_middleware(app):
    """Configure all application middleware."""
    # Add session middleware first
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv("FLASK_SECRET_KEY", "your-fallback-secret-key"),
    )
    
    # Add other middleware as needed
    # app.add_middleware(HTTPSRedirectMiddleware)  # Uncomment if needed
    
    return app