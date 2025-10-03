from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from app.security.oauth import oauth, is_provider_configured, get_oauth_redirect_uri, OAUTH_PROVIDERS
from app.security.oauth_users import OAuthUserManager, create_oauth_session_data
from app.database import get_database_instance, Database
import logging
from urllib.parse import quote_plus, unquote_plus
import httpx
import os

router = APIRouter(prefix="/auth", tags=["OAuth"])
logger = logging.getLogger(__name__)

@router.get("/providers")
async def get_available_providers():
    """Get list of available OAuth providers"""
    from app.security.oauth import get_configured_providers
    
    configured = get_configured_providers()
    providers = []
    
    for provider_name in configured:
        if provider_name in OAUTH_PROVIDERS:
            providers.append({
                'name': provider_name,
                'display_name': OAUTH_PROVIDERS[provider_name]['name'],
                'icon': OAUTH_PROVIDERS[provider_name]['icon'],
                'color': OAUTH_PROVIDERS[provider_name]['color'],
                'button_class': OAUTH_PROVIDERS[provider_name]['button_class']
            })
    
    return {
        'providers': providers,
        'count': len(providers)
    }

@router.get("/login/{provider}")
async def oauth_login(provider: str, request: Request):
    """Initiate OAuth login with provider (google/github/microsoft)"""
    
    # Validate provider
    if not is_provider_configured(provider):
        raise HTTPException(
            status_code=400, 
            detail=f"OAuth provider '{provider}' is not configured or supported"
        )
    
    try:
        # Get OAuth client for the provider
        client = oauth.create_client(provider)
        if not client:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create OAuth client for {provider}"
            )
        
        # Generate redirect URI
        redirect_uri = get_oauth_redirect_uri(request, provider)
        logger.info(f"Initiating OAuth login for {provider}, redirect_uri: {redirect_uri}")
        
        # Check for private IP address issues with Google
        if provider == 'google' and ('192.168.' in redirect_uri or '10.' in redirect_uri or '172.' in redirect_uri or 'localhost' not in redirect_uri.lower()):
            error_msg = (
                "Google OAuth doesn't support private IP addresses reliably. "
                "Please access your application via localhost instead: "
                "http://localhost:10000 and update your Google OAuth redirect URI to: "
                "http://localhost:10000/auth/callback/google"
            )
            logger.warning(f"Private IP detected in redirect URI: {redirect_uri}")
            return RedirectResponse(
                url=f"/login?error={quote_plus(error_msg)}",
                status_code=302
            )
        
        # Initiate OAuth flow
        return await client.authorize_redirect(request, redirect_uri)
        
    except Exception as e:
        logger.error(f"OAuth login error for {provider}: {e}")
        # Redirect to login page with error
        return RedirectResponse(
            url=f"/login?error={quote_plus(f'OAuth login failed: {str(e)}')}",
            status_code=302
        )

@router.get("/callback/{provider}")
async def oauth_callback(provider: str, request: Request, db: Database = Depends(get_database_instance)):
    """Handle OAuth callback and create session"""
    
    # Validate provider
    if not is_provider_configured(provider):
        raise HTTPException(
            status_code=400,
            detail=f"OAuth provider '{provider}' is not configured"
        )
    
    try:
        # Get OAuth client
        client = oauth.create_client(provider)
        if not client:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create OAuth client for {provider}"
            )
        
        # Get access token from callback
        try:
            token = await client.authorize_access_token(request)
        except Exception as e:
            logger.error(f"Failed to get access token for {provider}: {e}")
            
            # Provide specific error messages based on the error type
            error_msg = str(e)
            if "invalid_client" in error_msg.lower():
                error_msg = (
                    "OAuth client not found. Please check your GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET "
                    "are correct and match your Google Cloud Console configuration."
                )
            elif "invalid_request" in error_msg.lower():
                error_msg = (
                    "OAuth request invalid. Please check your redirect URI configuration "
                    "in Google Cloud Console matches your application URL."
                )
            else:
                error_msg = f"Authentication failed: {error_msg}"
            
            return RedirectResponse(
                url=f"/login?error={quote_plus(error_msg)}",
                status_code=302
            )
        
        # Extract user information based on provider
        user_info = await extract_user_info(client, token, provider)
        
        if not user_info or not user_info.get('email'):
            logger.error(f"Failed to get user info from {provider}")
            return RedirectResponse(
                url=f"/login?error={quote_plus('Failed to get user information. Please try again.')}",
                status_code=302
            )
        
        # Create or update user in database
        oauth_manager = OAuthUserManager(db)
        try:
            oauth_user = oauth_manager.create_or_update_oauth_user(
                email=user_info['email'],
                name=user_info.get('name'),
                provider=provider,
                provider_id=user_info.get('id'),
                avatar_url=user_info.get('avatar_url')
            )
        except Exception as e:
            logger.error(f"Failed to create/update OAuth user: {e}")
            return RedirectResponse(
                url=f"/login?error={quote_plus('Failed to create user account. Please try again.')}",
                status_code=302
            )
        
        # Create session
        session_data = create_oauth_session_data(oauth_user)
        request.session.update(session_data)
        
        logger.info(f"OAuth login successful for {user_info['email']} via {provider}")

        # Redirect to unified feed or intended page
        redirect_url = request.session.get('oauth_redirect_after_login', '/unified-feed')
        return RedirectResponse(url=redirect_url, status_code=302)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"OAuth callback error for {provider}: {e}")
        return RedirectResponse(
            url=f"/login?error={quote_plus('Authentication failed. Please try again.')}",
            status_code=302
        )

async def extract_user_info(client, token, provider: str) -> dict:
    """Extract user information from OAuth token based on provider"""
    
    try:
        if provider == 'google':
            # Google - try to get user info from token first, then via API call
            user_info = token.get('userinfo')
            if user_info:
                return {
                    'id': user_info.get('sub'),
                    'email': user_info.get('email'),
                    'name': user_info.get('name'),
                    'avatar_url': user_info.get('picture')
                }
            else:
                # Fallback: get user info via API call
                resp = await client.get('userinfo', token=token)
                if resp.status_code == 200:
                    user_data = resp.json()
                    return {
                        'id': user_data.get('sub'),
                        'email': user_data.get('email'),
                        'name': user_data.get('name'),
                        'avatar_url': user_data.get('picture')
                    }
                    
        elif provider == 'github':
            # Get user info from GitHub API
            resp = await client.get('user', token=token)
            if resp.status_code == 200:
                user_data = resp.json()
                
                # GitHub might not provide email in user endpoint, get it separately
                email = user_data.get('email')
                if not email:
                    email_resp = await client.get('user/emails', token=token)
                    if email_resp.status_code == 200:
                        emails = email_resp.json()
                        # Get primary email
                        for email_obj in emails:
                            if email_obj.get('primary', False):
                                email = email_obj.get('email')
                                break
                
                return {
                    'id': str(user_data.get('id')),
                    'email': email,
                    'name': user_data.get('name') or user_data.get('login'),
                    'avatar_url': user_data.get('avatar_url')
                }
                
        elif provider == 'microsoft':
            # Get user info from Microsoft Graph API
            resp = await client.get('https://graph.microsoft.com/v1.0/me', token=token)
            if resp.status_code == 200:
                user_data = resp.json()
                return {
                    'id': user_data.get('id'),
                    'email': user_data.get('userPrincipalName') or user_data.get('mail'),
                    'name': user_data.get('displayName'),
                    'avatar_url': None  # Microsoft Graph requires separate call for photo
                }
        
        logger.error(f"Failed to extract user info for provider {provider}")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting user info for {provider}: {e}")
        return None

@router.post("/logout")
async def oauth_logout(request: Request):
    """Logout user and clear session"""
    try:
        # Clear session
        request.session.clear()
        logger.info("User logged out successfully")
        return {"status": "success", "message": "Logged out successfully"}
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")

@router.get("/status")
async def oauth_status(request: Request):
    """Get current OAuth authentication status"""
    try:
        session_data = request.session
        
        if session_data.get('oauth_user'):
            oauth_user = session_data['oauth_user']
            return {
                'authenticated': True,
                'is_oauth': True,
                'provider': oauth_user.get('provider'),
                'user': {
                    'email': oauth_user.get('email'),
                    'name': oauth_user.get('name'),
                    'avatar_url': oauth_user.get('avatar_url')
                }
            }
        elif session_data.get('user'):
            return {
                'authenticated': True,
                'is_oauth': False,
                'user': {
                    'username': session_data['user']
                }
            }
        else:
            return {
                'authenticated': False,
                'is_oauth': False
            }
            
    except Exception as e:
        logger.error(f"Error getting OAuth status: {e}")
        return {
            'authenticated': False,
            'is_oauth': False,
            'error': str(e)
        }

@router.get("/config-check")
async def oauth_config_check():
    """Check OAuth configuration without exposing secrets"""
    try:
        from app.config.oauth_config import OAuthConfig
        
        report = OAuthConfig.validate_configuration()
        
        # Mask sensitive information
        config_status = {}
        
        for provider in ['google', 'github', 'microsoft']:
            client_id = os.getenv(f'{provider.upper()}_CLIENT_ID')
            client_secret = os.getenv(f'{provider.upper()}_CLIENT_SECRET')
            
            config_status[provider] = {
                'has_client_id': bool(client_id),
                'client_id_length': len(client_id) if client_id else 0,
                'client_id_preview': f"{client_id[:8]}..." if client_id and len(client_id) > 8 else None,
                'has_client_secret': bool(client_secret),
                'client_secret_length': len(client_secret) if client_secret else 0,
            }
            
            # Add Google-specific device config
            if provider == 'google':
                device_id = os.getenv('GOOGLE_DEVICE_ID')
                config_status[provider]['has_device_id'] = bool(device_id)
        
        return {
            'provider_status': config_status,
            'configured_providers': [p['name'] for p in report['configured_providers']],
            'missing_providers': [p['name'] for p in report['missing_providers']],
            'total_configured': len(report['configured_providers'])
        }
        
    except Exception as e:
        logger.error(f"Error checking OAuth config: {e}")
        return {
            'error': str(e),
            'provider_status': {},
            'configured_providers': [],
            'missing_providers': [],
            'total_configured': 0
        }