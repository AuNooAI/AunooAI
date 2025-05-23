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

### 2. OAuth Authentication (Recommended for Production)

**Implementation**: `app.security.oauth` and `app.security.oauth_users`

**Use Case**: Modern web authentication using external providers (Google, GitHub, Microsoft)

**How it works**:
- Users authenticate via OAuth2 flow with external providers
- Server validates OAuth tokens and creates local user records
- Access control via domain restrictions and/or user allowlist
- Sessions created upon successful OAuth authentication

**Supported Providers**:
- Google OAuth2
- GitHub OAuth2  
- Microsoft OAuth2

**Usage Pattern**:
```python
# OAuth routes are automatically configured
# Session-based authentication works seamlessly after OAuth login
from app.security.session import verify_session
from fastapi import Depends

@router.get("/protected-endpoint")
async def protected_function(
    session=Depends(verify_session)  # Works for both traditional and OAuth sessions
):
    # Your endpoint logic here
    pass
```

**OAuth Security Configuration**:

*Domain Restrictions*:
```bash
# Restrict to specific email domains
export ALLOWED_EMAIL_DOMAINS="yourcompany.com,partner.org"
```

*User Allowlist*:
```python
# Managed via database table oauth_allowlist
# Use admin routes or deployment script to manage
```

**OAuth Routes**:
- `GET /auth/providers` - List available OAuth providers
- `GET /auth/login/{provider}` - Initiate OAuth login
- `GET /auth/callback/{provider}` - Handle OAuth callback
- `POST /auth/logout` - Logout user
- `GET /auth/status` - Get authentication status

**Admin Management Routes** (requires session authentication):
- `GET /admin/oauth/allowlist` - View user allowlist
- `POST /admin/oauth/allowlist/add` - Add user to allowlist
- `DELETE /admin/oauth/allowlist/{email}` - Remove user from allowlist
- `GET /admin/oauth/users` - List all OAuth users
- `GET /admin/oauth/status` - Get OAuth system status

### 3. JWT Authentication (Available but not actively used)

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
20. **OAuth Admin** (`oauth_admin_routes.py`) - OAuth user and allowlist management

### 🔓 Public Routes (No Authentication Required)

The following routes are publicly accessible:

1. **OAuth Authentication** (`oauth_routes.py`):
   - `GET /auth/providers` - List available OAuth providers
   - `GET /auth/login/{provider}` - Initiate OAuth login
   - `GET /auth/callback/{provider}` - Handle OAuth callback
   - `GET /auth/status` - Get authentication status
   - `POST /auth/logout` - Logout (but requires valid session to be meaningful)

2. **Static Assets**: CSS, JavaScript, images
3. **Health Check**: Application status endpoints (if configured)

## Implementation Guidelines

### When to Use Session Authentication

**Use `session=Depends(verify_session)` for**:
- All web page routes
- API endpoints accessed by web application
- Administrative functions
- Data modification operations
- Sensitive data retrieval

**Note**: Session authentication works for both traditional login and OAuth-authenticated users

### When to Use OAuth Authentication

**Recommended for production deployments when**:
- You want modern, secure authentication
- Users have Google/GitHub/Microsoft accounts
- You need centralized identity management
- You want to avoid password management
- Multi-tenant or enterprise deployments

**OAuth Security Levels**:
- `OPEN`: No restrictions (anyone with valid OAuth account can access)
- `HIGH`: Domain restrictions and/or user allowlist enabled

### When to Use JWT Authentication

**Use JWT authentication for**:
- Programmatic API access
- Third-party integrations
- Mobile app backends
- Service-to-service communication

### OAuth Deployment Patterns

**Development/Testing**:
```bash
# No restrictions - anyone can log in
# ALLOWED_EMAIL_DOMAINS not set
# No allowlist entries
```

**Production with Domain Restrictions**:
```bash
export ALLOWED_EMAIL_DOMAINS="yourcompany.com,partner.org"
```

**Production with User Allowlist**:
```bash
# Use deployment script to add approved users
python scripts/setup_oauth_allowlist.py add admin@company.com support@company.com
```

**High Security (Both Restrictions)**:
```bash
export ALLOWED_EMAIL_DOMAINS="yourcompany.com"
python scripts/setup_oauth_allowlist.py add admin@yourcompany.com
```

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

### 2. OAuth Security Configuration

**For Production Deployments**:
- **Always configure access restrictions** - Never leave OAuth in `OPEN` mode for production
- **Use domain restrictions** for organization-wide access: `ALLOWED_EMAIL_DOMAINS="company.com"`
- **Use user allowlist** for granular control: Add only approved users
- **Combine both** for maximum security in sensitive environments

**OAuth Provider Security**:
- Use HTTPS redirect URIs in OAuth provider configuration
- Configure OAuth applications with minimal necessary scopes
- Regularly rotate OAuth client secrets
- Monitor OAuth provider security advisories

### 3. Access Control Management

**User Allowlist Best Practices**:
- Pre-populate allowlist during deployment using `scripts/setup_oauth_allowlist.py`
- Implement approval workflow for new user requests
- Regular allowlist audits and cleanup of inactive users
- Track who added users via `added_by` field

**Domain Restrictions**:
- Whitelist only trusted organizational domains
- Consider contractor/partner domain policies
- Document domain restriction policies clearly

### 4. Sensitive Operations
- Database operations (backup, restore, reset) require authentication
- AI/ML operations require authentication
- Data export operations require authentication
- Administrative functions require authentication
- OAuth user management requires admin-level session authentication

### 5. Error Handling
- Session authentication redirects to login page (307 redirect)
- JWT authentication returns 401 Unauthorized
- WebSocket authentication closes connection with appropriate code
- OAuth failures redirect to login with user-friendly error messages
- Log security events for monitoring and audit

### 6. Monitoring and Auditing

**OAuth Security Monitoring**:
- Monitor failed OAuth login attempts
- Track new user registrations via OAuth
- Alert on allowlist modifications
- Monitor domain restriction bypasses
- Regular security status reviews via `/admin/oauth/status`

**Audit Trail**:
- Log all allowlist changes with timestamps and actors
- Track OAuth user creation and updates
- Monitor admin access to OAuth management routes

## Testing Authentication

To test authentication implementation:

1. **Session Testing**: Access protected endpoints without logging in - should redirect to `/login`
2. **API Testing**: Call API endpoints without session - should return 307 redirect
3. **WebSocket Testing**: Connect to WebSocket without session - should close connection
4. **OAuth Testing**: 
   - Test OAuth login flow with configured providers
   - Verify domain restrictions work correctly
   - Test allowlist enforcement
   - Confirm denied users receive appropriate error messages

## Configuration

### Session Authentication Configuration

Session authentication is configured via:
- `SECRET_KEY` environment variable (NORN_SECRET_KEY)
- Starlette SessionMiddleware in main application setup
- Session storage in cookies

### OAuth Authentication Configuration

**Environment Variables**:
```bash
# OAuth Provider Credentials
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
MICROSOFT_CLIENT_ID=your_microsoft_client_id
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret

# OAuth Security Configuration
ALLOWED_EMAIL_DOMAINS=company.com,partner.org  # Optional: Domain restrictions
```

**OAuth Provider Setup**:

*Google OAuth2*:
1. Create project in Google Cloud Console
2. Enable Google+ API
3. Create OAuth2 credentials
4. Add redirect URI: `https://yourdomain.com/auth/callback/google`

*GitHub OAuth2*:
1. Create OAuth App in GitHub Settings
2. Set Authorization callback URL: `https://yourdomain.com/auth/callback/github`

*Microsoft OAuth2*:
1. Register app in Azure AD
2. Configure redirect URI: `https://yourdomain.com/auth/callback/microsoft`

**Database Tables** (automatically created):
- `oauth_users` - OAuth user records
- `oauth_sessions` - OAuth session tracking
- `oauth_allowlist` - User access control list

**Deployment Script Configuration**:
```bash
# Add users during deployment
python scripts/setup_oauth_allowlist.py config oauth_config.json

# Or add individual users
python scripts/setup_oauth_allowlist.py add admin@company.com --added-by deployment
```

### JWT Authentication Configuration

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

### OAuth-Specific Issues

1. **OAuth Provider Not Configured**: 
   - Verify `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set
   - Check provider configuration with `GET /auth/config-check`

2. **Access Denied Errors**:
   - Check domain restrictions: `ALLOWED_EMAIL_DOMAINS` environment variable
   - Verify user is in allowlist: `python scripts/setup_oauth_allowlist.py list`
   - Review security level: `python scripts/setup_oauth_allowlist.py status`

3. **OAuth Callback Failures**:
   - Verify redirect URIs match OAuth provider configuration exactly
   - Check for HTTPS requirements in production
   - Ensure OAuth provider credentials are correct

4. **Private IP Address Issues** (Google OAuth):
   - Google OAuth may not work with private IP addresses
   - Use `localhost` for local development
   - Configure proper domain names for production

5. **User Not Created After OAuth Login**:
   - Check application logs for domain/allowlist restrictions
   - Verify database permissions for table creation
   - Confirm OAuth user extraction from provider response

### Debug Steps

1. Check application logs for authentication errors
2. Verify session cookies are being set properly
3. Confirm middleware configuration in main application
4. Test authentication flow manually via browser/API client
5. **OAuth Debug Steps**:
   - Check OAuth provider configuration: `GET /auth/providers`
   - Review OAuth status: `GET /auth/status`
   - Verify admin OAuth status: `GET /admin/oauth/status`
   - Test allowlist management: `python scripts/setup_oauth_allowlist.py list`

## Future Enhancements

### ✅ Recently Implemented
- OAuth authentication with Google, GitHub, Microsoft
- Domain-based access restrictions
- User allowlist for granular access control
- OAuth admin management interface
- Deployment script for tenant provisioning
- Comprehensive audit logging

### 🔮 Planned Enhancements
- **Role-based access control (RBAC)**: Different permission levels for users
- **API rate limiting**: For authenticated endpoints
- **Session timeout configuration**: Configurable session expiration
- **Two-factor authentication**: Additional security layer
- **SSO integration**: Enterprise single sign-on support
- **OAuth token refresh**: Automatic token renewal
- **User self-service**: Allow users to request access