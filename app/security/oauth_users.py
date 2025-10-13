from app.database import Database
from typing import Optional, Dict, Any
import logging
from datetime import datetime
import sqlite3
import os

logger = logging.getLogger(__name__)

# Add allowed domains configuration
ALLOWED_EMAIL_DOMAINS = os.getenv('ALLOWED_EMAIL_DOMAINS', '').split(',') if os.getenv('ALLOWED_EMAIL_DOMAINS') else []

def is_email_domain_allowed(email: str) -> bool:
    """Check if email domain is in allowed domains list"""
    if not ALLOWED_EMAIL_DOMAINS or not ALLOWED_EMAIL_DOMAINS[0]:
        return True  # No restrictions if not configured
    
    domain = email.split('@')[-1].lower()
    return domain in [d.strip().lower() for d in ALLOWED_EMAIL_DOMAINS if d.strip()]

class OAuthUserManager:
    """Manager for OAuth user operations"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create_or_update_oauth_user(self, email: str, name: str, provider: str, 
                                   provider_id: str = None, avatar_url: str = None) -> Dict[str, Any]:
        """Create or update OAuth user in database"""
        
        # Check if email domain is allowed
        if not is_email_domain_allowed(email):
            logger.warning(f"OAuth login denied for {email} - domain not in allowlist")
            raise Exception(f"Access denied: {email.split('@')[-1]} domain is not authorized")
        
        # Check if user is in allowlist (if allowlist has entries)
        allowlist_count = self.db.facade.count_oauth_allowlist_active_users()

        if allowlist_count > 0 and not self.is_user_allowed(email):
            logger.warning(f"OAuth login denied for {email} - not in user allowlist")
            raise Exception(f"Access denied: {email} is not authorized to access this application")

        try:
            # Check if user exists
            user = self.db.facade.get_oauth_allowlist_user_by_email_and_provider(email, provider)

            if user:
                # Update existing user
                self.db.facade.update_oauth_allowlist_user((name, provider_id, avatar_url, email, provider))
                user_id = user[0]
                logger.info(f"Updated OAuth user: {email} ({provider})")
            else:
                # Create new user
                user_id = self.db.facade.create_oauth_allowlist_user((email, name, provider, provider_id, avatar_url))
                logger.info(f"Created new OAuth user: {email} ({provider})")

            # Facade methods handle their own commits - no conn.commit() needed here
            # Removed: conn.commit() - fixes Week 1 migration issue (line 57)

            # Fetch the complete user record
            user_record = self.db.facade.get_oauth_allowlist_user_by_id(user_id)

            if user_record:
                return {
                    'id': user_record[0],
                    'email': user_record[1],
                    'name': user_record[2],
                    'provider': user_record[3],
                    'provider_id': user_record[4],
                    'avatar_url': user_record[5],
                    'created_at': user_record[6],
                    'last_login': user_record[7],
                    'is_active': user_record[8]
                }
            else:
                raise Exception("Failed to retrieve user record after creation/update")
                
        except Exception as e:
            logger.error(f"Failed to create/update OAuth user {email}: {e}")
            raise
    
    def get_oauth_user(self, email: str, provider: str) -> Optional[Dict[str, Any]]:
        """Get OAuth user by email and provider"""
        try:
            user = self.db.facade.get_active_oauth_allowlist_user_by_email_and_provider(email, provider)

            if user:
                return {
                    'id': user[0],
                    'email': user[1],
                    'name': user[2],
                    'provider': user[3],
                    'provider_id': user[4],
                    'avatar_url': user[5],
                    'created_at': user[6],
                    'last_login': user[7],
                    'is_active': user[8]
                }
            return None
                
        except Exception as e:
            logger.error(f"Failed to get OAuth user {email}: {e}")
            return None
    
    def get_oauth_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get OAuth user by ID"""
        try:
            user = self.db.facade.get_active_oauth_allowlist_user_by_id(user_id)

            if user:
                return {
                    'id': user[0],
                    'email': user[1],
                    'name': user[2],
                    'provider': user[3],
                    'provider_id': user[4],
                    'avatar_url': user[5],
                    'created_at': user[6],
                    'last_login': user[7],
                    'is_active': user[8]
                }
            return None
                
        except Exception as e:
            logger.error(f"Failed to get OAuth user by ID {user_id}: {e}")
            return None
    
    def deactivate_user(self, email: str, provider: str) -> bool:
        """Deactivate OAuth user"""
        try:
            return self.db.facade.deactivate_user(email, provider) > 0

        except Exception as e:
            logger.error(f"Failed to deactivate OAuth user {email}: {e}")
            return False
    
    def list_oauth_users(self, provider: str = None) -> list:
        """List all OAuth users, optionally filtered by provider"""
        try:
            if provider:
                rows = self.db.facade.get_oauth_active_users_by_provider(provider)
            else:
                rows = self.db.facade.get_oauth_active_users()

            users = []
            for user in rows:
                users.append({
                    'id': user[0],
                    'email': user[1],
                    'name': user[2],
                    'provider': user[3],
                    'provider_id': user[4],
                    'avatar_url': user[5],
                    'created_at': user[6],
                    'last_login': user[7],
                    'is_active': user[8]
                })

            return users
                
        except Exception as e:
            logger.error(f"Failed to list OAuth users: {e}")
            return []

    def is_user_allowed(self, email: str) -> bool:
        """Check if user email is in the allowlist"""
        try:
            return self.db.facade.is_oauth_user_allowed(email)
        except Exception as e:
            logger.error(f"Failed to check allowlist for {email}: {e}")
            return False
    
    def add_to_allowlist(self, email: str, added_by: str = None) -> bool:
        """Add email to OAuth allowlist"""
        try:
            self.db.facade.add_oauth_user_to_allowlist(email.lower(), added_by)
            return True
        except Exception as e:
            logger.error(f"Failed to add {email} to allowlist: {e}")
            return False
    
    def remove_from_allowlist(self, email: str) -> bool:
        """Remove email from OAuth allowlist"""
        try:
            remove_count = self.db.facade.remove_oauth_user_from_allowlist(email.lower())
            logger.info(f"Removed {email} from OAuth allowlist")
            return remove_count > 0
        except Exception as e:
            logger.error(f"Failed to remove {email} from allowlist: {e}")
            return False

def get_oauth_user_by_session(session_data: dict) -> Optional[dict]:
    """Get OAuth user details from session data"""
    if not session_data:
        return None
        
    if session_data.get('provider') and session_data.get('oauth_user'):
        oauth_user = session_data['oauth_user']
        return {
            'id': oauth_user.get('id'),
            'email': oauth_user.get('email'),
            'name': oauth_user.get('name'),
            'provider': oauth_user.get('provider'),
            'avatar_url': oauth_user.get('avatar_url'),
            'is_oauth': True
        }
    
    # Check for traditional session user
    if session_data.get('user'):
        return {
            'username': session_data['user'],
            'is_oauth': False
        }
    
    return None

def create_oauth_session_data(oauth_user: Dict[str, Any]) -> Dict[str, Any]:
    """Create session data for OAuth user"""
    return {
        'user': oauth_user['email'],  # Keep compatibility with existing session verification
        'oauth_user': oauth_user,
        'provider': oauth_user['provider'],
        'is_oauth': True,
        'login_time': datetime.now().isoformat()
    }