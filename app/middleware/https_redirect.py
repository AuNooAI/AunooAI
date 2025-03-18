from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
import os


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip HTTPS redirect if running in Cloud Run or if DISABLE_SSL is set
        if os.getenv("DISABLE_SSL", "false").lower() == "true":
            return await call_next(request)
            
        # Check X-Forwarded-Proto header (used by Cloud Run and other proxies)
        forwarded_proto = request.headers.get("X-Forwarded-Proto")
        if forwarded_proto == "https":
            # The request is already using HTTPS through a proxy
            return await call_next(request)
            
        if request.url.scheme == "http":
            # Replace http with https in the URL
            url = str(request.url)
            url = url.replace("http://", "https://", 1)
            return RedirectResponse(url, status_code=301)
            
        return await call_next(request) 