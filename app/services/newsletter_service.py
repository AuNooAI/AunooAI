"""
Newsletter Generation Service with Streaming Progress v3.0

Provides dynamic newsletter generation with LLM-proposed sections.
No hardcoded sections or article limits - sections are determined by actual content.
"""

import asyncio
import json
import logging
import re
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


@dataclass
class NewsletterConfig:
    """Configuration for newsletter generation."""
    days_back: int = 7
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    model: str = "gpt-4o"
    max_articles: int = 2000  # High limit - no artificial cap


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

        Uses dynamic LLM-proposed sections based on actual content.
        If topic is '__all__', generates cross-topic newsletter from all topics.

        Yields progress updates for each stage:
        - fetching: Gathering ALL articles from database and vector store
        - analyzing: LLM proposes thematic sections
        - deep_dive: Generating consensus/credibility analysis
        - writing: Producing final newsletter content

        Final yield contains the complete newsletter.
        """
        if config is None:
            config = NewsletterConfig()

        # Handle cross-topic mode: __all__ means search all topics
        is_cross_topic = (topic == '__all__')
        topic_for_query = None if is_cross_topic else topic
        topic_display = "All Topics" if is_cross_topic else topic

        import time
        start_time = time.time()

        # Parse dates
        start_date, end_date = self._parse_dates(config)

        # Stage 1: Fetching ALL articles (no artificial limit)
        yield {
            "stage": "fetching",
            "status": "started",
            "progress": 0.0,
            "message": f"Gathering articles from database{' (cross-topic)' if is_cross_topic else ''}..."
        }

        articles = await self._fetch_articles(topic_for_query, start_date, end_date, config.max_articles)

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
                "error": f"No articles found for topic '{topic_display}' in the specified date range"
            }
            return

        if not self.ai_model_getter:
            yield {
                "stage": "error",
                "error": "AI model not available for dynamic section generation"
            }
            return

        # Stage 2: Score and rank articles, then LLM proposes sections
        yield {
            "stage": "analyzing",
            "status": "started",
            "progress": 0.0,
            "message": "Analyzing articles and proposing sections..."
        }

        # Score and rank all articles
        scored_articles = [(self._score_article(art), art) for art in articles]
        scored_articles.sort(key=lambda x: x[0], reverse=True)
        ranked_articles = [art for score, art in scored_articles]

        # LLM proposes sections based on content
        proposed_sections = await self._propose_sections(ranked_articles, topic_display, config.model)

        if not proposed_sections:
            self.logger.warning("LLM section proposal failed, using fallback")
            proposed_sections = self._fallback_section_proposal(ranked_articles)

        # Limit each section to best 4-7 articles based on corpus size
        proposed_sections = self._limit_section_articles(proposed_sections, len(ranked_articles))

        section_counts = {s['name']: len(s.get('articles', [])) for s in proposed_sections}
        total_used = sum(len(s.get('articles', [])) for s in proposed_sections)

        yield {
            "stage": "analyzing",
            "status": "completed",
            "progress": 1.0,
            "message": f"Organized into {len(proposed_sections)} sections",
            "section_counts": section_counts,
            "sections": [s['name'] for s in proposed_sections]
        }

        # Stage 3: Select deep dive topic from sections
        deep_dive_topic, deep_dive_articles = self._select_deep_dive_from_sections(
            proposed_sections, ranked_articles
        )

        # Stage 4: Deep Dive Analysis
        deep_dive_analysis = None
        if deep_dive_articles:
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

        # Stage 5: Writing Newsletter with dynamic sections
        yield {
            "stage": "writing",
            "status": "started",
            "progress": 0.0,
            "message": "Generating newsletter content..."
        }

        newsletter_content = await self._generate_newsletter_dynamic(
            proposed_sections, ranked_articles, topic_display, config.model,
            deep_dive_analysis=deep_dive_analysis,
            deep_dive_topic=deep_dive_topic,
            profile_context=profile_context
        )

        execution_time = int((time.time() - start_time) * 1000)

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
                "sections": [s['name'] for s in proposed_sections],
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
        topic: Optional[str],
        start_date: datetime,
        end_date: datetime,
        max_articles: int
    ) -> List[Dict]:
        """Fetch articles from database and vector store.

        If topic is None (cross-topic mode), fetches articles from all topics.
        """
        articles = []
        seen_uris: Set[str] = set()
        topic_display = topic if topic else "All Topics"

        # Strategy 1: Database with date range
        try:
            if hasattr(self.db, 'facade') and hasattr(self.db.facade, 'get_recent_articles_by_topic'):
                db_articles = self.db.facade.get_recent_articles_by_topic(
                    topic_name=topic,  # None for cross-topic mode
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
                    self.logger.info(f"DB search ({topic_display}): {len(db_articles)} articles")
        except Exception as e:
            self.logger.warning(f"DB search failed: {e}")

        # Strategy 2: Vector search (for cross-topic, use general queries)
        if self.vector_store and len(articles) < 100:
            try:
                if topic:
                    search_queries = [
                        topic,
                        f"latest {topic} news",
                        f"{topic} regulation policy",
                        f"{topic} funding investment",
                        f"{topic} research breakthrough"
                    ]
                else:
                    # Cross-topic search queries
                    search_queries = [
                        "latest breaking news",
                        "technology trends developments",
                        "policy regulation updates",
                        "economic market analysis",
                        "research innovation breakthrough"
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

    async def _propose_sections(
        self,
        articles: List[Dict],
        topic: str,
        model_name: str
    ) -> List[Dict]:
        """Have LLM analyze articles and propose thematic sections dynamically."""

        # Format articles as numbered list with key info
        articles_summary = self._format_articles_for_section_proposal(articles)

        prompt = f"""Analyze these {len(articles)} articles about "{topic}" from the past week.

Propose 5-8 thematic sections that best organize this week's news into a compelling newsletter.

For each section, provide:
- name: A catchy 2-4 word title (e.g., "Regulatory Reckoning", "Funding Frenzy", "The Weird & Wonderful")
- description: One sentence on what this section covers
- article_indices: List of article numbers (1-indexed) that belong in this section

## ARTICLES TO ORGANIZE:

{articles_summary}

## GUIDELINES:

1. Every article should be assigned to exactly ONE section (no duplicates)
2. Create sections based on what's ACTUALLY in the articles - don't force categories
3. Include a section for unusual/surprising/funny stories if any exist
4. Include a market/deals section if there are funding, M&A, or partnership articles
5. Balance sections reasonably - aim for 5-15 articles per section, but don't force it
6. If an article doesn't fit well anywhere, put it in a "Notable Mentions" or "Quick Hits" section
7. Section names should be engaging and specific to the content (not generic like "Tech News")

## OUTPUT FORMAT:

Return ONLY valid JSON array, no other text:
[
  {{"name": "Section Name", "description": "What this section covers", "article_indices": [1, 2, 5, 8]}},
  {{"name": "Another Section", "description": "Description here", "article_indices": [3, 4, 6, 7]}}
]

Ensure ALL articles (1 through {len(articles)}) are assigned to exactly one section."""

        try:
            model = self.ai_model_getter(model_name)

            if model:
                if hasattr(model, 'generate') and callable(getattr(model, 'generate')):
                    response = await model.generate(prompt, max_tokens=4000)
                    if hasattr(response, 'message') and hasattr(response.message, 'content'):
                        response_text = response.message.content
                    else:
                        response_text = str(response)
                elif hasattr(model, 'acomplete'):
                    response = await model.acomplete(prompt, max_tokens=4000)
                    response_text = response.text if hasattr(response, 'text') else str(response)
                else:
                    return None

                # Parse JSON response
                sections = self._parse_section_proposal(response_text, articles)
                return sections

        except Exception as e:
            self.logger.error(f"Section proposal failed: {e}")

        return None

    def _format_articles_for_section_proposal(self, articles: List[Dict], max_articles: int = 200) -> str:
        """Format articles as numbered list for section proposal."""
        lines = []

        for i, article in enumerate(articles[:max_articles], 1):
            title = article.get('title', 'Untitled')
            source = article.get('news_source', 'Unknown')
            date = article.get('pub_date') or article.get('publication_date', '')
            summary = (article.get('summary') or '')[:150]

            if date and isinstance(date, str) and len(date) > 10:
                date = date[:10]

            line = f"{i}. [{source}] {title}"
            if summary:
                line += f" — {summary}"
            lines.append(line)

        if len(articles) > max_articles:
            lines.append(f"\n... and {len(articles) - max_articles} more articles")

        return "\n".join(lines)

    def _parse_section_proposal(self, response_text: str, articles: List[Dict]) -> List[Dict]:
        """Parse LLM response into section structure with article assignments."""

        try:
            # Look for JSON array in response
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                sections_data = json.loads(json_match.group())
            else:
                self.logger.warning("No JSON array found in section proposal response")
                return None
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse section proposal JSON: {e}")
            return None

        # Convert to our format with actual article objects
        sections = []
        used_indices = set()

        for section_data in sections_data:
            name = section_data.get('name', 'Untitled Section')
            description = section_data.get('description', '')
            indices = section_data.get('article_indices', [])

            # Filter to valid, unused indices
            valid_indices = []
            section_articles = []

            for idx in indices:
                if isinstance(idx, int) and 1 <= idx <= len(articles) and idx not in used_indices:
                    valid_indices.append(idx)
                    used_indices.add(idx)
                    section_articles.append(articles[idx - 1])

            if section_articles:
                sections.append({
                    'name': name,
                    'description': description,
                    'article_indices': valid_indices,
                    'articles': section_articles
                })

        # Check for unassigned articles and add to "Notable Mentions"
        all_indices = set(range(1, len(articles) + 1))
        unassigned = all_indices - used_indices

        if unassigned and len(unassigned) <= len(articles) * 0.3:
            unassigned_articles = [articles[i - 1] for i in sorted(unassigned)]
            sections.append({
                'name': 'Notable Mentions',
                'description': 'Other noteworthy stories from this week',
                'article_indices': sorted(unassigned),
                'articles': unassigned_articles
            })
        elif unassigned:
            self.logger.warning(f"{len(unassigned)} articles not assigned to any section")

        return sections if sections else None

    def _limit_section_articles(
        self,
        sections: List[Dict],
        total_articles: int
    ) -> List[Dict]:
        """Limit each section to best 4-7 articles based on score.

        Scales the limit based on total corpus size:
        - <30 articles: 4 per section
        - <60 articles: 5 per section
        - <100 articles: 6 per section
        - 100+ articles: 7 per section
        """
        # Dynamic limit based on total corpus size
        if total_articles < 30:
            max_per_section = 4
        elif total_articles < 60:
            max_per_section = 5
        elif total_articles < 100:
            max_per_section = 6
        else:
            max_per_section = 7

        self.logger.info(f"Limiting sections to {max_per_section} articles each (corpus size: {total_articles})")

        limited_sections = []
        for section in sections:
            articles = section.get('articles', [])

            if len(articles) <= max_per_section:
                # Keep all if under limit
                limited_sections.append(section)
            else:
                # Score and keep top N
                scored = [(self._score_article(a), a) for a in articles]
                scored.sort(key=lambda x: x[0], reverse=True)
                top_articles = [a for _, a in scored[:max_per_section]]

                limited_sections.append({
                    'name': section['name'],
                    'description': section.get('description', ''),
                    'articles': top_articles
                })
                self.logger.debug(f"Section '{section['name']}': {len(articles)} -> {len(top_articles)} articles")

        return limited_sections

    def _fallback_section_proposal(self, articles: List[Dict]) -> List[Dict]:
        """Create simple sections when LLM proposal fails."""
        category_groups = defaultdict(list)

        for i, article in enumerate(articles):
            category = article.get('category') or 'General'
            category_groups[category].append((i + 1, article))

        sections = []
        for category, indexed_articles in category_groups.items():
            sections.append({
                'name': category.title(),
                'description': f'Articles in {category} category',
                'article_indices': [idx for idx, _ in indexed_articles],
                'articles': [art for _, art in indexed_articles]
            })

        return sections if sections else [{
            'name': 'This Week\'s News',
            'description': 'All articles from this week',
            'article_indices': list(range(1, len(articles) + 1)),
            'articles': articles
        }]

    def _select_deep_dive_from_sections(
        self,
        sections: List[Dict],
        articles: List[Dict]
    ) -> Tuple[str, List[Dict]]:
        """Select deep dive topic from the most interesting section."""

        if not sections:
            return "Key Developments", articles[:10]

        best_section = None
        best_score = 0

        for section in sections:
            if section['name'].lower() in ('notable mentions', 'quick hits', 'other'):
                continue

            section_articles = section.get('articles', [])
            if not section_articles:
                continue

            score = 0
            for art in section_articles:
                source = (art.get('news_source') or '').lower()
                if any(hs in source for hs in HIGH_QUALITY_SOURCES):
                    score += 3
                elif any(ms in source for ms in MEDIUM_QUALITY_SOURCES):
                    score += 1
                else:
                    score += 0.5

            score += min(len(section_articles), 10) * 0.5

            if score > best_score:
                best_score = score
                best_section = section

        if best_section:
            return best_section['name'], best_section['articles'][:10]

        return sections[0]['name'], sections[0].get('articles', [])[:10]

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

    async def _generate_newsletter_dynamic(
        self,
        sections: List[Dict],
        all_articles: List[Dict],
        topic: str,
        model_name: str,
        deep_dive_analysis: str = None,
        deep_dive_topic: str = None,
        profile_context: str = ""
    ) -> str:
        """Generate newsletter using LLM-proposed sections."""

        # Format sections for prompt
        sections_context = self._format_dynamic_sections_for_prompt(sections)
        total_articles = sum(len(s.get('articles', [])) for s in sections)

        org_context_section = ""
        if profile_context:
            org_context_section = f"""
---

## ORGANIZATIONAL CONTEXT (Tailor content to this audience!)

{profile_context}

---
"""

        deep_dive_section = ""
        if deep_dive_analysis:
            deep_dive_section = f"""
## PRE-GENERATED DEEP DIVE ANALYSIS

Topic: {deep_dive_topic}

{deep_dive_analysis}

**USE THIS ANALYSIS AS-IS for The Deep Dive section. Do not regenerate it.**
"""

        # Build section instructions dynamically
        section_instructions = ""
        for section in sections:
            name = section['name']
            desc = section.get('description', '')
            count = len(section.get('articles', []))
            section_instructions += f"\n## {name}\n{desc}\nYou have {count} articles for this section. Include the most important ones with citations.\n"

        prompt = f"""{org_context_section}CRITICAL INSTRUCTION - URLS ARE MANDATORY:
Format ALL citations as markdown links: **[Headline](URL)** (Source, Date)
Apply to EVERY section.

---

Role & Voice: Analyst for pragmatic decision-makers. Atlantic/Stratechery vibes. Techno-realist, skeptical of hype.

Dataset: {total_articles} curated articles organized into {len(sections)} sections. Use only these sources. ALWAYS CITE WITH MARKDOWN LINKS.

## SOURCE ARTICLES BY SECTION

{sections_context}

{deep_dive_section}

---

## OUTPUT FORMAT (Markdown)

Write a newsletter with the following sections. Each section should include relevant articles with proper citations.

{section_instructions}

## The Deep Dive — {deep_dive_topic or 'Key Development'}

{"USE THE PRE-GENERATED ANALYSIS ABOVE. Copy it directly into this section." if deep_dive_analysis else '''
Select the most significant story and analyze using MULTIPLE articles:
- What happened, why now, broader context (200-300 words)
- Consensus vs outlier takes (cite multiple sources)
- Credibility assessment: what's well-supported vs speculative?
- **Strategic Insight**: 4 bullets for enterprises/policymakers/investors/citizens
'''}

---

House Rules:
- Every citation = markdown link with URL
- No article repetition across sections
- Geographic diversity where possible
- Skeptical of hype, focused on substance
- Don't include sections with no relevant articles"""

        try:
            model = self.ai_model_getter(model_name)
            if model:
                if hasattr(model, 'generate'):
                    response = await model.generate(prompt, max_tokens=16000)
                    if hasattr(response, 'message') and hasattr(response.message, 'content'):
                        return response.message.content
                    return str(response)
                elif hasattr(model, 'acomplete'):
                    response = await model.acomplete(prompt)
                    return response.text if hasattr(response, 'text') else str(response)
        except Exception as e:
            self.logger.error(f"Newsletter generation failed: {e}")

        return self._generate_fallback_dynamic(sections, topic)

    def _format_dynamic_sections_for_prompt(self, sections: List[Dict]) -> str:
        """Format LLM-proposed sections for the newsletter prompt."""
        output = []

        for section in sections:
            name = section['name']
            desc = section.get('description', '')
            articles = section.get('articles', [])

            section_text = f"\n### {name.upper()}"
            if desc:
                section_text += f"\n({desc})"
            section_text += f"\n({len(articles)} articles)\n"

            for i, article in enumerate(articles, 1):
                title = article.get('title', 'Untitled')
                source = article.get('news_source', 'Unknown')
                url = article.get('url') or article.get('uri', '')
                date = article.get('pub_date') or article.get('publication_date', '')
                summary = (article.get('summary') or '')[:400]

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

            output.append(section_text)

        return "\n".join(output)

    def _generate_fallback_dynamic(self, sections: List[Dict], topic: str) -> str:
        """Generate basic newsletter when LLM is unavailable (dynamic sections version)."""
        parts = [f"# {topic} Weekly Newsletter\n"]

        for section in sections:
            name = section.get('name', 'News')
            articles = section.get('articles', [])

            if not articles:
                continue

            parts.append(f"\n## {name}\n")

            for article in articles[:10]:
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
