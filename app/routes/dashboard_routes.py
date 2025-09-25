"""API endpoints for the per-topic dashboard."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from app.database import Database, get_database_instance
from app.ai_models import LiteLLMModel  # Added for LLM access
from app.security.session import verify_session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
from collections import Counter
import json  # Added for parsing metadata
import re
from nltk.corpus import stopwords  # For stop word removal
import nltk  # For downloading stopwords if not present
# Removed problematic import: from app.models.article import ArticleSentiment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Download stopwords if not already downloaded (do this once, ideally at app startup)
try:
    stopwords.words('english')
except LookupError:
    nltk.download('stopwords', quiet=True)

# Define a set of English stop words for efficient lookup
ENGLISH_STOP_WORDS = set(stopwords.words('english'))

# --- Pydantic Models ---
class ArticleSchema(BaseModel):
    uri: str
    title: Optional[str] = None
    news_source: Optional[str] = None
    publication_date: Optional[str] = None
    submission_date: Optional[str] = None
    summary: Optional[str] = None
    category: Optional[str] = None
    future_signal: Optional[str] = None
    sentiment: Optional[str] = None
    time_to_impact: Optional[str] = None
    tags: Optional[List[str]] = None # Assuming tags are stored as JSON string list in DB and converted
    driver_type: Optional[str] = None
    topic: Optional[str] = None
    # Add other fields from your 'articles' table as needed
    # future_signal_explanation: Optional[str] = None
    # sentiment_explanation: Optional[str] = None
    # time_to_impact_explanation: Optional[str] = None
    # driver_type_explanation: Optional[str] = None

    class Config:
        orm_mode = True # If fetching SQLAlchemy models directly
        # If fetching dicts from DB, orm_mode might not be strictly necessary
        # but good practice if you might adapt to ORM later.

class PaginatedArticleResponse(BaseModel):
    page: int
    per_page: int
    total_items: int
    total_pages: int
    items: List[ArticleSchema]

# --- Models for Trend Analysis ---
class TimeSeriesDataPoint(BaseModel):
    date: str # Or datetime.date
    value: float # Generic value for count, average sentiment, etc.

class SentimentDataPoint(BaseModel):
    date: str 
    positive: int = 0 # Default to 0
    neutral: int = 0  # Default to 0
    negative: int = 0  # Default to 0
    mixed: int = 0     # Added for more sentiments
    critical: int = 0  # Added
    hyperbolic: int = 0 # Added
    # Add other specific sentiments you want to track here, defaulting to 0
    avg_score: Optional[float] = None 

class TopTagDataPoint(BaseModel):
    tag: str
    count: int

class SemanticOutlierArticle(ArticleSchema):
    anomaly_score: float

class HighlightedArticleSchema(ArticleSchema): # New model for LLM-curated highlights
    highlight_summary: Optional[str] = None
    highlight_category: Optional[str] = None # e.g., "Breaking", "Developing"

class TopicSummaryMetrics(BaseModel):
    total_articles: int
    new_articles_last_24h: int
    new_articles_last_7d: int
    dominant_news_source: Optional[str] = None
    most_frequent_time_to_impact: Optional[str] = None # Calculate most frequent as average is tricky with text
    # TODO: Add more metrics like:
    # overall_sentiment_trend: Optional[float] = None

class GeneratedInsight(BaseModel):
    id: str  # e.g., 'sentiment_trend', 'volume_spike'
    text: str  # The generated insight text
    confidence: Optional[float] = None  # Optional confidence score (0-1)
    details: Optional[dict] = None  # Optional supporting data
    article_uri: Optional[str] = None  # URI of the standout article, if applicable
    article_title: Optional[str] = None  # Title of the standout article, if applicable

class DashboardPodcastSchema(BaseModel):
    podcast_id: str
    title: str
    audio_url: Optional[str] = None
    transcript: Optional[str] = None  # Or link to transcript
    created_at: datetime
    duration_minutes: Optional[float] = None

# New Schema for Article-specific Insights - REPLACED by ThemedArticle and ThemeWithArticlesSchema
# class ArticleInsightSchema(BaseModel):
#     uri: str
#     title: Optional[str] = None
#     news_source: Optional[str] = None
#     publication_date: Optional[str] = None
#     summary: Optional[str] = None  # Original summary
#     generated_insight_text: str  # LLM generated insight for this specific article

class ThemedArticle(BaseModel): # New
    uri: str
    title: Optional[str] = None
    news_source: Optional[str] = None
    publication_date: Optional[str] = None
    short_summary: Optional[str] = None

class ThemeWithArticlesSchema(BaseModel): # New
    theme_name: str
    theme_summary: str
    articles: List[ThemedArticle]

# New Schema for Category-specific Insights
class CategoryInsightSchema(BaseModel):
    category: str
    article_count: int
    insight_text: Optional[str] = None  # Add this field for LLM-generated insights

# New Pydantic model for Word Frequency
class WordFrequencyDataPoint(BaseModel):
    word: str
    count: int

class StackedVolumeDataPoint(BaseModel):
    date: str
    values: Dict[str, int] # e.g., {"CategoryA": 10, "CategoryB": 5}

class RadarChartDataPoint(BaseModel):
    future_signal: str
    sentiment: str
    time_to_impact: str # Or a numerical representation if preferred
    article_count: int

class RadarChartResponse(BaseModel):
    labels: List[str] # Future signals
    datasets: List[Dict[str, Any]] # Data for Chart.js radar datasets

# Define a Pydantic model for map data points if we want structured output (optional for dummy data)
# class MapActivityPoint(BaseModel):
#     latitude: float
#     longitude: float
#     activity_level: str # e.g., "Normal", "High"
#     name: str # e.g., City name

# Define the MapActivityPoint model for country-based map data
class MapActivityPoint(BaseModel):
    country: str
    activity_level: str  # e.g., "normal", "high"
    articles: int

@router.get("/topic-summary/{topic_name}", response_model=TopicSummaryMetrics)
async def get_topic_summary_metrics(
    topic_name: str,
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
) -> List[MapActivityPoint]:
    """
    Provides a summary of key metrics for a given topic.
    """
    try:
        # Metric: Total articles for the topic
        query_total_articles = "SELECT COUNT(*) FROM articles WHERE topic = ?"
        # Use fetch_all and get the first value from the first row
        total_articles_result = await run_in_threadpool(db.fetch_all, query_total_articles, (topic_name,))
        total_articles_count = total_articles_result[0][0] if total_articles_result and total_articles_result[0] else 0

        # Metric: New articles in the last 24 hours
        time_24h_ago = (datetime.utcnow() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        query_new_24h = "SELECT COUNT(*) FROM articles WHERE topic = ? AND submission_date >= ?"
        # Use fetch_all and get the first value from the first row
        new_articles_24h_result = await run_in_threadpool(db.fetch_all, query_new_24h, (topic_name, time_24h_ago))
        new_articles_24h_count = new_articles_24h_result[0][0] if new_articles_24h_result and new_articles_24h_result[0] else 0

        # Metric: New articles in the last 7 days
        time_7d_ago = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        query_new_7d = "SELECT COUNT(*) FROM articles WHERE topic = ? AND submission_date >= ?"
        # Use fetch_all and get the first value from the first row
        new_articles_7d_result = await run_in_threadpool(db.fetch_all, query_new_7d, (topic_name, time_7d_ago))
        new_articles_7d_count = new_articles_7d_result[0][0] if new_articles_7d_result and new_articles_7d_result[0] else 0
        
        # --- New Metrics (last 30 days for relevance) --- 
        time_30d_ago = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

        # Metric: Dominant News Source (most frequent in last 30d)
        query_dominant_source = f"""
            SELECT news_source, COUNT(*) as count 
            FROM articles 
            WHERE topic = ? AND submission_date >= ? AND news_source IS NOT NULL AND news_source != ''
            GROUP BY news_source 
            ORDER BY count DESC 
            LIMIT 1
        """
        dominant_source_result = await run_in_threadpool(db.fetch_all, query_dominant_source, (topic_name, time_30d_ago))
        dominant_source = dominant_source_result[0][0] if dominant_source_result and dominant_source_result[0] else None

        # Metric: Most Frequent Time To Impact (in last 30d)
        query_frequent_tti = f"""
            SELECT time_to_impact, COUNT(*) as count
            FROM articles
            WHERE topic = ? AND submission_date >= ? AND time_to_impact IS NOT NULL AND time_to_impact != ''
            GROUP BY time_to_impact
            ORDER BY count DESC
            LIMIT 1
        """
        frequent_tti_result = await run_in_threadpool(db.fetch_all, query_frequent_tti, (topic_name, time_30d_ago))
        most_frequent_tti = frequent_tti_result[0][0] if frequent_tti_result and frequent_tti_result[0] else None

        return TopicSummaryMetrics(
            total_articles=total_articles_count,
            new_articles_last_24h=new_articles_24h_count,
            new_articles_last_7d=new_articles_7d_count,
            dominant_news_source=dominant_source,
            most_frequent_time_to_impact=most_frequent_tti
        )

    except Exception as e:
        logger.error(f"Error fetching topic summary metrics for {topic_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve summary metrics for topic {topic_name}")

@router.get("/articles/{topic_name}", response_model=PaginatedArticleResponse)
async def get_topic_articles(
    topic_name: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    start_date: Optional[str] = Query(None, description="Filter by specific start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Filter by specific end date YYYY-MM-DD"),
    # TODO: Add sort_by: Optional[str] = Query(None), sort_order: Optional[str] = Query("desc"),
    db: Database = Depends(get_database_instance),
    filter_no_category: bool = Query(True, description="Filter out articles with no category"), # New parameter
    session: dict = Depends(verify_session)
):
    """
    Retrieves a paginated list of articles for a given topic.
    Leverages the existing db.search_articles method.
    Can be filtered by submission date range and can exclude articles with no category.
    """
    try:
        # The db.search_articles method returns a tuple: (articles_list, total_count)
        # Pass date filters to search_articles. Assuming search_articles uses 'submission_date' 
        # when pub_date_start/end are passed without specifying date_type/date_field explicitly, 
        # OR we might need to adjust the search_articles call if it defaults to publication_date.
        # For simplicity, let's assume passing pub_date_start/end filters submission_date correctly for now.
        # We might need to check/modify db.search_articles if this assumption is wrong.
        
        articles_list_raw, total_items = await run_in_threadpool(
            db.search_articles,
            topic=topic_name,
            page=page,
            per_page=per_page,
            pub_date_start=start_date, # Pass date filters
            pub_date_end=end_date,     # Pass date filters
            date_type='submission',     # Explicitly tell search_articles to use submission_date
            require_category=filter_no_category # Pass the new filter flag
            # TODO: Pass sort_by and sort_order to search_articles once implemented there
        )

        # The 'tags' in articles from search_articles are returned as JSON strings.
        # We need to parse them into lists for ArticleSchema.
        processed_articles = []
        if articles_list_raw:
            for article_dict in articles_list_raw:
                tags_value = article_dict.get('tags')
                # Check if tags_value is a non-empty string
                if isinstance(tags_value, str) and tags_value.strip():
                    # Split by comma and strip whitespace from each tag
                    article_dict['tags'] = [tag.strip() for tag in tags_value.split(',') if tag.strip()]
                elif isinstance(tags_value, list): 
                    # Already a list, use as is (or perform further cleaning if needed)
                    article_dict['tags'] = tags_value
                else:
                    article_dict['tags'] = [] # Default to empty list for None or other types
                
                processed_articles.append(ArticleSchema(**article_dict))

        total_pages = (total_items + per_page - 1) // per_page  # Calculate total pages

        return PaginatedArticleResponse(
            page=page,
            per_page=per_page,
            total_items=total_items,
            total_pages=total_pages,
            items=processed_articles
        )

    except HTTPException as http_exc:  # Re-raise HTTPExceptions directly
        raise http_exc
    except Exception as e:
        logger.error(f"Error fetching articles for topic {topic_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve articles for topic {topic_name}")

@router.get("/volume-over-time/{topic_name}", response_model=List[StackedVolumeDataPoint])
async def get_topic_volume_over_time(
    topic_name: str,
    db: Database = Depends(get_database_instance),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    days_limit: int = Query(30, ge=1, le=365), # Fallback if no dates provided
    stack_by: str = Query("category", description="Field to stack by: 'category' or 'sentiment'"), # New parameter
    session: dict = Depends(verify_session)
):
    """
    Provides the number of articles per day, stacked by category or sentiment,
    for a given topic over a specified period. Uses submission_date for grouping.
    """
    logger.info(f"[get_topic_volume_over_time] Received: topic='{topic_name}', start_date='{start_date}', end_date='{end_date}', days_limit={days_limit}, stack_by='{stack_by}'") # Log input params
    try:
        end_date_dt = datetime.utcnow() if not end_date else datetime.strptime(end_date, '%Y-%m-%d')
        if start_date:
            start_date_dt = datetime.strptime(start_date, '%Y-%m-%d')
        else: # If frontend sends days_limit
            start_date_dt = end_date_dt - timedelta(days=days_limit) 
        
        start_date_str = start_date_dt.strftime('%Y-%m-%d')
        end_date_str = end_date_dt.strftime('%Y-%m-%d')

        logger.info(f"[get_topic_volume_over_time] Calculated SQL date range: {start_date_str} to {end_date_str}") # Log calculated range

        if stack_by not in ["category", "sentiment"]:
            raise HTTPException(status_code=400, detail="Invalid stack_by value. Must be 'category' or 'sentiment'.")

        # Ensure the chosen stack_by field is not null or empty for meaningful stacking
        query = f"""
            SELECT 
                DATE(submission_date) as article_day,
                {stack_by} as stack_value,
                COUNT(*) as article_count
            FROM articles
            WHERE topic = ? 
              AND DATE(submission_date) >= ? 
              AND DATE(submission_date) <= ?
              AND {stack_by} IS NOT NULL AND {stack_by} != ''
            GROUP BY article_day, stack_value
            ORDER BY article_day ASC, stack_value ASC;
        """

        sql_params = (topic_name, start_date_str, end_date_str)
        logger.info(f"[get_topic_volume_over_time] Executing SQL: {query} WITH PARAMS: {sql_params}") # Log query and params
        raw_results = await run_in_threadpool(db.fetch_all, query, sql_params)

        if not raw_results:
            logger.info(f"[get_topic_volume_over_time] No raw results from DB for topic '{topic_name}' in range {start_date_str}-{end_date_str}")
            return []

        # Process results into the desired structure: List[StackedVolumeDataPoint]
        # Output: [{"date": "2023-01-01", "values": {"CatA": 5, "CatB": 10}}, ...]
        processed_data = {}
        for row in raw_results:
            day, stack_val, count = row
            if day not in processed_data:
                processed_data[day] = {"date": day, "values": {}}
            processed_data[day]["values"][stack_val] = count
        
        # Convert dict to list of StackedVolumeDataPoint
        data_points = [StackedVolumeDataPoint(**day_data) for day_data in processed_data.values()]
        # Sort by date again just in case dictionary iteration order changed (though usually preserved in modern Python)
        data_points.sort(key=lambda x: x.date)
        
        return data_points

    except ValueError as ve: # Catch invalid date format specifically
        logger.error(f"Date format error for volume over time (topic: {topic_name}): {ve}")
        raise HTTPException(status_code=400, detail="Invalid date format. Please use YYYY-MM-DD.")
    except Exception as e:
        logger.error(f"Error fetching stacked volume over time for topic {topic_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve stacked volume data for topic {topic_name}")

@router.get("/sentiment-over-time/{topic_name}", response_model=List[SentimentDataPoint])
async def get_topic_sentiment_over_time(
    topic_name: str,
    db: Database = Depends(get_database_instance),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    days_limit: int = Query(30, ge=1, le=365), # Fallback if no dates provided
    session: dict = Depends(verify_session)
):
    """
    Provides the count of articles by various sentiments 
    per day for a given topic over a specified period, excluding 'unknown'.
    Uses submission_date for grouping.
    """
    logger.info(f"[get_topic_sentiment_over_time] Received: topic='{topic_name}', start: {start_date}, end: {end_date}, days: {days_limit}")
    try:
        end_date_dt = datetime.utcnow() if not end_date else datetime.strptime(end_date, '%Y-%m-%d')
        if start_date:
            start_date_dt = datetime.strptime(start_date, '%Y-%m-%d')
        else:
            start_date_dt = end_date_dt - timedelta(days=days_limit)
        start_date_str = start_date_dt.strftime('%Y-%m-%d')
        end_date_str = end_date_dt.strftime('%Y-%m-%d')

        logger.info(f"[get_topic_sentiment_over_time] Calculated SQL date range: {start_date_str} to {end_date_str}")

        # Query to get sentiment counts AND average score per day
        # Excludes 'unknown' sentiment directly in the WHERE clause.
        query = f"""
            SELECT 
                DATE(submission_date) as article_day,
                LOWER(sentiment) as sentiment_value, -- Get the actual sentiment string
                COUNT(*) as article_count,
                AVG(CASE LOWER(sentiment) 
                        WHEN 'positive' THEN 1.0 
                        WHEN 'neutral' THEN 0.0 
                        WHEN 'negative' THEN -1.0 
                        ELSE NULL -- Other specific mappings could be added here if they have numeric equivalents
                    END) as avg_sentiment_score_for_day 
            FROM articles
            WHERE topic = ? 
              AND DATE(submission_date) >= ?
              AND DATE(submission_date) <= ?
              AND sentiment IS NOT NULL AND sentiment != '' AND LOWER(sentiment) != 'unknown'
            GROUP BY article_day, sentiment_value
            ORDER BY article_day ASC, sentiment_value ASC;
        """
        
        sql_params = (topic_name, start_date_str, end_date_str)
        logger.info(f"[get_topic_sentiment_over_time] Executing SQL: {query} WITH PARAMS: {sql_params}")
        raw_results = await run_in_threadpool(db.fetch_all, query, sql_params)

        if not raw_results:
            logger.info(f"[get_topic_sentiment_over_time] No raw sentiment results from DB for topic '{topic_name}' in range {start_date_str}-{end_date_str}")
            return []

        # Process results: group by day and populate SentimentDataPoint
        daily_sentiment_data = {}
        for row in raw_results:
            day, sentiment_val, count, avg_score_day = row
            if day not in daily_sentiment_data:
                daily_sentiment_data[day] = {
                    "date": day,
                    "positive": 0, "neutral": 0, "negative": 0,
                    "mixed": 0, "critical": 0, "hyperbolic": 0,
                    "avg_score": None # Will be set once per day
                }
            
            # Populate the specific sentiment count
            if sentiment_val in daily_sentiment_data[day]: # Check if the sentiment is a tracked key
                daily_sentiment_data[day][sentiment_val] = count
            else:
                logger.warning(f"[get_topic_sentiment_over_time] Encountered untracked sentiment '{sentiment_val}' for day {day}. It will be ignored in totals but might affect avg_score if not mapped.")

            # avg_score_day is calculated per day (due to GROUP BY article_day, sentiment_value, it might be repeated)
            # We only need to set it once per day. The last one encountered for a day in sorted results will be fine.
            if avg_score_day is not None:
                 daily_sentiment_data[day]["avg_score"] = round(avg_score_day, 3)
        
        # Convert to list of Pydantic models
        data_points = [SentimentDataPoint(**day_data) for day_data in daily_sentiment_data.values()]
        data_points.sort(key=lambda x: x.date) # Ensure final sort by date
        
        logger.info(f"[get_topic_sentiment_over_time] Processed {len(data_points)} daily sentiment points.")
        return data_points

    except ValueError as ve: 
        logger.error(f"Date format error for sentiment over time (topic: {topic_name}): {ve}")
        raise HTTPException(status_code=400, detail="Invalid date format. Please use YYYY-MM-DD.")
    except Exception as e:
        logger.error(f"Error fetching sentiment over time for topic {topic_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve sentiment data for topic {topic_name}")

@router.get("/top-tags/{topic_name}", response_model=List[TopTagDataPoint])
async def get_topic_top_tags(
    topic_name: str,
    db: Database = Depends(get_database_instance),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    days_limit: int = Query(30, ge=1, le=365), # Fallback if no dates provided
    limit_tags: int = Query(10, ge=1, le=50), # How many top tags to return
    session: dict = Depends(verify_session)
):
    """
    Provides the most frequent tags for a given topic over a specified period.
    Assumes 'tags' column stores a comma-separated string of tags.
    """
    try:
        # Determine date range (same logic as volume)
        end_date_dt = datetime.utcnow() if not end_date else datetime.strptime(end_date, '%Y-%m-%d')
        if start_date:
            start_date_dt = datetime.strptime(start_date, '%Y-%m-%d')
            start_date_str = start_date
        else:
            start_date_dt = end_date_dt - timedelta(days=days_limit)
            start_date_str = start_date_dt.strftime('%Y-%m-%d')
        end_date_str = end_date_dt.strftime('%Y-%m-%d')

        query = f"""
            SELECT tags 
            FROM articles 
            WHERE topic = ? 
              AND DATE(submission_date) >= ? 
              AND DATE(submission_date) <= ? -- Added end date condition
              AND tags IS NOT NULL AND tags != ''
        """

        raw_tag_strings_rows = await run_in_threadpool(db.fetch_all, query, (topic_name, start_date_str, end_date_str))

        if raw_tag_strings_rows is None:
            raw_tag_strings_rows = []

        all_tags = []
        for row in raw_tag_strings_rows:
            tags_csv_string = row[0]
            # Split the comma-separated string
            if isinstance(tags_csv_string, str) and tags_csv_string.strip():
                tags_list = [tag.lower().strip() for tag in tags_csv_string.split(',') if tag.strip()]
                all_tags.extend(tags_list)
            # No JSON parsing needed here anymore

        if not all_tags:
            return []

        tag_counts = Counter(all_tags)
        top_tags = tag_counts.most_common(limit_tags)

        return [TopTagDataPoint(tag=tag, count=count) for tag, count in top_tags]

    except Exception as e:
        logger.error(f"Error fetching top tags for topic {topic_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve top tags for topic {topic_name}")

# --- Key Articles Endpoint ---
@router.get("/key-articles/{topic_name}", response_model=List[HighlightedArticleSchema])
async def get_key_articles(
    topic_name: str,
    top_k: int = Query(3, ge=1, le=5), # How many key articles LLM should identify
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
):
    """
    Identifies and returns key articles for a topic, selected and summarized by an LLM.
    """
    logger.info(f"Fetching LLM-curated key articles for topic: {topic_name}")
    try:
        # 1. Fetch recent articles (e.g., last 10-15 to give LLM some choice)
        paginated_response: PaginatedArticleResponse = await get_topic_articles(
            topic_name=topic_name,
            page=1,
            per_page=10, # Fetch 10 articles for the LLM to choose from
            start_date=None, # Explicitly pass None for default behavior
            end_date=None,   # Explicitly pass None for default behavior
            db=db
        )
        articles_to_consider = paginated_response.items

        if not articles_to_consider:
            return []

        # 2. Prepare content for LLM
        article_details_for_llm = []
        for i, art in enumerate(articles_to_consider):
            detail = (
                f"Article {i+1}:\n"
                f"  Title: {art.title or 'Untitled'}\n"
                f"  Source: {art.news_source or 'Unknown'}\n"
                f"  Published: {art.publication_date or 'N/A'}\n"
                f"  Sentiment: {art.sentiment or 'N/A'}\n"
                f"  Future Signal: {art.future_signal or 'N/A'}\n"
                f"  Summary: {art.summary or 'No summary available'}\n"
                f"  Tags: {(', '.join(art.tags)) if art.tags else 'N/A'}\n"
                f"  URI: {art.uri}"
            )
            article_details_for_llm.append(detail)
        
        combined_article_text = "\n---\n".join(article_details_for_llm)

        # 3. Initialize LLM
        llm_model_name = "gpt-4o" 
        ai_model = LiteLLMModel.get_instance(llm_model_name)
        if not ai_model:
            logger.error(f"Failed to initialize LLM model: {llm_model_name} for key articles")
            # Fallback or raise error - for now, return empty or original outliers
            # As a simple fallback, could return top_k of articles_to_consider directly
            return [HighlightedArticleSchema(**art.model_dump()) for art in articles_to_consider[:top_k]]

        # 4. Create prompt for LLM
        system_prompt = (
            f"You are an expert news analyst. From the provided list of articles about '{topic_name}', "
            f"identify the top {top_k} most significant or newsworthy articles for a business audience. "
            "For each selected article, provide its original URI (exact match from input), a short highlight summary (1-2 sentences explaining its significance), "
            "and assign a category from this list: [Breaking, Developing, Insight, Analysis, Update]."
            "Format your response as a JSON list of objects, where each object has keys: \"uri\", \"title\" (original title), \"highlight_summary\", and \"highlight_category\"."
            "Ensure the URI is exactly as provided in the input articles."
            "Example JSON object: { \"uri\": \"article_uri_here\", \"title\": \"Original Article Title\", \"highlight_summary\": \"This article is crucial because...\", \"highlight_category\": \"Breaking\" }"
        )
        
        user_prompt = f"Here are the articles (with their URIs) to analyze for topic '{topic_name}':\n\n{combined_article_text}\n\nPlease identify the top {top_k} articles and format your response as a JSON list as specified."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # 5. Call LLM and process response
        llm_response_str = await run_in_threadpool(ai_model.generate_response, messages)

        if not llm_response_str:
            logger.warning(f"LLM returned no response for key articles on topic {topic_name}")
            return [HighlightedArticleSchema(**art.model_dump()) for art in articles_to_consider[:top_k]] # Fallback

        try:
            # Attempt to parse the LLM response as JSON
            # The regex helps find the JSON block if the LLM adds extra text.
            json_match = re.search(r'\[\s*\{.*\}\s*\]', llm_response_str, re.DOTALL)
            if not json_match:
                logger.warning(f"LLM response for key articles (topic: {topic_name}) was not valid JSON: {llm_response_str}")
                # Fallback: try to return the first few original articles if parsing fails
                return [HighlightedArticleSchema(**art.model_dump()) for art in articles_to_consider[:top_k]]
            
            llm_highlights = json.loads(json_match.group(0))
            
            curated_articles = []
            for highlight_data in llm_highlights:
                uri = highlight_data.get("uri")
                original_article_data = next((art for art in articles_to_consider if art.uri == uri), None)
                
                if original_article_data:
                    # Create HighlightedArticleSchema by taking all fields from original_article_data
                    # and overriding/adding the LLM-provided ones.
                    article_dict = original_article_data.model_dump()
                    article_dict['highlight_summary'] = highlight_data.get("highlight_summary")
                    article_dict['highlight_category'] = highlight_data.get("highlight_category")
                    # Ensure title from LLM (if it differs slightly but URI matched) or original
                    article_dict['title'] = highlight_data.get("title", original_article_data.title)
                    
                    curated_articles.append(HighlightedArticleSchema(**article_dict))
                else:
                    logger.warning(f"LLM highlighted article URI '{uri}' not found in original list for topic {topic_name}")
            
            return curated_articles[:top_k] # Ensure we don't exceed top_k

        except json.JSONDecodeError as e:
            logger.error(f"JSONDecodeError for key articles (topic: {topic_name}): {e}. Response: {llm_response_str}", exc_info=True)
            return [HighlightedArticleSchema(**art.model_dump()) for art in articles_to_consider[:top_k]] # Fallback
        except Exception as e:
            logger.error(f"Error processing LLM response for key articles (topic: {topic_name}): {e}", exc_info=True)
            return [HighlightedArticleSchema(**art.model_dump()) for art in articles_to_consider[:top_k]] # Fallback

    except Exception as e:
        logger.error(f"Error in get_key_articles for {topic_name}: {e}", exc_info=True)
        return []

# --- Generated Insights Endpoint (Placeholder) ---
@router.get("/generated-insights/{topic_name}", response_model=List[GeneratedInsight])
async def get_generated_insights(
    topic_name: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    days_limit: int = Query(30), 
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
):
    """
    Generates analytical insights based on aggregated data trends for the topic using an LLM.
    """
    logger.info(f"Generating LLM insights from aggregated data for topic: {topic_name}, start: {start_date}, end: {end_date}, days: {days_limit}")

    try:
        # 1. Fetch aggregated data
        # To avoid Query object issues, we pass explicit defaults or the provided values
        # For days_limit, if start_date/end_date are given, they take precedence. 
        # The individual functions handle their own date logic based on what's passed.

        summary_metrics: TopicSummaryMetrics = await get_topic_summary_metrics(topic_name, db)
        
        # Fetch volume data - assuming default stack_by='category' is acceptable for general insights
        # If a specific stack_by is needed for insights, it should be passed here.
        volume_data: List[StackedVolumeDataPoint] = await get_topic_volume_over_time(
            topic_name, db, start_date, end_date, days_limit, stack_by="category" # Explicitly using category for insights
        )
        sentiment_data: List[SentimentDataPoint] = await get_topic_sentiment_over_time(
            topic_name, db, start_date, end_date, days_limit
        )
        top_tags_data: List[TopTagDataPoint] = await get_topic_top_tags(
            topic_name, db, start_date, end_date, days_limit, limit_tags=5
        )

        # 2. Prepare data for LLM
        data_for_llm = f"Summary Metrics for '{topic_name}':\n"
        data_for_llm += f"- Total Articles: {summary_metrics.total_articles}\n"
        data_for_llm += f"- New Articles (Last 24h): {summary_metrics.new_articles_last_24h}\n"
        data_for_llm += f"- New Articles (Last 7d): {summary_metrics.new_articles_last_7d}\n"
        data_for_llm += f"- Dominant News Source (30d): {summary_metrics.dominant_news_source or 'N/A'}\n"
        data_for_llm += f"- Most Frequent Time To Impact (30d): {summary_metrics.most_frequent_time_to_impact or 'N/A'}\n\n"

        if volume_data:
            data_for_llm += f"Article Volume Trend (number of articles per day):\n"
            for vd in volume_data[-7:]: # Show last 7 data points for brevity
                total_for_day = sum(vd.values.values()) # Calculate total from the values dictionary
                top_stack_value = max(vd.values, key=vd.values.get, default="N/A") if vd.values else "N/A"
                data_for_llm += f"- {vd.date}: {total_for_day} articles (dominant: {top_stack_value} with {vd.values.get(top_stack_value,0) if vd.values else 0})\n"
            data_for_llm += "\n"
        else:
            data_for_llm += "No specific article volume trend data available for the selected period.\n\n"

        if sentiment_data:
            data_for_llm += f"Sentiment Trend (counts per day & avg score):\n"
            for sd in sentiment_data[-7:]: # Show last 7 data points
                avg_score_str = f", Avg Score: {sd.avg_score:.2f}" if sd.avg_score is not None else ""
                data_for_llm += f"- {sd.date}: Pos: {sd.positive}, Neu: {sd.neutral}, Neg: {sd.negative}{avg_score_str}\n"
            data_for_llm += "\n"
        else:
            data_for_llm += "No specific sentiment trend data available for the selected period.\n\n"

        if top_tags_data:
            data_for_llm += f"Top 5 Tags (and their counts):\n"
            for tag_data in top_tags_data:
                data_for_llm += f"- {tag_data.tag}: {tag_data.count}\n"
            data_for_llm += "\n"
        else:
            data_for_llm += "No top tag data available for the selected period.\n\n"
        
        # 3. Initialize LLM
        llm_model_name = "gpt-4o"
        ai_model = LiteLLMModel.get_instance(llm_model_name)
        if not ai_model:
            logger.error(f"LLM Initialization error for insights: {llm_model_name}", exc_info=True)
            return [GeneratedInsight(id="llm_error", text="Could not initialize the AI model for insights.")]

        # 4. Create prompt for LLM
        date_range_desc = "the selected period"
        if start_date and end_date:
            date_range_desc = f"the period from {start_date} to {end_date}"
        elif days_limit:
            date_range_desc = f"the last {days_limit} days"
        
        system_prompt = (
            f"You are an expert data analyst. Based on the following aggregated data summary for the topic '{topic_name}' over '{date_range_desc}', "
            f"please provide 2-3 key analytical insights. Focus on significant trends, patterns, dominant characteristics, or noteworthy observations from the data. "
            f"Do not simply restate the input data. Provide interpretation or highlight what is interesting. "
            f"Each insight should be a concise statement. If you provide multiple insights, separate them with '***' on a new line."
        )
        
        user_prompt = f"Here is the data summary for topic '{topic_name}':\n\n{data_for_llm}\nPlease generate your 2-3 key analytical insights based on this data."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # 5. Call LLM and process response
        llm_response_text = await run_in_threadpool(ai_model.generate_response, messages)

        if not llm_response_text:
            return [GeneratedInsight(id="llm_no_response", text="The AI model did not return a response for trend insights.")]

        insights_texts = llm_response_text.strip().split("***")
        insights = []
        for i, text_blob in enumerate(insights_texts):
            text_blob = text_blob.strip()
            if text_blob:
                insights.append(GeneratedInsight(id=f"llm_trend_insight_{i+1}", text=text_blob, confidence=0.80))
        
        if not insights:
             return [GeneratedInsight(id="llm_empty_insight", text="AI model returned empty or unparsable trend insights.")]

        return insights

    except Exception as e:
        logger.error(f"Error generating LLM trend insights for {topic_name}: {e}", exc_info=True)
        return [GeneratedInsight(id="error", text="An unexpected error occurred while generating trend insights.")]

# --- Anomaly/Outlier Detection Endpoints ---
@router.get("/semantic-outliers/{topic_name}", response_model=List[SemanticOutlierArticle])
async def get_semantic_outliers(
    topic_name: str,
    db: Database = Depends(get_database_instance),
    top_k: int = Query(10, ge=1, le=50),  # How many outliers to return
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    days_limit: int = Query(30, ge=1, le=365), # Fallback if no dates provided
    session: dict = Depends(verify_session)
):
    logger.info(f"Fetching semantic outliers for topic: {topic_name}, dates: {start_date}-{end_date}")
    # Placeholder: Actual implementation would involve vector operations
    # For now, return empty or dummy data
    
    # Example using existing db.search_articles to get some data for now.
    # This is NOT semantic outlier detection.
    try:
        if start_date and end_date:
            # Ensure date format is correct for SQL
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        elif days_limit:
            effective_end_date_obj = datetime.utcnow()
            effective_start_date_obj = effective_end_date_obj - timedelta(days=days_limit)
            start_date = effective_start_date_obj.strftime('%Y-%m-%d')
            end_date = effective_end_date_obj.strftime('%Y-%m-%d')
        else:  # Default if no dates or days_limit given
            effective_end_date_obj = datetime.utcnow()
            effective_start_date_obj = effective_end_date_obj - timedelta(days=30)  # Default to 30 days
            start_date = effective_start_date_obj.strftime('%Y-%m-%d')
            end_date = effective_end_date_obj.strftime('%Y-%m-%d')

        # Fetch articles using db.search_articles, which handles date filtering
        articles_raw, _ = await run_in_threadpool(
            db.search_articles,
            topic=topic_name,
            page=1,
            per_page=top_k * 2,  # Fetch more to simulate outlier selection
            pub_date_start=start_date,
            pub_date_end=end_date,
            date_type='submission' 
        )

        if not articles_raw:
            return []

        # Simulate anomaly scores and pick top_k
        # In a real scenario, this would come from a proper anomaly detection model
        outliers = []
        for i, art_dict in enumerate(articles_raw):
            if len(outliers) >= top_k:
                break
            # Add a dummy anomaly score
            processed_article = ArticleSchema(**art_dict).dict()
            outliers.append(SemanticOutlierArticle(**processed_article, anomaly_score=1.0 - (i * 0.05)))
            
        return outliers

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Please use YYYY-MM-DD.")
    except Exception as e:
        logger.error(f"Error fetching semantic outliers for {topic_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve semantic outliers for topic {topic_name}")

@router.get("/article-insights/{topic_name}", response_model=List[ThemeWithArticlesSchema])
async def get_article_insights(
    topic_name: str,
    db: Database = Depends(get_database_instance),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD for article selection"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD for article selection"),
    days_limit: int = Query(7, ge=1, le=90, description="for article selection. Default 7 days."),
    force_regenerate: bool = Query(False, description="Force regeneration bypassing cache"),
    model: str = Query("gpt-4o-mini", description="AI model to use for analysis"),
    session: dict = Depends(verify_session)
):
    """
    Identifies common themes across articles and groups them thematically.
    Uses LLM to analyze and extract insights about article content.
    """
    try:
        # Check cache first
        cache_key = f"article_insights_{topic_name}_{start_date or 'no_start'}_{end_date or 'no_end'}_{days_limit}"
        
        # Get representative article for cache anchoring
        temp_response = await get_topic_articles(
            topic_name=topic_name,
            page=1,
            per_page=1,
            start_date=start_date,
            end_date=end_date,
            db=db
        )
        
        if temp_response.items and not force_regenerate:
            cache_uri = temp_response.items[0].uri
            cached = db.get_article_analysis_cache(
                article_uri=cache_uri,
                analysis_type=f"article_insights_{topic_name}",
                model_used="dashboard_api"
            )
            
            if cached and cached.get("metadata", {}).get("cache_key") == cache_key:
                logger.info(f"Cache HIT: article insights for {topic_name}")
                cached_themes = json.loads(cached["content"])
                # Convert back to Pydantic models for response_model compatibility
                return [ThemeWithArticlesSchema(**theme) for theme in cached_themes]
        
        if force_regenerate:
            logger.info(f"Force regenerating article insights for {topic_name} (bypassing cache)")
        
        # 1. Fetch recent articles within the date range
        paginated_response = await get_topic_articles(
            topic_name=topic_name,
            page=1,
            per_page=30,  # Fetch a reasonable number of articles for the LLM to analyze
            start_date=start_date,
            end_date=end_date,
            db=db
        )
        articles = paginated_response.items

        if not articles or len(articles) < 3:  # Need enough articles for meaningful themes
            logger.info(f"Not enough articles ({len(articles) if articles else 0}) for topic '{topic_name}' to generate themes")
            return []
            
        # 2. Create a mapping of URI to article data for easy lookup
        uri_to_article_map = {art.uri: {
            'title': art.title,
            'summary': art.summary,
            'news_source': art.news_source,
            'publication_date': art.publication_date,
            'tags': art.tags
        } for art in articles}
        
        # 3. Prepare article details for LLM analysis
        article_details_for_llm = []
        for i, art in enumerate(articles):
            detail = (
                f"Article {i+1}:\n"
                f"  Title: {art.title or 'Untitled'}\n"
                f"  Source: {art.news_source or 'Unknown'}\n"
                f"  Published: {art.publication_date or 'N/A'}\n"
                f"  Summary: {art.summary or 'No summary available'}\n"
                f"  URI: {art.uri}"
            )
            article_details_for_llm.append(detail)
        
        combined_article_text = "\n---\n".join(article_details_for_llm)
        
        # 4. Initialize LLM and create prompt for thematic analysis
        llm_model_name = model  # Use model from frontend
        ai_model = LiteLLMModel.get_instance(llm_model_name)
        if not ai_model:
            logger.error(f"Failed to initialize LLM model: {llm_model_name} for article insights")
            return []

        # 5. Create prompt for thematic analysis
        system_prompt = (
            f"You are an expert research analyst specializing in '{topic_name}'. "
            f"Analyze the provided articles and identify 3-5 common themes or patterns that emerge. "
            f"For each theme you identify:"
            f"\n1. Give it a concise, descriptive name"
            f"\n2. Write a summary paragraph explaining the theme (2-3 sentences)"
            f"\n3. List the URIs of 2-5 articles that best exemplify this theme"
            f"\nFormat your response as JSON with the structure:"
            f"\n[{{"
            f"\n  \"theme_name\": \"Name of Theme\","
            f"\n  \"theme_summary\": \"Summary explanation of the theme...\","
            f"\n  \"article_uris\": [\"uri1\", \"uri2\", ...] // URIs exactly as provided"
            f"\n}}, {{ ... next theme ... }}]"
        )
        
        user_prompt = f"Here are recent articles about '{topic_name}' to analyze for common themes:\n\n{combined_article_text}\n\nIdentify 3-5 themes and format as specified JSON."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # 6. Call LLM to identify themes
        llm_response_str = await run_in_threadpool(ai_model.generate_response, messages)
        
        # 7. Parse LLM response to extract themes
        llm_themes = []
        if not llm_response_str:
            logger.warning(f"LLM returned empty response for article insights on topic {topic_name}")
            return []
        
        # Check for LLM error messages first
        if "⚠️" in llm_response_str or "unavailable" in llm_response_str.lower() or "error" in llm_response_str.lower():
            logger.error(f"LLM returned error message for article insights: {llm_response_str}")
            return []
            
        try:
            # Attempt to extract JSON from the response - handle both clean JSON and markdown code blocks
            import re
            json_match = re.search(r'```json\s*(\[\s*\{.*\}\s*\])\s*```|```(\[\s*\{.*\}\s*\])```|\[\s*\{.*\}\s*\]', llm_response_str, re.DOTALL)
            if json_match:
                # Get the first non-None capturing group
                json_str = next(group for group in json_match.groups() if group is not None)
                llm_themes = json.loads(json_str)
            else:
                # Fallback - try parsing the whole response as JSON
                llm_themes = json.loads(llm_response_str)
        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse LLM response as JSON: {je}. Response was: {llm_response_str[:200]}...")
            return []
        except Exception as e:
            logger.error(f"Unexpected error processing LLM theme response: {e}. Response was: {llm_response_str[:200]}...", exc_info=True)
            return []

        # 8. Build themed insights from LLM analysis
        final_themed_insights: List[ThemeWithArticlesSchema] = []
        for llm_theme_data in llm_themes:  # Now llm_themes is defined
            if not isinstance(llm_theme_data, dict) or \
               "theme_name" not in llm_theme_data or \
               "theme_summary" not in llm_theme_data or \
               "article_uris" not in llm_theme_data or \
               not isinstance(llm_theme_data["article_uris"], list):
                logger.warning(f"Skipping malformed theme data from LLM: {llm_theme_data}")
                continue

            theme_articles: List[ThemedArticle] = []
            for uri in llm_theme_data["article_uris"]:
                original_article_data = uri_to_article_map.get(uri)  # Now uri_to_article_map is defined
                if original_article_data:
                    # Ensure summary is a string and truncate for short_summary
                    summary_text = original_article_data.get('summary', '')
                    short_s = (summary_text[:150] + '...') \
                        if summary_text and len(summary_text) > 150 else summary_text
                    
                    theme_articles.append(ThemedArticle(
                        uri=uri,
                        title=original_article_data.get('title'),
                        news_source=original_article_data.get('news_source'),
                        publication_date=original_article_data.get('publication_date'),
                        short_summary=short_s
                    ))
                else:
                    logger.warning(f"LLM returned URI '{uri}' for theme '{llm_theme_data['theme_name']}' not found in original article set.")
            
            if theme_articles:  # Only add theme if it has associated articles found in our DB
                final_themed_insights.append(ThemeWithArticlesSchema(
                    theme_name=llm_theme_data["theme_name"],
                    theme_summary=llm_theme_data["theme_summary"],
                    articles=theme_articles
                ))
            else:
                logger.info(f"Theme '{llm_theme_data['theme_name']}' had no matching articles from DB, skipping.")

        logger.info(f"Successfully generated {len(final_themed_insights)} thematic insights for topic {topic_name}.")
        
        # Cache the results for future requests
        try:
            if articles and final_themed_insights:
                cache_uri = articles[0].uri
                # Convert Pydantic models to dict for JSON serialization
                cache_content = json.dumps([theme.dict() for theme in final_themed_insights], ensure_ascii=False, default=str)
                cache_metadata = {
                    "cache_key": cache_key,
                    "topic": topic_name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "days_limit": days_limit,
                    "insight_type": "article_themes",
                    "article_count": len(articles)
                }
                
                success = db.save_article_analysis_cache(
                    article_uri=cache_uri,
                    analysis_type=f"article_insights_{topic_name}",
                    content=cache_content,
                    model_used="dashboard_api",
                    metadata=cache_metadata
                )
                
                if success:
                    logger.info(f"Cache SAVE: article insights for {topic_name}")
                else:
                    logger.warning(f"Cache SAVE FAILED: article insights for {topic_name}")
        except Exception as cache_error:
            logger.warning(f"Failed to cache article insights: {cache_error}")
        
        return final_themed_insights

    except HTTPException:  # Re-raise HTTPExceptions
        raise
    except Exception as e:
        logger.error(f"Error generating article insights for {topic_name}: {e}", exc_info=True)
        return []  # Return empty list on error for graceful frontend handling

@router.get("/latest-podcast/{topic_name}", response_model=Optional[DashboardPodcastSchema])
async def get_latest_podcast_for_topic(
    topic_name: str,
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
):
    """
    Retrieves the latest completed podcast associated with a given topic.
    """
    try:
        # Query the podcasts table, filter by metadata containing the topic,
        # order by creation date, and take the latest one.
        # This query assumes 'metadata' is a JSON string and can be parsed,
        # or that the DB supports JSON querying (e.g., json_extract in SQLite).
        # For simplicity with varying DBs, fetch recent completed podcasts and filter in Python.
        query = """
            SELECT id, title, audio_url, transcript, created_at, metadata
            FROM podcasts
            WHERE status = 'completed'
            ORDER BY created_at DESC
            LIMIT 20  -- Fetch a few recent ones to filter
        """
        
        # Using run_in_threadpool for potentially blocking DB call
        raw_podcasts = await run_in_threadpool(db.fetch_all, query)

        if not raw_podcasts:
            return None

        for podcast_row in raw_podcasts:
            podcast_id, title, audio_url, transcript_content, created_at, metadata_json = podcast_row
            
            if metadata_json:
                try:
                    metadata = json.loads(metadata_json)
                    # Check if 'topic' in metadata matches topic_name, or 'podcast_name' implies topic
                    # This part needs to align with how topics are actually stored in podcast metadata
                    podcast_topic = metadata.get("topic") or metadata.get("podcast_name") # Example logic
                    
                    if podcast_topic and topic_name.lower() in podcast_topic.lower():
                        duration_minutes = metadata.get("duration") # Assuming duration is in minutes
                        # if duration is string like "X.Y min", parse it
                        if isinstance(duration_minutes, str) and "min" in duration_minutes:
                            try:
                                duration_minutes = float(duration_minutes.replace(" min", "").strip())
                            except ValueError:
                                duration_minutes = None
                        
                        return DashboardPodcastSchema(
                            podcast_id=podcast_id,
                            title=title,
                            audio_url=audio_url,
                            transcript=transcript_content, # Or a link if transcript is too long
                            created_at=created_at,
                            duration_minutes=duration_minutes
                        )
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse metadata for podcast {podcast_id}: {metadata_json}")
                    continue # Skip if metadata is malformed
        
        return None # No matching podcast found

    except Exception as e:
        logger.error(f"Error fetching latest podcast for topic {topic_name}: {e}", exc_info=True)
        # Do not raise HTTPException here to allow the frontend to handle "no podcast" gracefully
        return None

@router.get("/podcasts-for-topic/{topic_name}", response_model=List[DashboardPodcastSchema])
async def get_podcasts_for_topic(
    topic_name: str,
    limit: int = Query(5, ge=1, le=20), # Limit the number of previous podcasts shown
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
):
    """
    Retrieves a list of completed podcasts associated with a given topic,
    excluding the absolute latest one (which is handled by /latest-podcast).
    """
    try:
        query = """
            SELECT id, title, audio_url, transcript, created_at, metadata
            FROM podcasts
            WHERE status = 'completed'
            ORDER BY created_at DESC
            LIMIT 100 -- Fetch more to allow for filtering if many don't match the topic
        """
        
        all_completed_podcasts = await run_in_threadpool(db.fetch_all, query)
        
        topic_podcasts = []
        if not all_completed_podcasts:
            return []

        latest_podcast_id_for_topic = None
        # Determine the ID of the latest podcast for this topic to exclude it from "previous"
        latest_podcast_data = await get_latest_podcast_for_topic(topic_name, db)
        if latest_podcast_data:
            latest_podcast_id_for_topic = latest_podcast_data.podcast_id

        for podcast_row in all_completed_podcasts:
            podcast_id, title, audio_url, transcript_content, created_at, metadata_json = podcast_row
            
            # Skip the absolute latest one for this topic, if found
            if podcast_id == latest_podcast_id_for_topic:
                continue

            if metadata_json:
                try:
                    metadata = json.loads(metadata_json)
                    podcast_topic_in_meta = metadata.get("topic") or metadata.get("podcast_name")
                    
                    if podcast_topic_in_meta and topic_name.lower() in podcast_topic_in_meta.lower():
                        duration_minutes = metadata.get("duration")
                        if isinstance(duration_minutes, str) and "min" in duration_minutes:
                            try:
                                duration_minutes = float(duration_minutes.replace(" min", "").strip())
                            except ValueError:
                                duration_minutes = None
                        
                        topic_podcasts.append(DashboardPodcastSchema(
                            podcast_id=podcast_id,
                            title=title,
                            audio_url=audio_url,
                            transcript=transcript_content, 
                            created_at=created_at,
                            duration_minutes=duration_minutes
                        ))
                        if len(topic_podcasts) >= limit:
                            break # Stop once we have enough previous podcasts
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse metadata for podcast {podcast_id}: {metadata_json}")
                    continue
        
        return topic_podcasts

    except Exception as e:
        logger.error(f"Error fetching podcasts for topic {topic_name}: {e}", exc_info=True)
        return [] # Return empty list on error

@router.get("/category-insights/{topic_name}", response_model=List[CategoryInsightSchema])
async def get_category_insights(
    topic_name: str,
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    days_limit: int = Query(30, ge=1, le=365), # Fallback if no dates provided
    force_regenerate: bool = Query(False, description="Force regeneration bypassing cache"),
    model: str = Query("gpt-4o-mini", description="AI model to use for analysis"),
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
):
    """
    Provides a distribution of articles across categories for a given topic and date range.
    Focuses on the top 5 most active categories and provides LLM-based insights for each.
    """
    logger.info(f"Fetching category insights for topic: {topic_name}")
    try:
        # Check cache first
        cache_key = f"category_insights_{topic_name}_{start_date or 'no_start'}_{end_date or 'no_end'}_{days_limit}"
        
        # Get representative article for cache anchoring
        temp_response = await get_topic_articles(
            topic_name=topic_name,
            page=1,
            per_page=1,
            start_date=start_date,
            end_date=end_date,
            db=db
        )
        
        if temp_response.items and not force_regenerate:
            cache_uri = temp_response.items[0].uri
            cached = db.get_article_analysis_cache(
                article_uri=cache_uri,
                analysis_type=f"category_insights_{topic_name}",
                model_used="dashboard_api"
            )
            
            if cached and cached.get("metadata", {}).get("cache_key") == cache_key:
                logger.info(f"Cache HIT: category insights for {topic_name}")
                cached_categories = json.loads(cached["content"])
                # Convert back to Pydantic models for response_model compatibility
                return [CategoryInsightSchema(**cat) for cat in cached_categories]
        
        if force_regenerate:
            logger.info(f"Force regenerating category insights for {topic_name} (bypassing cache)")
        
        # Determine date range (similar to volume/sentiment endpoints)
        end_date_dt = datetime.utcnow() if not end_date else datetime.strptime(end_date, '%Y-%m-%d')
        if start_date:
            start_date_dt = datetime.strptime(start_date, '%Y-%m-%d')
            start_date_str = start_date
        else:
            start_date_dt = end_date_dt - timedelta(days=days_limit)
            start_date_str = start_date_dt.strftime('%Y-%m-%d')
        end_date_str = end_date_dt.strftime('%Y-%m-%d')

        # Query to get article counts per category
        # Ensure category is not null or empty
        query = f"""
            SELECT 
                category, 
                COUNT(*) as article_count
            FROM articles
            WHERE topic = ? 
              AND DATE(submission_date) >= ? 
              AND DATE(submission_date) <= ?
              AND category IS NOT NULL AND category != ''
            GROUP BY category
            ORDER BY article_count DESC
            LIMIT 5;  -- Limit to top 5 most active categories
        """

        raw_results = await run_in_threadpool(db.fetch_all, query, (topic_name, start_date_str, end_date_str))

        if not raw_results:
            return []

        # Initialize LLM for generating insights
        llm_model_name = model  # Use model from frontend
        ai_model = LiteLLMModel.get_instance(llm_model_name)
        if not ai_model:
            logger.error(f"Failed to initialize LLM model: {llm_model_name} for category insights")
            # Return basic category data without insights if LLM fails
            return [CategoryInsightSchema(category=row[0], article_count=row[1]) 
                   for row in raw_results if row[0] is not None]

        # Create full category insights with LLM-generated analysis
        category_insights = []
        
        # Process each of the top 5 categories
        for category_row in raw_results:
            if not category_row[0]:  # Skip if category is None
                continue
                
            category_name = category_row[0]
            article_count = category_row[1]
            
            # Fetch some recent articles from this category for the LLM to analyze
            category_articles_query = f"""
                SELECT title, summary, news_source, publication_date, sentiment
                FROM articles
                WHERE topic = ? 
                AND category = ?
                AND DATE(submission_date) >= ? 
                AND DATE(submission_date) <= ?
                ORDER BY submission_date DESC
                LIMIT 10;  -- Sample of recent articles for this category
            """
            
            category_articles = await run_in_threadpool(
                db.fetch_all, 
                category_articles_query, 
                (topic_name, category_name, start_date_str, end_date_str)
            )
            
            # Skip if no articles found (shouldn't happen given our initial query)
            if not category_articles:
                category_insights.append(CategoryInsightSchema(
                    category=category_name,
                    article_count=article_count,
                    insight_text=f"No detailed articles found for analysis in category '{category_name}'."
                ))
                continue
                
            # Prepare article details for LLM
            article_texts = []
            for i, article in enumerate(category_articles):
                title, summary, source, pub_date, sentiment = article
                article_texts.append(
                    f"Article {i+1}:\n"
                    f"  Title: {title or 'Untitled'}\n"
                    f"  Source: {source or 'Unknown'}\n" 
                    f"  Published: {pub_date or 'N/A'}\n"
                    f"  Sentiment: {sentiment or 'Unknown'}\n"
                    f"  Summary: {summary or 'No summary available'}\n"
                )
            
            articles_text = "\n---\n".join(article_texts)
            
            # Check data quality before sending to LLM
            total_content_length = sum(len(str(article[0] or '')) + len(str(article[1] or '')) for article in category_articles)
            avg_content_length = total_content_length / len(category_articles) if category_articles else 0
            
            # If content is too sparse, provide a basic insight without LLM
            if avg_content_length < 50:  # Very short titles/summaries
                logger.warning(f"Category '{category_name}' has sparse content (avg {avg_content_length:.1f} chars), skipping LLM")
                category_insights.append(CategoryInsightSchema(
                    category=category_name,
                    article_count=article_count,
                    insight_text=f"The '{category_name}' category shows {article_count} articles with limited metadata. This suggests emerging or developing content in this area that may need more detailed analysis."
                ))
                continue
            
            # Create prompt for category analysis
            system_prompt = (
                f"You are an expert analyst specializing in '{topic_name}'. "
                f"Analyze the provided articles from the category '{category_name}' and "
                f"provide a concise 2-3 sentence insight about trends, patterns, or notable "
                f"characteristics of this category during this time period. "
                f"Focus on what makes this category distinctive compared to others and identify "
                f"any emerging trends or shifts in focus within the category. "
                f"If the article content is limited, focus on what you can infer from the available information."
            )
            
            user_prompt = (
                f"Here are recent articles from the '{category_name}' category "
                f"within the '{topic_name}' topic to analyze:\n\n{articles_text}\n\n"
                f"Provide a concise insight about this category based on these articles. "
                f"Note: Some articles may have limited content - focus on available information."
            )
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Call LLM to generate category insight
            try:
                logger.info(f"Generating insight for category '{category_name}' with {article_count} articles")
                insight_text = await run_in_threadpool(ai_model.generate_response, messages)
                
                # Check for LLM error messages or very short responses
                if not insight_text or len(insight_text.strip()) < 10:
                    logger.warning(f"LLM returned empty/short response for category '{category_name}'")
                    insight_text = f"The '{category_name}' category contains {article_count} articles. This represents an active area within {topic_name} with ongoing developments."
                elif insight_text and ("⚠️" in insight_text or "unavailable" in insight_text.lower() or "error" in insight_text.lower()):
                    logger.warning(f"LLM returned error for category '{category_name}': {insight_text}")
                    # Provide a more informative fallback based on the data we have
                    sample_titles = [article[0] for article in category_articles[:3] if article[0]]
                    if sample_titles:
                        insight_text = f"The '{category_name}' category shows {article_count} articles including topics like: {', '.join(sample_titles[:2])}. This suggests active development in this area."
                    else:
                        insight_text = f"The '{category_name}' category has {article_count} articles showing activity in this area of {topic_name}."
                
                # Add category with LLM-generated insight
                category_insights.append(CategoryInsightSchema(
                    category=category_name,
                    article_count=article_count,
                    insight_text=insight_text.strip()
                ))
            except Exception as e:
                logger.error(f"Error generating insight for category '{category_name}': {e}", exc_info=True)
                # Add category with more informative error message
                category_insights.append(CategoryInsightSchema(
                    category=category_name,
                    article_count=article_count,
                    insight_text=f"The '{category_name}' category has {article_count} articles. Detailed analysis is temporarily unavailable due to processing issues."
                ))
        
        logger.info(f"Generated insights for {len(category_insights)} categories in topic '{topic_name}'")
        
        # Cache the results for future requests
        try:
            if category_insights:
                # Use first article from temp_response as cache anchor
                temp_response = await get_topic_articles(
                    topic_name=topic_name,
                    page=1,
                    per_page=1,
                    start_date=start_date,
                    end_date=end_date,
                    db=db
                )
                
                if temp_response.items:
                    cache_uri = temp_response.items[0].uri
                    # Convert Pydantic models to dict for JSON serialization
                    cache_content = json.dumps([cat.dict() for cat in category_insights], ensure_ascii=False, default=str)
                    cache_metadata = {
                        "cache_key": cache_key,
                        "topic": topic_name,
                        "start_date": start_date,
                        "end_date": end_date,
                        "days_limit": days_limit,
                        "insight_type": "category_distribution",
                        "category_count": len(category_insights)
                    }
                    
                    success = db.save_article_analysis_cache(
                        article_uri=cache_uri,
                        analysis_type=f"category_insights_{topic_name}",
                        content=cache_content,
                        model_used="dashboard_api",
                        metadata=cache_metadata
                    )
                    
                    if success:
                        logger.info(f"Cache SAVE: category insights for {topic_name}")
                    else:
                        logger.warning(f"Cache SAVE FAILED: category insights for {topic_name}")
        except Exception as cache_error:
            logger.warning(f"Failed to cache category insights: {cache_error}")
        
        return category_insights

    except Exception as e:
        logger.error(f"Error fetching category insights for {topic_name}: {e}", exc_info=True)
        return [] # Return empty list on error

# New endpoint for Word Frequency
@router.get("/word-frequency/{topic_name}", response_model=List[WordFrequencyDataPoint])
async def get_word_frequency(
    topic_name: str,
    db: Database = Depends(get_database_instance),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    days_limit: int = Query(30, ge=1, le=365),
    limit_words: int = Query(50, ge=1, le=200), # How many top words to return
    session: dict = Depends(verify_session)
):
    """
    Provides word frequency counts from article titles and summaries for a given topic and date range.
    Filters out common English stop words.
    """
    logger.info(f"Fetching word frequency for topic: {topic_name}, dates: {start_date}-{end_date}, days: {days_limit}")
    try:
        # 1. Fetch articles for the topic and date range
        # Leveraging the existing get_topic_articles function for consistency
        paginated_response: PaginatedArticleResponse = await get_topic_articles(
            topic_name=topic_name,
            page=1, # Fetch all relevant articles, pagination not needed here for aggregation
            per_page=500, # Fetch up to 500 articles to analyze for word frequency
            start_date=start_date,
            end_date=end_date,
            db=db # Pass the db dependency
        )
        articles = paginated_response.items

        if not articles:
            return []

        # 2. Concatenate relevant text (titles and summaries)
        all_text = " "
        for article in articles:
            if article.title: # Add title if it exists
                all_text += article.title + " "
            if article.summary: # Add summary if it exists
                all_text += article.summary + " "
        
        if not all_text.strip():
            return []

        # 3. Tokenize, filter stop words, and count frequencies
        # Basic tokenization: split by non-alphanumeric characters, convert to lowercase
        words = re.findall(r'\b\w+\b', all_text.lower()) 
        
        # Filter out stop words and very short words (e.g., less than 3 characters)
        filtered_words = [word for word in words if word not in ENGLISH_STOP_WORDS and len(word) > 2]
        
        if not filtered_words:
            return []
            
        word_counts = Counter(filtered_words)
        top_words = word_counts.most_common(limit_words)

        return [WordFrequencyDataPoint(word=word, count=count) for word, count in top_words]

    except Exception as e:
        logger.error(f"Error fetching word frequency for topic {topic_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve word frequency data for topic {topic_name}")

# New endpoint for Radar Chart Data
@router.get("/radar-chart-data/{topic_name}", response_model=RadarChartResponse)
async def get_radar_chart_data(
    topic_name: str,
    db: Database = Depends(get_database_instance),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    days_limit: int = Query(30, ge=1, le=365),
    session: dict = Depends(verify_session)
):
    """
    Provides aggregated data for the radar chart: articles grouped by 
    Future Signal, Sentiment, and Time to Impact.
    """
    logger.info(f"Fetching radar chart data for topic: {topic_name}")
    try:
        end_date_dt = datetime.utcnow() if not end_date else datetime.strptime(end_date, '%Y-%m-%d')
        if start_date:
            start_date_dt = datetime.strptime(start_date, '%Y-%m-%d')
        else:
            start_date_dt = end_date_dt - timedelta(days=days_limit)
        start_date_str = start_date_dt.strftime('%Y-%m-%d')
        end_date_str = end_date_dt.strftime('%Y-%m-%d')

        query = f"""
            SELECT
                future_signal,
                sentiment,
                time_to_impact,
                COUNT(*) as article_count
            FROM articles
            WHERE topic = ?
              AND DATE(submission_date) >= ?
              AND DATE(submission_date) <= ?
              AND future_signal IS NOT NULL AND future_signal != ''
              AND sentiment IS NOT NULL AND sentiment != ''
              AND time_to_impact IS NOT NULL AND time_to_impact != ''
            GROUP BY future_signal, sentiment, time_to_impact
            ORDER BY future_signal, sentiment, time_to_impact;
        """
        raw_data = await run_in_threadpool(db.fetch_all, query, (topic_name, start_date_str, end_date_str))

        if not raw_data:
            return RadarChartResponse(labels=[], datasets=[])

        # Process data for radar chart
        # Radar chart labels are the distinct future signals
        future_signals = sorted(list(set(row['future_signal'] for row in raw_data)))
        
        # We need to create datasets for each sentiment. Each dataset will have a value for each future_signal.
        # The value could be an aggregation, e.g., sum of article_count for that sentiment & future_signal.
        # For simplicity, let's plot article_count directly. TTI can be used for radius/size in frontend.

        sentiment_groups = sorted(list(set(row['sentiment'] for row in raw_data)))
        time_to_impact_map = {"Immediate": 1, "Short-term": 2, "Medium-term": 3, "Long-term": 4, "Unknown": 5} # Example mapping for TTI

        datasets = []
        # Define a color map for sentiments (extend as needed)
        sentiment_colors = {
            "Positive": "rgba(75, 192, 192, 0.6)",
            "Negative": "rgba(255, 99, 132, 0.6)",
            "Neutral": "rgba(201, 203, 207, 0.6)",
            "Mixed": "rgba(255, 159, 64, 0.6)",
            "Critical": "rgba(153, 102, 255, 0.6)",
            "Hyperbolic": "rgba(255, 205, 86, 0.6)",
        }

        for sentiment_val in sentiment_groups:
            data_points_for_sentiment = [] # This will store counts for each future_signal
            point_details = [] # Store {tti_numeric, count} for custom point radius/tooltips

            for fs_label in future_signals:
                # Sum article_counts for this sentiment and future_signal, considering different TTIs
                total_count_for_fs_sentiment = 0
                # Store individual TTI counts for this specific point if needed for complex rendering
                tti_counts_at_point = {}
                for row in raw_data:
                    if row['future_signal'] == fs_label and row['sentiment'] == sentiment_val:
                        total_count_for_fs_sentiment += row['article_count']
                        tti_val = row['time_to_impact']
                        tti_counts_at_point[tti_val] = tti_counts_at_point.get(tti_val, 0) + row['article_count']
                
                data_points_for_sentiment.append(total_count_for_fs_sentiment)
                point_details.append({
                    "label": fs_label,
                    "sentiment": sentiment_val,
                    "total_articles": total_count_for_fs_sentiment,
                    "tti_breakdown": tti_counts_at_point # e.g. {"Immediate": 5, "Short-term": 2}
                })

            datasets.append({
                "label": sentiment_val,
                "data": data_points_for_sentiment,
                "backgroundColor": sentiment_colors.get(sentiment_val, "rgba(54, 162, 235, 0.2)"), # Default color
                "borderColor": sentiment_colors.get(sentiment_val, "rgba(54, 162, 235, 1)").replace("0.2", "1").replace("0.6", "1"), # Solid border
                "borderWidth": 1,
                "pointBackgroundColor": sentiment_colors.get(sentiment_val, "rgba(54, 162, 235, 1)"),
                "pointBorderColor": "#fff",
                "pointHoverBackgroundColor": "#fff",
                "pointHoverBorderColor": sentiment_colors.get(sentiment_val, "rgba(54, 162, 235, 1)"),
                "customData": point_details # Store detailed breakdown here
            })

        return RadarChartResponse(labels=future_signals, datasets=datasets)

    except ValueError as ve:
        logger.error(f"Date format error for radar chart (topic: {topic_name}): {ve}")
        raise HTTPException(status_code=400, detail="Invalid date format. Please use YYYY-MM-DD.")
    except Exception as e:
        logger.error(f"Error fetching radar chart data for topic {topic_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve radar chart data for {topic_name}")

@router.get("/map-activity-data/{topic_name}")
async def get_map_activity_data(
    topic_name: str,
    date_range_str: Optional[str] = Query(None, alias="date_range"),
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
) -> List[MapActivityPoint]:
    """
    Provides country-based data for the global news activity map.
    """
    try:
        # Parse date range if provided
        start_date = None
        end_date = None
        
        if date_range_str:
            date_parts = date_range_str.split(',')
            if len(date_parts) == 2:
                start_date = date_parts[0]
                end_date = date_parts[1]
        
        # Query the database for article counts by country
        # This is a placeholder implementation - in a real scenario, this would query actual data
        # from the database based on article metadata containing country information
        
        # In a real implementation, we would run a query like:
        # query = """
        #     SELECT 
        #         country, 
        #         COUNT(*) as article_count 
        #     FROM articles 
        #     WHERE topic = ? AND publication_date BETWEEN ? AND ?
        #     GROUP BY country
        #     ORDER BY article_count DESC
        # """
        # results = await db.fetch_all(query, (topic_name, start_date, end_date))
        
        # For now, return dummy data that varies slightly based on the topic
        # In a real implementation this would be replaced with actual database queries
        
        # Use topic name to generate semi-random data for demonstration
        import hashlib
        topic_hash = int(hashlib.md5(topic_name.encode()).hexdigest(), 16) % 100
        
        # Countries to include
        countries = [
            'United States', 'United Kingdom', 'Germany', 
            'France', 'China', 'Japan', 'India', 'Brazil', 
            'Russia', 'Australia', 'Canada', 'South Korea'
        ]
        
        # Generate country data based on topic hash
        country_data = []
        for country in countries:
            # Generate a semi-random number of articles based on topic
            country_hash = int(hashlib.md5(f"{topic_name}:{country}".encode()).hexdigest(), 16) % 100
            base_articles = 5 + (country_hash % 20)  # Base between 5-24
            
            # Adjust based on date range if provided (more articles for longer ranges)
            if start_date and end_date:
                try:
                    start = datetime.strptime(start_date, '%Y-%m-%d')
                    end = datetime.strptime(end_date, '%Y-%m-%d')
                    days = (end - start).days
                    # Scale articles up for longer time periods
                    base_articles = int(base_articles * (1 + days / 30))
                except Exception as e:
                    logger.warning(f"Error parsing date range: {e}")
            
            # Determine activity level
            activity_level = "high" if base_articles > 15 else "normal"
            
            # Add to results
            country_data.append(
                MapActivityPoint(
                    country=country,
                    activity_level=activity_level,
                    articles=base_articles
                )
            )
        
        # Sort by article count descending
        country_data.sort(key=lambda x: x.articles, reverse=True)
        
        # Return the top countries (limit to 8 for UI clarity)
        return country_data[:8]
        
    except Exception as e:
        logger.error(f"Error generating map activity data: {e}")
        raise HTTPException(status_code=500, detail="Error generating map data")

# Remember to include this router in your main app (e.g., in app/main.py)
# from app.routes import dashboard_routes
# app.include_router(dashboard_routes.router) 