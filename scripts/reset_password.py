#!/usr/bin/env python3
"""
Password Reset Script
---------------------
Reset a user's password when they've forgotten it.

Usage:
    python scripts/reset_password.py --username <username>
    python scripts/reset_password.py -u <username>

Examples:
    python scripts/reset_password.py --username admin
    python scripts/reset_password.py -u john.doe

Password Requirements:
    - Minimum 8 characters
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one number (0-9)
    - At least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)
"""

import os
import sys
import re
import getpass
import argparse

# Add parent directory to path so we can import app modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from passlib.context import CryptContext

# Try to load .env file from project root
try:
    from dotenv import load_dotenv
    env_path = os.path.join(PROJECT_ROOT, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, use environment variables only

# Password hashing context (same as used by the app)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_db_config() -> dict:
    """Get database configuration from environment or prompt user."""
    config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5433"),
        "database": os.getenv("DB_NAME") or os.getenv("POSTGRES_DB", "aunoo_db"),
        "user": os.getenv("DB_USER") or os.getenv("POSTGRES_USER", "aunoo_user"),
        "password": os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD", ""),
    }
    return config


DB_CONFIG = get_db_config()

# Password requirements
MIN_LENGTH = 8
SPECIAL_CHARS = r"!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`"


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def validate_password(password: str) -> dict:
    """
    Validate password against security requirements.
    
    Returns a dict with:
        - valid: True if all requirements met
        - errors: List of validation errors
    """
    errors = []
    
    # Check minimum length
    if len(password) < MIN_LENGTH:
        errors.append(f"❌ Password must be at least {MIN_LENGTH} characters (currently {len(password)})")
    
    # Check for uppercase letter
    if not re.search(r"[A-Z]", password):
        errors.append("❌ Password must contain at least one UPPERCASE letter (A-Z)")
    
    # Check for lowercase letter
    if not re.search(r"[a-z]", password):
        errors.append("❌ Password must contain at least one lowercase letter (a-z)")
    
    # Check for number
    if not re.search(r"[0-9]", password):
        errors.append("❌ Password must contain at least one number (0-9)")
    
    # Check for special character
    if not re.search(rf"[{re.escape(SPECIAL_CHARS)}]", password):
        errors.append(f"❌ Password must contain at least one special character ({SPECIAL_CHARS[:15]}...)")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def get_valid_password() -> str:
    """
    Prompt user for password and validate it.
    Keep asking until a valid password is provided.
    """
    print("\n" + "=" * 60)
    print("  PASSWORD REQUIREMENTS")
    print("=" * 60)
    print(f"  • Minimum {MIN_LENGTH} characters")
    print("  • At least one UPPERCASE letter (A-Z)")
    print("  • At least one lowercase letter (a-z)")
    print("  • At least one number (0-9)")
    print("  • At least one special character (!@#$%^&*...)")
    print("=" * 60)
    
    while True:
        print()
        # Use getpass to hide password input
        try:
            password = getpass.getpass("🔐 Enter new password: ")
        except KeyboardInterrupt:
            print("\n\n⚠️  Operation cancelled by user.")
            sys.exit(0)
        
        if not password:
            print("⚠️  Password cannot be empty. Please try again.")
            continue
        
        # Validate password
        result = validate_password(password)
        
        if result["valid"]:
            # Ask for confirmation
            try:
                confirm = getpass.getpass("🔐 Confirm new password: ")
            except KeyboardInterrupt:
                print("\n\n⚠️  Operation cancelled by user.")
                sys.exit(0)
            
            if password != confirm:
                print("\n❌ Passwords do not match. Please try again.")
                continue
            
            print("\n✅ Password meets all requirements!")
            return password
        else:
            print("\n⚠️  Password does not meet requirements:\n")
            for error in result["errors"]:
                print(f"   {error}")
            print("\nPlease try again with a stronger password.")


def prompt_db_credentials() -> dict:
    """Prompt user for database credentials."""
    print("\n" + "=" * 60)
    print("  DATABASE CONNECTION SETTINGS")
    print("=" * 60)
    print("\nCurrent settings (press Enter to keep):\n")
    
    host = input(f"  Host [{DB_CONFIG['host']}]: ").strip() or DB_CONFIG['host']
    port = input(f"  Port [{DB_CONFIG['port']}]: ").strip() or DB_CONFIG['port']
    database = input(f"  Database [{DB_CONFIG['database']}]: ").strip() or DB_CONFIG['database']
    user = input(f"  Username [{DB_CONFIG['user']}]: ").strip() or DB_CONFIG['user']
    password = getpass.getpass(f"  Password: ") or DB_CONFIG['password']
    
    return {
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
    }


def reset_user_password(username: str, new_password: str, db_config: dict = None):
    """Reset the password for a specified user in the database."""
    import psycopg2

    if db_config is None:
        db_config = DB_CONFIG

    # Hash the new password
    password_hash = get_password_hash(new_password)

    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host=db_config["host"],
            port=db_config["port"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute("SELECT username, email, is_active FROM users WHERE username = %s", (username,))
        existing_user = cursor.fetchone()

        if existing_user:
            # Update existing user
            cursor.execute(
                """
                UPDATE users
                SET password_hash = %s,
                    force_password_change = FALSE,
                    is_active = TRUE
                WHERE username = %s
                """,
                (password_hash, username),
            )
            print(f"✅ Updated password for user '{username}'")
        else:
            print(f"\n❌ User '{username}' not found in the database.")
            print("   This script can only reset passwords for existing users.")
            cursor.close()
            conn.close()
            return False

        # Commit the changes
        conn.commit()

        cursor.close()
        conn.close()

        return True

    except psycopg2.OperationalError as e:
        print(f"\n❌ Database connection failed.")
        print("\n💡 Tips:")
        print("   1. Make sure PostgreSQL is running")
        print("   2. Check if the database credentials are correct")
        print("   3. If using Docker: docker compose up -d postgres")
        return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Reset a user's password in AunooAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/reset_password.py --username admin
    python scripts/reset_password.py -u john.doe
    
Password Requirements:
    - Minimum 8 characters
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one number (0-9)
    - At least one special character (!@#$%^&*...)
        """
    )
    parser.add_argument(
        "-u", "--username",
        type=str,
        required=True,
        help="Username of the account to reset password for"
    )
    return parser.parse_args()


def main():
    """Main function."""
    # Parse command line arguments
    args = parse_arguments()
    username = args.username
    
    print("\n" + "=" * 60)
    print("  🔑 AUNOOAI PASSWORD RESET")
    print("=" * 60)
    print(f"\nResetting password for user: '{username}'")
    
    # Get and validate password
    new_password = get_valid_password()
    
    # Reset password in database
    print("\n📡 Updating database...")
    
    # Try with current config first
    result = reset_user_password(username, new_password)
    
    # If failed, offer to enter credentials manually
    if not result:
        retry = input("\n🔄 Enter database credentials manually? (y/n): ").strip().lower()
        if retry == 'y':
            custom_config = prompt_db_credentials()
            print("\n📡 Retrying...")
            result = reset_user_password(username, new_password, custom_config)
    
    if result:
        print("\n" + "=" * 60)
        print("  🎉 PASSWORD RESET SUCCESSFUL!")
        print("=" * 60)
    else:
        print("\n❌ Password reset failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user.")
        sys.exit(0)

