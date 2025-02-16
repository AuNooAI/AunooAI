from app.utils.create_tables import create_articles_table, create_keyword_alerts_table

@router.post("/api/databases")
async def create_database(request: Request, data: dict):
    try:
        name = data.get('name')
        if not name:
            raise HTTPException(status_code=400, detail="Database name is required")
            
        # Add .db extension if not present
        if not name.endswith('.db'):
            name = f"{name}.db"
            
        db_path = os.path.join(DATABASE_DIR, name)
        
        # Create new database with correct schema
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Enable foreign key support
        cursor.execute("PRAGMA foreign_keys = ON")
        
        # Create tables with updated schema
        create_articles_table(cursor)
        create_keyword_alerts_table(cursor)
        
        conn.commit()
        conn.close()
        
        return {"id": name, "name": name, "message": f"Database {name} created successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/merge_backup")
async def merge_backup(request: Request):
    try:
        form = await request.form()
        
        # ... existing code ...
        
        # After creating new database or before merging
        with sqlite3.connect(target_db_path) as conn:
            cursor = conn.cursor()
            
            # Enable foreign key support
            cursor.execute("PRAGMA foreign_keys = ON")
            
            # Ensure correct schema
            create_articles_table(cursor)
            create_keyword_alerts_table(cursor)
            
            conn.commit()
            
        # Continue with merge process...
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 