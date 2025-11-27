"""
Newsletter Generation Service with Streaming Progress

Provides a multi-step newsletter generation workflow with real-time progress updates.
"""

import asyncio
import logging
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# Source quality tiers
HIGH_QUALITY_SOURCES = {
    "reuters", "ft", "financial times", "wsj", "wall street journal", "bloomberg",
    "ap", "associated press", "mit technology review", "nature", "science",
    "wired", "ars technica", "the verge", "techcrunch", "nyt", "new york times",
    "washington post", "guardian", "economist", "bbc", "npr"
}

MEDIUM_QUALITY_SOURCES = {
    "forbes", "fortune", "cnbc", "venturebeat", "zdnet", "cnet", "engadget",
    "ieee spectrum", "hacker news", "medium", "substack", "stratechery",
    "the register", "information", "protocol", "semafor", "axios", "politico"
}

# Section categorization keywords
SECTION_KEYWORDS = {
    "policy_regulation": [
        "regulation", "policy", "law", "legal", "government", "congress", "eu",
        "legislation", "compliance", "gdpr", "act", "bill", "senate", "fcc",
        "ftc", "sec", "antitrust", "privacy", "ban", "restrict", "mandate"
    ],
    "models_research": [
        "model", "gpt", "llm", "claude", "gemini", "llama", "research", "paper",
        "benchmark", "training", "parameter", "architecture", "transformer",
        "neural", "deep learning", "machine learning", "algorithm", "dataset",
        "arxiv", "breakthrough", "sota", "state-of-the-art", "release"
    ],
    "enterprise_adoption": [
        "enterprise", "business", "company", "corporate", "deploy", "implement",
        "adopt", "integration", "productivity", "workflow", "automation",
        "customer", "revenue", "cost", "roi", "efficiency", "scale"
    ],
    "market_funding": [
        "funding", "raise", "series", "investment", "ipo", "acquisition",
        "merger", "m&a", "valuation", "billion", "million", "venture",
        "startup", "seed", "deal", "buy", "acquire", "partnership"
    ],
    "risk_trust": [
        "risk", "safety", "security", "threat", "vulnerability", "attack",
        "bias", "fairness", "ethics", "trust", "hallucination", "misinformation",
        "deepfake", "fraud", "scam", "abuse", "harm", "danger", "concern"
    ],
    "weird_unusual": [
        "bizarre", "strange", "weird", "unusual", "unexpected", "surprising",
        "viral", "controversy", "backlash", "outrage", "debate", "chaos",
        "failure", "error", "mistake", "bug", "glitch", "unintended", "funny",
        "ironic", "absurd", "curious", "odd", "wtf"
    ]
}

# Metatrend themes
METATREND_THEMES = {
    "consolidation": ["merger", "acquisition", "consolidat", "buyout", "acquire"],
    "regulation_pressure": ["regulation", "ban", "restrict", "compliance", "lawsuit", "antitrust"],
    "open_source_momentum": ["open source", "open-source", "llama", "mistral", "hugging face"],
    "enterprise_adoption": ["enterprise", "deploy", "adoption", "pilot", "production"],
    "safety_concerns": ["safety", "alignment", "risk", "harm", "ethics", "bias"],
    "cost_reduction": ["cheaper", "cost", "efficient", "optimize", "reduce"],
    "multimodal_expansion": ["multimodal", "vision", "audio", "video", "image"],
    "agent_evolution": ["agent", "autonomous", "agentic", "tool use", "function calling"],
    "geopolitical_tension": ["china", "export", "chip", "nvidia", "restriction", "eu", "regulation"],
    "talent_war": ["hire", "talent", "poach", "team", "researcher", "scientist"]
}


@dataclass
class NewsletterConfig:
    """Configuration for newsletter generation."""
    days_back: int = 7
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    model: str = "gpt-4o"
    max_articles: int = 200
    section_limits: Dict[str, int] = field(default_factory=lambda: {
        "policy_regulation": 5,
        "models_research": 5,
        "enterprise_adoption": 5,
        "market_funding": 8,
        "risk_trust": 4,
        "weird_unusual": 5,
        "general": 6
    })


class NewsletterService:
    """Service for generating newsletters with streaming progress."""

    def __init__(self, db, vector_store=None, ai_model_getter=None):
        self.db = db
        self.vector_store = vector_store
        self.ai_model_getter = ai_model_getter
        self.logger = logging.getLogger("newsletter_service")

    async def generate_newsletter(
        self,
        topic: str,
        config: Optional[NewsletterConfig] = None,
        profile_context: str = ""
    ) -> AsyncGenerator[Dict, None]:
        """
        Generate newsletter with streaming progress updates.

        Yields progress updates for each stage:
        - fetching: Gathering articles from database and vector store
        - categorizing: Organizing articles by section
        - analyzing: Detecting metatrends and selecting deep dive topic
        - deep_dive: Generating consensus/credibility analysis
        - writing: Producing final newsletter content

        Final yield contains the complete newsletter.
        """
        if config is None:
            config = NewsletterConfig()

        import time
        start_time = time.time()

        # Parse dates
        start_date, end_date = self._parse_dates(config)

        # Stage 1: Fetching articles
        yield {
            "stage": "fetching",
            "status": "started",
            "progress": 0.0,
            "message": "Gathering articles from database..."
        }

        articles = await self._fetch_articles(topic, start_date, end_date, config.max_articles)

        yield {
            "stage": "fetching",
            "status": "completed",
            "progress": 1.0,
            "message": f"Found {len(articles)} articles",
            "article_count": len(articles)
        }

        if not articles:
            yield {
                "stage": "error",
                "error": f"No articles found for topic '{topic}' in the specified date range"
            }
            return

        # Stage 2: Categorizing
        yield {
            "stage": "categorizing",
            "status": "started",
            "progress": 0.0,
            "message": "Categorizing articles by section..."
        }

        categorized = self._categorize_articles(articles)
        selected = self._select_articles_per_section(categorized, config.section_limits)

        section_counts = {k: len(v) for k, v in selected.items()}
        yield {
            "stage": "categorizing",
            "status": "completed",
            "progress": 1.0,
            "message": f"Organized into {len(section_counts)} sections",
            "section_counts": section_counts
        }

        # Stage 3: Analyzing (metatrends + deep dive topic selection)
        yield {
            "stage": "analyzing",
            "status": "started",
            "progress": 0.0,
            "message": "Detecting metatrends..."
        }

        metatrends = self._detect_metatrends(articles)
        deep_dive_topic, deep_dive_articles = self._select_deep_dive_topic(
            articles, categorized, metatrends
        )

        yield {
            "stage": "analyzing",
            "status": "completed",
            "progress": 1.0,
            "message": f"Found {len(metatrends)} metatrends, deep dive: {deep_dive_topic}",
            "metatrends": [t['theme'] for t in metatrends],
            "deep_dive_topic": deep_dive_topic
        }

        # Stage 4: Deep Dive Analysis
        deep_dive_analysis = None
        if self.ai_model_getter and deep_dive_articles:
            yield {
                "stage": "deep_dive",
                "status": "started",
                "progress": 0.0,
                "message": f"Analyzing '{deep_dive_topic}' for consensus and credibility..."
            }

            deep_dive_analysis = await self._generate_deep_dive(
                deep_dive_topic, deep_dive_articles, config.model
            )

            yield {
                "stage": "deep_dive",
                "status": "completed",
                "progress": 1.0,
                "message": "Deep dive analysis complete"
            }

        # Stage 5: Writing Newsletter
        yield {
            "stage": "writing",
            "status": "started",
            "progress": 0.0,
            "message": "Generating newsletter content..."
        }

        newsletter_content = await self._generate_newsletter_content(
            selected, topic, metatrends, deep_dive_analysis,
            deep_dive_topic, profile_context, config.model
        )

        execution_time = int((time.time() - start_time) * 1000)
        total_used = sum(len(arts) for arts in selected.values())

        yield {
            "stage": "writing",
            "status": "completed",
            "progress": 1.0,
            "message": "Newsletter generation complete"
        }

        # Final result
        yield {
            "stage": "complete",
            "done": True,
            "newsletter": newsletter_content,
            "stats": {
                "article_count": len(articles),
                "articles_used": total_used,
                "section_counts": section_counts,
                "metatrends": metatrends,
                "deep_dive_topic": deep_dive_topic,
                "execution_time_ms": execution_time
            }
        }

    def _parse_dates(self, config: NewsletterConfig) -> Tuple[datetime, datetime]:
        """Parse date configuration into datetime objects."""
        if config.end_date:
            try:
                end_date = datetime.strptime(config.end_date[:10], '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except:
                end_date = datetime.now()
        else:
            end_date = datetime.now()

        if config.start_date:
            try:
                start_date = datetime.strptime(config.start_date[:10], '%Y-%m-%d')
            except:
                start_date = end_date - timedelta(days=config.days_back)
        else:
            start_date = end_date - timedelta(days=config.days_back)

        return start_date, end_date

    async def _fetch_articles(
        self,
        topic: str,
        start_date: datetime,
        end_date: datetime,
        max_articles: int
    ) -> List[Dict]:
        """Fetch articles from database and vector store."""
        articles = []
        seen_uris: Set[str] = set()

        # Strategy 1: Database with date range
        try:
            if hasattr(self.db, 'facade') and hasattr(self.db.facade, 'get_recent_articles_by_topic'):
                db_articles = self.db.facade.get_recent_articles_by_topic(
                    topic_name=topic,
                    limit=max_articles,
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d')
                )
                if db_articles:
                    for art in db_articles:
                        uri = art.get('uri') or art.get('id')
                        if uri and uri not in seen_uris:
                            seen_uris.add(uri)
                            articles.append(art)
                    self.logger.info(f"DB search: {len(db_articles)} articles")
        except Exception as e:
            self.logger.warning(f"DB search failed: {e}")

        # Strategy 2: Vector search
        if self.vector_store and len(articles) < 100:
            try:
                search_queries = [
                    topic,
                    f"latest {topic} news",
                    f"{topic} regulation policy",
                    f"{topic} funding investment",
                    f"{topic} research breakthrough"
                ]

                for query in search_queries:
                    try:
                        results = self.vector_store(
                            query=query,
                            top_k=50,
                            metadata_filter={"topic": topic} if topic else None
                        )
                        if results:
                            for result in results:
                                metadata = result.get('metadata', {})
                                uri = metadata.get('uri') or result.get('id', '')
                                if uri and uri not in seen_uris:
                                    seen_uris.add(uri)
                                    articles.append({
                                        "uri": uri,
                                        "url": metadata.get("url") or metadata.get("link") or uri,
                                        "title": metadata.get("title", "Unknown Title"),
                                        "summary": metadata.get("summary", ""),
                                        "category": metadata.get("category", ""),
                                        "sentiment": metadata.get("sentiment", ""),
                                        "future_signal": metadata.get("future_signal", ""),
                                        "pub_date": metadata.get("pub_date") or metadata.get("publication_date", ""),
                                        "news_source": metadata.get("news_source", "Unknown"),
                                        "similarity_score": result.get("score", 0.0)
                                    })
                    except Exception as e:
                        self.logger.debug(f"Vector search failed: {e}")
            except Exception as e:
                self.logger.warning(f"Vector search failed: {e}")

        # Filter by date range
        articles = [
            art for art in articles
            if self._is_within_date_range(art, start_date, end_date)
        ]

        return articles

    def _is_within_date_range(self, article: Dict, start_date: datetime, end_date: datetime) -> bool:
        """Check if article is within date range."""
        pub_date = article.get('pub_date') or article.get('publication_date', '')
        if not pub_date:
            return True

        try:
            if isinstance(pub_date, str):
                if 'T' in pub_date:
                    date_obj = datetime.fromisoformat(pub_date.replace('Z', '+00:00')).replace(tzinfo=None)
                else:
                    date_obj = datetime.strptime(pub_date[:10], '%Y-%m-%d')
            else:
                date_obj = pub_date
            return start_date <= date_obj <= end_date
        except:
            return True

    def _categorize_articles(self, articles: List[Dict]) -> Dict[str, List[Dict]]:
        """Categorize articles by section."""
        categorized = defaultdict(list)

        for article in articles:
            title = (article.get('title') or '').lower()
            summary = (article.get('summary') or '').lower()
            category = (article.get('category') or '').lower()
            content = f"{title} {summary} {category}"

            section_scores = {}
            for section, keywords in SECTION_KEYWORDS.items():
                score = sum(1 for kw in keywords if kw in content)
                if score > 0:
                    section_scores[section] = score

            if section_scores:
                best_section = max(section_scores, key=section_scores.get)
                categorized[best_section].append(article)
            else:
                categorized["general"].append(article)

        return dict(categorized)

    def _select_articles_per_section(
        self,
        categorized: Dict[str, List[Dict]],
        limits: Dict[str, int]
    ) -> Dict[str, List[Dict]]:
        """Select best articles per section."""
        selected = {}
        used_uris: Set[str] = set()

        for section, section_articles in categorized.items():
            limit = limits.get(section, 5)

            scored = []
            for article in section_articles:
                uri = article.get('uri') or article.get('id', '')
                if uri in used_uris:
                    continue
                score = self._score_article(article)
                scored.append((score, article))

            scored.sort(key=lambda x: x[0], reverse=True)

            section_selected = []
            for score, article in scored[:limit]:
                uri = article.get('uri') or article.get('id', '')
                if uri not in used_uris:
                    used_uris.add(uri)
                    section_selected.append(article)

            selected[section] = section_selected

        return selected

    def _score_article(self, article: Dict) -> float:
        """Score article by quality signals."""
        score = 0.0

        source = (article.get('news_source') or '').lower()
        if any(hs in source for hs in HIGH_QUALITY_SOURCES):
            score += 30
        elif any(ms in source for ms in MEDIUM_QUALITY_SOURCES):
            score += 15

        pub_date = article.get('pub_date') or article.get('publication_date', '')
        if pub_date:
            try:
                if isinstance(pub_date, str):
                    if 'T' in pub_date:
                        date_obj = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                    else:
                        date_obj = datetime.strptime(pub_date[:10], '%Y-%m-%d')
                else:
                    date_obj = pub_date

                days_old = (datetime.now() - date_obj.replace(tzinfo=None)).days
                if days_old <= 1:
                    score += 25
                elif days_old <= 3:
                    score += 15
                elif days_old <= 7:
                    score += 5
            except:
                pass

        summary = article.get('summary') or ''
        if len(summary) > 200:
            score += 10

        sim_score = article.get('similarity_score', 0)
        if sim_score:
            score += sim_score * 20

        return score

    def _detect_metatrends(self, articles: List[Dict]) -> List[Dict]:
        """Detect metatrends across articles."""
        theme_counts = Counter()
        theme_articles = defaultdict(list)

        for article in articles:
            title = (article.get('title') or '').lower()
            summary = (article.get('summary') or '').lower()
            content = f"{title} {summary}"

            for theme, keywords in METATREND_THEMES.items():
                if any(kw in content for kw in keywords):
                    theme_counts[theme] += 1
                    if len(theme_articles[theme]) < 5:
                        theme_articles[theme].append(article.get('title', 'Untitled'))

        return [
            {"theme": theme, "count": count, "examples": theme_articles[theme][:3]}
            for theme, count in theme_counts.most_common(5)
            if count >= 3
        ]

    def _select_deep_dive_topic(
        self,
        articles: List[Dict],
        categorized: Dict[str, List[Dict]],
        metatrends: List[Dict]
    ) -> Tuple[str, List[Dict]]:
        """Select deep dive topic."""
        if metatrends and metatrends[0]['count'] >= 5:
            theme = metatrends[0]['theme']
            theme_keywords = METATREND_THEMES.get(theme, [])

            matching = [
                art for art in articles
                if any(kw in f"{art.get('title', '')} {art.get('summary', '')}".lower()
                       for kw in theme_keywords)
            ]

            if len(matching) >= 3:
                return theme.replace('_', ' ').title(), matching[:10]

        best_section = None
        best_score = 0

        for section, section_articles in categorized.items():
            if section in ('general', 'weird_unusual'):
                continue

            score = sum(
                3 if any(hs in (art.get('news_source') or '').lower() for hs in HIGH_QUALITY_SOURCES)
                else 1
                for art in section_articles
            )

            if score > best_score:
                best_score = score
                best_section = section

        if best_section and categorized.get(best_section):
            return f"This Week in {best_section.replace('_', ' ').title()}", categorized[best_section][:10]

        return "Key Developments", articles[:10]

    async def _generate_deep_dive(
        self,
        topic: str,
        articles: List[Dict],
        model_name: str
    ) -> Optional[str]:
        """Generate deep dive analysis."""
        articles_text = self._format_articles_for_analysis(articles)

        prompt = f"""You are an expert analyst conducting a deep dive investigation.

## TOPIC: {topic}

## SOURCE ARTICLES:

{articles_text}

## TASK:

Analyze using MULTIPLE articles:

1. **THE DEVELOPMENT**: What's the core claim/trend/incident?

2. **CONSENSUS ANALYSIS**:
   - What do sources agree on? (cite specific sources)
   - Where do they disagree?
   - What's well-supported vs speculative?

3. **CREDIBILITY EVALUATION**:
   - Most credible sources and why
   - Red flags (single-source claims, promotional content)
   - Confidence level: High/Medium/Low

4. **BROADER CONTEXT**:
   - Connection to larger trends
   - Second-order effects
   - "So what" for decision-makers

5. **STRATEGIC INSIGHT** (4 bullets):
   - For enterprises
   - For policymakers
   - For investors
   - For citizens

## OUTPUT:

300-400 words, Atlantic/Stratechery style.
- Citations as markdown links: **[Title](URL)**
- Call out hype vs substance
- End with Strategic Insight bullets"""

        try:
            model = self.ai_model_getter(model_name)
            if model:
                if hasattr(model, 'generate'):
                    # Use 8000 tokens for deep dive analysis
                    response = await model.generate(prompt, max_tokens=8000)
                    if hasattr(response, 'message') and hasattr(response.message, 'content'):
                        return response.message.content
                    return str(response)
                elif hasattr(model, 'acomplete'):
                    response = await model.acomplete(prompt)
                    return response.text if hasattr(response, 'text') else str(response)
        except Exception as e:
            self.logger.error(f"Deep dive generation failed: {e}")

        return None

    def _format_articles_for_analysis(self, articles: List[Dict]) -> str:
        """Format articles for deep dive prompt."""
        lines = []
        for i, article in enumerate(articles, 1):
            title = article.get('title', 'Untitled')
            source = article.get('news_source', 'Unknown')
            url = article.get('url') or article.get('uri', '')
            date = article.get('pub_date') or article.get('publication_date', '')
            summary = (article.get('summary') or '')[:500]

            if date and isinstance(date, str) and len(date) > 10:
                date = date[:10]

            lines.append(f"### Article {i}: {title}")
            lines.append(f"Source: {source} | Date: {date}")
            if url:
                lines.append(f"URL: {url}")
            if summary:
                lines.append(f"Summary: {summary}")
            lines.append("")

        return "\n".join(lines)

    async def _generate_newsletter_content(
        self,
        selected: Dict[str, List[Dict]],
        topic: str,
        metatrends: List[Dict],
        deep_dive_analysis: Optional[str],
        deep_dive_topic: str,
        profile_context: str,
        model_name: str
    ) -> str:
        """Generate the full newsletter."""
        sections_context = self._format_sections_for_prompt(selected)
        total_articles = sum(len(v) for v in selected.values())

        metatrends_text = ""
        if metatrends:
            metatrends_text = "\n## DETECTED METATRENDS\n"
            for trend in metatrends:
                metatrends_text += f"- **{trend['theme'].replace('_', ' ').title()}**: {trend['count']} articles\n"

        org_context = ""
        if profile_context:
            org_context = f"\n## ORGANIZATIONAL CONTEXT\n{profile_context}\n"

        deep_dive_section = ""
        if deep_dive_analysis:
            deep_dive_section = f"""
## PRE-GENERATED DEEP DIVE

Topic: {deep_dive_topic}

{deep_dive_analysis}

**USE THIS ANALYSIS AS-IS for The Deep Dive section.**
"""

        prompt = f"""{org_context}URLS ARE MANDATORY - Format as: **[Headline](URL)** (Source, Date)

Role: Analyst for decision-makers. Techno-realist, skeptical of hype.

Dataset: {total_articles} articles. Use only these sources.

{metatrends_text}

## SOURCE ARTICLES

{sections_context}

{deep_dive_section}

## OUTPUT FORMAT

## The News
6-12 headlines by theme. Each: **[Headline](URL)** (Source, Date) - why it matters.

## The Deep Dive — {deep_dive_topic}
{"USE THE PRE-GENERATED ANALYSIS ABOVE." if deep_dive_analysis else "Analyze using MULTIPLE articles with consensus/credibility assessment."}

## Weird Sh*t of the Week
2-3 bizarre/funny/ironic stories with sharp commentary. MUST cite at least 2 articles.

## Must Reads (5-7)
UNIQUE articles NOT in The News or Deep Dive. Why it's a must-read.

## Metatrends
{metatrends_text if metatrends_text else "Identify 2-3 patterns."}
Brief commentary on what these signal.

## Market Updates
M&A, Releases, Partnerships from MARKET section. One-line "so what" each.

House Rules: Every citation = markdown link. No repetition across sections."""

        try:
            model = self.ai_model_getter(model_name)
            if model:
                if hasattr(model, 'generate'):
                    # Use 16000 tokens for full newsletter generation
                    response = await model.generate(prompt, max_tokens=16000)
                    if hasattr(response, 'message') and hasattr(response.message, 'content'):
                        return response.message.content
                    return str(response)
                elif hasattr(model, 'acomplete'):
                    response = await model.acomplete(prompt)
                    return response.text if hasattr(response, 'text') else str(response)
        except Exception as e:
            self.logger.error(f"Newsletter generation failed: {e}")

        return self._generate_fallback(selected, topic)

    def _format_sections_for_prompt(self, selected: Dict[str, List[Dict]]) -> str:
        """Format articles for main prompt."""
        sections = []
        section_names = {
            "policy_regulation": "POLICY & REGULATION",
            "models_research": "MODELS & RESEARCH",
            "enterprise_adoption": "ENTERPRISE & ADOPTION",
            "market_funding": "MARKET & FUNDING",
            "risk_trust": "RISK & TRUST",
            "weird_unusual": "WEIRD/UNUSUAL",
            "general": "GENERAL"
        }

        for section_key, articles in selected.items():
            if not articles:
                continue

            section_name = section_names.get(section_key, section_key.upper())
            section_text = f"\n### {section_name} ({len(articles)} articles)\n"

            for i, article in enumerate(articles, 1):
                title = article.get('title', 'Untitled')
                source = article.get('news_source', 'Unknown')
                url = article.get('url') or article.get('uri', '')
                date = article.get('pub_date') or article.get('publication_date', '')
                summary = (article.get('summary') or '')[:400]

                if date and isinstance(date, str) and len(date) > 10:
                    date = date[:10]

                section_text += f"\n{i}. **{title}**\n"
                section_text += f"   Source: {source} | Date: {date}\n"
                if url:
                    section_text += f"   URL: {url}\n"
                if summary:
                    section_text += f"   Summary: {summary}\n"

            sections.append(section_text)

        return "\n".join(sections)

    def _generate_fallback(self, selected: Dict[str, List[Dict]], topic: str) -> str:
        """Generate basic newsletter when LLM unavailable."""
        parts = [f"# {topic} Weekly Newsletter\n"]

        for section_key, articles in selected.items():
            if not articles:
                continue

            parts.append(f"\n## {section_key.replace('_', ' ').title()}\n")

            for article in articles[:5]:
                title = article.get('title', 'Untitled')
                source = article.get('news_source', 'Unknown')
                url = article.get('url') or article.get('uri', '')
                date = (article.get('pub_date') or article.get('publication_date', ''))[:10]

                if url:
                    parts.append(f"- **[{title}]({url})** ({source}, {date})")
                else:
                    parts.append(f"- **{title}** ({source}, {date})")

        return "\n".join(parts)


# Service instance getter
_newsletter_service = None


def get_newsletter_service():
    """Get or create newsletter service instance."""
    global _newsletter_service
    if _newsletter_service is None:
        from app.services.auspex_service import get_auspex_service
        from app.vector_store import search_articles as vector_search_articles
        from app.ai_models import get_ai_model
        auspex = get_auspex_service()
        _newsletter_service = NewsletterService(
            db=auspex.db,
            vector_store=vector_search_articles,
            ai_model_getter=get_ai_model
        )
    return _newsletter_service
