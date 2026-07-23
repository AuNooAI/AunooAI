from fastapi import APIRouter, HTTPException, Depends, Request, Response
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta
from app.database import Database, get_database_instance
from app.tasks.keyword_monitor import KeywordMonitor, get_task_status
from app.security.session import verify_session, verify_session_api
from app.models.media_bias import MediaBias
import logging
import json
import traceback
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import io
import csv
from pathlib import Path
from sqlalchemy.exc import OperationalError, DatabaseError
from fastapi.responses import JSONResponse
from app.config.config import load_config
from app.relevance import RelevanceCalculator, RelevanceCalculatorError
from urllib.parse import urlencode
from app.ai_models import LiteLLMModel, get_available_models
import asyncio
import uuid

# Set up logger
logger = logging.getLogger(__name__)

# Add global job tracking
_processing_jobs = {}

class ProcessingJob:
    def __init__(self, job_id: str, topic_id: str, options: dict):
        self.job_id = job_id
        self.topic_id = topic_id
        self.options = options
        self.status = "running"
        self.progress = 0
        self.results = None
        self.error = None
        self.started_at = datetime.utcnow()
        self.completed_at = None

def build_analysis_url(article, topic):
    """Build URL with all available article metadata for analysis page"""
    params = {
        'url': getattr(article, 'url', '') or getattr(article, 'uri', ''),
        'topic': topic
    }
    
    # Add metadata if available
    if hasattr(article, 'title') and article.title:
        params['title'] = article.title
    if hasattr(article, 'source') and article.source:
        params['source'] = article.source
    if hasattr(article, 'publication_date') and article.publication_date:
        params['publication_date'] = article.publication_date
    if hasattr(article, 'summary') and article.summary:
        params['summary'] = article.summary
        
    # Add media bias data if available
    if hasattr(article, 'bias') and article.bias:
        params['bias'] = article.bias
    if hasattr(article, 'factual_reporting') and article.factual_reporting:
        params['factual_reporting'] = article.factual_reporting
    if hasattr(article, 'mbfc_credibility_rating') and article.mbfc_credibility_rating:
        params['mbfc_credibility_rating'] = article.mbfc_credibility_rating
    if hasattr(article, 'bias_country') and article.bias_country:
        params['bias_country'] = article.bias_country
    if hasattr(article, 'media_type') and article.media_type:
        params['media_type'] = article.media_type
    if hasattr(article, 'popularity') and article.popularity:
        params['popularity'] = article.popularity
    
    return urlencode(params)

# API routes with prefix
router = APIRouter(prefix="/api/keyword-monitor")

# Page routes without prefix (for HTML pages)
page_router = APIRouter()

# Set up templates
templates = Jinja2Templates(directory="templates")
templates.env.auto_reload = True  # Reload templates on changes

class KeywordGroup(BaseModel):
    name: str
    topic: str

class Keyword(BaseModel):
    group_id: int
    keyword: str

class KeywordMonitorSettings(BaseModel):
    check_interval: int
    interval_unit: int
    search_fields: str
    language: str
    sort_by: str
    page_size: int
    daily_request_limit: int = 100
    provider: str = "newsapi"  # Legacy single provider (deprecated)
    providers: Optional[str] = None  # JSON array of selected providers
    # Auto-ingest settings
    auto_ingest_enabled: bool = False
    min_relevance_threshold: float = 0.0
    quality_control_enabled: bool = True
    auto_save_approved_only: bool = False
    default_llm_model: str = "gpt-5.4-mini"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1000
    max_articles_per_run: int = 50
    auto_regenerate_reports: bool = False

class PollingToggle(BaseModel):
    enabled: bool


@router.get("/groups")
async def get_groups(db=Depends(get_database_instance), session=Depends(verify_session)):
    """Get all keyword monitoring groups with schedule info."""
    try:
        groups = db.facade.get_all_keyword_groups_with_schedule_info()
        return [
            {
                "id": g["id"],
                "name": g["name"],
                "topic": g["topic"],
                "created_at": g.get("created_at"),
                "provider": g.get("provider"),
                "source": g.get("source"),
                # Per-group scheduling fields
                "is_active": g.get("is_active", True),
                "has_custom_schedule": g.get("has_custom_schedule", False),
                "has_custom_providers": g.get("has_custom_providers", False),
                "last_checked_at": g.get("last_checked_at").isoformat() if g.get("last_checked_at") else None,
                "next_check_at": g.get("next_check_at").isoformat() if g.get("next_check_at") else None,
                "last_error": g.get("last_error"),
            }
            for g in groups
        ]
    except Exception as e:
        logger.error(f"Error getting keyword groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/keywords")
async def get_keywords(
    group_id: Optional[int] = None,
    db=Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Get all monitored keywords, optionally filtered by group_id."""
    try:
        keywords = db.facade.get_monitored_keywords()
        if group_id is not None:
            keywords = [k for k in keywords if k.get("group_id") == group_id]
        return [
            {
                "id": k["id"],
                "group_id": k["group_id"],
                "keyword": k["keyword"],
                "created_at": k.get("created_at"),
                "last_checked": k.get("last_checked"),
            }
            for k in keywords
        ]
    except Exception as e:
        logger.error(f"Error getting keywords: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group-summary")
async def get_group_summaries(db=Depends(get_database_instance), session=Depends(verify_session)):
    """Get summary statistics for all keyword groups (for Gather cards)."""
    try:
        # Use the new method that includes schedule info
        groups = db.facade.get_all_keyword_groups_with_schedule_info()
        keywords = db.facade.get_monitored_keywords()
        relevance_stats = db.facade.get_keyword_relevance_stats()

        # Get monitoring status
        status = db.facade.get_keyword_monitoring_counter()

        # Get relevance threshold from settings
        settings = db.facade.get_keyword_monitor_settings_by_id(1)
        relevance_threshold = settings.get('min_relevance_threshold', 0.39) if settings else 0.39

        summaries = []
        for group in groups:
            group_id = group["id"]
            group_keywords = [k for k in keywords if k.get("group_id") == group_id]
            group_stats = [s for s in relevance_stats if s.get("group_id") == group_id]

            # Calculate totals (handle None values)
            total_articles = sum((s.get("total_matches") or 0) for s in group_stats)
            avg_relevance = (
                sum((s.get("avg_relevance") or 0) for s in group_stats) / len(group_stats) * 100
                if group_stats else 0
            )
            high_relevance_pct = (
                sum((s.get("high_relevance_pct") or 0) for s in group_stats) / len(group_stats)
                if group_stats else 0
            )

            # Use group-level last_checked_at if available, otherwise find from keywords
            last_checked = group.get("last_checked_at")
            if not last_checked:
                for kw in group_keywords:
                    kw_last = kw.get("last_checked")
                    if kw_last:
                        if last_checked is None or kw_last > last_checked:
                            last_checked = kw_last

            # Determine status using group-level last_error if available
            group_error = group.get("last_error")
            status_value = "never_run"
            if group_error:
                status_value = "error"
            elif status and status.get("last_error"):
                status_value = "error"
            elif last_checked:
                status_value = "success"

            # Get detailed article stats for this group (pass relevance threshold)
            article_stats = db.facade.get_group_article_stats(group_id, relevance_threshold)

            # Calculate relevance percentage (relevant / total scored)
            total_scored = article_stats.get('relevant_count', 0) + article_stats.get('irrelevant_count', 0)
            relevance_pct = round((article_stats.get('relevant_count', 0) / total_scored * 100) if total_scored > 0 else 0)

            # Format timestamps
            last_checked_iso = None
            if last_checked:
                if hasattr(last_checked, 'isoformat'):
                    last_checked_iso = last_checked.isoformat()
                else:
                    last_checked_iso = str(last_checked)

            next_check_at = group.get("next_check_at")
            next_check_iso = None
            if next_check_at:
                if hasattr(next_check_at, 'isoformat'):
                    next_check_iso = next_check_at.isoformat()
                else:
                    next_check_iso = str(next_check_at)

            summaries.append({
                "id": group_id,
                "name": group["name"],
                "topic": group["topic"],
                "keyword_count": len(group_keywords),
                "total_articles": article_stats.get('total_count', 0),
                "avg_relevance": round(avg_relevance),
                "relevance_pct": relevance_pct,  # % of scored articles that are relevant
                "last_checked": last_checked_iso,
                "last_error": group_error or (status.get("last_error") if status else None),
                "status": status_value,
                # Relevance-based article counts
                "relevant_count": article_stats.get('relevant_count', 0),
                "irrelevant_count": article_stats.get('irrelevant_count', 0),
                "unscored_count": article_stats.get('unscored_count', 0),
                # Time-based counts
                "articles_past_24h": article_stats.get('articles_past_24h', 0),
                "articles_past_week": article_stats.get('articles_past_week', 0),
                "articles_past_month": article_stats.get('articles_past_month', 0),
                "daily_counts": article_stats.get('daily_counts', []),
                # Per-group schedule info
                "is_active": group.get("is_active", True),
                "has_custom_schedule": group.get("has_custom_schedule", False),
                "has_custom_providers": group.get("has_custom_providers", False),
                "next_check_at": next_check_iso,
            })

        return summaries
    except Exception as e:
        logger.error(f"Error getting group summaries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group/{group_id}/articles")
async def get_group_articles(
    group_id: int,
    limit: int = 20,
    db=Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Get recent articles for a keyword group."""
    try:
        # Get articles matched to this group
        articles = db.facade.get_articles_for_keyword_group(group_id, limit=limit)
        return [
            {
                "id": a.get("id"),
                "uri": a.get("uri") or a.get("url"),
                "title": a.get("title"),
                "source": a.get("source"),
                "publication_date": a.get("publication_date"),
                "detected_at": a.get("detected_at"),
                # Scores
                "keyword_relevance_score": a.get("keyword_relevance_score"),
                "topic_alignment_score": a.get("topic_alignment_score"),
                "overall_match_explanation": a.get("overall_match_explanation"),
                # Content
                "category": a.get("category"),
                "summary": a.get("summary"),
                # Enrichment fields with explanations
                "sentiment": a.get("sentiment"),
                "sentiment_explanation": a.get("sentiment_explanation"),
                "time_to_impact": a.get("time_to_impact"),
                "time_to_impact_explanation": a.get("time_to_impact_explanation"),
                "driver_type": a.get("driver_type"),
                "driver_type_explanation": a.get("driver_type_explanation"),
            }
            for a in articles
        ]
    except Exception as e:
        logger.error(f"Error getting group articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Per-Group Collection Settings Endpoints
# ============================================================================

class GroupSettingsUpdate(BaseModel):
    """Request body for updating per-group collection settings."""
    use_global_settings: Optional[bool] = None  # Set True to reset all to global defaults
    is_active: Optional[bool] = None
    check_interval: Optional[int] = None
    interval_unit: Optional[int] = None  # 60=minutes, 3600=hours, 86400=days
    search_date_range: Optional[int] = None
    providers: Optional[str] = None  # JSON array e.g., '["thenewsapi", "arxiv"]'
    social_platforms: Optional[str] = None  # JSON array of xpoz platforms; null = XPOZ_PLATFORMS env default
    auto_ingest_enabled: Optional[bool] = None
    min_relevance_threshold: Optional[float] = None
    quality_control_enabled: Optional[bool] = None
    auto_save_approved_only: Optional[bool] = None
    default_llm_model: Optional[str] = None
    llm_temperature: Optional[float] = None
    llm_max_tokens: Optional[int] = None


@router.get("/group/{group_id}/settings")
async def get_group_settings(
    group_id: int,
    db=Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Get effective collection settings for a keyword group.

    Returns merged settings where NULL values are replaced with global defaults.
    Also indicates which settings are custom vs inherited from global.
    """
    try:
        effective = db.facade.get_effective_group_settings(group_id)

        if not effective:
            raise HTTPException(status_code=404, detail=f"Group {group_id} not found")

        return {
            "success": True,
            "group_id": effective['id'],
            "group_name": effective['name'],
            "topic": effective['topic'],
            "is_active": effective['is_active'],
            "last_checked_at": effective['last_checked_at'].isoformat() if effective.get('last_checked_at') else None,
            "next_check_at": effective['next_check_at'].isoformat() if effective.get('next_check_at') else None,
            "last_error": effective.get('last_error'),
            "settings": effective['settings'],
            "custom_fields": effective['custom_fields'],
            "has_custom_schedule": effective['has_custom_schedule'],
            "has_custom_providers": effective['has_custom_providers'],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting group settings for group {group_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group/{group_id}/settings")
async def update_group_settings(
    group_id: int,
    settings: GroupSettingsUpdate,
    db=Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Update per-group collection settings.

    Set use_global_settings=true to reset all custom settings back to global defaults.
    Individual settings set to null will inherit from global settings.
    """
    try:
        # Check group exists
        group = db.facade.get_keyword_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail=f"Group {group_id} not found")

        # Convert Pydantic model to dict, excluding None values (unless use_global_settings)
        settings_dict = settings.model_dump(exclude_unset=True)

        success = db.facade.update_keyword_group_settings(group_id, settings_dict)

        if success:
            # Return updated effective settings
            effective = db.facade.get_effective_group_settings(group_id)
            return {
                "success": True,
                "message": "Settings updated successfully",
                "group_id": group_id,
                "effective_settings": effective['settings'] if effective else {},
                "custom_fields": effective['custom_fields'] if effective else [],
            }
        else:
            return {"success": False, "message": "No settings were updated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating group settings for group {group_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TestProcessRequest(BaseModel):
    article_uri: str
    group_id: int


@router.post("/test-process-article")
async def test_process_article(
    request: TestProcessRequest,
    db=Depends(get_database_instance),
    session=Depends(verify_session)
):
    """
    Test endpoint to process a single article through the LLM enrichment workflow.
    Returns step-by-step results for troubleshooting the pipeline.
    If the article is not in the database, it will scrape the URL first.
    """
    from app.services.automated_ingest_service import AutomatedIngestService
    from app.research import Research
    from datetime import datetime, timezone
    import time

    steps = []

    def add_step(name: str, status: str, message: str, details: dict = None):
        steps.append({
            "name": name,
            "status": status,  # "success", "error", "warning", "info"
            "message": message,
            "details": details or {}
        })

    try:
        # Step 1: Lookup article in database
        add_step("lookup", "info", f"Looking up article: {request.article_uri[:60]}...")

        article_data = db.facade.get_article_by_uri(request.article_uri)
        article_dict = None

        needs_scrape = False

        if article_data:
            # Convert to dict
            if hasattr(article_data, '_mapping'):
                article_dict = dict(article_data._mapping)
            else:
                article_dict = dict(article_data) if not isinstance(article_data, dict) else article_data

            # Ensure news_source is set (required by analyze_article_content)
            if not article_dict.get('news_source'):
                article_dict['news_source'] = article_dict.get('source', 'Unknown')

            # Check if article has content (summary is the main content field in articles table)
            has_content = bool(article_dict.get('summary'))
            content_length = len(article_dict.get('summary') or '')

            if has_content:
                add_step("lookup", "success", "Article found in database with content", {
                    "title": article_dict.get('title', 'N/A')[:80],
                    "source": article_dict.get('news_source', 'Unknown'),
                    "content_length": content_length
                })
            else:
                add_step("lookup", "warning", "Article found but has no content - will re-scrape", {
                    "title": article_dict.get('title', 'N/A')[:80]
                })
                needs_scrape = True
        else:
            needs_scrape = True
            add_step("lookup", "warning", "Article not in database - will attempt to scrape")

        # Step 1b: Scrape the article if needed
        if needs_scrape:
            add_step("scrape", "info", f"Scraping article from URL...")
            scrape_start = time.time()

            try:
                research = Research(db)
                scrape_result = await research.scrape_article(request.article_uri)
                scrape_elapsed = round(time.time() - scrape_start, 2)

                if scrape_result and scrape_result.get('content') and not scrape_result.get('error'):
                    content = scrape_result['content']
                    metadata = scrape_result.get('metadata', {})

                    add_step("scrape", "success", f"Scraped content ({scrape_elapsed}s)", {
                        "content_length": len(content),
                        "source": scrape_result.get('source', 'Unknown'),
                        "has_title": bool(metadata.get('title'))
                    })

                    # Step 1c: Save the scraped article to database
                    article_exists = article_data is not None
                    add_step("save_new", "info", f"{'Updating' if article_exists else 'Saving'} article in database...")

                    # Extract title from metadata or content
                    title = metadata.get('title', '')
                    if not title:
                        # Try to extract title from first line of content
                        lines = content.strip().split('\n')
                        if lines:
                            # Remove markdown headers
                            title = lines[0].lstrip('#').strip()[:200]

                    # Build article data for saving
                    extracted_source = scrape_result.get('source', research.extract_source(request.article_uri))
                    new_article_data = {
                        'uri': request.article_uri,
                        'url': request.article_uri,
                        'title': title or 'Untitled Article',
                        'summary': content[:8000] if content else '',  # Store content in summary field
                        'news_source': extracted_source,
                        'publication_date': scrape_result.get('publication_date') or datetime.now(timezone.utc).date().isoformat(),
                    }

                    try:
                        db.save_article(new_article_data)

                        # Link article to keyword group if it's a new article
                        if not article_exists:
                            from app.database_models import t_keyword_article_matches as keyword_article_matches
                            from sqlalchemy import insert
                            db.facade._execute_with_rollback(insert(keyword_article_matches).values(
                                article_uri=request.article_uri,
                                keyword_ids='',  # No specific keyword, just group association
                                group_id=request.group_id,
                            ))
                            db.facade.connection.commit()

                        add_step("save_new", "success", f"Article {'updated' if article_exists else 'saved'} to database", {
                            "title": new_article_data['title'][:60],
                            "source": new_article_data['news_source']
                        })

                        # Set article_dict so enrichment can proceed
                        article_dict = new_article_data

                    except Exception as save_err:
                        add_step("save_new", "error", f"Failed to save article: {str(save_err)}")
                        return {
                            "success": False,
                            "steps": steps,
                            "enrichment_fields": {},
                            "message": f"Article scraped but failed to save: {str(save_err)}"
                        }
                else:
                    error_msg = scrape_result.get('error', 'No content returned') if scrape_result else 'Scrape returned empty'
                    add_step("scrape", "error", f"Scrape failed ({scrape_elapsed}s): {error_msg}")
                    return {
                        "success": False,
                        "steps": steps,
                        "enrichment_fields": {},
                        "message": f"Could not scrape article: {error_msg}"
                    }

            except Exception as scrape_err:
                scrape_elapsed = round(time.time() - scrape_start, 2)
                add_step("scrape", "error", f"Scrape error ({scrape_elapsed}s): {str(scrape_err)}")
                return {
                    "success": False,
                    "steps": steps,
                    "enrichment_fields": {},
                    "message": f"Error scraping article: {str(scrape_err)}"
                }

        # Step 2: Get keyword group and topic
        add_step("topic", "info", f"Looking up keyword group {request.group_id}...")

        groups = db.facade.get_all_keyword_groups()
        group = next((g for g in groups if g['id'] == request.group_id), None)
        if not group:
            add_step("topic", "error", f"Keyword group {request.group_id} not found")
            return {
                "success": False,
                "steps": steps,
                "enrichment_fields": {},
                "message": "Keyword group not found"
            }

        topic = group['topic']
        article_dict['topic'] = topic
        add_step("topic", "success", f"Using topic: {topic}", {"group_name": group['name']})

        # Step 3: Initialize pipeline
        add_step("model", "info", "Initializing AI pipeline...")

        ingest_service = AutomatedIngestService(db)
        inference_mode = ingest_service.get_inference_mode()
        configured_model = ingest_service.get_llm_client()
        llm_params = ingest_service.get_llm_parameters()

        # Describe what the pipeline will use based on inference mode
        mode_descriptions = {
            'local': 'Local only (DeBERTa + Qwen + Phi-3)',
            'hybrid': 'Hybrid (DeBERTa → GPT fallback)',
            'external': 'External (GPT only)',
        }
        mode_desc = mode_descriptions.get(inference_mode, inference_mode)

        add_step("model", "success", f"Pipeline: {mode_desc}", {
            "inference_mode": inference_mode,
            "llm_fallback": configured_model if inference_mode != 'local' else 'Qwen (local)',
            "temperature": llm_params.get('temperature'),
            "max_tokens": llm_params.get('max_tokens')
        })

        # Step 4: Run enrichment through the configured pipeline
        add_step("enrich", "info", f"Running {inference_mode} enrichment...")
        start_time = time.time()

        try:
            enriched_article = ingest_service.analyze_article_content(article_dict)
            elapsed = round(time.time() - start_time, 2)

            # Extract enrichment fields
            update_fields = {
                'category': enriched_article.get('category'),
                'sentiment': enriched_article.get('sentiment'),
                'sentiment_explanation': enriched_article.get('sentiment_explanation'),
                'time_to_impact': enriched_article.get('time_to_impact'),
                'time_to_impact_explanation': enriched_article.get('time_to_impact_explanation'),
                'driver_type': enriched_article.get('driver_type'),
                'driver_type_explanation': enriched_article.get('driver_type_explanation'),
                'future_signal': enriched_article.get('future_signal'),
                'future_signal_explanation': enriched_article.get('future_signal_explanation'),
            }

            # Filter out None values
            update_fields = {k: v for k, v in update_fields.items() if v is not None}

            # Extract which model was used for each field (from adaptive enrichment)
            enrichment_sources = enriched_article.get('enrichment_sources', {})
            sources_summary = []
            for field in ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']:
                source = enrichment_sources.get(field, 'unknown')
                if field in update_fields:
                    sources_summary.append(f"{field}={source}")

            if not update_fields:
                add_step("enrich", "warning", f"Pipeline returned no enrichment fields ({elapsed}s)", {
                    "elapsed_seconds": elapsed,
                    "inference_mode": inference_mode
                })
                return {
                    "success": False,
                    "steps": steps,
                    "enrichment_fields": {},
                    "message": f"Enrichment completed but returned no data. Mode: {inference_mode}"
                }

            add_step("enrich", "success", f"Enrichment complete ({elapsed}s)", {
                "elapsed_seconds": elapsed,
                "fields_extracted": list(update_fields.keys()),
                "sources": ', '.join(sources_summary) if sources_summary else 'not tracked'
            })

        except Exception as analysis_error:
            elapsed = round(time.time() - start_time, 2)
            add_step("enrich", "error", f"LLM analysis failed: {str(analysis_error)}", {
                "elapsed_seconds": elapsed,
                "error_type": type(analysis_error).__name__
            })
            return {
                "success": False,
                "steps": steps,
                "enrichment_fields": {},
                "message": f"LLM analysis failed: {str(analysis_error)}"
            }

        # Step 5: Save to database
        add_step("save", "info", "Saving enrichment fields to database...")

        try:
            db.facade.update_article_fields(request.article_uri, update_fields)
            add_step("save", "success", f"Saved {len(update_fields)} fields to database")
        except Exception as save_error:
            add_step("save", "error", f"Failed to save: {str(save_error)}")
            return {
                "success": False,
                "steps": steps,
                "enrichment_fields": update_fields,
                "message": f"Enrichment succeeded but save failed: {str(save_error)}"
            }

        logger.info(f"✅ Test process complete for {request.article_uri}: {list(update_fields.keys())}")

        return {
            "success": True,
            "steps": steps,
            "enrichment_fields": update_fields,
            "message": f"Article processed successfully. Updated {len(update_fields)} fields."
        }

    except Exception as e:
        logger.error(f"Error in test_process_article: {e}", exc_info=True)
        add_step("error", "error", f"Unexpected error: {str(e)}")
        return {
            "success": False,
            "steps": steps,
            "enrichment_fields": {},
            "message": str(e)
        }


@router.delete("/group/{group_id}/unscored-articles")
async def delete_unscored_articles(
    group_id: int,
    db=Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Delete all unscored articles (no relevance score) for a keyword group."""
    try:
        # Get unscored article matches for this group
        deleted_count = db.facade.delete_unscored_article_matches(group_id)
        logger.info(f"🗑️ Deleted {deleted_count} unscored article matches for group {group_id}")
        return {
            "success": True,
            "deleted_count": deleted_count,
            "message": f"Deleted {deleted_count} unscored articles"
        }
    except Exception as e:
        logger.error(f"Error deleting unscored articles for group {group_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/groups")
async def create_group(group: KeywordGroup, db=Depends(get_database_instance), session=Depends(verify_session)):
    try:
        return {"id": db.facade.create_keyword_monitor_group((group.name, group.topic))}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/keywords")
async def add_keyword(keyword: Keyword, db=Depends(get_database_instance), session=Depends(verify_session)):
    try:
        return {"id": db.facade.create_keyword((keyword.group_id, keyword.keyword))}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/keywords/{keyword_id}")
async def delete_keyword(keyword_id: int, db=Depends(get_database_instance), session=Depends(verify_session)):
    try:
        db.facade.delete_keyword(keyword_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateKeywordRequest(BaseModel):
    keyword: str


@router.put("/keywords/{keyword_id}")
async def update_keyword(
    keyword_id: int,
    request: UpdateKeywordRequest,
    db=Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Update an existing keyword's text."""
    try:
        new_keyword = request.keyword.strip()
        if not new_keyword:
            raise HTTPException(status_code=400, detail="Keyword cannot be empty")

        # Normalize the keyword for API compatibility
        from app.utils.keyword_normalizer import normalize_keyword
        normalized = normalize_keyword(new_keyword)

        if not normalized:
            raise HTTPException(status_code=400, detail="Invalid keyword after normalization")

        db.facade.update_monitored_keyword_text(
            keyword_id=keyword_id,
            new_keyword=normalized
        )

        return {
            "success": True,
            "keyword_id": keyword_id,
            "keyword": normalized
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating keyword: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/groups/{group_id}")
async def delete_group(group_id: int, db=Depends(get_database_instance), session=Depends(verify_session)):
    try:
        db.facade.delete_keyword_group(group_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/groups/by-topic/{topic_name}")
async def delete_groups_by_topic(topic_name: str, db=Depends(get_database_instance), session=Depends(verify_session)):
    """Delete all keyword groups associated with a specific topic and clean up orphaned data"""
    try:
            groups = db.facade.get_all_group_ids_associated_to_topic(topic_name)

            if not groups:
                return {"success": True, "groups_deleted": 0}

            group_ids = [group['id'] for group in groups]
            groups_deleted = len(group_ids)
            
            # Find all keyword IDs belonging to these groups
            keyword_ids = []
            for group_id in group_ids:
                keywords = db.facade.get_keyword_ids_associated_to_group(group_id)
                keyword_ids.extend([kw['id'] for kw in keywords])
            
            # Delete all keyword alerts related to these keywords
            alerts_deleted = 0
            if keyword_ids:
                ids_str = ','.join('?' for _ in keyword_ids)
                
                # Check if the keyword_article_matches table exists
                use_new_table = db.facade.check_if_keyword_article_matches_table_exists()
                
                if use_new_table:
                    # For the new table structure
                    for group_id in group_ids:
                        alerts_deleted += db.facade.delete_keyword_article_matches_from_new_table_structure(group_id)
                else:
                    # For the original table structure
                    alerts_deleted = db.facade.delete_keyword_article_matches_from_old_table_structure(ids_str, keyword_ids)
            
            # Delete all keywords for these groups
            keywords_deleted = 0
            if group_ids:
                ids_str = ','.join('?' for _ in group_ids)
                keywords_deleted = db.facade.delete_groups_keywords(ids_str, group_ids)

            # Delete all keyword groups for this topic
            groups_deleted = db.facade.delete_all_keyword_groups(topic_name)

            return {
                "success": True,
                "groups_deleted": groups_deleted,
                "keywords_deleted": keywords_deleted,
                "alerts_deleted": alerts_deleted
            }
    except Exception as e:
        logging.error(f"Error deleting keyword groups for topic {topic_name}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: int, db=Depends(get_database_instance), session=Depends(verify_session_api)):
    try:
        # Check if the alert is in the keyword_article_matches table
        use_new_table = db.facade.check_if_keyword_article_matches_table_exists()

        if use_new_table:
            # Check if the alert ID is in the new table
            if db.facade.check_if_alert_id_exists_in_new_table_structure(alert_id):
                # Update the new table
                db.facade.mark_alert_as_read_or_unread_in_new_table(alert_id, 1)
            else:
                # Update the old table
                db.facade.mark_alert_as_read_or_unread_in_old_table(alert_id, 1)
        else:
            # Update the old table
            db.facade.mark_alert_as_read_in_old_table(alert_id)

        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class CheckNowRequest(BaseModel):
    topic: Optional[str] = None
    group_id: Optional[int] = None


@router.post("/check-now")
async def check_now(
    http_request: Request,
    request: CheckNowRequest = None,
    db=Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Trigger an immediate keyword check"""
    try:
        # Handle both old-style (no body) and new-style (with body) requests
        if request is None:
            # Old-style request - check all keywords
            topic = None
            group_id = None
        else:
            topic = request.topic
            group_id = request.group_id

        # Log number of keywords being monitored
        if group_id:
            keyword_count = db.facade.get_number_of_monitored_keywords_by_group_id(group_id)
            logger.info(f"Running manual keyword check for group {group_id} - {keyword_count} keywords configured")
        else:
            keyword_count = db.facade.get_total_number_of_keywords()
            logger.info(f"Running manual keyword check - {keyword_count} keywords configured")

        # Check if this should be a background task (for operations likely to take >10 seconds)
        request_type = http_request.headers.get('X-Request-Type', 'normal')
        use_background_task = keyword_count > 3  # Lower threshold for background tasks

        logger.info(f"Keyword check decision: count={keyword_count}, request_type={request_type}, use_background_task={use_background_task}")

        if use_background_task:
            # Use background task system for long-running operations
            from app.services.background_task_manager import get_task_manager, run_keyword_check_task

            task_manager = get_task_manager()
            task_id = task_manager.create_task(
                name="Keyword Check",
                total_items=keyword_count,
                metadata={"type": "keyword_check", "keyword_count": keyword_count}
            )

            # Start the task in background
            import asyncio
            logger.info(f"Starting background task {task_id} for keyword check")

            task_coroutine = task_manager.run_task(task_id, run_keyword_check_task, group_id=group_id)
            asyncio.create_task(task_coroutine)

            logger.info(f"Background task {task_id} started successfully")

            return JSONResponse({
                "success": True,
                "task_id": task_id,
                "total_keywords": keyword_count,
                "message": "Keyword check started as background task"
            })

        else:
            # Quick synchronous operation
            from app.tasks.keyword_monitor import _background_task_status
            from datetime import datetime

            monitor = KeywordMonitor(db)

            if group_id:
                logger.info(f"Calling monitor.check_keywords() for group {group_id}...")
            else:
                logger.info("Calling monitor.check_keywords()...")
            result = await monitor.check_keywords(group_id=group_id)
            logger.info(f"Result from check_keywords(): {result}")

            # Update the global status so UI shows correct "Last check" time
            _background_task_status["last_check_time"] = datetime.now()

            if result is None:
                logger.error("check_keywords() returned None!")
                _background_task_status["last_error"] = "Keyword check returned None"
                raise HTTPException(status_code=500, detail="Keyword check returned None - check collector initialization")

            if result.get("success", False):
                _background_task_status["last_error"] = None
                logger.info(f"Keyword check completed successfully: {result.get('new_articles', 0)} new articles found")
                return result
            else:
                error_msg = result.get('error', 'Unknown error')
                _background_task_status["last_error"] = error_msg
                logger.error(f"Keyword check failed: {error_msg}")
                raise HTTPException(status_code=500, detail=error_msg)
            
    except ValueError as e:
        logger.error(f"Value error in check_now: {str(e)}")
        if "Rate limit exceeded" in str(e) or "request limit reached" in str(e) or "rate limit" in str(e).lower():
            # Return a specific status code for rate limiting with the actual error message
            error_msg = str(e)
            if "NewsAPI rate limit exceeded" in error_msg:
                detail = "NewsAPI rate limit exceeded. Developer accounts are limited to 100 requests per 24 hours. Please upgrade to a paid plan or try again tomorrow."
            elif "request limit reached" in error_msg:
                detail = "Daily API request limit reached. Please try again tomorrow."
            else:
                detail = f"Rate limit exceeded: {error_msg}"
            
            raise HTTPException(
                status_code=429,  # Too Many Requests
                detail=detail
            )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error checking keywords: {str(e)}")
        logger.error(traceback.format_exc())  # Log the full traceback
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts")
async def get_alerts(
    request: Request,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance),
    show_read: bool = False
):
    try:
        # Initialize media bias for article enrichment
        media_bias = MediaBias(db)

        (columns, rows) = db.facade.get_alerts(show_read)
        alerts = []

        for row in rows:
            alert_data = dict(zip(columns, row))

            # Restructure for consistent response format
            article_data = {
                "title": alert_data.get("title", ""),
                "url": alert_data.get("url", ""),
                "uri": alert_data.get("uri", ""),
                "summary": alert_data.get("summary", ""),
                "source": alert_data.get("source", ""),
                "publication_date": alert_data.get("publication_date", "")
            }

            # Try to get media bias data using both source name and URL
            bias_data = None
            if article_data["source"]:
                # First try with the source name
                bias_data = media_bias.get_bias_for_source(article_data["source"])

            # If no match with source name, try with the URL
            if not bias_data and article_data["url"]:
                bias_data = media_bias.get_bias_for_source(article_data["url"])

            if bias_data:
                article_data["bias"] = bias_data.get("bias")
                article_data["factual_reporting"] = bias_data.get("factual_reporting")
                article_data["mbfc_credibility_rating"] = bias_data.get("mbfc_credibility_rating")
                article_data["bias_country"] = bias_data.get("country")
                article_data["press_freedom"] = bias_data.get("press_freedom")
                article_data["media_type"] = bias_data.get("media_type")
                article_data["popularity"] = bias_data.get("popularity")

            # Add specific logging for the Tom's Hardware article
            if "tomshardware.com" in article_data["url"] and "stargate" in article_data["url"]:
                logger.info(f"STARGATE ARTICLE DEBUG: uri={article_data['url']}")
                logger.info(f"STARGATE ARTICLE DEBUG: Data before enrichment lookup: {article_data}")

            # Check for enrichment data in the articles table
            try:
                enrichment_row = db.facade.get_article_enrichment(article_data)
                if enrichment_row:
                    (category, sentiment, driver_type, time_to_impact,
                     topic_alignment_score, keyword_relevance_score,
                     confidence_score, overall_match_explanation,
                     extracted_article_topics, extracted_article_keywords,
                     auto_ingested, ingest_status, quality_score, quality_issues) = enrichment_row

                    logger.info(f"API ENRICHMENT FOUND for {article_data['uri']}: category={category}, sentiment={sentiment}, driver_type={driver_type}, time_to_impact={time_to_impact}")

                    # Always add enrichment fields (use empty string if None to match page load behavior)
                    article_data["category"] = category or ''
                    article_data["sentiment"] = sentiment or ''
                    article_data["driver_type"] = driver_type or ''
                    article_data["time_to_impact"] = time_to_impact or ''
                    article_data["future_signal"] = ''  # Not in enrichment_row, but needed for consistency

                    # Always add relevance scores (even if None, for consistency)
                    article_data["topic_alignment_score"] = topic_alignment_score
                    article_data["keyword_relevance_score"] = keyword_relevance_score
                    article_data["confidence_score"] = confidence_score
                    article_data["overall_match_explanation"] = overall_match_explanation or ''
                    if extracted_article_topics:
                        try:
                            article_data["extracted_article_topics"] = json.loads(extracted_article_topics)
                        except:
                            article_data["extracted_article_topics"] = []
                    if extracted_article_keywords:
                        try:
                            article_data["extracted_article_keywords"] = json.loads(extracted_article_keywords)
                        except:
                            article_data["extracted_article_keywords"] = []

                    # Add auto-ingest fields
                    article_data["auto_ingested"] = bool(auto_ingested) if auto_ingested is not None else False
                    article_data["ingest_status"] = ingest_status
                    article_data["quality_score"] = quality_score
                    article_data["quality_issues"] = quality_issues

                    # Debug log to verify enrichment is in article_data
                    if "Uncertainty" in article_data["title"]:
                        logger.info(f"TEMPLATE DEBUG - AI Uncertainty article data after enrichment: {article_data}")
                else:
                    logger.info(f"API NO ENRICHMENT DATA for {article_data['uri']}")

                    # Special debugging for the Tom's Hardware article
                    if "tomshardware.com" in article_data["url"] and "stargate" in article_data["url"]:
                        logger.info(f"STARGATE ARTICLE DEBUG: No enrichment found for Stargate article!")
            except Exception as e:
                # If enrichment columns don't exist, that's fine
                logger.debug(f"No enrichment data available for article {article_data['uri']}: {e}")
                pass

            # Append alert to list (outside try/except, inside for loop)
            alerts.append({
                'id': alert_data.get("id", ""),
                'is_read': bool(alert_data.get("is_read", 0)),
                'detected_at': alert_data.get("detected_at", ""),
                'article': article_data,
                'matched_keyword': alert_data.get("matched_keyword", "")
            })

        # Return all alerts (outside for loop)
        return {
            "alerts": alerts
        }
    except Exception as e:
        logger.error(f"Error fetching alerts: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@page_router.get("/keyword-alerts", response_class=HTMLResponse)
async def keyword_alerts_page(request: Request, session=Depends(verify_session), db: Database = Depends(get_database_instance)):
    try:
        # Initialize media bias for article enrichment
        media_bias = MediaBias(db)

        # Check which table structure to use
        use_new_table = db.facade.check_if_keyword_article_matches_table_exists()

        rows = []
        if use_new_table:
            # Get all groups with their alerts and status using new table structure
            rows = db.facade.get_all_groups_with_alerts_and_status_new_table_structure()
        else:
            # Fallback to old table structure
            rows = db.facade.get_all_groups_with_alerts_and_status_old_table_structure()

        groups = []
        for row in rows:
            group_id, name, topic, unread_count, total_count, growth_status = row

            # Debug logging for the discrepancy
            logger.info(f"GROUP DEBUG - Group {group_id} ({topic}): unread_count={unread_count}, total_count={total_count}")

            # Get keywords for this group
            keywords = db.facade.get_keywords_associated_to_group(group_id)

            # Get the most recent unread alerts for this group
            fetched_articles = []
            if use_new_table:
                fetched_articles = db.facade.get_most_recent_unread_alerts_for_group_id_new_table_structure(group_id)
            else:
                fetched_articles = db.facade.get_most_recent_unread_alerts_for_group_id_old_table_structure(group_id)

            alerts = []

            # Debug logging for actual articles fetched
            logger.info(f"GROUP DEBUG - Group {group_id} ({topic}): fetched {len(fetched_articles)} articles (with LIMIT 25)")

            # Let's also count total unread articles without the limit to see the real count
            actual_unread_count = 0
            if use_new_table:
                db.facade.count_total_group_unread_articles_new_table_structure(group_id)
            else:
                db.facade.count_total_group_unread_articles_old_table_structure(group_id)

            logger.info(f"GROUP DEBUG - Group {group_id} ({topic}): actual unread count without limit = {actual_unread_count}")

            logger.info(f"Processing {len(fetched_articles)} articles for group {group_id}")
            for alert in fetched_articles:
                # Extract fields from mapping object
                alert_id = alert['id']
                article_uri = alert['article_uri']
                keyword_ids = alert['keyword_ids']
                matched_keyword = alert['matched_keyword']
                is_read = alert['is_read']
                detected_at = alert['detected_at']
                below_threshold = alert['below_threshold']
                title = alert['title']
                summary = alert['summary']
                uri = alert['uri']
                news_source = alert['news_source']
                publication_date = alert['publication_date']
                topic_alignment_score = alert['topic_alignment_score']
                keyword_relevance_score = alert['keyword_relevance_score']
                confidence_score = alert['confidence_score']
                overall_match_explanation = alert['overall_match_explanation']
                extracted_article_topics = alert['extracted_article_topics']
                extracted_article_keywords = alert['extracted_article_keywords']
                category = alert['category']
                sentiment = alert['sentiment']
                driver_type = alert['driver_type']
                time_to_impact = alert['time_to_impact']
                future_signal = alert['future_signal']
                bias = alert['bias']
                factual_reporting = alert['factual_reporting']
                mbfc_credibility_rating = alert['mbfc_credibility_rating']
                bias_country = alert['bias_country']
                press_freedom = alert['press_freedom']
                media_type = alert['media_type']
                popularity = alert['popularity']
                auto_ingested = alert['auto_ingested']
                ingest_status = alert['ingest_status']
                quality_score = alert['quality_score']
                quality_issues = alert['quality_issues']

                # Get all matched keywords for this article and group
                if keyword_ids:
                    keyword_id_list = [int(kid.strip()) for kid in keyword_ids.split(',') if kid.strip()]
                    if keyword_id_list:
                        placeholders = ','.join(['?'] * len(keyword_id_list))
                        matched_keywords = db.facade.get_all_matched_keywords_for_article_and_group(placeholders, keyword_id_list + [group_id])
                    else:
                        matched_keywords = []
                else:
                    matched_keywords = db.facade.get_all_matched_keywords_for_article_and_group_by_article_url_and_group_id(article_uri, group_id)

                # Check if we already have bias data from the database
                has_db_bias_data = bias or factual_reporting or mbfc_credibility_rating or bias_country

                # Only fetch from media_bias if we don't have it in the database
                bias_data = None
                if not has_db_bias_data:
                    # Try to get media bias data using both source name and URL
                    # First try with the source name as it's more reliable
                    bias_data = media_bias.get_bias_for_source(news_source)

                    # If no match with source name, try with the URL
                    if not bias_data and uri:
                        bias_data = media_bias.get_bias_for_source(uri)

                # Debug: Log if title is missing
                if not title:
                    logger.warning(f"MISSING TITLE: article_uri={article_uri}, uri={uri}, news_source={news_source}")

                article_data = {
                    "url": uri,
                    "uri": article_uri,
                    "title": title,
                    "summary": summary,
                    "source": news_source,
                    "publication_date": publication_date
                }

                # Add enrichment fields directly from the query results
                # Debug log for first article
                if title and "2510.00508" in uri:
                    logger.info(f"DEBUG ARXIV ARTICLE - Raw values from query:")
                    logger.info(f"  category={repr(category)} (type: {type(category).__name__})")
                    logger.info(f"  sentiment={repr(sentiment)} (type: {type(sentiment).__name__})")
                    logger.info(f"  driver_type={repr(driver_type)} (type: {type(driver_type).__name__})")
                    logger.info(f"  time_to_impact={repr(time_to_impact)} (type: {type(time_to_impact).__name__})")

                # Always add enrichment fields (use empty string if None to avoid Jinja issues)
                article_data["category"] = category or ''
                article_data["sentiment"] = sentiment or ''
                article_data["driver_type"] = driver_type or ''
                article_data["time_to_impact"] = time_to_impact or ''
                article_data["future_signal"] = future_signal or ''

                # Add auto-ingest status fields
                article_data["auto_ingested"] = bool(auto_ingested) if auto_ingested is not None else False
                article_data["ingest_status"] = ingest_status or ''
                article_data["quality_score"] = quality_score if quality_score is not None else None
                article_data["quality_issues"] = quality_issues or ''
                article_data["below_threshold"] = bool(below_threshold) if below_threshold is not None else False

                # Add relevance scores directly from query
                if topic_alignment_score is not None:
                    article_data["topic_alignment_score"] = topic_alignment_score
                if keyword_relevance_score is not None:
                    article_data["keyword_relevance_score"] = keyword_relevance_score
                if confidence_score is not None:
                    article_data["confidence_score"] = confidence_score
                if overall_match_explanation:
                    article_data["overall_match_explanation"] = overall_match_explanation

                # Handle extracted topics and keywords (they are JSON strings)
                if extracted_article_topics:
                    try:
                        article_data["extracted_article_topics"] = json.loads(extracted_article_topics)
                    except:
                        article_data["extracted_article_topics"] = []
                else:
                    article_data["extracted_article_topics"] = []

                if extracted_article_keywords:
                    try:
                        article_data["extracted_article_keywords"] = json.loads(extracted_article_keywords)
                    except:
                        article_data["extracted_article_keywords"] = []
                else:
                    article_data["extracted_article_keywords"] = []

                # Debug: Log enriched article data
                if category:
                    logger.info(f"ENRICHED ARTICLE: uri={uri}, title={title}, category={category}, sentiment={sentiment}")

                # Add specific logging for the Tom's Hardware article
                if "tomshardware.com" in uri and "stargate" in uri:
                    logger.info(f"STARGATE ARTICLE DEBUG: uri={uri}")
                    logger.info(f"STARGATE ARTICLE DEBUG: Data with enrichment: {article_data}")

                # Legacy enrichment lookup (kept for compatibility but should not be needed now)
                try:
                    enrichment_row = db.facade.get_article_enrichment_by_article_url(article_uri)
                    if enrichment_row:
                        (enrich_category, enrich_sentiment, enrich_driver_type, enrich_time_to_impact,
                         enrich_topic_alignment_score, enrich_keyword_relevance_score,
                         enrich_confidence_score, enrich_overall_match_explanation,
                         enrich_extracted_article_topics, enrich_extracted_article_keywords) = enrichment_row

                        # Only use these if not already set
                        if enrich_category and not category:
                            article_data["category"] = enrich_category
                        if enrich_sentiment and not sentiment:
                            article_data["sentiment"] = enrich_sentiment
                        if enrich_driver_type and not driver_type:
                            article_data["driver_type"] = enrich_driver_type
                        if enrich_time_to_impact and not time_to_impact:
                            article_data["time_to_impact"] = enrich_time_to_impact

                        # Add relevance data if available
                        if topic_alignment_score is not None:
                            article_data["topic_alignment_score"] = topic_alignment_score
                            logger.debug(f"Added topic_alignment_score: {topic_alignment_score} for {article_uri}")
                        if keyword_relevance_score is not None:
                            article_data["keyword_relevance_score"] = keyword_relevance_score
                            logger.debug(f"Added keyword_relevance_score: {keyword_relevance_score} for {article_uri}")
                        if confidence_score is not None:
                            article_data["confidence_score"] = confidence_score
                        if overall_match_explanation:
                            article_data["overall_match_explanation"] = overall_match_explanation
                        if extracted_article_topics:
                            try:
                                article_data["extracted_article_topics"] = json.loads(extracted_article_topics)
                            except:
                                article_data["extracted_article_topics"] = []
                        if extracted_article_keywords:
                            try:
                                article_data["extracted_article_keywords"] = json.loads(extracted_article_keywords)
                            except:
                                article_data["extracted_article_keywords"] = []

                        # Debug log to verify enrichment is in article_data
                        if "Uncertainty" in article_data["title"]:
                            logger.info(f"TEMPLATE DEBUG - AI Uncertainty article data after enrichment: {article_data}")
                    else:
                        logger.info(f"API NO ENRICHMENT DATA for {article_uri}")

                        # Special debugging for the Tom's Hardware article
                        if "tomshardware.com" in uri and "stargate" in uri:
                            logger.info(f"STARGATE ARTICLE DEBUG: No enrichment found for Stargate article!")
                except Exception as e:
                    # If enrichment columns don't exist, that's fine
                    logger.debug(f"No enrichment data available for article {article_uri}: {e}")
                    pass

                # Add bias data - prefer database values, fallback to bias_data lookup
                if has_db_bias_data:
                    # Use data from database
                    if bias:
                        article_data["bias"] = bias
                    if factual_reporting:
                        article_data["factual_reporting"] = factual_reporting
                    if mbfc_credibility_rating:
                        article_data["mbfc_credibility_rating"] = mbfc_credibility_rating
                    if bias_country:
                        article_data["bias_country"] = bias_country
                    if press_freedom:
                        article_data["press_freedom"] = press_freedom
                    if media_type:
                        article_data["media_type"] = media_type
                    if popularity:
                        article_data["popularity"] = popularity
                elif bias_data:
                    # Fallback to media_bias lookup
                    article_data["bias"] = bias_data.get("bias")
                    article_data["factual_reporting"] = bias_data.get("factual_reporting")
                    article_data["mbfc_credibility_rating"] = bias_data.get("mbfc_credibility_rating")
                    article_data["bias_country"] = bias_data.get("country")
                    article_data["press_freedom"] = bias_data.get("press_freedom")
                    article_data["media_type"] = bias_data.get("media_type")
                    article_data["popularity"] = bias_data.get("popularity")

                # Debug log article_data before adding to alerts
                if title and ("2510.00508" in uri or "5558" in str(alert_id)):
                    logger.info(f"DEBUG ARTICLE {alert_id} - URI: {uri}")
                    logger.info(f"DEBUG ARTICLE {alert_id} - Raw category from query: {repr(category)}")
                    logger.info(f"DEBUG ARTICLE {alert_id} - Final article_data keys: {list(article_data.keys())}")
                    logger.info(f"DEBUG ARTICLE {alert_id} - category in article_data: {'category' in article_data}")
                    if 'category' in article_data:
                        logger.info(f"DEBUG ARTICLE {alert_id} - category value: {repr(article_data['category'])}")

                alerts.append({
                    "id": alert_id,
                    "article": article_data,
                    "matched_keyword": matched_keywords[0] if matched_keywords else None,
                    "matched_keywords": matched_keywords,
                    "is_read": bool(is_read),
                    "detected_at": detected_at
                })

            groups.append({
                "id": group_id,
                "name": name,
                "topic": topic,
                "unread_count": unread_count,
                "total_count": total_count,
                "keywords": keywords,
                "alerts": alerts,
                "growth_status": growth_status
            })

            # Final debug log for this group
            logger.info(f"GROUP FINAL - Group {group_id} '{name}' ({topic}): "
                      f"unread_count={unread_count}, total_count={total_count}, "
                      f"alerts_added={len(alerts)}, actual_unread={actual_unread_count}")

        # Debug: Log all groups being sent to template
        logger.info(f"TEMPLATE DATA - Sending {len(groups)} groups to template:")
        for i, group in enumerate(groups):
            logger.info(f"  Group {i+1}: {group['topic']} - unread_count={group['unread_count']}, alerts={len(group['alerts'])}")

        # Define status colors
        status_colors = {
            "High growth": "danger",
            "Growing": "warning",
            "Stable": "success",
            "Inactive": "secondary",
            "No data": "light"
        }

        # Get current time for next check timer
        current_time = datetime.now().isoformat()

        # Get settings for interval display
        interval_settings = await get_settings(db)
        interval = interval_settings.get('check_interval', 60)
        interval_unit = interval_settings.get('interval_unit', 1)

        # Convert to minutes for display
        if interval_unit == 1:  # minutes
            display_interval = f"{interval} minutes"
        elif interval_unit == 2:  # hours
            display_interval = f"{interval} hours"
        elif interval_unit == 3:  # days
            display_interval = f"{interval} days"
        else:
            display_interval = f"{interval} minutes"

        return templates.TemplateResponse(
            "keyword_alerts.html",
            {
                "request": request,
                "groups": groups,
                "status_colors": status_colors,
                "now": current_time,
                "display_interval": display_interval,
                "is_enabled": interval_settings.get('is_enabled', False),
                "last_check_time": interval_settings.get('last_run_time'),
                "next_check_time": interval_settings.get('next_run_time'),
                "last_error": interval_settings.get('last_error'),
                "session": session,
                "current_page": "gather"
            }
        )

    except Exception as e:
        logger.error(f"Error in keyword_alerts_page: {str(e)}")
        traceback.print_exc()
        return templates.TemplateResponse(
            "keyword_alerts.html",
            {
                "request": request,
                "groups": [],
                "status_colors": {},
                "error": str(e),
                "session": session,
                "current_page": "gather"
            }
        )

@router.get("/settings")
async def get_settings(db=Depends(get_database_instance), session=Depends(verify_session)):
    try:
        # Create keyword_monitor_status table if it doesn't exist
        db.facade.create_keyword_monitor_table_if_not_exists_and_insert_default_value()

        # Debug: Check both tables
        (status_data, settings_data) = db.facade.check_keyword_monitor_status_and_settings_tables()
        logger.debug(f"Status data: {status_data}")
        logger.debug(f"Settings data: {settings_data}")

        # Get accurate keyword count
        total_keywords = db.facade.get_count_of_monitored_keywords()

        # Log the count for debugging
        logger.debug(f"Active keywords count: {total_keywords}")

        # Get settings and status together (including auto-ingest fields)
        settings = db.facade.get_settings_and_status_together()
        logger.debug(f"Settings query result: {settings}")

        if settings:
            # Get providers from facade
            providers_json = db.facade.get_keyword_monitoring_providers()

            # Get auto_regenerate_reports setting
            auto_regenerate_reports = db.facade.get_auto_regenerate_reports_setting()

            response_data = {
                "check_interval": settings[0],
                "interval_unit": settings[1],
                "search_fields": settings[2],
                "language": settings[3],
                "sort_by": settings[4],
                "page_size": settings[5],
                "daily_request_limit": settings[6],
                "is_enabled": settings[7],
                "provider": settings[8],
                "providers": providers_json,  # JSON array of selected providers
                "auto_ingest_enabled": settings[9],
                "min_relevance_threshold": settings[10],
                "quality_control_enabled": settings[11],
                "auto_save_approved_only": settings[12],
                "default_llm_model": settings[13],
                "llm_temperature": settings[14],
                "llm_max_tokens": settings[15],
                "max_articles_per_run": 50,      # Default value (not in query)
                "auto_regenerate_reports": auto_regenerate_reports,
                "requests_today": settings[16],  # Index 16: requests_today from status subquery
                "last_error": settings[17],      # Index 17: last_error from status subquery
                "last_run_time": settings[18],   # Index 18: last_check_time from status subquery
                "next_run_time": None,           # Not calculated yet - can be added later
                "total_keywords": total_keywords
            }
            logger.debug(f"Returning response data: {response_data}")
            return response_data
        else:
            # Return defaults for new users
            return {
                "check_interval": 24,  # 24 hours default
                "interval_unit": 3600,  # Hours (in seconds)
                "search_fields": "title,description,content",
                "language": "en",
                "sort_by": "publishedAt",
                "page_size": 10,
                "daily_request_limit": 100,
                "is_enabled": True,
                "provider": "newsapi",
                "providers": '["newsapi"]',  # Default to newsapi
                "auto_ingest_enabled": True,  # Auto-processing ON by default
                "min_relevance_threshold": 0.0,
                "quality_control_enabled": True,
                "auto_save_approved_only": True,  # Save Approved Only ON by default
                "default_llm_model": None,  # null = use first available model
                "llm_temperature": 0.2,  # Temperature 0.2 default
                "llm_max_tokens": 1000,
                "max_articles_per_run": 50,
                "auto_regenerate_reports": True,  # Auto-regenerate ON by default
                "requests_today": 0,
                "last_error": None,
                "total_keywords": total_keywords
            }
    except Exception as e:
        logger.error(f"Error getting settings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/settings")
async def save_settings(settings: KeywordMonitorSettings, db=Depends(get_database_instance), session=Depends(verify_session)):
    """Save keyword monitor settings"""
    try:
            logger.info(f"Saving keyword monitor settings. Provider: {settings.provider}, Providers: {settings.providers}")

            # Update or insert settings (including auto-ingest settings)
            db.facade.update_or_insert_keyword_monitor_settings((
                settings.check_interval,
                settings.interval_unit,
                settings.search_fields,
                settings.language,
                settings.sort_by,
                settings.page_size,
                settings.daily_request_limit,
                settings.provider,
                settings.auto_ingest_enabled,
                settings.min_relevance_threshold,
                settings.quality_control_enabled,
                settings.auto_save_approved_only,
                settings.default_llm_model,
                settings.llm_temperature,
                settings.llm_max_tokens,
                settings.max_articles_per_run
            ))

            # Save providers array if provided (multi-collector support)
            # ALWAYS save if provided, even if empty (will use default)
            if settings.providers is not None and settings.providers != "":
                logger.info(f"Updating providers to: {settings.providers}")
                db.facade.update_keyword_monitoring_providers(settings.providers)
            else:
                logger.warning(f"No providers provided, keeping existing configuration")

            # Save auto_regenerate_reports setting
            db.facade.update_auto_regenerate_reports_setting(settings.auto_regenerate_reports)

            return {"success": True}
            
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/available-providers")
async def get_available_providers():
    """Get list of configured providers that can be used for keyword monitoring"""
    import os

    available = []

    # Check NewsAPI (matches newsapi_collector.py)
    if os.getenv('PROVIDER_NEWSAPI_API_KEY') or os.getenv('PROVIDER_NEWSAPI_KEY'):
        available.append({
            "id": "newsapi",
            "name": "NewsAPI",
            "description": "100 requests/day",
            "configured": True
        })

    # Check TheNewsAPI (matches thenewsapi_collector.py)
    if os.getenv('PROVIDER_THENEWSAPI_API_KEY') or os.getenv('PROVIDER_THENEWSAPI_KEY'):
        available.append({
            "id": "thenewsapi",
            "name": "TheNewsAPI",
            "description": "100 requests/day",
            "configured": True
        })

    # Check NewsData.io (matches newsdata_collector.py)
    if os.getenv('PROVIDER_NEWSDATA_API_KEY') or os.getenv('NEWSDATA_API_KEY'):
        available.append({
            "id": "newsdata",
            "name": "NewsData.io",
            "description": "200 requests/day",
            "configured": True
        })

    # Check NewsFirehose (matches newsfirehose_collector.py)
    if os.getenv('PROVIDER_NEWSFIREHOSE_API_KEY') or os.getenv('NEWSFIREHOSE_API_KEY'):
        available.append({
            "id": "newsfirehose",
            "name": "NewsFirehose",
            "description": "Unified news aggregation",
            "configured": True
        })

    # Check Opoint (matches opoint_collector.py)
    if os.getenv('PROVIDER_OPOINT_API_KEY') or os.getenv('OPOINT_API_KEY'):
        available.append({
            "id": "opoint",
            "name": "Opoint",
            "description": "Media intelligence + entity/topic enrichment",
            "configured": True
        })

    # Check Bluesky (matches bluesky_collector.py)
    if os.getenv('PROVIDER_BLUESKY_USERNAME') and os.getenv('PROVIDER_BLUESKY_PASSWORD'):
        available.append({
            "id": "bluesky",
            "name": "Bluesky",
            "description": "Social media posts",
            "configured": True
        })

    # Semantic Scholar always available (API key optional for better rate limits)
    available.append({
        "id": "semantic_scholar",
        "name": "Semantic Scholar",
        "description": "200M+ academic papers (all disciplines)",
        "configured": True
    })

    # ArXiv always available (no API key required)
    available.append({
        "id": "arxiv",
        "name": "ArXiv",
        "description": "Academic papers (STEM only)",
        "configured": True
    })

    # Reddit — free RSS, no credentials required
    available.append({
        "id": "reddit",
        "name": "Reddit",
        "description": "Community discussion & sentiment (RSS, no key)",
        "configured": True
    })

    # Xpoz — paid social search (credit pool shared across tenants); platform
    # subset is selectable per group to control credit burn
    from app.collectors.xpoz_collector import _ALL_PLATFORMS as _XPOZ_PLATFORMS
    available.append({
        "id": "xpoz",
        "name": "Xpoz Social",
        "description": "Twitter/Reddit/Instagram/TikTok search (paid credits)",
        "configured": bool(os.getenv('XPOZ_API_KEY') or os.getenv('PROVIDER_XPOZ_API_KEY')),
        "platform_options": list(_XPOZ_PLATFORMS),
    })

    return {"providers": available}

@router.get("/trends")
async def get_trends(db=Depends(get_database_instance), session=Depends(verify_session)):
    try:
        # Get data for the last 7 days
        results = db.facade.get_trends()

        # Process results into the required format
        trends = {}
        for row in results:
            group_id, group_name, date, count = row
            if group_id not in trends:
                trends[group_id] = {
                    'id': group_id,
                    'name': group_name,
                    'dates': [],
                    'counts': []
                }
            trends[group_id]['dates'].append(date)
            trends[group_id]['counts'].append(count)

        return trends
            
    except Exception as e:
        logger.error(f"Error getting trends: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/toggle-polling")
async def toggle_polling(toggle: PollingToggle, db=Depends(get_database_instance), session=Depends(verify_session_api)):
    try:
        db.facade.toggle_polling(toggle)
        return {"status": "success", "enabled": toggle.enabled}
            
    except Exception as e:
        logger.error(f"Error toggling polling: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export-alerts")
async def export_alerts(db=Depends(get_database_instance), session=Depends(verify_session_api)):
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow([
            'Group Name',
            'Topic',
            'Article Title',
            'Source',
            'URL',
            'Publication Date',
            'Matched Keywords',
            'Detection Time'
        ])
        
        # Check if the keyword_article_matches table exists
        use_new_table = db.facade.check_if_keyword_article_matches_table_exists()

        if use_new_table:
            # Use the new table structure
            rows = db.facade.get_all_alerts_for_export_new_table_structure()
        else:
            # Use the original table structure
            rows = db.facade.get_all_alerts_for_export_old_table_structure()

        # Write data
        for row in rows:
            writer.writerow([
                row[0],  # group_name
                row[1],  # topic
                row[2],  # title
                row[3],  # news_source
                row[4],  # uri
                row[5],  # publication_date
                row[6],  # matched_keywords
                row[7]   # detected_at
            ])

        # Prepare the output
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                'Content-Disposition': f'attachment; filename=keyword_alerts_{datetime.now().strftime("%Y-%m-%d")}.csv'
            }
        )
    except Exception as e:
        logger.error(f"Error exporting alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export-group-alerts")
async def export_group_alerts(
    topic: str,
    group_id: int,
    db=Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Export alerts for a specific group"""
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow([
            'Group Name',
            'Topic',
            'Article Title',
            'Source',
            'URL',
            'Publication Date',
            'Matched Keywords',
            'Detection Time',
            'Is Read'
        ])
        
        # Check if the keyword_article_matches table exists
        # Check if the keyword_article_matches table exists
        use_new_table = db.facade.check_if_keyword_article_matches_table_exists()

        if use_new_table:
            # Use the new table structure
            rows = db.facade.get_all_group_and_topic_alerts_for_export_new_table_structure(group_id, topic)
        else:
            # Use the original table structure
            rows = db.facade.get_all_group_and_topic_alerts_for_export_old_table_structure(group_id, topic)

        # Write data
        for row in rows:
            writer.writerow([
                row[0],  # group_name
                row[1],  # topic
                row[2],  # title
                row[3],  # news_source
                row[4],  # uri
                row[5],  # publication_date
                row[6],  # matched_keywords
                row[7],  # detected_at
                'Yes' if row[8] else 'No'  # is_read
            ])

        # Prepare the output
        output.seek(0)
        
        # Create filename with topic and group info
        safe_topic = topic.replace(' ', '_').replace('/', '_')
        filename = f"{safe_topic}_group_{group_id}_alerts_{datetime.now().strftime('%Y-%m-%d')}.csv"
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                'Content-Disposition': f'attachment; filename={filename}'
            }
        )
    except Exception as e:
        logger.error(f"Error exporting group alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def save_keyword_alert(db: Database, article_data: dict):
    db.facade.save_keyword_alert(article_data)

@router.post("/alerts/{alert_id}/unread")
async def mark_alert_unread(alert_id: int, db: Database = Depends(get_database_instance), session=Depends(verify_session)):
    try:
        # Check if the alert is in the keyword_article_matches table
        use_new_table = db.facade.check_if_keyword_article_matches_table_exists()

        if use_new_table:
            # Check if the alert ID is in the new table
            if db.facade.check_if_alert_id_exists_in_new_table_structure(alert_id):
                # Update the new table
                db.facade.mark_alert_as_read_or_unread_in_new_table(alert_id, 0)
            else:
                # Update the old table
                db.facade.mark_alert_as_read_or_unread_in_old_table(alert_id, 0)
        else:
            # Update the old table
            db.facade.mark_alert_as_read_in_old_table(alert_id)

        return {"success": True}
    except Exception as e:
        logger.error(f"Error in mark_alert_unread: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts/{topic}")
async def get_group_alerts(
    topic: str,
    group_id: int,
    show_read: bool = False,
    skip_media_bias: bool = False,
    page: int = 1,
    page_size: int = 25,
    status: str = "all",
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    
    """Get alerts for a specific keyword group with pagination and status filtering.
    
    Args:
        status: Filter by article status:
            - "all": Return all articles (default)
            - "new": Return only new/unprocessed articles (category IS NULL OR category = ''
            - "added": Return only enriched/processed articles (category IS NOT NULL AND category != '')
    """
    try:
        # Initialize variables for error handling
        group_name = None
        total_pages = 1
        has_next = False
        has_prev = False

        # Validate pagination parameters
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 50
        if page_size > 200:  # Maximum page size to prevent performance issues
            page_size = 200
            
        offset = (page - 1) * page_size
        
        # Initialize media bias for article enrichment only if not skipping
        media_bias = MediaBias(db) if not skip_media_bias else None
        
        # Determine if we're using the new table structure
        use_new_table = db.facade.check_if_keyword_article_matches_table_exists()

        if use_new_table:
            # Using new structure (keyword_article_matches table) with pagination
            alert_results = db.facade.get_alerts_by_group_id_from_new_table_structure(status, show_read, group_id, page_size, offset)
        else:
            # Fallback to old structure (keyword_alerts table) with pagination
            alert_results = db.facade.get_alerts_by_group_id_from_old_table_structure(status, show_read, group_id, page_size, offset)

        # Get unread count for this group
        if use_new_table:
            unread_count = db.facade.count_unread_articles_by_group_id_from_new_table_structure(group_id)
        else:
            unread_count = db.facade.count_unread_articles_by_group_id_from_old_table_structure(group_id)

        # Get total count for this group (respecting status filter)
        if use_new_table:
            total_count = db.facade.count_total_articles_by_group_id_from_new_table_structure(group_id, status)
        else:
            total_count = db.facade.count_total_articles_by_group_id_from_old_table_structure(group_id, status)

        # Get group name early so it's available in error handling
        group_name = db.facade.get_group_name(group_id)

        alerts = []
        index = 0
        for alert in alert_results:
            # Extract fields from mapping object
            alert_id = alert['id']
            article_uri = alert['article_uri']
            keyword_ids = alert['keyword_ids']
            matched_keyword = alert['matched_keyword']
            is_read = alert['is_read']
            detected_at = alert['detected_at']
            below_threshold = alert.get('below_threshold', False)
            title = alert['title']
            summary = alert['summary']
            uri = alert['uri']
            news_source = alert['news_source']
            publication_date = alert['publication_date']
            topic_alignment_score = alert['topic_alignment_score']
            keyword_relevance_score = alert['keyword_relevance_score']
            confidence_score = alert['confidence_score']
            overall_match_explanation = alert['overall_match_explanation']
            extracted_article_topics = alert['extracted_article_topics']
            extracted_article_keywords = alert['extracted_article_keywords']
            category = alert['category']
            sentiment = alert['sentiment']
            driver_type = alert['driver_type']
            time_to_impact = alert['time_to_impact']
            future_signal = alert['future_signal']
            bias = alert['bias']
            factual_reporting = alert['factual_reporting']
            mbfc_credibility_rating = alert['mbfc_credibility_rating']
            bias_country = alert['bias_country']
            press_freedom = alert['press_freedom']
            media_type = alert['media_type']
            popularity = alert['popularity']
            auto_ingested = alert['auto_ingested']
            ingest_status = alert['ingest_status']
            quality_score = alert['quality_score']
            quality_issues = alert['quality_issues']

            if use_new_table:
                # For new table, keyword_ids is a comma-separated string
                if keyword_ids:
                    keyword_id_list = [int(kid.strip()) for kid in keyword_ids.split(',') if kid.strip()]
                    if keyword_id_list:
                        placeholders = ','.join(['?'] * len(keyword_id_list))
                        matched_keywords = db.facade.get_all_matched_keywords_for_article_and_group(placeholders, keyword_id_list + [group_id])
                    else:
                        matched_keywords = []
                else:
                    matched_keywords = []
            else:
                matched_keywords = db.facade.get_all_matched_keywords_for_article_and_group_by_article_url_and_group_id(article_uri, group_id)

            # Check if we already have media bias data from the database
            has_db_bias_data = bias or factual_reporting or mbfc_credibility_rating or bias_country

            # Try to get media bias data only if not skipping and not already in database
            bias_data = None

            if not skip_media_bias and media_bias and news_source and not has_db_bias_data:
                # First try with the original source name
                bias_data = media_bias.get_bias_for_source(news_source)

                # If no match, try a few common variations (reduced from many)
                if not bias_data:
                    source_lower = news_source.lower()
                    variations = [
                        source_lower,
                        source_lower.replace(" ", ""),
                        source_lower + ".com"
                    ]

                    for variation in variations:
                        bias_data = media_bias.get_bias_for_source(variation)
                        if bias_data:
                            break

                # If no match with source variations, try with the URL
                if not bias_data and uri:
                    bias_data = media_bias.get_bias_for_source(uri)

                # If we found bias data, ensure the source is enabled
                if bias_data and 'enabled' in bias_data and bias_data['enabled'] == 0:
                    try:
                        db.facade.update_media_bias(bias_data.get('source'))
                        # Update the bias data to show it's now enabled
                        bias_data['enabled'] = 1
                    except Exception as e:
                        logger.error(f"Error enabling media bias source {bias_data.get('source')}: {e}")

            article_data = {
                "url": uri,
                "uri": article_uri,
                "title": title,
                "summary": summary,
                "source": news_source,
                "publication_date": publication_date,
                "topic_alignment_score": topic_alignment_score,
                "keyword_relevance_score": keyword_relevance_score,
                "confidence_score": confidence_score,
                "overall_match_explanation": overall_match_explanation,
                "extracted_article_topics": extracted_article_topics,
                "extracted_article_keywords": extracted_article_keywords,
                "category": category,
                "sentiment": sentiment,
                "driver_type": driver_type,
                "time_to_impact": time_to_impact,
                "future_signal": future_signal,
                "bias": bias,
                "factual_reporting": factual_reporting,
                "mbfc_credibility_rating": mbfc_credibility_rating,
                "bias_country": bias_country,
                "press_freedom": press_freedom,
                "media_type": media_type,
                "popularity": popularity,
                "auto_ingested": bool(auto_ingested) if auto_ingested is not None else False,
                "ingest_status": ingest_status,
                "quality_score": quality_score,
                "quality_issues": quality_issues,
                "below_threshold": bool(below_threshold) if below_threshold is not None else False
            }

            # Parse JSON fields for extracted topics and keywords
            if extracted_article_topics:
                try:
                    article_data["extracted_article_topics"] = json.loads(extracted_article_topics)
                except:
                    article_data["extracted_article_topics"] = []
            else:
                article_data["extracted_article_topics"] = []

            if extracted_article_keywords:
                try:
                    article_data["extracted_article_keywords"] = json.loads(extracted_article_keywords)
                except:
                    article_data["extracted_article_keywords"] = []
            else:
                article_data["extracted_article_keywords"] = []

            # Log relevance data if available
            if topic_alignment_score is not None or keyword_relevance_score is not None:
                logger.debug(f"Relevance data for {article_uri}: Topic: {topic_alignment_score}, Keywords: {keyword_relevance_score}")

            # Override with dynamic bias data if found and database doesn't have it
            if bias_data and not has_db_bias_data:
                article_data["bias"] = bias_data.get("bias")
                article_data["factual_reporting"] = bias_data.get("factual_reporting")
                article_data["mbfc_credibility_rating"] = bias_data.get("mbfc_credibility_rating")
                article_data["bias_country"] = bias_data.get("country")
                article_data["press_freedom"] = bias_data.get("press_freedom")
                article_data["media_type"] = bias_data.get("media_type")
                article_data["popularity"] = bias_data.get("popularity")

            alerts.append({
                "id": alert_id,
                "article": article_data,
                "matched_keyword": matched_keywords[0] if matched_keywords else None,
                "matched_keywords": matched_keywords,
                "is_read": bool(is_read),
                "detected_at": detected_at
            })

        # Calculate pagination info
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        has_next = page < total_pages
        has_prev = page > 1
            
        # Return the response data
        # TODO: REVIEW THIS CHANGE AS THE PAGE IS BROKEN: http://localhost:10000/keyword-alerts
        # TODO: REVIEW THIS CHANGE AS THE PAGE IS BROKEN: http://localhost:10000/keyword-alerts
        # TODO: REVIEW THIS CHANGE AS THE PAGE IS BROKEN: http://localhost:10000/keyword-alerts
        # TODO: REVIEW THIS CHANGE AS THE PAGE IS BROKEN: http://localhost:10000/keyword-alerts
        return {
            "topic": topic,
            "group_id": group_id,
            "group_name": group_name,
            "alerts": alerts,
            "unread_count": unread_count,
            "total_count": total_count,
            "status_filter": status,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            }
        }
            
    except Exception as e:
        logger.error(f"Error getting group alerts: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/articles/by-topic/{topic_name}")
async def delete_articles_by_topic(topic_name: str, db=Depends(get_database_instance), session=Depends(verify_session)):
    """Delete all articles associated with a specific topic and their related data"""
    try:
        # Check if the keyword_article_matches table exists
        use_new_table = db.facade.check_if_keyword_article_matches_table_exists()

        alerts_deleted = 0
        articles_deleted = 0

        # First find relevant article URIs
        article_uris = []

        # From news_search_results
        article_uris.extend([row['article_uri'] for row in db.facade.get_article_urls_from_news_search_results_by_topic(topic_name)])

        # From paper_search_results
        article_uris.extend([row['article_uri'] for row in db.facade.get_article_urls_from_paper_search_results_by_topic(topic_name)])

        # Direct topic reference if the column exists
        has_topic_column = db.facade.check_if_articles_table_has_topic_column()

        if has_topic_column:
            article_uris.extend([row['uri'] for row in db.facade.article_urls_by_topic(topic_name)])

        # Remove duplicates
        article_uris = list(set(article_uris))

        if article_uris:
            # Delete related keyword alerts first
            if use_new_table:
                for uri in article_uris:
                    alerts_deleted += db.facade.delete_article_matches_by_url(uri)
            else:
                for uri in article_uris:
                    alerts_deleted += db.facade.delete_keyword_alerts_by_url(uri)

            # Delete news_search_results
            db.facade.delete_news_search_results_by_topic(topic_name)

            # Delete paper_search_results
            db.facade.delete_paper_search_results_by_topic(topic_name)

            # Delete articles
            for uri in article_uris:
                articles_deleted_count = db.facade.delete_article_by_url(uri)
                if articles_deleted_count > 0:
                    articles_deleted += articles_deleted_count

            return {
                "success": True, 
                "articles_deleted": articles_deleted,
                "alerts_deleted": alerts_deleted
            }
    except Exception as e:
        logging.error(f"Error deleting articles for topic {topic_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/bluesky-posts")
async def get_bluesky_posts(
    query: str,
    topic: str,
    count: int = 10,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Fetch Bluesky posts for a given query and topic."""
    try:
        # Log what we're receiving in the request
        logger.debug(f"Bluesky posts request: query='{query}', topic='{topic}', count={count}")
        
        # Import the collector here to avoid circular imports
        from app.collectors.bluesky_collector import BlueskyCollector
        
        try:
            bluesky_collector = BlueskyCollector()
            posts = await bluesky_collector.search_articles(
                query=query,
                topic=topic,
                max_results=count
            )
            
            # Log the raw data for debugging
            logger.debug(f"Bluesky returned {len(posts)} posts")
            
            # Format the posts for display with safer access to fields
            formatted_posts = []
            for post in posts:
                try:
                    # Create a post with defaults for all required fields
                    formatted_post = {
                        "title": "Untitled Post",
                        "date": "",
                        "source": "Bluesky",
                        "summary": "No content available",
                        "url": "#",
                        "author": "Unknown",
                        "image_url": None
                    }
                    
                    # Safely update each field if available
                    if post.get('title'):
                        formatted_post["title"] = post.get('title')
                        
                    if post.get('published_date'):
                        formatted_post["date"] = post.get('published_date')
                        
                    if post.get('summary'):
                        formatted_post["summary"] = post.get('summary')
                        
                    if post.get('url'):
                        formatted_post["url"] = post.get('url')
                    
                    # Handle authors safely
                    authors = post.get('authors', [])
                    if authors and len(authors) > 0:
                        formatted_post["author"] = authors[0]
                    
                    # Handle images safely
                    raw_data = post.get('raw_data', {})
                    images = raw_data.get('images', [])
                    if images and len(images) > 0 and isinstance(images[0], dict):
                        url = images[0].get('url')
                        if url:
                            formatted_post["image_url"] = url
                    
                    formatted_posts.append(formatted_post)
                except Exception as post_error:
                    # Log any errors processing individual posts but continue
                    logger.error(f"Error formatting Bluesky post: {str(post_error)}")
                    continue
            
            # Return the posts we were able to process
            return JSONResponse(content=formatted_posts)
        
        except ValueError as e:
            if "credentials not configured" in str(e):
                logger.warning("Bluesky credentials not configured - returning empty results")
                return JSONResponse(content=[])
            else:
                logger.error(f"Bluesky collector error: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error with Bluesky collector: {str(e)}")
                
    except Exception as e:
        logger.error(f"Error fetching Bluesky posts: {str(e)}")
        logger.exception("Full exception details:")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clean-orphaned-topics")
async def clean_orphaned_topics(db=Depends(get_database_instance), session=Depends(verify_session)):
    """Find and clean up orphaned topic data by comparing keyword groups against the main topics list"""
    try:
        # Get active topics list from config
        try:
            config = load_config()
            active_topics = set(topic["name"] for topic in config.get("topics", []))
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            active_topics = set()

        # Check if keyword_groups table exists
        if not db.facade.check_if_keyword_groups_table_exists():
            return {
                "status": "success",
                "message": "No keyword_groups table found",
                "orphaned_topics": []
            }

        # Get all topics referenced in keyword groups
        try:
            keyword_topics = db.facade.get_all_topics_referenced_in_keyword_groups()
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Database error: {str(e)}")
            return {
                "status": "error",
                "message": f"Database error: {str(e)}",
                "orphaned_topics": []
            }

        # Find orphaned topics (in keyword_groups but not in active topics)
        orphaned_topics = keyword_topics - active_topics

        if not orphaned_topics:
            return {
                "status": "success",
                "message": "No orphaned topics found",
                "orphaned_topics": []
            }

        # Clean up each orphaned topic
        cleanup_results = {}
        for topic in orphaned_topics:
            # Clean up keyword groups
            try:
                groups_result = await delete_groups_by_topic(topic, db)
                cleanup_results[topic] = {
                    "groups_deleted": groups_result.get("groups_deleted", 0),
                    "keywords_deleted": groups_result.get("keywords_deleted", 0),
                    "alerts_deleted": groups_result.get("alerts_deleted", 0)
                }
            except Exception as e:
                logger.error(f"Error cleaning up orphaned topic {topic}: {str(e)}")
                cleanup_results[topic] = {"error": str(e)}

        return {
            "status": "success",
            "message": f"Cleaned up {len(orphaned_topics)} orphaned topics",
            "orphaned_topics": list(orphaned_topics),
            "cleanup_results": cleanup_results
        }
            
    except Exception as e:
        logger.error(f"Error cleaning orphaned topics: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clean-orphaned-articles")
async def clean_orphaned_articles(db=Depends(get_database_instance), session=Depends(verify_session)):
    """Find and clean up orphaned articles that are no longer associated with any topic"""
    try:
        try:
            config = load_config()
            active_topics = set(topic["name"] for topic in config.get("topics", []))
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            active_topics = set()

        # Check if articles table exists
        if not db.facade.check_if_articles_table_exists():
            return {
                "status": "success",
                "message": "No articles table found",
                "orphaned_count": 0
            }

        # Get all article URIs that might be orphaned
        orphaned_article_uris = set()

        # Check if articles table has a topic column
        try:
            has_topic_column = db.facade.check_if_articles_table_has_topic_column()

            # First, check direct topic references if the column exists
            if has_topic_column:
                try:
                    for row in db.facade.get_urls_and_topics_from_articles():
                        uri = row['uri']
                        topic = row['topic']
                        if topic not in active_topics:
                            orphaned_article_uris.add(uri)
                except (OperationalError, DatabaseError) as e:
                    logger.error(f"Error querying articles table: {str(e)}")
        except Exception as e:
            logger.error(f"Error checking articles schema: {str(e)}")

        # Check if news_search_results table exists
        if db.facade.check_if_news_search_results_table_exists():
            try:
                for row in db.facade.get_urls_and_topics_from_news_search_results():
                    uri = row['article_uri']
                    topic = row['topic']
                    if topic not in active_topics:
                        orphaned_article_uris.add(uri)
            except (OperationalError, DatabaseError) as e:
                logger.error(f"Error querying news_search_results: {str(e)}")

        # Check if paper_search_results table exists
        if db.facade.check_if_paper_search_results_table_exists():
            try:
                for row in db.facade.get_urls_and_topics_from_paper_search_results():
                    uri = row['article_uri']
                    topic = row['topic']
                    if topic not in active_topics:
                        orphaned_article_uris.add(uri)
            except (OperationalError, DatabaseError) as e:
                logger.error(f"Error querying paper_search_results: {str(e)}")

        # Now check for articles that are not in any search results
        try:
            has_news_results = False
            has_paper_results = False

            # Check if search result tables exist
            has_news_results = db.facade.check_if_news_search_results_table_exists()

            has_paper_results = db.facade.check_if_paper_search_results_table_exists()

            if has_news_results or has_paper_results:
                orphaned_article_uris.update(db.facade.get_orphaned_urls_from_news_results_and_or_paper_results(has_news_results, has_paper_results))
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Error checking articles without search results: {str(e)}")

        if not orphaned_article_uris:
            return {
                "status": "success",
                "message": "No orphaned articles found",
                "orphaned_count": 0
            }

        # Clean up the orphaned articles
        alerts_deleted = 0
        articles_deleted = 0

        # Check if keyword_article_matches table exists
        use_new_table = db.facade.check_if_keyword_article_matches_table_exists()

        # Process articles in smaller batches to avoid SQL parameter limits
        batch_size = 100
        article_batches = [list(orphaned_article_uris)[i:i+batch_size]
                           for i in range(0, len(orphaned_article_uris), batch_size)]

        # Delete associated alerts first
        for batch in article_batches:
            try:
                for uri in batch:
                    if use_new_table:
                        alerts_deleted += db.facade.delete_keyword_article_matches_from_new_table_structure_by_url(uri)
                    else:
                        alerts_deleted += db.facade.delete_keyword_article_matches_from_old_table_structure_by_url(uri)
            except (OperationalError, DatabaseError) as e:
                logger.error(f"Error deleting alerts: {str(e)}")

        # Delete from search results tables
        for batch in article_batches:
            try:
                placeholders = ','.join(['?'] * len(batch))

                # Check if tables exist before attempting delete
                if db.facade.check_if_news_search_results_table_exists():
                    db.facade.delete_news_search_results_by_article_urls(placeholders, batch)

                if db.facade.check_if_paper_search_results_table_exists():
                    db.facade.delete_paper_search_results_by_article_urls(placeholders, batch)
            except (OperationalError, DatabaseError) as e:
                logger.error(f"Error deleting search results: {str(e)}")

        # Finally delete the articles
        for batch in article_batches:
            try:
                placeholders = ','.join(['?'] * len(batch))
                articles_deleted += db.facade.delete_articles_by_article_urls(placeholders, batch)
            except (OperationalError, DatabaseError) as e:
                logger.error(f"Error deleting articles: {str(e)}")

        return {
            "status": "success",
            "message": f"Cleaned up {articles_deleted} orphaned articles",
            "orphaned_count": articles_deleted,
            "alerts_deleted": alerts_deleted
        }
            
    except Exception as e:
        logger.error(f"Error cleaning orphaned articles: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clean-all-orphaned")
async def clean_all_orphaned(db=Depends(get_database_instance), session=Depends(verify_session)):
    """Clean up all orphaned data - both topics and articles in one operation"""
    try:
        topics_result = None
        articles_result = None
        has_errors = False
        error_messages = []

        # First clean orphaned topics
        try:
            topics_result = await clean_orphaned_topics(db, session)
            logger.info(f"Completed orphaned topics cleanup: {topics_result}")
            if topics_result.get("status") == "error":
                has_errors = True
                error_messages.append(f"Topics cleanup error: {topics_result.get('message', 'Unknown error')}")
        except Exception as e:
            has_errors = True
            error_msg = f"Error cleaning up orphaned topics: {str(e)}"
            error_messages.append(error_msg)
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            topics_result = {
                "status": "error",
                "message": error_msg,
                "orphaned_topics": []
            }

        # Then clean orphaned articles
        try:
            articles_result = await clean_orphaned_articles(db, session)
            logger.info(f"Completed orphaned articles cleanup: {articles_result}")
            if articles_result.get("status") == "error":
                has_errors = True
                error_messages.append(f"Articles cleanup error: {articles_result.get('message', 'Unknown error')}")
        except Exception as e:
            has_errors = True
            error_msg = f"Error cleaning up orphaned articles: {str(e)}"
            error_messages.append(error_msg)
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            articles_result = {
                "status": "error",
                "message": error_msg,
                "orphaned_count": 0,
                "alerts_deleted": 0
            }

        # Return appropriate status based on whether errors occurred
        if has_errors:
            return {
                "status": "partial" if (topics_result or articles_result) else "error",
                "message": "; ".join(error_messages),
                "topics_result": topics_result,
                "articles_result": articles_result
            }

        return {
            "status": "success",
            "topics_result": topics_result,
            "articles_result": articles_result
        }
    except Exception as e:
        logger.error(f"Error cleaning all orphaned data: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_keyword_monitor_status(db=Depends(get_database_instance), session=Depends(verify_session_api)):
    """Get the status of the keyword monitoring background task"""
    try:
        # Get status from the background task
        task_status = get_task_status()
        
        # Get settings from the database
        # Get monitor settings
        settings = db.facade.get_monitor_settings()

        # Get keyword count
        keyword_count = db.facade.get_total_number_of_keywords()

        # Get request count for today
        status_row =  db.facade.get_request_count_for_today()
            
        # Format response
        response = {
            "background_task": task_status,
            "settings": {
                "check_interval": settings[0] if settings else 15,
                "interval_unit": settings[1] if settings else 60,
                "is_enabled": settings[2] if settings else True,
                "search_date_range": settings[3] if settings else 7,
                "daily_request_limit": settings[4] if settings else 100,
                "display_interval": format_interval(
                    settings[0] * settings[1] if settings else 900
                ) if settings else "15 minutes"
            },
            "keywords": {
                "count": keyword_count
            },
            "api_usage": {
                "requests_today": status_row[0] if status_row else 0,
                "last_reset_date": status_row[1] if status_row else None,
                "limit": settings[4] if settings else 100
            }
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting keyword monitor status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
        
def format_interval(seconds):
    """Format interval in seconds to a human-readable string"""
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    else:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"

class RelevanceAnalysisRequest(BaseModel):
    article_uris: List[str]
    model_name: str
    topic: str
    group_id: Optional[int] = None  # Add group_id to get keywords

@router.post("/analyze-relevance")
async def analyze_relevance(
    request: RelevanceAnalysisRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Analyze relevance for selected articles using the specified LLM model."""
    try:
        logger.info(f"Starting relevance analysis for {len(request.article_uris)} articles using model: {request.model_name}")
        
        # Get monitoring keywords from the group if group_id is provided
        keywords_str = ""
        if request.group_id:
            keywords = db.facade.get_keywords_associated_to_group_ordered_by_keyword(request.group_id)
            keywords_str = ", ".join(keywords)
            logger.info(f"Found {len(keywords)} monitoring keywords for group {request.group_id}: {keywords_str}")
        
        # Initialize the relevance calculator with the specified model
        try:
            relevance_calculator = RelevanceCalculator(request.model_name)
        except RelevanceCalculatorError as e:
            logger.error(f"Failed to initialize relevance calculator: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Failed to initialize AI model: {str(e)}")
        
        # Fetch articles from database
        articles = []

        for uri in request.article_uris:
            article_row = db.facade.get_articles_by_url(uri)

            if not article_row:
                logger.warning(f"Article not found in database: {uri}")
                continue

            article = dict(article_row)

            # Try to get raw content if available
            raw_row = db.facade.get_raw_articles_markdown_by_url(uri)

            # Use raw content if available, otherwise fall back to summary
            content = ""
            if raw_row and raw_row[0]:
                content = raw_row[0]
            elif article.get('summary'):
                content = article['summary']
            elif article.get('title'):
                content = article['title']

            articles.append({
                'uri': article['uri'],
                'title': article.get('title', ''),
                'source': article.get('news_source', ''),
                'content': content
            })
        
        if not articles:
            raise HTTPException(status_code=404, detail="No articles found for the provided URIs")
        
        # Perform relevance analysis
        try:
            analyzed_articles = relevance_calculator.analyze_articles_batch(
                articles=articles,
                topic=request.topic,
                keywords=keywords_str
            )
        except RelevanceCalculatorError as e:
            logger.error(f"Relevance analysis failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Relevance analysis failed: {str(e)}")
        
        # Save results to database
        updated_count = 0

        for analyzed_article in analyzed_articles:
            try:
                # Convert lists to JSON strings for storage
                extracted_topics = json.dumps(analyzed_article.get('extracted_article_topics', []))
                extracted_keywords = json.dumps(analyzed_article.get('extracted_article_keywords', []))

                updated_article_count = db.facade.update_article_by_url((
                    analyzed_article.get('topic_alignment_score', 0.0),
                    analyzed_article.get('keyword_relevance_score', 0.0),
                    analyzed_article.get('confidence_score', 0.0),
                    analyzed_article.get('overall_match_explanation', ''),
                    extracted_topics,
                    extracted_keywords,
                    analyzed_article['uri']
                ))

                if updated_article_count > 0:
                    updated_count += 1
                    logger.info(f"✅ Successfully updated article '{analyzed_article.get('title', 'Unknown')[:50]}...' - "
                               f"Topic: {analyzed_article.get('topic_alignment_score', 0.0):.2f}, "
                               f"Keywords: {analyzed_article.get('keyword_relevance_score', 0.0):.2f}, "
                               f"Confidence: {analyzed_article.get('confidence_score', 0.0):.2f}")
                else:
                    logger.warning(f"⚠️ No rows updated for article {analyzed_article['uri']}")

            except Exception as e:
                logger.error(f"Failed to save relevance data for article {analyzed_article['uri']}: {str(e)}")
                continue
        
        logger.info(f"✅ Relevance analysis completed successfully! "
                   f"Analyzed: {len(analyzed_articles)} articles, "
                   f"Updated: {updated_count} records in database.")
        
        return {
            "success": True,
            "analyzed_count": len(analyzed_articles),
            "updated_count": updated_count,
            "message": f"Successfully analyzed {len(analyzed_articles)} articles and updated {updated_count} records."
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in relevance analysis: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

class ContentReviewRequest(BaseModel):
    article_title: str
    article_summary: str
    article_source: str
    model_name: str
    article_url: Optional[str] = None

@router.post("/review-content")
async def review_content(
    request: ContentReviewRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Review article content for quality issues using LLM to detect unwanted content like cookie notices, paywalls, etc."""
    try:
        logger.info(f"Starting LLM content review for article: {request.article_title[:50]}... using model: {request.model_name}")
        
        # Initialize the AI model
        try:
            ai_model = LiteLLMModel.get_instance(request.model_name)
        except Exception as e:
            logger.error(f"Failed to initialize AI model {request.model_name}: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Failed to initialize AI model: {str(e)}")
        
        # Create the prompt for content quality review
        system_prompt = """You are a content quality reviewer. Your job is to analyze scraped article content and identify potential issues that would make the content unsuitable for automatic database insertion.

Key issues to detect:
1. Cookie consent notices (e.g., "This site uses cookies", "Accept cookies", "Cookie policy")
2. Paywall content (e.g., "Subscribe to continue reading", "Premium content", "Sign up for full access")
3. Navigation/menu content (e.g., "Home | About | Contact", navigation menus)
4. Error pages (e.g., "Page not found", "403 Forbidden", "Server error")
5. Incomplete/truncated content (e.g., content ending mid-sentence, "..." at the end)
6. Placeholder text (e.g., "Lorem ipsum", placeholder content)
7. GDPR/privacy notices (e.g., "We value your privacy", "Privacy policy")
8. Social media sharing buttons/text (e.g., "Share on Facebook", "Follow us")
9. Advertisement content (e.g., "Advertisement", "Sponsored content")
10. Subscription prompts (e.g., "Join our newsletter", "Get our app")

IMPORTANT: You must respond with ONLY a valid JSON object. Do not include any text before or after the JSON. Do not use markdown code blocks.

Required JSON format:
{
    "quality_score": 0.8,
    "issues_detected": ["example issue 1", "example issue 2"],
    "recommendation": "approve",
    "explanation": "Brief explanation text here",
    "content_type": "article"
}

Field requirements:
- quality_score: number between 0.0 and 1.0
- issues_detected: array of strings
- recommendation: must be one of: "approve", "review", "reject"
- explanation: string
- content_type: must be one of: "article", "cookie_notice", "paywall", "error_page", "navigation", "other"

Quality scoring guidelines:
- 0.9-1.0: High quality article content, no significant issues
- 0.7-0.8: Good content with minor issues (some promotional text, but mostly article)
- 0.5-0.6: Mixed content with significant issues (partial paywall, heavy promotional content)
- 0.3-0.4: Poor content with major issues (mostly unwanted content, some article text)
- 0.0-0.2: Very poor content (cookie notices, error pages, navigation only)

Be strict about quality - it's better to flag questionable content for review than to let poor content through."""

        user_prompt = f"""Please review this scraped article content for quality issues:

Title: {request.article_title}
Source: {request.article_source}
Summary/Content: {request.article_summary}

Analyze this content and provide your assessment."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Get response from AI model
        try:
            response_text = await ai_model.agenerate_response(messages)
            logger.debug(f"LLM response received: {response_text[:200]}...")
        except Exception as e:
            logger.error(f"Error getting response from AI model: {str(e)}")
            raise HTTPException(status_code=500, detail=f"AI model error: {str(e)}")
        
        # Parse the JSON response
        try:
            # Clean the response text to extract JSON
            response_text = response_text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                # Remove first line (```json or ```)
                if lines[0].strip().startswith('```'):
                    lines = lines[1:]
                # Remove last line if it's ```
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                response_text = '\n'.join(lines).strip()

            # Find JSON object in the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1

            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON object found in response")

            json_str = response_text[start_idx:end_idx]

            # Try to fix common JSON issues
            # Replace single quotes with double quotes (but be careful with apostrophes in text)
            # This is a simplified approach - for production you'd want more robust handling

            result = json.loads(json_str)
            
            # Validate and provide defaults
            review_result = {
                "quality_score": float(result.get("quality_score", 0.5)),
                "issues_detected": result.get("issues_detected", []),
                "recommendation": result.get("recommendation", "review"),
                "explanation": result.get("explanation", "No explanation provided"),
                "content_type": result.get("content_type", "other")
            }
            
            # Ensure quality score is within valid range
            review_result["quality_score"] = max(0.0, min(1.0, review_result["quality_score"]))
            
            # Ensure recommendation is valid
            if review_result["recommendation"] not in ["approve", "review", "reject"]:
                review_result["recommendation"] = "review"
            
            # Ensure issues_detected is a list
            if not isinstance(review_result["issues_detected"], list):
                review_result["issues_detected"] = []
            
            logger.info(f"Content review completed - Score: {review_result['quality_score']:.2f}, "
                       f"Recommendation: {review_result['recommendation']}, "
                       f"Issues: {len(review_result['issues_detected'])}")
            
            return {
                "success": True,
                "review": review_result,
                "model_used": request.model_name
            }
            
        except (json.JSONDecodeError, ValueError, KeyError) as parse_error:
            logger.error(f"Failed to parse LLM response as JSON: {str(parse_error)}")
            logger.error(f"Raw response: {response_text}")
            
            # Return conservative default if parsing fails
            return {
                "success": False,
                "error": f"Failed to parse AI response: {str(parse_error)}",
                "review": {
                    "quality_score": 0.3,  # Conservative score when uncertain
                    "issues_detected": ["AI response parsing failed"],
                    "recommendation": "review",
                    "explanation": f"Unable to parse AI model response: {str(parse_error)}",
                    "content_type": "other"
                },
                "model_used": request.model_name
            }
            
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in content review: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Auto-ingest endpoints
class AutoIngestToggle(BaseModel):
    enabled: bool

class BulkProcessRequest(BaseModel):
    topic_id: str
    max_articles: Optional[int] = 100
    relevance_threshold_override: Optional[float] = None
    quality_control_enabled: bool = True
    dry_run: bool = False
    llm_model_override: Optional[str] = None

@router.post("/auto-ingest/enable")
async def enable_auto_ingest(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Enable or disable auto-ingest functionality"""
    try:
        # Update auto_ingest_enabled setting
        db.facade.enable_or_disable_auto_ingest(True)

        return {
            "success": True,
            "auto_ingest_enabled": toggle.enabled,
            "message": f"Auto-ingest {'enabled' if toggle.enabled else 'disabled'} successfully"
        }
            
    except Exception as e:
        logger.error(f"Error toggling auto-ingest: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auto-ingest/disable")
async def disable_auto_ingest(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Disable auto-ingest functionality"""
    return db.facade.enable_or_disable_auto_ingest(False)

@router.get("/auto-ingest/status")
async def get_auto_ingest_status(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Get current auto-ingest status and settings"""
    try:
        settings = db.facade.get_auto_ingest_settings()

        if settings:
            # Get processing statistics
            stats = db.facade.get_processing_statistics()

            return {
                "success": True,
                "settings": {
                    "auto_ingest_enabled": bool(settings[0]),
                    "min_relevance_threshold": float(settings[1] or 0.0),
                    "quality_control_enabled": bool(settings[2]),
                    "auto_save_approved_only": bool(settings[3]),
                    "default_llm_model": settings[4],  # Can be None = use first available
                    "llm_temperature": float(settings[5] if settings[5] is not None else 0.2),
                    "llm_max_tokens": int(settings[6] or 1000)
                },
                "statistics": {
                    "total_auto_ingested": stats[0] if stats else 0,
                    "approved_count": stats[1] if stats else 0,
                    "failed_count": stats[2] if stats else 0,
                    "avg_quality_score": float(stats[3]) if stats and stats[3] else 0.0
                }
            }
        else:
            # Return defaults for new users
            return {
                "success": True,
                "settings": {
                    "auto_ingest_enabled": True,  # Auto-processing ON by default
                    "min_relevance_threshold": 0.0,
                    "quality_control_enabled": True,
                    "auto_save_approved_only": True,  # Save Approved Only ON by default
                    "default_llm_model": None,  # null = use first available model
                    "llm_temperature": 0.2,  # Temperature 0.2 default
                    "llm_max_tokens": 1000
                },
                "statistics": {
                    "total_auto_ingested": 0,
                    "approved_count": 0,
                    "failed_count": 0,
                    "avg_quality_score": 0.0
                }
            }
                
    except Exception as e:
        logger.error(f"Error getting auto-ingest status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auto-ingest/trigger")
async def trigger_auto_ingest(
    topic: Optional[str] = None,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Manually trigger auto-ingest for testing"""
    try:
        # Import here to avoid circular imports
        from app.tasks.keyword_monitor import KeywordMonitor
        
        monitor = KeywordMonitor(db)
        
        if not monitor.should_auto_ingest():
            return {
                "success": False,
                "message": "Auto-ingest is disabled in settings"
            }
        
        # For manual trigger, we'll simulate with placeholder data
        # In a real implementation, this would fetch recent articles
        
        return {
            "success": True,
            "message": "Auto-ingest trigger functionality implemented - requires integration with article collection",
            "auto_ingest_enabled": True
        }
        
    except Exception as e:
        logger.error(f"Error triggering auto-ingest: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/bulk-process-topic")
async def bulk_process_topic(
    request: BulkProcessRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Process all articles from a specific topic group with auto-ingest pipeline (async)"""
    try:
        from app.services.automated_ingest_service import AutomatedIngestService
        from app.services.async_db import initialize_async_db

        # If dry_run, just return counts without processing
        if request.dry_run:
            logger.info(f"Dry run: Getting article counts for topic '{request.topic_id}'")

            # Initialize async database
            await initialize_async_db()
            service = AutomatedIngestService(db)

            # Get article counts
            all_articles, unprocessed_articles = await service.async_db.get_topic_articles(request.topic_id)

            total_count = len(all_articles)
            unprocessed_count = len(unprocessed_articles)
            would_process = min(unprocessed_count, request.max_articles)

            logger.info(f"Dry run results: {total_count} total, {unprocessed_count} unprocessed, {would_process} would process")

            return {
                "success": True,
                "dry_run": True,
                "total_count": total_count,
                "unprocessed_unread_articles": unprocessed_count,
                "articles_found": total_count,
                "would_process": would_process,
                "topic": request.topic_id
            }

        # Normal processing: Generate job ID
        job_id = str(uuid.uuid4())

        # Create job tracking object
        job = ProcessingJob(job_id, request.topic_id, request.dict())
        _processing_jobs[job_id] = job

        # Start background task
        asyncio.create_task(_background_bulk_process(job_id, request, db))

        # Return immediately with job ID
        return {
            "success": True,
            "job_id": job_id,
            "status": "started",
            "message": f"Bulk processing started for topic: {request.topic_id}",
            "check_status_url": f"/keyword-monitor/bulk-process-status/{job_id}"
        }

    except Exception as e:
        logger.error(f"Error starting bulk topic processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def _background_bulk_process(job_id: str, request: BulkProcessRequest, db: Database):
    """Enhanced background task with progressive processing and WebSocket updates"""
    job = _processing_jobs[job_id]
    
    try:
        # Set job status to running
        job.status = "running"
        logger.info(f"🚀 Starting progressive background processing for job {job_id}")
        
        from app.services.automated_ingest_service import AutomatedIngestService
        from app.services.async_db import initialize_async_db
        
        # Initialize async database
        await initialize_async_db()
        
        service = AutomatedIngestService(db)
        
        # Get articles using async database
        all_articles, unprocessed_articles = await service.async_db.get_topic_articles(request.topic_id)
        keywords = await service.async_db.get_topic_keywords(request.topic_id)
        
        if not unprocessed_articles:
            job.status = "completed"
            job.results = {
                "success": True,
                "message": f"No unprocessed articles found for topic: {request.topic_id}",
                "processed_count": 0,
                "total_count": len(all_articles)
            }
            job.completed_at = datetime.utcnow()
            return
        
        # Apply limits
        articles_to_process = unprocessed_articles[:request.max_articles]
        
        logger.info(f"📊 Processing {len(articles_to_process)} articles for topic '{request.topic_id}'")
        
        # Process articles progressively with WebSocket updates
        final_results = None
        async for progress_update in service.process_articles_progressive(
            articles_to_process, 
            request.topic_id, 
            keywords,
            batch_size=3,  # Smaller batches for better responsiveness
            job_id=job_id
        ):
            # Update job progress
            if progress_update.get("type") == "progress":
                job.progress = progress_update.get("percentage", 0)
                logger.debug(f"📈 Job {job_id} progress: {job.progress}%")
            elif progress_update.get("type") == "completed":
                final_results = progress_update.get("final_results")
                break
            elif progress_update.get("type") == "error":
                raise Exception(progress_update.get("message", "Unknown error"))
        
        # Update job status with final results
        job.status = "completed"
        job.results = {
            "success": True,
            "processed_count": final_results.get("processed", 0),
            "total_count": len(all_articles),
            "approved_count": final_results.get("quality_passed", 0),
            "filtered_count": final_results.get("processed", 0) - final_results.get("relevant", 0),
            "failed_count": len(final_results.get("errors", [])),
            "saved_count": final_results.get("saved", 0),
            "vector_indexed_count": final_results.get("vector_indexed", 0),
            "processing_results": final_results,
            "topic_id": request.topic_id,
            "articles_processed": len(articles_to_process),
            "processing_log": [
                f"Total articles for topic: {len(all_articles)}",
                f"Unprocessed articles: {len(unprocessed_articles)}",
                f"Processed: {final_results.get('processed', 0)}",
                f"Approved: {final_results.get('quality_passed', 0)}",
                f"Saved: {final_results.get('saved', 0)}",
                f"Vector indexed: {final_results.get('vector_indexed', 0)}",
                f"Errors: {len(final_results.get('errors', []))}"
            ] + final_results.get("errors", [])
        }
        job.completed_at = datetime.utcnow()
        logger.info(f"✅ Completed progressive background processing for job {job_id}")
        
        # Schedule job cleanup after 5 minutes
        asyncio.create_task(_cleanup_job_after_delay(job_id, 300))
        
    except Exception as e:
        logger.error(f"❌ Error in progressive background processing: {str(e)}")
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.utcnow()
        
        # Send error WebSocket update
        try:
            from app.routes.websocket_routes import send_error_update
            await send_error_update(job_id, str(e))
        except Exception as ws_error:
            logger.warning(f"Failed to send WebSocket error update: {ws_error}")
        
        # Schedule job cleanup after 5 minutes even on failure
        asyncio.create_task(_cleanup_job_after_delay(job_id, 300))

async def _cleanup_job_after_delay(job_id: str, delay_seconds: int):
    """Clean up completed job after a delay"""
    await asyncio.sleep(delay_seconds)
    if job_id in _processing_jobs:
        job = _processing_jobs[job_id]
        if job.status in ["completed", "failed"]:
            logger.info(f"Cleaning up completed job {job_id}")
            del _processing_jobs[job_id]

@router.get("/bulk-process-status/{job_id}")
async def get_bulk_process_status(
    job_id: str,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Get status of a bulk processing job"""
    if job_id not in _processing_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = _processing_jobs[job_id]
    return {
        "job_id": job_id,
        "status": job.status,
        "progress": job.progress,
        "results": job.results,
        "error": job.error,
        "started_at": job.started_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None
    }

@router.get("/active-jobs-status")
async def get_active_jobs_status(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """
    Get status of all active background processing jobs

    Returns:
        Dictionary containing active job information
    """
    try:
        # Import keyword monitor jobs
        from app.tasks.keyword_monitor import get_keyword_monitor_jobs
        keyword_jobs = get_keyword_monitor_jobs()

        active_jobs = []
        all_jobs_details = []

        # Process bulk processing jobs
        for job_id, job in _processing_jobs.items():
            job_detail = {
                "job_id": job_id,
                "topic_id": job.topic_id,
                "status": job.status,
                "progress": job.progress,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "job_type": "bulk_processing"
            }
            all_jobs_details.append(job_detail)

            if job.status == "running":
                active_jobs.append(job_detail)

        # Process keyword monitor auto-ingest jobs
        for job_id, job in keyword_jobs.items():
            job_detail = {
                "job_id": job_id,
                "topic_id": job.topic,
                "status": job.status,
                "progress": job.progress,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "job_type": "keyword_monitor_auto_ingest",
                "article_count": job.article_count
            }
            all_jobs_details.append(job_detail)

            if job.status == "running":
                active_jobs.append(job_detail)

        total_jobs = len(_processing_jobs) + len(keyword_jobs)

        return {
            "success": True,
            "active_jobs": active_jobs,
            "all_jobs": all_jobs_details,
            "total_active": len(active_jobs),
            "total_jobs": total_jobs
        }
        
    except Exception as e:
        logger.error(f"Error getting active jobs status: {e}")
        return {
            "success": False,
            "error": str(e),
            "active_jobs": [],
            "all_jobs": [],
            "total_active": 0,
            "total_jobs": 0
        }

@router.post("/clear-completed-jobs")
async def clear_completed_jobs(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """
    Manually clear all completed/failed jobs from memory
    """
    try:
        initial_count = len(_processing_jobs)
        cleared_jobs = []
        
        # Get list of jobs to clear
        jobs_to_clear = []
        for job_id, job in _processing_jobs.items():
            if job.status in ["completed", "failed"]:
                jobs_to_clear.append(job_id)
                cleared_jobs.append({
                    "job_id": job_id,
                    "status": job.status,
                    "topic_id": job.topic_id
                })
        
        # Clear the jobs
        for job_id in jobs_to_clear:
            del _processing_jobs[job_id]
        
        final_count = len(_processing_jobs)
        
        return {
            "success": True,
            "message": f"Cleared {len(jobs_to_clear)} completed/failed jobs",
            "initial_job_count": initial_count,
            "final_job_count": final_count,
            "cleared_jobs": cleared_jobs
        }
        
    except Exception as e:
        logger.error(f"Error clearing completed jobs: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# =====================================================
# Keyword Relevance Analysis Endpoints
# =====================================================

@router.get("/relevance-stats")
async def get_relevance_stats(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """
    Get aggregated relevance statistics for all keywords.
    Returns keyword performance metrics including match counts,
    average relevance scores, and high/low relevance splits.
    """
    logger.info("=== RELEVANCE-STATS ENDPOINT CALLED ===")
    try:
        # Get keyword stats from database
        logger.info("Fetching keyword relevance stats from database...")
        keyword_stats = db.facade.get_keyword_relevance_stats()
        logger.info(f"Got {len(keyword_stats) if keyword_stats else 0} keyword stats")

        # Convert to list of dicts for JSON serialization
        keywords = []
        total_matches = 0
        total_high_relevance = 0
        relevance_sum = 0
        keywords_with_data = 0

        for row in keyword_stats:
            matches = row['total_matches'] or 0
            high_rel = row['high_relevance_count'] or 0
            low_rel = row['low_relevance_count'] or 0
            avg_rel = float(row['avg_relevance']) if row['avg_relevance'] else 0

            # Calculate percentages
            high_pct = round(100 * high_rel / matches, 1) if matches > 0 else 0
            low_pct = round(100 * low_rel / matches, 1) if matches > 0 else 0

            keywords.append({
                "keyword_id": row['keyword_id'],
                "keyword": row['keyword'],
                "group_id": row['group_id'],
                "group_name": row['group_name'],
                "topic": row['topic'],
                "total_matches": matches,
                "avg_relevance": avg_rel,
                "avg_topic_alignment": float(row['avg_topic_alignment']) if row['avg_topic_alignment'] else 0,
                "avg_confidence": float(row['avg_confidence']) if row['avg_confidence'] else 0,
                "high_relevance_count": high_rel,
                "high_relevance_pct": high_pct,
                "low_relevance_count": low_rel,
                "low_relevance_pct": low_pct
            })

            total_matches += matches
            total_high_relevance += high_rel
            if avg_rel > 0:
                relevance_sum += avg_rel
                keywords_with_data += 1

        # Calculate summary stats
        overall_avg_relevance = round(relevance_sum / keywords_with_data, 3) if keywords_with_data > 0 else 0
        overall_high_relevance_pct = round(100 * total_high_relevance / total_matches, 1) if total_matches > 0 else 0

        return {
            "keywords": keywords,
            "summary": {
                "total_keywords": len(keywords),
                "total_articles": total_matches,
                "overall_avg_relevance": overall_avg_relevance,
                "overall_high_relevance_pct": overall_high_relevance_pct
            }
        }

    except Exception as e:
        logger.error(f"Error getting relevance stats: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error fetching relevance stats: {str(e)}")


@router.get("/keyword/{keyword_id}/articles")
async def get_keyword_articles(
    keyword_id: int,
    group_id: int,
    relevance_filter: str = "all",
    limit: int = 50,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """
    Get articles matched to a specific keyword with relevance data.

    Args:
        keyword_id: The monitored_keywords.id
        group_id: The keyword_groups.id
        relevance_filter: 'all', 'high' (>=0.7), or 'low' (<0.4)
        limit: Maximum number of articles to return
    """
    try:
        # Get articles for this keyword
        articles = db.facade.get_articles_for_keyword(
            keyword_id=keyword_id,
            group_id=group_id,
            relevance_filter=relevance_filter,
            limit=limit
        )

        # Convert to list of dicts
        article_list = []
        for row in articles:
            article_list.append({
                "uri": row['uri'],
                "title": row['title'],
                "news_source": row['news_source'],
                "publication_date": row['publication_date'],
                "keyword_relevance_score": float(row['keyword_relevance_score']) if row['keyword_relevance_score'] else 0,
                "topic_alignment_score": float(row['topic_alignment_score']) if row['topic_alignment_score'] else 0,
                "confidence_score": float(row['confidence_score']) if row['confidence_score'] else 0,
                "overall_match_explanation": row['overall_match_explanation'] or "",
                "extracted_article_keywords": row['extracted_article_keywords'] or ""
            })

        return {
            "keyword_id": keyword_id,
            "group_id": group_id,
            "filter": relevance_filter,
            "count": len(article_list),
            "articles": article_list
        }

    except Exception as e:
        logger.error(f"Error getting articles for keyword {keyword_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error fetching keyword articles: {str(e)}")


@router.get("/source-distribution")
async def get_source_distribution(
    group_id: Optional[int] = None,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """
    Get news source distribution split by high/low relevance.

    Args:
        group_id: Optional group_id to filter by. If None, returns all sources.
    """
    try:
        sources = db.facade.get_source_distribution_by_relevance(group_id)

        # Convert to list of dicts
        source_list = []
        for row in sources:
            total = row['total_count'] or 0
            high = row['high_relevance_count'] or 0
            low = row['low_relevance_count'] or 0

            source_list.append({
                "news_source": row['news_source'],
                "total_count": total,
                "high_relevance_count": high,
                "low_relevance_count": low,
                "high_relevance_pct": round(100 * high / total, 1) if total > 0 else 0,
                "low_relevance_pct": round(100 * low / total, 1) if total > 0 else 0,
                "avg_relevance": float(row['avg_relevance']) if row['avg_relevance'] else 0,
                "bias": row['bias'] or "Unknown"
            })

        return {
            "group_id": group_id,
            "sources": source_list
        }

    except Exception as e:
        logger.error(f"Error getting source distribution: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error fetching source distribution: {str(e)}")


class KeywordRefinementRequest(BaseModel):
    keyword_id: int
    keyword: str
    topic: str
    group_id: int


@router.post("/suggest-refinements")
async def suggest_keyword_refinements(
    request: KeywordRefinementRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """
    Use LLM to analyze a low-performing keyword and suggest refined patterns.

    Returns analysis of why the keyword is too broad and suggests improved patterns.
    """
    try:
        # Get sample low-relevance article titles for context
        low_relevance_titles = db.facade.get_low_relevance_article_titles_for_keyword(
            keyword_id=request.keyword_id,
            group_id=request.group_id,
            limit=10
        )

        if not low_relevance_titles:
            return {
                "original_keyword": request.keyword,
                "analysis": "No low-relevance articles found for this keyword. The keyword may be performing well or has no matched articles yet.",
                "suggestions": [],
                "common_false_positive_sources": [],
                "recommended_exclusions": []
            }

        # Format titles for LLM
        titles_text = "\n".join([f"- {title}" for title in low_relevance_titles])

        # Build the LLM prompt
        prompt = f"""Analyze this keyword pattern used for monitoring news articles about "{request.topic}":

Keyword Pattern: {request.keyword}

Sample LOW-RELEVANCE article titles that matched this keyword (these are false positives we want to avoid):
{titles_text}

The keyword is matching too many irrelevant articles. Please analyze and provide refinements.

Respond in JSON format with this exact structure:
{{
    "analysis": "Brief explanation of why the current keyword pattern is too broad and what's causing false positives",
    "suggestions": [
        {{
            "refined_pattern": "The improved keyword pattern using boolean operators (AND, OR, NOT, quotes for phrases)",
            "explanation": "Why this refinement would help reduce false positives"
        }}
    ],
    "common_false_positive_sources": ["List", "of", "common", "irrelevant", "topics"],
    "recommended_exclusions": ["term1", "term2", "term3"]
}}

Provide 2-3 refined patterns. Use standard boolean search syntax:
- Use quotes for exact phrases: "artificial intelligence"
- Use OR for alternatives: AI OR "artificial intelligence"
- Use AND for required terms: AI AND safety
- Use NOT or minus (-) for exclusions: AI -stock -market
- Use parentheses for grouping: (AI OR ML) AND safety

Focus on making the patterns more specific to {request.topic} while excluding the false positive topics seen in the sample titles."""

        # Call the LLM - use first available configured model
        available_models = get_available_models()
        if not available_models:
            raise HTTPException(status_code=500, detail="No configured models available")
        default_model = available_models[0]['name']

        # Prepend system instruction to the prompt since generate() only accepts prompt and max_tokens
        full_prompt = """You are an expert at crafting precise keyword search patterns for news monitoring. You understand boolean search syntax and how to balance specificity with recall. Always respond with valid JSON.

""" + prompt

        model = LiteLLMModel(default_model)
        response = await model.generate(full_prompt, max_tokens=1500)

        # Parse the JSON response
        try:
            # Extract content from response object
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                response_text = response.message.content.strip()
            else:
                response_text = str(response).strip()

            # Handle markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            result = json.loads(response_text)

            return {
                "original_keyword": request.keyword,
                "analysis": result.get("analysis", ""),
                "suggestions": result.get("suggestions", []),
                "common_false_positive_sources": result.get("common_false_positive_sources", []),
                "recommended_exclusions": result.get("recommended_exclusions", []),
                "sample_low_relevance_titles": low_relevance_titles[:5]
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.error(f"Raw response: {response}")

            # Return a structured error response
            return {
                "original_keyword": request.keyword,
                "analysis": "The AI generated a response but it couldn't be parsed. Please try again.",
                "suggestions": [],
                "common_false_positive_sources": [],
                "recommended_exclusions": [],
                "sample_low_relevance_titles": low_relevance_titles[:5],
                "raw_response": response[:500]  # Include partial response for debugging
            }

    except Exception as e:
        logger.error(f"Error suggesting keyword refinements: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error generating keyword suggestions: {str(e)}")


# ============================================================================
# API-Compatible Keyword Improvement Endpoints (Relevance Feedback Loop)
# ============================================================================

@router.get("/keyword/{keyword_id}/suggest-improvements")
async def suggest_keyword_improvements(
    keyword_id: int,
    group_id: int,
    model: str = "gpt-5.4-mini",
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """
    Analyze keyword performance and suggest API-compatible improvements.

    Uses LLM to analyze low-relevance articles and propose:
    - Replacement keywords (more specific)
    - Additional keywords to add
    - Exclusion terms (-term format)

    All suggestions follow API compatibility rules (no boolean operators, simple terms).
    """
    try:
        from app.services.keyword_suggestion_service import KeywordSuggestionService

        suggestion_service = KeywordSuggestionService(db)
        result = await suggestion_service.suggest_keyword_improvements(
            keyword_id=keyword_id,
            group_id=group_id,
            model=model
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error suggesting keyword improvements: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error generating suggestions: {str(e)}")


class ApplySuggestionRequest(BaseModel):
    suggestion_type: str  # 'replace', 'add', 'exclude'
    suggested_keyword: str
    reason: Optional[str] = None


@router.post("/keyword/{keyword_id}/apply-suggestion")
async def apply_keyword_suggestion(
    keyword_id: int,
    group_id: int,
    request: ApplySuggestionRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """
    Apply a suggested keyword change (requires user approval).

    Can:
    - Replace: Update the existing keyword text
    - Add: Add a new keyword alongside the existing one
    - Exclude: Add an exclusion term (-prefix) to the group
    """
    try:
        username = session.get('user', {}).get('username', 'unknown')

        # Validate suggestion type
        if request.suggestion_type not in ['replace', 'add', 'exclude']:
            raise HTTPException(status_code=400, detail=f"Invalid suggestion_type: {request.suggestion_type}")

        # Normalize the suggested keyword
        from app.utils.keyword_normalizer import normalize_keyword
        normalized = normalize_keyword(request.suggested_keyword)

        if not normalized:
            raise HTTPException(status_code=400, detail="Invalid keyword after normalization")

        # For exclusions, ensure the keyword starts with -
        if request.suggestion_type == 'exclude' and not normalized.startswith('-'):
            normalized = f"-{normalized}"

        # Apply the suggestion based on type
        if request.suggestion_type == 'replace':
            # Update the existing keyword
            db.facade.update_monitored_keyword_text(
                keyword_id=keyword_id,
                new_keyword=normalized
            )
            message = f"Keyword replaced with '{normalized}'"

        elif request.suggestion_type == 'add':
            # Add new keyword to the group - this becomes a separate search query
            db.facade.add_keywords_to_group(group_id, normalized)
            message = f"Added new keyword '{normalized}' (will be searched separately)"

        elif request.suggestion_type == 'exclude':
            # Append exclusion to the ORIGINAL keyword so it's included in the same search
            # This makes the exclusion actually work with news APIs
            current_keyword = db.facade.get_monitored_keyword_by_id(keyword_id)
            if current_keyword:
                current_text = current_keyword.get('keyword', '')
                # Append exclusion term to existing keyword
                new_keyword_text = f"{current_text} {normalized}"
                db.facade.update_monitored_keyword_text(
                    keyword_id=keyword_id,
                    new_keyword=new_keyword_text
                )
                message = f"Added exclusion '{normalized}' to keyword (now: '{new_keyword_text[:50]}...')"
            else:
                raise HTTPException(status_code=404, detail="Original keyword not found")

        logger.info(f"User {username} applied {request.suggestion_type} suggestion: {normalized}")

        return {
            "success": True,
            "message": message,
            "keyword_id": keyword_id,
            "group_id": group_id,
            "applied_keyword": normalized,
            "suggestion_type": request.suggestion_type
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying keyword suggestion: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error applying suggestion: {str(e)}")


@router.get("/group/{group_id}/performance-report")
async def get_group_performance_report(
    group_id: int,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """
    Get comprehensive performance report for all keywords in a group.

    Returns:
    - Summary statistics (total keywords, articles, avg relevance)
    - Per-keyword performance metrics
    - Flag indicating if auto-suggestions are available
    """
    try:
        from app.services.keyword_suggestion_service import KeywordSuggestionService

        suggestion_service = KeywordSuggestionService(db)
        result = await suggestion_service.get_group_performance_report(group_id)

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting group performance report: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")