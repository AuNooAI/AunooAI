import sqlite3
import os
from config.settings import DATABASE_DIR
import json

def get_active_database():
    config_path = os.path.join('data', 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config.get('active_database', 'fnaapp.db')

def update_articles_table():
    db_path = os.path.join(DATABASE_DIR, f"{get_active_database()}")
    print(f"Updating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if the driver_type column exists
        cursor.execute("PRAGMA table_info(articles)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'driver_type_explanation' not in columns:
            # Add the driver_type column
            cursor.execute("ALTER TABLE articles ADD COLUMN driver_type_explanation TEXT")
            print("Added driver_type_explanation column to articles table")

        # Update existing rows with a default value
        cursor.execute("UPDATE articles SET driver_type_explanation = 'Unknown' WHERE driver_type_explanation IS NULL")
        print(f"Updated {cursor.rowcount} rows with default driver_type_explanation value")

        conn.commit()
        print("Database update completed successfully")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        conn.rollback()

    finally:
        conn.close()

if __name__ == "__main__":
    update_articles_table()