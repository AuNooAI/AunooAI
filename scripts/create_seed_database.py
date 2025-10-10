#!/usr/bin/env python3
"""
Create a minimal seed database (fnaapp.db.seed) with essential defaults.

This seed database contains:
- Default admin user (username: admin, password: admin - must be changed on first login)
- Default Auspex prompt
- Default keyword monitoring settings
- Default media bias settings
- All required empty tables

Usage:
    python scripts/create_seed_database.py
"""

import sys
import os
import sqlite3
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def create_seed_database():
    """Create a minimal seed database with essential defaults."""

    seed_db_path = Path(__file__).parent.parent / 'app' / 'data' / 'fnaapp.db.seed'

    # Remove existing seed database if it exists
    if seed_db_path.exists():
        print(f"Removing existing seed database: {seed_db_path}")
        seed_db_path.unlink()

    # Ensure directory exists
    seed_db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Creating seed database: {seed_db_path}")

    # Connect to the seed database (creates it)
    conn = sqlite3.connect(str(seed_db_path))
    cursor = conn.cursor()

    try:
        # Run Alembic migration to create schema
        print("Running Alembic migrations to create schema...")

        # Temporarily set DB_TYPE to sqlite for migrations
        old_db_type = os.environ.get('DB_TYPE')
        os.environ['DB_TYPE'] = 'sqlite'

        # Use alembic to create schema (we'll do this manually for simplicity)
        # For now, let's use the existing migration file SQL structure

        # Import and run the migration
        import subprocess

        # Set environment to use our seed database
        env = os.environ.copy()
        env['DB_TYPE'] = 'sqlite'
        env['DB_PATH'] = str(seed_db_path)

        # Create a temporary alembic.ini that points to our seed database
        alembic_ini_content = f"""[alembic]
script_location = alembic
sqlalchemy.url = sqlite:///{seed_db_path}

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""

        temp_alembic_ini = Path(__file__).parent.parent / 'alembic.seed.ini'
        with open(temp_alembic_ini, 'w') as f:
            f.write(alembic_ini_content)

        # Find alembic command (try venv first)
        venv_alembic = Path(__file__).parent.parent / '.venv' / 'bin' / 'alembic'
        alembic_cmd = str(venv_alembic) if venv_alembic.exists() else 'alembic'

        # Run alembic upgrade
        result = subprocess.run(
            [alembic_cmd, '-c', str(temp_alembic_ini), 'upgrade', 'head'],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env=env
        )

        # Clean up temp file
        temp_alembic_ini.unlink()

        if result.returncode != 0:
            print(f"Migration warning: {result.stderr}")
            print("Continuing with manual table creation...")
        else:
            print("✅ Schema created via Alembic migrations")

        # Restore original DB_TYPE
        if old_db_type:
            os.environ['DB_TYPE'] = old_db_type

        # Reconnect to ensure tables are visible
        conn.close()
        conn = sqlite3.connect(str(seed_db_path))
        cursor = conn.cursor()

        # Insert default admin user (password hash for 'admin')
        print("Creating default admin user...")
        # Use the same password hashing as the rest of the app (passlib with bcrypt)
        from passlib.context import CryptContext

        pwd_context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
            bcrypt__default_rounds=12,
            bcrypt__ident="2b"
        )

        admin_password_hash = pwd_context.hash('admin')

        cursor.execute("""
            INSERT OR IGNORE INTO users (username, password_hash, force_password_change, completed_onboarding)
            VALUES (?, ?, 1, 0)
        """, ('admin', admin_password_hash))

        print("✅ Created default admin user (username: admin, password: admin)")

        # Insert default Auspex prompt
        print("Creating default Auspex prompt...")
        default_auspex_prompt = """You are Auspex, an advanced AI research assistant specialized in analyzing news trends, sentiment patterns, and providing strategic insights.

Your capabilities include:
- Analyzing vast amounts of news data and research
- Identifying emerging trends and patterns
- Providing sentiment analysis and future impact predictions
- Accessing real-time news data through specialized tools
- Comparing different categories and topics
- Offering strategic foresight and risk analysis

When tool data is provided to you, it will be clearly marked at the beginning of your context. Always acknowledge when you're using tool data and explain what insights you're drawing from it.

Always provide thorough, insightful analysis backed by data. Be concise but comprehensive in your responses."""

        current_time = datetime.now().isoformat()

        cursor.execute("""
            INSERT OR IGNORE INTO auspex_prompts
            (name, title, content, description, is_default, created_at, updated_at, user_created)
            VALUES (?, ?, ?, ?, 1, ?, ?, NULL)
        """, (
            'default',
            'Default Auspex Assistant',
            default_auspex_prompt,
            'Default Auspex AI assistant configuration',
            current_time,
            current_time
        ))

        print("✅ Created default Auspex prompt")

        # Insert default keyword monitoring settings
        print("Creating default keyword monitoring settings...")
        cursor.execute("""
            INSERT OR IGNORE INTO keyword_monitor_settings
            (id, check_interval, interval_unit, search_fields, language, sort_by, page_size,
             is_enabled, daily_request_limit, search_date_range, provider, auto_ingest_enabled,
             min_relevance_threshold, quality_control_enabled, auto_save_approved_only,
             default_llm_model, llm_temperature, llm_max_tokens)
            VALUES (1, 1, 0, 'title,description', 'en', 'publishedAt', 10, 0, 100, 7,
                    'newsdata', 0, 0.7, 1, 1, 'gpt-4o-mini', 0.3, 2000)
        """)

        print("✅ Created default keyword monitoring settings")

        # Insert default keyword monitor status
        print("Creating default keyword monitor status...")
        cursor.execute("""
            INSERT OR IGNORE INTO keyword_monitor_status
            (id, last_check_time, last_error, requests_today, last_reset_date)
            VALUES (1, NULL, NULL, 0, ?)
        """, (current_time,))

        print("✅ Created default keyword monitor status")

        # Insert default media bias settings
        print("Creating default media bias settings...")
        cursor.execute("""
            INSERT OR IGNORE INTO mediabias_settings
            (id, enabled, last_updated, source_file)
            VALUES (1, 0, ?, 'mbfc_raw.csv')
        """, (current_time,))

        print("✅ Created default media bias settings")

        # Commit all changes
        conn.commit()

        print("\n" + "="*60)
        print("✅ Seed database created successfully!")
        print("="*60)
        print(f"\nLocation: {seed_db_path}")
        print("\nDefault credentials:")
        print("  Username: admin")
        print("  Password: admin")
        print("  (Must be changed on first login)")
        print("\nThis seed database can be copied to app/data/fnaapp.db")
        print("for new installations.")

        return True

    except Exception as e:
        print(f"\n❌ Error creating seed database: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    success = create_seed_database()
    sys.exit(0 if success else 1)
