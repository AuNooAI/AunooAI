#!/usr/bin/env python3
"""
Setup OAuth allowlist for tenant deployment.
This script manages OAuth user allowlist for new tenant deployments.
It can add users, remove users, and configure domain restrictions.
"""

import os
import sys
import argparse
import logging
import json
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path to import app modules
script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
parent_dir = script_dir.parent
sys.path.insert(0, str(parent_dir))

from app.database import Database
from app.security.oauth_users import OAuthUserManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def get_database_connection():
    """Get database connection using app configuration."""
    db = Database()
    return db


def add_users_to_allowlist(emails: List[str], added_by: str = "deployment") -> bool:
    """Add multiple users to OAuth allowlist."""
    try:
        db = get_database_connection()
        oauth_manager = OAuthUserManager(db)
        
        success_count = 0
        for email in emails:
            try:
                if oauth_manager.add_to_allowlist(email, added_by):
                    logger.info(f"✓ Added {email} to allowlist")
                    success_count += 1
                else:
                    logger.warning(f"✗ Failed to add {email} to allowlist")
            except Exception as e:
                logger.error(f"✗ Error adding {email}: {e}")
        
        logger.info(f"Successfully added {success_count}/{len(emails)} users")
        return success_count == len(emails)
        
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False


def remove_users_from_allowlist(emails: List[str]) -> bool:
    """Remove multiple users from OAuth allowlist."""
    try:
        db = get_database_connection()
        oauth_manager = OAuthUserManager(db)
        
        success_count = 0
        for email in emails:
            try:
                if oauth_manager.remove_from_allowlist(email):
                    logger.info(f"✓ Removed {email} from allowlist")
                    success_count += 1
                else:
                    logger.warning(f"✗ {email} not found in allowlist")
            except Exception as e:
                logger.error(f"✗ Error removing {email}: {e}")
        
        logger.info(f"Successfully removed {success_count}/{len(emails)} users")
        return success_count == len(emails)
        
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False


def list_allowlist_users() -> List[Dict[str, Any]]:
    """List all users in OAuth allowlist."""
    try:
        db = get_database_connection()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT email, added_by, added_at, is_active 
                FROM oauth_allowlist 
                ORDER BY added_at DESC
            """)
            
            users = []
            for row in cursor.fetchall():
                users.append({
                    'email': row[0],
                    'added_by': row[1],
                    'added_at': row[2],
                    'is_active': bool(row[3])
                })
            
            return users
            
    except Exception as e:
        logger.error(f"Failed to list allowlist users: {e}")
        return []


def setup_from_config(config_file: str) -> bool:
    """Setup allowlist from JSON configuration file."""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Add domain restrictions to environment
        if 'allowed_domains' in config:
            domains = ','.join(config['allowed_domains'])
            os.environ['ALLOWED_EMAIL_DOMAINS'] = domains
            logger.info(f"Set domain restrictions: {domains}")
        
        # Add users to allowlist
        if 'allowlist_users' in config:
            emails = config['allowlist_users']
            added_by = config.get('added_by', 'deployment')
            return add_users_to_allowlist(emails, added_by)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to setup from config: {e}")
        return False


def create_sample_config(output_file: str):
    """Create a sample configuration file."""
    sample_config = {
        "allowed_domains": [
            "yourcompany.com",
            "trusted-partner.org"
        ],
        "allowlist_users": [
            "admin@yourcompany.com",
            "support@yourcompany.com",
            "deploy@yourcompany.com"
        ],
        "added_by": "deployment"
    }
    
    with open(output_file, 'w') as f:
        json.dump(sample_config, f, indent=2)
    
    logger.info(f"Created sample config file: {output_file}")


def get_oauth_status():
    """Get and display OAuth security status."""
    try:
        db = get_database_connection()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Count allowlist entries
            cursor.execute("SELECT COUNT(*) FROM oauth_allowlist WHERE is_active = 1")
            allowlist_count = cursor.fetchone()[0]
            
            # Count OAuth users
            cursor.execute("SELECT COUNT(*) FROM oauth_users WHERE is_active = 1")
            oauth_users_count = cursor.fetchone()[0]
            
            # Get domain restrictions
            domain_restrictions = os.getenv('ALLOWED_EMAIL_DOMAINS', '').split(',')
            domain_restrictions = [d.strip() for d in domain_restrictions if d.strip()]
        
        logger.info("=== OAuth Security Status ===")
        logger.info(f"Allowlist enabled: {'Yes' if allowlist_count > 0 else 'No'}")
        logger.info(f"Allowlist users: {allowlist_count}")
        logger.info(f"Domain restrictions: {domain_restrictions if domain_restrictions else 'None'}")
        logger.info(f"Total OAuth users: {oauth_users_count}")
        
        security_level = "HIGH" if allowlist_count > 0 or domain_restrictions else "OPEN"
        logger.info(f"Security level: {security_level}")
        
    except Exception as e:
        logger.error(f"Failed to get OAuth status: {e}")


def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(
        description="Manage OAuth allowlist for tenant deployment"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Add users command
    add_parser = subparsers.add_parser('add', help='Add users to allowlist')
    add_parser.add_argument('emails', nargs='+', help='Email addresses to add')
    add_parser.add_argument('--added-by', default='deployment', 
                           help='Who is adding these users')
    
    # Remove users command
    remove_parser = subparsers.add_parser('remove', help='Remove users from allowlist')
    remove_parser.add_argument('emails', nargs='+', help='Email addresses to remove')
    
    # List users command
    list_parser = subparsers.add_parser('list', help='List allowlist users')
    
    # Setup from config command
    config_parser = subparsers.add_parser('config', help='Setup from JSON config file')
    config_parser.add_argument('file', help='JSON configuration file')
    
    # Create sample config command
    sample_parser = subparsers.add_parser('sample', help='Create sample config file')
    sample_parser.add_argument('--output', default='oauth_config.json', 
                              help='Output file name')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show OAuth security status')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'add':
        success = add_users_to_allowlist(args.emails, args.added_by)
        sys.exit(0 if success else 1)
        
    elif args.command == 'remove':
        success = remove_users_from_allowlist(args.emails)
        sys.exit(0 if success else 1)
        
    elif args.command == 'list':
        users = list_allowlist_users()
        if users:
            logger.info("=== OAuth Allowlist Users ===")
            for user in users:
                status = "✓" if user['is_active'] else "✗"
                logger.info(f"{status} {user['email']} (added by: {user['added_by']}, "
                           f"date: {user['added_at']})")
        else:
            logger.info("No users in allowlist")
    
    elif args.command == 'config':
        success = setup_from_config(args.file)
        sys.exit(0 if success else 1)
        
    elif args.command == 'sample':
        create_sample_config(args.output)
        
    elif args.command == 'status':
        get_oauth_status()


if __name__ == "__main__":
    main() 