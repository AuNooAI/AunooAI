import sqlite3
import os
from app.database import Database

def check_relevance_columns():
    db = Database()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('PRAGMA table_info(articles)')
        columns = cursor.fetchall()
        
        print('Articles table columns:')
        for col in columns:
            print(f'  {col[1]} ({col[2]})')
        
        # Check specifically for relevance columns
        relevance_columns = [col for col in columns if 'relevance' in col[1] or 'alignment' in col[1] or 'confidence' in col[1] or 'explanation' in col[1] or 'extracted' in col[1]]
        print(f'\nRelevance-related columns found: {len(relevance_columns)}')
        for col in relevance_columns:
            print(f'  ✓ {col[1]} ({col[2]})')
        
        if len(relevance_columns) >= 6:
            print('\n✅ All relevance columns appear to be properly added!')
            return True
        else:
            print(f'\n❌ Expected 6 relevance columns, found {len(relevance_columns)}')
            return False

if __name__ == '__main__':
    check_relevance_columns() 