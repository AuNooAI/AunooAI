from fastapi import Depends
from sqlalchemy.orm import Session
from app.research import Research
from app.database import get_db

def get_research(db: Session = Depends(get_db)):
    return Research(db)
