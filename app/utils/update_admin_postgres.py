import psycopg2
import os
import logging
from passlib.context import CryptContext

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Create password context - matches the one used in the application
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__default_rounds=12,  # Adjust rounds as needed
    bcrypt__ident="2b"         # Explicitly set bcrypt identifier
)

def update_admin_password(db_host: str, db_name: str, db_user: str, db_password: str, admin_password: str):
    """
    Update the admin user's password in the PostgreSQL database.

    Args:
        db_host: PostgreSQL host (e.g., 'localhost')
        db_name: Database name
        db_user: Database user
        db_password: Database password
        admin_password: New password for the admin user
    """
    # Hash the password
    hashed_password = pwd_context.hash(admin_password)

    logger.info(f"Connecting to PostgreSQL database: {db_name}@{db_host}")

    # Connect to database
    conn = psycopg2.connect(
        host=db_host,
        database=db_name,
        user=db_user,
        password=db_password
    )
    cursor = conn.cursor()

    try:
        # Check if admin user exists
        cursor.execute("SELECT username FROM users WHERE username = 'admin'")
        existing_user = cursor.fetchone()

        if existing_user:
            # Update existing admin user
            cursor.execute(
                """UPDATE users
                   SET password_hash = %s,
                       force_password_change = TRUE,
                       completed_onboarding = FALSE,
                       role = 'admin'
                   WHERE username = 'admin'""",
                (hashed_password,)
            )
            logger.info("Admin user password updated successfully")
        else:
            # Create new admin user
            cursor.execute(
                """INSERT INTO users
                   (username, password_hash, force_password_change, completed_onboarding, email, role, is_active)
                   VALUES ('admin', %s, TRUE, FALSE, 'admin@aunoo.ai', 'admin', TRUE)""",
                (hashed_password,)
            )
            logger.info("Admin user created successfully")

        conn.commit()
        logger.info("Changes committed. Admin password is now set and force_password_change is true")

        # Verify the update
        cursor.execute("SELECT username, force_password_change, completed_onboarding FROM users WHERE username = 'admin'")
        result = cursor.fetchone()
        if result:
            logger.info(f"Verification - Username: {result[0]}, Force Password Change: {result[1]}, Completed Onboarding: {result[2]}")

    except Exception as e:
        logger.error(f"Error updating password: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    import argparse

    # Get defaults from environment
    default_host = os.environ.get("DB_HOST", "localhost")
    default_name = os.environ.get("DB_NAME", "multi")
    default_user = os.environ.get("DB_USER", "multi_user")
    default_password = os.environ.get("DB_PASSWORD", "")  # Must be provided
    default_admin_password = "lC6edF7!3P5Nl#bx"  # From DEPLOYMENT_INFO.txt

    parser = argparse.ArgumentParser(description='Update admin password in PostgreSQL database')
    parser.add_argument('--host', default=default_host, help='PostgreSQL host')
    parser.add_argument('--database', default=default_name, help='Database name')
    parser.add_argument('--user', default=default_user, help='Database user')
    parser.add_argument('--db-password', default=default_password, help='Database password')
    parser.add_argument('--admin-password', default=default_admin_password, help='New password for the admin user')
    args = parser.parse_args()

    print("=" * 60)
    print("PostgreSQL Admin Password Update")
    print("=" * 60)
    print(f"Host:     {args.host}")
    print(f"Database: {args.database}")
    print(f"DB User:  {args.user}")
    print(f"Admin Password will be set to: {args.admin_password}")
    print("=" * 60)

    update_admin_password(
        args.host,
        args.database,
        args.user,
        args.db_password,
        args.admin_password
    )

    print("=" * 60)
    print("✅ Admin password updated successfully!")
    print("You can now login with:")
    print("  Username: admin")
    print(f"  Password: {args.admin_password}")
    print("=" * 60)
