#!/usr/bin/env python3
"""
Migrate organizational profiles from SQLite to PostgreSQL.
"""

import sys
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

# Add the app directory to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
env_path = project_root / '.env'
load_dotenv(env_path)

def migrate_profiles():
    """Migrate organizational profiles from SQLite to PostgreSQL."""

    # SQLite database path
    sqlite_db = project_root / 'app' / 'data' / 'fnaapp.db'

    print("🚀 Migrating organizational profiles from SQLite to PostgreSQL...")
    print(f"Source: {sqlite_db}")

    if not sqlite_db.exists():
        print(f"❌ SQLite database not found at {sqlite_db}")
        return False

    try:
        # Connect to SQLite
        sqlite_conn = sqlite3.connect(str(sqlite_db))
        sqlite_conn.row_factory = sqlite3.Row
        cursor = sqlite_conn.cursor()

        # Get all profiles from SQLite
        cursor.execute("SELECT * FROM organizational_profiles ORDER BY id")
        profiles = cursor.fetchall()

        if not profiles:
            print("⚠️  No organizational profiles found in SQLite")
            sqlite_conn.close()
            return True

        print(f"📝 Found {len(profiles)} organizational profiles in SQLite")

        # Import psycopg2 for PostgreSQL
        import psycopg2
        from psycopg2.extras import execute_values

        # PostgreSQL connection details from environment
        pg_conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            dbname=os.getenv('DB_NAME', 'skunkworkx'),
            user=os.getenv('DB_USER', 'skunkworkx_user'),
            password=os.getenv('DB_PASSWORD')
        )
        pg_cursor = pg_conn.cursor()

        # Check if any profiles already exist in PostgreSQL
        pg_cursor.execute("SELECT COUNT(*) FROM organizational_profiles")
        existing_count = pg_cursor.fetchone()[0]

        if existing_count > 0:
            print(f"⚠️  PostgreSQL already has {existing_count} organizational profiles")
            response = input("Do you want to clear existing profiles and re-import? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Migration cancelled by user")
                pg_conn.close()
                sqlite_conn.close()
                return False

            # Clear existing profiles
            pg_cursor.execute("DELETE FROM organizational_profiles")
            pg_conn.commit()
            print("✅ Cleared existing profiles")

        # Prepare data for insertion
        insert_data = []
        for profile in profiles:
            insert_data.append((
                profile['name'],
                profile['description'],
                profile['industry'],
                profile['organization_type'],
                profile['region'],
                profile['key_concerns'],
                profile['strategic_priorities'],
                profile['risk_tolerance'],
                profile['innovation_appetite'],
                profile['decision_making_style'],
                profile['stakeholder_focus'],
                profile['competitive_landscape'],
                profile['regulatory_environment'],
                profile['custom_context'],
                profile['created_at'],
                profile['updated_at'],
                bool(profile['is_default'])
            ))

        # Insert into PostgreSQL
        insert_query = """
        INSERT INTO organizational_profiles (
            name, description, industry, organization_type, region,
            key_concerns, strategic_priorities, risk_tolerance,
            innovation_appetite, decision_making_style, stakeholder_focus,
            competitive_landscape, regulatory_environment, custom_context,
            created_at, updated_at, is_default
        ) VALUES %s
        """

        execute_values(pg_cursor, insert_query, insert_data)
        pg_conn.commit()

        # Verify migration
        pg_cursor.execute("SELECT COUNT(*) FROM organizational_profiles")
        migrated_count = pg_cursor.fetchone()[0]

        print(f"✅ Successfully migrated {migrated_count} organizational profiles to PostgreSQL")

        # Show summary
        pg_cursor.execute("SELECT name, industry, region FROM organizational_profiles ORDER BY id")
        migrated_profiles = pg_cursor.fetchall()

        print("\n📋 Migrated profiles:")
        for idx, (name, industry, region) in enumerate(migrated_profiles, 1):
            print(f"  {idx}. {name} ({industry} • {region or 'No region'})")

        # Cleanup
        pg_conn.close()
        sqlite_conn.close()

        return True

    except ImportError as e:
        print(f"❌ Required package not installed: {e}")
        print("Please install: pip install psycopg2-binary")
        return False
    except Exception as e:
        print(f"❌ Migration error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function."""
    print("=" * 70)
    print("AuNoo AI - Organizational Profiles Migration (SQLite → PostgreSQL)")
    print("=" * 70)
    print()

    success = migrate_profiles()

    if success:
        print("\n🎉 Migration completed successfully!")
        print("\nNext steps:")
        print("1. Restart your AuNoo AI application (service will auto-reload)")
        print("2. Navigate to News Feed → Profile → Manage Profiles")
        print("3. Verify all organizational profiles are available")
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
