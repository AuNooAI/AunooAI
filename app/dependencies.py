from fastapi import Depends
from app.research import Research
from app.database import Database, get_db
from sqlalchemy.orm import Session

def get_research(db: Session = Depends(get_db)):
    database = Database()  # Create a Database instance
    return Research(database)
