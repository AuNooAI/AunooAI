"""One router for everything under app/mcp_access, registered once in
``app/core/routers.py``."""

from fastapi import APIRouter

from . import admin_routes, oauth_routes, transport, user_routes

router = APIRouter()
router.include_router(transport.router)
router.include_router(oauth_routes.router)
router.include_router(user_routes.router)
router.include_router(admin_routes.router)
