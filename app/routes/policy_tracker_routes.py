"""
Policy Tracker API Routes

Provides endpoints for the Policy Tracker dashboard which analyzes articles
from a specific topic using 10 policy category classifications.
Integrates with existing keyword groups system for category tracking.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, date
from sqlalchemy import text
import logging
import json

from app.security.session import verify_session
from app.database import get_database_instance

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/policy-tracker", tags=["Policy Tracker"])


# ============================================================================
# Constants
# ============================================================================

# Default topic for the policy tracker
DEFAULT_TRACKER_TOPIC = "Trump Administration Tracker"

# Policy categories from Trump Action Tracker (trumpactiontracker.info)
# Using SHORT category names that match the imported database data
# Keywords include singular/plural forms and common variations
POLICY_CATEGORIES = {
    "Undermining Democracy": [
        "democracy", "democratic", "voting rights", "election", "elections", "constitution",
        "democratic norms", "voting", "ballot", "ballots", "electoral", "constitutional",
        "autocracy", "authoritarian", "dictator", "dictatorship",
        "judicial", "courts", "court", "prosecution", "prosecutor", "justice",
        "judge", "judges", "attorney general", "DOJ", "FBI", "supreme court", "unconstitutional",
        "rule of law", "lawsuit", "lawsuits", "ruling", "rulings", "injunction"
    ],
    "Hollowing State": [
        "federal agency", "federal agencies", "bureaucracy", "government shutdown", "defund",
        "dismantle", "DOGE", "efficiency", "federal workers", "federal employee", "federal employees",
        "civil service", "regulatory", "firing", "fired", "layoff", "layoffs", "purge", "purged",
        "Schedule F", "workforce reduction", "gutting", "dismantling"
    ],
    "Suppressing Dissent": [
        "protest", "protests", "protester", "protesters", "activist", "activists", "arrest",
        "arrested", "arrests", "surveillance", "censorship", "demonstration", "demonstrations",
        "free speech", "crackdown", "dissent", "retaliation", "whistleblower", "whistleblowers",
        "political opponent", "target", "targeted", "weaponize", "weaponized"
    ],
    "Controlling Information": [
        "misinformation", "propaganda", "media", "press freedom", "fact-check", "fake news",
        "disinformation", "press", "journalism", "journalist", "journalists", "censor",
        "censored", "government data", "transparency", "FOIA", "news outlet", "news outlets"
    ],
    "Attacking Science": [
        "CDC", "FDA", "vaccine", "vaccines", "vaccination", "climate", "EPA", "research funding",
        "NIH", "public health", "environment", "environmental", "science", "scientific",
        "RFK", "Kennedy", "health policy", "medical", "pandemic", "scientist", "scientists"
    ],
    "Attacking Education": [
        "university", "universities", "professor", "professors", "DEI", "curriculum",
        "academic", "academics", "college", "colleges", "education", "schools", "school",
        "tenure", "diversity", "campus", "campuses", "student", "students", "museum",
        "cultural", "library", "libraries", "Harvard", "Yale", "MIT", "Stanford",
        "higher education", "woke", "indoctrination"
    ],
    "Weakening Civil Rights": [
        "civil rights", "discrimination", "discriminatory", "LGBTQ", "LGBT", "gay", "lesbian",
        "abortion", "equal protection", "reproductive rights", "transgender", "trans",
        "DEI", "affirmative action", "racial", "gender", "disability",
        "women's rights", "minority", "minorities"
    ],
    "Corruption": [
        "conflict of interest", "ethics", "nepotism", "emoluments", "self-dealing",
        "corruption", "corrupt", "bribery", "grift", "pardon", "pardons", "ethics violation",
        "profiteering", "enrichment", "kickback"
    ],
    "Foreign Policy": [
        "NATO", "sanctions", "sanction", "foreign policy", "ally", "allies", "alliance",
        "alliances", "treaty", "treaties", "withdraw", "withdrawal", "isolationist",
        "tariff", "tariffs", "trade war", "Greenland", "Panama", "annexation", "annex",
        "military intervention", "military", "troops",
        "China", "Russia", "Ukraine", "Gaza", "Israel", "Middle East", "diplomat", "diplomacy",
        "embassy", "ambassador", "United Nations", "UN", "G7", "G20", "summit", "bilateral"
    ],
    "Nationalism & Immigration": [
        "immigration", "immigrant", "immigrants", "border", "border patrol",
        "deportation", "deportations", "deport", "deported", "ICE", "migrant", "migrants",
        "asylum", "detention", "detention center", "detention centers", "wall", "border wall",
        "illegal alien", "illegal aliens", "undocumented", "CBP", "customs and border",
        "immigration enforcement", "mass deportation", "immigration raid", "immigration raids",
        "sanctuary city", "sanctuary cities", "visa", "visas", "green card", "citizenship",
        "naturalization", "USCIS", "immigration court", "removal", "removals",
        "nationalist", "nationalism", "National Guard", "invasion", "Honduras", "Mexico",
        "Latin America", "Central America", "America first"
    ]
}


# Themes from EDA analysis (04_thematic_analysis.py)
THEMES = {
    "Immigration": ["ICE", "deportation", "detention", "border", "immigrant", "asylum", "visa", "migrant"],
    "Press/Media": ["journalist", "reporter", "censorship", "media", "press freedom", "news outlet", "broadcaster"],
    "Courts/Judges": ["ruling", "lawsuit", "injunction", "judge", "federal court", "appeals court", "district court"],
    "Federal Workforce": ["firing", "layoff", "purge", "federal employee", "civil service", "Schedule F", "workforce reduction"],
    "Science/Health": ["CDC", "vaccine", "climate", "EPA", "NIH", "FDA", "RFK", "public health", "research funding"],
    "Universities": ["campus", "professor", "academic", "college", "DEI", "tenure", "student visa", "international student"],
    "Military": ["troops", "deployment", "Insurrection Act", "military", "Pentagon", "National Guard", "martial"],
    "Venezuela": ["Maduro", "Venezuela", "El Salvador", "Bukele", "Latin America"],
    "Greenland": ["Greenland", "annexation", "Panama Canal", "Denmark", "Arctic"]
}

# Entities to track
TRACKED_ENTITIES = [
    "ICE", "FBI", "DOJ", "DHS", "DOGE", "Congress", "Supreme Court", "Pentagon",
    "CDC", "NIH", "FDA", "EPA", "IRS", "State Department", "Homeland Security"
]

# Escalation markers from EDA analysis
ESCALATION_MARKERS = {
    "Threats": ["threat", "warn", "ultimatum", "retaliate", "consequences", "punish"],
    "Military": ["deploy", "troops", "invasion", "operation", "military force", "soldiers", "National Guard"],
    "Emergency Powers": ["emergency", "Insurrection Act", "martial law", "national emergency", "executive order", "emergency powers"],
    "Defiance": ["defy", "ignore", "unconstitutional", "illegal order", "resist", "refuse to comply", "nullify"],
    "Violent Imagery": ["attack", "assault", "raid", "seize", "crackdown", "storm", "invade", "round up"]
}

# Geographic focus locations
US_LOCATIONS = ["Minnesota", "California", "Texas", "New York", "Florida", "Washington DC", "Arizona", "Georgia", "Michigan", "Pennsylvania"]
INTERNATIONAL_LOCATIONS = ["Greenland", "Venezuela", "Russia", "China", "Gaza", "Palestine", "Ukraine", "Denmark", "Mexico", "Canada", "Panama"]


# ============================================================================
# LLM Semantic Analysis Prompts
# ============================================================================

CATEGORY_DEFINITIONS = """
## Policy Category Definitions (from Trump Action Tracker - trumpactiontracker.info)

These are the 11 categories used to classify government actions. Use the EXACT short names shown:

1. **Democratic Norms** - Actions undermining democratic institutions, electoral integrity, constitutional processes.

2. **Rule of Law** - Undermining judicial independence, defying court orders, politicizing DOJ/FBI, attacking judges, eroding checks and balances.

3. **Hollowing State** - Systematic weakening of federal agencies. Mass firings, Schedule F, DOGE measures, eliminating agencies, dismantling expertise.

4. **Suppressing Dissent** - Using state power to target opponents, protesters, activists, journalists. Surveillance, arrests, retaliation against whistleblowers.

5. **Controlling Information** - Government misinformation, propaganda, attacking media, censoring data, restricting press access.

6. **Science & Health Control** - Politicizing CDC/FDA/NIH/EPA, suppressing climate science, vaccine misinformation, appointing ideologues (RFK Jr).

7. **Attacking Education** - Targeting universities, DEI programs, curriculum changes, threatening academic freedom, defunding schools.

8. **Weakening Civil Rights** - Rolling back LGBTQ+, reproductive, voting, racial equality protections. Discriminatory policies.

9. **Corruption & Enrichment** - Self-dealing, conflicts of interest, nepotism, questionable pardons, using office for personal gain.

10. **Immigration Enforcement** - ICE raids, mass deportations, detention centers, border wall, asylum restrictions, sanctuary city crackdowns, immigration courts, visa policies, citizenship/naturalization changes.

11. **Foreign Policy / Nationalism** - Aggressive foreign policy, destabilizing NATO/alliances, trade wars, tariffs, annexation threats (Greenland, Panama), relations with China/Russia/Ukraine, diplomatic actions, international summits.
"""

SEMANTIC_CATEGORIZATION_PROMPT = """You are a policy analyst classifying news articles about Trump administration actions using the Trump Action Tracker methodology.

{category_definitions}

## Task
Analyze the following article and classify it into ALL applicable categories. Most actions fall into 1-4 categories. Use the EXACT category names listed above.

**Article Title:** {title}

**Article Summary:** {summary}

## Response Format
Return a JSON object with:
- "categories": array of EXACT category names that apply (use full names from the list above)
- "confidence": number 0-1 indicating classification confidence
- "reasoning": brief explanation of why each category applies

Example response:
{{"categories": ["Rule of Law", "Suppressing Dissent"], "confidence": 0.85, "reasoning": "DOJ targeting political opponents combines rule of law violations with state weaponization against enemies."}}

Respond ONLY with valid JSON, no other text."""

NARRATIVE_ANALYSIS_PROMPT = """You are generating an analytical narrative report on policy tracker data for decision-makers monitoring democratic institutions.

## Analytical Framework

This analysis operates under the following working assumptions based on documented patterns:

1. **Authoritarian Consolidation**: The administration's actions should be evaluated through the lens of potential authoritarian power consolidation - dismantling checks and balances, concentrating executive power, undermining independent institutions, and neutralizing opposition.

2. **Christian Nationalist Agenda**: Policies may reflect a right-wing Christian nationalist ideology that seeks to impose religious values through state power, restrict reproductive rights, marginalize LGBTQ+ populations, and blur church-state separation.

3. **Attention-Maximizing Behavior**: Actions may prioritize media spectacle, outrage generation, and distraction over coherent policy, regardless of international law, diplomatic norms, or institutional precedent.

4. **Bad Faith Interpretation**: When administration statements conflict with actions, prioritize analyzing actions. Assume strategic deception is possible. Look for gaps between rhetoric and implementation.

Be critical. Call out violations of democratic norms, international law, and human rights. Identify patterns that suggest coordinated efforts to undermine democratic institutions. Do not both-sides authoritarianism.

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
Key findings in 3-4 sentences. What is the most concerning pattern? What requires immediate attention?

## Trend Analysis
What patterns emerge from the category distribution? Which categories show coordinated activity? How do the numbers reflect the authoritarian consolidation framework? Use paragraphs for this analysis.

## Thematic Spotlight
YOU MUST use bullet points in this section. Format EXACTLY like this:

- **Immigration Enforcement**: [Analysis of how this theme connects to the authoritarian playbook, with specific numbers]
- **Federal Workforce Purge**: [Analysis with data showing pattern]
- **Judicial Defiance**: [Analysis connecting to institutional capture]

Analyze 2-3 dominant themes. Each theme MUST be a bullet point starting with "- **Theme Name**:"

## Escalation Assessment
Analyze escalation indicators critically. Is rhetoric becoming more aggressive? Are there signs of normalization of previously unacceptable positions? What red lines are being tested?

## Institutional Targets
YOU MUST use bullet points in this section. Format EXACTLY like this:

- **DOJ/FBI**: [How this institution is being targeted and why it matters for democratic oversight]
- **Federal Courts**: [Analysis of attacks on judicial independence]
- **Independent Agencies**: [Which agencies are being hollowed out]

List the main institutional targets with analysis of the strategy.

## Forward-Looking Concerns
YOU MUST use bullet points in this section. Format EXACTLY like this:

- **Escalation of Military Deployment**: Monitor for expanded use of troops in civilian contexts, particularly around protests or elections
- **Judicial Appointments Acceleration**: Watch for attempts to stack courts with loyalists who will rubber-stamp executive overreach
- **Media Crackdown Expansion**: Track targeting of additional news outlets, especially those reporting on administration misconduct
- **Emergency Powers Invocation**: Monitor for pretexts to invoke emergency powers that suspend normal legal processes

List 4-6 specific forward-looking concerns. Each MUST be a bullet starting with "- **Concern Title**:" followed by explanation.

CRITICAL FORMATTING REQUIREMENTS:
- Use ## for section headers (H2 markdown)
- MANDATORY: Thematic Spotlight MUST use bullet points (- **Theme**: analysis)
- MANDATORY: Institutional Targets MUST use bullet points (- **Institution**: analysis)
- MANDATORY: Forward-Looking Concerns MUST use bullet points (- **Concern**: explanation)
- Use **bold** for the title/header of each bullet point
- Include specific numbers from the data
- Be analytical and critical, not neutral
- Connect data points to the broader pattern of democratic backsliding

IF YOU DO NOT USE BULLET POINTS IN SECTIONS 3, 5, AND 6, THE RESPONSE WILL BE REJECTED."""

CATEGORY_INSIGHT_PROMPT = """You are a policy analyst providing insights on a specific policy category.

## Category: {category_name}

**Articles in this category:** {article_count}
**Percentage of total:** {percentage}%
**Recent trend:** {trend}

**Sample article titles from this category:**
{sample_titles}

## Task
Write a brief analytical insight (150-250 words) covering:
1. What this category captures and why it matters
2. Analysis of the current volume and trend
3. Key sub-themes within this category based on the sample titles
4. Connections to other policy areas

Be specific and analytical, not generic."""


# ============================================================================
# Request/Response Models
# ============================================================================

class PolicyStatsResponse(BaseModel):
    """Overview statistics for the policy tracker."""
    total_articles: int
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    most_active_category: Optional[str] = None
    multi_category_count: int = 0  # Articles with 3+ categories
    category_breakdown: Dict[str, int] = {}


class PolicyCategoryResponse(BaseModel):
    """Category distribution data."""
    category: str
    article_count: int
    percentage: float
    recent_trend: str = "stable"  # up, down, stable


class PolicyArticleResponse(BaseModel):
    """Article data for the policy tracker."""
    uri: str
    title: str
    summary: Optional[str] = None
    news_source: Optional[str] = None
    publication_date: Optional[str] = None
    categories: List[str] = []
    sentiment: Optional[str] = None
    bias: Optional[str] = None
    factual_reporting: Optional[str] = None


class PolicyArticlesListResponse(BaseModel):
    """Paginated list of articles."""
    articles: List[PolicyArticleResponse]
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
    articles: List[PolicyArticleResponse]
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

def categorize_article(title: str, summary: str) -> List[str]:
    """
    Categorize an article based on keyword matching.
    Returns list of matching category names.
    """
    text_content = f"{title} {summary}".lower()
    matched_categories = []

    for category, keywords in POLICY_CATEGORIES.items():
        for keyword in keywords:
            if keyword.lower() in text_content:
                matched_categories.append(category)
                break  # Only add category once

    return matched_categories


# ============================================================================
# Service Functions (for use by other modules like automated_ingest_service)
# ============================================================================

def categorize_article_sync(
    article_uri: str,
    title: str,
    summary: str,
    topic: str = None,
    use_llm: bool = False,
    llm_model: str = None
) -> List[str]:
    """
    Categorize an article into policy categories and store the results.

    This function can be called from the automated ingest pipeline to
    automatically categorize articles after they pass relevance scoring.

    Args:
        article_uri: Unique identifier for the article
        title: Article title
        summary: Article summary/content
        topic: Topic name (default: Trump Administration Tracker)
        use_llm: If True, use LLM for more accurate categorization
        llm_model: Optional specific LLM model to use

    Returns:
        List of matched category names
    """
    if topic is None:
        topic = DEFAULT_TRACKER_TOPIC

    # Use keyword-based categorization
    categories = categorize_article(title, summary)

    if use_llm and categories:
        # Optionally refine with LLM (for future implementation)
        pass

    # Store categories in database
    if categories:
        db = get_database_instance()
        conn = db._temp_get_connection()
        try:
            for category in categories:
                try:
                    conn.execute(text("""
                        INSERT INTO policy_article_categories
                        (article_uri, category, topic, classification_method)
                        VALUES (:uri, :category, :topic, :method)
                        ON CONFLICT (article_uri, category) DO NOTHING
                    """), {
                        "uri": article_uri,
                        "category": category,
                        "topic": topic,
                        "method": "llm" if use_llm else "keyword"
                    })
                except Exception as e:
                    logger.warning(f"Failed to store category {category} for {article_uri}: {e}")
            conn.commit()
            logger.info(f"Categorized article {article_uri} into {len(categories)} policy categories: {categories}")
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
                    INSERT INTO policy_article_categories
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
                    INSERT INTO policy_article_categories
                    (article_uri, category, topic, classification_method)
                    VALUES (:uri, :category, :topic, 'keyword')
                    ON CONFLICT (article_uri, category) DO NOTHING
                """), {"uri": article_uri, "category": category, "topic": topic})
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()


def is_policy_tracker_topic(topic: str) -> bool:
    """Check if a topic is the policy tracker topic."""
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
        FROM policy_article_categories
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
                INSERT INTO policy_article_categories (article_uri, category, topic, classification_method)
                VALUES (:uri, :category, :topic, 'keyword')
                ON CONFLICT (article_uri, category) DO NOTHING
            """), {"uri": article_uri, "category": category, "topic": topic})
        except Exception as e:
            logger.warning(f"Failed to store category {category} for {article_uri}: {e}")


def update_daily_stats(conn, topic: str, category: str, stat_date: date, count: int, new_count: int = 0):
    """Update daily stats for a category."""
    conn.execute(text("""
        INSERT INTO policy_category_daily_stats (date, topic, category, article_count, new_articles_count)
        VALUES (:date, :topic, :category, :count, :new_count)
        ON CONFLICT (date, topic, category)
        DO UPDATE SET
            article_count = :count,
            new_articles_count = policy_category_daily_stats.new_articles_count + :new_count,
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
            INSERT INTO policy_tracker_runs (topic, run_type, status)
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
    """Background task to classify articles."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get articles to classify
        if run_type == "full":
            # Get all articles
            result = conn.execute(text("""
                SELECT uri, title, summary
                FROM articles
                WHERE topic = :topic
                AND publication_date >= :start_date
                AND publication_date <= :end_date
            """), {"topic": topic, "start_date": start_date, "end_date": end_date})
        else:
            # Get only uncategorized articles
            result = conn.execute(text("""
                SELECT a.uri, a.title, a.summary
                FROM articles a
                LEFT JOIN policy_article_categories pac ON a.uri = pac.article_uri
                WHERE a.topic = :topic
                AND a.publication_date >= :start_date
                AND a.publication_date <= :end_date
                AND pac.id IS NULL
            """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        articles = result.fetchall()
        articles_processed = 0
        articles_categorized = 0
        today = date.today()

        # Classify each article
        for uri, title, summary in articles:
            categories = categorize_article(title or '', summary or '')
            articles_processed += 1

            if categories:
                store_article_categories(conn, uri, categories, topic)
                articles_categorized += 1

        # Commit categorizations
        conn.commit()

        # Update daily stats
        category_counts: Dict[str, int] = {cat: 0 for cat in POLICY_CATEGORIES.keys()}
        result = conn.execute(text("""
            SELECT category, COUNT(*) as count
            FROM policy_article_categories
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
            UPDATE policy_tracker_runs
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
            UPDATE policy_tracker_runs
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
            FROM policy_tracker_runs
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
            FROM policy_tracker_runs
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
            FROM policy_category_daily_stats
            WHERE topic = :topic
            AND date >= :start_date
            ORDER BY date ASC
        """), {"topic": topic, "start_date": start_date})

        # Group by category
        trends: Dict[str, List[TrendDataResponse]] = {cat: [] for cat in POLICY_CATEGORIES.keys()}

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

@router.get("/stats", response_model=PolicyStatsResponse)
async def get_policy_stats(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """
    Get overview statistics for the policy tracker.
    Uses stored categorizations when available, falls back to real-time classification.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get articles for the topic within date range
        result = conn.execute(text("""
            SELECT uri, title, summary, publication_date
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
            ORDER BY publication_date DESC
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        articles = result.fetchall()
        article_uris = [a[0] for a in articles]

        # Get stored categories
        stored_categories = get_stored_categories(conn, article_uris)

        # Categorize each article
        category_counts: Dict[str, int] = {cat: 0 for cat in POLICY_CATEGORIES.keys()}
        multi_category_count = 0
        new_categorizations = []

        classified_articles = []
        for article in articles:
            uri, title, summary, pub_date = article

            # Only count articles with stored categories
            if uri not in stored_categories:
                continue

            classified_articles.append(article)
            categories = stored_categories[uri]

            for cat in categories:
                if cat in category_counts:
                    category_counts[cat] += 1

            if len(categories) >= 3:
                multi_category_count += 1

        # Use only classified articles for stats
        articles = classified_articles

        # Find most active category
        most_active = max(category_counts.items(), key=lambda x: x[1]) if category_counts else (None, 0)

        # Get actual date range from articles
        actual_start = None
        actual_end = None
        if articles:
            dates = [a[3] for a in articles if a[3]]
            if dates:
                actual_start = str(min(dates))
                actual_end = str(max(dates))

        return PolicyStatsResponse(
            total_articles=len(articles),
            date_range_start=actual_start,
            date_range_end=actual_end,
            most_active_category=most_active[0] if most_active[1] > 0 else None,
            multi_category_count=multi_category_count,
            category_breakdown=category_counts
        )

    except Exception as e:
        logger.error(f"Error fetching policy stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/articles", response_model=PolicyArticlesListResponse)
async def get_policy_articles(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    categories: Optional[str] = Query(None, description="Comma-separated category filter"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    sort_by: str = Query("date", description="Sort by: date, relevance, category_count"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    session=Depends(verify_session)
):
    """
    Get paginated list of articles for the policy tracker.
    Uses stored categorizations when available.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get articles for the topic
        result = conn.execute(text("""
            SELECT uri, title, summary, news_source, publication_date,
                   sentiment, bias, factual_reporting
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
            ORDER BY publication_date DESC
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        all_articles = result.fetchall()
        article_uris = [a[0] for a in all_articles]

        # Get stored categories
        stored_categories = get_stored_categories(conn, article_uris)

        # Process and categorize articles
        processed_articles = []
        category_filter = [c.strip() for c in categories.split(',')] if categories else None
        new_categorizations = []

        for article in all_articles:
            uri, title, summary, source, pub_date, sentiment, bias, factual = article

            # Only show articles with stored categories
            if uri not in stored_categories:
                continue

            article_categories = stored_categories[uri]

            # Filter by category if specified
            if category_filter:
                if not any(cat in article_categories for cat in category_filter):
                    continue

            processed_articles.append({
                'uri': uri,
                'title': title,
                'summary': summary,
                'news_source': source,
                'publication_date': str(pub_date) if pub_date else None,
                'categories': article_categories,
                'sentiment': sentiment,
                'bias': bias,
                'factual_reporting': factual,
                'category_count': len(article_categories)
            })

        # Sort
        if sort_by == "category_count":
            processed_articles.sort(key=lambda x: x['category_count'], reverse=True)
        elif sort_by == "date":
            processed_articles.sort(
                key=lambda x: x['publication_date'] or '',
                reverse=True
            )

        # Paginate
        total_count = len(processed_articles)
        total_pages = (total_count + per_page - 1) // per_page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated = processed_articles[start_idx:end_idx]

        return PolicyArticlesListResponse(
            articles=[PolicyArticleResponse(**a) for a in paginated],
            total_count=total_count,
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )

    except Exception as e:
        logger.error(f"Error fetching policy articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/categories", response_model=List[PolicyCategoryResponse])
async def get_category_distribution(
    topic: Optional[str] = Query(DEFAULT_TRACKER_TOPIC, description="Topic to filter by"),
    days_back: int = Query(365, ge=0, le=730, description="Days to look back (0 = all time)"),
    session=Depends(verify_session)
):
    """
    Get distribution of articles across policy categories.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Try to get from stored categories first
        result = conn.execute(text("""
            SELECT pac.category, COUNT(DISTINCT pac.article_uri) as count
            FROM policy_article_categories pac
            JOIN articles a ON pac.article_uri = a.uri
            WHERE pac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            GROUP BY pac.category
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        stored_counts = {row[0]: row[1] for row in result.fetchall()}

        # If we have stored data, use it
        if stored_counts:
            category_counts = {cat: stored_counts.get(cat, 0) for cat in POLICY_CATEGORIES.keys()}
        else:
            # Fall back to real-time classification
            result = conn.execute(text("""
                SELECT title, summary
                FROM articles
                WHERE topic = :topic
                AND publication_date >= :start_date
                AND publication_date <= :end_date
            """), {"topic": topic, "start_date": start_date, "end_date": end_date})

            articles = result.fetchall()
            category_counts = {cat: 0 for cat in POLICY_CATEGORIES.keys()}

            for title, summary in articles:
                categories = categorize_article(title or '', summary or '')
                for cat in categories:
                    category_counts[cat] += 1

        total = sum(category_counts.values())

        # Calculate trends by comparing to previous period
        prev_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=days_back)).strftime('%Y-%m-%d')
        prev_result = conn.execute(text("""
            SELECT pac.category, COUNT(DISTINCT pac.article_uri) as count
            FROM policy_article_categories pac
            JOIN articles a ON pac.article_uri = a.uri
            WHERE pac.topic = :topic
            AND a.publication_date >= :prev_start
            AND a.publication_date < :start_date
            GROUP BY pac.category
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

            response.append(PolicyCategoryResponse(
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
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get articles with dates
        result = conn.execute(text("""
            SELECT title, summary, publication_date
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
            ORDER BY publication_date ASC
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        articles = result.fetchall()

        # Get stored categories for these articles
        article_uris_result = conn.execute(text("""
            SELECT uri FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})
        article_uris = [r[0] for r in article_uris_result.fetchall()]
        stored_categories = get_stored_categories(conn, article_uris)

        # Group by month
        monthly_data: Dict[str, Dict[str, int]] = {}

        # Also get URIs for each article
        uri_result = conn.execute(text("""
            SELECT uri, title, summary, publication_date
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
            ORDER BY publication_date ASC
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        for uri, title, summary, pub_date in uri_result.fetchall():
            if not pub_date:
                continue

            # Extract year-month
            try:
                if isinstance(pub_date, str):
                    month_key = pub_date[:7]  # YYYY-MM
                else:
                    month_key = pub_date.strftime('%Y-%m')
            except:
                continue

            if month_key not in monthly_data:
                monthly_data[month_key] = {cat: 0 for cat in POLICY_CATEGORIES.keys()}
                monthly_data[month_key]['_total'] = 0

            # Use stored categories if available
            if uri in stored_categories:
                categories = stored_categories[uri]
            else:
                categories = categorize_article(title or '', summary or '')

            monthly_data[month_key]['_total'] += 1

            for cat in categories:
                if cat in monthly_data[month_key]:
                    monthly_data[month_key][cat] += 1

        # Build response
        response = []
        for month in sorted(monthly_data.keys()):
            data = monthly_data[month].copy()
            total = data.pop('_total')
            response.append(TemporalDataResponse(
                month=month,
                total=total,
                by_category=data
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

            articles.append(PolicyArticleResponse(
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
    Get the policy tracker configuration including categories and keywords.
    """
    return {
        "default_topic": DEFAULT_TRACKER_TOPIC,
        "categories": POLICY_CATEGORIES
    }


# ============================================================================
# CSV Import Endpoint
# ============================================================================

# Map CSV column names to our policy category names
CSV_TO_CATEGORY_MAP = {
    "Violating Democratic Norms, Undermining Rule of Law": ["Undermining Democracy"],
    "Hollowing State / Weakening Federal Institutions": ["Hollowing State"],
    "Suppressing Dissent / Weaponising State Against 'Enemies'": ["Suppressing Dissent"],
    "Controlling Information Including Spreading Misinformation and Propaganda": ["Controlling Information"],
    "Control of Science & Health to Align with State Ideology": ["Attacking Science"],
    "Attacking Universities, Schools, Museums, Culture": ["Attacking Education"],
    "Weakening Civil Rights": ["Weakening Civil Rights"],
    "Corruption & Enrichment": ["Corruption"],
    "Aggressive Foreign Policy & Global Destabilisation": ["Foreign Policy"],
    "Nationalism & Immigration": ["Nationalism & Immigration"],
}


class CSVImportRequest(BaseModel):
    """Request for CSV import."""
    csv_content: str = Field(..., description="CSV file content as string")
    topic: str = Field(DEFAULT_TRACKER_TOPIC, description="Topic for imported articles")
    import_articles: bool = Field(True, description="Whether to create articles if they don't exist")


class CSVImportResponse(BaseModel):
    """Response from CSV import."""
    rows_processed: int
    articles_found: int
    articles_created: int
    categories_added: int
    errors: int
    message: str


@router.post("/import-csv", response_model=CSVImportResponse)
async def import_csv_data(
    request: CSVImportRequest,
    session=Depends(verify_session)
):
    """
    Import policy tracker data from CSV content.

    Expects CSV format from trumpactiontracker.info with columns:
    - Index, Date, Title, URL
    - 10 category columns with Yes/No values
    """
    import csv
    from io import StringIO

    db = get_database_instance()
    conn = db._temp_get_connection()

    stats = {
        "rows_processed": 0,
        "articles_found": 0,
        "articles_created": 0,
        "categories_added": 0,
        "errors": 0
    }

    try:
        # Parse CSV content
        lines = request.csv_content.strip().split('\n')

        # Find the header row (starts with "Index,")
        header_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("Index,"):
                header_idx = i
                break

        csv_content = '\n'.join(lines[header_idx:])
        reader = csv.DictReader(StringIO(csv_content))

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
                stats["articles_found"] += 1
            elif request.import_articles:
                try:
                    conn.execute(text("""
                        INSERT INTO articles (uri, title, summary, topic, publication_date, news_source, article_origin)
                        VALUES (:uri, :title, :summary, :topic, :pub_date, :source, 'external')
                        ON CONFLICT (uri) DO NOTHING
                    """), {
                        "uri": article_uri,
                        "title": title,
                        "summary": title,
                        "topic": request.topic,
                        "pub_date": pub_date,
                        "source": "Trump Action Tracker"
                    })
                    stats["articles_created"] += 1
                except Exception as e:
                    logger.warning(f"Error creating article: {e}")
                    stats["errors"] += 1
                    continue
            else:
                continue

            # Extract categories from Yes/No columns
            categories = []
            for csv_col, category_names in CSV_TO_CATEGORY_MAP.items():
                value = row.get(csv_col, "").strip().lower()
                if value == "yes":
                    categories.extend(category_names)

            categories = list(set(categories))

            # Store categories
            for category in categories:
                try:
                    conn.execute(text("""
                        INSERT INTO policy_article_categories
                        (article_uri, category, topic, classification_method)
                        VALUES (:uri, :category, :topic, 'csv_import')
                        ON CONFLICT (article_uri, category) DO NOTHING
                    """), {
                        "uri": article_uri,
                        "category": category,
                        "topic": request.topic
                    })
                    stats["categories_added"] += 1
                except Exception as e:
                    logger.warning(f"Error storing category: {e}")

            if stats["rows_processed"] % 100 == 0:
                conn.commit()

        conn.commit()

        return CSVImportResponse(
            rows_processed=stats["rows_processed"],
            articles_found=stats["articles_found"],
            articles_created=stats["articles_created"],
            categories_added=stats["categories_added"],
            errors=stats["errors"],
            message=f"Successfully imported {stats['rows_processed']} rows"
        )

    except Exception as e:
        logger.error(f"Error importing CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Analysis Endpoints
# ============================================================================

class CooccurrenceResponse(BaseModel):
    """Category co-occurrence data."""
    category1: str
    category2: str
    count: int
    percentage: float


@router.get("/cooccurrence", response_model=List[CooccurrenceResponse])
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
            SELECT pac.article_uri, pac.category
            FROM policy_article_categories pac
            JOIN articles a ON pac.article_uri = a.uri
            WHERE pac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
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
            response.append(CooccurrenceResponse(
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


class EscalationDataPoint(BaseModel):
    """Escalation metric for a time period."""
    period: str
    total_actions: int
    multi_category_count: int
    avg_categories: float
    top_categories: List[str]


@router.get("/escalation", response_model=List[EscalationDataPoint])
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
            SELECT a.uri, a.publication_date, pac.category
            FROM articles a
            JOIN policy_article_categories pac ON a.uri = pac.article_uri
            WHERE pac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
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

            response.append(EscalationDataPoint(
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
# EDA Analysis Endpoints (New)
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
            SELECT uri, title, summary
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
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
            SELECT title, summary, publication_date
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
            ORDER BY publication_date ASC
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
            SELECT title, summary
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
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
            SELECT title, summary
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
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
            SELECT title, summary
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
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
            SELECT title, summary, publication_date
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
            ORDER BY publication_date ASC
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
            SELECT publication_date
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
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
            SELECT DATE(a.publication_date) as pub_date, COUNT(DISTINCT a.uri) as count
            FROM articles a
            INNER JOIN policy_article_categories pac ON a.uri = pac.article_uri
            WHERE a.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            GROUP BY DATE(a.publication_date)
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
    """Get full 10x10 co-occurrence matrix for heatmap visualization."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(days_back)

        # Get articles with their categories
        result = conn.execute(text("""
            SELECT pac.article_uri, pac.category
            FROM policy_article_categories pac
            JOIN articles a ON pac.article_uri = a.uri
            WHERE pac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        # Build article -> categories mapping
        article_categories: Dict[str, List[str]] = {}
        for uri, category in result.fetchall():
            if uri not in article_categories:
                article_categories[uri] = []
            article_categories[uri].append(category)

        # Get ordered list of categories
        categories = list(POLICY_CATEGORIES.keys())
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
            {"role": "system", "content": "You are a policy analysis expert. Respond only with valid JSON."},
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
        valid_categories = list(POLICY_CATEGORIES.keys())
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
                        INSERT INTO policy_article_categories
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
            INSERT INTO policy_tracker_runs (topic, run_type, status)
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
            message=f"Batch semantic classification started. Track progress at /api/policy-tracker/classify/status/{run_id}"
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
            # Get all articles
            result = conn.execute(text("""
                SELECT uri, title, summary
                FROM articles
                WHERE topic = :topic
                AND publication_date >= :start_date
                AND publication_date <= :end_date
                ORDER BY publication_date DESC
                LIMIT :limit
            """), {"topic": topic, "start_date": start_date, "end_date": end_date, "limit": limit})
        else:
            # Get only uncategorized articles (by LLM method)
            result = conn.execute(text("""
                SELECT a.uri, a.title, a.summary
                FROM articles a
                LEFT JOIN policy_article_categories pac
                    ON a.uri = pac.article_uri
                    AND pac.classification_method = 'llm_semantic'
                WHERE a.topic = :topic
                AND a.publication_date >= :start_date
                AND a.publication_date <= :end_date
                AND pac.id IS NULL
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
                                INSERT INTO policy_article_categories
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
            UPDATE policy_tracker_runs
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
                UPDATE policy_tracker_runs
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
    Generate an LLM-powered narrative analysis of the policy tracker data.
    Returns a comprehensive analytical report similar to the EDA findings.
    """
    from app.ai_models import LiteLLMModel

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(request.days_back)

        # Gather all the data for the narrative

        # 1. Get category counts
        result = conn.execute(text("""
            SELECT pac.category, COUNT(DISTINCT pac.article_uri) as count
            FROM policy_article_categories pac
            JOIN articles a ON pac.article_uri = a.uri
            WHERE pac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            GROUP BY pac.category
            ORDER BY count DESC
        """), {"topic": request.topic, "start_date": start_date, "end_date": end_date})

        category_data = {row[0]: row[1] for row in result.fetchall()}

        # Get total articles and unique categorized articles count
        result = conn.execute(text("""
            SELECT COUNT(*) FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
        """), {"topic": request.topic, "start_date": start_date, "end_date": end_date})
        total_articles = result.fetchone()[0]

        # Count unique articles that have at least one category (not sum of category counts)
        result = conn.execute(text("""
            SELECT COUNT(DISTINCT pac.article_uri)
            FROM policy_article_categories pac
            JOIN articles a ON pac.article_uri = a.uri
            WHERE pac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
        """), {"topic": request.topic, "start_date": start_date, "end_date": end_date})
        total_categorized = result.fetchone()[0]

        category_breakdown = "\n".join([
            f"- {cat}: {count} articles ({round(count/total_articles*100, 1)}%)"
            for cat, count in sorted(category_data.items(), key=lambda x: x[1], reverse=True)
        ])

        # 2. Get theme data
        result = conn.execute(text("""
            SELECT title, summary
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
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
            {"role": "system", "content": """You are a senior policy analyst specializing in democratic backsliding and authoritarian transitions. You write critical analytical reports for civil society organizations monitoring threats to democracy.

Your role is to:
- Identify patterns consistent with authoritarian consolidation
- Call out violations of democratic norms without false balance
- Connect individual actions to broader anti-democratic strategies
- Use specific data to support critical analysis
- Write with urgency appropriate to the threat level

CRITICAL FORMATTING REQUIREMENT: You MUST use bullet points (lines starting with "- **Bold Header**:") in the Thematic Spotlight, Institutional Targets, and Forward-Looking Concerns sections. Each bullet must have a bold header followed by analysis. This is mandatory.

Do not normalize abnormal behavior. Do not both-sides threats to democracy. Be direct about what the data shows."""},
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
                INSERT INTO policy_tracker_narratives
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
    Generate an LLM-powered insight for a specific policy category.
    """
    from app.ai_models import LiteLLMModel

    if request.category not in POLICY_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {request.category}")

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        start_date, end_date = get_date_range_filter(request.days_back)

        # Get category count and trend
        result = conn.execute(text("""
            SELECT COUNT(DISTINCT pac.article_uri)
            FROM policy_article_categories pac
            JOIN articles a ON pac.article_uri = a.uri
            WHERE pac.category = :category
            AND pac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
        """), {"category": request.category, "topic": request.topic, "start_date": start_date, "end_date": end_date})

        article_count = result.fetchone()[0]

        # Get total for percentage
        result = conn.execute(text("""
            SELECT COUNT(*)
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
        """), {"topic": request.topic, "start_date": start_date, "end_date": end_date})

        total_articles = result.fetchone()[0]
        percentage = round((article_count / total_articles * 100) if total_articles > 0 else 0, 1)

        # Get trend by comparing periods
        prev_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=request.days_back)).strftime('%Y-%m-%d')

        result = conn.execute(text("""
            SELECT COUNT(DISTINCT pac.article_uri)
            FROM policy_article_categories pac
            JOIN articles a ON pac.article_uri = a.uri
            WHERE pac.category = :category
            AND pac.topic = :topic
            AND a.publication_date >= :prev_start
            AND a.publication_date < :start_date
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
            JOIN policy_article_categories pac ON a.uri = pac.article_uri
            WHERE pac.category = :category
            AND pac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
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
            {"role": "system", "content": "You are a policy analyst providing concise, insightful analysis."},
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

TRUMP_ACTION_TRACKER_BASE_URL = "https://www.trumpactiontracker.info"


def build_tracker_url(start_date: str, end_date: str) -> str:
    """Build Trump Action Tracker URL with date range."""
    return f"{TRUMP_ACTION_TRACKER_BASE_URL}/?start={start_date}&end={end_date}"


class URLImportRequest(BaseModel):
    """Request for URL-based import."""
    url: Optional[str] = Field(None, description="URL to fetch CSV from (optional - will use Trump Action Tracker with date range if not provided)")
    start_date: str = Field("2025-01-20", description="Start date for Trump Action Tracker (YYYY-MM-DD)")
    end_date: str = Field(None, description="End date for Trump Action Tracker (YYYY-MM-DD, defaults to today)")
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
            INSERT INTO policy_tracker_imports
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
            "message": f"Import started. Track progress at /api/policy-tracker/import/{import_id}/status"
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
    If no URL provided, fetches from Trump Action Tracker with specified date range.
    """
    import httpx

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Determine URL
        if request.url:
            fetch_url = request.url
        else:
            # Build Trump Action Tracker URL
            end_date = request.end_date or datetime.now().strftime('%Y-%m-%d')
            fetch_url = build_tracker_url(request.start_date, end_date)

        # Create import record
        result = conn.execute(text("""
            INSERT INTO policy_tracker_imports
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
            "message": f"Import started. Track progress at /api/policy-tracker/import/{import_id}/status"
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

        # Find the header row (starts with "Index,")
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
                        "source": "Trump Action Tracker"
                    })
                    stats["articles_created"] += 1
                except Exception as e:
                    logger.warning(f"Error creating article: {e}")
                    stats["errors"] += 1
                    continue

            # Extract categories from Yes/No columns
            categories = []
            for csv_col, category_names in CSV_TO_CATEGORY_MAP.items():
                value = row.get(csv_col, "").strip().lower()
                if value == "yes":
                    categories.extend(category_names)

            categories = list(set(categories))

            # Store categories
            for category in categories:
                try:
                    conn.execute(text("""
                        INSERT INTO policy_article_categories
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
                    UPDATE policy_tracker_imports
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

        # Run LLM classification if requested
        narrative_id = None
        if run_llm_classification:
            try:
                # Import asyncio for running async function
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # Run batch classification (process new articles)
                # This would be done via the existing semantic batch classification
                logger.info("LLM classification requested - would process new articles")
            except Exception as e:
                logger.warning(f"LLM classification failed: {e}")

        # Regenerate narrative if requested
        if regenerate_narrative:
            try:
                narrative_id = await save_narrative_to_db(topic, 365, conn)
            except Exception as e:
                logger.warning(f"Narrative generation failed: {e}")

        # Update import record with success
        conn.execute(text("""
            UPDATE policy_tracker_imports
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
            UPDATE policy_tracker_imports
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
            UPDATE policy_tracker_imports
            SET status = 'failed', completed_at = NOW(), error_message = :error
            WHERE id = :id
        """), {"id": import_id, "error": f"Failed to fetch URL: {str(e)}"})
        conn.commit()
    except Exception as e:
        logger.error(f"URL import {import_id} failed: {e}")
        conn.execute(text("""
            UPDATE policy_tracker_imports
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

        # Gather data for narrative (same as generate_narrative_analysis)
        result = conn.execute(text("""
            SELECT pac.category, COUNT(DISTINCT pac.article_uri) as count
            FROM policy_article_categories pac
            JOIN articles a ON pac.article_uri = a.uri
            WHERE pac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
            GROUP BY pac.category
            ORDER BY count DESC
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})

        category_data = {row[0]: row[1] for row in result.fetchall()}

        result = conn.execute(text("""
            SELECT COUNT(*) FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})
        total_articles = result.fetchone()[0]

        # Count unique articles that have at least one category
        result = conn.execute(text("""
            SELECT COUNT(DISTINCT pac.article_uri)
            FROM policy_article_categories pac
            JOIN articles a ON pac.article_uri = a.uri
            WHERE pac.topic = :topic
            AND a.publication_date >= :start_date
            AND a.publication_date <= :end_date
        """), {"topic": topic, "start_date": start_date, "end_date": end_date})
        total_categorized = result.fetchone()[0]

        category_breakdown = "\n".join([
            f"- {cat}: {count} articles ({round(count/total_articles*100, 1)}%)"
            for cat, count in sorted(category_data.items(), key=lambda x: x[1], reverse=True)
        ]) if total_articles > 0 else "No articles found"

        # Get theme, entity, escalation data
        result = conn.execute(text("""
            SELECT title, summary
            FROM articles
            WHERE topic = :topic
            AND publication_date >= :start_date
            AND publication_date <= :end_date
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
            {"role": "system", "content": """You are a senior policy analyst specializing in democratic backsliding and authoritarian transitions. You write critical analytical reports for civil society organizations monitoring threats to democracy.

Your role is to:
- Identify patterns consistent with authoritarian consolidation
- Call out violations of democratic norms without false balance
- Connect individual actions to broader anti-democratic strategies
- Use specific data to support critical analysis
- Write with urgency appropriate to the threat level

CRITICAL FORMATTING REQUIREMENT: You MUST use bullet points (lines starting with "- **Bold Header**:") in the Thematic Spotlight, Institutional Targets, and Forward-Looking Concerns sections. Each bullet must have a bold header followed by analysis. This is mandatory.

Do not normalize abnormal behavior. Do not both-sides threats to democracy. Be direct about what the data shows."""},
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
            INSERT INTO policy_tracker_narratives
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
            FROM policy_tracker_imports
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
            FROM policy_tracker_narratives
            WHERE topic = :topic
            ORDER BY generated_at DESC
            LIMIT 1
        """), {"topic": topic})

        row = result.fetchone()
        if not row:
            return None

        return SavedNarrativeResponse(
            id=row[0],
            topic=row[1],
            narrative=row[2],
            data_summary=row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {},
            days_back=row[4],
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
            SELECT COUNT(*) FROM policy_tracker_narratives WHERE topic = :topic
        """), {"topic": topic})
        total_count = result.fetchone()[0]

        # Get narratives
        result = conn.execute(text("""
            SELECT id, topic, narrative, data_summary, days_back,
                   date_range_start, date_range_end, generated_at
            FROM policy_tracker_narratives
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
    run_llm_classification: bool = False
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
async def get_feed_keyword_groups(session=Depends(verify_session)):
    """
    Get keyword groups with article counts.
    Returns total articles per group and how many are already categorized in policy tracker.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Get keyword groups with article counts
        # Uses keyword_groups table and counts articles by topic
        result = conn.execute(text("""
            SELECT
                kg.id,
                kg.name,
                kg.topic,
                COUNT(DISTINCT a.uri) as total_articles,
                COUNT(DISTINCT pac.article_uri) as already_categorized
            FROM keyword_groups kg
            LEFT JOIN articles a ON a.topic = kg.topic
            LEFT JOIN policy_article_categories pac ON a.uri = pac.article_uri
            GROUP BY kg.id, kg.name, kg.topic
            ORDER BY kg.name
        """))

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
    Since articles are already in the articles table with topics, this runs policy categorization.
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
            INSERT INTO policy_tracker_imports
            (topic, import_type, status, started_at, run_llm_classification)
            VALUES (:topic, 'keyword_group_process', 'processing', CURRENT_TIMESTAMP, :run_llm)
            RETURNING id
        """), {
            "topic": group_topic,
            "run_llm": request.run_llm_classification
        })
        import_id = result.fetchone()[0]
        conn.commit()

        # Get uncategorized articles for this topic
        result = conn.execute(text("""
            SELECT a.uri, a.title, a.summary
            FROM articles a
            LEFT JOIN policy_article_categories pac ON a.uri = pac.article_uri
            WHERE a.topic = :topic
            AND pac.article_uri IS NULL
            LIMIT 1000
        """), {"topic": group_topic})

        articles = result.fetchall()
        logger.info(f"Processing {len(articles)} uncategorized articles for topic '{group_topic}' (LLM: {request.run_llm_classification})")

        if not articles:
            # No articles to process
            conn.execute(text("""
                UPDATE policy_tracker_imports
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

        if request.run_llm_classification:
            # Use LLM-based classification in background (accurate but slow)
            # Return immediately and process in background
            conn.close()  # Close this connection, background task will open its own

            background_tasks.add_task(
                _run_import_from_feed_task,
                import_id,
                group_topic,
                articles,
                request.regenerate_narrative
            )

            return ImportFromFeedResponse(
                import_id=import_id,
                status="processing",
                message=f"Started LLM classification for {len(articles)} articles in background. Check import status for progress.",
                articles_imported=0,
                articles_skipped=0
            )

        # Use keyword-based categorization (fast, runs synchronously)
        articles_categorized = 0
        articles_no_match = 0
        articles_error = 0

        for uri, title, summary in articles:
            if not title:
                articles_no_match += 1
                continue

            try:
                categories = categorize_article(title or '', summary or '')
                if categories:
                    for category in categories:
                        conn.execute(text("""
                            INSERT INTO policy_article_categories
                            (article_uri, category, topic, classification_method)
                            VALUES (:uri, :category, :topic, 'keyword')
                            ON CONFLICT (article_uri, category) DO NOTHING
                        """), {
                            "uri": uri,
                            "category": category,
                            "topic": group_topic
                        })
                    articles_categorized += 1
                    logger.debug(f"Keyword categorized '{title[:50]}' into {categories}")
                else:
                    articles_no_match += 1
            except Exception as e:
                logger.warning(f"Failed to categorize article {uri}: {e}")
                conn.rollback()  # Reset transaction state after error
                articles_error += 1

        conn.commit()
        logger.info(f"Keyword categorization complete: {articles_categorized} categorized, {articles_no_match} no match, {articles_error} errors")

        # Update import record
        conn.execute(text("""
            UPDATE policy_tracker_imports
            SET status = 'completed',
                completed_at = CURRENT_TIMESTAMP,
                articles_created = :categorized,
                articles_updated = :no_match,
                errors = :errors
            WHERE id = :import_id
        """), {
            "import_id": import_id,
            "categorized": articles_categorized,
            "no_match": articles_no_match,
            "errors": articles_error
        })
        conn.commit()

        # Optionally trigger narrative generation
        if request.regenerate_narrative and articles_categorized > 0:
            background_tasks.add_task(
                _run_narrative_generation_task,
                group_topic,
                365  # days_back
            )

        # Build informative message
        if articles_categorized > 0:
            message = f"Categorized {articles_categorized} articles into policy categories"
        elif articles_no_match > 0:
            message = f"No articles matched policy keywords ({articles_no_match} checked)"
        else:
            message = "No uncategorized articles found"

        return ImportFromFeedResponse(
            import_id=import_id,
            status="completed",
            message=message,
            articles_imported=articles_categorized,
            articles_skipped=articles_no_match
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
                    UPDATE policy_tracker_imports
                    SET status = 'failed', error_message = :error, completed_at = CURRENT_TIMESTAMP
                    WHERE id = :import_id
                """), {"import_id": import_id, "error": str(e)})
                conn.commit()
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


async def _run_import_from_feed_task(import_id: int, group_topic: str, articles: list, regenerate_narrative: bool):
    """Background task to run LLM classification for import-from-feed."""
    import asyncio

    db = get_database_instance()
    conn = db._temp_get_connection()

    articles_categorized = 0
    articles_no_match = 0
    articles_error = 0

    try:
        for uri, title, summary in articles:
            if not title:
                articles_no_match += 1
                continue

            try:
                # Add small delay to avoid rate limiting
                await asyncio.sleep(0.3)

                result = await llm_categorize_article(title or "", summary or "", "gpt-4o-mini")

                if result["categories"]:
                    for category in result["categories"]:
                        conn.execute(text("""
                            INSERT INTO policy_article_categories
                            (article_uri, category, topic, classification_method, confidence)
                            VALUES (:uri, :category, :topic, 'llm_semantic', :confidence)
                            ON CONFLICT (article_uri, category)
                            DO UPDATE SET classification_method = 'llm_semantic', confidence = :confidence
                        """), {
                            "uri": uri,
                            "category": category,
                            "topic": group_topic,
                            "confidence": result["confidence"]
                        })
                    articles_categorized += 1
                    logger.info(f"LLM categorized '{title[:50]}' into {result['categories']}")

                    # Commit progress periodically to keep connection alive
                    if articles_categorized % 10 == 0:
                        conn.commit()
                        logger.info(f"Progress: {articles_categorized}/{len(articles)} categorized so far...")
                else:
                    articles_no_match += 1
            except Exception as e:
                logger.warning(f"Failed to LLM categorize article {uri}: {e}")
                try:
                    conn.rollback()  # Reset transaction state after error
                except:
                    pass
                articles_error += 1

        conn.commit()
        logger.info(f"LLM categorization complete: {articles_categorized} categorized, {articles_no_match} no match, {articles_error} errors")

        # Update import record
        conn.execute(text("""
            UPDATE policy_tracker_imports
            SET status = 'completed',
                completed_at = CURRENT_TIMESTAMP,
                articles_created = :categorized,
                articles_updated = :no_match,
                errors = :errors
            WHERE id = :import_id
        """), {
            "import_id": import_id,
            "categorized": articles_categorized,
            "no_match": articles_no_match,
            "errors": articles_error
        })
        conn.commit()

        # Optionally trigger narrative generation
        if regenerate_narrative and articles_categorized > 0:
            await _run_narrative_generation_task(group_topic, 365)

    except Exception as e:
        logger.error(f"Error in background import task: {e}")
        try:
            conn.rollback()
        except:
            pass
        try:
            conn.execute(text("""
                UPDATE policy_tracker_imports
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
        from app.ai_models import get_ai_model

        db = get_database_instance()
        conn = db._temp_get_connection()

        try:
            start_date, end_date = get_date_range_filter(days_back)

            # Get articles to classify
            if reprocess:
                result = conn.execute(text("""
                    SELECT uri, title, summary
                    FROM articles
                    WHERE topic = :topic
                    AND publication_date >= :start_date
                    AND publication_date <= :end_date
                    LIMIT :limit
                """), {"topic": topic, "start_date": start_date, "end_date": end_date, "limit": limit})
            else:
                result = conn.execute(text("""
                    SELECT a.uri, a.title, a.summary
                    FROM articles a
                    LEFT JOIN policy_article_categories pac ON a.uri = pac.article_uri
                    WHERE a.topic = :topic
                    AND a.publication_date >= :start_date
                    AND a.publication_date <= :end_date
                    AND pac.article_uri IS NULL
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
                                INSERT INTO policy_article_categories
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
        from app.ai_models import get_ai_model

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
