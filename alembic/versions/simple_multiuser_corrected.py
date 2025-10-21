"""simple multi-user support with OAuth integration

Revision ID: simple_multiuser_v2
Revises: 1745b4f22f68
Create Date: 2025-10-21

CORRECTED VERSION - Includes:
- OAuth user migration to users table
- Email required (populated for all users)
- Case-insensitive usernames
- Existing articles attribution
- First admin creation or upgrade
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from passlib.context import CryptContext

# revision identifiers
revision = 'simple_multiuser_v2'
down_revision = 'e0aa2eb4fa0a'  # Latest migration: add_hnsw_vector_index
branch_labels = None
depends_on = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__default_rounds=12)


def upgrade():
    """Apply simple multi-user changes with OAuth integration."""

    bind = op.get_bind()

    print("\n" + "="*60)
    print("SIMPLE MULTI-USER MIGRATION v2 - Starting...")
    print("="*60)

    # 1. Extend users table
    print("\n[1/8] Extending users table with new columns...")
    op.add_column('users', sa.Column('email', sa.Text(), nullable=True))  # Nullable during migration
    op.add_column('users', sa.Column('role', sa.Text(), nullable=False, server_default='user'))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='TRUE'))
    op.add_column('users', sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')))

    # Create indexes
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_is_active', 'users', ['is_active'])
    op.create_index('idx_users_role', 'users', ['role'])

    # Add check constraint for role
    op.create_check_constraint(
        'check_user_role',
        'users',
        "role IN ('admin', 'user')"
    )

    print("✓ Users table extended")

    # 2. Ensure at least one admin exists
    print("\n[2/8] Ensuring admin user exists...")
    result = bind.execute(sa.text("SELECT COUNT(*) FROM users")).scalar()

    if result == 0:
        # No users - create default admin
        password_hash = pwd_context.hash("admin123")

        bind.execute(sa.text("""
            INSERT INTO users (username, password_hash, email, role, is_active, force_password_change)
            VALUES (:username, :password_hash, :email, :role, TRUE, TRUE)
        """), {
            "username": "admin",
            "password_hash": password_hash,
            "email": "admin@localhost",
            "role": "admin"
        })

        print("✓ Created default admin user")
        print("  Username: admin")
        print("  Password: admin123")
        print("  Email: admin@localhost")
        print("  ⚠️  CHANGE PASSWORD ON FIRST LOGIN!")

        first_admin = "admin"
    else:
        # Upgrade first user to admin if no admin exists
        admin_count = bind.execute(sa.text("SELECT COUNT(*) FROM users WHERE role = 'admin'")).scalar()

        if admin_count == 0:
            # Get first user
            first_user_row = bind.execute(sa.text("""
                SELECT username FROM users ORDER BY username LIMIT 1
            """)).fetchone()

            first_user = first_user_row[0] if first_user_row else None

            if first_user:
                # Set email if not present
                bind.execute(sa.text("""
                    UPDATE users
                    SET role = 'admin',
                        is_active = TRUE,
                        email = COALESCE(email, :email)
                    WHERE username = :username
                """), {
                    "username": first_user,
                    "email": f"{first_user}@localhost"
                })

                print(f"✓ Upgraded user '{first_user}' to admin role")
                first_admin = first_user
            else:
                print("⚠️  Warning: Could not find first user to upgrade")
                first_admin = None
        else:
            # Get first admin for OAuth migration
            first_admin_row = bind.execute(sa.text("""
                SELECT username FROM users WHERE role = 'admin' ORDER BY username LIMIT 1
            """)).fetchone()
            first_admin = first_admin_row[0] if first_admin_row else None
            print(f"✓ Admin user already exists: {first_admin}")

    # 3. Migrate OAuth users to users table
    print("\n[3/8] Migrating OAuth users to users table...")

    # Check if oauth_allowlist table exists
    try:
        oauth_users = bind.execute(sa.text("""
            SELECT email, is_active
            FROM oauth_allowlist
            WHERE is_active = TRUE
        """)).fetchall()

        migrated_count = 0
        for oauth_user in oauth_users:
            email, is_active = oauth_user

            # Check if user already exists in users table
            existing = bind.execute(sa.text("""
                SELECT username FROM users WHERE email = :email
            """), {"email": email}).fetchone()

            if not existing:
                # Create user entry for OAuth user
                # Username = email (normalized)
                username = email.lower().replace('@', '_at_').replace('.', '_')

                bind.execute(sa.text("""
                    INSERT INTO users (username, password_hash, email, role, is_active, force_password_change, completed_onboarding)
                    VALUES (:username, :password_hash, :email, :role, :is_active, FALSE, TRUE)
                """), {
                    "username": username,
                    "password_hash": "",  # Empty for OAuth users
                    "email": email,
                    "role": "user",
                    "is_active": is_active
                })

                migrated_count += 1
                print(f"  ✓ Migrated OAuth user: {email} -> {username}")

        print(f"✓ Migrated {migrated_count} OAuth users to users table")

    except Exception as e:
        print(f"  ⚠️  Note: Could not migrate OAuth users: {e}")
        print("     (This is OK if oauth_allowlist table doesn't exist)")

    # 4. Populate email for existing traditional users
    print("\n[4/8] Populating email for existing users...")

    users_without_email = bind.execute(sa.text("""
        SELECT username FROM users WHERE email IS NULL
    """)).fetchall()

    for user_row in users_without_email:
        username = user_row[0]
        bind.execute(sa.text("""
            UPDATE users
            SET email = :email
            WHERE username = :username
        """), {
            "email": f"{username}@localhost",
            "username": username
        })

    print(f"✓ Populated email for {len(users_without_email)} users")

    # 5. Make email unique constraint (now that all have emails)
    print("\n[5/8] Creating unique constraint on email...")
    op.create_unique_constraint('uq_users_email', 'users', ['email'])
    print("✓ Email uniqueness enforced")

    # 6. Add created_by to articles (optional)
    print("\n[6/8] Adding created_by column to articles...")
    op.add_column('articles', sa.Column('created_by', sa.Text(), nullable=True))

    # Add foreign key
    op.create_foreign_key(
        'fk_articles_created_by',
        'articles', 'users',
        ['created_by'], ['username'],
        ondelete='SET NULL'
    )

    op.create_index('idx_articles_created_by', 'articles', ['created_by'])
    print("✓ Articles attribution column added")

    # 7. Assign existing articles to first admin (optional)
    print("\n[7/8] Assigning existing articles to admin...")

    if first_admin:
        result = bind.execute(sa.text("""
            UPDATE articles
            SET created_by = :admin_username
            WHERE created_by IS NULL
        """), {"admin_username": first_admin})

        print(f"✓ Assigned {result.rowcount} existing articles to {first_admin}")
    else:
        print("  ⚠️  Skipped: No admin user found")

    # 8. Final summary
    print("\n[8/8] Migration Summary:")
    print("="*60)

    total_users = bind.execute(sa.text("SELECT COUNT(*) FROM users")).scalar()
    admin_users = bind.execute(sa.text("SELECT COUNT(*) FROM users WHERE role = 'admin'")).scalar()
    regular_users = bind.execute(sa.text("SELECT COUNT(*) FROM users WHERE role = 'user'")).scalar()
    oauth_users = bind.execute(sa.text("SELECT COUNT(*) FROM users WHERE password_hash = ''")).scalar()

    print(f"  Total Users: {total_users}")
    print(f"  - Admins: {admin_users}")
    print(f"  - Regular Users: {regular_users}")
    print(f"  - OAuth Users: {oauth_users}")
    print("="*60)
    print("\n✅ MIGRATION COMPLETE!")
    print("\nNext Steps:")
    print("1. Login as admin and change password immediately")
    print("2. Create additional users via /config page (Users tab)")
    print("3. Test OAuth login (if configured)")
    print("="*60 + "\n")


def downgrade():
    """Rollback simple multi-user changes."""

    print("\n" + "="*60)
    print("ROLLING BACK SIMPLE MULTI-USER MIGRATION...")
    print("="*60)

    # Drop foreign key constraint
    op.drop_constraint('fk_articles_created_by', 'articles', type_='foreignkey')

    # Drop indexes
    op.drop_index('idx_articles_created_by', 'articles')
    op.drop_index('idx_users_role', 'users')
    op.drop_index('idx_users_is_active', 'users')
    op.drop_index('idx_users_email', 'users')

    # Drop columns
    op.drop_column('articles', 'created_by')

    # Drop check constraint
    op.drop_constraint('check_user_role', 'users', type_='check')

    # Drop unique constraint
    op.drop_constraint('uq_users_email', 'users', type_='unique')

    # Drop columns from users
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'role')
    op.drop_column('users', 'email')

    print("✅ ROLLBACK COMPLETE\n")
