"""
Science Funding Tracker API Routes

Provides endpoints for the Science Funding Tracker dashboard which analyzes articles
about university grants and science infrastructure using 10 funding category classifications.
Integrates with existing keyword groups system for category tracking.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, date, time as dt_time
from sqlalchemy import text
import logging
import json

from app.security.session import verify_session
from app.database import get_database_instance

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/science-funding", tags=["Science Funding"])


# ============================================================================
# Constants
# ============================================================================

# Default topic for the science funding tracker
DEFAULT_TRACKER_TOPIC = "University Grants & Science Infrastructure Impact"

# Science funding categories with keywords for classification
# Keywords include singular/plural forms and common variations
SCIENCE_CATEGORIES = {
    "Grant Freezes & Cuts": [
        "grant freeze", "funding freeze", "funding cut", "budget cut", "sequestration",
        "continuing resolution", "appropriations", "grant suspension", "funding halt",
        "award suspension", "grant termination", "funding reduction", "grant clawback",
        "indirect cost", "overhead rate", "F&A rate", "cost recovery"
    ],
    "NIH & Biomedical": [
        "NIH", "National Institutes of Health", "biomedical", "clinical trial",
        "cancer research", "Alzheimer", "genomics", "NIAID", "NCI", "NIMH", "NHLBI",
        "biomedical research", "drug development", "pharmaceutical", "Collins",
        "Berger", "Tabak"
    ],
    "NSF & Basic Science": [
        "NSF", "National Science Foundation", "basic research", "fundamental research",
        "STEM", "physics", "mathematics", "chemistry", "peer review", "merit review",
        "research proposal", "principal investigator", "R01", "R21", "grant application"
    ],
    "DOE & Energy Research": [
        "DOE", "Department of Energy", "national laboratory", "national lab", "Argonne",
        "Brookhaven", "Fermilab", "Los Alamos", "Oak Ridge", "Sandia", "SLAC",
        "Lawrence Livermore", "ARPA-E", "fusion", "nuclear", "clean energy",
        "renewable energy"
    ],
    "University Impact": [
        "university", "universities", "college", "colleges", "higher education",
        "research university", "R1", "tenure", "provost", "chancellor", "endowment",
        "tuition", "campus", "academic freedom", "faculty", "professor", "postdoc",
        "graduate student", "dissertation"
    ],
    "Brain Drain & Workforce": [
        "brain drain", "researcher exodus", "scientist leaving", "talent loss", "visa",
        "H-1B", "J-1", "OPT", "international student", "foreign researcher",
        "recruitment", "retention", "early career", "young scientist", "postdoctoral",
        "workforce", "STEM pipeline"
    ],
    "Climate & Environmental": [
        "climate", "climate science", "climate change", "global warming", "EPA", "NOAA",
        "carbon", "emissions", "Paris Agreement", "sustainability", "environmental",
        "ecology", "biodiversity", "conservation", "endangered species", "pollution",
        "clean air", "clean water"
    ],
    "DEI & Ideological Targeting": [
        "DEI", "diversity equity inclusion", "affirmative action", "woke", "ideological",
        "political litmus", "viewpoint diversity", "critical race theory", "CRT",
        "social justice", "equity mandate", "diversity statement", "diversity requirement"
    ],
    "Public Health & Medical": [
        "CDC", "FDA", "public health", "pandemic", "vaccine", "vaccination",
        "infectious disease", "epidemiology", "health research", "drug approval",
        "clinical research", "health disparities", "maternal health", "mental health",
        "opioid", "RFK", "Kennedy"
    ],
    "International Collaboration": [
        "international collaboration", "research partnership", "foreign government",
        "scientific cooperation", "academic exchange", "Fulbright", "bilateral",
        "multilateral", "CERN", "WHO", "joint research", "foreign funding",
        "China Initiative", "research security"
    ]
}


# Themes from science funding analysis
THEMES = {
    "Federal Agencies": [
        "NIH", "NSF", "DOE", "EPA", "NOAA", "NASA", "CDC", "FDA"
    ],
    "National Labs": [
        "Argonne", "Brookhaven", "Fermilab", "Los Alamos", "Oak Ridge", "Sandia",
        "SLAC", "Lawrence Livermore", "Lawrence Berkeley"
    ],
    "Elite Universities": [
        "Harvard", "MIT", "Stanford", "Yale", "Princeton", "Columbia",
        "Johns Hopkins", "Caltech", "Berkeley", "University of Michigan"
    ],
    "Research Fields": [
        "cancer", "Alzheimer", "climate", "AI", "quantum", "fusion", "genomics",
        "neuroscience"
    ],
    "Policy Mechanisms": [
        "executive order", "appropriations", "continuing resolution", "sequestration",
        "indirect cost"
    ],
    "Workforce": [
        "postdoc", "graduate student", "tenure", "faculty", "international student"
    ]
}

# Entities to track
TRACKED_ENTITIES = [
    "NIH", "NSF", "DOE", "EPA", "NOAA", "NASA", "CDC", "FDA", "OSTP", "OMB",
    "DOGE", "Congress", "ARPA-E", "DARPA", "Howard Hughes Medical Institute"
]

# Escalation markers for science funding
ESCALATION_MARKERS = {
    "Funding Actions": [
        "freeze", "cut", "suspend", "terminate", "cancel", "defund", "slash",
        "eliminate", "zero out"
    ],
    "Institutional Threats": [
        "close", "shut down", "merge", "restructure", "downsize", "reorganize",
        "abolish"
    ],
    "Personnel Actions": [
        "fire", "lay off", "reassign", "demote", "investigate", "retaliate",
        "gag order", "silence"
    ],
    "Policy Escalation": [
        "executive order", "emergency", "override", "bypass", "waive", "exempt",
        "prohibit"
    ],
    "Rhetoric": [
        "wasteful", "fraud", "politicized", "indoctrination", "hoax", "unnecessary",
        "bloated"
    ]
}

# Geographic focus locations
US_LOCATIONS = [
    "Massachusetts", "California", "Maryland", "North Carolina", "New York",
    "Texas", "Illinois", "Pennsylvania", "Michigan", "Wisconsin"
]
INTERNATIONAL_LOCATIONS = [
    "China", "EU", "UK", "Japan", "South Korea", "Canada", "Australia",
    "Switzerland", "Germany", "India"
]


# ============================================================================
# LLM Semantic Analysis Prompts
# ============================================================================

CATEGORY_DEFINITIONS = """
## Science Funding Category Definitions

These are the 10 categories used to classify articles about science funding and research infrastructure. Use the EXACT category names shown:

1. **Grant Freezes & Cuts** - Federal grant freezes, funding cuts, sequestration impacts, appropriations battles, indirect cost rate changes, award suspensions, and clawback actions affecting research funding.

2. **NIH & Biomedical** - Actions involving the National Institutes of Health, biomedical research funding, clinical trials, cancer/Alzheimer's/genomics research, and NIH institute-level impacts (NIAID, NCI, NIMH, NHLBI).

3. **NSF & Basic Science** - National Science Foundation funding, basic/fundamental research, STEM education support, peer review processes, merit review, and impacts on principal investigators and grant applications.

4. **DOE & Energy Research** - Department of Energy programs, national laboratory operations (Argonne, Brookhaven, Fermilab, Los Alamos, Oak Ridge, Sandia, SLAC, Lawrence Livermore), ARPA-E, fusion research, nuclear science, and clean/renewable energy research.

5. **University Impact** - Effects on universities and colleges, higher education institutions, research universities (R1), tenure systems, endowments, academic freedom, faculty and graduate student impacts.

6. **Brain Drain & Workforce** - Researcher exodus, talent loss, visa issues (H-1B, J-1, OPT), international student/researcher recruitment and retention, early career scientists, postdoctoral workforce, and STEM pipeline concerns.

7. **Climate & Environmental** - Climate science, climate change research, EPA/NOAA programs, carbon/emissions research, Paris Agreement implications, environmental science, ecology, biodiversity, and conservation research funding.

8. **DEI & Ideological Targeting** - Diversity equity and inclusion mandates in research, affirmative action in academia, ideological litmus tests, viewpoint diversity debates, critical race theory in universities, and diversity statement requirements.

9. **Public Health & Medical** - CDC and FDA research programs, pandemic preparedness, vaccine research, infectious disease studies, epidemiology funding, drug approval processes, health disparities research, and public health infrastructure.

10. **International Collaboration** - International research partnerships, scientific cooperation agreements, academic exchanges (Fulbright), multilateral research programs (CERN, WHO), foreign funding concerns, China Initiative impacts, and research security measures.
"""

SEMANTIC_CATEGORIZATION_PROMPT = """You are a science policy analyst classifying news articles about science funding and research infrastructure impacts.

{category_definitions}

## Task
Analyze the following article and classify it into ALL applicable categories. Most articles fall into 1-4 categories. Use the EXACT category names listed above.

**Article Title:** {title}

**Article Summary:** {summary}

## Response Format
Return a JSON object with:
- "categories": array of EXACT category names that apply (use full names from the list above)
- "confidence": number 0-1 indicating classification confidence
- "reasoning": brief explanation of why each category applies

Example response:
{{"categories": ["Grant Freezes & Cuts", "NIH & Biomedical"], "confidence": 0.85, "reasoning": "NIH grant freeze directly impacts biomedical research funding pipelines."}}

Respond ONLY with valid JSON, no other text."""

NARRATIVE_ANALYSIS_PROMPT = """You are generating an analytical narrative report on science funding data for decision-makers monitoring the health of the US research enterprise.

## Analytical Framework

This analysis operates under the following working assumptions based on documented patterns:

1. **Research Enterprise Vulnerability**: The US scientific research enterprise depends on stable, predictable federal funding. Disruptions cascade through universities, national labs, and the broader innovation ecosystem with multi-year consequences.

2. **Brain Drain Acceleration**: When funding becomes unreliable or politicized, top researchers - especially early-career scientists and international talent - leave for more stable environments. This talent loss is difficult to reverse.

3. **Institutional Erosion**: Federal science agencies (NIH, NSF, DOE, EPA, NOAA) represent decades of accumulated expertise. Defunding, reorganization, or political interference can destroy institutional capacity that takes generations to rebuild.

4. **Global Competition**: Other nations (China, EU, South Korea, Japan) are increasing research investment. US funding cuts don't just slow American science - they accelerate competitors who recruit displaced talent and fill research gaps.

Be analytical and evidence-based. Identify patterns that suggest coordinated defunding efforts vs. routine budget fluctuations. Connect funding actions to downstream impacts on research, workforce, and international competitiveness.

## Data Summary

**Time Period:** {date_range}
**Total Articles Analyzed:** {total_articles}

**Category Distribution:**
{category_breakdown}

**Top Themes:**
{themes_breakdown}

**Escalation Indicators:**
{escalation_breakdown}

**Key Entities Mentioned:**
{entities_breakdown}

**Geographic Focus:**
{geography_breakdown}

## Required Sections

Write a comprehensive analytical narrative (800-1200 words) with these EXACT section headers (use ## markdown format):

## Executive Summary
Key findings in 3-4 sentences. What is the most concerning pattern for the US research enterprise? What requires immediate attention?

## Funding Trend Analysis
What patterns emerge from the category distribution? Which funding areas are under greatest pressure? How do the numbers reflect broader policy directions? Use paragraphs for this analysis.

## Thematic Spotlight
YOU MUST use bullet points in this section. Format EXACTLY like this:

- **NIH Funding Crisis**: [Analysis of biomedical research funding impacts with specific numbers]
- **National Lab Workforce**: [Analysis of DOE lab impacts and personnel actions]
- **University Fallout**: [Analysis of how funding changes cascade to higher education]

Analyze 2-3 dominant themes. Each theme MUST be a bullet point starting with "- **Theme Name**:"

## Escalation Assessment
Analyze escalation indicators. Are funding cuts deepening? Are new agencies being targeted? Is rhetoric against science intensifying? What patterns suggest this is coordinated vs. routine?

## Institutional Impact
YOU MUST use bullet points in this section. Format EXACTLY like this:

- **NIH/Biomedical Research**: [How biomedical funding changes affect disease research and clinical trials]
- **National Laboratories**: [Impact on DOE labs, nuclear science, energy research]
- **University Research Enterprise**: [Cascading effects on graduate programs, tenure, research capacity]

List the main institutional targets with analysis of downstream impacts.

## Forward-Looking Concerns
YOU MUST use bullet points in this section. Format EXACTLY like this:

- **Brain Drain Acceleration**: Monitor for increased researcher departures to industry or international institutions
- **Grant Pipeline Collapse**: Watch for declining grant applications as researchers lose confidence in federal funding
- **International Competitiveness**: Track how US funding cuts affect global research leadership rankings
- **Workforce Pipeline**: Monitor graduate program enrollment declines and postdoc position eliminations

List 4-6 specific forward-looking concerns. Each MUST be a bullet starting with "- **Concern Title**:" followed by explanation.

CRITICAL FORMATTING REQUIREMENTS:
- Use ## for section headers (H2 markdown)
- MANDATORY: Thematic Spotlight MUST use bullet points (- **Theme**: analysis)
- MANDATORY: Institutional Impact MUST use bullet points (- **Institution**: analysis)
- MANDATORY: Forward-Looking Concerns MUST use bullet points (- **Concern**: explanation)
- Use **bold** for the title/header of each bullet point
- Include specific numbers from the data
- Be analytical and evidence-based, not neutral
- Connect data points to the broader pattern of research enterprise health

IF YOU DO NOT USE BULLET POINTS IN SECTIONS 3, 5, AND 6, THE RESPONSE WILL BE REJECTED."""

CATEGORY_INSIGHT_PROMPT = """You are a science policy analyst providing insights on a specific science funding category.

## Category: {category_name}

**Articles in this category:** {article_count}
**Percentage of total:** {percentage}%
**Recent trend:** {trend}

**Sample article titles from this category:**
{sample_titles}

## Task
Write a brief analytical insight (150-250 words) covering:
1. What this category captures and why it matters for the research enterprise
2. Analysis of the current volume and trend
3. Key sub-themes within this category based on the sample titles
4. Connections to other science funding areas

Be specific and analytical, not generic."""


# ============================================================================
# Request/Response Models
# ============================================================================

class ScienceStatsResponse(BaseModel):
    """Overview statistics for the science funding tracker."""
    total_articles: int
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    most_active_category: Optional[str] = None
    multi_category_count: int = 0  # Articles with 3+ categories
    category_breakdown: Dict[str, int] = {}


class ScienceCategoryResponse(BaseModel):
    """Category distribution data."""
    category: str
    article_count: int
    percentage: float
    recent_trend: str = "stable"  # up, down, stable


class ScienceArticleResponse(BaseModel):
    """Article data for the science funding tracker."""
    uri: str
    title: str
    summary: Optional[str] = None
    news_source: Optional[str] = None
    publication_date: Optional[str] = None
    categories: List[str] = []
    sentiment: Optional[str] = None
    bias: Optional[str] = None
    factual_reporting: Optional[str] = None


class ScienceArticlesListResponse(BaseModel):
    """Paginated list of articles."""
    articles: List[ScienceArticleResponse]
    total_count: int
    page: int
    per_page: int
    total_pages: int


class TemporalDataResponse(BaseModel):
    """Time series data for charts."""
    month: str
    total: int
    by_category: Dict[str, int] = {}


class RelatedArticleResponse(BaseModel):
    """Related article from vector search."""
    uri: str
    title: str
    summary: Optional[str] = None
    news_source: Optional[str] = None
    publication_date: Optional[str] = None
    topic: Optional[str] = None
    similarity_score: float


class SearchResultResponse(BaseModel):
    """Semantic search result."""
    articles: List[ScienceArticleResponse]
    total_count: int
    query: str


class ClassifyRequest(BaseModel):
    """Request for article classification."""
    topic: str = DEFAULT_TRACKER_TOPIC
    run_type: str = "incremental"  # full or incremental
    days_back: int = 30


class ClassifyResponse(BaseModel):
    """Response from classification run."""
    run_id: int
    status: str
    articles_processed: int
    articles_categorized: int
    message: str


class TrendDataResponse(BaseModel):
    """Daily trend data for a category."""
    date: str
    article_count: int
    new_articles: int


# ============================================================================
# Helper Functions
# ============================================================================

def _categorize_article_keywords(title: str, summary: str) -> List[str]:
    """
    Categorize an article based on keyword matching.
    Returns list of matching category names (display format).
    Uses word boundary matching for short keywords to avoid false positives.
    """
    import re
    text_content = f"{title} {summary}".lower()
    matched_categories = []

    for category, keywords in SCIENCE_CATEGORIES.items():
        for keyword in keywords:
            kw_lower = keyword.lower()
            if len(kw_lower) <= 3:
                # Short keywords (NIH, NSF, DOE, EPA, etc.) need word boundaries
                pattern = r'\b' + re.escape(kw_lower) + r'\b'
                if re.search(pattern, text_content):
                    matched_categories.append(category)
                    break
            else:
                # Longer keywords/phrases can use substring matching
                if kw_lower in text_content:
                    matched_categories.append(category)
                    break

    return matched_categories


def categorize_article(title: str, summary: str) -> List[str]:
    """
    Categorize an article into science funding categories.

    Uses keyword matching to classify articles.

    Args:
        title: Article title
        summary: Article summary/content

    Returns:
        List of category names (display format, e.g., "Grant Freezes & Cuts")
    """
    return _categorize_article_keywords(title, summary)


# ============================================================================
# Service Functions (for use by other modules like automated_ingest_service)
# ============================================================================

def categorize_article_sync(
    article_uri: str,
    title: str,
    summary: str,
    topic: str = None,
    llm_model: str = None
) -> List[str]:
    """
    Categorize an article into science funding categories and store the results.

    This function can be called from the automated ingest pipeline to
    automatically categorize articles after they pass relevance scoring.

    Args:
        article_uri: Unique identifier for the article
        title: Article title
        summary: Article summary/content
        topic: Topic name (default: University Grants & Science Infrastructure)
        llm_model: Optional specific LLM model to use (reserved for future use)

    Returns:
        List of matched category names
    """
    if topic is None:
        topic = DEFAULT_TRACKER_TOPIC

    classification_method = "keyword"
    categories = _categorize_article_keywords(title, summary)

    # Store categories in database
    if categories:
        db = get_database_instance()
        conn = db._temp_get_connection()
        try:
            for category in categories:
                try:
                    conn.execute(text("""
                        INSERT INTO science_article_categories
                        (article_uri, category, topic, classification_method)
                        VALUES (:uri, :category, :topic, :method)
                        ON CONFLICT (article_uri, category) DO NOTHING
                    """), {
                        "uri": article_uri,
                        "category": category,
                        "topic": topic,
                        "method": classification_method
                    })
                except Exception as e:
                    logger.warning(f"Failed to store category {category} for {article_uri}: {e}")
            conn.commit()
            logger.info(f"Categorized article {article_uri} ({classification_method}) into {len(categories)} categories: {categories}")
        finally:
            conn.close()

    return categories


async def categorize_article_async(
    article_uri: str,
    title: str,
    summary: str,
    topic: str = None,
    use_llm: bool = False,
    conn = None
) -> List[str]:
    """
    Async version of categorize_article_sync for use in async pipelines.

    Args:
        article_uri: Unique identifier for the article
        title: Article title
        summary: Article summary/content
        topic: Topic name
        use_llm: If True, use LLM for categorization (future)
        conn: Optional existing database connection to reuse

    Returns:
        List of matched category names
    """
    import asyncio

    if topic is None:
        topic = DEFAULT_TRACKER_TOPIC

    # Use keyword-based categorization (fast, synchronous)
    categories = categorize_article(title, summary)

    if not categories:
        return []

    # Store categories - run in thread pool if no connection provided
    if conn:
        # Use provided connection
        for category in categories:
            try:
                conn.execute(text("""
                    INSERT INTO science_article_categories
                    (article_uri, category, topic, classification_method)
                    VALUES (:uri, :category, :topic, :method)
                    ON CONFLICT (article_uri, category) DO NOTHING
                """), {
                    "uri": article_uri,
                    "category": category,
                    "topic": topic,
                    "method": "keyword"
                })
            except Exception as e:
                logger.warning(f"Failed to store category {category} for {article_uri}: {e}")
    else:
        # Run synchronous DB operation in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: _store_categories_sync(article_uri, categories, topic)
        )

    logger.debug(f"Categorized {article_uri} into {len(categories)} categories")
    return categories


def _store_categories_sync(article_uri: str, categories: List[str], topic: str):
    """Helper to store categories synchronously."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        for category in categories:
            try:
                conn.execute(text("""
                    INSERT INTO science_article_categories
                    (article_uri, category, topic, classification_method)
                    VALUES (:uri, :category, :topic, 'keyword')
                    ON CONFLICT (article_uri, category) DO NOTHING
                """), {"uri": article_uri, "category": category, "topic": topic})
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()


def is_science_tracker_topic(topic: str) -> bool:
    """Check if a topic is the science funding tracker topic."""
    return topic == DEFAULT_TRACKER_TOPIC


# ============================================================================
# Additional Helper Functions
# ============================================================================

def get_date_range_filter(days_back: int = 30) -> tuple:
    """
    Get start and end dates for filtering.

    Args:
        days_back: Number of days to look back. If 0, returns '1900-01-01' for start_date (all time).

    Returns:
        Tuple of (start_date, end_date) as strings.
    """
    end_date = datetime.now()
    if days_back == 0:
        # All time - return a very old date so existing queries work unchanged
        return '1900-01-01', end_date.strftime('%Y-%m-%d')
    start_date = end_date - timedelta(days=days_back)
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')


def get_stored_categories(conn, article_uris: List[str]) -> Dict[str, List[str]]:
    """Get stored categories for a list of article URIs."""
    if not article_uris:
        return {}

    # Build placeholders for IN clause
    placeholders = ', '.join([f':uri_{i}' for i in range(len(article_uris))])
    params = {f'uri_{i}': uri for i, uri in enumerate(article_uris)}

    result = conn.execute(text(f"""
        SELECT article_uri, category
        FROM science_article_categories
        WHERE article_uri IN ({placeholders})
    """), params)

    # Group by article_uri
    categories_map: Dict[str, List[str]] = {}
    for row in result.fetchall():
        uri, category = row
        if uri not in categories_map:
            categories_map[uri] = []
        categories_map[uri].append(category)

    return categories_map


def store_article_categories(conn, article_uri: str, categories: List[str], topic: str):
    """Store categories for an article."""
    for category in categories:
        try:
            conn.execute(text("""
                INSERT INTO science_article_categories (article_uri, category, topic, classification_method)
                VALUES (:uri, :category, :topic, 'keyword')
                ON CONFLICT (article_uri, category) DO NOTHING
            """), {"uri": article_uri, "category": category, "topic": topic})
        except Exception as e:
            logger.warning(f"Failed to store category {category} for {article_uri}: {e}")


def update_daily_stats(conn, topic: str, category: str, stat_date: date, count: int, new_count: int = 0):
    """Update daily stats for a category."""
    conn.execute(text("""
        INSERT INTO science_category_daily_stats (date, topic, category, article_count, new_articles_count)
        VALUES (:date, :topic, :category, :count, :new_count)
        ON CONFLICT (date, topic, category)
        DO UPDATE SET
            article_count = :count,
            new_articles_count = science_category_daily_stats.new_articles_count + :new_count,
            updated_at = NOW()
    """), {"date": stat_date, "topic": topic, "category": category, "count": count, "new_count": new_count})


# ============================================================================
# Classification Endpoints
# ============================================================================

@router.post("/classify", response_model=ClassifyResponse)
async def classify_articles(
    request: ClassifyRequest,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session)
):
    """
    Run classification on articles and store results.

    - full: Re-classify all articles for the topic
    - incremental: Only classify articles not yet categorized
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Create a run record
        result = conn.execute(text("""
            INSERT INTO science_tracker_runs (topic, run_type, status)
            VALUES (:topic, :run_type, 'running')
            RETURNING id
        """), {"topic": request.topic, "run_type": request.run_type})
        run_id = result.fetchone()[0]
        conn.commit()

        # Run classification in background
        background_tasks.add_task(
            run_classification_task,
            run_id,
            request.topic,
            request.run_type,
            request.days_back
        )

        return ClassifyResponse(
            run_id=run_id,
            status="running",
            articles_processed=0,
            articles_categorized=0,
            message="Classification started in background"
        )

    except Exception as e:
        logger.error(f"Error starting classification: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


async def run_classification_task(run_id: int, topic: str, run_type: str, days_back: int):
    """Background task to classify articles using SLM-first, LLM fallback, keyword last resort."""
    import asyncio

    db = get_database_instance()
    conn = db._temp_get_connection()

    # Try loading the SLM classifier
    slm_available = False
    try:
        from app.services.science_funding_classifier_service import get_science_funding_classifier
        slm = get_science_funding_classifier()
        slm_available = slm.is_available()
        if slm_available:
            logger.info("SLM classifier available - using SLM-first classification")
        else:
            logger.info("SLM classifier not available - using LLM-first classification")
    except Exception as e:
        logger.info(f"SLM classifier not loaded ({e}) - using LLM-first classification")

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get articles to classify (only enriched articles that passed relevance scoring)
        if run_type == "full":
            # Get all enriched articles
            result = conn.execute(text("""
                SELECT uri, title, summary
                FROM articles
                WHERE topic = :topic
                AND publication_date >= :start_date
                AND publication_date <= :end_date
                AND category IS NOT NULL AND category != ''
            """), {"topic": topic, "start_date": start_date, "end_date": end_date})
        else:
            # Get only uncategorized enriched articles
            result = conn.execute(text("""
                SELECT a.uri, a.title, a.summary
                FROM articles a
                LEFT JOIN science_article_categories sac ON a.uri = sac.article_uri
                WHERE a.topic = :topic
                AND a.publication_date >= :start_date
                AND a.publication_date <= :end_date
                AND a.category IS NOT NULL AND a.category != ''
                AND sac.id IS NULL
            """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        articles = result.fetchall()
        total_articles = len(articles)
        articles_processed = 0
        articles_categorized = 0
        today = date.today()

        # Update run record with total count
        conn.execute(text("""
            UPDATE science_tracker_runs
            SET articles_processed = 0, articles_categorized = 0
            WHERE id = :run_id
        """), {"run_id": run_id})
        conn.commit()

        # Classify each article: SLM -> LLM -> keyword
        for uri, title, summary in articles:
            articles_processed += 1
            text_input = title or ''
            if summary:
                text_input = f"{title}. {summary}" if title else summary

            categories = []
            method = "keyword"
            confidence = None

            # Step 1: Try SLM (fast, free)
            if slm_available:
                try:
                    slm_result = slm.classify(text_input, return_scores=True)
                    categories = slm_result.get("categories", [])
                    if categories:
                        method = "slm"
                        # Average of scores for matched categories
                        scores = slm_result.get("scores", {})
                        if scores:
                            matched_scores = [scores[c] for c in categories if c in scores]
                            confidence = sum(matched_scores) / len(matched_scores) if matched_scores else 0.7
                except Exception as e:
                    logger.debug(f"SLM failed for {uri}: {e}")

            # Step 2: Fall back to LLM if SLM returned nothing
            if not categories:
                try:
                    await asyncio.sleep(0.3)
                    llm_result = await llm_categorize_article(title or '', summary or '')
                    categories = llm_result.get("categories", [])
                    method = "llm_semantic"
                    confidence = llm_result.get("confidence", 0.7)
                except Exception as e:
                    logger.warning(f"LLM classification failed for {uri}: {e}")

            # Step 3: Fall back to keywords
            if not categories:
                categories = _categorize_article_keywords(title or '', summary or '')
                method = "keyword"
                confidence = None

            if categories:
                for category in categories:
                    try:
                        conn.execute(text("""
                            INSERT INTO science_article_categories
                            (article_uri, category, topic, classification_method, confidence)
                            VALUES (:uri, :category, :topic, :method, :confidence)
                            ON CONFLICT (article_uri, category)
                            DO UPDATE SET
                                classification_method = :method,
                                confidence = :confidence,
                                classified_at = NOW()
                        """), {
                            "uri": uri,
                            "category": category,
                            "topic": topic,
                            "method": method,
                            "confidence": confidence
                        })
                    except Exception as e:
                        logger.warning(f"Failed to store category {category} for {uri}: {e}")
                articles_categorized += 1

            # Update progress every 25 articles
            if articles_processed % 25 == 0 or articles_processed == total_articles:
                conn.commit()
                conn.execute(text("""
                    UPDATE science_tracker_runs
                    SET articles_processed = :processed,
                        articles_categorized = :categorized
                    WHERE id = :run_id
                """), {"run_id": run_id, "processed": articles_processed, "categorized": articles_categorized})
                conn.commit()

        # Final commit
        conn.commit()

        # Update daily stats
        category_counts: Dict[str, int] = {cat: 0 for cat in SCIENCE_CATEGORIES.keys()}
        result = conn.execute(text("""
            SELECT category, COUNT(*) as count
            FROM science_article_categories
            WHERE topic = :topic
            GROUP BY category
        """), {"topic": topic})

        for row in result.fetchall():
            category_counts[row[0]] = row[1]

        for category, count in category_counts.items():
            update_daily_stats(conn, topic, category, today, count, 0)

        conn.commit()

        # Update run record
        conn.execute(text("""
            UPDATE science_tracker_runs
            SET status = 'completed',
                completed_at = NOW(),
                articles_processed = :processed,
                articles_categorized = :categorized
            WHERE id = :run_id
        """), {"run_id": run_id, "processed": articles_processed, "categorized": articles_categorized})
        conn.commit()

        logger.info(f"Classification run {run_id} completed: {articles_processed} processed, {articles_categorized} categorized")

    except Exception as e:
        logger.error(f"Classification run {run_id} failed: {e}")
        conn.execute(text("""
            UPDATE science_tracker_runs
            SET status = 'failed', error_message = :error, completed_at = NOW()
            WHERE id = :run_id
        """), {"run_id": run_id, "error": str(e)})
        conn.commit()
    finally:
        conn.close()


@router.get("/classify/status/{run_id}")
async def get_classification_status(
    run_id: int,
    session=Depends(verify_session)
):
    """Get the status of a classification run."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        result = conn.execute(text("""
            SELECT id, topic, started_at, completed_at, articles_processed,
                   articles_categorized, status, error_message, run_type
            FROM science_tracker_runs
            WHERE id = :run_id
        """), {"run_id": run_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")

        return {
            "run_id": row[0],
            "topic": row[1],
            "started_at": str(row[2]) if row[2] else None,
            "completed_at": str(row[3]) if row[3] else None,
            "articles_processed": row[4],
            "articles_categorized": row[5],
            "status": row[6],
            "error_message": row[7],
            "run_type": row[8]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting classification status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/classify/runs")
async def get_classification_runs(
    limit: int = Query(10, ge=1, le=50, description="Number of recent runs to return"),
    session=Depends(verify_session)
):
    """Get recent classification runs."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        result = conn.execute(text("""
            SELECT id, topic, started_at, completed_at, articles_processed,
                   articles_categorized, status, error_message, run_type
            FROM science_tracker_runs
            ORDER BY started_at DESC
            LIMIT :limit
        """), {"limit": limit})

        runs = []
        for row in result.fetchall():
            runs.append({
                "run_id": row[0],
                "topic": row[1],
                "started_at": str(row[2]) if row[2] else None,
                "completed_at": str(row[3]) if row[3] else None,
                "articles_processed": row[4],
                "articles_categorized": row[5],
                "status": row[6],
                "error_message": row[7],
                "run_type": row[8]
            })

        return {"runs": runs}

    except Exception as e:
        logger.error(f"Error getting classification runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/trends", response_model=Dict[str, List[TrendDataResponse]])
async def get_category_trends(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """
    Get daily trend data for all categories from stored stats.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date = (datetime.now() - timedelta(days=days_back)).date()

        result = conn.execute(text("""
            SELECT date, category, article_count, new_articles_count
            FROM science_category_daily_stats
            WHERE topic = :topic
            AND date >= :start_date
            ORDER BY date ASC
        """), {"topic": topic, "start_date": start_date})

        # Group by category
        trends: Dict[str, List[TrendDataResponse]] = {cat: [] for cat in SCIENCE_CATEGORIES.keys()}

        for row in result.fetchall():
            stat_date, category, count, new_count = row
            if category in trends:
                trends[category].append(TrendDataResponse(
                    date=str(stat_date),
                    article_count=count,
                    new_articles=new_count
                ))

        return trends

    except Exception as e:
        logger.error(f"Error fetching category trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Data Retrieval Endpoints (using stored data when available)
# ============================================================================

@router.get("/stats", response_model=ScienceStatsResponse)
async def get_science_stats(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """
    Get overview statistics for the science funding tracker.
    Uses efficient SQL aggregation instead of loading all articles into memory.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get category counts using efficient JOIN and GROUP BY
        category_result = conn.execute(text("""
            SELECT sac.category, COUNT(DISTINCT sac.article_uri) as count
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            GROUP BY sac.category
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        category_counts: Dict[str, int] = {cat: 0 for cat in SCIENCE_CATEGORIES.keys()}
        for row in category_result.fetchall():
            category, count = row
            if category in category_counts:
                category_counts[category] = count

        # Get total articles with categories and multi-category count
        stats_result = conn.execute(text("""
            SELECT
                COUNT(DISTINCT a.uri) as total_articles,
                MIN(a.publication_date) as date_start,
                MAX(a.publication_date) as date_end,
                SUM(CASE WHEN cat_counts.cat_count >= 3 THEN 1 ELSE 0 END) as multi_category_count
            FROM articles a
            JOIN (
                SELECT article_uri, COUNT(*) as cat_count
                FROM science_article_categories
                WHERE topic = :topic
                GROUP BY article_uri
            ) cat_counts ON a.uri = cat_counts.article_uri
            WHERE a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        stats_row = stats_result.fetchone()
        total_articles = stats_row[0] or 0
        actual_start = str(stats_row[1]) if stats_row[1] else None
        actual_end = str(stats_row[2]) if stats_row[2] else None
        multi_category_count = stats_row[3] or 0

        # Find most active category
        most_active = max(category_counts.items(), key=lambda x: x[1]) if category_counts else (None, 0)

        return ScienceStatsResponse(
            total_articles=total_articles,
            date_range_start=actual_start,
            date_range_end=actual_end,
            most_active_category=most_active[0] if most_active[1] > 0 else None,
            multi_category_count=multi_category_count,
            category_breakdown=category_counts
        )

    except Exception as e:
        logger.error(f"Error fetching science funding stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/articles", response_model=ScienceArticlesListResponse)
async def get_science_articles(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    categories: Optional[str] = Query(None, description="Comma-separated category filter"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    sort_by: str = Query("date", description="Sort by: date, relevance, category_count"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    session=Depends(verify_session)
):
    """
    Get paginated list of articles for the science funding tracker.
    Uses efficient SQL with JOINs and pagination.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)
        category_filter = [c.strip() for c in categories.split(',')] if categories else None
        offset = (page - 1) * per_page

        # Build the base query with category counts
        base_query = """
            WITH article_cats AS (
                SELECT a.uri, a.title, a.summary, a.news_source, a.publication_date,
                       a.sentiment, a.bias, a.factual_reporting,
                       ARRAY_AGG(sac.category) as categories,
                       COUNT(sac.category) as category_count
                FROM articles a
                JOIN science_article_categories sac ON a.uri = sac.article_uri
                WHERE sac.topic = :topic
                AND a.publication_date >= :start_date
                AND a.publication_date <= :end_date
                AND a.category IS NOT NULL AND a.category != ''
                {category_filter_clause}
                GROUP BY a.uri, a.title, a.summary, a.news_source, a.publication_date,
                         a.sentiment, a.bias, a.factual_reporting
            )
        """

        # Add category filter if specified
        if category_filter:
            # Filter articles that have at least one of the specified categories
            category_placeholders = ', '.join([f':cat_{i}' for i in range(len(category_filter))])
            category_filter_clause = f"AND sac.category IN ({category_placeholders})"
            params = {
                "topic": topic,
                "start_date": start_date,
                "end_date": end_date,
                "per_page": per_page,
                "offset": offset
            }
            for i, cat in enumerate(category_filter):
                params[f'cat_{i}'] = cat
        else:
            category_filter_clause = ""
            params = {
                "topic": topic,
                "start_date": start_date,
                "end_date": end_date,
                "per_page": per_page,
                "offset": offset
            }

        base_query = base_query.format(category_filter_clause=category_filter_clause)

        # Get total count
        count_query = base_query + "SELECT COUNT(*) FROM article_cats"
        count_result = conn.execute(text(count_query), params)
        total_count = count_result.scalar() or 0
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 0

        # Determine sort order
        if sort_by == "category_count":
            order_clause = "ORDER BY category_count DESC, publication_date DESC"
        else:  # date
            order_clause = "ORDER BY publication_date DESC"

        # Get paginated articles
        articles_query = base_query + f"""
            SELECT uri, title, summary, news_source, publication_date,
                   sentiment, bias, factual_reporting, categories, category_count
            FROM article_cats
            {order_clause}
            LIMIT :per_page OFFSET :offset
        """

        result = conn.execute(text(articles_query), params)

        articles = []
        for row in result.fetchall():
            uri, title, summary, source, pub_date, sentiment, bias, factual, cats, cat_count = row
            articles.append(ScienceArticleResponse(
                uri=uri,
                title=title,
                summary=summary,
                news_source=source,
                publication_date=str(pub_date) if pub_date else None,
                categories=list(cats) if cats else [],
                sentiment=sentiment,
                bias=bias,
                factual_reporting=factual
            ))

        return ScienceArticlesListResponse(
            articles=articles,
            total_count=total_count,
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )

    except Exception as e:
        logger.error(f"Error fetching science funding articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/categories", response_model=List[ScienceCategoryResponse])
async def get_category_distribution(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """
    Get distribution of articles across science funding categories.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Try to get from stored categories first
        result = conn.execute(text("""
            SELECT sac.category, COUNT(DISTINCT sac.article_uri) as count
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            GROUP BY sac.category
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        stored_counts = {row[0]: row[1] for row in result.fetchall()}

        # Use stored classification data only (no live keyword fallback)
        category_counts = {cat: stored_counts.get(cat, 0) for cat in SCIENCE_CATEGORIES.keys()}

        total = sum(category_counts.values())

        # Calculate trends by comparing to previous period
        prev_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=days_back)).strftime('%Y-%m-%d')
        prev_result = conn.execute(text("""
            SELECT sac.category, COUNT(DISTINCT sac.article_uri) as count
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :prev_start
            AND a.publication_date < :start_date
            AND a.category IS NOT NULL AND a.category != ''
            GROUP BY sac.category
        """), {"topic": topic, "prev_start": prev_start, "start_date": start_date})

        prev_counts = {row[0]: row[1] for row in prev_result.fetchall()}

        # Build response with trends
        response = []
        for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            prev_count = prev_counts.get(category, 0)
            if prev_count == 0:
                trend = "stable" if count == 0 else "up"
            elif count > prev_count * 1.1:
                trend = "up"
            elif count < prev_count * 0.9:
                trend = "down"
            else:
                trend = "stable"

            response.append(ScienceCategoryResponse(
                category=category,
                article_count=count,
                percentage=round((count / total * 100) if total > 0 else 0, 1),
                recent_trend=trend
            ))

        return response

    except Exception as e:
        logger.error(f"Error fetching category distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/temporal", response_model=List[TemporalDataResponse])
async def get_temporal_data(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """
    Get monthly article counts by category for time series charts.
    Uses efficient SQL aggregation.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get monthly totals (articles with categories)
        totals_result = conn.execute(text("""
            SELECT TO_CHAR(a.publication_date::timestamp, 'YYYY-MM') as month,
                   COUNT(DISTINCT a.uri) as total
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            GROUP BY TO_CHAR(a.publication_date::timestamp, 'YYYY-MM')
            ORDER BY month
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        monthly_totals = {row[0]: row[1] for row in totals_result.fetchall()}

        # Get monthly category counts
        category_result = conn.execute(text("""
            SELECT TO_CHAR(a.publication_date::timestamp, 'YYYY-MM') as month,
                   sac.category,
                   COUNT(DISTINCT sac.article_uri) as count
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            GROUP BY TO_CHAR(a.publication_date::timestamp, 'YYYY-MM'), sac.category
            ORDER BY month
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        # Build monthly data structure
        monthly_data: Dict[str, Dict[str, int]] = {}
        for row in category_result.fetchall():
            month, category, count = row
            if month not in monthly_data:
                monthly_data[month] = {cat: 0 for cat in SCIENCE_CATEGORIES.keys()}
            if category in SCIENCE_CATEGORIES:
                monthly_data[month][category] = count

        # Build response
        response = []
        for month in sorted(monthly_data.keys()):
            response.append(TemporalDataResponse(
                month=month,
                total=monthly_totals.get(month, 0),
                by_category=monthly_data[month]
            ))

        return response

    except Exception as e:
        logger.error(f"Error fetching temporal data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/related/{uri:path}", response_model=List[RelatedArticleResponse])
async def get_related_articles(
    uri: str,
    limit: int = Query(10, ge=1, le=50),
    session=Depends(verify_session)
):
    """
    Find related articles using vector similarity search.
    Returns articles from ALL topics, not just the tracker topic.
    """
    try:
        from app.vector_store import get_vector_store

        vector_store = get_vector_store()

        # Search for similar articles
        results = vector_store.find_similar_by_uri(uri, n_results=limit + 1)

        # Filter out the source article
        related = [r for r in results if r.get('uri') != uri][:limit]

        return [
            RelatedArticleResponse(
                uri=r.get('uri', ''),
                title=r.get('title', ''),
                summary=r.get('summary'),
                news_source=r.get('news_source'),
                publication_date=r.get('publication_date'),
                topic=r.get('topic'),
                similarity_score=r.get('similarity_score', 0.0)
            )
            for r in related
        ]

    except Exception as e:
        logger.error(f"Error fetching related articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=SearchResultResponse)
async def semantic_search(
    query: str = Query(..., min_length=2, description="Search query"),
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    limit: int = Query(20, ge=1, le=100),
    session=Depends(verify_session)
):
    """
    Perform semantic search within tracker articles.
    """
    try:
        from app.vector_store import get_vector_store

        vector_store = get_vector_store()

        # Build filter for topic
        filter_dict = {"topic": topic} if topic else {}

        # Search
        results = vector_store.similarity_search(query, n_results=limit, filter=filter_dict)

        # Process results
        articles = []
        for r in results:
            title = r.get('title', '')
            summary = r.get('summary', '')
            categories = categorize_article(title, summary)

            articles.append(ScienceArticleResponse(
                uri=r.get('uri', ''),
                title=title,
                summary=summary,
                news_source=r.get('news_source'),
                publication_date=r.get('publication_date'),
                categories=categories,
                sentiment=r.get('sentiment'),
                bias=r.get('bias'),
                factual_reporting=r.get('factual_reporting')
            ))

        return SearchResultResponse(
            articles=articles,
            total_count=len(articles),
            query=query
        )

    except Exception as e:
        logger.error(f"Error performing semantic search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_tracker_config(session=Depends(verify_session)):
    """
    Get the science funding tracker configuration including categories and keywords.
    """
    return {
        "default_topic": DEFAULT_TRACKER_TOPIC,
        "categories": SCIENCE_CATEGORIES
    }


# ============================================================================
# Analysis Endpoints
# ============================================================================

class ScienceCooccurrenceResponse(BaseModel):
    """Category co-occurrence data."""
    category1: str
    category2: str
    count: int
    percentage: float


@router.get("/cooccurrence", response_model=List[ScienceCooccurrenceResponse])
async def get_category_cooccurrence(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    limit: int = Query(20, ge=1, le=50, description="Number of top pairs to return"),
    session=Depends(verify_session)
):
    """
    Get category co-occurrence analysis - which categories frequently appear together.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get articles with their categories
        result = conn.execute(text("""
            SELECT sac.article_uri, sac.category
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        # Build article -> categories mapping
        article_categories: Dict[str, List[str]] = {}
        for uri, category in result.fetchall():
            if uri not in article_categories:
                article_categories[uri] = []
            article_categories[uri].append(category)

        total_articles = len(article_categories)

        # Count co-occurrences
        cooccurrence_counts: Dict[tuple, int] = {}
        for uri, cats in article_categories.items():
            cats = sorted(set(cats))
            for i, cat1 in enumerate(cats):
                for cat2 in cats[i+1:]:
                    pair = (cat1, cat2)
                    cooccurrence_counts[pair] = cooccurrence_counts.get(pair, 0) + 1

        # Sort by count and return top pairs
        sorted_pairs = sorted(cooccurrence_counts.items(), key=lambda x: x[1], reverse=True)

        response = []
        for (cat1, cat2), count in sorted_pairs[:limit]:
            response.append(ScienceCooccurrenceResponse(
                category1=cat1,
                category2=cat2,
                count=count,
                percentage=round((count / total_articles * 100) if total_articles > 0 else 0, 1)
            ))

        return response

    except Exception as e:
        logger.error(f"Error getting co-occurrence data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


class ScienceEscalationDataPoint(BaseModel):
    """Escalation metric for a time period."""
    period: str
    total_actions: int
    multi_category_count: int
    avg_categories: float
    top_categories: List[str]


@router.get("/escalation", response_model=List[ScienceEscalationDataPoint])
async def get_escalation_analysis(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    period: str = Query("month", description="Aggregation period: week, month, quarter"),
    session=Depends(verify_session)
):
    """
    Get escalation analysis - how intensity of actions changes over time.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get articles with their categories and dates
        result = conn.execute(text("""
            SELECT a.uri, a.publication_date, sac.category
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            ORDER BY a.publication_date
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        # Group by article and period
        article_data: Dict[str, Dict] = {}
        for uri, pub_date, category in result.fetchall():
            if uri not in article_data:
                # Determine period key
                if isinstance(pub_date, str):
                    try:
                        pub_date = datetime.strptime(pub_date[:10], "%Y-%m-%d")
                    except:
                        continue

                if period == "week":
                    period_key = pub_date.strftime("%Y-W%W")
                elif period == "quarter":
                    q = (pub_date.month - 1) // 3 + 1
                    period_key = f"{pub_date.year}-Q{q}"
                else:  # month
                    period_key = pub_date.strftime("%Y-%m")

                article_data[uri] = {"period": period_key, "categories": []}

            article_data[uri]["categories"].append(category)

        # Aggregate by period
        period_stats: Dict[str, Dict] = {}
        for uri, data in article_data.items():
            p = data["period"]
            if p not in period_stats:
                period_stats[p] = {
                    "total": 0,
                    "multi_cat": 0,
                    "total_cats": 0,
                    "cat_counts": {}
                }

            cats = list(set(data["categories"]))
            period_stats[p]["total"] += 1
            period_stats[p]["total_cats"] += len(cats)
            if len(cats) >= 3:
                period_stats[p]["multi_cat"] += 1

            for cat in cats:
                period_stats[p]["cat_counts"][cat] = period_stats[p]["cat_counts"].get(cat, 0) + 1

        # Build response
        response = []
        for p in sorted(period_stats.keys()):
            stats = period_stats[p]
            top_cats = sorted(stats["cat_counts"].items(), key=lambda x: x[1], reverse=True)[:3]

            response.append(ScienceEscalationDataPoint(
                period=p,
                total_actions=stats["total"],
                multi_category_count=stats["multi_cat"],
                avg_categories=round(stats["total_cats"] / stats["total"], 2) if stats["total"] > 0 else 0,
                top_categories=[c[0] for c in top_cats]
            ))

        return response

    except Exception as e:
        logger.error(f"Error getting escalation data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# EDA Analysis Endpoints
# ============================================================================

class ThemeDataResponse(BaseModel):
    """Theme frequency analysis."""
    theme: str
    article_count: int
    percentage: float
    keywords_matched: List[str] = []


class ThemeEvolutionResponse(BaseModel):
    """Monthly theme evolution."""
    month: str
    by_theme: Dict[str, int] = {}


class EntityDataResponse(BaseModel):
    """Entity mention counts."""
    entity: str
    mention_count: int
    percentage: float


class GeographyDataResponse(BaseModel):
    """Geographic focus analysis."""
    location: str
    mention_count: int
    location_type: str  # "domestic" or "international"


class EscalationMarkerResponse(BaseModel):
    """Escalation marker analysis."""
    marker_type: str
    article_count: int
    percentage: float
    keywords_matched: List[str] = []


class EscalationTrendResponse(BaseModel):
    """Escalation trends over time."""
    period: str
    by_marker: Dict[str, int] = {}
    total_escalation_articles: int = 0


class DayOfWeekResponse(BaseModel):
    """Day of week distribution."""
    day: str
    day_number: int
    article_count: int
    percentage: float


class DailyIntensityResponse(BaseModel):
    """Daily intensity with rolling average."""
    date: str
    count: int
    rolling_avg_7day: float


class CooccurrenceMatrixResponse(BaseModel):
    """Full co-occurrence matrix for heatmap."""
    categories: List[str]
    matrix: List[List[int]]


def extract_themes_from_text(title: str, summary: str) -> List[str]:
    """Extract themes from article text."""
    text_content = f"{title} {summary}".lower()
    matched_themes = []

    for theme, keywords in THEMES.items():
        for keyword in keywords:
            if keyword.lower() in text_content:
                matched_themes.append(theme)
                break

    return matched_themes


def extract_entities_from_text(title: str, summary: str) -> List[str]:
    """Extract tracked entities from article text."""
    text_content = f"{title} {summary}"
    matched_entities = []

    for entity in TRACKED_ENTITIES:
        if entity.lower() in text_content.lower():
            matched_entities.append(entity)

    return matched_entities


def extract_locations_from_text(title: str, summary: str) -> Dict[str, List[str]]:
    """Extract geographic locations from article text."""
    text_content = f"{title} {summary}"
    result = {"domestic": [], "international": []}

    for location in US_LOCATIONS:
        if location.lower() in text_content.lower():
            result["domestic"].append(location)

    for location in INTERNATIONAL_LOCATIONS:
        if location.lower() in text_content.lower():
            result["international"].append(location)

    return result


def extract_escalation_markers_from_text(title: str, summary: str) -> Dict[str, List[str]]:
    """Extract escalation markers from article text."""
    text_content = f"{title} {summary}".lower()
    matched_markers = {}

    for marker_type, keywords in ESCALATION_MARKERS.items():
        matched = []
        for keyword in keywords:
            if keyword.lower() in text_content:
                matched.append(keyword)
        if matched:
            matched_markers[marker_type] = matched

    return matched_markers


@router.get("/themes", response_model=List[ThemeDataResponse])
async def get_themes(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """Get theme frequency analysis."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        result = conn.execute(text("""
            SELECT DISTINCT a.uri, a.title, a.summary
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        articles = result.fetchall()
        theme_counts: Dict[str, int] = {theme: 0 for theme in THEMES.keys()}
        total_articles = len(articles)

        for uri, title, summary in articles:
            themes = extract_themes_from_text(title or '', summary or '')
            for theme in themes:
                theme_counts[theme] += 1

        response = []
        for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True):
            response.append(ThemeDataResponse(
                theme=theme,
                article_count=count,
                percentage=round((count / total_articles * 100) if total_articles > 0 else 0, 1),
                keywords_matched=THEMES.get(theme, [])[:5]  # Return first 5 keywords
            ))

        return response

    except Exception as e:
        logger.error(f"Error getting themes: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/themes/evolution", response_model=List[ThemeEvolutionResponse])
async def get_themes_evolution(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """Get monthly theme evolution data."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        result = conn.execute(text("""
            SELECT DISTINCT a.title, a.summary, a.publication_date
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            ORDER BY a.publication_date ASC
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        monthly_data: Dict[str, Dict[str, int]] = {}

        for title, summary, pub_date in result.fetchall():
            if not pub_date:
                continue

            try:
                if isinstance(pub_date, str):
                    month_key = pub_date[:7]
                else:
                    month_key = pub_date.strftime('%Y-%m')
            except:
                continue

            if month_key not in monthly_data:
                monthly_data[month_key] = {theme: 0 for theme in THEMES.keys()}

            themes = extract_themes_from_text(title or '', summary or '')
            for theme in themes:
                monthly_data[month_key][theme] += 1

        response = []
        for month in sorted(monthly_data.keys()):
            response.append(ThemeEvolutionResponse(
                month=month,
                by_theme=monthly_data[month]
            ))

        return response

    except Exception as e:
        logger.error(f"Error getting theme evolution: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/entities", response_model=List[EntityDataResponse])
async def get_entities(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """Get entity mention counts."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        result = conn.execute(text("""
            SELECT DISTINCT a.title, a.summary
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        articles = result.fetchall()
        entity_counts: Dict[str, int] = {entity: 0 for entity in TRACKED_ENTITIES}
        total_articles = len(articles)

        for title, summary in articles:
            entities = extract_entities_from_text(title or '', summary or '')
            for entity in entities:
                entity_counts[entity] += 1

        response = []
        for entity, count in sorted(entity_counts.items(), key=lambda x: x[1], reverse=True):
            if count > 0:  # Only include entities with mentions
                response.append(EntityDataResponse(
                    entity=entity,
                    mention_count=count,
                    percentage=round((count / total_articles * 100) if total_articles > 0 else 0, 1)
                ))

        return response

    except Exception as e:
        logger.error(f"Error getting entities: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/geography", response_model=List[GeographyDataResponse])
async def get_geography(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """Get geographic focus analysis."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        result = conn.execute(text("""
            SELECT DISTINCT a.title, a.summary
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        domestic_counts: Dict[str, int] = {loc: 0 for loc in US_LOCATIONS}
        international_counts: Dict[str, int] = {loc: 0 for loc in INTERNATIONAL_LOCATIONS}

        for title, summary in result.fetchall():
            locations = extract_locations_from_text(title or '', summary or '')
            for loc in locations["domestic"]:
                domestic_counts[loc] += 1
            for loc in locations["international"]:
                international_counts[loc] += 1

        response = []

        # Add domestic locations
        for location, count in sorted(domestic_counts.items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                response.append(GeographyDataResponse(
                    location=location,
                    mention_count=count,
                    location_type="domestic"
                ))

        # Add international locations
        for location, count in sorted(international_counts.items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                response.append(GeographyDataResponse(
                    location=location,
                    mention_count=count,
                    location_type="international"
                ))

        return response

    except Exception as e:
        logger.error(f"Error getting geography: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/escalation-markers", response_model=List[EscalationMarkerResponse])
async def get_escalation_markers(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """Get escalation marker analysis."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        result = conn.execute(text("""
            SELECT DISTINCT a.title, a.summary
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        articles = result.fetchall()
        marker_counts: Dict[str, int] = {marker: 0 for marker in ESCALATION_MARKERS.keys()}
        total_articles = len(articles)

        for title, summary in articles:
            markers = extract_escalation_markers_from_text(title or '', summary or '')
            for marker_type in markers.keys():
                marker_counts[marker_type] += 1

        response = []
        for marker, count in sorted(marker_counts.items(), key=lambda x: x[1], reverse=True):
            response.append(EscalationMarkerResponse(
                marker_type=marker,
                article_count=count,
                percentage=round((count / total_articles * 100) if total_articles > 0 else 0, 1),
                keywords_matched=ESCALATION_MARKERS.get(marker, [])[:5]
            ))

        return response

    except Exception as e:
        logger.error(f"Error getting escalation markers: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/escalation-markers/trends", response_model=List[EscalationTrendResponse])
async def get_escalation_marker_trends(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """Get escalation marker trends over time."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        result = conn.execute(text("""
            SELECT DISTINCT a.title, a.summary, a.publication_date
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            ORDER BY a.publication_date ASC
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        monthly_data: Dict[str, Dict[str, int]] = {}

        for title, summary, pub_date in result.fetchall():
            if not pub_date:
                continue

            try:
                if isinstance(pub_date, str):
                    month_key = pub_date[:7]
                else:
                    month_key = pub_date.strftime('%Y-%m')
            except:
                continue

            if month_key not in monthly_data:
                monthly_data[month_key] = {marker: 0 for marker in ESCALATION_MARKERS.keys()}
                monthly_data[month_key]["_total"] = 0

            markers = extract_escalation_markers_from_text(title or '', summary or '')
            if markers:
                monthly_data[month_key]["_total"] += 1
            for marker_type in markers.keys():
                monthly_data[month_key][marker_type] += 1

        response = []
        for month in sorted(monthly_data.keys()):
            data = monthly_data[month].copy()
            total = data.pop("_total", 0)
            response.append(EscalationTrendResponse(
                period=month,
                by_marker=data,
                total_escalation_articles=total
            ))

        return response

    except Exception as e:
        logger.error(f"Error getting escalation trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/day-of-week", response_model=List[DayOfWeekResponse])
async def get_day_of_week_distribution(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """Get day of week distribution for articles."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        result = conn.execute(text("""
            SELECT DISTINCT a.publication_date
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        day_counts = {i: 0 for i in range(7)}  # 0=Monday, 6=Sunday
        total_articles = 0

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for (pub_date,) in result.fetchall():
            if not pub_date:
                continue

            try:
                if isinstance(pub_date, str):
                    pub_date = datetime.strptime(pub_date[:10], "%Y-%m-%d")
                day_of_week = pub_date.weekday()
                day_counts[day_of_week] += 1
                total_articles += 1
            except:
                continue

        response = []
        for day_num, count in day_counts.items():
            response.append(DayOfWeekResponse(
                day=day_names[day_num],
                day_number=day_num,
                article_count=count,
                percentage=round((count / total_articles * 100) if total_articles > 0 else 0, 1)
            ))

        return response

    except Exception as e:
        logger.error(f"Error getting day of week distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/daily-intensity", response_model=List[DailyIntensityResponse])
async def get_daily_intensity(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """Get daily article counts with 7-day rolling average."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        result = conn.execute(text("""
            SELECT DATE(a.publication_date::timestamp) as pub_date, COUNT(DISTINCT a.uri) as count
            FROM articles a
            INNER JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE a.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            GROUP BY DATE(a.publication_date::timestamp)
            ORDER BY pub_date ASC
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        daily_counts: Dict[str, int] = {}
        for row in result.fetchall():
            daily_counts[str(row[0])] = row[1]

        # Fill in missing dates with 0
        current = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        all_dates = []
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            all_dates.append((date_str, daily_counts.get(date_str, 0)))
            current += timedelta(days=1)

        # Calculate 7-day rolling average
        response = []
        for i, (date_str, count) in enumerate(all_dates):
            if i >= 6:
                window = [all_dates[j][1] for j in range(i - 6, i + 1)]
                rolling_avg = sum(window) / 7
            else:
                window = [all_dates[j][1] for j in range(0, i + 1)]
                rolling_avg = sum(window) / len(window) if window else 0

            response.append(DailyIntensityResponse(
                date=date_str,
                count=count,
                rolling_avg_7day=round(rolling_avg, 2)
            ))

        return response

    except Exception as e:
        logger.error(f"Error getting daily intensity: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/cooccurrence-matrix", response_model=CooccurrenceMatrixResponse)
async def get_cooccurrence_matrix(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """Get full co-occurrence matrix for heatmap visualization."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get articles with their categories
        result = conn.execute(text("""
            SELECT sac.article_uri, sac.category
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        # Build article -> categories mapping
        article_categories: Dict[str, List[str]] = {}
        for uri, category in result.fetchall():
            if uri not in article_categories:
                article_categories[uri] = []
            article_categories[uri].append(category)

        # Get ordered list of categories
        categories = list(SCIENCE_CATEGORIES.keys())
        n = len(categories)

        # Initialize matrix
        matrix = [[0] * n for _ in range(n)]

        # Count co-occurrences
        for uri, cats in article_categories.items():
            cats_set = set(cats)
            for i, cat1 in enumerate(categories):
                if cat1 in cats_set:
                    # Diagonal: count of articles with this category
                    matrix[i][i] += 1
                    # Off-diagonal: co-occurrence with other categories
                    for j, cat2 in enumerate(categories):
                        if i != j and cat2 in cats_set:
                            matrix[i][j] += 1

        return CooccurrenceMatrixResponse(
            categories=categories,
            matrix=matrix
        )

    except Exception as e:
        logger.error(f"Error getting co-occurrence matrix: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# LLM-Powered Semantic Analysis Endpoints
# ============================================================================

class SemanticClassifyRequest(BaseModel):
    """Request for LLM-based semantic classification."""
    article_uri: str = Field(..., description="URI of the article to classify")
    title: str = Field(..., description="Article title")
    summary: str = Field(..., description="Article summary/content")
    model: str = Field("gpt-4.1-mini", description="LLM model to use for classification")


class SemanticClassifyResponse(BaseModel):
    """Response from semantic classification."""
    article_uri: str
    categories: List[str]
    confidence: float
    reasoning: str
    method: str = "llm_semantic"


class SemanticClassifyBatchRequest(BaseModel):
    """Request for batch semantic classification."""
    topic: str = Field(DEFAULT_TRACKER_TOPIC, description="Topic to classify articles for")
    days_back: int = Field(30, ge=1, le=365, description="Days back to look for uncategorized articles")
    limit: int = Field(50, ge=1, le=200, description="Maximum articles to classify")
    model: str = Field("gpt-4.1-mini", description="LLM model to use")
    reprocess: bool = Field(False, description="Re-classify already classified articles")


class SemanticClassifyBatchResponse(BaseModel):
    """Response from batch classification."""
    run_id: Optional[int] = None
    articles_processed: int
    articles_categorized: int
    articles_skipped: int
    errors: int
    message: str


class NarrativeRequest(BaseModel):
    """Request for narrative analysis generation."""
    topic: str = Field(DEFAULT_TRACKER_TOPIC, description="Topic to analyze")
    days_back: int = Field(365, ge=7, le=730, description="Days to analyze")
    model: str = Field("gpt-4.1-mini", description="LLM model for narrative generation")


class NarrativeResponse(BaseModel):
    """Response with generated narrative."""
    narrative: str
    generated_at: str
    data_summary: Dict[str, Any]


class CategoryInsightRequest(BaseModel):
    """Request for category-specific insight."""
    category: str = Field(..., description="Category to analyze")
    topic: str = Field(DEFAULT_TRACKER_TOPIC, description="Topic context")
    days_back: int = Field(365, ge=7, le=730, description="Days to analyze")
    model: str = Field("gpt-4.1-mini", description="LLM model to use")


class CategoryInsightResponse(BaseModel):
    """Response with category insight."""
    category: str
    insight: str
    article_count: int
    percentage: float
    trend: str


async def llm_categorize_article(
    title: str,
    summary: str,
    model_name: str = "gpt-4.1-mini"
) -> Dict[str, Any]:
    """
    Use LLM for semantic categorization of an article.
    Returns dict with categories, confidence, and reasoning.
    """
    from app.ai_models import LiteLLMModel

    try:
        prompt = SEMANTIC_CATEGORIZATION_PROMPT.format(
            category_definitions=CATEGORY_DEFINITIONS,
            title=title,
            summary=summary or "No summary available"
        )

        model = LiteLLMModel.get_instance(model_name)
        response = model.generate_response([
            {"role": "system", "content": "You are a science policy analysis expert. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ])

        # Parse JSON response
        response_text = response.strip()
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        result = json.loads(response_text)

        # Validate categories against our defined categories
        valid_categories = list(SCIENCE_CATEGORIES.keys())
        validated_cats = [c for c in result.get("categories", []) if c in valid_categories]

        return {
            "categories": validated_cats,
            "confidence": result.get("confidence", 0.7),
            "reasoning": result.get("reasoning", "")
        }

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        # Fall back to keyword categorization
        return {
            "categories": categorize_article(title, summary),
            "confidence": 0.5,
            "reasoning": "Fallback to keyword matching due to LLM response parse error"
        }
    except Exception as e:
        logger.error(f"LLM categorization error: {e}")
        # Fall back to keyword categorization
        return {
            "categories": categorize_article(title, summary),
            "confidence": 0.5,
            "reasoning": f"Fallback to keyword matching due to error: {str(e)}"
        }


@router.post("/semantic-classify", response_model=SemanticClassifyResponse)
async def semantic_classify_article(
    request: SemanticClassifyRequest,
    session=Depends(verify_session)
):
    """
    Classify a single article using LLM-powered semantic analysis.
    Returns categories with confidence score and reasoning.
    """
    try:
        result = await llm_categorize_article(
            request.title,
            request.summary,
            request.model
        )

        # Store the categories in database
        if result["categories"]:
            db = get_database_instance()
            conn = db._temp_get_connection()
            try:
                for category in result["categories"]:
                    conn.execute(text("""
                        INSERT INTO science_article_categories
                        (article_uri, category, topic, classification_method, confidence)
                        VALUES (:uri, :category, :topic, :method, :confidence)
                        ON CONFLICT (article_uri, category)
                        DO UPDATE SET
                            classification_method = :method,
                            confidence = :confidence,
                            classified_at = NOW()
                    """), {
                        "uri": request.article_uri,
                        "category": category,
                        "topic": DEFAULT_TRACKER_TOPIC,
                        "method": "llm_semantic",
                        "confidence": result["confidence"]
                    })
                conn.commit()
            finally:
                conn.close()

        return SemanticClassifyResponse(
            article_uri=request.article_uri,
            categories=result["categories"],
            confidence=result["confidence"],
            reasoning=result["reasoning"],
            method="llm_semantic"
        )

    except Exception as e:
        logger.error(f"Error in semantic classification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/semantic-classify/batch", response_model=SemanticClassifyBatchResponse)
async def semantic_classify_batch(
    request: SemanticClassifyBatchRequest,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session)
):
    """
    Batch classify articles using LLM semantic analysis.
    Processes uncategorized articles (or all if reprocess=True) in background.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Create a run record to track progress
        result = conn.execute(text("""
            INSERT INTO science_tracker_runs (topic, run_type, status)
            VALUES (:topic, 'semantic_llm', 'running')
            RETURNING id
        """), {"topic": request.topic})
        run_id = result.fetchone()[0]
        conn.commit()

        # Start background task with run_id
        background_tasks.add_task(
            run_semantic_batch_classification,
            run_id,
            request.topic,
            request.days_back,
            request.limit,
            request.model,
            request.reprocess
        )

        return SemanticClassifyBatchResponse(
            run_id=run_id,
            articles_processed=0,
            articles_categorized=0,
            articles_skipped=0,
            errors=0,
            message=f"Batch semantic classification started. Track progress at /api/science-funding/classify/status/{run_id}"
        )

    except Exception as e:
        logger.error(f"Error starting semantic batch classification: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


async def run_semantic_batch_classification(
    run_id: int,
    topic: str,
    days_back: int,
    limit: int,
    model_name: str,
    reprocess: bool
):
    """Background task for batch semantic classification."""
    import asyncio

    db = get_database_instance()
    conn = db._temp_get_connection()

    stats = {
        "processed": 0,
        "categorized": 0,
        "skipped": 0,
        "errors": 0
    }

    try:
        start_date, end_date = get_date_range_filter(days_back)

        if reprocess:
            # Get all enriched articles
            result = conn.execute(text("""
                SELECT uri, title, summary
                FROM articles
                WHERE topic = :topic
                AND publication_date >= :start_date
                AND publication_date <= :end_date
                AND category IS NOT NULL AND category != ''
                ORDER BY publication_date DESC
                LIMIT :limit
            """), {"topic": topic, "start_date": start_date, "end_date": end_date, "limit": limit})
        else:
            # Get only uncategorized enriched articles (by LLM method)
            result = conn.execute(text("""
                SELECT a.uri, a.title, a.summary
                FROM articles a
                LEFT JOIN science_article_categories sac
                    ON a.uri = sac.article_uri
                    AND sac.classification_method = 'llm_semantic'
                WHERE a.topic = :topic
                AND a.publication_date >= :start_date
                AND a.publication_date <= :end_date
                AND a.category IS NOT NULL AND a.category != ''
                AND sac.id IS NULL
                ORDER BY a.publication_date DESC
                LIMIT :limit
            """), {"topic": topic, "start_date": start_date, "end_date": end_date, "limit": limit})

        articles = result.fetchall()

        for uri, title, summary in articles:
            stats["processed"] += 1

            try:
                # Add small delay to avoid rate limiting
                await asyncio.sleep(0.5)

                result = await llm_categorize_article(title or "", summary or "", model_name)

                if result["categories"]:
                    # Store categories
                    for category in result["categories"]:
                        try:
                            conn.execute(text("""
                                INSERT INTO science_article_categories
                                (article_uri, category, topic, classification_method, confidence)
                                VALUES (:uri, :category, :topic, 'llm_semantic', :confidence)
                                ON CONFLICT (article_uri, category)
                                DO UPDATE SET
                                    classification_method = 'llm_semantic',
                                    confidence = :confidence,
                                    classified_at = NOW()
                            """), {
                                "uri": uri,
                                "category": category,
                                "topic": topic,
                                "confidence": result["confidence"]
                            })
                        except Exception as e:
                            logger.warning(f"Failed to store category for {uri}: {e}")

                    conn.commit()
                    stats["categorized"] += 1
                    logger.info(f"Classified {uri}: {result['categories']} (confidence: {result['confidence']})")
                else:
                    stats["skipped"] += 1

            except Exception as e:
                logger.error(f"Error classifying {uri}: {e}")
                stats["errors"] += 1

        # Update run record with success
        conn.execute(text("""
            UPDATE science_tracker_runs
            SET status = 'completed',
                completed_at = NOW(),
                articles_processed = :processed,
                articles_categorized = :categorized
            WHERE id = :run_id
        """), {
            "run_id": run_id,
            "processed": stats["processed"],
            "categorized": stats["categorized"]
        })
        conn.commit()

        logger.info(f"Batch classification complete: {stats}")

    except Exception as e:
        logger.error(f"Batch classification failed: {e}")
        # Update run record with failure
        try:
            conn.execute(text("""
                UPDATE science_tracker_runs
                SET status = 'failed',
                    completed_at = NOW(),
                    error_message = :error,
                    articles_processed = :processed,
                    articles_categorized = :categorized
                WHERE id = :run_id
            """), {
                "run_id": run_id,
                "error": str(e),
                "processed": stats["processed"],
                "categorized": stats["categorized"]
            })
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


@router.post("/generate-narrative", response_model=NarrativeResponse)
async def generate_narrative_analysis(
    request: NarrativeRequest,
    session=Depends(verify_session)
):
    """
    Generate an LLM-powered narrative analysis of the science funding tracker data.
    Returns a comprehensive analytical report on the health of the US research enterprise.
    """
    from app.ai_models import LiteLLMModel

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(request.days_back)

        # Gather all the data for the narrative

        # 1. Get category counts (only enriched articles)
        result = conn.execute(text("""
            SELECT sac.category, COUNT(DISTINCT sac.article_uri) as count
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            GROUP BY sac.category
            ORDER BY count DESC
        """), {"topic": request.topic, "start_date": start_date, "end_date": end_date})

        category_data = {row[0]: row[1] for row in result.fetchall()}

        # Count classified articles (enriched + has science categories)
        result = conn.execute(text("""
            SELECT COUNT(DISTINCT sac.article_uri)
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": request.topic, "start_date": start_date, "end_date": end_date})
        total_articles = result.fetchone()[0]
        total_categorized = total_articles

        category_breakdown = "\n".join([
            f"- {cat}: {count} articles ({round(count/total_articles*100, 1)}%)"
            for cat, count in sorted(category_data.items(), key=lambda x: x[1], reverse=True)
        ]) if total_articles > 0 else "No classified articles found"

        # 2. Get theme data (classified articles only)
        result = conn.execute(text("""
            SELECT DISTINCT a.title, a.summary
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": request.topic, "start_date": start_date, "end_date": end_date})

        theme_counts = {theme: 0 for theme in THEMES.keys()}
        entity_counts = {entity: 0 for entity in TRACKED_ENTITIES}
        escalation_counts = {marker: 0 for marker in ESCALATION_MARKERS.keys()}
        domestic_counts = {loc: 0 for loc in US_LOCATIONS}
        international_counts = {loc: 0 for loc in INTERNATIONAL_LOCATIONS}

        for title, summary in result.fetchall():
            title = title or ""
            summary = summary or ""

            # Themes
            for theme, keywords in THEMES.items():
                for kw in keywords:
                    if kw.lower() in (title + " " + summary).lower():
                        theme_counts[theme] += 1
                        break

            # Entities
            for entity in TRACKED_ENTITIES:
                if entity.lower() in (title + " " + summary).lower():
                    entity_counts[entity] += 1

            # Escalation
            for marker, keywords in ESCALATION_MARKERS.items():
                for kw in keywords:
                    if kw.lower() in (title + " " + summary).lower():
                        escalation_counts[marker] += 1
                        break

            # Geography
            for loc in US_LOCATIONS:
                if loc.lower() in (title + " " + summary).lower():
                    domestic_counts[loc] += 1
            for loc in INTERNATIONAL_LOCATIONS:
                if loc.lower() in (title + " " + summary).lower():
                    international_counts[loc] += 1

        themes_breakdown = "\n".join([
            f"- {theme}: {count} articles"
            for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ])

        escalation_breakdown = "\n".join([
            f"- {marker}: {count} articles"
            for marker, count in sorted(escalation_counts.items(), key=lambda x: x[1], reverse=True)
        ])

        entities_breakdown = "\n".join([
            f"- {entity}: {count} mentions"
            for entity, count in sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:8]
            if count > 0
        ])

        geography_breakdown = "Domestic:\n" + "\n".join([
            f"  - {loc}: {count}"
            for loc, count in sorted(domestic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            if count > 0
        ]) + "\nInternational:\n" + "\n".join([
            f"  - {loc}: {count}"
            for loc, count in sorted(international_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            if count > 0
        ])

        # Build the prompt
        prompt = NARRATIVE_ANALYSIS_PROMPT.format(
            date_range=f"{start_date} to {end_date}",
            total_articles=total_articles,
            category_breakdown=category_breakdown,
            themes_breakdown=themes_breakdown,
            escalation_breakdown=escalation_breakdown,
            entities_breakdown=entities_breakdown,
            geography_breakdown=geography_breakdown
        )

        # Generate narrative with LLM
        model = LiteLLMModel.get_instance(request.model)
        narrative = model.generate_response([
            {"role": "system", "content": """You are a senior science policy analyst specializing in research funding, academic institutions, and the innovation economy. You write critical analytical reports for decision-makers monitoring the health of America's research enterprise.

Your role is to:
- Identify patterns of funding erosion and institutional damage
- Quantify the long-term cost of short-term budget decisions
- Connect individual funding actions to broader research capacity impacts
- Use specific data to support analytical conclusions
- Write with appropriate urgency about irreversible damage to scientific capacity

CRITICAL FORMATTING REQUIREMENT: You MUST use bullet points (lines starting with "- **Bold Header**:") in the Research Spotlight, Institutional Damage, and Forward-Looking Concerns sections. Each bullet must have a bold header followed by analysis. This is mandatory.

Do not minimize the consequences of science defunding. Be direct about what the data shows."""},
            {"role": "user", "content": prompt}
        ])

        data_summary = {
            "total_articles": total_articles,
            "total_categorized": total_categorized,
            "date_range": {"start": start_date, "end": end_date},
            "categories": category_data,
            "top_themes": dict(sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:5]),
            "escalation": escalation_counts,
            "top_entities": dict(sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:8])
        }

        # Save narrative to database for persistence
        try:
            conn.execute(text("""
                INSERT INTO science_tracker_narratives
                (topic, narrative, data_summary, days_back, date_range_start, date_range_end)
                VALUES (:topic, :narrative, :data_summary, :days_back, :start_date, :end_date)
            """), {
                "topic": request.topic,
                "narrative": narrative,
                "data_summary": json.dumps(data_summary),
                "days_back": request.days_back,
                "start_date": start_date,
                "end_date": end_date
            })
            conn.commit()
            logger.info(f"Saved narrative for topic {request.topic}")
        except Exception as save_err:
            logger.warning(f"Failed to save narrative to database: {save_err}")
            # Don't fail the request if save fails - still return the generated narrative

        return NarrativeResponse(
            narrative=narrative,
            generated_at=datetime.now().isoformat(),
            data_summary=data_summary
        )

    except Exception as e:
        logger.error(f"Error generating narrative: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/category-insight", response_model=CategoryInsightResponse)
async def generate_category_insight(
    request: CategoryInsightRequest,
    session=Depends(verify_session)
):
    """
    Generate an LLM-powered insight for a specific science funding category.
    """
    from app.ai_models import LiteLLMModel

    if request.category not in SCIENCE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {request.category}")

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(request.days_back)

        # Get category count and trend
        result = conn.execute(text("""
            SELECT COUNT(DISTINCT sac.article_uri)
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.category = :category
            AND sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"category": request.category, "topic": request.topic, "start_date": start_date, "end_date": end_date})

        article_count = result.fetchone()[0]

        # Get total for percentage (enriched articles only)
        result = conn.execute(text("""
            SELECT COUNT(*)
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
            AND category IS NOT NULL AND category != ''
        """), {"topic": request.topic, "start_date": start_date, "end_date": end_date})

        total_articles = result.fetchone()[0]
        percentage = round((article_count / total_articles * 100) if total_articles > 0 else 0, 1)

        # Get trend by comparing periods
        prev_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=request.days_back)).strftime('%Y-%m-%d')

        result = conn.execute(text("""
            SELECT COUNT(DISTINCT sac.article_uri)
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.category = :category
            AND sac.topic = :topic
            AND a.publication_date >= :prev_start
            AND a.publication_date < :start_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"category": request.category, "topic": request.topic, "prev_start": prev_start, "start_date": start_date})

        prev_count = result.fetchone()[0]

        if prev_count == 0:
            trend = "stable" if article_count == 0 else "up"
        elif article_count > prev_count * 1.1:
            trend = "up"
        elif article_count < prev_count * 0.9:
            trend = "down"
        else:
            trend = "stable"

        # Get sample titles
        result = conn.execute(text("""
            SELECT a.title
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.category = :category
            AND sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            ORDER BY a.publication_date DESC
            LIMIT 10
        """), {"category": request.category, "topic": request.topic, "start_date": start_date, "end_date": end_date})

        sample_titles = "\n".join([f"- {row[0]}" for row in result.fetchall() if row[0]])

        # Generate insight with LLM
        prompt = CATEGORY_INSIGHT_PROMPT.format(
            category_name=request.category,
            article_count=article_count,
            percentage=percentage,
            trend=trend,
            sample_titles=sample_titles or "No sample titles available"
        )

        model = LiteLLMModel.get_instance(request.model)
        insight = model.generate_response([
            {"role": "system", "content": "You are a science policy analyst providing concise, insightful analysis."},
            {"role": "user", "content": prompt}
        ])

        return CategoryInsightResponse(
            category=request.category,
            insight=insight,
            article_count=article_count,
            percentage=percentage,
            trend=trend
        )

    except Exception as e:
        logger.error(f"Error generating category insight: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Import and Narrative Persistence Endpoints
# ============================================================================

class URLImportRequest(BaseModel):
    """Request for URL-based import."""
    url: str = Field(..., description="URL to fetch CSV from")
    topic: str = Field(DEFAULT_TRACKER_TOPIC, description="Topic for imported articles")
    run_llm_classification: bool = Field(False, description="Run LLM classification on new articles")
    regenerate_narrative: bool = Field(False, description="Regenerate narrative after import")


class ImportStatusResponse(BaseModel):
    """Status of an import operation."""
    id: int
    topic: str
    import_type: str
    source_url: Optional[str] = None
    filename: Optional[str] = None
    status: str
    started_at: str
    completed_at: Optional[str] = None
    rows_processed: int
    articles_created: int
    articles_updated: int
    categories_added: int
    errors: int
    error_message: Optional[str] = None
    run_llm_classification: bool
    narrative_id: Optional[int] = None


class SavedNarrativeResponse(BaseModel):
    """Saved narrative response."""
    id: int
    topic: str
    narrative: str
    data_summary: Dict[str, Any]
    days_back: Optional[int] = None
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    generated_at: str


class NarrativeListResponse(BaseModel):
    """List of saved narratives."""
    narratives: List[SavedNarrativeResponse]
    total_count: int


@router.post("/upload-csv")
async def upload_csv_file(
    file: UploadFile = File(...),
    topic: str = Form(DEFAULT_TRACKER_TOPIC),
    run_llm_classification: bool = Form(False),
    regenerate_narrative: bool = Form(False),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session=Depends(verify_session)
):
    """
    Upload a CSV file for import.
    Handles multipart form upload and processes in background.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Read file content
        content = await file.read()
        csv_content = content.decode('utf-8')

        # Create import record
        result = conn.execute(text("""
            INSERT INTO science_tracker_imports
            (topic, import_type, filename, status, run_llm_classification)
            VALUES (:topic, 'file_upload', :filename, 'processing', :run_llm)
            RETURNING id
        """), {
            "topic": topic,
            "filename": file.filename,
            "run_llm": run_llm_classification
        })
        import_id = result.fetchone()[0]
        conn.commit()

        # Process in background
        background_tasks.add_task(
            process_csv_import,
            import_id,
            csv_content,
            topic,
            run_llm_classification,
            regenerate_narrative
        )

        return {
            "import_id": import_id,
            "status": "processing",
            "message": f"Import started. Track progress at /api/science-funding/import/{import_id}/status"
        }

    except Exception as e:
        logger.error(f"Error starting CSV upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/import-url")
async def import_from_url(
    request: URLImportRequest,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session)
):
    """
    Import CSV data from a URL.
    """
    import httpx

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        fetch_url = request.url

        # Create import record
        result = conn.execute(text("""
            INSERT INTO science_tracker_imports
            (topic, import_type, source_url, status, run_llm_classification)
            VALUES (:topic, 'url_import', :url, 'processing', :run_llm)
            RETURNING id
        """), {
            "topic": request.topic,
            "url": fetch_url,
            "run_llm": request.run_llm_classification
        })
        import_id = result.fetchone()[0]
        conn.commit()

        # Process in background
        background_tasks.add_task(
            process_url_import,
            import_id,
            fetch_url,
            request.topic,
            request.run_llm_classification,
            request.regenerate_narrative
        )

        return {
            "import_id": import_id,
            "status": "processing",
            "source_url": fetch_url,
            "message": f"Import started. Track progress at /api/science-funding/import/{import_id}/status"
        }

    except Exception as e:
        logger.error(f"Error starting URL import: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


async def process_csv_import(
    import_id: int,
    csv_content: str,
    topic: str,
    run_llm_classification: bool,
    regenerate_narrative: bool
):
    """Background task to process CSV import."""
    import csv
    from io import StringIO

    db = get_database_instance()
    conn = db._temp_get_connection()

    stats = {
        "rows_processed": 0,
        "articles_created": 0,
        "articles_updated": 0,
        "categories_added": 0,
        "errors": 0
    }

    try:
        # Parse CSV content
        lines = csv_content.strip().split('\n')

        # Find the header row (starts with "Index," or first row)
        header_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("Index,"):
                header_idx = i
                break

        csv_data = '\n'.join(lines[header_idx:])
        reader = csv.DictReader(StringIO(csv_data))

        for row in reader:
            stats["rows_processed"] += 1

            url = row.get("URL", "").strip()
            title = row.get("Title", "").strip()
            date_str = row.get("Date", "").strip()

            if not url or not title:
                continue

            article_uri = url

            # Parse date
            pub_date = None
            if date_str:
                try:
                    pub_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        pub_date = datetime.strptime(date_str, "%d/%m/%Y").date()
                    except ValueError:
                        pass

            # Check if article exists
            result = conn.execute(text("SELECT uri FROM articles WHERE uri = :uri"), {"uri": article_uri})
            article_exists = result.fetchone() is not None

            if article_exists:
                stats["articles_updated"] += 1
            else:
                try:
                    conn.execute(text("""
                        INSERT INTO articles (uri, title, summary, topic, publication_date, news_source, article_origin)
                        VALUES (:uri, :title, :summary, :topic, :pub_date, :source, 'external')
                        ON CONFLICT (uri) DO NOTHING
                    """), {
                        "uri": article_uri,
                        "title": title,
                        "summary": title,
                        "topic": topic,
                        "pub_date": pub_date,
                        "source": "Science Funding Import"
                    })
                    stats["articles_created"] += 1
                except Exception as e:
                    logger.warning(f"Error creating article: {e}")
                    stats["errors"] += 1
                    continue

            # Classify the article using keyword matching
            categories = categorize_article(title, title)

            # Store categories
            for category in categories:
                try:
                    conn.execute(text("""
                        INSERT INTO science_article_categories
                        (article_uri, category, topic, classification_method)
                        VALUES (:uri, :category, :topic, 'csv_import')
                        ON CONFLICT (article_uri, category) DO NOTHING
                    """), {
                        "uri": article_uri,
                        "category": category,
                        "topic": topic
                    })
                    stats["categories_added"] += 1
                except Exception as e:
                    logger.warning(f"Error storing category: {e}")

            if stats["rows_processed"] % 100 == 0:
                conn.commit()
                # Update progress
                conn.execute(text("""
                    UPDATE science_tracker_imports
                    SET rows_processed = :rows, articles_created = :created,
                        articles_updated = :updated, categories_added = :cats, errors = :errors
                    WHERE id = :id
                """), {
                    "id": import_id,
                    "rows": stats["rows_processed"],
                    "created": stats["articles_created"],
                    "updated": stats["articles_updated"],
                    "cats": stats["categories_added"],
                    "errors": stats["errors"]
                })
                conn.commit()

        conn.commit()

        # Regenerate narrative if requested
        narrative_id = None
        if regenerate_narrative:
            try:
                narrative_id = await save_narrative_to_db(topic, 365, conn)
            except Exception as e:
                logger.warning(f"Narrative generation failed: {e}")

        # Update import record with success
        conn.execute(text("""
            UPDATE science_tracker_imports
            SET status = 'completed', completed_at = NOW(),
                rows_processed = :rows, articles_created = :created,
                articles_updated = :updated, categories_added = :cats,
                errors = :errors, narrative_id = :narrative_id
            WHERE id = :id
        """), {
            "id": import_id,
            "rows": stats["rows_processed"],
            "created": stats["articles_created"],
            "updated": stats["articles_updated"],
            "cats": stats["categories_added"],
            "errors": stats["errors"],
            "narrative_id": narrative_id
        })
        conn.commit()

        logger.info(f"CSV import {import_id} completed: {stats}")

    except Exception as e:
        logger.error(f"CSV import {import_id} failed: {e}")
        conn.execute(text("""
            UPDATE science_tracker_imports
            SET status = 'failed', completed_at = NOW(), error_message = :error,
                rows_processed = :rows, articles_created = :created,
                articles_updated = :updated, categories_added = :cats, errors = :errors
            WHERE id = :id
        """), {
            "id": import_id,
            "error": str(e),
            "rows": stats["rows_processed"],
            "created": stats["articles_created"],
            "updated": stats["articles_updated"],
            "cats": stats["categories_added"],
            "errors": stats["errors"]
        })
        conn.commit()
    finally:
        conn.close()


async def process_url_import(
    import_id: int,
    url: str,
    topic: str,
    run_llm_classification: bool,
    regenerate_narrative: bool
):
    """Background task to fetch and process CSV from URL."""
    import httpx

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Fetch CSV from URL
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            csv_content = response.text

        # Process the CSV using the same logic
        await process_csv_import(
            import_id,
            csv_content,
            topic,
            run_llm_classification,
            regenerate_narrative
        )

    except httpx.RequestError as e:
        logger.error(f"URL fetch failed for import {import_id}: {e}")
        conn.execute(text("""
            UPDATE science_tracker_imports
            SET status = 'failed', completed_at = NOW(), error_message = :error
            WHERE id = :id
        """), {"id": import_id, "error": f"Failed to fetch URL: {str(e)}"})
        conn.commit()
    except Exception as e:
        logger.error(f"URL import {import_id} failed: {e}")
        conn.execute(text("""
            UPDATE science_tracker_imports
            SET status = 'failed', completed_at = NOW(), error_message = :error
            WHERE id = :id
        """), {"id": import_id, "error": str(e)})
        conn.commit()
    finally:
        conn.close()


async def save_narrative_to_db(topic: str, days_back: int, conn=None) -> int:
    """Generate and save narrative to database, returning the narrative ID."""
    from app.ai_models import LiteLLMModel

    close_conn = False
    if conn is None:
        db = get_database_instance()
        conn = db._temp_get_connection()
        close_conn = True

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Gather data for narrative (only enriched articles)
        result = conn.execute(text("""
            SELECT sac.category, COUNT(DISTINCT sac.article_uri) as count
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            GROUP BY sac.category
            ORDER BY count DESC
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        category_data = {row[0]: row[1] for row in result.fetchall()}

        # Count classified articles (enriched + has science categories)
        result = conn.execute(text("""
            SELECT COUNT(DISTINCT sac.article_uri)
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})
        total_articles = result.fetchone()[0]
        total_categorized = total_articles

        category_breakdown = "\n".join([
            f"- {cat}: {count} articles ({round(count/total_articles*100, 1)}%)"
            for cat, count in sorted(category_data.items(), key=lambda x: x[1], reverse=True)
        ]) if total_articles > 0 else "No classified articles found"

        # Get theme, entity, escalation data (classified articles only)
        result = conn.execute(text("""
            SELECT DISTINCT a.title, a.summary
            FROM articles a
            JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        theme_counts = {theme: 0 for theme in THEMES.keys()}
        entity_counts = {entity: 0 for entity in TRACKED_ENTITIES}
        escalation_counts = {marker: 0 for marker in ESCALATION_MARKERS.keys()}
        domestic_counts = {loc: 0 for loc in US_LOCATIONS}
        international_counts = {loc: 0 for loc in INTERNATIONAL_LOCATIONS}

        for title, summary in result.fetchall():
            title = title or ""
            summary = summary or ""
            text_content = (title + " " + summary).lower()

            for theme, keywords in THEMES.items():
                for kw in keywords:
                    if kw.lower() in text_content:
                        theme_counts[theme] += 1
                        break

            for entity in TRACKED_ENTITIES:
                if entity.lower() in text_content:
                    entity_counts[entity] += 1

            for marker, keywords in ESCALATION_MARKERS.items():
                for kw in keywords:
                    if kw.lower() in text_content:
                        escalation_counts[marker] += 1
                        break

            for loc in US_LOCATIONS:
                if loc.lower() in text_content:
                    domestic_counts[loc] += 1
            for loc in INTERNATIONAL_LOCATIONS:
                if loc.lower() in text_content:
                    international_counts[loc] += 1

        themes_breakdown = "\n".join([
            f"- {theme}: {count} articles"
            for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ])

        escalation_breakdown = "\n".join([
            f"- {marker}: {count} articles"
            for marker, count in sorted(escalation_counts.items(), key=lambda x: x[1], reverse=True)
        ])

        entities_breakdown = "\n".join([
            f"- {entity}: {count} mentions"
            for entity, count in sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:8]
            if count > 0
        ])

        geography_breakdown = "Domestic:\n" + "\n".join([
            f"  - {loc}: {count}"
            for loc, count in sorted(domestic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            if count > 0
        ]) + "\nInternational:\n" + "\n".join([
            f"  - {loc}: {count}"
            for loc, count in sorted(international_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            if count > 0
        ])

        # Generate narrative with LLM
        prompt = NARRATIVE_ANALYSIS_PROMPT.format(
            date_range=f"{start_date} to {end_date}",
            total_articles=total_articles,
            category_breakdown=category_breakdown,
            themes_breakdown=themes_breakdown,
            escalation_breakdown=escalation_breakdown,
            entities_breakdown=entities_breakdown,
            geography_breakdown=geography_breakdown
        )

        model = LiteLLMModel.get_instance("gpt-4.1-mini")
        narrative = model.generate_response([
            {"role": "system", "content": """You are a senior science policy analyst specializing in research funding, academic institutions, and the innovation economy. You write critical analytical reports for decision-makers monitoring the health of America's research enterprise.

Your role is to:
- Identify patterns of funding erosion and institutional damage
- Quantify the long-term cost of short-term budget decisions
- Connect individual funding actions to broader research capacity impacts
- Use specific data to support analytical conclusions
- Write with appropriate urgency about irreversible damage to scientific capacity

CRITICAL FORMATTING REQUIREMENT: You MUST use bullet points (lines starting with "- **Bold Header**:") in the Research Spotlight, Institutional Damage, and Forward-Looking Concerns sections. Each bullet must have a bold header followed by analysis. This is mandatory.

Do not minimize the consequences of science defunding. Be direct about what the data shows."""},
            {"role": "user", "content": prompt}
        ])

        data_summary = {
            "total_articles": total_articles,
            "total_categorized": total_categorized,
            "date_range": {"start": start_date, "end": end_date},
            "categories": category_data,
            "top_themes": dict(sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:5]),
            "escalation": escalation_counts,
            "top_entities": dict(sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:8])
        }

        # Save to database
        result = conn.execute(text("""
            INSERT INTO science_tracker_narratives
            (topic, narrative, data_summary, days_back, date_range_start, date_range_end)
            VALUES (:topic, :narrative, :data_summary, :days_back, :start_date, :end_date)
            RETURNING id
        """), {
            "topic": topic,
            "narrative": narrative,
            "data_summary": json.dumps(data_summary),
            "days_back": days_back,
            "start_date": start_date,
            "end_date": end_date
        })
        narrative_id = result.fetchone()[0]
        conn.commit()

        logger.info(f"Saved narrative {narrative_id} for topic {topic}")
        return narrative_id

    finally:
        if close_conn:
            conn.close()


@router.get("/import/{import_id}/status", response_model=ImportStatusResponse)
async def get_import_status(
    import_id: int,
    session=Depends(verify_session)
):
    """Get the status of an import operation."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        result = conn.execute(text("""
            SELECT id, topic, import_type, source_url, filename, status,
                   started_at, completed_at, rows_processed, articles_created,
                   articles_updated, categories_added, errors, error_message,
                   run_llm_classification, narrative_id
            FROM science_tracker_imports
            WHERE id = :id
        """), {"id": import_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Import not found")

        return ImportStatusResponse(
            id=row[0],
            topic=row[1],
            import_type=row[2],
            source_url=row[3],
            filename=row[4],
            status=row[5],
            started_at=str(row[6]) if row[6] else None,
            completed_at=str(row[7]) if row[7] else None,
            rows_processed=row[8],
            articles_created=row[9],
            articles_updated=row[10],
            categories_added=row[11],
            errors=row[12],
            error_message=row[13],
            run_llm_classification=row[14],
            narrative_id=row[15]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting import status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/narrative/latest", response_model=Optional[SavedNarrativeResponse])
async def get_latest_narrative(
    topic: str = Query(DEFAULT_TRACKER_TOPIC, description="Topic to get narrative for"),
    session=Depends(verify_session)
):
    """Get the most recently saved narrative for a topic."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        result = conn.execute(text("""
            SELECT id, topic, narrative, data_summary, days_back,
                   date_range_start, date_range_end, generated_at
            FROM science_tracker_narratives
            WHERE topic = :topic
            ORDER BY generated_at DESC
            LIMIT 1
        """), {"topic": topic})

        row = result.fetchone()
        if not row:
            return None

        data_summary = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}
        days_back = row[4]
        saved_topic = row[1]

        # Recompute article count live — only classified articles matter
        start_date, end_date = get_date_range_filter(days_back or 365)

        classified_result = conn.execute(text("""
            SELECT COUNT(DISTINCT sac.article_uri)
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
        """), {"topic": saved_topic, "start_date": start_date, "end_date": end_date})
        article_count = classified_result.fetchone()[0]
        data_summary["total_articles"] = article_count
        data_summary["total_categorized"] = article_count

        # Recompute per-category breakdown live
        cat_result = conn.execute(text("""
            SELECT sac.category, COUNT(DISTINCT sac.article_uri) as count
            FROM science_article_categories sac
            JOIN articles a ON sac.article_uri = a.uri
            WHERE sac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            AND a.category IS NOT NULL AND a.category != ''
            GROUP BY sac.category
            ORDER BY count DESC
        """), {"topic": saved_topic, "start_date": start_date, "end_date": end_date})
        data_summary["categories"] = {row[0]: row[1] for row in cat_result.fetchall()}

        return SavedNarrativeResponse(
            id=row[0],
            topic=saved_topic,
            narrative=row[2],
            data_summary=data_summary,
            days_back=days_back,
            date_range_start=str(row[5]) if row[5] else None,
            date_range_end=str(row[6]) if row[6] else None,
            generated_at=str(row[7]) if row[7] else None
        )

    except Exception as e:
        logger.error(f"Error getting latest narrative: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/narratives", response_model=NarrativeListResponse)
async def list_narratives(
    topic: str = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of narratives to return"),
    session=Depends(verify_session)
):
    """List historical narratives for a topic."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Get total count
        result = conn.execute(text("""
            SELECT COUNT(*) FROM science_tracker_narratives WHERE topic = :topic
        """), {"topic": topic})
        total_count = result.fetchone()[0]

        # Get narratives
        result = conn.execute(text("""
            SELECT id, topic, narrative, data_summary, days_back,
                   date_range_start, date_range_end, generated_at
            FROM science_tracker_narratives
            WHERE topic = :topic
            ORDER BY generated_at DESC
            LIMIT :limit
        """), {"topic": topic, "limit": limit})

        narratives = []
        for row in result.fetchall():
            narratives.append(SavedNarrativeResponse(
                id=row[0],
                topic=row[1],
                narrative=row[2],
                data_summary=row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {},
                days_back=row[4],
                date_range_start=str(row[5]) if row[5] else None,
                date_range_end=str(row[6]) if row[6] else None,
                generated_at=str(row[7]) if row[7] else None
            ))

        return NarrativeListResponse(
            narratives=narratives,
            total_count=total_count
        )

    except Exception as e:
        logger.error(f"Error listing narratives: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Feed Import Endpoints - Import articles from Gather pipeline (feed_items)
# ============================================================================

class FeedKeywordGroupInfo(BaseModel):
    """Info about a feed keyword group with article counts."""
    id: int
    name: str
    total_feed_items: int
    already_imported: int


class FeedKeywordGroupsResponse(BaseModel):
    """Response model for feed keyword groups list."""
    groups: List[FeedKeywordGroupInfo]


class ImportFromFeedRequest(BaseModel):
    """Request model for importing from feed_items."""
    group_id: int
    regenerate_narrative: bool = False
    topic: str = DEFAULT_TRACKER_TOPIC


class ImportFromFeedResponse(BaseModel):
    """Response model for feed import."""
    import_id: int
    status: str
    message: str
    articles_imported: int = 0
    articles_skipped: int = 0


@router.get("/feed-keyword-groups", response_model=FeedKeywordGroupsResponse)
async def get_feed_keyword_groups(
    days_back: int = 365,
    session=Depends(verify_session)
):
    """
    Get keyword groups with article counts filtered by date range.
    Returns enriched articles per group and how many are already categorized in science tracker.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get keyword groups with enriched article counts (only articles with category) within date range
        result = conn.execute(text("""
            SELECT
                kg.id,
                kg.name,
                kg.topic,
                COUNT(DISTINCT a.uri) as total_articles,
                COUNT(DISTINCT sac.article_uri) as already_categorized
            FROM keyword_groups kg
            LEFT JOIN articles a ON a.topic = kg.topic
                AND a.category IS NOT NULL AND a.category != ''
                AND a.publication_date >= :start_date
                AND a.publication_date <= :end_date
            LEFT JOIN science_article_categories sac ON a.uri = sac.article_uri
            GROUP BY kg.id, kg.name, kg.topic
            ORDER BY kg.name
        """), {"start_date": start_date, "end_date": end_date})

        groups = []
        for row in result.fetchall():
            groups.append(FeedKeywordGroupInfo(
                id=row[0],
                name=row[1],
                total_feed_items=row[3] or 0,
                already_imported=row[4] or 0
            ))

        return FeedKeywordGroupsResponse(groups=groups)

    except Exception as e:
        logger.error(f"Error fetching keyword groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/import-from-feed", response_model=ImportFromFeedResponse)
async def import_from_feed(
    request: ImportFromFeedRequest,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session)
):
    """
    Process articles from a keyword group - run classification on uncategorized articles.
    Since articles are already in the articles table with topics, this runs science funding categorization.
    Always uses keyword-based classification.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()
    import_id = None

    try:
        # Get the topic for this keyword group
        result = conn.execute(text("""
            SELECT topic FROM keyword_groups WHERE id = :group_id
        """), {"group_id": request.group_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Keyword group not found")

        group_topic = row[0]

        # Create import record
        result = conn.execute(text("""
            INSERT INTO science_tracker_imports
            (topic, import_type, status, started_at, run_llm_classification)
            VALUES (:topic, 'keyword_group_process', 'processing', CURRENT_TIMESTAMP, false)
            RETURNING id
        """), {
            "topic": group_topic
        })
        import_id = result.fetchone()[0]
        conn.commit()

        # Get uncategorized articles that have enrichment data (summary/category)
        result = conn.execute(text("""
            SELECT a.uri, a.title, a.summary
            FROM articles a
            LEFT JOIN science_article_categories sac ON a.uri = sac.article_uri
            WHERE a.topic = :topic
            AND sac.article_uri IS NULL
            AND (a.category IS NOT NULL AND a.category != '')
            ORDER BY a.publication_date DESC
        """), {"topic": group_topic})

        articles = result.fetchall()
        logger.info(f"Processing {len(articles)} uncategorized enriched articles for topic '{group_topic}'")

        if not articles:
            # No articles to process
            conn.execute(text("""
                UPDATE science_tracker_imports
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP,
                    articles_created = 0, articles_updated = 0, errors = 0
                WHERE id = :import_id
            """), {"import_id": import_id})
            conn.commit()
            conn.close()
            return ImportFromFeedResponse(
                import_id=import_id,
                status="completed",
                message="No uncategorized articles found",
                articles_imported=0,
                articles_skipped=0
            )

        # Update import record to show we're launching LLM classification
        conn.execute(text("""
            UPDATE science_tracker_imports
            SET run_llm_classification = true
            WHERE id = :import_id
        """), {"import_id": import_id})
        conn.commit()
        conn.close()

        # Run LLM classification in background
        article_data = [(uri, title, summary) for uri, title, summary in articles]
        background_tasks.add_task(
            _run_feed_import_llm_classification,
            import_id,
            group_topic,
            article_data,
            request.regenerate_narrative
        )

        return ImportFromFeedResponse(
            import_id=import_id,
            status="processing",
            message=f"LLM classification started for {len(articles)} articles. Track progress at /api/science-funding/imports/{import_id}",
            articles_imported=0,
            articles_skipped=0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing keyword group: {e}")
        # Rollback any pending transaction before trying to update import record
        try:
            conn.rollback()
        except:
            pass
        # Try to update import record with error
        if import_id:
            try:
                conn.execute(text("""
                    UPDATE science_tracker_imports
                    SET status = 'failed', error_message = :error, completed_at = CURRENT_TIMESTAMP
                    WHERE id = :import_id
                """), {"import_id": import_id, "error": str(e)})
                conn.commit()
            except:
                pass
        try:
            conn.close()
        except:
            pass
        raise HTTPException(status_code=500, detail=str(e))


async def _run_feed_import_llm_classification(
    import_id: int,
    topic: str,
    articles: List[tuple],
    regenerate_narrative: bool = False
):
    """Background task to classify feed-imported articles using SLM-first, LLM fallback."""
    import asyncio

    db = get_database_instance()
    conn = db._temp_get_connection()

    # Try loading SLM classifier
    slm_available = False
    slm = None
    try:
        from app.services.science_funding_classifier_service import get_science_funding_classifier
        slm = get_science_funding_classifier()
        slm_available = slm.is_available()
        if slm_available:
            logger.info(f"Feed import: SLM classifier available for {len(articles)} articles")
    except Exception as e:
        logger.info(f"Feed import: SLM not available ({e}), using LLM")

    articles_categorized = 0
    articles_no_match = 0
    articles_error = 0
    total_articles = len(articles)
    articles_done = 0

    try:
        for uri, title, summary in articles:
            articles_done += 1

            if not title:
                articles_no_match += 1
                continue

            try:
                text_input = title or ''
                if summary:
                    text_input = f"{title}. {summary}" if title else summary

                categories = []
                method = "keyword"
                confidence = None

                # Step 1: Try SLM (fast, free)
                if slm_available:
                    try:
                        slm_result = slm.classify(text_input, return_scores=True)
                        categories = slm_result.get("categories", [])
                        if categories:
                            method = "slm"
                            scores = slm_result.get("scores", {})
                            if scores:
                                matched_scores = [scores[c] for c in categories if c in scores]
                                confidence = sum(matched_scores) / len(matched_scores) if matched_scores else 0.7
                    except Exception as e:
                        logger.debug(f"SLM failed for {uri}: {e}")

                # Step 2: Fall back to LLM
                if not categories:
                    await asyncio.sleep(0.3)
                    llm_result = await llm_categorize_article(title or '', summary or '')
                    categories = llm_result.get("categories", [])
                    method = "llm_semantic"
                    confidence = llm_result.get("confidence", 0.7)

                # Step 3: Fall back to keywords
                if not categories:
                    categories = _categorize_article_keywords(title or '', summary or '')
                    method = "keyword"
                    confidence = None

                if categories:
                    for category in categories:
                        conn.execute(text("""
                            INSERT INTO science_article_categories
                            (article_uri, category, topic, classification_method, confidence)
                            VALUES (:uri, :category, :topic, :method, :confidence)
                            ON CONFLICT (article_uri, category)
                            DO UPDATE SET
                                classification_method = :method,
                                confidence = :confidence,
                                classified_at = NOW()
                        """), {
                            "uri": uri,
                            "category": category,
                            "topic": topic,
                            "method": method,
                            "confidence": confidence
                        })
                    articles_categorized += 1
                else:
                    articles_no_match += 1

            except Exception as e:
                logger.warning(f"Failed to classify article {uri}: {e}")
                try:
                    conn.rollback()
                except:
                    pass
                articles_error += 1

            # Update progress every 10 articles
            if articles_done % 10 == 0 or articles_done == total_articles:
                conn.commit()
                conn.execute(text("""
                    UPDATE science_tracker_imports
                    SET rows_processed = :done,
                        categories_added = :categorized,
                        articles_created = :categorized,
                        articles_updated = :no_match,
                        errors = :errors
                    WHERE id = :import_id
                """), {
                    "import_id": import_id,
                    "done": articles_done,
                    "categorized": articles_categorized,
                    "no_match": articles_no_match,
                    "errors": articles_error
                })
                conn.commit()

        conn.commit()
        logger.info(f"Feed import LLM classification complete: {articles_categorized} categorized, {articles_no_match} no match, {articles_error} errors")

        conn.execute(text("""
            UPDATE science_tracker_imports
            SET status = 'completed',
                completed_at = CURRENT_TIMESTAMP,
                rows_processed = :done,
                categories_added = :categorized,
                articles_created = :categorized,
                articles_updated = :no_match,
                errors = :errors
            WHERE id = :import_id
        """), {
            "import_id": import_id,
            "done": total_articles,
            "categorized": articles_categorized,
            "no_match": articles_no_match,
            "errors": articles_error
        })
        conn.commit()

        if regenerate_narrative and articles_categorized > 0:
            await _run_narrative_generation_task(topic, 365)

    except Exception as e:
        logger.error(f"Feed import LLM classification failed: {e}")
        try:
            conn.rollback()
            conn.execute(text("""
                UPDATE science_tracker_imports
                SET status = 'failed', error_message = :error, completed_at = CURRENT_TIMESTAMP
                WHERE id = :import_id
            """), {"import_id": import_id, "error": str(e)})
            conn.commit()
        except:
            pass
    finally:
        conn.close()


async def _run_batch_classification_task(topic: str, days_back: int, limit: int, reprocess: bool):
    """Background task to run batch classification."""
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        try:
            start_date, end_date = get_date_range_filter(days_back)

            # Get articles to classify (only enriched articles)
            if reprocess:
                result = conn.execute(text("""
                    SELECT uri, title, summary
                    FROM articles
                    WHERE topic = :topic
                    AND publication_date >= :start_date
                    AND publication_date <= :end_date
                    AND category IS NOT NULL AND category != ''
                    LIMIT :limit
                """), {"topic": topic, "start_date": start_date, "end_date": end_date, "limit": limit})
            else:
                result = conn.execute(text("""
                    SELECT a.uri, a.title, a.summary
                    FROM articles a
                    LEFT JOIN science_article_categories sac ON a.uri = sac.article_uri
                    WHERE a.topic = :topic
                    AND a.publication_date >= :start_date
                    AND a.publication_date <= :end_date
                    AND a.category IS NOT NULL AND a.category != ''
                    AND sac.article_uri IS NULL
                    LIMIT :limit
                """), {"topic": topic, "start_date": start_date, "end_date": end_date, "limit": limit})

            articles = result.fetchall()
            logger.info(f"Background classification: processing {len(articles)} articles")

            for uri, title, summary in articles:
                categories = categorize_article(title or '', summary or '')
                if categories:
                    for category in categories:
                        try:
                            conn.execute(text("""
                                INSERT INTO science_article_categories
                                (article_uri, category, topic, classification_method)
                                VALUES (:uri, :category, :topic, 'keyword')
                                ON CONFLICT (article_uri, category) DO NOTHING
                            """), {"uri": uri, "category": category, "topic": topic})
                        except:
                            pass

            conn.commit()
            logger.info(f"Background classification completed for {len(articles)} articles")

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Background classification failed: {e}")


async def _run_narrative_generation_task(topic: str, days_back: int):
    """Background task to regenerate narrative."""
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        try:
            # This is a simplified version - the full narrative generation
            # logic is already in the generate_narrative endpoint
            logger.info(f"Background narrative generation triggered for {topic}")
            # In practice, this would call the same logic as generate_narrative endpoint

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Background narrative generation failed: {e}")


# ============================================================================
# Scheduling Models
# ============================================================================

class ScienceScheduleCreate(BaseModel):
    name: str = Field(..., description="Name for the schedule")
    topic: Optional[str] = Field(None, description="Topic to classify")
    run_type: str = Field("incremental", description="Run type: 'full' or 'incremental'")
    days_back: int = Field(30, description="Days back to look for articles")
    schedule_enabled: bool = Field(True, description="Enable scheduling")
    schedule_type: str = Field("interval", description="Schedule type: 'interval' or 'daily'")
    schedule_interval: Optional[int] = Field(None, description="Interval value")
    schedule_unit: Optional[str] = Field("hours", description="Interval unit: 'minutes', 'hours', 'days'")
    schedule_time: Optional[str] = Field(None, description="Time for daily schedule (HH:MM)")
    notify_on_complete: bool = Field(True, description="Send notification on completion")
    notify_threshold: int = Field(10, description="Minimum articles to trigger notification")


class ScienceScheduleUpdate(BaseModel):
    name: Optional[str] = None
    topic: Optional[str] = None
    run_type: Optional[str] = None
    days_back: Optional[int] = None
    schedule_enabled: Optional[bool] = None
    schedule_type: Optional[str] = None
    schedule_interval: Optional[int] = None
    schedule_unit: Optional[str] = None
    schedule_time: Optional[str] = None
    notify_on_complete: Optional[bool] = None
    notify_threshold: Optional[int] = None


# ============================================================================
# SLM Classifier Endpoints
# ============================================================================

@router.get("/slm/status")
async def get_slm_status(session=Depends(verify_session)):
    """Get the status of the local SLM classifier."""
    try:
        from app.services.science_funding_classifier_service import get_science_funding_classifier
        classifier = get_science_funding_classifier()
        return classifier.get_status()
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.post("/slm/classify")
async def slm_classify_text(
    request: dict,
    session=Depends(verify_session),
):
    """Classify text using the local SLM (for testing)."""
    try:
        from app.services.science_funding_classifier_service import get_science_funding_classifier
        classifier = get_science_funding_classifier()
        if not classifier.is_available():
            raise HTTPException(status_code=503, detail="SLM classifier not available")

        text = request.get("text", "")
        threshold = request.get("threshold")
        result = classifier.classify(text, threshold=threshold, return_scores=True)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Scheduling Endpoints
# ============================================================================

@router.get("/schedules")
async def list_schedules(session=Depends(verify_session)):
    """List all science tracker classification schedules."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        result = conn.execute(text("""
            SELECT id, name, topic, run_type, days_back,
                   schedule_enabled, schedule_type, schedule_interval, schedule_unit, schedule_time,
                   notify_on_complete, notify_threshold,
                   last_run_at, next_run_at, last_run_status,
                   last_run_articles_processed, last_run_articles_categorized, run_count
            FROM science_tracker_schedules
            ORDER BY name
        """))
        schedules = []
        for row in result:
            row_dict = dict(row._mapping)
            if row_dict.get('schedule_time'):
                row_dict['schedule_time'] = str(row_dict['schedule_time'])
            schedules.append(row_dict)

        return {"schedules": schedules}
    except Exception as e:
        logger.error(f"Error listing science tracker schedules: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/schedules")
async def create_schedule(
    schedule: ScienceScheduleCreate,
    session=Depends(verify_session)
):
    """Create a new science tracker classification schedule."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        schedule_time_val = None
        if schedule.schedule_time:
            try:
                parts = schedule.schedule_time.split(':')
                schedule_time_val = dt_time(int(parts[0]), int(parts[1]))
            except:
                pass

        next_run_at = None
        if schedule.schedule_enabled:
            from app.tasks.science_funding_monitor import calculate_next_run
            next_run_at = calculate_next_run(
                schedule.schedule_type,
                schedule.schedule_interval,
                schedule.schedule_unit,
                schedule_time_val
            )

        result = conn.execute(text("""
            INSERT INTO science_tracker_schedules
            (name, topic, run_type, days_back,
             schedule_enabled, schedule_type, schedule_interval, schedule_unit, schedule_time,
             notify_on_complete, notify_threshold, next_run_at)
            VALUES (:name, :topic, :run_type, :days_back,
                    :schedule_enabled, :schedule_type, :schedule_interval, :schedule_unit, :schedule_time,
                    :notify_on_complete, :notify_threshold, :next_run_at)
            RETURNING id
        """), {
            "name": schedule.name,
            "topic": schedule.topic,
            "run_type": schedule.run_type,
            "days_back": schedule.days_back,
            "schedule_enabled": schedule.schedule_enabled,
            "schedule_type": schedule.schedule_type,
            "schedule_interval": schedule.schedule_interval,
            "schedule_unit": schedule.schedule_unit,
            "schedule_time": schedule_time_val,
            "notify_on_complete": schedule.notify_on_complete,
            "notify_threshold": schedule.notify_threshold,
            "next_run_at": next_run_at
        })
        schedule_id = result.scalar()
        conn.commit()

        return {
            "status": "success",
            "message": "Schedule created successfully",
            "schedule_id": schedule_id,
            "next_run_at": next_run_at.isoformat() if next_run_at else None
        }
    except Exception as e:
        logger.error(f"Error creating science tracker schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    schedule: ScienceScheduleUpdate,
    session=Depends(verify_session)
):
    """Update a science tracker classification schedule."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        updates = []
        params = {"id": schedule_id}

        if schedule.name is not None:
            updates.append("name = :name")
            params["name"] = schedule.name

        if schedule.topic is not None:
            updates.append("topic = :topic")
            params["topic"] = schedule.topic if schedule.topic else None

        if schedule.run_type is not None:
            updates.append("run_type = :run_type")
            params["run_type"] = schedule.run_type

        if schedule.days_back is not None:
            updates.append("days_back = :days_back")
            params["days_back"] = schedule.days_back

        if schedule.schedule_enabled is not None:
            updates.append("schedule_enabled = :schedule_enabled")
            params["schedule_enabled"] = schedule.schedule_enabled

        if schedule.schedule_type is not None:
            updates.append("schedule_type = :schedule_type")
            params["schedule_type"] = schedule.schedule_type

        if schedule.schedule_interval is not None:
            updates.append("schedule_interval = :schedule_interval")
            params["schedule_interval"] = schedule.schedule_interval

        if schedule.schedule_unit is not None:
            updates.append("schedule_unit = :schedule_unit")
            params["schedule_unit"] = schedule.schedule_unit

        if schedule.schedule_time is not None:
            schedule_time_val = None
            if schedule.schedule_time:
                try:
                    parts = schedule.schedule_time.split(':')
                    schedule_time_val = dt_time(int(parts[0]), int(parts[1]))
                except:
                    pass
            updates.append("schedule_time = :schedule_time")
            params["schedule_time"] = schedule_time_val

        if schedule.notify_on_complete is not None:
            updates.append("notify_on_complete = :notify_on_complete")
            params["notify_on_complete"] = schedule.notify_on_complete

        if schedule.notify_threshold is not None:
            updates.append("notify_threshold = :notify_threshold")
            params["notify_threshold"] = schedule.notify_threshold

        if not updates:
            return {"status": "success", "message": "No updates provided"}

        # Recalculate next_run_at if schedule config changed
        if any(key in params for key in ['schedule_enabled', 'schedule_type', 'schedule_interval', 'schedule_unit', 'schedule_time']):
            current = conn.execute(text("""
                SELECT schedule_enabled, schedule_type, schedule_interval, schedule_unit, schedule_time
                FROM science_tracker_schedules WHERE id = :id
            """), {"id": schedule_id}).mappings().first()

            if current:
                from app.tasks.science_funding_monitor import calculate_next_run
                s_enabled = params.get('schedule_enabled', current['schedule_enabled'])
                s_type = params.get('schedule_type', current['schedule_type'])
                s_interval = params.get('schedule_interval', current['schedule_interval'])
                s_unit = params.get('schedule_unit', current['schedule_unit'])
                s_time = params.get('schedule_time') if 'schedule_time' in params else current['schedule_time']

                if s_enabled:
                    next_run = calculate_next_run(s_type, s_interval, s_unit, s_time)
                    updates.append("next_run_at = :next_run_at")
                    params["next_run_at"] = next_run

        updates.append("updated_at = NOW()")

        conn.execute(text(f"""
            UPDATE science_tracker_schedules
            SET {', '.join(updates)}
            WHERE id = :id
        """), params)
        conn.commit()

        return {"status": "success", "message": "Schedule updated successfully"}
    except Exception as e:
        logger.error(f"Error updating science tracker schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    session=Depends(verify_session)
):
    """Delete a science tracker classification schedule."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        result = conn.execute(text("""
            DELETE FROM science_tracker_schedules WHERE id = :id
        """), {"id": schedule_id})
        conn.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Schedule not found")

        return {"status": "success", "message": "Schedule deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting science tracker schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/schedules/{schedule_id}/run")
async def trigger_schedule_run(
    schedule_id: int,
    session=Depends(verify_session)
):
    """Manually trigger a schedule to run immediately."""
    from app.tasks.science_funding_monitor import run_schedule_now as _run_schedule_now

    db = get_database_instance()

    try:
        result = await _run_schedule_now(db, schedule_id)

        if not result["success"]:
            if result.get("error") == "Schedule not found":
                raise HTTPException(status_code=404, detail="Schedule not found")
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))

        return {
            "status": "success",
            "message": f"Schedule processed {result.get('articles_processed', 0)} articles",
            "articles_processed": result.get("articles_processed", 0),
            "articles_categorized": result.get("articles_categorized", 0)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running science tracker schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedules/status")
async def get_schedules_status(session=Depends(verify_session)):
    """Get the status of the science tracker monitor background task."""
    from app.tasks.science_funding_monitor import get_task_status
    return get_task_status()
