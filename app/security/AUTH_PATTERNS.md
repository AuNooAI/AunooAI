# Authentication Patterns for AunooAI

## Overview

This document outlines the authentication patterns implemented across the AunooAI application to ensure consistent security practices.

## Authentication Systems

### 1. Session-Based Authentication (Primary)

**Implementation**: `app.security.session.verify_session`

**Use Case**: Web routes and API endpoints that are accessed by authenticated web users

**How it works**:
- Users log in via traditional web form
- Server creates a session stored in cookies via Starlette's SessionMiddleware
- `verify_session` checks for valid session in request
- Redirects to `/login` page if session is invalid (HTTP 307)

**Usage Pattern**:
```python
from app.security.session import verify_session
from fastapi import Depends

@router.get("/protected-endpoint")
async def protected_function(
    # other parameters...
    session=Depends(verify_session)
):
    # Your endpoint logic here
    pass
```

### 2. JWT Authentication (Available but not actively used)

**Implementation**: `app.security.auth.get_current_user`

**Use Case**: Intended for programmatic API access (future enhancement)

**How it works**:
- Client obtains JWT token via OAuth2 flow
- Token includes username and expiration
- `get_current_user` validates JWT token
- Returns user object or raises 401 error

**Usage Pattern** (when needed):
```python
from app.security.auth import get_current_user
from fastapi import Depends

@router.get("/api-endpoint")
async def api_function(
    current_user: User = Depends(get_current_user)
):
    # Your API logic here
    pass
```

## Current Authentication Status

### ✅ Fully Protected Routes

All endpoints in these files require session authentication:

1. **Web Routes** (`web_routes.py`) - All page routes
2. **Chat Routes** (`chat_routes.py`) - Database chat functionality
3. **Topic Management** (`topic_routes.py`, `topic_map_routes.py`) - Topic CRUD operations
4. **Newsletter** (`newsletter_routes.py`) - Newsletter compilation
5. **Keyword Monitoring** (`keyword_alerts.py`, `keyword_monitor.py`, `keyword_monitor_api.py`) - Alert management
6. **Onboarding** (`onboarding_routes.py`) - User onboarding flow
7. **Statistics** (`stats_routes.py`) - Application statistics
8. **Vector Search Enhanced** (`vector_routes_enhanced.py`) - Advanced search with caching
9. **Database Operations** (`database.py`) - Database downloads, backups, resets
10. **Dashboard Analytics** (`dashboard_routes.py`) - Business intelligence endpoints
11. **Vector Search** (`vector_routes.py`) - Semantic search and ML operations
12. **API Routes** (`api_routes.py`) - Enriched articles API
13. **Dataset Management** (`dataset_routes.py`) - Media bias data operations
14. **Podcast Generation** (`podcast_routes.py`) - AI podcast creation
15. **Prompt Management** (`prompt_routes.py`) - Prompt versioning and templates
16. **Saved Searches** (`saved_searches.py`) - Search persistence
17. **Scenario Builder** (`scenario_routes.py`) - Business scenario management
18. **Media Bias** (`media_bias_routes.py`) - Media bias API operations
19. **Auspex Service** (`auspex_routes.py`) - AI suggestion service

## Implementation Guidelines

### When to Use Session Authentication

**Use `session=Depends(verify_session)` for**:
- All web page routes
- API endpoints accessed by web application
- Administrative functions
- Data modification operations
- Sensitive data retrieval

### When to Use JWT Authentication

**Use JWT authentication for**:
- Programmatic API access
- Third-party integrations
- Mobile app backends
- Service-to-service communication

### WebSocket Authentication

For WebSocket endpoints, implement basic session checking:

```python
@router.websocket("/ws-endpoint")
async def websocket_endpoint(websocket):
    # Check for session in cookies
    try:
        cookies = websocket.cookies
        if not cookies.get('session'):
            await websocket.close(code=1008, reason="Authentication required")
            return
    except Exception:
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    await websocket.accept()
    # Your WebSocket logic here
```

## Security Best Practices

### 1. Consistent Authentication
- All endpoints should have authentication unless they are explicitly public
- Use the same authentication method within related functionality
- Document any exceptions clearly

### 2. Sensitive Operations
- Database operations (backup, restore, reset) require authentication
- AI/ML operations require authentication
- Data export operations require authentication
- Administrative functions require authentication

### 3. Error Handling
- Session authentication redirects to login page (307 redirect)
- JWT authentication returns 401 Unauthorized
- WebSocket authentication closes connection with appropriate code

### 4. Future Enhancements
- Consider implementing role-based access control (RBAC)
- Add API rate limiting for authenticated endpoints
- Implement session timeout configuration
- Add audit logging for sensitive operations

## Testing Authentication

To test authentication implementation:

1. **Session Testing**: Access protected endpoints without logging in - should redirect to `/login`
2. **API Testing**: Call API endpoints without session - should return 307 redirect
3. **WebSocket Testing**: Connect to WebSocket without session - should close connection

## Configuration

Session authentication is configured via:
- `SECRET_KEY` environment variable (NORN_SECRET_KEY)
- Starlette SessionMiddleware in main application setup
- Session storage in cookies

JWT authentication is configured via:
- `SECRET_KEY` environment variable
- Token expiration settings in `auth.py`
- OAuth2 password bearer scheme

## Troubleshooting

### Common Issues

1. **Import Error**: Ensure `from app.security.session import verify_session` is imported
2. **Redirect Loop**: Check if login page itself requires authentication
3. **Session Not Found**: Verify SessionMiddleware is properly configured
4. **JWT Token Invalid**: Check token expiration and signing key

### Debug Steps

1. Check application logs for authentication errors
2. Verify session cookies are being set properly
3. Confirm middleware configuration in main application
4. Test authentication flow manually via browser/API client