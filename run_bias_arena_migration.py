#!/usr/bin/env python3
"""Script to run the model bias arena migration."""

import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import get_database_instance

def main():
    try:
        print("Connecting to database...")
        db = get_database_instance()
        print(f"Connected to: {db.db_path}")
        
        print("Reading migration file...")
        migration_path = "app/database/migrations/create_model_bias_arena_table.sql"
        with open(migration_path, 'r') as f:
            migration_sql = f.read()
        
        print("Executing migration...")
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript(migration_sql)
            conn.commit()
        
        print("✅ Model bias arena tables created successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    main() 