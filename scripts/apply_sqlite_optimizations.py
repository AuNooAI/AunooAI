#!/usr/bin/env python3
"""
Apply SQLite Optimizations Script

This script applies the SQLite performance optimizations to existing databases.
It should be run after deploying the code changes to ensure all databases
are properly optimized.
"""

import sys
import os
import sqlite3
import shutil
from datetime import datetime

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import Database

def backup_database(db_path):
    """Create a backup of the database before applying optimizations"""
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"Database backed up to: {backup_path}")
    return backup_path

def apply_optimizations(db_path):
    """Apply SQLite optimizations to a database"""
    print(f"Applying optimizations to: {db_path}")
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Apply all optimizations (page_size can only be set on new databases)
        optimizations = [
            ("journal_mode", "WAL"),
            ("synchronous", "NORMAL"),
            ("temp_store", "MEMORY"),
            ("mmap_size", "30000000000"),
            # ("page_size", "32768"),  # Can only be set when creating new database
            ("cache_size", "50000"),
            ("busy_timeout", "30000"),
            ("wal_autocheckpoint", "1000"),
        ]
        
        print("Applying SQLite optimizations...")
        for pragma, value in optimizations:
            try:
                cursor.execute(f"PRAGMA {pragma} = {value}")
                print(f"  ✓ {pragma} = {value}")
            except sqlite3.Error as e:
                print(f"  ✗ Failed to set {pragma}: {e}")
        
        # Run optimize
        try:
            cursor.execute("PRAGMA optimize")
            print("  ✓ optimize")
        except sqlite3.Error as e:
            print(f"  ✗ Failed to run optimize: {e}")
        
        # Verify settings
        print("\nVerifying optimizations...")
        verification_queries = [
            ("journal_mode", "PRAGMA journal_mode"),
            ("synchronous", "PRAGMA synchronous"),
            ("temp_store", "PRAGMA temp_store"),
            ("mmap_size", "PRAGMA mmap_size"),
            ("page_size", "PRAGMA page_size"),  # Show current page size (read-only for existing DB)
            ("cache_size", "PRAGMA cache_size"),
            ("busy_timeout", "PRAGMA busy_timeout"),
            ("wal_autocheckpoint", "PRAGMA wal_autocheckpoint"),
        ]
        
        for name, query in verification_queries:
            try:
                cursor.execute(query)
                result = cursor.fetchone()[0]
                print(f"  {name}: {result}")
            except sqlite3.Error as e:
                print(f"  {name}: Error - {e}")
        
        conn.close()
        print("✅ Optimizations applied successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Failed to apply optimizations: {e}")
        return False

def vacuum_database(db_path):
    """Run VACUUM to optimize the database"""
    print(f"Running VACUUM on: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Run VACUUM
        cursor.execute("VACUUM")
        conn.close()
        
        print("✅ VACUUM completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ VACUUM failed: {e}")
        return False

def analyze_database(db_path):
    """Run ANALYZE to update database statistics"""
    print(f"Running ANALYZE on: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Run ANALYZE
        cursor.execute("ANALYZE")
        conn.close()
        
        print("✅ ANALYZE completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ ANALYZE failed: {e}")
        return False

def get_database_paths():
    """Get all database paths from the application"""
    try:
        db = Database()
        return [db.db_path]
    except Exception as e:
        print(f"Error getting database paths: {e}")
        return []

def main():
    """Main function to apply optimizations"""
    print("=" * 60)
    print("SQLite Optimization Application Script")
    print("=" * 60)
    
    # Get database paths
    db_paths = get_database_paths()
    
    if not db_paths:
        print("No databases found to optimize.")
        return False
    
    success_count = 0
    
    for db_path in db_paths:
        if not os.path.exists(db_path):
            print(f"Database not found: {db_path}")
            continue
        
        print(f"\nProcessing database: {db_path}")
        
        # Create backup
        try:
            backup_path = backup_database(db_path)
        except Exception as e:
            print(f"Failed to create backup: {e}")
            continue
        
        # Apply optimizations
        if apply_optimizations(db_path):
            # Run VACUUM
            if vacuum_database(db_path):
                # Run ANALYZE
                if analyze_database(db_path):
                    success_count += 1
                    print(f"✅ Database {db_path} optimized successfully!")
                else:
                    print(f"⚠️  Database {db_path} optimized but ANALYZE failed")
            else:
                print(f"⚠️  Database {db_path} optimized but VACUUM failed")
        else:
            print(f"❌ Failed to optimize database {db_path}")
    
    print("\n" + "=" * 60)
    print("Optimization Summary")
    print("=" * 60)
    print(f"Successfully optimized: {success_count}/{len(db_paths)} databases")
    
    if success_count == len(db_paths):
        print("\n✅ All databases optimized successfully!")
        print("The SQLite performance optimizations are now active.")
        print("\nNext steps:")
        print("1. Restart your application to use the optimized connections")
        print("2. Run the performance test script to validate improvements")
        print("3. Monitor the application for reduced file locking issues")
    else:
        print(f"\n⚠️  {len(db_paths) - success_count} databases failed optimization")
        print("Please check the error messages above and retry if needed.")
    
    return success_count == len(db_paths)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
