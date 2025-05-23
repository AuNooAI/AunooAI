from app.database import Database
from typing import Optional, Dict, Any
import logging
from datetime import datetime
import sqlite3

logger = logging.getLogger(__name__)

class OAuthUserManager:
    """Manager for OAuth user operations"""
    
    def __init__(self, db: Database):
        self.db = db
        self._ensure_oauth_tables()
    
    def _ensure_oauth_tables(self):
        """Ensure OAuth user tables exist"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create oauth_users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS oauth_users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email TEXT NOT NULL,
                        name TEXT,
                        provider TEXT NOT NULL,
                        provider_id TEXT,
                        avatar_url TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE,
                        UNIQUE(email, provider)
                    )
                """)
                
                # Create oauth_sessions table for tracking active sessions
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS oauth_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        session_token TEXT UNIQUE,
                        provider TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES oauth_users (id)
                    )
                """)
                
                conn.commit()
                logger.info("OAuth tables ensured successfully")
                
        except Exception as e:
            logger.error(f"Failed to create OAuth tables: {e}")
            raise
    
    def create_or_update_oauth_user(self, email: str, name: str, provider: str, 
                                   provider_id: str = None, avatar_url: str = None) -> Dict[str, Any]:
        """Create or update OAuth user in database"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if user exists
                cursor.execute(
                    "SELECT * FROM oauth_users WHERE email = ? AND provider = ?",
                    (email, provider)
                )
                user = cursor.fetchone()
                
                if user:
                    # Update existing user
                    cursor.execute("""
                        UPDATE oauth_users 
                        SET name = ?, provider_id = ?, avatar_url = ?, last_login = CURRENT_TIMESTAMP
                        WHERE email = ? AND provider = ?
                    """, (name, provider_id, avatar_url, email, provider))
                    user_id = user[0]
                    logger.info(f"Updated OAuth user: {email} ({provider})")
                else:
                    # Create new user
                    cursor.execute("""
                        INSERT INTO oauth_users (email, name, provider, provider_id, avatar_url)
                        VALUES (?, ?, ?, ?, ?)
                    """, (email, name, provider, provider_id, avatar_url))
                    user_id = cursor.lastrowid
                    logger.info(f"Created new OAuth user: {email} ({provider})")
                
                conn.commit()
                
                # Fetch the complete user record
                cursor.execute("SELECT * FROM oauth_users WHERE id = ?", (user_id,))
                user_record = cursor.fetchone()
                
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
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM oauth_users WHERE email = ? AND provider = ? AND is_active = 1",
                    (email, provider)
                )
                user = cursor.fetchone()
                
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
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM oauth_users WHERE id = ? AND is_active = 1",
                    (user_id,)
                )
                user = cursor.fetchone()
                
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
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE oauth_users SET is_active = 0 WHERE email = ? AND provider = ?",
                    (email, provider)
                )
                conn.commit()
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Failed to deactivate OAuth user {email}: {e}")
            return False
    
    def list_oauth_users(self, provider: str = None) -> list:
        """List all OAuth users, optionally filtered by provider"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                if provider:
                    cursor.execute(
                        "SELECT * FROM oauth_users WHERE provider = ? AND is_active = 1 ORDER BY created_at DESC",
                        (provider,)
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM oauth_users WHERE is_active = 1 ORDER BY created_at DESC"
                    )
                
                users = []
                for user in cursor.fetchall():
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