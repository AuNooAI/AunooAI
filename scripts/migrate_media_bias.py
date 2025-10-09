#!/usr/bin/env python3
"""
Migrate media bias data from SQLite to PostgreSQL
"""

import sys
import os
import sqlite3
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

def migrate_media_bias():
    """Migrate media bias sources from SQLite to PostgreSQL"""

    # Get database URL from environment
    sync_db_url = os.getenv('SYNC_DATABASE_URL', 'postgresql+psycopg2://skunkworkx_user:84Bd5WgemIKV3Bv3NRHF2uF8oTr2P1kA@localhost:5432/skunkworkx')

    # Connect to SQLite
    sqlite_db_path = "/home/orochford/tenants/skunkworkx.aunoo.ai/app/data/fnaapp.db"
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_cursor = sqlite_conn.cursor()

    # Connect to PostgreSQL
    pg_engine = create_engine(sync_db_url)

    print("Starting media bias migration...")

    try:
        # Get all media bias sources from SQLite
        sqlite_cursor.execute("""
            SELECT source, country, bias, factual_reporting, press_freedom,
                   media_type, popularity, mbfc_credibility_rating, enabled
            FROM mediabias
        """)

        sources = sqlite_cursor.fetchall()
        print(f"Found {len(sources)} media bias sources in SQLite")

        if not sources:
            print("No sources to migrate")
            return

        # Migrate to PostgreSQL
        migrated = 0
        skipped = 0

        with pg_engine.connect() as pg_conn:
            for source in sources:
                source_name, country, bias, factual_reporting, press_freedom, media_type, popularity, mbfc_credibility_rating, enabled = source

                # Check if source already exists in PostgreSQL
                result = pg_conn.execute(
                    text("SELECT COUNT(*) FROM mediabias WHERE source = :source"),
                    {"source": source_name}
                ).scalar()

                if result > 0:
                    skipped += 1
                    continue

                # Insert into PostgreSQL
                pg_conn.execute(
                    text("""
                        INSERT INTO mediabias
                        (source, country, bias, factual_reporting, press_freedom,
                         media_type, popularity, mbfc_credibility_rating, enabled)
                        VALUES
                        (:source, :country, :bias, :factual_reporting, :press_freedom,
                         :media_type, :popularity, :mbfc_credibility_rating, :enabled)
                    """),
                    {
                        "source": source_name,
                        "country": country,
                        "bias": bias,
                        "factual_reporting": factual_reporting,
                        "press_freedom": press_freedom,
                        "media_type": media_type,
                        "popularity": popularity,
                        "mbfc_credibility_rating": mbfc_credibility_rating,
                        "enabled": bool(enabled) if enabled is not None else True
                    }
                )
                migrated += 1

                if migrated % 100 == 0:
                    print(f"Migrated {migrated} sources...")

            pg_conn.commit()

        print(f"\n✅ Migration complete!")
        print(f"   Migrated: {migrated}")
        print(f"   Skipped (already exist): {skipped}")
        print(f"   Total: {len(sources)}")

        # Also migrate settings if they exist
        sqlite_cursor.execute("SELECT enabled, last_updated, source_file FROM mediabias_settings WHERE id = 1")
        settings_row = sqlite_cursor.fetchone()

        if settings_row:
            enabled, last_updated, source_file = settings_row
            with pg_engine.connect() as pg_conn:
                # Update settings in PostgreSQL
                pg_conn.execute(
                    text("""
                        INSERT INTO mediabias_settings (id, enabled, last_updated, source_file)
                        VALUES (1, :enabled, :last_updated, :source_file)
                        ON CONFLICT (id) DO UPDATE
                        SET enabled = :enabled,
                            last_updated = :last_updated,
                            source_file = :source_file
                    """),
                    {
                        "enabled": bool(enabled) if enabled is not None else True,
                        "last_updated": last_updated,
                        "source_file": source_file
                    }
                )
                pg_conn.commit()
            print(f"✅ Migrated media bias settings")

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        sqlite_conn.close()

    return 0

if __name__ == "__main__":
    sys.exit(migrate_media_bias())
