from fastapi import Depends
from app.research import Research
from app.analytics import Analytics
from app.report import Report
from app.database import Database, get_database_instance
import logging

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Singleton instances
_research_instance = None
_analytics_instance = None
_report_instance = None

def get_research(db: Database = Depends(get_database_instance)):
    global _research_instance
    if _research_instance is None:
        _research_instance = Research(db)
        logger.debug("Created new Research instance")
    return _research_instance

def get_analytics(db: Database = Depends(get_database_instance)):
    global _analytics_instance
    if _analytics_instance is None:
        _analytics_instance = Analytics(db)
        logger.debug("Created new Analytics instance")
    return _analytics_instance

def get_report(db: Database = Depends(get_database_instance)):
    global _report_instance
    if _report_instance is None:
        _report_instance = Report(db)
        logger.debug("Created new Report instance")
    return _report_instance
