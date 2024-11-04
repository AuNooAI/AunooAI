from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from app.database import Database, get_db
from app.research import Research
from app.bulk_research import BulkResearch
from typing import List
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Add the get_research dependency
def get_research(db: Database = Depends(get_db)) -> Research:
    return Research(db)

@router.post("/api/bulk-research")
async def bulk_research_post(
    data: dict,
    research: Research = Depends(get_research),
    db: Database = Depends(get_db)
):
    urls = data.get('urls', [])
    summary_type = data.get('summaryType', 'curious_ai')
    model_name = data.get('modelName', 'gpt-3.5-turbo')
    summary_length = data.get('summaryLength', '50')
    summary_voice = data.get('summaryVoice', 'neutral')
    topic = data.get('topic')

    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    bulk_research = BulkResearch(db)
    results = await bulk_research.analyze_bulk_urls(
        urls=urls,
        summary_type=summary_type,
        model_name=model_name,
        summary_length=summary_length,
        summary_voice=summary_voice,
        topic=topic
    )

    return JSONResponse(content=results)

@router.post("/api/save-bulk-articles")
async def save_bulk_articles(
    data: dict,
    research: Research = Depends(get_research),
    db: Database = Depends(get_db)
):
    articles = data.get('articles', [])
    bulk_research = BulkResearch(db)
    results = await bulk_research.save_bulk_articles(articles)
    return JSONResponse(content=results)
