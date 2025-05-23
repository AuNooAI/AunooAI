from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.requests import Request
import os
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# Create config from environment
config = Config()

# Initialize OAuth
oauth = OAuth()

def setup_oauth_providers():
    """Setup OAuth providers based on available environment variables"""
    providers_configured = []
    
    # Google OAuth setup
    google_client_id = os.getenv('GOOGLE_CLIENT_ID')
    google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    
    if google_client_id and google_client_secret:
        try:
            client_kwargs = {
                'scope': 'openid email profile'
            }
            
            oauth.register(
                name='google',
                client_id=google_client_id,
                client_secret=google_client_secret,
                server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
                client_kwargs=client_kwargs
            )
            providers_configured.append('google')
            logger.info("Google OAuth provider configured successfully")
        except Exception as e:
            logger.error(f"Failed to configure Google OAuth: {e}")
    else:
        logger.warning("Google OAuth not configured - missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET")
    
    # GitHub OAuth setup
    github_client_id = os.getenv('GITHUB_CLIENT_ID')
    github_client_secret = os.getenv('GITHUB_CLIENT_SECRET')
    
    if github_client_id and github_client_secret:
        try:
            oauth.register(
                name='github',
                client_id=github_client_id,
                client_secret=github_client_secret,
                access_token_url='https://github.com/login/oauth/access_token',
                authorize_url='https://github.com/login/oauth/authorize',
                api_base_url='https://api.github.com/',
                client_kwargs={
                    'scope': 'user:email'
                }
            )
            providers_configured.append('github')
            logger.info("GitHub OAuth provider configured successfully")
        except Exception as e:
            logger.error(f"Failed to configure GitHub OAuth: {e}")
    else:
        logger.warning("GitHub OAuth not configured - missing GITHUB_CLIENT_ID or GITHUB_CLIENT_SECRET")
    
    # Microsoft OAuth setup (optional)
    microsoft_client_id = os.getenv('MICROSOFT_CLIENT_ID')
    microsoft_client_secret = os.getenv('MICROSOFT_CLIENT_SECRET')
    
    if microsoft_client_id and microsoft_client_secret:
        try:
            oauth.register(
                name='microsoft',
                client_id=microsoft_client_id,
                client_secret=microsoft_client_secret,
                server_metadata_url='https://login.microsoftonline.com/common/v2.0/.well-known/openid_configuration',
                client_kwargs={
                    'scope': 'openid email profile'
                }
            )
            providers_configured.append('microsoft')
            logger.info("Microsoft OAuth provider configured successfully")
        except Exception as e:
            logger.error(f"Failed to configure Microsoft OAuth: {e}")
    
    logger.info(f"OAuth providers configured: {providers_configured}")
    return providers_configured

# OAuth provider configurations for frontend display
OAUTH_PROVIDERS = {
    'google': {
        'name': 'Google',
        'icon': 'fab fa-google',
        'color': '#db4437',
        'button_class': 'btn-google'
    },
    'github': {
        'name': 'GitHub', 
        'icon': 'fab fa-github',
        'color': '#333',
        'button_class': 'btn-github'
    },
    'microsoft': {
        'name': 'Microsoft',
        'icon': 'fab fa-microsoft',
        'color': '#00a1f1',
        'button_class': 'btn-microsoft'
    }
}

def get_configured_providers():
    """Get list of OAuth providers that are properly configured"""
    configured = []
    
    if os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET'):
        configured.append('google')
    
    if os.getenv('GITHUB_CLIENT_ID') and os.getenv('GITHUB_CLIENT_SECRET'):
        configured.append('github')
        
    if os.getenv('MICROSOFT_CLIENT_ID') and os.getenv('MICROSOFT_CLIENT_SECRET'):
        configured.append('microsoft')
    
    return configured

def get_oauth_redirect_uri(request: Request, provider: str) -> str:
    """Generate OAuth redirect URI for the given provider"""
    base_url = str(request.base_url).rstrip('/')
    return f"{base_url}/auth/callback/{provider}"

def is_provider_configured(provider: str) -> bool:
    """Check if a specific OAuth provider is configured"""
    return provider in get_configured_providers()

# Initialize providers when module is imported
configured_providers = setup_oauth_providers()