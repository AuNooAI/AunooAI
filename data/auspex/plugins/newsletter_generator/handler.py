"""
Newsletter Generator Tool Handler v2.1

Multi-step newsletter generation that:
1. Fetches a large corpus of articles (100-200)
2. Categorizes articles by newsletter section
3. Prioritizes by recency, source quality, and relevance
4. Detects metatrends across the corpus
5. Generates deep dive with consensus/credibility analysis (separate agent call)
6. Generates each section with proper article coverage
7. Ensures no article duplication across sections
"""

import asyncio
import logging
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.tool_plugin_base import ToolHandler, ToolResult


# Source quality tiers for prioritization
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

# Keywords for categorizing articles by section
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

# Keywords for metatrend detection
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


class NewsletterGeneratorHandler(ToolHandler):
    """Handler for multi-step newsletter generation."""

    def __init__(self, definition, config=None):
        super().__init__(definition, config)
        self.logger = logging.getLogger("tool.newsletter_generator")

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """
        Execute multi-step newsletter generation.

        Steps:
        1. Fetch large article corpus
        2. Categorize by section
        3. Detect metatrends
        4. Prioritize and select best articles per section
        5. Generate deep dive analysis (separate LLM call)
        6. Generate full newsletter with LLM
        """
        import time
        start_time = time.time()

        topic = params.get("topic") or context.get("topic", "AI")
        days_back = params.get("days_back", 7)

        # Parse date range parameters
        start_date = None
        end_date = None

        start_date_param = params.get("start_date")
        if start_date_param:
            if isinstance(start_date_param, str):
                try:
                    start_date = datetime.strptime(start_date_param[:10], '%Y-%m-%d')
                except:
                    self.logger.warning(f"Invalid start_date format: {start_date_param}")
            elif isinstance(start_date_param, datetime):
                start_date = start_date_param

        end_date_param = params.get("end_date")
        if end_date_param:
            if isinstance(end_date_param, str):
                try:
                    end_date = datetime.strptime(end_date_param[:10], '%Y-%m-%d')
                    end_date = end_date.replace(hour=23, minute=59, second=59)
                except:
                    self.logger.warning(f"Invalid end_date format: {end_date_param}")
            elif isinstance(end_date_param, datetime):
                end_date = end_date_param

        db = context.get("db")
        vector_search = context.get("vector_store")
        ai_model_getter = context.get("ai_model")

        if not db:
            return ToolResult(success=False, error="Database not available")

        # Log date range info
        if start_date and end_date:
            self.logger.info(f"Newsletter for {topic}: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        else:
            self.logger.info(f"Newsletter for {topic}: last {days_back} days")

        # Step 1: Fetch large article corpus
        articles = await self._fetch_article_corpus(
            db, vector_search, topic, days_back,
            start_date_override=start_date,
            end_date_override=end_date
        )

        if not articles:
            return ToolResult(
                success=False,
                error=f"No articles found for topic '{topic}' in the specified date range"
            )

        self.logger.info(f"Fetched {len(articles)} total articles")

        # Step 2: Categorize articles by section
        categorized = self._categorize_articles(articles)
        for section, section_articles in categorized.items():
            self.logger.info(f"Section '{section}': {len(section_articles)} articles")

        # Step 3: Detect metatrends across the corpus
        metatrends = self._detect_metatrends(articles)
        self.logger.info(f"Detected metatrends: {metatrends}")

        # Step 4: Prioritize and select best articles per section
        selected = self._select_articles_per_section(categorized)

        # Step 5: Select deep dive topic and related articles
        deep_dive_topic, deep_dive_articles = self._select_deep_dive_topic(
            articles, categorized, metatrends
        )
        self.logger.info(f"Deep dive topic: {deep_dive_topic} ({len(deep_dive_articles)} articles)")

        # Step 6: Generate deep dive analysis (separate LLM call for quality)
        deep_dive_analysis = None
        if ai_model_getter and deep_dive_articles:
            deep_dive_analysis = await self._generate_deep_dive_analysis(
                deep_dive_topic, deep_dive_articles, ai_model_getter, context
            )

        # Step 7: Generate full newsletter
        newsletter_content = None
        if ai_model_getter:
            newsletter_content = await self._generate_newsletter(
                selected, topic, ai_model_getter, context,
                metatrends=metatrends,
                deep_dive_analysis=deep_dive_analysis,
                deep_dive_topic=deep_dive_topic
            )

        execution_time = int((time.time() - start_time) * 1000)
        total_used = sum(len(arts) for arts in selected.values())

        return ToolResult(
            success=True,
            data={
                "analysis": newsletter_content or self._generate_fallback(selected, topic),
                "article_count": len(articles),
                "articles_used": total_used,
                "section_counts": {k: len(v) for k, v in selected.items()},
                "metatrends": metatrends,
                "deep_dive_topic": deep_dive_topic
            },
            message=f"Generated newsletter from {len(articles)} articles ({total_used} used)",
            execution_time_ms=execution_time
        )

    def _detect_metatrends(self, articles: List[Dict]) -> List[Dict]:
        """Detect metatrends across the article corpus."""
        theme_counts = Counter()
        theme_articles = defaultdict(list)

        for article in articles:
            title = (article.get('title') or '').lower()
            summary = (article.get('summary') or '').lower()
            content = f"{title} {summary}"

            for theme, keywords in METATREND_THEMES.items():
                if any(kw in content for kw in keywords):
                    theme_counts[theme] += 1
                    if len(theme_articles[theme]) < 5:  # Keep top 5 examples
                        theme_articles[theme].append(article.get('title', 'Untitled'))

        # Return top metatrends (at least 3 articles to be significant)
        significant_trends = [
            {
                "theme": theme,
                "count": count,
                "examples": theme_articles[theme][:3]
            }
            for theme, count in theme_counts.most_common(5)
            if count >= 3
        ]

        return significant_trends

    def _select_deep_dive_topic(
        self,
        articles: List[Dict],
        categorized: Dict[str, List[Dict]],
        metatrends: List[Dict]
    ) -> Tuple[str, List[Dict]]:
        """Select the best topic for deep dive based on article clustering and metatrends."""

        # Priority 1: Use top metatrend if significant
        if metatrends and metatrends[0]['count'] >= 5:
            theme = metatrends[0]['theme']
            theme_keywords = METATREND_THEMES.get(theme, [])

            # Find all articles matching this theme
            matching_articles = []
            for article in articles:
                title = (article.get('title') or '').lower()
                summary = (article.get('summary') or '').lower()
                content = f"{title} {summary}"
                if any(kw in content for kw in theme_keywords):
                    matching_articles.append(article)

            if len(matching_articles) >= 3:
                # Format theme name nicely
                topic_name = theme.replace('_', ' ').title()
                return topic_name, matching_articles[:10]

        # Priority 2: Find cluster of related articles by looking at most common terms
        # Use the section with the most high-quality recent articles
        best_section = None
        best_score = 0

        for section, section_articles in categorized.items():
            if section in ('general', 'weird_unusual'):
                continue

            # Score by number of recent, high-quality articles
            score = 0
            for art in section_articles:
                source = (art.get('news_source') or '').lower()
                if any(hs in source for hs in HIGH_QUALITY_SOURCES):
                    score += 3
                elif any(ms in source for ms in MEDIUM_QUALITY_SOURCES):
                    score += 1
                else:
                    score += 0.5

            if score > best_score:
                best_score = score
                best_section = section

        if best_section and categorized.get(best_section):
            section_name = best_section.replace('_', ' ').title()
            return f"This Week in {section_name}", categorized[best_section][:10]

        # Fallback: use first significant metatrend or general topic
        if metatrends:
            theme = metatrends[0]['theme'].replace('_', ' ').title()
            return theme, articles[:10]

        return "Key Developments", articles[:10]

    async def _generate_deep_dive_analysis(
        self,
        topic: str,
        articles: List[Dict],
        ai_model_getter,
        context: Dict
    ) -> Optional[str]:
        """Generate deep dive analysis with consensus/credibility evaluation."""

        # Format articles for analysis
        articles_text = self._format_articles_for_analysis(articles)

        prompt = f"""You are an expert analyst conducting a deep dive investigation for a professional newsletter.

## TOPIC: {topic}

## SOURCE ARTICLES (analyze these for consensus and credibility):

{articles_text}

## YOUR TASK:

Analyze this topic by examining multiple articles to understand:

1. **THE CLAIM/TREND/INCIDENT**: What is the core development or claim being reported? Be specific.

2. **CONSENSUS ANALYSIS**:
   - What do multiple sources agree on? (cite specific sources)
   - Where do sources disagree or present conflicting information?
   - What claims are well-supported vs. speculative?

3. **CREDIBILITY EVALUATION**:
   - Which sources are most credible on this topic? Why?
   - Are there any red flags (single-source claims, promotional content, missing context)?
   - What's the confidence level: High/Medium/Low?

4. **BROADER CONTEXT**:
   - How does this connect to larger industry trends?
   - What are the second-order effects to watch?
   - What's the "so what" for decision-makers?

5. **STRATEGIC INSIGHT** (4 bullets):
   - For enterprises
   - For policymakers
   - For investors
   - For citizens/consumers

## OUTPUT FORMAT:

Write 300-400 words of analysis in a clear, analytical voice (Atlantic/Stratechery style).
- Start with the core finding/development
- Include specific citations as markdown links: **[Title](URL)**
- Call out hype vs. substance explicitly
- End with the 4 Strategic Insight bullets

Be skeptical, evidence-based, and focused on what matters for decision-makers."""

        try:
            model_name = self.config.get('model') or context.get('model') or 'gpt-4o'
            model = ai_model_getter(model_name)

            if model:
                if hasattr(model, 'generate') and callable(getattr(model, 'generate')):
                    response = await model.generate(prompt)
                    if hasattr(response, 'message') and hasattr(response.message, 'content'):
                        return response.message.content
                    return str(response)
                elif hasattr(model, 'acomplete'):
                    response = await model.acomplete(prompt)
                    return response.text if hasattr(response, 'text') else str(response)
        except Exception as e:
            self.logger.error(f"Deep dive analysis failed: {e}")

        return None

    def _format_articles_for_analysis(self, articles: List[Dict]) -> str:
        """Format articles for deep dive analysis."""
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

    def _parse_date(self, date_val) -> Optional[datetime]:
        """Parse a date value into a datetime object."""
        if not date_val:
            return None
        if isinstance(date_val, datetime):
            return date_val
        if isinstance(date_val, str):
            try:
                if 'T' in date_val:
                    return datetime.fromisoformat(date_val.replace('Z', '+00:00')).replace(tzinfo=None)
                else:
                    return datetime.strptime(date_val[:10], '%Y-%m-%d')
            except:
                return None
        return None

    def _is_within_date_range(self, article: Dict, start_date: datetime, end_date: datetime) -> bool:
        """Check if an article falls within the specified date range."""
        pub_date = article.get('pub_date') or article.get('publication_date', '')
        article_date = self._parse_date(pub_date)

        if not article_date:
            return True  # Include if no date

        return start_date <= article_date <= end_date

    async def _fetch_article_corpus(
        self,
        db,
        vector_search,
        topic: str,
        days_back: int,
        start_date_override: Optional[datetime] = None,
        end_date_override: Optional[datetime] = None
    ) -> List[Dict]:
        """Fetch a large corpus of articles using multiple search strategies."""
        articles = []
        seen_uris: Set[str] = set()

        if end_date_override:
            end_date = end_date_override
        else:
            end_date = datetime.now()

        if start_date_override:
            start_date = start_date_override
        else:
            start_date = end_date - timedelta(days=days_back)

        self.logger.info(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        # Strategy 1: Get recent articles by date from database
        try:
            if hasattr(db, 'facade') and hasattr(db.facade, 'get_recent_articles_by_topic'):
                db_articles = db.facade.get_recent_articles_by_topic(
                    topic_name=topic,
                    limit=200,
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d')
                )
                if db_articles:
                    for art in db_articles:
                        uri = art.get('uri') or art.get('id')
                        if uri and uri not in seen_uris:
                            seen_uris.add(uri)
                            articles.append(art)
                    self.logger.info(f"DB date range search: {len(db_articles)} articles")
            elif hasattr(db, 'facade') and hasattr(db.facade, 'get_articles_by_topic'):
                db_articles = db.facade.get_articles_by_topic(topic=topic, limit=200)
                if db_articles:
                    for art in db_articles:
                        uri = art.get('uri') or art.get('id')
                        if uri and uri not in seen_uris:
                            seen_uris.add(uri)
                            articles.append(art)
                    self.logger.info(f"DB topic search (no date filter): {len(db_articles)} articles")
        except Exception as e:
            self.logger.warning(f"DB topic search failed: {e}")

        # Strategy 2: Vector search with broad topic query
        if vector_search and len(articles) < 100:
            try:
                search_queries = [
                    topic,
                    f"latest {topic} news developments",
                    f"{topic} regulation policy",
                    f"{topic} funding investment startup",
                    f"{topic} research breakthrough"
                ]

                for query in search_queries:
                    try:
                        results = vector_search(
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
                                        "category": metadata.get("category", "Uncategorized"),
                                        "sentiment": metadata.get("sentiment", "Neutral"),
                                        "future_signal": metadata.get("future_signal", ""),
                                        "publication_date": metadata.get("publication_date", ""),
                                        "pub_date": metadata.get("pub_date") or metadata.get("publication_date", ""),
                                        "news_source": metadata.get("news_source", "Unknown"),
                                        "similarity_score": result.get("score", 0.0)
                                    })
                    except Exception as e:
                        self.logger.debug(f"Vector search for '{query}' failed: {e}")

                self.logger.info(f"After vector search: {len(articles)} total articles")
            except Exception as e:
                self.logger.warning(f"Vector search failed: {e}")

        # Strategy 3: SQL search fallback
        if len(articles) < 50 and hasattr(db, 'search_articles'):
            try:
                db_articles, count = db.search_articles(topic=topic, page=1, per_page=100)
                if db_articles:
                    for art in db_articles:
                        uri = art.get('uri') or art.get('id')
                        if uri and uri not in seen_uris:
                            seen_uris.add(uri)
                            articles.append(art)
                    self.logger.info(f"SQL fallback: added {len(db_articles)} more articles")
            except Exception as e:
                self.logger.warning(f"SQL search failed: {e}")

        # Apply date range filter
        pre_filter_count = len(articles)
        articles = [art for art in articles if self._is_within_date_range(art, start_date, end_date)]
        self.logger.info(f"Date filter: {pre_filter_count} -> {len(articles)} articles")

        return articles

    def _categorize_articles(self, articles: List[Dict]) -> Dict[str, List[Dict]]:
        """Categorize articles into newsletter sections based on content analysis."""
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

                for section, score in section_scores.items():
                    if section != best_section and score >= 2:
                        categorized[section].append(article)
            else:
                categorized["general"].append(article)

        return dict(categorized)

    def _select_articles_per_section(
        self,
        categorized: Dict[str, List[Dict]]
    ) -> Dict[str, List[Dict]]:
        """Select and prioritize best articles for each section."""
        selected = {}
        used_uris: Set[str] = set()

        config_limits = self.config.get('section_limits', {})
        limits = {
            "policy_regulation": config_limits.get("policy_regulation", 5),
            "models_research": config_limits.get("models_research", 5),
            "enterprise_adoption": config_limits.get("enterprise_adoption", 5),
            "market_funding": config_limits.get("market_funding", 8),
            "risk_trust": config_limits.get("risk_trust", 4),
            "weird_unusual": config_limits.get("weird_unusual", 5),  # Increased for weird shit
            "general": config_limits.get("general", 6)
        }

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
        """Score an article based on quality signals."""
        score = 0.0

        source_config = self.config.get('source_quality', {})
        recency_config = self.config.get('recency_scoring', {})
        content_config = self.config.get('content_quality', {})

        high_quality_bonus = source_config.get('high_quality_bonus', 30)
        medium_quality_bonus = source_config.get('medium_quality_bonus', 15)
        config_high_sources = set(source_config.get('high_quality_sources', []))
        config_medium_sources = set(source_config.get('medium_quality_sources', []))

        high_sources = config_high_sources or HIGH_QUALITY_SOURCES
        medium_sources = config_medium_sources or MEDIUM_QUALITY_SOURCES

        source = (article.get('news_source') or '').lower()
        if any(hs in source for hs in high_sources):
            score += high_quality_bonus
        elif any(ms in source for ms in medium_sources):
            score += medium_quality_bonus

        same_day_bonus = recency_config.get('same_day_bonus', 25)
        within_3_days_bonus = recency_config.get('within_3_days_bonus', 15)
        within_week_bonus = recency_config.get('within_week_bonus', 5)

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
                    score += same_day_bonus
                elif days_old <= 3:
                    score += within_3_days_bonus
                elif days_old <= 7:
                    score += within_week_bonus
            except:
                pass

        long_summary_bonus = content_config.get('long_summary_bonus', 10)
        min_summary_length = content_config.get('min_summary_length', 200)
        future_signal_bonus = content_config.get('future_signal_bonus', 5)
        sim_score_multiplier = content_config.get('similarity_score_multiplier', 20)

        summary = article.get('summary') or ''
        if len(summary) > min_summary_length:
            score += long_summary_bonus

        sim_score = article.get('similarity_score', 0)
        if sim_score:
            score += sim_score * sim_score_multiplier

        if article.get('future_signal') and article.get('future_signal') != 'None':
            score += future_signal_bonus

        return score

    async def _generate_newsletter(
        self,
        selected: Dict[str, List[Dict]],
        topic: str,
        ai_model_getter,
        context: Dict,
        metatrends: List[Dict] = None,
        deep_dive_analysis: str = None,
        deep_dive_topic: str = None
    ) -> str:
        """Generate newsletter content using LLM with structured sections."""

        sections_context = self._format_sections_for_prompt(selected)
        profile_context = context.get('profile_context', '')

        # Format metatrends for the prompt
        metatrends_text = ""
        if metatrends:
            metatrends_text = "\n## DETECTED METATRENDS (patterns across the corpus)\n"
            for trend in metatrends:
                metatrends_text += f"- **{trend['theme'].replace('_', ' ').title()}**: {trend['count']} articles\n"

        prompt = self._build_newsletter_prompt(
            topic, sections_context, selected, profile_context,
            metatrends_text=metatrends_text,
            deep_dive_analysis=deep_dive_analysis,
            deep_dive_topic=deep_dive_topic
        )

        try:
            model_name = self.config.get('model') or context.get('model') or 'gpt-4o'
            model = ai_model_getter(model_name)

            if model:
                if hasattr(model, 'generate') and callable(getattr(model, 'generate')):
                    response = await model.generate(prompt)
                    if hasattr(response, 'message') and hasattr(response.message, 'content'):
                        return response.message.content
                    return str(response)
                elif hasattr(model, 'acomplete'):
                    response = await model.acomplete(prompt)
                    return response.text if hasattr(response, 'text') else str(response)
        except Exception as e:
            self.logger.error(f"LLM generation failed: {e}")

        return self._generate_fallback(selected, topic)

    def _format_sections_for_prompt(self, selected: Dict[str, List[Dict]]) -> str:
        """Format selected articles by section for the LLM prompt."""
        sections = []

        section_names = {
            "policy_regulation": "POLICY & REGULATION",
            "models_research": "MODELS & RESEARCH",
            "enterprise_adoption": "ENTERPRISE & ADOPTION",
            "market_funding": "MARKET & FUNDING",
            "risk_trust": "RISK & TRUST",
            "weird_unusual": "WEIRD/UNUSUAL/FUNNY",
            "general": "GENERAL NEWS"
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
                sentiment = article.get('sentiment', '')
                signal = article.get('future_signal', '')

                if date and isinstance(date, str) and len(date) > 10:
                    date = date[:10]

                section_text += f"\n{i}. **{title}**\n"
                section_text += f"   Source: {source}"
                if date:
                    section_text += f" | Date: {date}"
                section_text += f"\n"
                if url:
                    section_text += f"   URL: {url}\n"
                if summary:
                    section_text += f"   Summary: {summary}\n"
                if sentiment and sentiment not in ('Neutral', 'Unknown'):
                    section_text += f"   Sentiment: {sentiment}\n"
                if signal and signal not in ('None', 'Unknown', ''):
                    section_text += f"   Future Signal: {signal}\n"

            sections.append(section_text)

        return "\n".join(sections)

    def _build_newsletter_prompt(
        self,
        topic: str,
        sections_context: str,
        selected: Dict[str, List[Dict]],
        profile_context: str = "",
        metatrends_text: str = "",
        deep_dive_analysis: str = None,
        deep_dive_topic: str = None
    ) -> str:
        """Build the comprehensive newsletter generation prompt."""

        total_articles = sum(len(v) for v in selected.values())

        org_context_section = ""
        if profile_context:
            org_context_section = f"""
---

## ORGANIZATIONAL CONTEXT (Tailor content to this audience!)

{profile_context}

---
"""

        # Pre-generated deep dive section
        deep_dive_section = ""
        if deep_dive_analysis:
            deep_dive_section = f"""
## PRE-GENERATED DEEP DIVE ANALYSIS

Topic: {deep_dive_topic}

{deep_dive_analysis}

**USE THIS ANALYSIS AS-IS for The Deep Dive section. Do not regenerate it.**
"""

        return f"""{org_context_section}CRITICAL INSTRUCTION - URLS ARE MANDATORY:
Format ALL citations as markdown links: **[Headline](URL)** (Source, Date)
Apply to EVERY section.

---

Role & Voice: Analyst for pragmatic decision-makers. Atlantic/Stratechery vibes. Techno-realist, skeptical of hype.

Dataset: {total_articles} curated articles. Use only these sources. ALWAYS CITE WITH MARKDOWN LINKS.

{metatrends_text}

## CATEGORIZED SOURCE ARTICLES

{sections_context}

{deep_dive_section}

---

## OUTPUT FORMAT (Markdown)

## The News

6-12 headlines grouped by theme (Policy, Models, Enterprise, Risk).
Each: **[Headline](URL)** (Source, Date) - one sentence on why it matters.
Keep punchy.

## The Deep Dive — {deep_dive_topic or 'Key Development'}

{"USE THE PRE-GENERATED ANALYSIS ABOVE. Copy it directly into this section." if deep_dive_analysis else '''
Analyze the most significant trend/claim/incident using MULTIPLE articles (not just one!):
- What happened, why now, broader context (200-300 words)
- Consensus vs outlier takes (cite multiple sources)
- Credibility assessment: what's well-supported vs speculative?
- **Strategic Insight**: 4 bullets for enterprises/policymakers/investors/citizens
'''}

## Weird Sh*t of the Week

Feature 2-3 bizarre, funny, ironic, or troubling stories from WEIRD/UNUSUAL section.
Sharp, witty commentary (Vice/Futurism style).
Evolutionary psychology, cult behavior, or cyberpunk comparisons welcome.
**MUST include at least 2 different articles with citations.**

## Must Reads (5-7)

Select 5-7 UNIQUE articles NOT already featured in The News or Deep Dive.
**[Title](URL)** (Source, Date)
1-2 line summary + why it's a must-read.

## Metatrends

Based on patterns detected across {total_articles} articles this week:
{metatrends_text if metatrends_text else "- Identify 2-3 emerging patterns"}
Brief commentary on what these patterns signal for the coming weeks.

## Market Updates

From MARKET & FUNDING section:
- **M&A / Fundraising**: deals with amounts and rationale
- **Releases / Models / Tooling**: what changed
- **Partnerships**: notable deployments
One-line "so what" for each.

---

House Rules:
- Every citation = markdown link with URL
- No article repetition across sections
- Geographic diversity
- Skeptical of hype, focused on substance"""

    def _generate_fallback(self, selected: Dict[str, List[Dict]], topic: str) -> str:
        """Generate basic newsletter when LLM is unavailable."""
        parts = [f"# {topic} Weekly Newsletter\n"]

        section_names = {
            "policy_regulation": "Policy & Regulation",
            "models_research": "Models & Research",
            "enterprise_adoption": "Enterprise & Adoption",
            "market_funding": "Market Updates",
            "risk_trust": "Risk & Trust",
            "weird_unusual": "Notable Stories",
            "general": "General News"
        }

        for section_key, articles in selected.items():
            if not articles:
                continue

            section_name = section_names.get(section_key, section_key)
            parts.append(f"\n## {section_name}\n")

            for article in articles[:5]:
                title = article.get('title', 'Untitled')
                source = article.get('news_source', 'Unknown')
                url = article.get('url') or article.get('uri', '')
                date = article.get('pub_date') or article.get('publication_date', '')

                if date and isinstance(date, str) and len(date) > 10:
                    date = date[:10]

                if url:
                    parts.append(f"- **[{title}]({url})** ({source}, {date})")
                else:
                    parts.append(f"- **{title}** ({source}, {date})")

        return "\n".join(parts)
