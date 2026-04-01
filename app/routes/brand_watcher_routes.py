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

## Analysis Approach

Your job is to SYNTHESIZE the articles into coherent themes and narratives, not to cherry-pick or list individual articles. Read all the provided articles and identify the underlying patterns, recurring themes, and emerging storylines. When you reference specific articles, use them as evidence supporting a broader theme — not as standalone items.

For example, instead of "Article X reports a data breach", write: "Data security has emerged as a significant theme, with incidents including a [major breach at a subsidiary](https://example.com/article) that exposed customer records, reinforcing broader concerns about information governance across the group."

## Required Sections

Write a comprehensive brand intelligence narrative (600-1000 words) with these EXACT section headers (use ## markdown format):

## Executive Summary
Key findings in 3-4 sentences. Synthesize the dominant narrative threads around this brand. What requires immediate attention? If the Brand Risk Assessment shows Elevated or High risk, explain what themes in the coverage are driving it.

## Category Analysis
What patterns emerge from the category distribution? Which areas have the most coverage? Synthesize what the articles in each major category are collectively saying about the brand — don't just report percentages.

## Sentiment & Reputation
YOU MUST use bullet points in this section. Format EXACTLY like this:

- **Positive Signals**: [Synthesize themes from the positive articles. What recurring patterns of good news exist? Link to representative articles as evidence using [title](url) format.]
- **Risk Indicators**: [Synthesize themes from the negative articles. What recurring patterns of concern exist? Reference the Brand Risk Assessment level and explain what themes are driving it, linking to representative articles as evidence using [title](url) format. Do NOT speculate — ground every claim in the articles provided.]
- **Competitive Position**: [How the brand is positioned vs competitors based on coverage themes]

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


class ArticlesListResponse(BaseModel):
    articles: List[ArticleResponse]
    total_count: int
    page: int
    per_page: int
    total_pages: int


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
    model: str = "gpt-4.1-mini"


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
    model: str = "gpt-4.1-mini"


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
        model = LiteLLMModel.get_instance("gpt-4.1-mini")
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

            base_params = {"start": start_date, "end": end_date, **brand_params}
            if topics:
                for i, t in enumerate(topics):
                    base_params[f"topic_{i}"] = t

            # Query articles that mention this brand (only enriched/analyzed articles)
            if run_type == "full":
                art_result = conn.execute(text(f"""
                    SELECT a.uri, a.title, a.summary FROM articles a
                    WHERE a.publication_date >= :start AND a.publication_date <= :end
                    AND a.analyzed = true
                    {topic_filter}
                    {brand_filter}
                """), base_params)
            else:
                # Incremental: only articles not yet classified for this brand
                art_result = conn.execute(text(f"""
                    SELECT a.uri, a.title, a.summary FROM articles a
                    LEFT JOIN bw_article_categories bac ON a.uri = bac.article_uri AND bac.brand_id = :bid
                    WHERE a.publication_date >= :start AND a.publication_date <= :end
                    AND a.analyzed = true
                    AND bac.id IS NULL
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

            for uri, title, summary in articles:
                title = title or ''
                summary = summary or ''

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
                    for cat in categories:
                        try:
                            conn.execute(text("""
                                INSERT INTO bw_article_categories
                                (article_uri, brand_id, category, classification_method, confidence)
                                VALUES (:uri, :bid, :cat, :method, :conf)
                                ON CONFLICT (article_uri, brand_id, category)
                                DO UPDATE SET classification_method = :method,
                                    confidence = :conf, classified_at = NOW()
                            """), {"uri": uri, "bid": bid, "cat": cat, "method": method, "conf": confidence})
                        except Exception as e:
                            logger.warning(f"Failed to store category {cat} for {uri}: {e}")
                    articles_categorized += 1

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

        model = LiteLLMModel.get_instance("gpt-4.1-mini")
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
            WHERE a.publication_date >= :start AND a.publication_date <= :end
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
            WHERE a.publication_date >= :start AND a.publication_date <= :end
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
            WHERE a.publication_date >= :start AND a.publication_date <= :end
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
            WHERE a.publication_date >= :prev_start AND a.publication_date < :start
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
            WHERE a.publication_date >= :start AND a.publication_date <= :end
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
            WHERE a.publication_date >= :start AND a.publication_date <= :end
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
                WHERE bac.brand_id = :bid
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
                WHERE bac.brand_id = :bid
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
            WHERE a.publication_date >= :start AND a.publication_date <= :end
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
            WHERE bac.brand_id = :bid
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
            WHERE bac.brand_id = :bid
            AND a.publication_date >= (NOW() - INTERVAL '7 days')::text
            GROUP BY bac.category
        """), {"bid": brand_id})
        recent_counts = {row[0]: row[1] for row in recent.fetchall()}

        # 30-day avg (per week, excluding last 7 days)
        avg_result = conn.execute(text("""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri) / 4.0 as avg_weekly
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid
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
                })

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
                   bac.classification_method, a.uri
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
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
                }
                for r in rows
            ]
            return {"brand": brand_name, "export_date": datetime.now().isoformat(), "articles": data, "total": len(data)}

        # CSV export
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Title", "Category", "Sentiment", "Source", "Confidence", "Method", "URI"])
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
    per_page: int = Query(25, ge=1, le=100),
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
                       a.tags, a.extracted_article_keywords
                FROM articles a
                JOIN bw_article_categories bac ON a.uri = bac.article_uri
                JOIN bw_brands b ON bac.brand_id = b.id
                WHERE a.publication_date >= :start AND a.publication_date <= :end
                AND a.analyzed = true
                {brand_clause} {cat_clause} {topic_clause}
                GROUP BY a.uri, a.title, a.summary, a.news_source,
                         a.publication_date, a.sentiment, bac.brand_id, b.display_name,
                         a.tags, a.extracted_article_keywords
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

        articles = []
        for row in result.fetchall():
            row_brand_id = row[6]
            if row_brand_id and row_brand_id not in brand_terms_cache:
                br = conn.execute(text(f"SELECT {BRAND_SELECT_COLS} FROM bw_brands WHERE id = :id"), {"id": row_brand_id}).fetchone()
                if br:
                    brand_terms_cache[row_brand_id] = _get_brand_search_terms(_brand_row_to_dict(br))
            search_terms = brand_terms_cache.get(row_brand_id, [])
            matched = _find_matched_keywords(row[1], row[2], search_terms, tags=row[10], keywords=row[11]) if search_terms else []
            articles.append(ArticleResponse(
                uri=row[0], title=row[1], summary=row[2],
                news_source=row[3],
                publication_date=str(row[4]) if row[4] else None,
                sentiment=row[5],
                brand_id=row[6], brand_name=row[7],
                categories=list(row[8]) if row[8] else [],
                matched_keywords=matched,
            ))

        return ArticlesListResponse(
            articles=articles, total_count=total_count,
            page=page, per_page=per_page, total_pages=total_pages,
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
            WHERE bac.brand_id = :bid
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
                WHERE bac.brand_id = :bid
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
            WHERE bac.brand_id = :bid
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
            WHERE bac.brand_id = :bid
            AND a.publication_date >= (NOW() - INTERVAL '7 days')::text
            GROUP BY bac.category
        """), {"bid": request.brand_id})
        recent_alert_counts = {row[0]: row[1] for row in recent_alert.fetchall()}

        avg_alert = conn.execute(text("""
            SELECT bac.category, COUNT(DISTINCT bac.article_uri) / 4.0 as avg_weekly
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid
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
                   bac.category, a.publication_date, a.uri
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid
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
                lines.append(f"- [{category}] ({pub_date}) [{title}]({uri}) — {summary}")
            neg_articles_text = "\n".join(lines)

        # Fetch recent positive articles to ground positive signals with evidence
        pos_articles_result = conn.execute(text("""
            SELECT DISTINCT a.title, a.summary, a.sentiment,
                   bac.category, a.publication_date, a.uri
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid
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
                lines.append(f"- [{category}] ({pub_date}) [{title}]({uri}) — {summary}")
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

        prompt = NARRATIVE_ANALYSIS_PROMPT.format(
            brand_name=brand["display_name"],
            date_range=f"{start_date} to {end_date}",
            total_articles=total_articles,
            category_breakdown=category_breakdown,
            competitor_breakdown=competitor_breakdown,
            risk_assessment=risk_assessment,
            key_articles=key_articles,
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
            WHERE bac.brand_id = :bid AND bac.category = :cat
            AND a.publication_date >= :start AND a.publication_date <= :end
        """), {"bid": request.brand_id, "cat": request.category, "start": start_date, "end": end_date})
        article_count = count_result.fetchone()[0]

        # Total for percentage
        total_result = conn.execute(text("""
            SELECT COUNT(DISTINCT bac.article_uri)
            FROM bw_article_categories bac
            JOIN articles a ON bac.article_uri = a.uri
            WHERE bac.brand_id = :bid
            AND a.publication_date >= :start AND a.publication_date <= :end
        """), {"bid": request.brand_id, "start": start_date, "end": end_date})
        total = total_result.fetchone()[0] or 1
        percentage = round(article_count / total * 100, 1)

        # Sample titles
        sample_result = conn.execute(text("""
            SELECT a.title FROM articles a
            JOIN bw_article_categories bac ON a.uri = bac.article_uri
            WHERE bac.brand_id = :bid AND bac.category = :cat
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
