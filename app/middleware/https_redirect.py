from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.scheme == "http":
            # Replace http with https in the URL
            url = str(request.url)
            url = url.replace("http://", "https://", 1)
            return RedirectResponse(url, status_code=301)
        return await call_next(request) 