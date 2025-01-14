from fastapi import Depends
from app.research import Research
from app.database import Database, get_db
from sqlalchemy.orm import Session
import logging

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create a single instance of Research
_research_instance = None

def get_research(db: Session = Depends(get_db)):
    global _research_instance
    if _research_instance is None:
        database = Database()  # Create a Database instance
        _research_instance = Research(database)
        logger.debug("Created new Research instance")
    return _research_instance
