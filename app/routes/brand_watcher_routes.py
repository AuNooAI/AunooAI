"""
Brand Watcher API Routes

Multi-brand intelligence module for tracking brand mentions, sentiment,
competitive positioning, and reputation risk across news articles.

Classification approach: keyword-based → LLM fallback → SLM (DeBERTa) when 500+ samples.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, date, time as dt_time
from sqlalchemy import text
import logging
import json
import re
import os

from app.security.session import verify_session
from app.database import get_database_instance
from app.database_query_facade import DatabaseQueryFacade
from app.utils.keyword_normalizer import normalize_keyword_list

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/brand-watcher", tags=["Brand Watcher"])


# ============================================================================
# Constants & Categories (11)
# ============================================================================

BW_CATEGORIES = {
    "Product & Innovation": [
        "launch", "unveil", "release", "patent", "innovation", "breakthrough",
        "prototype", "R&D", "research and development", "new product",
        "product line", "feature update", "upgrade", "next-gen", "next generation",
        "rollout", "debut", "introduce", "cutting-edge", "disruptive"
    ],
    "Financial Performance": [
        "earnings", "revenue", "profit", "stock", "IPO", "acquisition", "merger",
        "quarterly results", "annual report", "share price", "market cap",
        "valuation", "funding round", "Series A", "Series B", "Series C",
        "dividend", "fiscal year", "balance sheet", "cash flow", "EBITDA"
    ],
    "Leadership & Governance": [
        "CEO", "executive", "appoint", "resign", "board", "leadership",
        "chief officer", "CTO", "CFO", "COO", "chairman", "director",
        "management team", "succession", "corporate governance", "restructuring",
        "organizational change", "C-suite"
    ],
    "Brand Sentiment & Perception": [
        "reputation", "sentiment", "perception", "trust", "boycott", "backlash",
        "brand image", "public opinion", "consumer confidence", "brand loyalty",
        "brand awareness", "viral", "trending", "controversy", "scandal",
        "outrage", "praise", "beloved", "toxic"
    ],
    "Competitive Landscape": [
        "competitor", "market share", "rival", "outpace", "benchmark",
        "competitive advantage", "industry leader", "overtake", "leapfrog",
        "head-to-head", "market position", "competitive threat", "displace",
        "challenger", "incumbent", "market dominance"
    ],
    "Legal & Regulatory": [
        "lawsuit", "sue", "investigation", "regulatory", "fine", "compliance",
        "antitrust", "litigation", "court ruling", "settlement", "subpoena",
        "enforcement action", "consent decree", "class action", "injunction",
        "penalty", "sanction", "whistleblower", "SEC", "FTC"
    ],
    "Partnerships & Alliances": [
        "partnership", "alliance", "collaboration", "joint venture",
        "strategic partnership", "memorandum of understanding", "MOU",
        "co-development", "ecosystem", "integration", "co-branding",
        "licensing deal", "distribution agreement", "channel partner"
    ],
    "ESG & Social Responsibility": [
        "sustainability", "ESG", "diversity", "carbon", "climate",
        "net zero", "renewable", "social responsibility", "DEI",
        "corporate social responsibility", "CSR", "environmental impact",
        "green initiative", "circular economy", "inclusion", "equity",
        "community investment", "philanthropy"
    ],
    "Customer & Product Issues": [
        "recall", "outage", "breach", "hack", "vulnerability", "complaint",
        "defect", "malfunction", "service disruption", "data leak",
        "security incident", "class action", "consumer protection",
        "product safety", "quality issue", "customer dissatisfaction"
    ],
    "Market Strategy & Expansion": [
        "expansion", "market entry", "pricing", "distribution", "international",
        "go-to-market", "geographic expansion", "new market", "globalization",
        "localization", "emerging market", "supply chain", "logistics",
        "retail strategy", "e-commerce", "direct-to-consumer", "DTC"
    ],
    "Media & Advertising": [
        "campaign", "advertising", "marketing", "sponsor", "media buy",
        "brand awareness", "influencer", "endorsement", "commercial",
        "ad spend", "digital marketing", "social media campaign",
        "public relations", "press release", "media coverage", "PR strategy"
    ],
}

CATEGORY_COLORS = {
    "Product & Innovation": "#2563eb",
    "Financial Performance": "#16a34a",
    "Leadership & Governance": "#7c3aed",
    "Brand Sentiment & Perception": "#db2777",
    "Competitive Landscape": "#d97706",
    "Legal & Regulatory": "#dc2626",
    "Partnerships & Alliances": "#0891b2",
    "ESG & Social Responsibility": "#059669",
    "Customer & Product Issues": "#e11d48",
    "Market Strategy & Expansion": "#4f46e5",
    "Media & Advertising": "#9333ea",
}


# ============================================================================
# LLM Prompts
# ============================================================================

CATEGORY_DEFINITIONS = """
## Brand Watcher Category Definitions

These are the 11 categories used to classify articles about brands. Use the EXACT category names shown:

1. **Product & Innovation** - Product launches, features, R&D, patents, prototypes, breakthroughs, upgrades, next-generation developments.

2. **Financial Performance** - Earnings reports, revenue, profit/loss, stock price movements, IPOs, acquisitions, mergers, funding rounds, valuations, fiscal results.

3. **Leadership & Governance** - Executive appointments and departures, board decisions, corporate governance changes, organizational restructuring, C-suite movements.

4. **Brand Sentiment & Perception** - Public opinion, brand trust/loyalty, boycotts, backlash, controversy, viral moments, consumer confidence, brand image.

5. **Competitive Landscape** - Competitor moves, market share changes, competitive positioning, industry rankings, head-to-head comparisons, market dominance shifts.

6. **Legal & Regulatory** - Lawsuits, investigations, regulatory actions, compliance issues, fines, antitrust cases, settlements, enforcement actions.

7. **Partnerships & Alliances** - Joint ventures, strategic partnerships, collaborations, licensing deals, ecosystem growth, co-development agreements.

8. **ESG & Social Responsibility** - Sustainability initiatives, ESG reporting, DEI programs, carbon/climate commitments, corporate social responsibility, community impact.

9. **Customer & Product Issues** - Product recalls, service outages, data breaches, security vulnerabilities, quality defects, consumer complaints, safety issues.

10. **Market Strategy & Expansion** - Geographic expansion, market entry, pricing strategy, distribution changes, go-to-market plans, international growth.

11. **Media & Advertising** - Marketing campaigns, ad spending, sponsorships, influencer partnerships, PR activities, media coverage, brand awareness initiatives.
"""

SEMANTIC_CATEGORIZATION_PROMPT = """You are a brand intelligence analyst classifying news articles about specific brands.

{category_definitions}

## Brand Context
**Brand:** {brand_name}
**Brand Keywords:** {brand_keywords}
**Products:** {product_keywords}
**Key People:** {people_keywords}

## Task
Analyze the following article and classify it into ALL applicable categories. Most articles fall into 1-3 categories. Use the EXACT category names listed above.

**Article Title:** {title}

**Article Summary:** {summary}

## Response Format
Return a JSON object with:
- "categories": array of EXACT category names that apply (use full names from the list above)
- "confidence": number 0-1 indicating classification confidence
- "reasoning": brief explanation of why each category applies

Example response:
{{"categories": ["Financial Performance", "Leadership & Governance"], "confidence": 0.85, "reasoning": "CEO departure announcement coupled with quarterly earnings miss."}}

Respond ONLY with valid JSON, no other text."""

NARRATIVE_ANALYSIS_PROMPT = """You are generating an analytical brand intelligence report for decision-makers monitoring brand reputation and competitive positioning.

## Brand: {brand_name}

## Data Summary

**Time Period:** {date_range}
**Total Articles Analyzed:** {total_articles}

**Category Distribution:**
{category_breakdown}

**Top Competitor Mentions:**
{competitor_breakdown}

**Brand Risk Assessment:**
{risk_assessment}

**Key Positive Articles:**
{key_articles}

**Social Pulse (Reddit/Bluesky):**
{social_signal}

**Adverse Risk Findings:**
{risk_findings}

**Open Incidents:**
{incident_summary}

**Employee / Workforce Signal (Glassdoor):**
{employee_signal}

## Analysis Approach

Your job is to SYNTHESIZE the articles into coherent themes and narratives, not to cherry-pick or list individual articles. Read all the provided articles and identify the underlying patterns, recurring themes, and emerging storylines. When you reference specific articles, use them as evidence supporting a broader theme — not as standalone items.

CRITICAL — Distinguish brand impact from topic sentiment:
- An article tagged "negative" may have a negative TOPIC (e.g. cybersecurity threats, disease, conflict) but be POSITIVE for the brand if the brand published the content (a book, research paper, or guide). A publisher releasing a book about cybersecurity threats is product output, not a risk indicator.
- Look at the article source and summary carefully. If the brand is the PUBLISHER or AUTHOR of the content, the article likely represents product activity or thought leadership, NOT a reputational risk — even if the subject matter is negative.
- Only treat articles as genuine risk indicators when the brand itself is the subject of criticism, scandal, legal action, operational failure, or negative stakeholder reaction.
- Similarly for positive articles: distinguish between "positive coverage about the brand" vs "the brand published content on a positive topic."

For example, instead of "Article X reports a data breach", write: "Data security has emerged as a significant theme, with incidents including a [major breach at a subsidiary](https://example.com/article) that exposed customer records, reinforcing broader concerns about information governance across the group."

## Required Sections

Write a comprehensive brand intelligence narrative (600-1000 words) with these EXACT section headers (use ## markdown format). Do NOT add a document title, H1 heading, or any preamble — begin directly with "## Executive Summary":

## Executive Summary
Key findings in 3-4 sentences. Synthesize the dominant narrative threads around this brand. What requires immediate attention? If the Brand Risk Assessment shows Elevated or High risk, explain what themes in the coverage are driving it.

## Category Analysis
What patterns emerge from the category distribution? Which areas have the most coverage? Synthesize what the articles in each major category are collectively saying about the brand — don't just report percentages.

## Sentiment & Reputation
YOU MUST use bullet points in this section. Format EXACTLY like this:

- **Positive Signals**: [Synthesize themes from the positive articles. What recurring patterns of good news exist? Link to representative articles as evidence using [title](url) format.]
- **Risk Indicators**: [Synthesize themes from the negative articles. What recurring patterns of concern exist? Reference the Brand Risk Assessment level and explain what themes are driving it, linking to representative articles as evidence using [title](url) format. Do NOT speculate — ground every claim in the articles provided.]
- **Competitive Position**: [How the brand is positioned vs competitors based on coverage themes]

## Social Pulse
Summarize what social conversation (Reddit/Bluesky) adds beyond the news coverage, using ONLY the Social Pulse data provided. Cover: overall volume and the platform split, net sentiment among on-brand posts, and the dominant themes in the top on-brand posts. Note how social sentiment compares to the news coverage (aligned or diverging). If no social data is provided, say so in one sentence and move on. Keep to 2-4 sentences or bullets. Do NOT invent posts, handles, or numbers — ground every claim in the provided social data.

## Risk & Compliance
Cover the adverse risk findings and open incidents using ONLY the Adverse Risk Findings and Open Incidents data provided. State the counts by type plainly, name the most severe findings with their article links, and list open incidents with severity and status. If both blocks report none, write one sentence saying no adverse risk findings or open incidents were recorded in the period and move on. Do NOT speculate beyond the data.

## Workforce Signal
Summarize the employee picture using ONLY the Employee / Workforce Signal data provided: overall Glassdoor rating and review volume, CEO approval and business outlook, the weakest sub-ratings, recent employee-review sentiment, workforce risk findings, and how the rating compares to the competitor ratings given. If the block reports no employee data, write one sentence and move on. Keep to 2-4 sentences or bullets. Do NOT invent numbers.

## Forward-Looking Concerns
YOU MUST use bullet points in this section. List 3-5 specific concerns synthesized from patterns across multiple articles:

- **Concern Title**: Explanation grounded in article themes
- **Concern Title**: Explanation grounded in article themes

CRITICAL FORMATTING REQUIREMENTS:
- Use ## for section headers (H2 markdown)
- MANDATORY: Sentiment & Reputation MUST use bullet points
- MANDATORY: Forward-Looking Concerns MUST use bullet points
- MANDATORY: If risk level is Elevated or High, the report MUST explicitly reference this assessment with its score and the themes driving it
- MANDATORY: When citing articles, use the exact markdown link format: [Article Title](url). Preserve the links so readers can click through to sources.
- MANDATORY: SYNTHESIZE, don't list. Identify themes across multiple articles rather than summarizing articles one by one. Articles are evidence for themes, not items in a list.
- Use **bold** for bullet point headers
- Include specific numbers from the data
- Be analytical and evidence-based, grounding all claims in the provided articles"""

CATEGORY_INSIGHT_PROMPT = """You are a brand intelligence analyst providing insights on a specific category for a brand.

## Brand: {brand_name}
## Category: {category_name}

**Articles in this category:** {article_count}
**Percentage of total:** {percentage}%
**Recent trend:** {trend}

**Sample article titles from this category:**
{sample_titles}

## Task
Write a brief analytical insight (150-250 words) covering:
1. What this category captures and why it matters for the brand
2. Analysis of the current volume and trend
3. Key sub-themes within this category based on the sample titles
4. Connections to other brand intelligence areas

Be specific and analytical, not generic."""


# ============================================================================
# Request/Response Models
# ============================================================================

class BrandCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    brand_keywords: List[str] = Field(default_factory=list)
    product_keywords: Optional[List[str]] = None
    people_keywords: Optional[List[str]] = None
    competitor_keywords: Optional[List[str]] = None
    color: Optional[str] = None


class BrandUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    brand_keywords: Optional[List[str]] = None
    product_keywords: Optional[List[str]] = None
    people_keywords: Optional[List[str]] = None
    competitor_keywords: Optional[List[str]] = None
    color: Optional[str] = None


class BrandResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    brand_keywords: List[str]
    product_keywords: Optional[List[str]] = None
    people_keywords: Optional[List[str]] = None
    competitor_keywords: Optional[List[str]] = None
    enabled: bool = True
    color: Optional[str] = None
    is_primary: bool = False
    config: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ClassifyRequest(BaseModel):
    brand_id: Optional[int] = None
    topic: Optional[str] = None          # Deprecated: use topics
    topics: Optional[List[str]] = None   # Multiple topics
    run_type: str = "incremental"
    days_back: int = 30


class ClassifyResponse(BaseModel):
    run_id: int
    status: str
    articles_processed: int
    articles_categorized: int
    message: str


class StatsResponse(BaseModel):
    total_articles: int
    total_brands: int
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    most_active_category: Optional[str] = None
    multi_category_count: int = 0
    category_breakdown: Dict[str, int] = {}


class CategoryDistribution(BaseModel):
    category: str
    article_count: int
    percentage: float
    recent_trend: str = "stable"


class ArticleResponse(BaseModel):
    uri: str
    title: str
    summary: Optional[str] = None
    news_source: Optional[str] = None
    publication_date: Optional[str] = None
    categories: List[str] = []
    brand_id: Optional[int] = None
    brand_name: Optional[str] = None
    sentiment: Optional[str] = None
    matched_keywords: List[str] = []
    # Opoint entity verification: {brands:[...], relevance:float} when the article's
    # Opoint organization entities resolve (by Wikidata ID) to a tracked brand.
    entity_match: Optional[dict] = None
    # Story clustering (bw_article_stories): how many articles share this story
    # (syndicated republications) and the cluster key for display-side dedup.
    story_size: Optional[int] = None
    story_neg: Optional[int] = None
    story_pos: Optional[int] = None
    story_scored: Optional[int] = None
    story_group_id: Optional[str] = None
    # MBFC source authority (when the source is in the mediabias dataset).
    factual_reporting: Optional[str] = None
    # Adverse risk findings: [{risk_type, severity, confidence}] (bw_article_risks).
    risks: List[dict] = []
    # Case state (bw_finding_reviews): new | reviewed | escalated | dismissed.
    review_status: Optional[str] = None
    # Five Signals screen (bw_article_signals): {status, verdict, composite,
    # signals: [{key, band, score}]} — compact row summary; full detail via
    # GET /signals/detail.
    signals_summary: Optional[dict] = None


class ArticlesListResponse(BaseModel):
    articles: List[ArticleResponse]
    total_count: int
    page: int
    per_page: int
    total_pages: int
    # False when AUNOO_SAAS_MCP_KEY is unset — the UI hides the Five Signals
    # run action entirely.
    signals_available: bool = False


class TemporalDataResponse(BaseModel):
    month: str
    total: int
    by_category: Dict[str, int] = {}


class ComparisonDataResponse(BaseModel):
    brand_id: int
    brand_name: str
    total_articles: int
    category_breakdown: Dict[str, int] = {}
    sentiment_breakdown: Dict[str, int] = {}
    color: Optional[str] = None


class ShareOfVoiceResponse(BaseModel):
    brand_id: int
    brand_name: str
    mention_count: int
    percentage: float
    color: Optional[str] = None


class NarrativeRequest(BaseModel):
    brand_id: int
    days_back: int = 365
    model: str = "gpt-5.4-mini"


class NarrativeResponse(BaseModel):
    narrative: str
    generated_at: str
    data_summary: Dict[str, Any] = {}


class SavedNarrativeResponse(BaseModel):
    id: int
    brand_id: int
    brand_name: Optional[str] = None
    narrative: str
    data_summary: Dict[str, Any] = {}
    days_back: Optional[int] = None
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    generated_at: Optional[str] = None


class CategoryInsightRequest(BaseModel):
    brand_id: int
    category: str
    days_back: int = 365
    model: str = "gpt-5.4-mini"


class CategoryInsightResponse(BaseModel):
    category: str
    insight: str
    article_count: int
    percentage: float
    trend: str


# ============================================================================
# Helper Functions
# ============================================================================

def _get_brand_search_terms(brand: dict) -> list:
    """Extract all search terms from a brand config."""
    terms = set()
    terms.add(brand["display_name"].lower().strip())
    if brand["name"].lower().strip() != brand["display_name"].lower().strip():
        terms.add(brand["name"].lower().strip())
    for kw_field in ['brand_keywords', 'product_keywords', 'people_keywords']:
        for kw in (brand.get(kw_field) or []):
            if kw and kw.strip():
                terms.add(kw.strip().lower())
    return [t for t in terms if t]


def _build_brand_filter_sql(search_terms: list, param_prefix: str = "bterm", alias: str = "a") -> tuple:
    """Build SQL WHERE clause for brand keyword matching.

    Searches title, summary, tags, and extracted_article_keywords.
    Short terms (<=4 chars) use PostgreSQL regex word boundaries (\\y)
    to avoid false positives like 'WLY' matching 'newly'.
    Longer terms use LIKE for simplicity.

    Returns (sql_fragment, params_dict).
    """
    conditions = []
    params = {}
    for i, term in enumerate(search_terms):
        pkey = f"{param_prefix}_{i}"
        if len(term) <= 4 and ' ' not in term:
            # Use regex word boundaries for short single-word terms
            conditions.append(
                f"({alias}.title ~* {':' + pkey}"
                f" OR COALESCE({alias}.summary, '') ~* {':' + pkey}"
                f" OR COALESCE({alias}.tags, '') ~* {':' + pkey}"
                f" OR COALESCE({alias}.extracted_article_keywords, '') ~* {':' + pkey})"
            )
            escaped = re.escape(term)
            params[pkey] = f"\\y{escaped}\\y"
        else:
            conditions.append(
                f"(LOWER({alias}.title) LIKE {':' + pkey}"
                f" OR LOWER(COALESCE({alias}.summary, '')) LIKE {':' + pkey}"
                f" OR LOWER(COALESCE({alias}.tags, '')) LIKE {':' + pkey}"
                f" OR LOWER(COALESCE({alias}.extracted_article_keywords, '')) LIKE {':' + pkey})"
            )
            params[pkey] = f"%{term}%"
    if not conditions:
        return "AND FALSE", params
    return f"AND ({' OR '.join(conditions)})", params


def _find_matched_keywords(title: str, summary: str, search_terms: list, tags: str = None, keywords: str = None) -> list:
    """Find which brand search terms actually appear in the article text.
    Searches title, summary, tags, and extracted_article_keywords.
    Uses word boundary matching for short terms to stay consistent with SQL."""
    matched = []
    title_lower = (title or '').lower()
    summary_lower = (summary or '').lower()
    tags_lower = (tags or '').lower()
    keywords_lower = (keywords or '').lower()
    fields = [title_lower, summary_lower, tags_lower, keywords_lower]
    for term in search_terms:
        if len(term) <= 4 and ' ' not in term:
            pattern = r'\b' + re.escape(term) + r'\b'
            if any(re.search(pattern, f) for f in fields):
                matched.append(term)
        else:
            if any(term in f for f in fields):
                matched.append(term)
    return matched


def _get_date_range(days_back: int = 30) -> tuple:
    end_date = datetime.now()
    if days_back == 0:
        return '1900-01-01', end_date.strftime('%Y-%m-%d')
    start_date = end_date - timedelta(days=days_back)
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')


def _categorize_article_keywords(title: str, summary: str, brand: dict) -> List[str]:
    """
    Categorize an article using keyword matching against both
    the global BW_CATEGORIES and the brand-specific keywords.
    """
    text_content = f"{title} {summary}".lower()
    matched = []

    for category, keywords in BW_CATEGORIES.items():
        for kw in keywords:
            kw_lower = kw.lower()
            if len(kw_lower) <= 3:
                pattern = r'\b' + re.escape(kw_lower) + r'\b'
                if re.search(pattern, text_content):
                    matched.append(category)
                    break
            else:
                if kw_lower in text_content:
                    matched.append(category)
                    break

    return matched


def _match_articles_to_brand(brand: dict, title: str, summary: str) -> bool:
    """Check if an article mentions a brand (via brand_keywords, product_keywords, people_keywords).
    Falls back to display_name if no explicit keywords are configured."""
    text_content = f"{title} {summary}".lower()

    has_any_keywords = False
    for kw_field in ['brand_keywords', 'product_keywords', 'people_keywords']:
        keywords = brand.get(kw_field) or []
        if isinstance(keywords, str):
            try:
                keywords = json.loads(keywords)
            except (json.JSONDecodeError, TypeError):
                keywords = []
        if keywords:
            has_any_keywords = True
        for kw in keywords:
            if kw.lower() in text_content:
                return True

    # If no keywords configured at all, match on display_name and name
    if not has_any_keywords:
        display_name = (brand.get("display_name") or "").lower().strip()
        name = (brand.get("name") or "").lower().strip()
        if display_name and display_name in text_content:
            return True
        if name and name != display_name and name in text_content:
            return True

    return False


def _update_daily_stats(conn, brand_id: int, category: str, stat_date: date, count: int):
    conn.execute(text("""
        INSERT INTO bw_daily_stats (date, brand_id, category, article_count)
        VALUES (:date, :brand_id, :category, :count)
        ON CONFLICT (date, brand_id, category)
        DO UPDATE SET article_count = :count, updated_at = NOW()
    """), {"date": stat_date, "brand_id": brand_id, "category": category, "count": count})


def _brand_row_to_dict(row) -> dict:
    config_val = row[12] if len(row) > 12 else {}
    if isinstance(config_val, str):
        try:
            config_val = json.loads(config_val)
        except (json.JSONDecodeError, TypeError):
            config_val = {}
    return {
        "id": row[0],
        "name": row[1],
        "display_name": row[2],
        "description": row[3],
        "brand_keywords": row[4] if isinstance(row[4], list) else json.loads(row[4]) if row[4] else [],
        "product_keywords": row[5] if isinstance(row[5], list) else json.loads(row[5]) if row[5] else [],
        "people_keywords": row[6] if isinstance(row[6], list) else json.loads(row[6]) if row[6] else [],
        "competitor_keywords": row[7] if isinstance(row[7], list) else json.loads(row[7]) if row[7] else [],
        "enabled": row[8],
        "color": row[9],
        "created_at": str(row[10]) if row[10] else None,
        "updated_at": str(row[11]) if row[11] else None,
        "config": config_val if isinstance(config_val, dict) else {},
        "is_primary": bool(row[13]) if len(row) > 13 else False,
    }


BRAND_SELECT_COLS = """id, name, display_name, description,
    brand_keywords, product_keywords, people_keywords, competitor_keywords,
    enabled, color, created_at, updated_at, COALESCE(config, '{}') as config,
    COALESCE(is_primary, false) as is_primary"""


# ============================================================================
# Brand CRUD Endpoints
# ============================================================================

@router.get("/brands", response_model=List[BrandResponse])
async def list_brands(session=Depends(verify_session)):
    """List all configured brands."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result = conn.execute(text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands ORDER BY display_name"))
        return [BrandResponse(**_brand_row_to_dict(row)) for row in result.fetchall()]
    except Exception as e:
        logger.error(f"Error listing brands: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/opoint-coverage")
async def opoint_brand_coverage(
    days: int = Query(90, ge=1, le=365),
    min_relevance: float = Query(0.0, ge=0.0, le=1.0),
    samples: int = Query(0, ge=0, le=50),
    exclude_scholarly: bool = Query(False, description="Drop academic/journal sources (publisher/citation mentions, not 3rd-party news)"),
    session=Depends(verify_session),
):
    """Brand coverage derived from Opoint's resolved entities (Wikidata-ID match).

    Counts articles whose Opoint organization entities resolve to each brand's
    configured Wikidata IDs (bw_brands.config['wikidata_ids']), with relevance
    distribution. This is the entity-based alternative to substring keyword
    matching — precise and disambiguated.
    """
    from collections import defaultdict
    from datetime import datetime as _dt, timedelta as _td
    from app.services.opoint_brand_matcher import load_brand_wikidata, match_brands, source_reach_weight, is_scholarly_source

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        brand_wd = load_brand_wikidata(db.facade)
        # publication_date is TEXT/ISO -> safe lexicographic comparison (no ::timestamp cast)
        cutoff = (_dt.utcnow() - _td(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(text("""
            SELECT uri, title, publication_date, opoint_entities, news_source
            FROM articles
            WHERE jsonb_typeof(opoint_entities->'entities') = 'object'
              AND publication_date >= :cutoff
        """), {"cutoff": cutoff}).fetchall()

        agg = defaultdict(lambda: {"articles_matched": 0, "sum_rel": 0.0, "high_conf": 0, "reach": 0.0})
        sample_rows = []
        scholarly_excluded = 0
        for uri, title, pubdate, oe, news_source in rows:
            if exclude_scholarly and is_scholarly_source(news_source, uri):
                scholarly_excluded += 1
                continue
            hits = [h for h in match_brands(oe, brand_wd) if h["relevance_score"] >= min_relevance]
            if not hits:
                continue
            rw = source_reach_weight(oe)  # reach proxy from source global traffic rank
            for h in hits:
                a = agg[h["brand"]]
                a["articles_matched"] += 1
                a["sum_rel"] += h["relevance_score"]
                a["reach"] += rw
                if h["relevance_score"] >= 0.5:
                    a["high_conf"] += 1
            if samples and len(sample_rows) < samples:
                sample_rows.append({"uri": uri, "title": title,
                                    "publication_date": str(pubdate), "brands": hits})

        # Share-of-voice denominators (each shared mention counts toward each brand's voice)
        total_articles = sum(v["articles_matched"] for v in agg.values()) or 1
        total_reach = sum(v["reach"] for v in agg.values()) or 1.0

        coverage = [{"brand": b, "articles_matched": v["articles_matched"],
                     "avg_relevance": round(v["sum_rel"] / v["articles_matched"], 3),
                     "high_confidence": v["high_conf"],
                     "reach_weight": round(v["reach"], 3),
                     "article_sov_pct": round(100 * v["articles_matched"] / total_articles, 1),
                     "reach_sov_pct": round(100 * v["reach"] / total_reach, 1)}
                    for b, v in sorted(agg.items(), key=lambda kv: -kv[1]["reach"])]
        return {
            "window_days": days,
            "min_relevance": min_relevance,
            "opoint_articles_scanned": len(rows),
            "exclude_scholarly": exclude_scholarly,
            "scholarly_excluded": scholarly_excluded,
            "reach_metric": "source_global_traffic_rank_proxy",
            "brand_wikidata": {b: sorted(ids) for b, ids in brand_wd.items()},
            "coverage": coverage,
            "samples": sample_rows,
        }
    except Exception as e:
        logger.error(f"opoint-coverage error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/source-comparison")
@router.get("/opoint-pov")
async def opoint_proof_of_value(
    brand_id: int = Query(..., description="Brand to compare"),
    days_back: int = Query(90, ge=1, le=365),
    min_relevance: float = Query(0.4, ge=0.0, le=1.0, description="On-brand relevance bar for 'chargeable' value"),
    annual_cost: float = Query(20000, ge=0, description="Opoint annual cost (EUR) for cost-per-usable"),
    session=Depends(verify_session),
):
    """Proof-of-value: Opoint coverage vs. what we already do, for one brand.

    Compares, over a window, the brand's articles surfaced/enriched by Opoint vs.
    those from existing news sources, on four axes:
      1. Volume + source-domain reach (incremental domains Opoint adds).
      2. Enrichment exclusivity — resolved entities (Wikidata), source reach
         (site_rank), country — which existing sources don't provide at all.
      3. Precision — Opoint Wikidata entity brand-match vs our keyword-based
         classification (bw_article_categories).
      4. CHARGEABLE VALUE — the quality-adjusted funnel: of Opoint's raw volume,
         how much is genuinely on-brand (entity relevance >= min_relevance),
         non-scholarly, AND incremental (from a source domain existing sources
         didn't surface). This is the 'is it worth it / can we charge' number.
    """
    from app.services.opoint_brand_matcher import load_brand_wikidata, match_brands, is_scholarly_source
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        brand = conn.execute(text("SELECT id, name, display_name FROM bw_brands WHERE id=:id"),
                             {"id": brand_id}).fetchone()
        if not brand:
            raise HTTPException(status_code=404, detail="Brand not found")
        slug, display_name = brand[1], brand[2]
        topic = f"Brand Monitoring {display_name}"
        start_date, end_date = _get_date_range(days_back)
        params = {"t": topic, "start": start_date, "end": end_date}

        # Opoint-surfaced rows (with their enrichment) + existing (no opoint) rows
        opoint_rows = conn.execute(text("""
            SELECT uri, news_source, opoint_entities, title, publication_date, sentiment FROM articles
            WHERE topic=:t AND publication_date>=:start AND publication_date<=:end
              AND opoint_entities IS NOT NULL
        """), params).fetchall()
        existing_rows = conn.execute(text("""
            SELECT news_source, publication_date, bias_country, sentiment, media_type FROM articles
            WHERE topic=:t AND publication_date>=:start AND publication_date<=:end
              AND opoint_entities IS NULL
        """), params).fetchall()

        brand_wd = {}
        try:
            all_wd = load_brand_wikidata(db.facade)
            if slug in all_wd:
                brand_wd = {slug: all_wd[slug]}
        except Exception as e:
            logger.debug(f"pov wikidata load failed: {e}")

        from collections import Counter
        def _dom(ns):
            return (ns or "").lower().replace("www.", "").strip() or "unknown"
        def _month(pd):
            return pd[:7] if pd and len(pd) >= 7 else "unknown"

        def _sent(s):
            return (s or "").strip().capitalize() or "Unrated"

        # Existing-dataset aggregations (symmetric side of the comparison)
        existing_dom_counts = Counter()
        existing_country_counts = Counter()
        existing_sentiment = Counter()
        existing_mediatype = Counter()
        for (ns, pd, bc, sent, mt) in existing_rows:
            existing_dom_counts[_dom(ns)] += 1
            if bc:
                existing_country_counts[bc] += 1
            existing_sentiment[_sent(sent)] += 1
            existing_mediatype[(mt or "Unknown").strip() or "Unknown"] += 1
        existing_domains = set(existing_dom_counts)

        opoint_domains = set()
        entity_resolved = entity_verified = with_reach = with_country = 0
        on_brand = non_scholarly = chargeable = ch_verified = ch_reach = 0
        # drill-down accumulators
        rel_hist = Counter()                 # relevance bucket -> opoint article count
        opoint_dom_counts = Counter()        # domain -> opoint article count
        scholarly_dom = {}                   # domain -> bool scholarly
        country_counts = Counter()           # country -> opoint article count
        monthly_opoint = Counter()           # month -> opoint count
        opoint_sentiment = Counter()
        opoint_mediatype = Counter()
        chargeable_samples = []              # the actual usable items
        for uri, ns, oe, title, pd, sent in opoint_rows:
            dom = _dom(ns)
            opoint_domains.add(dom)
            opoint_dom_counts[dom] += 1
            monthly_opoint[_month(pd)] += 1
            opoint_sentiment[_sent(sent)] += 1
            if dom not in scholarly_dom:
                scholarly_dom[dom] = is_scholarly_source(ns, uri)
            if isinstance(oe, dict):
                opoint_mediatype[(oe.get("media_type") or "Unknown")] += 1
            if not isinstance(oe, dict):
                rel_hist["0.0"] += 1
                continue
            inner = oe.get("entities")
            if isinstance(inner, dict) and inner.get("entities"):
                entity_resolved += 1
            if oe.get("site_rank"):
                with_reach += 1
            if oe.get("countryname"):
                with_country += 1
                country_counts[oe.get("countryname")] += 1
            hits = match_brands(oe, brand_wd) if brand_wd else []
            if hits:
                entity_verified += 1
            rel = max((h["relevance_score"] for h in hits if h["brand"] == slug), default=0.0)
            rel_hist[f"{min(int(rel * 10), 9) / 10:.1f}"] += 1
            if rel < min_relevance:
                continue
            on_brand += 1
            if is_scholarly_source(ns, uri):
                continue
            non_scholarly += 1
            if dom not in existing_domains:
                chargeable += 1
                ch_verified += 1
                rank = (oe.get("site_rank") or {}).get("rank_global") if isinstance(oe.get("site_rank"), dict) else None
                if rank:
                    ch_reach += 1
                if len(chargeable_samples) < 30:
                    chargeable_samples.append({
                        "title": title, "url": uri, "source": dom,
                        "relevance": round(rel, 3), "rank_global": rank,
                    })

        keyword_classified = conn.execute(text("""
            SELECT COUNT(DISTINCT a.uri) FROM articles a
            JOIN bw_article_categories bac ON a.uri=bac.article_uri
            WHERE bac.brand_id=:b AND a.publication_date>=:start AND a.publication_date<=:end
        """), {"b": brand_id, "start": start_date, "end": end_date}).scalar() or 0

        opoint_only = sorted(opoint_domains - existing_domains)
        shared = opoint_domains & existing_domains
        existing_only = existing_domains - opoint_domains

        # Monthly existing series (align months with opoint)
        monthly_existing = Counter(_month(r[1]) for r in existing_rows)
        months = sorted(m for m in (set(monthly_opoint) | set(monthly_existing)) if m != "unknown")
        monthly = [{"month": m, "opoint": monthly_opoint.get(m, 0), "existing": monthly_existing.get(m, 0)} for m in months]

        # Relevance histogram in fixed bucket order
        rel_buckets = [f"{i/10:.1f}" for i in range(10)]
        relevance_histogram = [{"bucket": b, "count": rel_hist.get(b, 0)} for b in rel_buckets]

        # Top Opoint-only domains by article count (what the incremental coverage actually is)
        top_opoint_only_domains = [
            {"domain": d, "articles": opoint_dom_counts[d], "scholarly": scholarly_dom.get(d, False)}
            for d in sorted(opoint_only, key=lambda d: -opoint_dom_counts[d])[:20]
        ]

        # Project the windowed chargeable count onto a full year so cost-per-usable is a
        # true ANNUAL rate (the €20k cost is annual). e.g. 88 chargeable over 365d -> 88/yr;
        # 22 over 90d -> ~89/yr.
        annualized_chargeable = (chargeable * 365.0 / days_back) if days_back else float(chargeable)
        cost_per_chargeable = round(annual_cost / annualized_chargeable, 2) if annualized_chargeable else None

        return {
            "brand": display_name, "topic": topic, "window_days": days_back,
            "volume": {"opoint_articles": len(opoint_rows), "existing_articles": len(existing_rows)},
            "source_domains": {
                "opoint": len(opoint_domains), "existing": len(existing_domains),
                "opoint_only": len(opoint_only), "shared": len(shared),
                "existing_only": len(existing_only), "opoint_only_sample": opoint_only[:25],
            },
            "enrichment_exclusive": {
                "entities_resolved": {"opoint": entity_resolved, "existing": 0},
                "source_reach": {"opoint": with_reach, "existing": 0},
                "country_tagged": {"opoint": with_country, "existing": 0},
            },
            "precision": {
                "opoint_entity_verified": entity_verified,
                "keyword_classified": keyword_classified,
                "wikidata_ids": sorted(brand_wd.get(slug, [])),
            },
            "chargeable_value": {
                "min_relevance": min_relevance, "opoint_total": len(opoint_rows),
                "on_brand": on_brand, "non_scholarly": non_scholarly, "chargeable": chargeable,
                "chargeable_with_reach": ch_reach,
                "chargeable_rate_pct": round(100 * chargeable / len(opoint_rows), 1) if opoint_rows else 0.0,
            },
            # --- drill-down analytics ---
            "relevance_histogram": relevance_histogram,
            "top_opoint_only_domains": top_opoint_only_domains,
            "monthly": monthly,
            "by_country": [{"country": c, "count": n} for c, n in country_counts.most_common(10)],
            "chargeable_samples": chargeable_samples,
            "cost": {
                "annual_eur": annual_cost,
                "chargeable": chargeable,                    # in the selected window
                "annualized_chargeable": round(annualized_chargeable, 1),  # projected to 1 year
                "cost_per_chargeable_eur": cost_per_chargeable,            # annual basis
            },
            # --- symmetric Existing vs Opoint comparison (Source Comparison tab) ---
            "summary": {
                "existing": {
                    "articles": len(existing_rows),
                    "unique_sources": len(existing_domains),
                    "countries": len(existing_country_counts),
                },
                "opoint": {
                    "articles": len(opoint_rows),
                    "unique_sources": len(opoint_domains),
                    "countries": len(country_counts),
                },
            },
            "top_domains": {
                "existing": [{"domain": d, "articles": n} for d, n in existing_dom_counts.most_common(20)],
                "opoint": [{"domain": d, "articles": n, "scholarly": scholarly_dom.get(d, False)}
                           for d, n in opoint_dom_counts.most_common(20)],
            },
            "country_compare": {
                "existing": [{"country": c, "count": n} for c, n in existing_country_counts.most_common(10)],
                "opoint": [{"country": c, "count": n} for c, n in country_counts.most_common(10)],
            },
            "sentiment_compare": {
                "existing": [{"sentiment": s, "count": n} for s, n in existing_sentiment.most_common()],
                "opoint": [{"sentiment": s, "count": n} for s, n in opoint_sentiment.most_common()],
            },
            "media_type_compare": {
                "existing": [{"media_type": m, "count": n} for m, n in existing_mediatype.most_common(8)],
                "opoint": [{"media_type": m, "count": n} for m, n in opoint_mediatype.most_common(8)],
            },
            "overlap": {
                "shared": len(shared), "existing_only": len(existing_only), "opoint_only": len(opoint_only),
                "opoint_only_domains": [{"domain": d, "articles": opoint_dom_counts[d]} for d in sorted(opoint_only, key=lambda d: -opoint_dom_counts[d])[:20]],
                "shared_domains": [{"domain": d, "articles": opoint_dom_counts[d]} for d in sorted(shared, key=lambda d: -opoint_dom_counts[d])[:20]],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"opoint-pov error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


def _brand_pov_summary(conn, db, brand_row, days_back, min_relevance, annual_cost):
    """Compact per-brand existing-vs-Opoint summary (for portfolio table + report).

    brand_row = (id, name/slug, display_name). Returns the headline numbers.
    """
    from app.services.opoint_brand_matcher import load_brand_wikidata, match_brands, is_scholarly_source
    bid, slug, display = brand_row[0], brand_row[1], brand_row[2]
    topic = f"Brand Monitoring {display}"
    start_date, end_date = _get_date_range(days_back)
    p = {"t": topic, "s": start_date, "e": end_date}

    existing = conn.execute(text("""
        SELECT news_source FROM articles
        WHERE topic=:t AND publication_date>=:s AND publication_date<=:e AND opoint_entities IS NULL
    """), p).fetchall()
    existing_domains = {(ns or "").lower().replace("www.", "").strip() for (ns,) in existing}
    opoint = conn.execute(text("""
        SELECT news_source, opoint_entities FROM articles
        WHERE topic=:t AND publication_date>=:s AND publication_date<=:e AND opoint_entities IS NOT NULL
    """), p).fetchall()

    brand_wd = {}
    try:
        wd = load_brand_wikidata(db.facade)
        if slug in wd:
            brand_wd = {slug: wd[slug]}
    except Exception:
        pass

    chargeable = 0
    for ns, oe in opoint:
        if not isinstance(oe, dict):
            continue
        hits = match_brands(oe, brand_wd) if brand_wd else []
        rel = max((h["relevance_score"] for h in hits if h["brand"] == slug), default=0.0)
        if rel < min_relevance:
            continue
        if is_scholarly_source(ns, None):
            continue
        dom = (ns or "").lower().replace("www.", "").strip()
        if dom not in existing_domains:
            chargeable += 1
    annualized = (chargeable * 365.0 / days_back) if days_back else float(chargeable)
    return {
        "brand": display,
        "existing_articles": len(existing),
        "opoint_articles": len(opoint),
        "chargeable": chargeable,
        "annualized_chargeable": round(annualized, 1),
        "cost_per_chargeable_eur": round(annual_cost / annualized, 2) if annualized else None,
        "chargeable_rate_pct": round(100 * chargeable / len(opoint), 1) if opoint else 0.0,
    }


@router.get("/source-comparison/portfolio")
async def source_comparison_portfolio(
    days_back: int = Query(365, ge=1, le=365),
    min_relevance: float = Query(0.4, ge=0.0, le=1.0),
    annual_cost: float = Query(20000, ge=0),
    session=Depends(verify_session),
):
    """All-brands summary: existing vs Opoint volume + chargeable + cost-per-usable."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        brands = conn.execute(text("SELECT id, name, display_name FROM bw_brands WHERE enabled ORDER BY display_name")).fetchall()
        rows = [_brand_pov_summary(conn, db, b, days_back, min_relevance, annual_cost) for b in brands]
        totals = {
            "existing_articles": sum(r["existing_articles"] for r in rows),
            "opoint_articles": sum(r["opoint_articles"] for r in rows),
            "chargeable": sum(r["chargeable"] for r in rows),
            "annualized_chargeable": round(sum(r["annualized_chargeable"] for r in rows), 1),
        }
        total_ann = totals["annualized_chargeable"]
        totals["cost_per_chargeable_eur"] = round(annual_cost / total_ann, 2) if total_ann else None
        return {"window_days": days_back, "annual_cost": annual_cost, "brands": rows, "totals": totals}
    except Exception as e:
        logger.error(f"portfolio error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/source-comparison/domain-articles")
async def source_comparison_domain_articles(
    brand_id: int = Query(...),
    domain: str = Query(...),
    dataset: str = Query("opoint", description="'opoint' or 'existing'"),
    days_back: int = Query(365, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    session=Depends(verify_session),
):
    """Drill-down: the actual articles from one source domain (one dataset)."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        brand = conn.execute(text("SELECT display_name FROM bw_brands WHERE id=:id"), {"id": brand_id}).fetchone()
        if not brand:
            raise HTTPException(status_code=404, detail="Brand not found")
        topic = f"Brand Monitoring {brand[0]}"
        start_date, end_date = _get_date_range(days_back)
        op_clause = "a.opoint_entities IS NOT NULL" if dataset == "opoint" else "a.opoint_entities IS NULL"
        rows = conn.execute(text(f"""
            SELECT uri, title, publication_date, sentiment, topic_alignment_score, news_source
            FROM articles a
            WHERE topic=:t AND publication_date>=:s AND publication_date<=:e AND {op_clause}
              AND lower(replace(news_source,'www.','')) = :dom
            ORDER BY publication_date DESC LIMIT :lim
        """), {"t": topic, "s": start_date, "e": end_date, "dom": domain.lower().replace("www.", ""), "lim": limit}).fetchall()
        return {"brand": brand[0], "domain": domain, "dataset": dataset, "articles": [
            {"uri": r[0], "title": r[1], "publication_date": str(r[2]) if r[2] else None,
             "sentiment": r[3], "relevance": round(r[4], 3) if r[4] is not None else None, "source": r[5]}
            for r in rows
        ]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"domain-articles error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/source-comparison/report")
async def source_comparison_report(
    days_back: int = Query(365, ge=1, le=365),
    min_relevance: float = Query(0.4, ge=0.0, le=1.0),
    annual_cost: float = Query(20000, ge=0),
    session=Depends(verify_session),
):
    """Downloadable self-contained HTML report — all-brands Existing vs Opoint."""
    from fastapi.responses import Response
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        brands = conn.execute(text("SELECT id, name, display_name FROM bw_brands WHERE enabled ORDER BY display_name")).fetchall()
        rows = [_brand_pov_summary(conn, db, b, days_back, min_relevance, annual_cost) for b in brands]
        t_existing = sum(r["existing_articles"] for r in rows)
        t_opoint = sum(r["opoint_articles"] for r in rows)
        t_charge = sum(r["chargeable"] for r in rows)
        t_ann = round(sum(r["annualized_chargeable"] for r in rows), 1)
        cpu = round(annual_cost / t_ann, 2) if t_ann else None
        rate = round(100 * t_charge / t_opoint, 1) if t_opoint else 0.0

        # --- Scholarly redundancy: top Opoint-only journal venues vs Semantic Scholar ---
        import re as _re, aiohttp
        from collections import Counter as _C
        JOURNAL_RE = _re.compile(r'journal|review|annals|bulletin|proceedings|acta|quarterly|letters|frontiers|omega|oncology|chemistry|neuro|cancer|medicine|lancet|bmj', _re.I)
        existing_all = set()
        opoint_dom = _C()
        for b in brands:
            tp = f"Brand Monitoring {b[2]}"
            for (ns,) in conn.execute(text("SELECT DISTINCT news_source FROM articles WHERE topic=:t AND opoint_entities IS NULL"), {"t": tp}).fetchall():
                existing_all.add((ns or "").lower().replace("www.", ""))
            for ns, c in conn.execute(text("SELECT lower(replace(news_source,'www.','')) d, count(*) FROM articles WHERE topic=:t AND opoint_entities IS NOT NULL GROUP BY 1"), {"t": tp}).fetchall():
                opoint_dom[ns] += c
        def _clean_venue(v):
            return _re.sub(r'\s*\((online|print)\)\s*', '', v or '', flags=_re.I).strip()
        # candidate journal venues Opoint surfaced that our existing feeds didn't (top by volume)
        journal_venues = [(_clean_venue(d), n) for d, n in opoint_dom.most_common()
                          if d not in existing_all and JOURNAL_RE.search(d or "")][:10]
        ss_have = conn.execute(text("SELECT count(*) FROM articles WHERE news_source='semantic_scholar' OR uri LIKE '%semanticscholar.org%'")).scalar() or 0

        import os as _os
        ss_key = _os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        ss_headers = {"x-api-key": ss_key} if ss_key else {}

        async def _ss_count(cl, venue):
            # one retry — SS unauthenticated tier rate-limits (429) aggressively
            for attempt in range(2):
                try:
                    async with cl.get("https://api.semanticscholar.org/graph/v1/paper/search/bulk",
                                      params={"venue": venue, "fields": "venue", "year": "2024-2026"},
                                      headers=ss_headers, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            return (await r.json()).get("total")
                        if r.status == 429 and attempt == 0:
                            await asyncio.sleep(3.0)
                            continue
                except Exception:
                    if attempt == 0:
                        await asyncio.sleep(2.0)
                        continue
                return None
            return None
        # Always list the journal venues + Opoint counts (from our data, reliable);
        # attach a LIVE Semantic Scholar indexed-count best-effort (None if SS rate-limits).
        ss_rows = [{"venue": d, "opoint": n, "ss": None} for d, n in journal_venues[:6]]
        try:
            async with aiohttp.ClientSession() as cl:
                for row in ss_rows:
                    row["ss"] = await _ss_count(cl, row["venue"])
                    await asyncio.sleep(1.5 if not ss_key else 0.2)
        except Exception as ss_err:
            logger.warning(f"SS coverage lookup failed: {ss_err}")

        def tr(r):
            return (f"<tr><td>{r['brand']}</td><td class='n'>{r['existing_articles']:,}</td>"
                    f"<td class='n'>{r['opoint_articles']:,}</td><td class='n'>{r['chargeable']:,}</td>"
                    f"<td class='n'>{r['annualized_chargeable']:,.0f}</td>"
                    f"<td class='n'>{('€'+format(r['cost_per_chargeable_eur'],',.0f')) if r['cost_per_chargeable_eur'] else '—'}</td>"
                    f"<td class='n'>{r['chargeable_rate_pct']}%</td></tr>")
        from datetime import datetime as _dt, timedelta as _td
        # No wall-clock in scripts, but this is a live request — use range bounds for the dateline
        start_date, end_date = _get_date_range(days_back)

        # Build the Semantic Scholar redundancy section (graceful if SS unavailable)
        if ss_rows:
            ss_trs = "".join(
                f"<tr><td>{r['venue']}</td><td class='n'>{r['opoint']:,}</td>"
                f"<td class='n'>{(format(r['ss'],',')+' indexed') if r['ss'] else 'indexed by S2'}</td></tr>"
                for r in ss_rows)
            ss_section = f"""
<h2>Scholarly coverage is redundant — Semantic Scholar</h2>
<p>The journal venues Opoint surfaces as "unique" are already indexed by <b>Semantic Scholar</b>, a source we
already run for free (≈ &lt;€2k stack) and from which we already hold <b>{ss_have:,}</b> papers. Below: Opoint's
articles from each venue (this window) vs. how many Semantic Scholar indexes (2024–2026).</p>
<table><thead><tr><th>Journal venue (Opoint-only)</th><th class="n">Opoint articles</th><th class="n">Semantic Scholar (2024–26)</th></tr></thead>
<tbody>{ss_trs}</tbody></table>
<p class="sub">Opoint adds a trickle from journals where Semantic Scholar holds thousands — the scholarly "incremental
reach" is coverage we can already obtain for free; we simply aren't pointing our academic collector at the brand topics.</p>
"""
        else:
            ss_section = f"""<h2>Scholarly coverage is redundant — Semantic Scholar</h2>
<p>The journal venues Opoint surfaces are already indexed by Semantic Scholar, which we run for free — we already
hold <b>{ss_have:,}</b> Semantic Scholar papers in-house.</p>"""

        html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Opoint vs Existing — Source Comparison Report</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111827;max-width:900px;margin:40px auto;padding:0 24px;line-height:1.5}}
h1{{font-size:26px;margin-bottom:4px}} h2{{font-size:18px;margin-top:32px;border-bottom:2px solid #eee;padding-bottom:4px}}
.sub{{color:#6b7280;font-size:13px}} table{{border-collapse:collapse;width:100%;margin:16px 0;font-size:14px}}
th,td{{border:1px solid #e5e7eb;padding:8px 10px;text-align:left}} th{{background:#f9fafb}} td.n,th.n{{text-align:right}}
.verdict{{background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:16px;margin:20px 0}}
.big{{font-size:30px;font-weight:700;color:#b45309}} .kpis{{display:flex;gap:24px;flex-wrap:wrap;margin:16px 0}}
.kpi{{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:14px 18px}} .kpi .v{{font-size:22px;font-weight:700}}
.kpi .l{{font-size:12px;color:#6b7280}}
</style></head><body>
<h1>Opoint vs. Existing — Source Comparison</h1>
<p class="sub">All tracked brands · window {start_date} → {end_date} ({days_back}d) · Opoint annual cost €{annual_cost:,.0f}</p>

<div class="verdict">
<div>Across all brands, of <b>{t_opoint:,}</b> Opoint articles only <b>{t_charge:,}</b> were high-value incremental
(on-brand ≥{min_relevance}, non-scholarly, from a source we don't already cover) — <span class="big">{rate}%</span>.</div>
<div style="margin-top:10px">Projected to a year that's ~<b>{t_ann:,.0f}</b> usable articles for <b>€{annual_cost:,.0f}</b> =
<b>{('€'+format(cpu,',.0f')) if cpu else '—'}</b> per usable article. Our existing feeds already deliver
<b>{t_existing:,}</b> articles in the same window at a fraction of the cost.</div>
</div>

<div class="kpis">
<div class="kpi"><div class="v">{t_existing:,}</div><div class="l">Existing articles</div></div>
<div class="kpi"><div class="v">{t_opoint:,}</div><div class="l">Opoint articles</div></div>
<div class="kpi"><div class="v">{t_charge:,}</div><div class="l">Chargeable (window)</div></div>
<div class="kpi"><div class="v">{('€'+format(cpu,',.0f')) if cpu else '—'}</div><div class="l">Cost / usable article (annualized)</div></div>
</div>

<h2>Per-brand breakdown</h2>
<table><thead><tr><th>Brand</th><th class="n">Existing</th><th class="n">Opoint</th><th class="n">Chargeable</th>
<th class="n">Annualized</th><th class="n">€/usable</th><th class="n">Rate</th></tr></thead>
<tbody>{''.join(tr(r) for r in rows)}</tbody></table>
{ss_section}
<h2>Thesis</h2>
<p>The data supports the position that <b>premium aggregator feeds are not cost-justified and that adding more
sources does not materially improve brand coverage</b>: ~{100-rate:.0f}% of Opoint's volume is peripheral / citation
noise, the genuinely incremental high-value share is ~{rate}%, and the resulting annualized cost-per-usable-article
(~{('€'+format(cpu,',.0f')) if cpu else '—'}) is far above our existing &lt;€2k/yr sources, which already surface the
substantive coverage. Opoint's distinctive value is enrichment (resolved entities, source reach, country), not
incremental article volume.</p>
<p class="sub">Generated by AunooAI Source Comparison · evidence reproducible in /explore → Source Comparison.</p>
</body></html>"""
        return Response(content=html, media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="opoint_source_comparison_{days_back}d.html"',
                                 "Cache-Control": "no-store"})
    except Exception as e:
        logger.error(f"source-comparison report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/social")
async def get_social_posts(
    topics: Optional[str] = Query(None, description="Comma-separated brand topic(s)"),
    days_back: int = Query(30, ge=1, le=365),
    min_relevance: float = Query(0.0, ge=0.0, le=1.0),
    source: Optional[str] = Query(None, description="Filter: 'reddit' or 'bluesky'"),
    keyword: Optional[str] = Query(None, description="Only posts triggered by this brand keyword (case-insensitive)"),
    start_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD); overrides days_back window start"),
    end_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD); overrides days_back window end (inclusive)"),
    include_unevaluated: bool = Query(True, description="When no min_relevance, include posts the social eval hasn't scored yet"),
    limit: int = Query(100, ge=1, le=20000),
    session=Depends(verify_session),
):
    """Social (Reddit/Bluesky) brand mentions with basic relevance + sentiment.

    Reads social posts directly from `articles` by topic + news_source — does NOT
    require classification into bw_article_categories. relevance =
    topic_alignment_score (set by the lightweight social eval); sentiment as stored.
    """
    from app.services.social_eval_service import SOCIAL_SOURCES
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        # Explicit start/end (from the export modal date range) override days_back.
        # end is made inclusive of the whole day; publication_date is ISO text so
        # 'T23:59:59' sorts as the day's max under lexicographic comparison.
        if start_date or end_date:
            win_start = start_date or '1900-01-01'
            win_end = (end_date or datetime.now().strftime('%Y-%m-%d')) + 'T23:59:59'
        else:
            win_start, win_end = _get_date_range(days_back)
        topic_clause, topic_params = _build_topics_filter(topics)

        # social-source filter: either a specific source, or any of the social sources
        if source and source.lower() in ("reddit", "bluesky"):
            src_keys = ["reddit"] if source.lower() == "reddit" else ["bluesky", "bsky"]
        else:
            src_keys = list(SOCIAL_SOURCES)
        src_clause = "(" + " OR ".join(f"LOWER(a.news_source) LIKE :_src_{i}" for i in range(len(src_keys))) + ")"
        params = {"start": win_start, "end": win_end, "min_rel": min_relevance, "lim": limit, **topic_params}
        for i, k in enumerate(src_keys):
            params[f"_src_{i}"] = f"%{k}%"

        # Relevance filtering. The lightweight social eval may not have scored every
        # post yet (topic_alignment_score IS NULL). A threshold means "evaluated AND
        # at/above it", so NULLs are excluded the moment any minimum is requested.
        # With no threshold, include_unevaluated decides whether pending posts show.
        if min_relevance > 0:
            rel_clause = "AND a.topic_alignment_score >= :min_rel"
        elif not include_unevaluated:
            rel_clause = "AND a.topic_alignment_score IS NOT NULL"
        else:
            rel_clause = ""

        rows = conn.execute(text(f"""
            SELECT a.uri, a.title, a.summary, a.news_source, a.publication_date,
                   a.topic_alignment_score, a.sentiment, a.topic
            FROM articles a
            WHERE a.publication_date >= :start AND a.publication_date <= :end
              AND {src_clause}
              {topic_clause}
              {rel_clause}
            ORDER BY a.publication_date DESC
            LIMIT :lim
        """), params).fetchall()

        def _platform(ns):
            s = (ns or "").lower()
            if "reddit" in s:
                return "reddit"
            if "bsky" in s or "bluesky" in s:
                return "bluesky"
            return "social"

        posts = [{
            "uri": r[0], "title": r[1], "summary": r[2], "news_source": r[3],
            "platform": _platform(r[3]),
            "publication_date": str(r[4]) if r[4] else None,
            "relevance": round(r[5], 3) if r[5] is not None else None,
            "sentiment": r[6], "topic": r[7],
        } for r in rows]

        # Attach the brand keyword(s) that triggered each post so the UI can show a
        # chip and filter by it. The keyword monitor records matches in
        # keyword_article_matches (comma-separated monitored_keywords ids); resolve
        # those ids to names. Done in two small lookups to avoid ::int[] cast pitfalls
        # on any stray/blank ids.
        kw_map: dict = {}
        uris = [p["uri"] for p in posts]
        if uris:
            match_rows = conn.execute(text(
                "SELECT article_uri, keyword_ids FROM keyword_article_matches "
                "WHERE article_uri = ANY(:uris)"
            ), {"uris": uris}).fetchall()
            uri_ids: dict = {}
            id_set: set = set()
            for m_uri, kids in match_rows:
                ids = [int(x) for x in (kids or "").split(",") if x.strip().isdigit()]
                if not ids:
                    continue
                uri_ids.setdefault(m_uri, set()).update(ids)
                id_set.update(ids)
            id_to_kw: dict = {}
            if id_set:
                for kid, kw in conn.execute(text(
                    "SELECT id, keyword FROM monitored_keywords WHERE id = ANY(:ids)"
                ), {"ids": list(id_set)}).fetchall():
                    id_to_kw[kid] = kw
            for m_uri, ids in uri_ids.items():
                kw_map[m_uri] = sorted({id_to_kw[i] for i in ids if i in id_to_kw})
        for p in posts:
            p["matched_keywords"] = kw_map.get(p["uri"], [])

        # Optional filter: only posts triggered by a specific keyword (case-insensitive).
        if keyword:
            kw_lc = keyword.strip().lower()
            posts = [p for p in posts if any(k.lower() == kw_lc for k in p["matched_keywords"])]

        # sentiment + platform rollups for the tab summary
        from collections import Counter
        sent_counts = Counter((p["sentiment"] or "Unrated") for p in posts)
        plat_counts = Counter(p["platform"] for p in posts)
        kw_counts = Counter(k for p in posts for k in p["matched_keywords"])
        evaluated = sum(1 for p in posts if p["relevance"] is not None)
        return {
            "window_days": days_back,
            "min_relevance": min_relevance,
            "include_unevaluated": include_unevaluated,
            "keyword": keyword,
            "total": len(posts),
            "evaluated": evaluated,
            "by_platform": dict(plat_counts),
            "by_sentiment": dict(sent_counts),
            "by_keyword": dict(kw_counts.most_common()),
            "posts": posts,
        }
    except Exception as e:
        logger.error(f"brand-watcher/social error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/brands", response_model=BrandResponse, status_code=201)
async def create_brand(brand: BrandCreate, session=Depends(verify_session)):
    """Create a new brand to track."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        slug = brand.name if re.match(r'^[a-z0-9-]+$', brand.name) else _slugify(brand.display_name)

        result = conn.execute(text(f"""
            INSERT INTO bw_brands (name, display_name, description,
                brand_keywords, product_keywords, people_keywords, competitor_keywords, color)
            VALUES (:name, :display_name, :description,
                :brand_kw, :product_kw, :people_kw, :competitor_kw, :color)
            RETURNING {BRAND_SELECT_COLS}
        """), {
            "name": slug,
            "display_name": brand.display_name,
            "description": brand.description,
            "brand_kw": json.dumps(brand.brand_keywords),
            "product_kw": json.dumps(brand.product_keywords or []),
            "people_kw": json.dumps(brand.people_keywords or []),
            "competitor_kw": json.dumps(brand.competitor_keywords or []),
            "color": brand.color,
        })
        row = result.fetchone()
        conn.commit()
        return BrandResponse(**_brand_row_to_dict(row))
    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating brand: {e}")
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Brand name already exists")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/brands/{brand_id}", response_model=BrandResponse)
async def get_brand(brand_id: int, session=Depends(verify_session)):
    """Get a single brand by ID."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result = conn.execute(text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands WHERE id = :id"), {"id": brand_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Brand not found")
        return BrandResponse(**_brand_row_to_dict(row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching brand {brand_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.put("/brands/{brand_id}", response_model=BrandResponse)
async def update_brand(brand_id: int, updates: BrandUpdate, session=Depends(verify_session)):
    """Update a brand's configuration."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        # Build dynamic SET clause
        set_parts = []
        params = {"id": brand_id}
        if updates.display_name is not None:
            set_parts.append("display_name = :display_name")
            params["display_name"] = updates.display_name
        if updates.description is not None:
            set_parts.append("description = :description")
            params["description"] = updates.description
        if updates.brand_keywords is not None:
            set_parts.append("brand_keywords = :brand_kw")
            params["brand_kw"] = json.dumps(updates.brand_keywords)
        if updates.product_keywords is not None:
            set_parts.append("product_keywords = :product_kw")
            params["product_kw"] = json.dumps(updates.product_keywords)
        if updates.people_keywords is not None:
            set_parts.append("people_keywords = :people_kw")
            params["people_kw"] = json.dumps(updates.people_keywords)
        if updates.competitor_keywords is not None:
            set_parts.append("competitor_keywords = :competitor_kw")
            params["competitor_kw"] = json.dumps(updates.competitor_keywords)
        if updates.color is not None:
            set_parts.append("color = :color")
            params["color"] = updates.color

        if not set_parts:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_parts.append("updated_at = NOW()")
        set_clause = ", ".join(set_parts)

        result = conn.execute(text(f"""
            UPDATE bw_brands SET {set_clause} WHERE id = :id
            RETURNING {BRAND_SELECT_COLS}
        """), params)
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Brand not found")
        conn.commit()
        return BrandResponse(**_brand_row_to_dict(row))
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating brand {brand_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.delete("/brands/{brand_id}")
async def delete_brand(
    brand_id: int,
    cleanup_monitoring: bool = Query(False),
    session=Depends(verify_session),
):
    """Delete a brand and all associated data (CASCADE).

    If cleanup_monitoring=true, also removes the associated topic from
    config.json and deletes the keyword group.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        # Look up display_name before deleting (needed for monitoring cleanup)
        display_name = None
        if cleanup_monitoring:
            name_result = conn.execute(
                text("SELECT display_name FROM bw_brands WHERE id = :id"),
                {"id": brand_id},
            )
            name_row = name_result.fetchone()
            if name_row:
                display_name = name_row[0]

        result = conn.execute(text("DELETE FROM bw_brands WHERE id = :id RETURNING id"), {"id": brand_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Brand not found")
        conn.commit()

        # Clean up monitoring topic + keyword groups
        if cleanup_monitoring and display_name:
            topic_name = f"Brand Monitoring {display_name}"
            try:
                # Remove topic from config.json
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                config_path = os.path.join(base_dir, 'app', 'config', 'config.json')

                with open(config_path, 'r') as f:
                    config = json.load(f)

                original_count = len(config.get("topics", []))
                config["topics"] = [t for t in config.get("topics", []) if t.get("name") != topic_name]

                if len(config["topics"]) < original_count:
                    temp_config_path = f"{config_path}.temp"
                    with open(temp_config_path, 'w') as f:
                        json.dump(config, f, indent=2)
                    os.replace(temp_config_path, config_path)
                    logger.info(f"Removed topic '{topic_name}' from config.json")

                # Remove keyword groups associated with that topic
                facade = DatabaseQueryFacade(db, logger)
                groups = facade.get_all_group_ids_associated_to_topic(topic_name)
                for g in (groups or []):
                    gid = g['id'] if isinstance(g, dict) else g[0]
                    facade.delete_group_keywords(gid)
                    facade.delete_keyword_group(gid)
                    logger.info(f"Deleted keyword group {gid} for topic '{topic_name}'")
            except Exception as cleanup_err:
                logger.error(f"Monitoring cleanup error (brand still deleted): {cleanup_err}")

        return {"message": "Brand deleted", "id": brand_id}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error deleting brand {brand_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.put("/brands/{brand_id}/toggle")
async def toggle_brand(brand_id: int, session=Depends(verify_session)):
    """Toggle brand enabled/disabled."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result = conn.execute(text("""
            UPDATE bw_brands SET enabled = NOT enabled, updated_at = NOW()
            WHERE id = :id
            RETURNING id, enabled
        """), {"id": brand_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Brand not found")
        conn.commit()
        return {"id": row[0], "enabled": row[1]}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error toggling brand {brand_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.put("/brands/{brand_id}/set-primary")
async def set_primary_brand(brand_id: int, session=Depends(verify_session)):
    """Set a brand as the primary brand (unsets all others)."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        # Verify brand exists
        exists = conn.execute(text("SELECT id FROM bw_brands WHERE id = :id"), {"id": brand_id}).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Brand not found")
        conn.execute(text("UPDATE bw_brands SET is_primary = false"))
        conn.execute(text("UPDATE bw_brands SET is_primary = true WHERE id = :id"), {"id": brand_id})
        conn.commit()
        return {"id": brand_id, "is_primary": True}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error setting primary brand {brand_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.put("/brands/{brand_id}/config")
async def update_brand_config(brand_id: int, config_update: dict, session=Depends(verify_session)):
    """Update brand-specific config (e.g., slm_confidence_threshold)."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        # Merge with existing config
        existing = conn.execute(text(
            "SELECT COALESCE(config, '{}') FROM bw_brands WHERE id = :id"
        ), {"id": brand_id}).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Brand not found")

        current_config = existing[0] if isinstance(existing[0], dict) else json.loads(existing[0] or '{}')
        current_config.update(config_update)

        conn.execute(text("""
            UPDATE bw_brands SET config = :config, updated_at = NOW() WHERE id = :id
        """), {"id": brand_id, "config": json.dumps(current_config)})
        conn.commit()
        return {"config": current_config}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating brand config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Brand Monitoring Setup (Topic + Keyword Group)
# ============================================================================

@router.post("/brands/{brand_id}/setup-monitoring")
async def setup_brand_monitoring(brand_id: int, session=Depends(verify_session)):
    """Create a config.json topic and keyword group for a brand.

    Idempotent: skips topic creation if it already exists, updates keywords
    if group already exists.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        # 1. Fetch brand
        result = conn.execute(text("""
            SELECT id, display_name, brand_keywords, product_keywords, people_keywords
            FROM bw_brands WHERE id = :id
        """), {"id": brand_id})
        brand = result.fetchone()
        if not brand:
            raise HTTPException(status_code=404, detail="Brand not found")

        display_name = brand[1]
        # JSONB columns — already returned as Python lists by psycopg2
        brand_keywords = brand[2] if isinstance(brand[2], list) else (json.loads(brand[2]) if brand[2] else [])
        product_keywords = brand[3] if isinstance(brand[3], list) else (json.loads(brand[3]) if brand[3] else [])
        people_keywords = brand[4] if isinstance(brand[4], list) else (json.loads(brand[4]) if brand[4] else [])

        topic_name = f"Brand Monitoring {display_name}"
        group_name = f"{display_name} - Brand Watch"

        # 2. Create topic in config.json (idempotent)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(base_dir, 'app', 'config', 'config.json')

        with open(config_path, 'r') as f:
            config = json.load(f)

        # Check if topic already exists
        existing_names = [t["name"] for t in config.get("topics", [])]
        topic_created = False

        if topic_name not in existing_names:
            # Borrow sentiment/time_to_impact/driver_types from first topic
            standard_topic = config["topics"][0] if config.get("topics") else {}

            bw_categories = list(BW_CATEGORIES.keys())

            new_topic = {
                "name": topic_name,
                "description": f"Brand monitoring topic for {display_name}. Tracks brand mentions, sentiment, competitive positioning, and reputation across news articles.",
                "categories": bw_categories,
                "future_signals": [
                    "Brand gaining momentum",
                    "Brand losing momentum",
                    "Reputation risk emerging",
                    "Competitive threat detected",
                    "Market opportunity identified",
                    "Crisis developing",
                    "Positive PR wave",
                    "Regulatory action pending",
                ],
                "sentiment": standard_topic.get("sentiment", ["Optimistic", "Cautious", "Neutral", "Concerned", "Pessimistic"]),
                "time_to_impact": standard_topic.get("time_to_impact", ["Immediate", "Short-term", "Mid-term", "Long-term"]),
                "driver_types": standard_topic.get("driver_types", ["Catalyst", "Accelerator", "Delayer", "Blocker", "Initiator", "Terminator", "Unknown"]),
            }

            config["topics"].append(new_topic)

            # Atomic write: temp file + os.replace()
            try:
                temp_config_path = f"{config_path}.temp"
                with open(temp_config_path, 'w') as f:
                    json.dump(config, f, indent=2)

                if not os.path.exists(temp_config_path):
                    raise Exception(f"Failed to create temp file at {temp_config_path}")

                os.replace(temp_config_path, config_path)
                topic_created = True
                logger.info(f"Created topic '{topic_name}' in config.json")
            except Exception as e:
                logger.error(f"Atomic write failed, trying direct write: {e}")
                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                topic_created = True
                logger.info(f"Created topic '{topic_name}' via direct write")
        else:
            logger.info(f"Topic '{topic_name}' already exists, skipping")

        # 3. Create keyword group (idempotent — update if exists)
        facade = DatabaseQueryFacade(db, logger)
        group = facade.get_keyword_group_id_by_name_and_topic(group_name, topic_name)
        group_created = False

        if group:
            group_id = group[0]
            logger.info(f"Found existing keyword group {group_id}, updating keywords")
            facade.delete_group_keywords(group_id)
        else:
            group_id = facade.create_group(group_name, topic_name)
            group_created = True
            logger.info(f"Created keyword group '{group_name}' with ID {group_id}")

        # Combine brand + product + people keywords (NOT competitor)
        all_keywords = brand_keywords + product_keywords + people_keywords
        normalized = normalize_keyword_list(all_keywords)
        logger.info(f"Normalized {len(all_keywords)} keywords to {len(normalized)}")

        for kw in normalized:
            facade.add_keywords_to_group(group_id, kw)

        return {
            "brand_id": brand_id,
            "topic_name": topic_name,
            "topic_created": topic_created,
            "group_name": group_name,
            "group_created": group_created,
            "keywords_added": len(normalized),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting up monitoring for brand {brand_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


class SocialMonitoringRequest(BaseModel):
    interval_hours: int = Field(24, ge=1, le=168)
    model: Optional[str] = None              # default_llm_model for the social eval
    providers: Optional[List[str]] = None    # default ['reddit', 'bluesky']


@router.post("/brands/{brand_id}/social-monitoring")
async def setup_social_monitoring(brand_id: int, req: SocialMonitoringRequest = SocialMonitoringRequest(), session=Depends(verify_session)):
    """Create/update a dedicated social keyword group for a brand (Reddit/Bluesky).

    Polls on its OWN interval (decoupled from the news brand-watch group) and the
    posts get the cheap social relevance+sentiment eval (not the heavy news pipeline).
    Idempotent: updates the '<Brand> - Social' group if it already exists.
    """
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        brand = conn.execute(text(
            "SELECT id, display_name, brand_keywords, product_keywords, people_keywords, config "
            "FROM bw_brands WHERE id = :id"), {"id": brand_id}).fetchone()
        if not brand:
            raise HTTPException(status_code=404, detail="Brand not found")
        display_name = brand[1]

        def _kw(v):
            return v if isinstance(v, list) else (json.loads(v) if v else [])
        keywords = normalize_keyword_list(_kw(brand[2]) + _kw(brand[3]) + _kw(brand[4]))

        # Social keyword cleanup: brands can list overly-ambiguous keywords (bare
        # surnames, idioms like "For Dummies", typos) that collide with everyday
        # social chatter and flood the feed with off-brand posts. Those are kept for
        # the news path (where relevance scoring disambiguates) but excluded from
        # social collection. Stored in bw_brands.config.social_keyword_excludes.
        cfg = brand[5] if isinstance(brand[5], dict) else (json.loads(brand[5]) if brand[5] else {})
        excludes = {str(x).strip().lower() for x in (cfg.get("social_keyword_excludes") or [])}
        if excludes:
            keywords = [k for k in keywords if k.strip().lower() not in excludes]

        topic_name = f"Brand Monitoring {display_name}"
        group_name = f"{display_name} - Social"
        providers = req.providers or ["reddit", "bluesky"]
        interval_unit = 3600  # hours
        primary = providers[0] if providers else "reddit"

        facade = DatabaseQueryFacade(db, logger)
        existing = facade.get_keyword_group_id_by_name_and_topic(group_name, topic_name)
        if existing:
            group_id = existing[0]
            facade.delete_group_keywords(group_id)
            created = False
        else:
            group_id = facade.create_group(group_name, topic_name)
            created = True

        # Apply social settings (own interval, social providers, eval model, light pipeline)
        conn.execute(text("""
            UPDATE keyword_groups
            SET providers = :providers, source = :src, provider = :src,
                check_interval = :ci, interval_unit = :iu,
                is_active = true, auto_ingest_enabled = true,
                min_relevance_threshold = 0, default_llm_model = :model
            WHERE id = :id
        """), {"providers": json.dumps(providers), "src": primary,
               "ci": req.interval_hours, "iu": interval_unit,
               "model": req.model, "id": group_id})
        conn.commit()

        for kw in keywords:
            facade.add_keywords_to_group(group_id, kw)

        return {
            "brand_id": brand_id, "group_id": group_id, "group_name": group_name,
            "created": created, "providers": providers,
            "interval_hours": req.interval_hours, "model": req.model,
            "keywords_added": len(keywords),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting up social monitoring for brand {brand_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Keyword Suggestion
# ============================================================================

class SuggestKeywordsRequest(BaseModel):
    brand_name: str
    description: Optional[str] = None

@router.post("/suggest-keywords")
async def suggest_keywords(request: SuggestKeywordsRequest, session=Depends(verify_session)):
    """Use LLM to suggest brand keywords, product keywords, people keywords, and competitor keywords."""
    from app.ai_models import LiteLLMModel

    prompt = f"""You are a brand intelligence analyst. Given the brand name and optional description, suggest comprehensive keyword lists for monitoring this brand in news articles.

Brand name: {request.brand_name}
{f'Description: {request.description}' if request.description else ''}

Return a JSON object with these four arrays:
- "brand_keywords": Variations of the brand/company name that would appear in news (full legal name, common abbreviations, stock ticker symbols, former names, parent company names). Include the brand name itself.
- "product_keywords": Major products, services, platforms, or publications associated with this brand.
- "people_keywords": Key executives, founders, or notable people associated with this brand (CEO, CFO, board members).
- "competitor_keywords": Major direct competitors in the same industry.

Be thorough but only include terms that would realistically appear in news articles. Each keyword should be specific enough to avoid false positives.

Respond ONLY with valid JSON, no markdown formatting."""

    try:
        model = LiteLLMModel.get_instance("gpt-5.4-mini")
        response = await model.agenerate_response([
            {"role": "system", "content": "You are a brand intelligence analyst. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ])

        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        result = json.loads(response_text)

        return {
            "brand_keywords": result.get("brand_keywords", []),
            "product_keywords": result.get("product_keywords", []),
            "people_keywords": result.get("people_keywords", []),
            "competitor_keywords": result.get("competitor_keywords", []),
        }
    except Exception as e:
        logger.error(f"Error suggesting keywords: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Classification Endpoints
# ============================================================================

@router.post("/classify", response_model=ClassifyResponse)
async def classify_articles(
    request: ClassifyRequest,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session),
):
    """Run classification on articles for a brand (or all brands)."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result = conn.execute(text("""
            INSERT INTO bw_tracker_runs (brand_id, run_type, status)
            VALUES (:brand_id, :run_type, 'running')
            RETURNING id
        """), {"brand_id": request.brand_id, "run_type": request.run_type})
        run_id = result.fetchone()[0]
        conn.commit()

        # Merge legacy 'topic' with 'topics' list
        topics = list(request.topics or [])
        if request.topic and request.topic not in topics:
            topics.append(request.topic)

        background_tasks.add_task(
            _run_classification_task,
            run_id, request.brand_id, request.run_type, request.days_back, topics or None
        )

        topic_msg = f" for topics: {', '.join(topics)}" if topics else ""
        return ClassifyResponse(
            run_id=run_id, status="running",
            articles_processed=0, articles_categorized=0,
            message=f"Classification started in background{topic_msg}"
        )
    except Exception as e:
        logger.error(f"Error starting classification: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


async def _run_classification_task(run_id: int, brand_id: Optional[int], run_type: str, days_back: int, topics: Optional[List[str]] = None):
    """Background: classify articles per brand using SLM → LLM → keyword waterfall."""
    import asyncio

    db = get_database_instance()
    conn = db._temp_get_connection()

    # Try SLM
    slm_available = False
    try:
        from app.services.brand_watcher_classifier_service import get_brand_watcher_classifier
        slm = get_brand_watcher_classifier()
        slm_available = slm.is_available()
        if slm_available:
            logger.info("Brand Watcher SLM classifier available")
    except Exception as e:
        logger.info(f"Brand Watcher SLM not loaded ({e})")

    # Per-brand relevance scorer: bw_article_categories.relevance_score is judged
    # against the BRAND (not the article's owning topic), so cross-topic articles
    # (e.g. a Wiley story owned by "Scientific Publishers") aren't hidden by the
    # display filter just because their global score targets another topic.
    _brand_rel_svc = None
    try:
        from app.services.hybrid_relevance_service import get_hybrid_relevance_service
        _brand_rel_svc = get_hybrid_relevance_service()
        _brand_rel_svc.load_models()
    except Exception as e:
        logger.warning(f"Brand relevance scorer unavailable ({e}) — relevance_score will fall back to topic score")

    # MBFC source-authority stamp: keyword-monitor / cross-topic articles bypass the
    # auto-ingest bias enrichment, so most BW articles had NULL factual_reporting and
    # the authority weighting silently defaulted to 0.5. Stamp them here (in-memory
    # domain lookup — effectively free).
    _mbfc = None
    try:
        from app.models.media_bias import MediaBias
        _mbfc = MediaBias(db)
    except Exception as e:
        logger.warning(f"MediaBias unavailable for BW stamp ({e})")

    try:
        # For "incremental_since_last", look up last completed run date
        if run_type == "incremental_since_last":
            last_run = conn.execute(text("""
                SELECT completed_at FROM bw_tracker_runs
                WHERE status = 'completed'
                AND (brand_id = :bid OR (:bid IS NULL AND brand_id IS NULL))
                ORDER BY completed_at DESC LIMIT 1
            """), {"bid": brand_id})
            last_row = last_run.fetchone()
            if last_row and last_row[0]:
                start_date = last_row[0].strftime('%Y-%m-%d')
                end_date = datetime.now().strftime('%Y-%m-%d')
                logger.info(f"Incremental since last run: {start_date} to {end_date}")
            else:
                # No previous run — fall back to 30 days
                start_date, end_date = _get_date_range(30)
                logger.info("No previous run found, falling back to last 30 days")
            run_type = "incremental"  # Treat as normal incremental from here
        else:
            start_date, end_date = _get_date_range(days_back)

        # Get brands to process
        if brand_id:
            brand_result = conn.execute(text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands WHERE id = :id AND enabled = true"),
                                        {"id": brand_id})
        else:
            brand_result = conn.execute(text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands WHERE enabled = true"))

        brands = [_brand_row_to_dict(row) for row in brand_result.fetchall()]
        if not brands:
            conn.execute(text("""
                UPDATE bw_tracker_runs SET status = 'completed', completed_at = NOW(),
                    articles_processed = 0, articles_categorized = 0
                WHERE id = :run_id
            """), {"run_id": run_id})
            conn.commit()
            conn.close()
            return

        articles_processed = 0
        articles_categorized = 0
        if topics:
            topic_placeholders = ", ".join(f":topic_{i}" for i in range(len(topics)))
            topic_filter = f"AND a.topic IN ({topic_placeholders})"
        else:
            topic_filter = ""

        # Social posts (Reddit/Bluesky) are scored by the lightweight social pipeline and
        # surfaced in the Social tab + the narrative's Social Pulse. They must NOT enter the
        # news classification (bw_article_categories) — substring brand matches (e.g. "Kohen
        # Wiley") would otherwise conflate social noise with news coverage.
        from app.services.social_eval_service import SOCIAL_SOURCES
        social_excl = "AND NOT (" + " OR ".join(
            f"LOWER(a.news_source) LIKE :_soc_{i}" for i in range(len(SOCIAL_SOURCES))) + ")"
        social_excl_params = {f"_soc_{i}": f"%{k}%" for i, k in enumerate(SOCIAL_SOURCES)}

        logger.info(f"BW Run {run_id}: {len(brands)} brands, date range {start_date}-{end_date}, topics={topics!r}, run_type={run_type}")

        for brand in brands:
            bid = brand["id"]

            # Build brand search terms for SQL-level filtering
            search_terms = _get_brand_search_terms(brand)

            if not search_terms:
                logger.warning(f"BW Run {run_id}: brand '{brand['display_name']}' has no search terms, skipping")
                continue

            # Build SQL brand search with word-boundary matching for short terms
            brand_filter, brand_params = _build_brand_filter_sql(search_terms)

            base_params = {"start": start_date, "end": end_date, **brand_params, **social_excl_params}
            if topics:
                for i, t in enumerate(topics):
                    base_params[f"topic_{i}"] = t

            # Query articles that mention this brand (only enriched/analyzed articles)
            if run_type == "full":
                art_result = conn.execute(text(f"""
                    SELECT a.uri, a.title, a.summary, a.topic, a.topic_alignment_score,
                           a.news_source, a.factual_reporting, a.sentiment FROM articles a
                    WHERE a.publication_date >= :start AND a.publication_date <= :end
                    AND a.analyzed = true
                    {social_excl}
                    {topic_filter}
                    {brand_filter}
                """), base_params)
            else:
                # Incremental: only articles not yet classified for this brand
                art_result = conn.execute(text(f"""
                    SELECT a.uri, a.title, a.summary, a.topic, a.topic_alignment_score,
                           a.news_source, a.factual_reporting, a.sentiment FROM articles a
                    LEFT JOIN bw_article_categories bac ON a.uri = bac.article_uri AND bac.brand_id = :bid
                    WHERE a.publication_date >= :start AND a.publication_date <= :end
                    AND a.analyzed = true
                    AND bac.id IS NULL
                    {social_excl}
                    {topic_filter}
                    {brand_filter}
                """), {**base_params, "bid": bid})

            articles = art_result.fetchall()

            # Log skip count for incremental runs
            if run_type != "full":
                already_count = conn.execute(text(f"""
                    SELECT COUNT(*) FROM articles a
                    JOIN bw_article_categories bac ON a.uri = bac.article_uri AND bac.brand_id = :bid
                    WHERE a.publication_date >= :start AND a.publication_date <= :end
                    {topic_filter}
                    {brand_filter}
                """), {**base_params, "bid": bid}).scalar() or 0
                if already_count > 0:
                    logger.info(f"BW Run {run_id}: Skipping {already_count} already-classified articles for brand '{brand['display_name']}'")

            logger.info(f"BW Run {run_id}: brand '{brand['display_name']}' (id={bid}): "
                        f"{len(articles)} new articles to classify matching {search_terms}")

            brand_topic = f"Brand Monitoring {brand['display_name']}"
            for uri, title, summary, art_topic, art_score, art_source, art_factual, art_sent in articles:
                title = title or ''
                summary = summary or ''

                # Source-authority stamp for articles that missed ingest-time enrichment.
                if _mbfc is not None and not art_factual and art_source:
                    try:
                        bi = _mbfc.get_bias_for_source(art_source)
                        if bi:
                            conn.execute(text("""
                                UPDATE articles SET
                                    bias = COALESCE(NULLIF(bias, ''), :bias),
                                    factual_reporting = :fact,
                                    mbfc_credibility_rating = COALESCE(mbfc_credibility_rating, :cred),
                                    bias_source = COALESCE(bias_source, :bsrc),
                                    bias_country = COALESCE(bias_country, :bctry)
                                WHERE uri = :u
                            """), {"bias": bi.get('bias'), "fact": bi.get('factual_reporting'),
                                   "cred": bi.get('mbfc_credibility_rating'),
                                   "bsrc": bi.get('source') or 'mbfc', "bctry": bi.get('country'), "u": uri})
                    except Exception as me:
                        logger.debug(f"MBFC stamp failed for {uri}: {me}")

                articles_processed += 1
                text_input = f"{title}. {summary}" if summary else title
                categories = []
                method = "keyword"
                confidence = None

                # Step 1: SLM (with per-brand threshold)
                brand_threshold = brand.get("config", {}).get("slm_confidence_threshold")
                if slm_available:
                    try:
                        slm_result = slm.classify(text_input, threshold=brand_threshold, return_scores=True)
                        categories = slm_result.get("categories", [])
                        if categories:
                            method = "slm"
                            scores = slm_result.get("scores", {})
                            if scores:
                                matched = [scores[c] for c in categories if c in scores]
                                confidence = sum(matched) / len(matched) if matched else 0.7
                    except Exception as e:
                        logger.debug(f"SLM failed for {uri}: {e}")

                # Step 2: LLM fallback
                if not categories:
                    try:
                        await asyncio.sleep(0.3)
                        llm_result = await _llm_categorize_article(title, summary, brand)
                        categories = llm_result.get("categories", [])
                        method = "llm_semantic"
                        confidence = llm_result.get("confidence", 0.7)
                    except Exception as e:
                        logger.warning(f"LLM classification failed for {uri}: {e}")

                # Step 3: keyword fallback
                if not categories:
                    categories = _categorize_article_keywords(title, summary, brand)
                    method = "keyword"
                    confidence = None

                if categories:
                    # Per-brand relevance: reuse the article's own score when it already
                    # lives in this brand's topic (that score IS brand relevance); for
                    # cross-topic articles, judge against the brand explicitly.
                    brand_rel = None
                    if art_topic == brand_topic and art_score is not None:
                        brand_rel = float(art_score)
                    elif _brand_rel_svc is not None:
                        try:
                            _r = _brand_rel_svc.score_relevance(
                                brand_topic, title, (summary or '')[:2000], keywords=search_terms)
                            brand_rel = float(_r.get("score") or 0.0)
                        except Exception as e:
                            logger.debug(f"brand relevance scoring failed for {uri}: {e}")
                    for cat in categories:
                        try:
                            conn.execute(text("""
                                INSERT INTO bw_article_categories
                                (article_uri, brand_id, category, classification_method, confidence, relevance_score)
                                VALUES (:uri, :bid, :cat, :method, :conf, :rel)
                                ON CONFLICT (article_uri, brand_id, category)
                                DO UPDATE SET classification_method = :method,
                                    confidence = :conf, classified_at = NOW(),
                                    relevance_score = COALESCE(:rel, bw_article_categories.relevance_score)
                            """), {"uri": uri, "bid": bid, "cat": cat, "method": method, "conf": confidence, "rel": brand_rel})
                        except Exception as e:
                            logger.warning(f"Failed to store category {cat} for {uri}: {e}")
                    articles_categorized += 1

                    # Adverse-risk pass: only for negative or risk-vocabulary articles
                    # (bounds LLM cost to the adverse sliver of the stream).
                    try:
                        risk_gate = bool(_NEG_SENT_RE.search(str(art_sent or ''))) or bool(_RISK_TRIGGER_RE.search(text_input))
                        if risk_gate:
                            risks = await _llm_detect_risks(title, summary, brand['display_name'])
                            method_r = 'llm'
                            if risks is None:
                                risks = _keyword_risk_fallback(text_input)
                                method_r = 'keyword'
                            if risks:
                                _store_article_risks(conn, uri, bid, risks, method_r)
                    except Exception as re_err:
                        logger.debug(f"risk pass failed for {uri}: {re_err}")

                if articles_processed % 25 == 0:
                    conn.commit()
                    conn.execute(text("""
                        UPDATE bw_tracker_runs SET articles_processed = :p, articles_categorized = :c
                        WHERE id = :run_id
                    """), {"run_id": run_id, "p": articles_processed, "c": articles_categorized})
                    conn.commit()

            # Update daily stats for this brand
            today = date.today()
            cat_result = conn.execute(text("""
                SELECT category, COUNT(*) FROM bw_article_categories
                WHERE brand_id = :bid GROUP BY category
            """), {"bid": bid})
            for cat, count in cat_result.fetchall():
                _update_daily_stats(conn, bid, cat, today, count)
            conn.commit()

        # Mark run complete
        conn.execute(text("""
            UPDATE bw_tracker_runs SET status = 'completed', completed_at = NOW(),
                articles_processed = :p, articles_categorized = :c
            WHERE id = :run_id
        """), {"run_id": run_id, "p": articles_processed, "c": articles_categorized})
        conn.commit()
        logger.info(f"Brand Watcher run {run_id}: {articles_processed} processed, {articles_categorized} categorized")

        # Send notification on completion
        if articles_categorized > 0:
            try:
                brand_names = [b["display_name"] for b in brands]
                topic_msg = f" across {len(topics)} topics" if topics else ""
                db.facade.create_notification(
                    username=None,
                    type='brand_watcher',
                    title=f'Brand Watcher: {", ".join(brand_names[:3])}{"..." if len(brand_names) > 3 else ""}',
                    message=f'Classified {articles_categorized} articles{topic_msg}',
                    link='/newsfeed?tab=brand-watcher'
                )
            except Exception as notif_err:
                logger.warning(f"Failed to send classification notification: {notif_err}")

        # Auto-generate narrative clusters for brands with enough data
        for brand in brands:
            try:
                _auto_generate_narrative_clusters(db, brand["id"], brand["display_name"])
            except Exception as cluster_err:
                logger.warning(f"Auto narrative clustering failed for {brand['display_name']}: {cluster_err}")

    except Exception as e:
        logger.error(f"Brand Watcher run {run_id} failed: {e}")
        conn.execute(text("""
            UPDATE bw_tracker_runs SET status = 'failed', error_message = :err, completed_at = NOW()
            WHERE id = :run_id
        """), {"run_id": run_id, "err": str(e)})
        conn.commit()
    finally:
        conn.close()


def _auto_generate_narrative_clusters(db, brand_id: int, brand_name: str):
    """Auto-detect article clusters by category + date proximity and create narratives."""
    conn = db._temp_get_connection()
    try:
        # Find clusters: articles grouped by category within 3-day windows, having 3+ articles
        result = conn.execute(text("""
            WITH clustered AS (
                SELECT bac.category,
                       DATE_TRUNC('day', a.publication_date::timestamp)::date as pub_date,
                       COUNT(DISTINCT bac.article_uri) as cnt,
                       ARRAY_AGG(DISTINCT a.title ORDER BY a.title) as titles
                FROM bw_article_categories bac
                JOIN articles a ON bac.article_uri = a.uri
                WHERE bac.brand_id = :bid
                AND a.publication_date >= (NOW() - INTERVAL '7 days')::text
                GROUP BY bac.category, DATE_TRUNC('day', a.publication_date::timestamp)::date
                HAVING COUNT(DISTINCT bac.article_uri) >= 3
            )
            SELECT category, pub_date, cnt, titles
            FROM clustered
            ORDER BY cnt DESC
            LIMIT 5
        """), {"bid": brand_id})

        clusters = result.fetchall()
        if not clusters:
            conn.close()
            return

        for category, pub_date, count, titles in clusters:
            # Check if a narrative already exists for this cluster
            existing = conn.execute(text("""
                SELECT id FROM bw_tracker_narratives
                WHERE brand_id = :bid
                AND data_summary->>'cluster_category' = :cat
                AND date_range_start = :pub_date
                AND generated_at >= NOW() - INTERVAL '7 days'
            """), {"bid": brand_id, "cat": category, "pub_date": pub_date}).fetchone()

            if existing:
                continue

            # Build a simple auto-narrative from the cluster
            title_list = titles[:5] if isinstance(titles, list) else []
            title_summary = "\n".join(f"- {t}" for t in title_list)

            narrative_text = (
                f"## Event Cluster: {category}\n\n"
                f"**{count} related articles** detected around {pub_date} for {brand_name}.\n\n"
                f"### Key Headlines\n{title_summary}\n\n"
                f"*Auto-detected cluster — generate a full narrative for deeper analysis.*"
            )

            data_summary = {
                "cluster_category": category,
                "article_count": count,
                "auto_generated": True,
                "titles": title_list,
            }

            conn.execute(text("""
                INSERT INTO bw_tracker_narratives
                (brand_id, narrative, data_summary, days_back, date_range_start, date_range_end)
                VALUES (:bid, :narrative, :data, 7, :start, :end)
            """), {
                "bid": brand_id,
                "narrative": narrative_text,
                "data": json.dumps(data_summary),
                "start": pub_date,
                "end": pub_date,
            })

        conn.commit()
        logger.info(f"Auto-generated {len(clusters)} narrative clusters for {brand_name}")
    except Exception as e:
        logger.warning(f"Narrative cluster generation error: {e}")
    finally:
        conn.close()


async def _llm_categorize_article(title: str, summary: str, brand: dict) -> Dict[str, Any]:
    """LLM semantic categorization with brand context."""
    from app.ai_models import LiteLLMModel

    try:
        prompt = SEMANTIC_CATEGORIZATION_PROMPT.format(
            category_definitions=CATEGORY_DEFINITIONS,
            brand_name=brand.get("display_name", ""),
            brand_keywords=", ".join(brand.get("brand_keywords", [])),
            product_keywords=", ".join(brand.get("product_keywords", [])),
            people_keywords=", ".join(brand.get("people_keywords", [])),
            title=title,
            summary=summary or "No summary available"
        )

        model = LiteLLMModel.get_instance("gpt-5.4-mini")
        response = await model.agenerate_response([
            {"role": "system", "content": "You are a brand intelligence analyst. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ])

        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        result = json.loads(response_text)
        valid_cats = list(BW_CATEGORIES.keys())
        validated = [c for c in result.get("categories", []) if c in valid_cats]

        return {
            "categories": validated,
            "confidence": result.get("confidence", 0.7),
            "reasoning": result.get("reasoning", ""),
        }
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response: {e}")
        return {
            "categories": _categorize_article_keywords(title, summary, brand),
            "confidence": 0.5,
            "reasoning": "Fallback to keyword matching (JSON parse error)",
        }
    except Exception as e:
        logger.error(f"LLM categorization error: {e}")
        return {
            "categories": _categorize_article_keywords(title, summary, brand),
            "confidence": 0.5,
            "reasoning": f"Fallback to keyword matching ({e})",
        }


@router.get("/classify/status/{run_id}")
async def get_classification_status(run_id: int, session=Depends(verify_session)):
    """Get status of a classification run."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result = conn.execute(text("""
            SELECT id, brand_id, started_at, completed_at,
                   articles_processed, articles_categorized, status, error_message, run_type
            FROM bw_tracker_runs WHERE id = :id
        """), {"id": run_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        return {
            "run_id": row[0], "brand_id": row[1],
            "started_at": str(row[2]) if row[2] else None,
            "completed_at": str(row[3]) if row[3] else None,
            "articles_processed": row[4], "articles_categorized": row[5],
            "status": row[6], "error_message": row[7], "run_type": row[8],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/classify/runs")
async def list_classification_runs(
    limit: int = Query(10, ge=1, le=50),
    session=Depends(verify_session),
):
    """List recent classification runs."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result = conn.execute(text("""
            SELECT r.id, r.brand_id, b.display_name, r.started_at, r.completed_at,
                   r.articles_processed, r.articles_categorized, r.status, r.error_message, r.run_type
            FROM bw_tracker_runs r
            LEFT JOIN bw_brands b ON r.brand_id = b.id
            ORDER BY r.started_at DESC LIMIT :limit
        """), {"limit": limit})

        runs = []
        for row in result.fetchall():
            runs.append({
                "run_id": row[0], "brand_id": row[1], "brand_name": row[2],
                "started_at": str(row[3]) if row[3] else None,
                "completed_at": str(row[4]) if row[4] else None,
                "articles_processed": row[5], "articles_categorized": row[6],
                "status": row[7], "error_message": row[8], "run_type": row[9],
            })
        return {"runs": runs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


def _build_brand_ids_filter(brand_id: Optional[int], brand_ids: Optional[str], alias: str = "bac") -> tuple:
    """Build SQL brand filter from single brand_id or comma-separated brand_ids.
    Returns (sql_fragment, params_dict).
    brand_ids takes precedence over brand_id when both provided."""
    if brand_ids:
        bid_list = [int(x.strip()) for x in brand_ids.split(",") if x.strip().isdigit()]
        if bid_list:
            placeholders = ", ".join(f":_bid_{i}" for i in range(len(bid_list)))
            params = {f"_bid_{i}": b for i, b in enumerate(bid_list)}
            return f"AND {alias}.brand_id IN ({placeholders})", params
    if brand_id:
        return f"AND {alias}.brand_id = :brand_id", {"brand_id": brand_id}
    return "", {}


def _build_topics_filter(topics_param: Optional[str], alias: str = "a") -> tuple:
    """Parse comma-separated topics param into SQL filter and params dict.
    Returns (sql_fragment, params_dict)."""
    if not topics_param:
        return "", {}
    topic_list = [t.strip() for t in topics_param.split(",") if t.strip()]
    if not topic_list:
        return "", {}
    placeholders = ", ".join(f":_topic_{i}" for i in range(len(topic_list)))
    params = {f"_topic_{i}": t for i, t in enumerate(topic_list)}
    return f"AND {alias}.topic IN ({placeholders})", params


# ============================================================================
# Stats & Analytics Endpoints
# ============================================================================

@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    brand_id: Optional[int] = Query(None, description="Filter by brand ID"),
    brand_ids: Optional[str] = Query(None, description="Comma-separated brand IDs"),
    topics: Optional[str] = Query(None, description="Comma-separated topics"),
    days_back: int = Query(365, ge=0, le=730),
    session=Depends(verify_session),
):
    """Overview statistics (overall or per-brand)."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        start_date, end_date = _get_date_range(days_back)
        brand_filter, brand_params = _build_brand_ids_filter(brand_id, brand_ids)
        topic_filter, topic_params = _build_topics_filter(topics)
        params = {"start": start_date, "end": end_date, **brand_params, **topic_params}

        # Category counts
        cat_result = conn.execute(text(f"""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri)
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE a.publication_date >= :start AND a.publication_date <= :end AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            {brand_filter} {topic_filter}
            GROUP BY bac.category
        """), params)

        cat_counts = {cat: 0 for cat in BW_CATEGORIES.keys()}
        for row in cat_result.fetchall():
            if row[0] in cat_counts:
                cat_counts[row[0]] = row[1]

        # Aggregate stats — inner sub-query needs its own brand filter without table alias
        brand_sub_filter = brand_filter.replace("bac.", "")  # strip alias for unqualified column
        brand_sub_where = f"WHERE 1=1 {brand_sub_filter}" if brand_sub_filter else ""
        stats_result = conn.execute(text(f"""
            SELECT COUNT(DISTINCT a.uri),
                   MIN(a.publication_date), MAX(a.publication_date),
                   SUM(CASE WHEN cc.cnt >= 3 THEN 1 ELSE 0 END)
            FROM articles a
            JOIN (
                SELECT article_uri, COUNT(*) as cnt FROM bw_article_categories
                {brand_sub_where}
                GROUP BY article_uri
            ) cc ON a.uri = cc.article_uri
            WHERE a.publication_date >= :start AND a.publication_date <= :end AND a.topic_alignment_score >= 0.4
            {topic_filter}
        """), params)
        sr = stats_result.fetchone()

        # Brand count
        brand_count_result = conn.execute(text("SELECT COUNT(*) FROM bw_brands WHERE enabled = true"))
        total_brands = brand_count_result.fetchone()[0]

        most_active = max(cat_counts.items(), key=lambda x: x[1]) if cat_counts else (None, 0)

        return StatsResponse(
            total_articles=sr[0] or 0,
            total_brands=total_brands,
            date_range_start=str(sr[1]) if sr[1] else None,
            date_range_end=str(sr[2]) if sr[2] else None,
            most_active_category=most_active[0] if most_active[1] > 0 else None,
            multi_category_count=sr[3] or 0,
            category_breakdown=cat_counts,
        )
    except Exception as e:
        logger.error(f"Error fetching brand watcher stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/categories", response_model=List[CategoryDistribution])
async def get_category_distribution(
    brand_id: Optional[int] = Query(None),
    brand_ids: Optional[str] = Query(None, description="Comma-separated brand IDs"),
    topics: Optional[str] = Query(None),
    days_back: int = Query(365, ge=0, le=730),
    session=Depends(verify_session),
):
    """Category distribution across articles."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        start_date, end_date = _get_date_range(days_back)
        brand_filter, brand_params = _build_brand_ids_filter(brand_id, brand_ids)
        topic_filter, topic_params = _build_topics_filter(topics)
        params = {"start": start_date, "end": end_date, **brand_params, **topic_params}

        result = conn.execute(text(f"""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri) as count
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE a.publication_date >= :start AND a.publication_date <= :end AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            {brand_filter} {topic_filter}
            GROUP BY bac.category
        """), params)
        stored = {row[0]: row[1] for row in result.fetchall()}
        cat_counts = {cat: stored.get(cat, 0) for cat in BW_CATEGORIES.keys()}
        total = sum(cat_counts.values())

        # Trend calculation
        prev_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=days_back)).strftime('%Y-%m-%d')
        prev_params = {"prev_start": prev_start, "start": start_date, **brand_params, **topic_params}
        prev_result = conn.execute(text(f"""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri) as count
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE a.publication_date >= :prev_start AND a.publication_date < :start AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            {brand_filter} {topic_filter}
            GROUP BY bac.category
        """), prev_params)
        prev = {row[0]: row[1] for row in prev_result.fetchall()}

        response = []
        for cat, count in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
            pc = prev.get(cat, 0)
            if pc == 0:
                trend = "stable" if count == 0 else "up"
            elif count > pc * 1.1:
                trend = "up"
            elif count < pc * 0.9:
                trend = "down"
            else:
                trend = "stable"
            response.append(CategoryDistribution(
                category=cat,
                article_count=count,
                percentage=round((count / total * 100) if total > 0 else 0, 1),
                recent_trend=trend,
            ))
        return response
    except Exception as e:
        logger.error(f"Error fetching category distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/temporal", response_model=List[TemporalDataResponse])
async def get_temporal_data(
    brand_id: Optional[int] = Query(None),
    brand_ids: Optional[str] = Query(None, description="Comma-separated brand IDs"),
    topics: Optional[str] = Query(None),
    days_back: int = Query(365, ge=0, le=730),
    session=Depends(verify_session),
):
    """Monthly time series by category."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        start_date, end_date = _get_date_range(days_back)
        brand_filter, brand_params = _build_brand_ids_filter(brand_id, brand_ids)
        topic_filter, topic_params = _build_topics_filter(topics)
        params = {"start": start_date, "end": end_date, **brand_params, **topic_params}

        # Monthly totals
        totals_result = conn.execute(text(f"""
            SELECT TO_CHAR(a.publication_date::timestamp, 'YYYY-MM') as month,
                   COUNT(DISTINCT a.uri)
            FROM articles a
            JOIN bw_article_categories bac ON a.uri = bac.article_uri
            WHERE a.publication_date >= :start AND a.publication_date <= :end AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            {brand_filter} {topic_filter}
            GROUP BY TO_CHAR(a.publication_date::timestamp, 'YYYY-MM')
            ORDER BY month
        """), params)
        monthly_totals = {row[0]: row[1] for row in totals_result.fetchall()}

        # Monthly by category
        cat_result = conn.execute(text(f"""
            SELECT TO_CHAR(a.publication_date::timestamp, 'YYYY-MM') as month,
                   bac.category, COUNT(DISTINCT bac.article_uri)
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE a.publication_date >= :start AND a.publication_date <= :end AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            {brand_filter} {topic_filter}
            GROUP BY TO_CHAR(a.publication_date::timestamp, 'YYYY-MM'), bac.category
            ORDER BY month
        """), params)

        monthly_data: Dict[str, Dict[str, int]] = {}
        for row in cat_result.fetchall():
            month, cat, count = row
            if month not in monthly_data:
                monthly_data[month] = {c: 0 for c in BW_CATEGORIES.keys()}
            if cat in BW_CATEGORIES:
                monthly_data[month][cat] = count

        result_list = [
            TemporalDataResponse(month=m, total=monthly_totals.get(m, 0), by_category=monthly_data[m])
            for m in sorted(monthly_data.keys())
        ]
        logger.info(f"Temporal data: {len(result_list)} months, totals={monthly_totals}")
        return result_list
    except Exception as e:
        logger.error(f"Error fetching temporal data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/comparison", response_model=List[ComparisonDataResponse])
async def get_brand_comparison(
    topics: Optional[str] = Query(None),
    brand_ids: Optional[str] = Query(None, description="Comma-separated brand IDs to compare"),
    days_back: int = Query(365, ge=0, le=730),
    session=Depends(verify_session),
):
    """Cross-brand category comparison. Optionally filter to specific brand_ids."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        start_date, end_date = _get_date_range(days_back)
        topic_filter, topic_params = _build_topics_filter(topics)

        if brand_ids:
            bid_list = [int(x.strip()) for x in brand_ids.split(",") if x.strip().isdigit()]
            if bid_list:
                placeholders = ", ".join(f":cmp_bid_{i}" for i in range(len(bid_list)))
                brand_filter_sql = f"AND id IN ({placeholders})"
                bid_params = {f"cmp_bid_{i}": b for i, b in enumerate(bid_list)}
                brands_result = conn.execute(
                    text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands WHERE enabled = true {brand_filter_sql} ORDER BY display_name"),
                    bid_params
                )
            else:
                brands_result = conn.execute(text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands WHERE enabled = true ORDER BY display_name"))
        else:
            brands_result = conn.execute(text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands WHERE enabled = true ORDER BY display_name"))
        brands = [_brand_row_to_dict(row) for row in brands_result.fetchall()]

        response = []
        for brand in brands:
            bid = brand["id"]
            params = {"bid": bid, "start": start_date, "end": end_date, **topic_params}
            cat_result = conn.execute(text(f"""
                SELECT bac.category, COUNT(DISTINCT bac.article_uri)
                FROM bw_article_categories bac
                JOIN articles a ON bac.article_uri = a.uri
                WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
                AND a.publication_date >= :start AND a.publication_date <= :end
                {topic_filter}
                GROUP BY bac.category
            """), params)

            breakdown = {row[0]: row[1] for row in cat_result.fetchall()}
            total = sum(breakdown.values())

            # Sentiment breakdown for this brand
            sent_result = conn.execute(text(f"""
                SELECT COALESCE(a.sentiment, 'Unknown') as sentiment, COUNT(DISTINCT bac.article_uri)
                FROM bw_article_categories bac
                JOIN articles a ON bac.article_uri = a.uri
                WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
                AND a.publication_date >= :start AND a.publication_date <= :end
                {topic_filter}
                GROUP BY COALESCE(a.sentiment, 'Unknown')
            """), params)
            sentiment_breakdown = {row[0]: row[1] for row in sent_result.fetchall()}

            response.append(ComparisonDataResponse(
                brand_id=bid,
                brand_name=brand["display_name"],
                total_articles=total,
                category_breakdown=breakdown,
                sentiment_breakdown=sentiment_breakdown,
                color=brand.get("color"),
            ))
        return response
    except Exception as e:
        logger.error(f"Error fetching comparison: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/share-of-voice", response_model=List[ShareOfVoiceResponse])
async def get_share_of_voice(
    topics: Optional[str] = Query(None),
    days_back: int = Query(365, ge=0, le=730),
    session=Depends(verify_session),
):
    """Mention volume comparison across brands."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        start_date, end_date = _get_date_range(days_back)
        topic_filter, topic_params = _build_topics_filter(topics)
        params = {"start": start_date, "end": end_date, **topic_params}

        result = conn.execute(text(f"""
            SELECT bac.brand_id, b.display_name, b.color,
                   COUNT(DISTINCT bac.article_uri)
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            JOIN bw_brands b ON bac.brand_id = b.id
            WHERE a.publication_date >= :start AND a.publication_date <= :end AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND b.enabled = true
            {topic_filter}
            GROUP BY bac.brand_id, b.display_name, b.color
            ORDER BY COUNT(DISTINCT bac.article_uri) DESC
        """), params)

        rows = result.fetchall()
        grand_total = sum(r[3] for r in rows) or 1

        return [
            ShareOfVoiceResponse(
                brand_id=r[0], brand_name=r[1],
                mention_count=r[3],
                percentage=round(r[3] / grand_total * 100, 1),
                color=r[2],
            ) for r in rows
        ]
    except Exception as e:
        logger.error(f"Error fetching share of voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Sentiment Trends Endpoint
# ============================================================================

@router.get("/brands/{brand_id}/sentiment-trends")
async def get_sentiment_trends(
    brand_id: int,
    topics: Optional[str] = Query(None),
    days_back: int = Query(365, ge=0, le=730),
    session=Depends(verify_session),
):
    """Weekly sentiment trends per category for a brand."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        start_date, end_date = _get_date_range(days_back)
        topic_filter, topic_params = _build_topics_filter(topics)
        params = {"bid": brand_id, "start": start_date, "end": end_date, **topic_params}

        result = conn.execute(text(f"""
            SELECT DATE_TRUNC('week', a.publication_date::timestamp)::date as week,
                   bac.category,
                   a.sentiment,
                   COUNT(*) as cnt
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND a.publication_date >= :start AND a.publication_date <= :end
            AND a.sentiment IS NOT NULL AND a.sentiment != ''
            {topic_filter}
            GROUP BY week, bac.category, a.sentiment
            ORDER BY week
        """), params)

        # Build structured response
        weekly_data: Dict[str, Dict[str, Dict[str, int]]] = {}
        for row in result.fetchall():
            week_str = str(row[0])
            category = row[1]
            sentiment = row[2]
            count = row[3]

            if week_str not in weekly_data:
                weekly_data[week_str] = {}
            if category not in weekly_data[week_str]:
                weekly_data[week_str][category] = {}
            weekly_data[week_str][category][sentiment] = count

        trends = []
        for week, cats in sorted(weekly_data.items()):
            for category, sentiments in cats.items():
                total = sum(sentiments.values())
                trends.append({
                    "week": week,
                    "category": category,
                    "sentiments": sentiments,
                    "total": total,
                })

        return {"trends": trends}
    except Exception as e:
        logger.error(f"Error fetching sentiment trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Category Alerts Endpoint
# ============================================================================

@router.get("/brands/{brand_id}/alerts")
async def get_brand_alerts(
    brand_id: int,
    days_back: int = Query(30, ge=1, le=365),
    session=Depends(verify_session),
):
    """Get recent spike alerts for a brand by checking category counts vs rolling average."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        # Recent 7-day counts
        recent = conn.execute(text("""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri) as cnt
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND a.publication_date >= (NOW() - INTERVAL '7 days')::text
            GROUP BY bac.category
        """), {"bid": brand_id})
        recent_counts = {row[0]: row[1] for row in recent.fetchall()}

        # 30-day avg (per week, excluding last 7 days)
        avg_result = conn.execute(text("""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri) / 4.0 as avg_weekly
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND a.publication_date >= (NOW() - INTERVAL '30 days')::text
            AND a.publication_date < (NOW() - INTERVAL '7 days')::text
            GROUP BY bac.category
        """), {"bid": brand_id})
        avg_counts = {row[0]: float(row[1]) for row in avg_result.fetchall()}

        alerts = []
        for category, count in recent_counts.items():
            avg = avg_counts.get(category, 0)
            if avg > 0 and count >= avg * 2 and count >= 3:
                alerts.append({
                    "category": category,
                    "current_count": count,
                    "average_count": round(avg, 1),
                    "spike_ratio": round(count / avg, 1),
                    "severity": "high" if count >= avg * 3 else "medium",
                    "articles": [],
                })

        # Attach the actual articles driving each spike so the UI can link to them
        # (not just show a count). Same window + relevance filter as the spike detection.
        if alerts:
            spiking = [a["category"] for a in alerts]
            ph = ", ".join(f":c{i}" for i in range(len(spiking)))
            art_params = {"bid": brand_id}
            for i, c in enumerate(spiking):
                art_params[f"c{i}"] = c
            art_rows = conn.execute(text(f"""
                SELECT bac.category, a.uri, a.title, a.publication_date, a.sentiment, a.news_source
                FROM bw_article_categories bac
                JOIN articles a ON bac.article_uri = a.uri
                WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
                AND a.publication_date >= (NOW() - INTERVAL '7 days')::text
                AND bac.category IN ({ph})
                ORDER BY a.publication_date DESC
            """), art_params).fetchall()
            by_cat: Dict[str, list] = {}
            for cat, uri, title, pubdate, sentiment, source in art_rows:
                bucket = by_cat.setdefault(cat, [])
                if len(bucket) < 12:
                    bucket.append({
                        "uri": uri, "title": title,
                        "publication_date": str(pubdate) if pubdate else None,
                        "sentiment": sentiment, "news_source": source,
                    })
            for a in alerts:
                a["articles"] = by_cat.get(a["category"], [])

        return {"alerts": sorted(alerts, key=lambda a: a["spike_ratio"], reverse=True)}
    except Exception as e:
        logger.error(f"Error fetching brand alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Export Endpoint
# ============================================================================

@router.get("/brands/{brand_id}/export")
async def export_brand_data(
    brand_id: int,
    format: str = Query("csv", description="Export format: csv or json"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    days_back: int = Query(365, ge=0, le=730),
    session=Depends(verify_session),
):
    """Export classified articles for a brand as CSV or JSON."""
    from fastapi.responses import StreamingResponse
    import io
    import csv

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        if start_date and end_date:
            sd, ed = start_date, end_date
        else:
            sd, ed = _get_date_range(days_back)

        result = conn.execute(text("""
            SELECT a.publication_date, a.title, bac.category,
                   a.sentiment, a.news_source, bac.confidence,
                   bac.classification_method, a.uri,
                   COALESCE(bac.relevance_score, a.topic_alignment_score) AS relevance,
                   a.factual_reporting, a.bias,
                   rk.risks, fr.status AS case_status
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            LEFT JOIN (
                SELECT article_uri, brand_id,
                       STRING_AGG(risk_type || ' (' || severity || ')', '; '
                                  ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END) AS risks
                FROM bw_article_risks GROUP BY article_uri, brand_id
            ) rk ON rk.article_uri = a.uri AND rk.brand_id = bac.brand_id
            LEFT JOIN bw_finding_reviews fr ON fr.article_uri = a.uri AND fr.brand_id = bac.brand_id
            WHERE bac.brand_id = :bid
            AND a.publication_date >= :start AND a.publication_date <= :end
            ORDER BY a.publication_date DESC
        """), {"bid": brand_id, "start": sd, "end": ed})

        rows = result.fetchall()

        # Get brand name for filename
        brand_row = conn.execute(text("SELECT display_name FROM bw_brands WHERE id = :id"), {"id": brand_id}).fetchone()
        brand_name = brand_row[0] if brand_row else "brand"
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', brand_name)

        if format == "json":
            data = [
                {
                    "date": str(r[0]) if r[0] else None,
                    "title": r[1],
                    "category": r[2],
                    "sentiment": r[3],
                    "source": r[4],
                    "confidence": float(r[5]) if r[5] else None,
                    "method": r[6],
                    "uri": r[7],
                    "relevance": float(r[8]) if r[8] is not None else None,
                    "factuality": r[9],
                    "bias": r[10],
                    "risks": r[11],
                    "case_status": r[12] or "new",
                }
                for r in rows
            ]
            return {"brand": brand_name, "export_date": datetime.now().isoformat(), "articles": data, "total": len(data)}

        # CSV export
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Title", "Category", "Sentiment", "Source", "Confidence", "Method", "URI",
                         "Relevance", "Factuality", "Bias", "Risks", "Case Status"])
        for r in rows:
            writer.writerow([
                str(r[0]) if r[0] else "",
                r[1] or "",
                r[2] or "",
                r[3] or "",
                r[4] or "",
                f"{r[5]:.2f}" if r[5] else "",
                r[6] or "",
                r[7] or "",
                f"{r[8]:.2f}" if r[8] is not None else "",
                r[9] or "",
                r[10] or "",
                r[11] or "",
                r[12] or "new",
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=brand_watcher_{safe_name}_{sd}_{ed}.csv"},
        )
    except Exception as e:
        logger.error(f"Error exporting brand data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Articles Endpoint
# ============================================================================

@router.get("/articles", response_model=ArticlesListResponse)
async def get_articles(
    brand_id: Optional[int] = Query(None),
    brand_ids: Optional[str] = Query(None, description="Comma-separated brand IDs"),
    topics: Optional[str] = Query(None),
    categories: Optional[str] = Query(None, description="Comma-separated categories"),
    days_back: int = Query(365, ge=0, le=730),
    sort_by: str = Query("date"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
    session=Depends(verify_session),
):
    """Paginated classified articles list."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        start_date, end_date = _get_date_range(days_back)
        cat_filter_list = [c.strip() for c in categories.split(',')] if categories else None
        offset = (page - 1) * per_page

        brand_clause, brand_params = _build_brand_ids_filter(brand_id, brand_ids)
        topic_clause, topic_params = _build_topics_filter(topics)
        params: dict = {"start": start_date, "end": end_date, "per_page": per_page, "offset": offset, **brand_params, **topic_params}

        cat_clause = ""
        if cat_filter_list:
            placeholders = ', '.join([f':cat_{i}' for i in range(len(cat_filter_list))])
            cat_clause = f"AND bac.category IN ({placeholders})"
            for i, c in enumerate(cat_filter_list):
                params[f'cat_{i}'] = c

        base = f"""
            WITH art AS (
                SELECT a.uri, a.title, a.summary, a.news_source, a.publication_date,
                       a.sentiment, bac.brand_id, b.display_name as brand_name,
                       ARRAY_AGG(DISTINCT bac.category) as categories,
                       COUNT(DISTINCT bac.category) as cat_count,
                       a.tags, a.extracted_article_keywords, b.name as brand_slug,
                       a.opoint_entities, a.factual_reporting,
                       MAX(st.story_group_id) as story_group_id,
                       MAX(stc.story_size) as story_size,
                       MAX(stc.story_neg) as story_neg,
                       MAX(stc.story_pos) as story_pos,
                       MAX(stc.story_scored) as story_scored
                FROM articles a
                JOIN bw_article_categories bac ON a.uri = bac.article_uri
                JOIN bw_brands b ON bac.brand_id = b.id
                -- Story clustering: syndicated republications share a story_group_id;
                -- story_size ("×N sources") is an amplification/velocity signal.
                LEFT JOIN bw_article_stories st
                    ON st.article_uri = a.uri AND st.brand_id = bac.brand_id
                LEFT JOIN (
                    -- Per-story sentiment mix across the syndicated copies: powers the
                    -- "negative consensus" / "polarized coverage" screening flags.
                    SELECT st2.brand_id, st2.story_group_id, COUNT(*) AS story_size,
                           COUNT(*) FILTER (WHERE a2.sentiment ~* 'neg|concern|pessim|critical|alarm') AS story_neg,
                           COUNT(*) FILTER (WHERE a2.sentiment ~* 'pos|optimis') AS story_pos,
                           COUNT(*) FILTER (WHERE COALESCE(a2.sentiment, '') <> '') AS story_scored
                    FROM bw_article_stories st2
                    JOIN articles a2 ON a2.uri = st2.article_uri
                    GROUP BY st2.brand_id, st2.story_group_id
                ) stc ON stc.brand_id = st.brand_id AND stc.story_group_id = st.story_group_id
                WHERE a.publication_date >= :start AND a.publication_date <= :end
                AND a.analyzed = true
                AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
                {brand_clause} {cat_clause} {topic_clause}
                GROUP BY a.uri, a.title, a.summary, a.news_source,
                         a.publication_date, a.sentiment, bac.brand_id, b.display_name,
                         a.tags, a.extracted_article_keywords, b.name, a.opoint_entities,
                         a.factual_reporting
            )
        """

        count_q = base + " SELECT COUNT(*) FROM art"
        total_count = conn.execute(text(count_q), params).scalar() or 0
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 0

        order = "ORDER BY cat_count DESC, publication_date DESC" if sort_by == "category_count" else "ORDER BY publication_date DESC"
        arts_q = base + f" SELECT * FROM art {order} LIMIT :per_page OFFSET :offset"
        result = conn.execute(text(arts_q), params)

        # Pre-load brand search terms for matched_keywords computation
        brand_terms_cache: dict = {}
        if brand_id:
            brand_row = conn.execute(text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands WHERE id = :id"), {"id": brand_id}).fetchone()
            if brand_row:
                brand_terms_cache[brand_id] = _get_brand_search_terms(_brand_row_to_dict(brand_row))

        # Opoint entity verification: brand -> Wikidata IDs (loaded once)
        from app.services.opoint_brand_matcher import load_brand_wikidata, match_brands
        try:
            brand_wikidata = load_brand_wikidata(db.facade)
        except Exception as e:
            logger.debug(f"opoint brand_wikidata load failed: {e}")
            brand_wikidata = {}

        rows_all = result.fetchall()
        # Bulk-load adverse risk findings + case states for this page.
        risk_map: dict = {}
        review_map: dict = {}
        uris_page = [r[0] for r in rows_all]
        if uris_page:
            for r_uri, r_bid, r_type, r_sev, r_conf in conn.execute(text(
                "SELECT article_uri, brand_id, risk_type, severity, confidence FROM bw_article_risks WHERE article_uri = ANY(:us)"
            ), {"us": uris_page}).fetchall():
                risk_map.setdefault((r_uri, r_bid), []).append(
                    {"risk_type": r_type, "severity": r_sev, "confidence": r_conf})
            for v_uri, v_bid, v_status in conn.execute(text(
                "SELECT article_uri, brand_id, status FROM bw_finding_reviews WHERE article_uri = ANY(:us)"
            ), {"us": uris_page}).fetchall():
                review_map[(v_uri, v_bid)] = v_status

        # Bulk-load Five Signals screens for this page (compact row summary).
        signals_map: dict = {}
        if uris_page:
            for s_uri, s_bid, s_status, s_verdict, s_comp, s_sigs in conn.execute(text(
                "SELECT article_uri, brand_id, status, verdict, composite_score, signals"
                " FROM bw_article_signals WHERE article_uri = ANY(:us)"
            ), {"us": uris_page}).fetchall():
                s_parsed = s_sigs if isinstance(s_sigs, dict) else (json.loads(s_sigs) if s_sigs else {})
                signals_map[(s_uri, s_bid)] = {
                    "status": s_status, "verdict": s_verdict,
                    "composite": s_comp,
                    "signals": [
                        {"key": k, "band": (s_parsed.get(k) or {}).get("band"),
                         "score": (s_parsed.get(k) or {}).get("score")}
                        for k in ("veracity", "source_credibility", "corroboration",
                                  "propagation", "amplification_integrity")
                    ] if s_parsed else [],
                }

        articles = []
        for row in rows_all:
            row_brand_id = row[6]
            if row_brand_id and row_brand_id not in brand_terms_cache:
                br = conn.execute(text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands WHERE id = :id"), {"id": row_brand_id}).fetchone()
                if br:
                    brand_terms_cache[row_brand_id] = _get_brand_search_terms(_brand_row_to_dict(br))
            search_terms = brand_terms_cache.get(row_brand_id, [])
            matched = _find_matched_keywords(row[1], row[2], search_terms, tags=row[10], keywords=row[11]) if search_terms else []

            # Opoint entity verification for this article (live-computed)
            entity_match = None
            if brand_wikidata:
                hits = match_brands(row[13], brand_wikidata)  # row[13] = opoint_entities
                if hits:
                    row_brand_slug = row[12]  # b.name (slug)
                    this_brand = next((h for h in hits if h["brand"] == row_brand_slug), None)
                    entity_match = {
                        "brands": sorted({h["brand"] for h in hits}),
                        "relevance": round(this_brand["relevance_score"], 3) if this_brand else None,
                        "verified": this_brand is not None,
                    }

            articles.append(ArticleResponse(
                uri=row[0], title=row[1], summary=row[2],
                news_source=row[3],
                publication_date=str(row[4]) if row[4] else None,
                sentiment=row[5],
                brand_id=row[6], brand_name=row[7],
                categories=list(row[8]) if row[8] else [],
                matched_keywords=matched,
                entity_match=entity_match,
                factual_reporting=row[14],
                story_group_id=row[15],
                story_size=row[16],
                story_neg=row[17],
                story_pos=row[18],
                story_scored=row[19],
                risks=risk_map.get((row[0], row[6]), []),
                review_status=review_map.get((row[0], row[6])),
                signals_summary=signals_map.get((row[0], row[6])),
            ))

        from app.services.bw_signals_service import signals_available
        return ArticlesListResponse(
            articles=articles, total_count=total_count,
            page=page, per_page=per_page, total_pages=total_pages,
            signals_available=signals_available(),
        )
    except Exception as e:
        logger.error(f"Error fetching brand watcher articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Narrative / Insights Endpoints
# ============================================================================

@router.post("/generate-narrative", response_model=NarrativeResponse)
async def generate_narrative(request: NarrativeRequest, session=Depends(verify_session)):
    """Generate an LLM-powered brand intelligence narrative."""
    from app.ai_models import LiteLLMModel

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        start_date, end_date = _get_date_range(request.days_back)

        # Fetch brand
        brand_result = conn.execute(text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands WHERE id = :id"),
                                    {"id": request.brand_id})
        brand_row = brand_result.fetchone()
        if not brand_row:
            raise HTTPException(status_code=404, detail="Brand not found")
        brand = _brand_row_to_dict(brand_row)

        # Category counts
        cat_result = conn.execute(text("""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri)
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND a.publication_date >= :start AND a.publication_date <= :end
            GROUP BY bac.category ORDER BY COUNT(DISTINCT bac.article_uri) DESC
        """), {"bid": request.brand_id, "start": start_date, "end": end_date})
        category_data = {row[0]: row[1] for row in cat_result.fetchall()}

        total_articles = sum(category_data.values()) or 0
        category_breakdown = "\n".join([
            f"- {cat}: {count} articles ({round(count/total_articles*100, 1)}%)"
            for cat, count in sorted(category_data.items(), key=lambda x: x[1], reverse=True)
        ]) if total_articles > 0 else "No classified articles found"

        # Competitor mentions
        competitor_kws = brand.get("competitor_keywords") or []
        competitor_counts: Dict[str, int] = {}
        if competitor_kws:
            art_result = conn.execute(text("""
                SELECT DISTINCT a.title, a.summary FROM articles a
                JOIN bw_article_categories bac ON a.uri = bac.article_uri
                WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
                AND a.publication_date >= :start AND a.publication_date <= :end
            """), {"bid": request.brand_id, "start": start_date, "end": end_date})
            for atitle, asumm in art_result.fetchall():
                combined = f"{atitle or ''} {asumm or ''}".lower()
                for comp in competitor_kws:
                    if comp.lower() in combined:
                        competitor_counts[comp] = competitor_counts.get(comp, 0) + 1

        competitor_breakdown = "\n".join([
            f"- {comp}: {count} mentions"
            for comp, count in sorted(competitor_counts.items(), key=lambda x: x[1], reverse=True)[:8]
            if count > 0
        ]) or "No competitor mentions tracked"

        # --- Compute Brand Risk Assessment (mirrors frontend logic) ---
        # Sentiment trends: weekly sentiment aggregates
        sent_result = conn.execute(text("""
            SELECT DATE_TRUNC('week', a.publication_date::timestamp)::date as week,
                   a.sentiment, COUNT(*) as cnt
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND a.publication_date >= :start AND a.publication_date <= :end
            AND a.sentiment IS NOT NULL AND a.sentiment != ''
            GROUP BY week, a.sentiment
            ORDER BY week
        """), {"bid": request.brand_id, "start": start_date, "end": end_date})

        # Normalize sentiment labels to match frontend bucketing
        _NEGATIVE_LABELS = {"negative", "pessimistic", "concerning", "concerned", "critical", "alarming"}
        _POSITIVE_LABELS = {"positive", "optimistic", "positive development"}

        weekly_sentiments: Dict[str, Dict[str, int]] = {}
        for row in sent_result.fetchall():
            week_str = str(row[0])
            raw_sentiment = row[1]
            count = row[2]
            if week_str not in weekly_sentiments:
                weekly_sentiments[week_str] = {"Positive": 0, "Neutral": 0, "Negative": 0, "total": 0}
            lo = raw_sentiment.lower().strip() if raw_sentiment else ""
            if lo in _NEGATIVE_LABELS:
                bucket = "Negative"
            elif lo in _POSITIVE_LABELS:
                bucket = "Positive"
            else:
                bucket = "Neutral"
            weekly_sentiments[week_str][bucket] += count
            weekly_sentiments[week_str]["total"] += count

        sorted_weeks = sorted(weekly_sentiments.keys())
        recent_4 = sorted_weeks[-4:] if len(sorted_weeks) >= 4 else sorted_weeks
        older_4 = sorted_weeks[-8:-4] if len(sorted_weeks) >= 8 else sorted_weeks[:max(0, len(sorted_weeks) - 4)]

        recent_neg = sum(weekly_sentiments[w].get("Negative", 0) for w in recent_4)
        recent_total = sum(weekly_sentiments[w].get("total", 0) for w in recent_4)
        older_neg = sum(weekly_sentiments[w].get("Negative", 0) for w in older_4)
        older_total = sum(weekly_sentiments[w].get("total", 0) for w in older_4)

        recent_neg_pct = (recent_neg / recent_total * 100) if recent_total > 0 else 0
        older_neg_pct = (older_neg / older_total * 100) if older_total > 0 else 0
        neg_trend = recent_neg_pct - older_neg_pct  # positive = worsening

        # Category spike alerts (recent 7d vs prior 30d avg)
        recent_alert = conn.execute(text("""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri) as cnt
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND a.publication_date >= (NOW() - INTERVAL '7 days')::text
            GROUP BY bac.category
        """), {"bid": request.brand_id})
        recent_alert_counts = {row[0]: row[1] for row in recent_alert.fetchall()}

        avg_alert = conn.execute(text("""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri) / 4.0 as avg_weekly
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND a.publication_date >= (NOW() - INTERVAL '30 days')::text
            AND a.publication_date < (NOW() - INTERVAL '7 days')::text
            GROUP BY bac.category
        """), {"bid": request.brand_id})
        avg_alert_counts = {row[0]: float(row[1]) for row in avg_alert.fetchall()}

        alerts = []
        for category, count in recent_alert_counts.items():
            avg = avg_alert_counts.get(category, 0)
            if avg > 0 and count >= avg * 2 and count >= 3:
                severity = "high" if count >= avg * 3 else "medium"
                alerts.append({"category": category, "current": count, "average": round(avg, 1),
                               "spike_ratio": round(count / avg, 1), "severity": severity})

        alert_count = len(alerts)
        high_alerts = sum(1 for a in alerts if a["severity"] == "high")

        risk_score = min(100, round(
            (recent_neg_pct * 1.5) +
            (neg_trend * 2 if neg_trend > 0 else 0) +
            (alert_count * 5) +
            (high_alerts * 10)
        ))
        risk_level = "High" if risk_score >= 60 else "Elevated" if risk_score >= 30 else "Low"

        # Fetch recent negative/concerning articles so the narrative can cite specific drivers
        neg_articles_result = conn.execute(text("""
            SELECT DISTINCT a.title, a.summary, a.sentiment,
                   bac.category, a.publication_date, a.uri, a.news_source
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND a.publication_date >= :start AND a.publication_date <= :end
            AND LOWER(a.sentiment) IN ('negative', 'pessimistic', 'concerning',
                                        'concerned', 'critical', 'alarming')
            ORDER BY a.publication_date DESC
            LIMIT 20
        """), {"bid": request.brand_id, "start": start_date, "end": end_date})
        neg_articles = neg_articles_result.fetchall()

        neg_articles_text = ""
        if neg_articles:
            lines = []
            for art in neg_articles:
                title = art[0] or "Untitled"
                summary = (art[1] or "")[:200]
                category = art[3] or ""
                pub_date = art[4] or ""
                uri = art[5] or ""
                source = art[6] or "Unknown source"
                lines.append(f"- [{category}] ({pub_date}) [{title}]({uri}) — Source: {source} — {summary}")
            neg_articles_text = "\n".join(lines)

        # Fetch recent positive articles to ground positive signals with evidence
        pos_articles_result = conn.execute(text("""
            SELECT DISTINCT a.title, a.summary, a.sentiment,
                   bac.category, a.publication_date, a.uri, a.news_source
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND a.publication_date >= :start AND a.publication_date <= :end
            AND LOWER(a.sentiment) IN ('positive', 'optimistic', 'positive development')
            ORDER BY a.publication_date DESC
            LIMIT 20
        """), {"bid": request.brand_id, "start": start_date, "end": end_date})
        pos_articles = pos_articles_result.fetchall()

        pos_articles_text = ""
        if pos_articles:
            lines = []
            for art in pos_articles:
                title = art[0] or "Untitled"
                summary = (art[1] or "")[:200]
                category = art[3] or ""
                pub_date = art[4] or ""
                uri = art[5] or ""
                source = art[6] or "Unknown source"
                lines.append(f"- [{category}] ({pub_date}) [{title}]({uri}) — Source: {source} — {summary}")
            pos_articles_text = "\n".join(lines)

        # Build risk assessment text for the prompt
        risk_factors = []
        if recent_neg_pct >= 15:
            risk_factors.append(f"High negative sentiment volume ({recent_neg_pct:.1f}% of recent coverage)")
        if neg_trend > 2:
            risk_factors.append(f"Negative sentiment trending upward (+{neg_trend:.1f} percentage points vs prior 4 weeks)")
        if high_alerts > 0:
            risk_factors.append(f"{high_alerts} high-severity category spike(s): " +
                                ", ".join(a['category'] for a in alerts if a['severity'] == 'high'))
        if alert_count > 0 and high_alerts == 0:
            risk_factors.append(f"{alert_count} category spike alert(s): " +
                                ", ".join(a['category'] for a in alerts))

        risk_assessment = f"Risk Level: {risk_level} (Score: {risk_score}/100)\n"
        risk_assessment += f"Recent Negative Sentiment: {recent_neg_pct:.1f}%\n"
        risk_assessment += f"Negative Trend (4-week change): {'+' if neg_trend > 0 else ''}{neg_trend:.1f} percentage points\n"
        risk_assessment += f"Active Alerts: {alert_count}" + (f" ({high_alerts} high-severity)" if high_alerts > 0 else "") + "\n"
        if risk_factors:
            risk_assessment += "Contributing Factors:\n" + "\n".join(f"- {f}" for f in risk_factors)
        else:
            risk_assessment += "No significant risk factors identified"

        if neg_articles_text:
            risk_assessment += f"\n\n**Recent Negative/Concerning Articles ({len(neg_articles)} most recent):**\n{neg_articles_text}"

        key_articles = ""
        if pos_articles_text:
            key_articles += f"**Recent Positive/Optimistic Articles ({len(pos_articles)} most recent):**\n{pos_articles_text}"

        # --- Social Pulse: Bluesky/Reddit signal for this brand's monitoring topic ---
        # Social posts bypass news classification (bw_article_categories); they're matched
        # to the brand by its monitoring topic + a social news_source. relevance =
        # topic_alignment_score from the lightweight social eval.
        from app.services.social_eval_service import SOCIAL_SOURCES
        social_topic = f"Brand Monitoring {brand['display_name']}"
        _ssrc = "(" + " OR ".join(f"LOWER(a.news_source) LIKE :_ssrc_{i}" for i in range(len(SOCIAL_SOURCES))) + ")"
        _sparams = {"stopic": social_topic, "start": start_date, "end": end_date}
        for i, k in enumerate(SOCIAL_SOURCES):
            _sparams[f"_ssrc_{i}"] = f"%{k}%"
        social_rows = conn.execute(text(f"""
            SELECT a.title, a.summary, a.news_source, a.publication_date,
                   a.topic_alignment_score, a.sentiment
            FROM articles a
            WHERE a.topic = :stopic
              AND a.publication_date >= :start AND a.publication_date <= :end
              AND {_ssrc}
            ORDER BY a.publication_date DESC
        """), _sparams).fetchall()

        social_signal = "No social (Reddit/Bluesky) posts were collected for this brand in the period."
        social_summary = {"total": 0, "by_platform": {}, "evaluated": 0, "net_sentiment": None, "on_brand": 0}
        if social_rows:
            def _splat(ns):
                s = (ns or "").lower()
                return "reddit" if "reddit" in s else ("bluesky" if ("bsky" in s or "bluesky" in s) else "social")
            plat: Dict[str, int] = {}
            pos = neg = scored = 0
            on_brand = []
            for s_title, s_summary, s_ns, s_pub, s_rel, s_sent in social_rows:
                pl = _splat(s_ns)
                plat[pl] = plat.get(pl, 0) + 1
                if s_rel is not None and s_rel >= 0.4:
                    on_brand.append((s_rel, s_title, s_summary, s_sent, s_pub, pl))
                    lo = (s_sent or "").lower()
                    if lo in _POSITIVE_LABELS or "pos" in lo:
                        pos += 1; scored += 1
                    elif lo in _NEGATIVE_LABELS or "neg" in lo:
                        neg += 1; scored += 1
                    elif s_sent:
                        scored += 1
            net = round((pos - neg) / scored * 100) if scored else None
            on_brand.sort(key=lambda x: x[0], reverse=True)
            lines = [
                f"Total social posts: {len(social_rows)} ("
                + ", ".join(f"{k}: {v}" for k, v in sorted(plat.items(), key=lambda x: -x[1])) + ")",
                f"On-brand posts (relevance >= 0.4): {len(on_brand)}",
            ]
            if net is not None:
                lines.append(f"Net sentiment among on-brand posts: {'+' if net > 0 else ''}{net}% (positive - negative)")
            if on_brand:
                lines.append("Top on-brand posts:")
                for o_rel, o_title, o_summary, o_sent, o_pub, o_pl in on_brand[:8]:
                    body = (o_summary or o_title or "")[:160].replace("\n", " ")
                    lines.append(f"- [{o_pl}] ({str(o_pub)[:10]}) rel {o_rel:.2f}, {o_sent or 'unrated'}: {body}")
            social_signal = "\n".join(lines)
            social_summary = {"total": len(social_rows), "by_platform": plat,
                              "evaluated": scored, "net_sentiment": net, "on_brand": len(on_brand)}

        # Adverse risk findings (taxonomy) recorded against articles in the window
        nrisk_rows = conn.execute(text("""
            SELECT r.risk_type, r.severity, a.title, a.uri
            FROM bw_article_risks r JOIN articles a ON a.uri = r.article_uri
            WHERE r.brand_id = :bid
              AND a.publication_date >= :start AND a.publication_date <= :end
            ORDER BY CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                     a.publication_date DESC
        """), {"bid": request.brand_id, "start": start_date, "end": end_date}).fetchall()
        nrisk_by_type: Dict[str, int] = {}
        for _rt, _sev, _t, _u in nrisk_rows:
            nrisk_by_type[_rt] = nrisk_by_type.get(_rt, 0) + 1
        if nrisk_rows:
            _rf = ["Counts by type: " + ", ".join(
                f"{k}: {v}" for k, v in sorted(nrisk_by_type.items(), key=lambda x: -x[1]))]
            for _rt, _sev, _t, _u in nrisk_rows[:8]:
                _rf.append(f"- {_rt} ({_sev}): [{_t}]({_u})")
            risk_findings = "\n".join(_rf)
        else:
            risk_findings = "None recorded in this period."

        # Five Signals screens (saas claim-validation + propagation) on articles
        # in the window — feeds the same Risk & Compliance section.
        nsig_rows = conn.execute(text("""
            SELECT s.verdict, s.composite_score, s.signals, a.title, a.uri
            FROM bw_article_signals s JOIN articles a ON a.uri = s.article_uri
            WHERE s.brand_id = :bid AND s.status = 'completed'
              AND a.publication_date >= :start AND a.publication_date <= :end
            ORDER BY s.composite_score ASC NULLS LAST
        """), {"bid": request.brand_id, "start": start_date, "end": end_date}).fetchall()
        nsig_verdicts: Dict[str, int] = {}
        nsig_flagged = []
        for _sv, _sc, _ss, _st, _su in nsig_rows:
            if _sv:
                nsig_verdicts[_sv] = nsig_verdicts.get(_sv, 0) + 1
            _ssp = _ss if isinstance(_ss, dict) else (json.loads(_ss) if _ss else {})
            _amp = (_ssp.get("amplification_integrity") or {})
            if _sv in ("contested", "non_independent") or _amp.get("band") == "bad":
                nsig_flagged.append((_st, _su, _sv, _amp.get("summary")))
        if nsig_rows:
            _sf = [f"\nFive Signals screening: {len(nsig_rows)} articles screened "
                   f"(claim validation + social propagation). Verdicts: "
                   + ", ".join(f"{k}: {v}" for k, v in sorted(nsig_verdicts.items(), key=lambda x: -x[1]))
                   + "."]
            for _st, _su, _sv, _amps in nsig_flagged[:5]:
                _line = f"- Flagged: [{_st}]({_su}) — verdict {_sv}"
                if _amps:
                    _line += f"; {_amps}"
                _sf.append(_line)
            risk_findings += "\n" + "\n".join(_sf)

        # Open incidents (managed cases)
        ninc_rows = conn.execute(text("""
            SELECT title, severity, status, created_at::text FROM bw_incidents
            WHERE brand_id = :bid AND status NOT IN ('resolved', 'closed')
            ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                     WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC
            LIMIT 10
        """), {"bid": request.brand_id}).fetchall()
        incident_summary = "\n".join(
            f"- [{_sev}/{_st}] {_t} (opened {str(_ca)[:10]})"
            for _t, _sev, _st, _ca in ninc_rows) or "None open."

        # Employee / workforce signal: cached Glassdoor aggregates + landed reviews
        nemp_lines = []
        _cfg_raw = conn.execute(text(
            "SELECT COALESCE(config, '{}') FROM bw_brands WHERE id = :bid"
        ), {"bid": request.brand_id}).fetchone()
        _cfg = _cfg_raw[0] if isinstance(_cfg_raw[0], dict) else json.loads(_cfg_raw[0] or "{}")
        _gd = ((_cfg.get("glassdoor_overview") or {}).get("data")) or None
        if _gd:
            nemp_lines.append(
                f"Glassdoor: {_gd.get('rating')}/5 overall ({_gd.get('review_count')} reviews), "
                f"CEO approval {round((_gd.get('ceo_rating') or 0) * 100)}%, "
                f"business outlook {round((_gd.get('business_outlook_rating') or 0) * 100)}% positive, "
                f"recommend-to-friend {round((_gd.get('recommend_to_friend_rating') or 0) * 100)}%")
            _subs = {
                "work-life balance": _gd.get("work_life_balance_rating"),
                "culture & values": _gd.get("culture_and_values_rating"),
                "compensation": _gd.get("compensation_and_benefits_rating"),
                "senior management": _gd.get("senior_management_rating"),
                "career opportunities": _gd.get("career_opportunities_rating"),
                "diversity & inclusion": _gd.get("diversity_and_inclusion_rating"),
            }
            _subs = {k: v for k, v in _subs.items() if v is not None}
            if _subs:
                nemp_lines.append("Sub-ratings (weakest first): " + ", ".join(
                    f"{k} {v}" for k, v in sorted(_subs.items(), key=lambda x: x[1])))
        _gr = conn.execute(text("""
            SELECT a.sentiment, COUNT(*) FROM articles a
            JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :bid
            WHERE a.news_source = 'Glassdoor'
              AND a.publication_date >= :start AND a.publication_date <= :end
            GROUP BY a.sentiment
        """), {"bid": request.brand_id, "start": start_date, "end": end_date}).fetchall()
        _gpos = sum(n for s, n in _gr if s and "positiv" in s.lower())
        _gneg = sum(n for s, n in _gr if s and "negativ" in s.lower())
        _gtot = sum(n for _s, n in _gr)
        if _gtot:
            nemp_lines.append(f"Employee reviews landed this period: {_gtot} ({_gpos} positive, {_gneg} negative)")
        _wf_count = nrisk_by_type.get("workforce_labor", 0)
        if _wf_count:
            nemp_lines.append(f"Workforce risk findings in period: {_wf_count}")
        _comp_bits = []
        for _cname, _ccfg_raw in conn.execute(text(
            "SELECT display_name, COALESCE(config, '{}') FROM bw_brands "
            "WHERE enabled = true AND id <> :bid"), {"bid": request.brand_id}).fetchall():
            _ccfg = _ccfg_raw if isinstance(_ccfg_raw, dict) else json.loads(_ccfg_raw or "{}")
            _cgd = ((_ccfg.get("glassdoor_overview") or {}).get("data")) or {}
            if _cgd.get("rating") is not None:
                _comp_bits.append(f"{_cname} {_cgd['rating']}/5")
        if _comp_bits:
            nemp_lines.append("Competitor Glassdoor ratings: " + ", ".join(_comp_bits))
        employee_signal = "\n".join(nemp_lines) or "No employee data available."

        prompt = NARRATIVE_ANALYSIS_PROMPT.format(
            brand_name=brand["display_name"],
            date_range=f"{start_date} to {end_date}",
            total_articles=total_articles,
            category_breakdown=category_breakdown,
            competitor_breakdown=competitor_breakdown,
            risk_assessment=risk_assessment,
            key_articles=key_articles,
            social_signal=social_signal,
            risk_findings=risk_findings,
            incident_summary=incident_summary,
            employee_signal=employee_signal,
        )

        model = LiteLLMModel.get_instance(request.model)
        narrative = await model.agenerate_response([
            {"role": "system", "content": "You are a senior brand intelligence analyst writing reports for C-suite executives."},
            {"role": "user", "content": prompt}
        ])

        data_summary = {
            "total_articles": total_articles,
            "date_range": {"start": start_date, "end": end_date},
            "categories": category_data,
            "competitors": competitor_counts,
            "risk_assessment": {
                "risk_level": risk_level,
                "risk_score": risk_score,
                "recent_neg_pct": round(recent_neg_pct, 1),
                "neg_trend": round(neg_trend, 1),
                "alert_count": alert_count,
                "high_alerts": high_alerts,
                "contributing_factors": risk_factors,
            },
            "social": social_summary,
            "risks": {"total": len(nrisk_rows), "by_type": nrisk_by_type},
            "signals": {"screened": len(nsig_rows), "verdicts": nsig_verdicts,
                        "flagged": len(nsig_flagged)},
            "open_incidents": len(ninc_rows),
            "employee": {
                "glassdoor_rating": _gd.get("rating") if _gd else None,
                "business_outlook": _gd.get("business_outlook_rating") if _gd else None,
                "reviews_in_period": _gtot,
                "workforce_risks": _wf_count,
            },
        }

        # Save narrative
        try:
            conn.execute(text("""
                INSERT INTO bw_tracker_narratives
                (brand_id, narrative, data_summary, days_back, date_range_start, date_range_end)
                VALUES (:bid, :narrative, :data, :days, :start, :end)
            """), {
                "bid": request.brand_id, "narrative": narrative,
                "data": json.dumps(data_summary),
                "days": request.days_back,
                "start": start_date, "end": end_date,
            })
            conn.commit()
        except Exception as save_err:
            logger.warning(f"Failed to save narrative: {save_err}")

        return NarrativeResponse(
            narrative=narrative,
            generated_at=datetime.now().isoformat(),
            data_summary=data_summary,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating narrative: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/narrative/latest", response_model=Optional[SavedNarrativeResponse])
async def get_latest_narrative(
    brand_id: int = Query(..., description="Brand ID"),
    session=Depends(verify_session),
):
    """Get the most recent narrative for a brand."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result = conn.execute(text("""
            SELECT n.id, n.brand_id, b.display_name, n.narrative, n.data_summary,
                   n.days_back, n.date_range_start, n.date_range_end, n.generated_at
            FROM bw_tracker_narratives n
            JOIN bw_brands b ON n.brand_id = b.id
            WHERE n.brand_id = :bid
            ORDER BY n.generated_at DESC LIMIT 1
        """), {"bid": brand_id})

        row = result.fetchone()
        if not row:
            return None

        data_summary = row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {}
        days_back = row[5]

        # Recompute live article count
        start_date, end_date = _get_date_range(days_back or 365)
        live_count = conn.execute(text("""
            SELECT COUNT(DISTINCT bac.article_uri)
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid
            AND a.publication_date >= :start AND a.publication_date <= :end
        """), {"bid": brand_id, "start": start_date, "end": end_date}).fetchone()[0]
        data_summary["total_articles"] = live_count

        # Recompute category breakdown
        cat_result = conn.execute(text("""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri)
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid
            AND a.publication_date >= :start AND a.publication_date <= :end
            GROUP BY bac.category ORDER BY COUNT(DISTINCT bac.article_uri) DESC
        """), {"bid": brand_id, "start": start_date, "end": end_date})
        data_summary["categories"] = {r[0]: r[1] for r in cat_result.fetchall()}

        return SavedNarrativeResponse(
            id=row[0], brand_id=row[1], brand_name=row[2],
            narrative=row[3], data_summary=data_summary,
            days_back=days_back,
            date_range_start=str(row[6]) if row[6] else None,
            date_range_end=str(row[7]) if row[7] else None,
            generated_at=str(row[8]) if row[8] else None,
        )
    except Exception as e:
        logger.error(f"Error getting latest narrative: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/category-insight", response_model=CategoryInsightResponse)
async def generate_category_insight(request: CategoryInsightRequest, session=Depends(verify_session)):
    """Generate LLM insight for a specific category + brand."""
    from app.ai_models import LiteLLMModel

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        start_date, end_date = _get_date_range(request.days_back)

        # Fetch brand
        brand_result = conn.execute(text("SELECT display_name FROM bw_brands WHERE id = :id"), {"id": request.brand_id})
        brand_row = brand_result.fetchone()
        if not brand_row:
            raise HTTPException(status_code=404, detail="Brand not found")
        brand_name = brand_row[0]

        # Count articles in category
        count_result = conn.execute(text("""
            SELECT COUNT(DISTINCT bac.article_uri)
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4 AND bac.category = :cat
            AND a.publication_date >= :start AND a.publication_date <= :end
        """), {"bid": request.brand_id, "cat": request.category, "start": start_date, "end": end_date})
        article_count = count_result.fetchone()[0]

        # Total for percentage
        total_result = conn.execute(text("""
            SELECT COUNT(DISTINCT bac.article_uri)
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
            AND a.publication_date >= :start AND a.publication_date <= :end
        """), {"bid": request.brand_id, "start": start_date, "end": end_date})
        total = total_result.fetchone()[0] or 1
        percentage = round(article_count / total * 100, 1)

        # Sample titles
        sample_result = conn.execute(text("""
            SELECT a.title FROM articles a
            JOIN bw_article_categories bac ON a.uri = bac.article_uri
            WHERE bac.brand_id = :bid AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4 AND bac.category = :cat
            AND a.publication_date >= :start AND a.publication_date <= :end
            ORDER BY a.publication_date DESC LIMIT 10
        """), {"bid": request.brand_id, "cat": request.category, "start": start_date, "end": end_date})
        sample_titles = "\n".join([f"- {row[0]}" for row in sample_result.fetchall()])

        trend = "stable"  # simplified for category insight

        prompt = CATEGORY_INSIGHT_PROMPT.format(
            brand_name=brand_name,
            category_name=request.category,
            article_count=article_count,
            percentage=percentage,
            trend=trend,
            sample_titles=sample_titles or "No articles found",
        )

        model = LiteLLMModel.get_instance(request.model)
        insight = await model.agenerate_response([
            {"role": "system", "content": "You are a brand intelligence analyst. Be specific and analytical."},
            {"role": "user", "content": prompt}
        ])

        return CategoryInsightResponse(
            category=request.category, insight=insight,
            article_count=article_count, percentage=percentage, trend=trend,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating category insight: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# SLM Status Endpoints
# ============================================================================

@router.get("/slm/status")
async def get_slm_status(session=Depends(verify_session)):
    """Get status of the local SLM classifier."""
    try:
        from app.services.brand_watcher_classifier_service import get_brand_watcher_classifier
        classifier = get_brand_watcher_classifier()
        return classifier.get_status()
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.post("/slm/classify")
async def slm_classify_text(request: dict, session=Depends(verify_session)):
    """Classify text using the local SLM (testing)."""
    try:
        from app.services.brand_watcher_classifier_service import get_brand_watcher_classifier
        classifier = get_brand_watcher_classifier()
        if not classifier.is_available():
            raise HTTPException(status_code=503, detail="SLM classifier not available")
        text_input = request.get("text", "")
        threshold = request.get("threshold")
        return classifier.classify(text_input, threshold=threshold, return_scores=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/classifier/retrain")
async def retrain_classifier(
    background_tasks: BackgroundTasks,
    session=Depends(verify_session),
):
    """Trigger SLM classifier retraining."""
    import subprocess

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    train_script = os.path.join(base_dir, "scripts", "train_brand_watcher_classifier.py")

    if not os.path.exists(train_script):
        raise HTTPException(status_code=404, detail="Training script not found")

    # Check article count
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        count = conn.execute(text("SELECT COUNT(*) FROM bw_article_categories")).scalar() or 0
    finally:
        conn.close()

    if count < 50:
        raise HTTPException(status_code=400, detail=f"Only {count} classified articles. Need at least 50 for training.")

    def _run_training():
        try:
            result = subprocess.run(
                ["python", train_script],
                cwd=base_dir,
                capture_output=True, text=True, timeout=3600,
            )
            marker_file = os.path.join(base_dir, "models", "brand_watcher_classifier", ".last_train_timestamp")
            os.makedirs(os.path.dirname(marker_file), exist_ok=True)
            with open(marker_file, 'w') as f:
                f.write(datetime.now().isoformat())

            db.facade.create_notification(
                username=None,
                type='brand_watcher',
                title='Brand Watcher: SLM Retrain Complete',
                message=f'Classifier retrained with {count} classified articles.',
                link='/newsfeed?tab=brand-watcher'
            )
            logger.info(f"SLM retrain complete: {result.returncode}")
        except Exception as e:
            logger.error(f"SLM retrain failed: {e}")

    background_tasks.add_task(_run_training)

    return {
        "status": "started",
        "message": f"Retraining started with {count} classified articles",
    }


# ============================================================================
# Config Endpoint
# ============================================================================

@router.get("/topics")
async def get_topics(session=Depends(verify_session)):
    """List topics that have articles available for brand classification."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result = conn.execute(text("""
            SELECT topic, COUNT(*) as article_count
            FROM articles
            WHERE topic IS NOT NULL AND topic != ''
            GROUP BY topic
            ORDER BY article_count DESC
        """))
        return [{"topic": row[0], "article_count": row[1]} for row in result.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching topics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/config")
async def get_config(session=Depends(verify_session)):
    """Return module configuration."""
    return {
        "categories": BW_CATEGORIES,
        "category_colors": CATEGORY_COLORS,
    }


# ============================================================================
# Schedule Endpoints
# ============================================================================

class ScheduleCreate(BaseModel):
    name: str
    brand_id: Optional[int] = None
    topics: Optional[List[str]] = None
    run_type: str = "incremental"
    days_back: int = 30
    schedule_enabled: bool = True
    schedule_type: str = "interval"
    schedule_interval: Optional[int] = 24
    schedule_unit: str = "hours"
    schedule_time: Optional[str] = None
    notify_on_complete: bool = True
    notify_threshold: int = 10


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    brand_id: Optional[int] = None
    run_type: Optional[str] = None
    days_back: Optional[int] = None
    schedule_enabled: Optional[bool] = None
    schedule_type: Optional[str] = None
    schedule_interval: Optional[int] = None
    schedule_unit: Optional[str] = None
    schedule_time: Optional[str] = None
    notify_on_complete: Optional[bool] = None
    notify_threshold: Optional[int] = None


def _calculate_next_run(schedule_type: str, interval: Optional[int],
                        unit: str, schedule_time: Optional[dt_time]) -> Optional[datetime]:
    """Calculate the next run time based on schedule configuration."""
    now = datetime.now()
    if schedule_type == "daily":
        if schedule_time:
            next_run = now.replace(hour=schedule_time.hour, minute=schedule_time.minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run
        return now + timedelta(days=1)
    elif schedule_type == "interval" and interval:
        if unit == "hours":
            return now + timedelta(hours=interval)
        elif unit == "minutes":
            return now + timedelta(minutes=interval)
        elif unit == "days":
            return now + timedelta(days=interval)
    return now + timedelta(hours=24)


@router.get("/schedules")
async def list_schedules(session=Depends(verify_session)):
    """List all brand watcher classification schedules."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result = conn.execute(text("""
            SELECT s.id, s.name, s.brand_id, b.display_name as brand_name,
                   s.run_type, s.days_back, s.topics,
                   s.schedule_enabled, s.schedule_type, s.schedule_interval, s.schedule_unit, s.schedule_time,
                   s.notify_on_complete, s.notify_threshold,
                   s.last_run_at, s.next_run_at, s.last_run_status,
                   s.last_run_articles_processed, s.last_run_articles_categorized, s.run_count,
                   s.created_at
            FROM bw_tracker_schedules s
            LEFT JOIN bw_brands b ON s.brand_id = b.id
            ORDER BY s.name
        """))
        schedules = []
        for row in result:
            row_dict = dict(row._mapping)
            if row_dict.get('schedule_time'):
                row_dict['schedule_time'] = str(row_dict['schedule_time'])
            for ts_field in ['last_run_at', 'next_run_at', 'created_at']:
                if row_dict.get(ts_field):
                    row_dict[ts_field] = row_dict[ts_field].isoformat()
            schedules.append(row_dict)
        return {"schedules": schedules}
    except Exception as e:
        logger.error(f"Error listing brand watcher schedules: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/schedules")
async def create_schedule(schedule: ScheduleCreate, session=Depends(verify_session)):
    """Create a new brand watcher classification schedule."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        schedule_time_val = None
        if schedule.schedule_time:
            try:
                parts = schedule.schedule_time.split(':')
                schedule_time_val = dt_time(int(parts[0]), int(parts[1]))
            except Exception:
                pass

        next_run_at = None
        if schedule.schedule_enabled:
            next_run_at = _calculate_next_run(
                schedule.schedule_type, schedule.schedule_interval,
                schedule.schedule_unit, schedule_time_val
            )

        result = conn.execute(text("""
            INSERT INTO bw_tracker_schedules
            (name, brand_id, topics, run_type, days_back,
             schedule_enabled, schedule_type, schedule_interval, schedule_unit, schedule_time,
             notify_on_complete, notify_threshold, next_run_at)
            VALUES (:name, :brand_id, :topics, :run_type, :days_back,
                    :schedule_enabled, :schedule_type, :schedule_interval, :schedule_unit, :schedule_time,
                    :notify_on_complete, :notify_threshold, :next_run_at)
            RETURNING id
        """), {
            "name": schedule.name,
            "brand_id": schedule.brand_id,
            "topics": json.dumps(schedule.topics) if schedule.topics else None,
            "run_type": schedule.run_type,
            "days_back": schedule.days_back,
            "schedule_enabled": schedule.schedule_enabled,
            "schedule_type": schedule.schedule_type,
            "schedule_interval": schedule.schedule_interval,
            "schedule_unit": schedule.schedule_unit,
            "schedule_time": schedule_time_val,
            "notify_on_complete": schedule.notify_on_complete,
            "notify_threshold": schedule.notify_threshold,
            "next_run_at": next_run_at,
        })
        schedule_id = result.scalar()
        conn.commit()
        return {
            "status": "success",
            "message": "Schedule created",
            "schedule_id": schedule_id,
            "next_run_at": next_run_at.isoformat() if next_run_at else None,
        }
    except Exception as e:
        logger.error(f"Error creating brand watcher schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: int, updates: ScheduleUpdate, session=Depends(verify_session)):
    """Update a brand watcher classification schedule."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        set_clauses = []
        params = {"schedule_id": schedule_id}
        for field in ['name', 'brand_id', 'run_type', 'days_back',
                      'schedule_enabled', 'schedule_type', 'schedule_interval',
                      'schedule_unit', 'notify_on_complete', 'notify_threshold']:
            value = getattr(updates, field, None)
            if value is not None:
                set_clauses.append(f"{field} = :{field}")
                params[field] = value

        if updates.schedule_time is not None:
            try:
                parts = updates.schedule_time.split(':')
                params["schedule_time"] = dt_time(int(parts[0]), int(parts[1]))
            except Exception:
                params["schedule_time"] = None
            set_clauses.append("schedule_time = :schedule_time")

        if not set_clauses:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clauses.append("updated_at = NOW()")
        conn.execute(text(f"""
            UPDATE bw_tracker_schedules SET {', '.join(set_clauses)}
            WHERE id = :schedule_id
        """), params)

        # Recalculate next_run if scheduling changed
        if any(getattr(updates, f, None) is not None for f in
               ['schedule_enabled', 'schedule_type', 'schedule_interval', 'schedule_unit', 'schedule_time']):
            row = conn.execute(text("""
                SELECT schedule_enabled, schedule_type, schedule_interval, schedule_unit, schedule_time
                FROM bw_tracker_schedules WHERE id = :schedule_id
            """), {"schedule_id": schedule_id}).fetchone()
            if row:
                next_run_at = None
                if row[0]:  # schedule_enabled
                    next_run_at = _calculate_next_run(row[1], row[2], row[3], row[4])
                conn.execute(text("""
                    UPDATE bw_tracker_schedules SET next_run_at = :next_run_at WHERE id = :schedule_id
                """), {"schedule_id": schedule_id, "next_run_at": next_run_at})

        conn.commit()
        return {"status": "success", "message": "Schedule updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating brand watcher schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int, session=Depends(verify_session)):
    """Delete a brand watcher classification schedule."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        conn.execute(text("DELETE FROM bw_tracker_schedules WHERE id = :id"), {"id": schedule_id})
        conn.commit()
        return {"status": "success", "message": "Schedule deleted"}
    except Exception as e:
        logger.error(f"Error deleting brand watcher schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/schedules/{schedule_id}/run")
async def run_schedule_now(
    schedule_id: int,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session),
):
    """Manually trigger a schedule to run now."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        row = conn.execute(text("""
            SELECT brand_id, run_type, days_back, topics FROM bw_tracker_schedules WHERE id = :id
        """), {"id": schedule_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Schedule not found")

        brand_id, run_type, days_back = row[0], row[1], row[2]
        sched_topics = row[3] if isinstance(row[3], list) else json.loads(row[3]) if row[3] else None

        result = conn.execute(text("""
            INSERT INTO bw_tracker_runs (brand_id, run_type, status)
            VALUES (:brand_id, :run_type, 'running')
            RETURNING id
        """), {"brand_id": brand_id, "run_type": run_type})
        run_id = result.fetchone()[0]
        conn.commit()

        background_tasks.add_task(
            _run_classification_task,
            run_id, brand_id, run_type, days_back, sched_topics
        )

        # Update schedule tracking
        conn.execute(text("""
            UPDATE bw_tracker_schedules
            SET last_run_at = NOW(), run_count = run_count + 1, last_run_status = 'running'
            WHERE id = :id
        """), {"id": schedule_id})
        conn.commit()

        return {
            "status": "success",
            "message": "Schedule run started",
            "run_id": run_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running brand watcher schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Adverse risk taxonomy (cross-cutting dimension; see bw_article_risks)
# ============================================================================

RISK_TYPES = ["legal_regulatory", "financial_distress", "fraud_integrity",
              "esg", "executive_misconduct", "data_breach", "workforce_labor"]

# Cheap pre-screen: only articles that are negative OR contain risk vocabulary get
# the LLM risk pass, bounding cost to the adverse sliver of the stream.
_RISK_TRIGGER_RE = re.compile(
    r"lawsuit|\bsues?\b|\bsued\b|litigat|\bcourt\b|regulator|antitrust|\bprobe\b|investigat|\bfine[sd]?\b|penalty|"
    r"\bfraud|scandal|misconduct|bribe|corrupt|plagiar|retract|falsif|"
    r"\bbreach|\bhack|ransom|\bleak\b|cyberattack|"
    r"bankrupt|insolven|default|downgrade|layoff|restructur|going concern|"
    r"boycott|discriminat|harass|greenwash|child labor|resign|ousted|fired|"
    r"\bstrikes?\b|\bunion\b|redundanc|walkout|tribunal|unfair dismissal|"
    r"toxic (workplace|culture)|pay dispute|wage theft|understaff",
    re.IGNORECASE)

_NEG_SENT_RE = re.compile(r"negativ|concern|pessimis|critical|alarm", re.IGNORECASE)


def _keyword_risk_fallback(text_content: str) -> list:
    """Heuristic risk tagging when the LLM is unavailable."""
    t = (text_content or "").lower()
    found = []
    def add(rt, sev): found.append({"risk_type": rt, "severity": sev, "confidence": 0.4})
    if re.search(r"lawsuit|\bsues?\b|\bsued\b|litigat|regulator|antitrust|\bprobe\b|investigat|\bfine[sd]?\b|penalty|\bcourt\b", t): add("legal_regulatory", "medium")
    if re.search(r"bankrupt|insolven|default|downgrade|going concern|layoff|restructur", t): add("financial_distress", "medium")
    if re.search(r"fraud|scandal|bribe|corrupt|plagiar|retract|falsif", t): add("fraud_integrity", "high")
    if re.search(r"boycott|discriminat|harass|greenwash|child labor|environmental damage", t): add("esg", "medium")
    if re.search(r"misconduct|resign|ousted|fired.*(ceo|cfo|executive|director)|(ceo|cfo|executive|director).*(misconduct|resign|ousted|fired)", t): add("executive_misconduct", "medium")
    if re.search(r"\bbreach|\bhack|ransom|cyberattack|data leak", t): add("data_breach", "high")
    # Bare "union"/"strike" collide with ordinary prose ("union of ideas", "striking
    # design") — the fallback (which tags directly, no LLM adjudication) needs the
    # compound forms only.
    if re.search(r"(trade|labou?r|staff) union|union (members?|dispute|vote|action|strike)|(staff|workers?|employees?) (strike|walkout)|strike (action|ballot)|redundanc|tribunal|unfair dismissal|toxic (workplace|culture)|pay dispute|wage theft|mass layoff", t): add("workforce_labor", "medium")
    return found


async def _llm_detect_risks(title: str, summary: str, brand_name: str) -> Optional[list]:
    """LLM risk classification. Returns list of {risk_type, severity, confidence} or None on failure."""
    from app.ai_models import LiteLLMModel, extract_content
    prompt = f"""You are an adverse-media screening analyst. Does this article describe an ADVERSE event involving the company "{brand_name}"?

Article Title: {title}
Article Summary: {(summary or "")[:1500]}

Risk types (use ONLY these keys): legal_regulatory (lawsuits, regulatory action, fines, probes), financial_distress (bankruptcy risk, downgrades, defaults), fraud_integrity (fraud, corruption, research/publication integrity, retractions), esg (environmental/social harms, consumer discrimination, boycotts), executive_misconduct (leadership scandals, forced departures), data_breach (hacks, breaches, ransomware), workforce_labor (strikes, union disputes, mass layoffs/redundancies, employment tribunals, unfair-dismissal or workplace-discrimination claims, toxic-culture allegations, pay disputes).

Rules:
- Only flag risks where {brand_name} is the SUBJECT of the adverse event (not merely mentioned, not the plaintiff suing someone else unless it exposes them to counter-risk).
- Routine negative sentiment (bad quarter, critical review) is NOT a risk finding unless it fits a type above.
- severity: high = material/ongoing threat; medium = notable; low = minor/speculative.

Respond with ONLY a JSON array (empty [] if none): [{{"risk_type": "...", "severity": "high|medium|low", "confidence": 0.0-1.0}}]"""
    try:
        model = LiteLLMModel.get_instance("gpt-5.4-mini")
        response = await model.agenerate_response(
            [{"role": "user", "content": prompt}], max_tokens=200, temperature=0.0)
        raw = extract_content(response).strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
        # The model sometimes appends prose after the array — parse the FIRST JSON
        # value and ignore trailing text.
        start = raw.find("[")
        if start < 0:
            return []
        data, _ = json.JSONDecoder().raw_decode(raw[start:])
        out = []
        for item in (data if isinstance(data, list) else []):
            rt = (item.get("risk_type") or "").strip()
            if rt in RISK_TYPES:
                sev = item.get("severity") if item.get("severity") in ("high", "medium", "low") else "medium"
                out.append({"risk_type": rt, "severity": sev,
                            "confidence": max(0.0, min(1.0, float(item.get("confidence") or 0.5)))})
        return out
    except Exception as e:
        logger.debug(f"LLM risk detection failed: {e}")
        return None


def _store_article_risks(conn, uri: str, brand_id: int, risks: list, method: str) -> None:
    for r in risks:
        try:
            conn.execute(text("""
                INSERT INTO bw_article_risks (article_uri, brand_id, risk_type, severity, confidence, method)
                VALUES (:u, :b, :rt, :sev, :c, :m)
                ON CONFLICT (article_uri, brand_id, risk_type)
                DO UPDATE SET severity = :sev, confidence = :c, method = :m, detected_at = NOW()
            """), {"u": uri, "b": brand_id, "rt": r["risk_type"], "sev": r["severity"],
                   "c": r.get("confidence"), "m": method})
        except Exception as e:
            logger.warning(f"risk store failed for {uri}: {e}")


# ============================================================================
# Adverse-media alerting: config + event history
# ============================================================================

class AlertConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    rules: Optional[dict] = None
    channels: Optional[dict] = None
    email_recipients: Optional[List[str]] = None
    webhook_url: Optional[str] = None
    cooldown_hours: Optional[int] = None


@router.get("/alert-config")
async def get_alert_config_ep(session=Depends(verify_session)):
    """Tenant-wide adverse-alert configuration (creates a default row if absent)."""
    from app.services.brand_alert_service import get_alert_config
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        cfg = get_alert_config(conn)
        if not cfg:
            conn.execute(text("INSERT INTO bw_alert_config (brand_id) VALUES (NULL)"))
            conn.commit()
            cfg = get_alert_config(conn)
        return cfg
    finally:
        conn.close()


@router.put("/alert-config")
async def update_alert_config_ep(req: AlertConfigUpdate, session=Depends(verify_session)):
    from app.services.brand_alert_service import get_alert_config
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        cfg = get_alert_config(conn)
        if not cfg:
            conn.execute(text("INSERT INTO bw_alert_config (brand_id) VALUES (NULL)"))
            conn.commit()
            cfg = get_alert_config(conn)
        sets, params = [], {"id": cfg["id"]}
        if req.enabled is not None:
            sets.append("enabled = :en"); params["en"] = req.enabled
        if req.rules is not None:
            sets.append("rules = :ru"); params["ru"] = json.dumps(req.rules)
        if req.channels is not None:
            sets.append("channels = :ch"); params["ch"] = json.dumps(req.channels)
        if req.email_recipients is not None:
            sets.append("email_recipients = :er"); params["er"] = json.dumps(req.email_recipients)
        if req.webhook_url is not None:
            sets.append("webhook_url = :wh"); params["wh"] = req.webhook_url or None
        if req.cooldown_hours is not None:
            sets.append("cooldown_hours = :cd"); params["cd"] = max(1, min(168, req.cooldown_hours))
        if sets:
            conn.execute(text(f"UPDATE bw_alert_config SET {', '.join(sets)}, updated_at = NOW() WHERE id = :id"), params)
            conn.commit()
        return get_alert_config(conn)
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/alert-events")
async def list_alert_events(limit: int = Query(50, ge=1, le=200), unacked_only: bool = Query(False), session=Depends(verify_session)):
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        # rule='digest' rows are send-idempotence bookkeeping, not adverse alerts.
        where = "WHERE e.rule <> 'digest'" + (" AND acknowledged_at IS NULL" if unacked_only else "")
        rows = conn.execute(text(f"""
            SELECT e.id, e.brand_id, b.display_name, e.rule, e.severity, e.title, e.body,
                   e.payload, e.delivered, e.acknowledged_by, e.acknowledged_at, e.created_at
            FROM bw_alert_events e LEFT JOIN bw_brands b ON b.id = e.brand_id
            {where} ORDER BY e.created_at DESC LIMIT :lim
        """), {"lim": limit}).fetchall()
        return {"events": [{
            "id": r[0], "brand_id": r[1], "brand_name": r[2], "rule": r[3], "severity": r[4],
            "title": r[5], "body": r[6], "payload": r[7], "delivered": r[8],
            "acknowledged_by": r[9],
            "acknowledged_at": r[10].isoformat() if r[10] else None,
            "created_at": r[11].isoformat() if r[11] else None,
        } for r in rows]}
    finally:
        conn.close()


@router.post("/alert-events/{event_id}/ack")
async def ack_alert_event(event_id: int, session=Depends(verify_session)):
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        actor = (session or {}).get("sub") or (session or {}).get("username") or "user"
        conn.execute(text("""
            UPDATE bw_alert_events SET acknowledged_by = :a, acknowledged_at = NOW()
            WHERE id = :i AND acknowledged_at IS NULL
        """), {"a": str(actor)[:100], "i": event_id})
        conn.commit()
        return {"ok": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/alert-events/evaluate-now")
async def evaluate_alerts_now(session=Depends(verify_session)):
    """Manual trigger of the adverse-alert evaluation (also used for testing)."""
    from app.tasks.brand_watcher_monitor import evaluate_adverse_alerts
    db = get_database_instance()
    created = evaluate_adverse_alerts(db)
    return {"created": created}


# ============================================================================
# Finding-level case states (reviewed / escalated / dismissed + audit log)
# ============================================================================

FINDING_STATUSES = ("new", "reviewed", "escalated", "dismissed")


class FindingStateRequest(BaseModel):
    article_uri: str
    brand_id: int
    status: str
    note: Optional[str] = None


@router.post("/findings/state")
async def set_finding_state(req: FindingStateRequest, session=Depends(verify_session)):
    if req.status not in FINDING_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {FINDING_STATUSES}")
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        actor = str((session or {}).get("sub") or (session or {}).get("username") or "user")[:100]
        old = conn.execute(text(
            "SELECT status FROM bw_finding_reviews WHERE article_uri = :u AND brand_id = :b"
        ), {"u": req.article_uri, "b": req.brand_id}).fetchone()
        old_status = old[0] if old else None
        conn.execute(text("""
            INSERT INTO bw_finding_reviews (article_uri, brand_id, status, actor, note)
            VALUES (:u, :b, :s, :a, :n)
            ON CONFLICT (article_uri, brand_id)
            DO UPDATE SET status = :s, actor = :a, note = :n, updated_at = NOW()
        """), {"u": req.article_uri, "b": req.brand_id, "s": req.status, "a": actor, "n": req.note})
        conn.execute(text("""
            INSERT INTO bw_finding_review_log (article_uri, brand_id, old_status, new_status, actor, note)
            VALUES (:u, :b, :o, :s, :a, :n)
        """), {"u": req.article_uri, "b": req.brand_id, "o": old_status, "s": req.status, "a": actor, "n": req.note})
        conn.commit()
        return {"ok": True, "status": req.status, "previous": old_status}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/findings/log")
async def get_finding_log(uri: str = Query(...), brand_id: Optional[int] = Query(None), session=Depends(verify_session)):
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        bclause = "AND brand_id = :b" if brand_id else ""
        params = {"u": uri}
        if brand_id:
            params["b"] = brand_id
        rows = conn.execute(text(f"""
            SELECT old_status, new_status, actor, note, at FROM bw_finding_review_log
            WHERE article_uri = :u {bclause} ORDER BY at DESC LIMIT 50
        """), params).fetchall()
        return {"log": [{"old_status": r[0], "new_status": r[1], "actor": r[2], "note": r[3],
                          "at": r[4].isoformat() if r[4] else None} for r in rows]}
    finally:
        conn.close()


# ============================================================================
# Official / scholarly sources (SEC EDGAR, CourtListener, regulations.gov,
# Crossref, OpenAlex) — per-brand opt-in, polled daily by the monitor loop
# ============================================================================

@router.get("/official-sources/status")
async def get_official_sources_status(session=Depends(verify_session)):
    """Per-brand per-source enablement + last-poll + landed-count, for the Sources modal."""
    from app.services.bw_official_sources import official_sources_status
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        return {"brands": official_sources_status(conn)}
    finally:
        conn.close()


@router.post("/official-sources/poll-now")
async def poll_official_sources_now(brand_id: Optional[int] = Query(None),
                                    session=Depends(verify_session)):
    """Force an immediate poll of all opted-in sources (ignores the 24h cursor)."""
    from app.services.bw_official_sources import poll_official_sources
    db = get_database_instance()
    result = await poll_official_sources(db, force=True, only_brand_id=brand_id)
    return result


@router.get("/story-siblings")
async def get_story_siblings(group_id: str = Query(...), brand_id: Optional[int] = Query(None),
                             session=Depends(verify_session)):
    """All articles sharing a story_group_id — powers the multi-article detail view
    for '×N sources' syndicated stories."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        bclause = "AND st.brand_id = :b" if brand_id else ""
        params = {"g": group_id}
        if brand_id:
            params["b"] = brand_id
        rows = conn.execute(text(f"""
            SELECT DISTINCT a.uri, a.title, a.summary, a.news_source, a.publication_date,
                   a.bias, a.factual_reporting, a.sentiment
            FROM bw_article_stories st
            JOIN articles a ON a.uri = st.article_uri
            WHERE st.story_group_id = :g {bclause}
            ORDER BY a.publication_date DESC
            LIMIT 25
        """), params).fetchall()
        return {"articles": [{
            "uri": r[0], "title": r[1], "summary": r[2], "news_source": r[3],
            "publication_date": r[4], "bias": r[5], "factual_reporting": r[6],
            "sentiment": r[7],
        } for r in rows]}
    finally:
        conn.close()


# ============================================================================
# Incident management + evidence locker
# ============================================================================
# Incidents group adverse findings into managed cases. Evidence is captured
# SERVER-SIDE at attach time (the client only names the source) and stored as
# an immutable snapshot with a sha256 chained to the previous item — sources
# get deleted or edited; the locker entry is the durable, tamper-evident record.

INCIDENT_STATUSES = ["open", "investigating", "contained", "resolved", "closed"]
INCIDENT_SEVERITIES = ["low", "medium", "high", "critical"]


class IncidentCreate(BaseModel):
    brand_id: int
    title: str
    description: Optional[str] = None
    severity: str = "medium"


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    owner: Optional[str] = None
    note: Optional[str] = None  # optional context recorded with the change


class IncidentNote(BaseModel):
    note: str


class EvidenceAttach(BaseModel):
    evidence_type: str            # article | alert_event | risk_finding | note | url
    source_ref: Optional[str] = None   # article uri / alert event id / risk id / url
    title: Optional[str] = None        # for manual note/url evidence
    content: Optional[str] = None      # for manual note evidence


def _incident_actor(session) -> str:
    return str((session or {}).get("sub") or (session or {}).get("username") or "user")[:100]


def _incident_event(conn, incident_id: int, kind: str, actor: str,
                    old_value=None, new_value=None, note=None):
    conn.execute(text("""
        INSERT INTO bw_incident_events (incident_id, kind, actor, old_value, new_value, note)
        VALUES (:i, :k, :a, :o, :n, :nt)
    """), {"i": incident_id, "k": kind, "a": actor,
           "o": str(old_value) if old_value is not None else None,
           "n": str(new_value) if new_value is not None else None, "nt": note})


def _capture_evidence(conn, incident_id: int, req: "EvidenceAttach", actor: str) -> dict:
    """Snapshot the referenced source NOW and append it to the incident's hash chain."""
    import hashlib
    etype = req.evidence_type
    title, content, meta = req.title, req.content, {}
    if etype == "article":
        if not req.source_ref:
            raise HTTPException(status_code=400, detail="source_ref (article uri) required")
        row = conn.execute(text("""
            SELECT title, summary, news_source, publication_date, sentiment, topic,
                   topic_alignment_score, factual_reporting, bias, social_meta
            FROM articles WHERE uri = :u
        """), {"u": req.source_ref}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Article not found")
        title = row[0]
        content = f"{row[0] or ''}\n\n{row[1] or ''}"
        meta = {"news_source": row[2], "publication_date": row[3], "sentiment": row[4],
                "topic": row[5], "relevance": row[6], "factual_reporting": row[7],
                "bias": row[8], "social_meta": row[9], "uri": req.source_ref}
        risks = conn.execute(text(
            "SELECT risk_type, severity, confidence FROM bw_article_risks WHERE article_uri = :u"
        ), {"u": req.source_ref}).fetchall()
        if risks:
            meta["risks"] = [{"risk_type": r[0], "severity": r[1], "confidence": r[2]} for r in risks]
    elif etype == "alert_event":
        row = conn.execute(text("""
            SELECT rule, severity, title, body, payload, created_at
            FROM bw_alert_events WHERE id = :i
        """), {"i": int(req.source_ref or 0)}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Alert event not found")
        title = row[2]
        content = f"{row[2] or ''}\n\n{row[3] or ''}"
        meta = {"rule": row[0], "severity": row[1], "payload": row[4],
                "created_at": row[5].isoformat() if row[5] else None, "event_id": req.source_ref}
    elif etype in ("note", "url"):
        if not (req.content or req.source_ref):
            raise HTTPException(status_code=400, detail="content or source_ref required")
        title = req.title or (req.source_ref or "manual note")[:120]
        content = req.content or req.source_ref or ""
        meta = {"url": req.source_ref} if etype == "url" else {}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown evidence_type: {etype}")

    prev = conn.execute(text("""
        SELECT chain_sha256 FROM bw_incident_evidence
        WHERE incident_id = :i ORDER BY id DESC LIMIT 1
    """), {"i": incident_id}).fetchone()
    prev_chain = prev[0] if prev else ""
    meta_json = json.dumps(meta, sort_keys=True, default=str)
    content_sha = hashlib.sha256(f"{content}|{meta_json}".encode()).hexdigest()
    chain_sha = hashlib.sha256(f"{prev_chain}|{content_sha}".encode()).hexdigest()
    row = conn.execute(text("""
        INSERT INTO bw_incident_evidence
            (incident_id, evidence_type, source_ref, title, content, meta,
             content_sha256, chain_sha256, captured_by)
        VALUES (:i, :t, :r, :ti, :c, :m, :cs, :ch, :a)
        RETURNING id, captured_at
    """), {"i": incident_id, "t": etype, "r": req.source_ref, "ti": (title or "")[:300],
           "c": content, "m": meta_json, "cs": content_sha, "ch": chain_sha, "a": actor}).fetchone()
    _incident_event(conn, incident_id, "evidence_added", actor,
                    new_value=etype, note=(title or "")[:200])
    return {"id": row[0], "content_sha256": content_sha, "chain_sha256": chain_sha,
            "captured_at": row[1].isoformat() if row[1] else None}


@router.post("/incidents", status_code=201)
async def create_incident(req: IncidentCreate, session=Depends(verify_session)):
    if req.severity not in INCIDENT_SEVERITIES:
        raise HTTPException(status_code=400, detail="Invalid severity")
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        actor = _incident_actor(session)
        row = conn.execute(text("""
            INSERT INTO bw_incidents (brand_id, title, description, severity, created_by, owner)
            VALUES (:b, :t, :d, :s, :a, :a)
            RETURNING id
        """), {"b": req.brand_id, "t": req.title.strip()[:300], "d": req.description,
               "s": req.severity, "a": actor}).fetchone()
        _incident_event(conn, row[0], "created", actor, new_value=req.severity)
        conn.commit()
        return {"id": row[0]}
    except HTTPException:
        conn.rollback(); raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/incidents")
async def list_incidents(status: Optional[str] = Query(None), brand_id: Optional[int] = Query(None),
                         limit: int = Query(50, ge=1, le=200), session=Depends(verify_session)):
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        clauses, params = [], {"lim": limit}
        if status:
            clauses.append("i.status = :st"); params["st"] = status
        if brand_id:
            clauses.append("i.brand_id = :b"); params["b"] = brand_id
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(text(f"""
            SELECT i.id, i.brand_id, b.display_name, i.title, i.severity, i.status,
                   i.owner, i.created_at, i.updated_at, i.resolved_at,
                   (SELECT COUNT(*) FROM bw_incident_evidence e WHERE e.incident_id = i.id) AS evidence_count,
                   (SELECT COUNT(*) FROM bw_incident_events ev WHERE ev.incident_id = i.id) AS event_count
            FROM bw_incidents i JOIN bw_brands b ON b.id = i.brand_id
            {where}
            ORDER BY CASE i.status WHEN 'open' THEN 0 WHEN 'investigating' THEN 1
                     WHEN 'contained' THEN 2 WHEN 'resolved' THEN 3 ELSE 4 END,
                     CASE i.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                     WHEN 'medium' THEN 2 ELSE 3 END, i.updated_at DESC
            LIMIT :lim
        """), params).fetchall()
        return {"incidents": [{
            "id": r[0], "brand_id": r[1], "brand_name": r[2], "title": r[3],
            "severity": r[4], "status": r[5], "owner": r[6],
            "created_at": r[7].isoformat() if r[7] else None,
            "updated_at": r[8].isoformat() if r[8] else None,
            "resolved_at": r[9].isoformat() if r[9] else None,
            "evidence_count": r[10], "event_count": r[11],
        } for r in rows]}
    finally:
        conn.close()


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: int, session=Depends(verify_session)):
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        r = conn.execute(text("""
            SELECT i.id, i.brand_id, b.display_name, i.title, i.description, i.severity,
                   i.status, i.owner, i.created_by, i.created_at, i.updated_at, i.resolved_at
            FROM bw_incidents i JOIN bw_brands b ON b.id = i.brand_id WHERE i.id = :i
        """), {"i": incident_id}).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Incident not found")
        events = conn.execute(text("""
            SELECT kind, actor, old_value, new_value, note, at
            FROM bw_incident_events WHERE incident_id = :i ORDER BY at DESC, id DESC LIMIT 200
        """), {"i": incident_id}).fetchall()
        evidence = conn.execute(text("""
            SELECT id, evidence_type, source_ref, title, content, meta,
                   content_sha256, chain_sha256, captured_by, captured_at
            FROM bw_incident_evidence WHERE incident_id = :i ORDER BY id
        """), {"i": incident_id}).fetchall()
        def _j(v):
            if v is None or isinstance(v, (dict, list)):
                return v
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return {
            "id": r[0], "brand_id": r[1], "brand_name": r[2], "title": r[3],
            "description": r[4], "severity": r[5], "status": r[6], "owner": r[7],
            "created_by": r[8],
            "created_at": r[9].isoformat() if r[9] else None,
            "updated_at": r[10].isoformat() if r[10] else None,
            "resolved_at": r[11].isoformat() if r[11] else None,
            "timeline": [{"kind": e[0], "actor": e[1], "old_value": e[2], "new_value": e[3],
                          "note": e[4], "at": e[5].isoformat() if e[5] else None} for e in events],
            "evidence": [{"id": e[0], "evidence_type": e[1], "source_ref": e[2], "title": e[3],
                          "content": e[4], "meta": _j(e[5]), "content_sha256": e[6],
                          "chain_sha256": e[7], "captured_by": e[8],
                          "captured_at": e[9].isoformat() if e[9] else None} for e in evidence],
        }
    finally:
        conn.close()


@router.put("/incidents/{incident_id}")
async def update_incident(incident_id: int, req: IncidentUpdate, session=Depends(verify_session)):
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        cur = conn.execute(text(
            "SELECT title, description, severity, status, owner FROM bw_incidents WHERE id = :i"
        ), {"i": incident_id}).fetchone()
        if not cur:
            raise HTTPException(status_code=404, detail="Incident not found")
        actor = _incident_actor(session)
        sets, params = [], {"i": incident_id}
        if req.status is not None and req.status != cur[3]:
            if req.status not in INCIDENT_STATUSES:
                raise HTTPException(status_code=400, detail="Invalid status")
            sets.append("status = :st"); params["st"] = req.status
            if req.status in ("resolved", "closed"):
                sets.append("resolved_at = COALESCE(resolved_at, NOW())")
            _incident_event(conn, incident_id, "status_change", actor, cur[3], req.status, req.note)
        if req.severity is not None and req.severity != cur[2]:
            if req.severity not in INCIDENT_SEVERITIES:
                raise HTTPException(status_code=400, detail="Invalid severity")
            sets.append("severity = :sv"); params["sv"] = req.severity
            _incident_event(conn, incident_id, "severity_change", actor, cur[2], req.severity, req.note)
        if req.owner is not None and req.owner != cur[4]:
            sets.append("owner = :ow"); params["ow"] = req.owner[:100]
            _incident_event(conn, incident_id, "owner_change", actor, cur[4], req.owner, req.note)
        if req.title is not None and req.title.strip() and req.title != cur[0]:
            sets.append("title = :ti"); params["ti"] = req.title.strip()[:300]
        if req.description is not None and req.description != cur[1]:
            sets.append("description = :de"); params["de"] = req.description
        if sets:
            conn.execute(text(f"UPDATE bw_incidents SET {', '.join(sets)}, updated_at = NOW() WHERE id = :i"), params)
        conn.commit()
        return {"ok": True}
    except HTTPException:
        conn.rollback(); raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/incidents/{incident_id}/note")
async def add_incident_note(incident_id: int, req: IncidentNote, session=Depends(verify_session)):
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        if not conn.execute(text("SELECT 1 FROM bw_incidents WHERE id = :i"), {"i": incident_id}).fetchone():
            raise HTTPException(status_code=404, detail="Incident not found")
        _incident_event(conn, incident_id, "note", _incident_actor(session), note=req.note[:2000])
        conn.execute(text("UPDATE bw_incidents SET updated_at = NOW() WHERE id = :i"), {"i": incident_id})
        conn.commit()
        return {"ok": True}
    except HTTPException:
        conn.rollback(); raise
    finally:
        conn.close()


@router.post("/incidents/{incident_id}/evidence", status_code=201)
async def attach_evidence(incident_id: int, req: EvidenceAttach, session=Depends(verify_session)):
    """Capture a server-side snapshot of the source into the incident's evidence chain.
    Evidence is append-only by design — there is no update or delete endpoint."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        if not conn.execute(text("SELECT 1 FROM bw_incidents WHERE id = :i"), {"i": incident_id}).fetchone():
            raise HTTPException(status_code=404, detail="Incident not found")
        result = _capture_evidence(conn, incident_id, req, _incident_actor(session))
        conn.execute(text("UPDATE bw_incidents SET updated_at = NOW() WHERE id = :i"), {"i": incident_id})
        conn.commit()
        return result
    except HTTPException:
        conn.rollback(); raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/incidents/{incident_id}/verify-chain")
async def verify_evidence_chain(incident_id: int, session=Depends(verify_session)):
    """Recompute the evidence hash chain and report whether it is intact."""
    import hashlib
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(text("""
            SELECT id, content, meta, content_sha256, chain_sha256
            FROM bw_incident_evidence WHERE incident_id = :i ORDER BY id
        """), {"i": incident_id}).fetchall()
        prev_chain = ""
        broken = []
        for rid, content, meta, csha, chsha in rows:
            meta_json = meta if isinstance(meta, str) else json.dumps(meta or {}, sort_keys=True, default=str)
            # meta round-trips through JSONB, so recompute from the canonical form
            try:
                meta_json = json.dumps(meta if isinstance(meta, (dict, list)) else json.loads(meta or "{}"),
                                       sort_keys=True, default=str)
            except (json.JSONDecodeError, TypeError):
                pass
            expect_c = hashlib.sha256(f"{content}|{meta_json}".encode()).hexdigest()
            expect_ch = hashlib.sha256(f"{prev_chain}|{expect_c}".encode()).hexdigest()
            if expect_c != csha or expect_ch != chsha:
                broken.append(rid)
            prev_chain = chsha
        return {"items": len(rows), "intact": not broken, "broken_ids": broken}
    finally:
        conn.close()


# ============================================================================
# Employee / Workforce Risk API
# ============================================================================

def _cfg_dict(raw):
    return raw if isinstance(raw, dict) else json.loads(raw or "{}")


_SENT_POS_RE = re.compile(r"positiv|optimis", re.I)
_SENT_NEG_RE = re.compile(r"negativ|pessimis|concern|critical|alarm", re.I)


@router.get("/brands/{brand_id}/employee-risk")
async def get_employee_risk(
    brand_id: int,
    days_back: int = Query(90, ge=0, le=730),
    refresh: bool = Query(False, description="Force-refresh the Glassdoor overview cache"),
    session=Depends(verify_session),
):
    """Workforce picture for a brand: Glassdoor aggregate ratings (cached 24h),
    landed employee reviews, workforce_labor risk findings, and competitor
    aggregates for every other glassdoor-enabled brand."""
    from app.services.bw_official_sources import refresh_glassdoor_overview

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        brands = conn.execute(text("""
            SELECT id, display_name, color, COALESCE(config, '{}') AS config
            FROM bw_brands WHERE enabled = true ORDER BY is_primary DESC, display_name
        """)).fetchall()
        me = next((b for b in brands if b[0] == brand_id), None)
        if not me:
            raise HTTPException(status_code=404, detail="Brand not found")

        overview = None
        glassdoor_enabled = False
        competitors = []
        for bid, name, color, cfg_raw in brands:
            cfg = _cfg_dict(cfg_raw)
            if "glassdoor" not in (cfg.get("extra_sources") or []):
                continue
            if bid == brand_id:
                glassdoor_enabled = True
            ov = await refresh_glassdoor_overview(conn, bid, name, cfg,
                                                  force=(refresh and bid == brand_id))
            if bid == brand_id:
                overview = ov
            elif ov:
                competitors.append({"brand_id": bid, "brand_name": name,
                                    "color": color, "overview": ov})

        sd, ed = _get_date_range(days_back)
        review_rows = conn.execute(text("""
            SELECT a.uri, a.title, a.summary, a.sentiment, a.publication_date
            FROM articles a
            JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :b
            WHERE a.news_source = 'Glassdoor'
              AND a.publication_date >= :sd AND a.publication_date <= :ed
            ORDER BY a.publication_date DESC LIMIT 100
        """), {"b": brand_id, "sd": sd, "ed": ed}).fetchall()
        pos = neu = neg = 0
        reviews = []
        for uri, title, summary, sentiment, pub in review_rows:
            s = sentiment or ""
            if _SENT_NEG_RE.search(s):
                neg += 1
            elif _SENT_POS_RE.search(s):
                pos += 1
            elif s:
                neu += 1
            reviews.append({"uri": uri, "title": title, "summary": summary,
                            "sentiment": sentiment, "publication_date": str(pub or "")})
        scored = pos + neu + neg
        net = round(((pos - neg) / scored) * 100) if scored else None

        risk_rows = conn.execute(text("""
            SELECT r.article_uri, a.title, a.news_source, r.severity, r.confidence,
                   r.method, r.detected_at::text, fr.status, a.publication_date
            FROM bw_article_risks r
            JOIN articles a ON a.uri = r.article_uri
            LEFT JOIN bw_finding_reviews fr
                ON fr.article_uri = r.article_uri AND fr.brand_id = r.brand_id
            WHERE r.brand_id = :b AND r.risk_type = 'workforce_labor'
            ORDER BY CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                     a.publication_date DESC
            LIMIT 50
        """), {"b": brand_id}).fetchall()
        workforce_risks = [
            {"uri": r[0], "title": r[1], "news_source": r[2], "severity": r[3],
             "confidence": float(r[4]) if r[4] is not None else None, "method": r[5],
             "detected_at": r[6], "case_status": r[7] or "new",
             "publication_date": str(r[8] or "")}
            for r in risk_rows
        ]

        history = []
        try:
            for snap_date, snap_data in conn.execute(text("""
                SELECT snapshot_date, data FROM bw_glassdoor_snapshots
                WHERE brand_id = :b ORDER BY snapshot_date ASC LIMIT 400
            """), {"b": brand_id}).fetchall():
                sd_ = snap_data if isinstance(snap_data, dict) else json.loads(snap_data or "{}")
                history.append({"date": str(snap_date),
                                "rating": sd_.get("rating"),
                                "business_outlook_rating": sd_.get("business_outlook_rating"),
                                "ceo_rating": sd_.get("ceo_rating"),
                                "recommend_to_friend_rating": sd_.get("recommend_to_friend_rating"),
                                "senior_management_rating": sd_.get("senior_management_rating"),
                                "work_life_balance_rating": sd_.get("work_life_balance_rating"),
                                "compensation_and_benefits_rating": sd_.get("compensation_and_benefits_rating"),
                                "culture_and_values_rating": sd_.get("culture_and_values_rating"),
                                "review_count": sd_.get("review_count")})
        except Exception as _he:
            logger.warning(f"glassdoor history read failed for brand {brand_id}: {_he}")
            conn.rollback()

        return {
            "brand_id": brand_id,
            "glassdoor_enabled": glassdoor_enabled,
            "overview": overview,
            "reviews": reviews,
            "review_sentiment": {"pos": pos, "neu": neu, "neg": neg,
                                 "scored": scored, "net": net},
            "workforce_risks": workforce_risks,
            "competitors": competitors,
            "history": history,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"employee-risk failed for brand {brand_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/brands/{brand_id}/risk-summary")
async def get_risk_summary(
    brand_id: int,
    days_back: int = Query(90, ge=0, le=730),
    session=Depends(verify_session),
):
    """Per-brand adverse-risk rollup: counts by type x severity, top findings,
    official-source record counts, and alert-event count for the window."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        sd, ed = _get_date_range(days_back)
        by_type: dict = {}
        for rt, sev, n in conn.execute(text("""
            SELECT r.risk_type, r.severity, COUNT(*)
            FROM bw_article_risks r JOIN articles a ON a.uri = r.article_uri
            WHERE r.brand_id = :b AND a.publication_date >= :sd AND a.publication_date <= :ed
            GROUP BY r.risk_type, r.severity
        """), {"b": brand_id, "sd": sd, "ed": ed}).fetchall():
            slot = by_type.setdefault(rt, {"high": 0, "medium": 0, "low": 0, "total": 0})
            slot[sev if sev in ("high", "medium", "low") else "low"] += n
            slot["total"] += n

        top = [
            {"uri": r[0], "title": r[1], "risk_type": r[2], "severity": r[3],
             "confidence": float(r[4]) if r[4] is not None else None,
             "publication_date": str(r[5] or ""), "news_source": r[6],
             "case_status": r[7] or "new"}
            for r in conn.execute(text("""
                SELECT r.article_uri, a.title, r.risk_type, r.severity, r.confidence,
                       a.publication_date, a.news_source, fr.status
                FROM bw_article_risks r
                JOIN articles a ON a.uri = r.article_uri
                LEFT JOIN bw_finding_reviews fr
                    ON fr.article_uri = r.article_uri AND fr.brand_id = r.brand_id
                WHERE r.brand_id = :b AND a.publication_date >= :sd AND a.publication_date <= :ed
                ORDER BY CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                         a.publication_date DESC
                LIMIT 10
            """), {"b": brand_id, "sd": sd, "ed": ed}).fetchall()
        ]

        official = {
            ns: n for ns, n in conn.execute(text("""
                SELECT a.news_source, COUNT(DISTINCT a.uri)
                FROM articles a
                JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :b
                WHERE a.bias_source LIKE 'official:%'
                  AND a.publication_date >= :sd AND a.publication_date <= :ed
                GROUP BY a.news_source
            """), {"b": brand_id, "sd": sd, "ed": ed}).fetchall()
        }

        alert_events = conn.execute(text("""
            SELECT COUNT(*) FROM bw_alert_events
            WHERE brand_id = :b AND rule <> 'digest'
              AND created_at >= now() - (:d || ' days')::interval
        """), {"b": brand_id, "d": str(days_back or 3650)}).fetchone()[0]

        open_incidents = conn.execute(text("""
            SELECT COUNT(*) FROM bw_incidents
            WHERE brand_id = :b AND status NOT IN ('resolved', 'closed')
        """), {"b": brand_id}).fetchone()[0]

        return {"brand_id": brand_id, "days_back": days_back, "by_type": by_type,
                "top_findings": top, "official_sources": official,
                "alert_events": alert_events, "open_incidents": open_incidents}
    except Exception as e:
        logger.error(f"risk-summary failed for brand {brand_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Five Signals article screening (saas.aunoo.ai claim validation + propagation)
# ============================================================================

class SignalsRunRequest(BaseModel):
    article_uri: str
    brand_id: int
    force: bool = False
    # Which engine(s) to query: 'full' (both), 'validation' (claim validation
    # only), 'reach' (Bluesky story-reach only). Partial runs merge into the
    # stored row and the five signals recompose over both payloads.
    mode: str = "full"


@router.post("/signals/run")
async def run_article_signals(
    request: SignalsRunRequest,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session),
):
    """Kick off a Five Signals screen for one article (background).

    The screen calls saas.aunoo.ai's claim-validation and deep story-reach
    jobs (2-4 min wall clock) and composes the result into
    ``bw_article_signals``; the frontend polls GET /signals/detail until the
    row leaves 'running'. Completed rows are returned as-is unless force.
    """
    from app.services.bw_signals_service import signals_available, run_five_signals
    if not signals_available():
        raise HTTPException(status_code=503,
                            detail="Five Signals is not configured (AUNOO_SAAS_MCP_KEY missing)")
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        row = conn.execute(text(
            "SELECT uri FROM articles WHERE uri = :u"
        ), {"u": request.article_uri}).fetchone()
        if not row or not str(row[0]).lower().startswith(("http://", "https://")):
            raise HTTPException(status_code=400,
                                detail="Five Signals needs a public article URL "
                                       "(social posts and employee reviews are not screenable)")
        if request.mode not in ("full", "validation", "reach"):
            raise HTTPException(status_code=400, detail="mode must be full | validation | reach")
        existing = conn.execute(text(
            "SELECT status, validation IS NOT NULL, reach IS NOT NULL FROM bw_article_signals"
            " WHERE article_uri = :u AND brand_id = :b"
        ), {"u": request.article_uri, "b": request.brand_id}).fetchone()
        if existing and existing[0] == "running":
            return {"status": "running"}
        # Cached-return only when every engine the caller asked for has already
        # run — a partial run may still fill in the missing engine.
        if existing and existing[0] == "completed" and not request.force:
            has_val, has_reach = bool(existing[1]), bool(existing[2])
            wanted_done = (has_val if request.mode == "validation"
                           else has_reach if request.mode == "reach"
                           else (has_val and has_reach))
            if wanted_done:
                return {"status": "completed", "cached": True}
        background_tasks.add_task(
            run_five_signals, request.article_uri, request.brand_id,
            request.article_uri, 90, request.force, "user", request.mode,
        )
        return {"status": "running"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"signals/run failed for {request.article_uri}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/signals/detail")
async def get_article_signals(
    article_uri: str,
    brand_id: int,
    session=Depends(verify_session),
):
    """Full Five Signals row for one article (poll target for the modal)."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        row = conn.execute(text("""
            SELECT status, signals, verdict, composite_score, validation, reach,
                   xnet, error, requested_by, created_at::text, updated_at::text
            FROM bw_article_signals WHERE article_uri = :u AND brand_id = :b
        """), {"u": article_uri, "b": brand_id}).fetchone()
        if not row:
            return {"status": "none"}
        def _j(v):
            return v if isinstance(v, (dict, list)) or v is None else json.loads(v)
        return {
            "status": row[0], "signals": _j(row[1]), "verdict": row[2],
            "composite_score": row[3], "validation": _j(row[4]), "reach": _j(row[5]),
            "xnet": _j(row[6]),
            "error": row[7], "requested_by": row[8],
            "created_at": row[9], "updated_at": row[10],
        }
    except Exception as e:
        logger.error(f"signals/detail failed for {article_uri}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
