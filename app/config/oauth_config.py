"""
OAuth Configuration for AunooAI

This module provides configuration management for OAuth providers.
Environment variables should be set for each provider you want to enable.
"""

import os
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

class OAuthConfig:
    """OAuth configuration manager"""
    
    # OAuth provider configurations
    PROVIDER_CONFIGS = {
        'google': {
            'name': 'Google',
            'display_name': 'Google',
            'client_id_env': 'GOOGLE_CLIENT_ID',
            'client_secret_env': 'GOOGLE_CLIENT_SECRET',
            'scopes': ['openid', 'email', 'profile'],
            'server_metadata_url': 'https://accounts.google.com/.well-known/openid-configuration',
            'icon': 'fab fa-google',
            'color': '#db4437',
            'button_class': 'btn-google'
        },
        'github': {
            'name': 'GitHub',
            'display_name': 'GitHub',
            'client_id_env': 'GITHUB_CLIENT_ID',
            'client_secret_env': 'GITHUB_CLIENT_SECRET',
            'scopes': ['user:email'],
            'access_token_url': 'https://github.com/login/oauth/access_token',
            'authorize_url': 'https://github.com/login/oauth/authorize',
            'api_base_url': 'https://api.github.com/',
            'icon': 'fab fa-github',
            'color': '#333',
            'button_class': 'btn-github'
        },
        'microsoft': {
            'name': 'Microsoft',
            'display_name': 'Microsoft',
            'client_id_env': 'MICROSOFT_CLIENT_ID',
            'client_secret_env': 'MICROSOFT_CLIENT_SECRET',
            'scopes': ['openid', 'email', 'profile'],
            'server_metadata_url': 'https://login.microsoftonline.com/common/v2.0/.well-known/openid_configuration',
            'icon': 'fab fa-microsoft',
            'color': '#00a1f1',
            'button_class': 'btn-microsoft'
        }
    }
    
    @classmethod
    def get_configured_providers(cls) -> List[str]:
        """Get list of providers that have required environment variables set"""
        configured = []
        
        for provider_name, config in cls.PROVIDER_CONFIGS.items():
            client_id = os.getenv(config['client_id_env'])
            client_secret = os.getenv(config['client_secret_env'])
            
            if client_id and client_secret:
                configured.append(provider_name)
        
        return configured
    
    @classmethod
    def is_provider_configured(cls, provider: str) -> bool:
        """Check if a specific provider is configured"""
        if provider not in cls.PROVIDER_CONFIGS:
            return False
        
        config = cls.PROVIDER_CONFIGS[provider]
        client_id = os.getenv(config['client_id_env'])
        client_secret = os.getenv(config['client_secret_env'])
        
        return bool(client_id and client_secret)
    
    @classmethod
    def get_provider_config(cls, provider: str) -> Optional[Dict]:
        """Get configuration for a specific provider"""
        if provider not in cls.PROVIDER_CONFIGS:
            return None
        
        config = cls.PROVIDER_CONFIGS[provider].copy()
        
        # Add actual environment values
        config['client_id'] = os.getenv(config['client_id_env'])
        config['client_secret'] = os.getenv(config['client_secret_env'])
        
        return config
    
    @classmethod
    def get_frontend_config(cls, provider: str) -> Optional[Dict]:
        """Get safe configuration for frontend (no secrets)"""
        if provider not in cls.PROVIDER_CONFIGS:
            return None
        
        config = cls.PROVIDER_CONFIGS[provider]
        
        return {
            'name': provider,
            'display_name': config['display_name'],
            'icon': config['icon'],
            'color': config['color'],
            'button_class': config['button_class']
        }
    
    @classmethod
    def validate_configuration(cls) -> Dict[str, Dict]:
        """Validate OAuth configuration and return status report"""
        report = {
            'configured_providers': [],
            'missing_providers': [],
            'errors': []
        }
        
        for provider_name, config in cls.PROVIDER_CONFIGS.items():
            client_id = os.getenv(config['client_id_env'])
            client_secret = os.getenv(config['client_secret_env'])
            
            if client_id and client_secret:
                report['configured_providers'].append({
                    'name': provider_name,
                    'display_name': config['display_name'],
                    'has_client_id': bool(client_id),
                    'has_client_secret': bool(client_secret)
                })
            else:
                missing_vars = []
                if not client_id:
                    missing_vars.append(config['client_id_env'])
                if not client_secret:
                    missing_vars.append(config['client_secret_env'])
                
                report['missing_providers'].append({
                    'name': provider_name,
                    'display_name': config['display_name'],
                    'missing_vars': missing_vars
                })
        
        return report

# Application-wide OAuth settings
OAUTH_SETTINGS = {
    'redirect_after_login': os.getenv('OAUTH_REDIRECT_AFTER_LOGIN', '/dashboard'),
    'session_timeout': int(os.getenv('OAUTH_SESSION_TIMEOUT', '86400')),  # 24 hours
    'require_email_verification': os.getenv('OAUTH_REQUIRE_EMAIL_VERIFICATION', 'false').lower() == 'true',
    'allow_new_user_registration': os.getenv('OAUTH_ALLOW_NEW_USER_REGISTRATION', 'true').lower() == 'true',
    'debug_mode': os.getenv('OAUTH_DEBUG_MODE', 'false').lower() == 'true'
}

def get_oauth_settings() -> Dict:
    """Get OAuth application settings"""
    return OAUTH_SETTINGS.copy()

def get_required_env_vars() -> Dict[str, List[str]]:
    """Get list of required environment variables for each provider"""
    required_vars = {}
    
    for provider_name, config in OAuthConfig.PROVIDER_CONFIGS.items():
        required_vars[provider_name] = [
            config['client_id_env'],
            config['client_secret_env']
        ]
    
    return required_vars