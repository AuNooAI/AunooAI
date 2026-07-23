"""
Article Intelligence Analyzer (Option A)
Deep analysis of individual articles with cross-referencing and verification.

This is the building block used by the Strategic Intelligence Oracle to
analyze individual articles/events in depth.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse

import litellm

from app.ai_models import resolve_litellm_call_params, extract_json_response
from app.database import get_database_instance
from app.services.auspex_tools import get_auspex_tools_service
from app.services.search_router import get_search_router, SearchSource
from app.models.media_bias import MediaBias
from app.research import Research
from app.vector_store import search_articles as vector_search_articles

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of verifying a claim against sources."""
    claim: str
    verified: bool
    confidence: float
    supporting_sources: List[str] = field(default_factory=list)
    contradicting_sources: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ArticleAnalysis:
    """Complete analysis of an article."""
    url: str
    title: str
    summary: str
    full_content: Optional[str] = None

    # Extracted information
    key_facts: List[Dict] = field(default_factory=list)
    key_entities: List[Dict] = field(default_factory=list)
    timeline: List[Dict] = field(default_factory=list)

    # Verification
    verification_results: List[VerificationResult] = field(default_factory=list)
    cross_references: List[Dict] = field(default_factory=list)
    contradictions: List[Dict] = field(default_factory=list)

    # Source quality
    source_credibility: Optional[Dict] = None
    source_bias: Optional[str] = None

    # Assessment
    confidence_score: float = 0.0
    impact_assessment: Dict = field(default_factory=dict)
    quality_gates: Dict = field(default_factory=dict)

    # Metadata
    analyzed_at: datetime = field(default_factory=datetime.now)
    related_articles_count: int = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "key_facts": self.key_facts,
            "key_entities": self.key_entities,
            "timeline": self.timeline,
            "verification": {
                "results": [
                    {
                        "claim": vr.claim,
                        "verified": vr.verified,
                        "confidence": vr.confidence,
                        "supporting_sources": vr.supporting_sources,
                        "contradicting_sources": vr.contradicting_sources,
                        "notes": vr.notes
                    }
                    for vr in self.verification_results
                ],
                "cross_references": self.cross_references,
                "contradictions": self.contradictions
            },
            "source": {
                "credibility": self.source_credibility,
                "bias": self.source_bias
            },
            "confidence_score": self.confidence_score,
            "impact_assessment": self.impact_assessment,
            "quality_gates": self.quality_gates,
            "metadata": {
                "analyzed_at": self.analyzed_at.isoformat(),
                "related_articles_count": self.related_articles_count
            }
        }


@dataclass
class AnalyzerConfig:
    """Configuration for article analysis."""
    # Verification settings
    min_cross_references: int = 2
    credibility_threshold: int = 60

    # Search settings
    max_related_articles: int = 20
    search_days_back: int = 7

    # Model settings
    analysis_model: str = "gpt-5.4"
    analysis_temperature: float = 0.3
    extraction_model: str = "gpt-5.4-mini"
    extraction_temperature: float = 0.2

    # Timeouts
    fetch_timeout: int = 30
    analysis_timeout: int = 60

    # Quality gate thresholds
    accuracy_threshold: float = 0.85
    context_threshold: float = 0.70
    sourcing_threshold: float = 0.80


class ArticleIntelligenceAnalyzer:
    """
    Analyzes individual articles with cross-referencing and verification.

    This is Option A - the building block for deep article analysis that can be:
    1. Used standalone via API for single article analysis
    2. Called by StrategicIntelligenceService for batch event analysis
    """

    def __init__(self, config: Optional[AnalyzerConfig] = None):
        self.config = config or AnalyzerConfig()
        self.db = get_database_instance()
        self.tools = get_auspex_tools_service()
        self.search_router = get_search_router()
        self.media_bias = MediaBias(self.db)
        self.research = Research(self.db)

    async def analyze_url(self, url: str, topic: Optional[str] = None) -> ArticleAnalysis:
        """
        Perform deep analysis on a single URL.

        Args:
            url: The article URL to analyze
            topic: Optional topic context for better search

        Returns:
            Complete ArticleAnalysis with verification and assessment
        """
        logger.info(f"Starting deep analysis of: {url}")

        # Initialize analysis object
        analysis = ArticleAnalysis(url=url, title="", summary="")

        try:
            # Step 1: Fetch and parse the article
            article_data = await self._fetch_article(url, topic)
            analysis.title = article_data.get("title", "")
            analysis.summary = article_data.get("summary", "")
            analysis.full_content = article_data.get("content", "")

            # Step 2: Get source credibility
            source_domain = self._extract_domain(url)
            bias_data = self.media_bias.get_bias_for_source(source_domain)
            if bias_data:
                analysis.source_credibility = {
                    "rating": bias_data.get("mbfc_credibility_rating"),
                    "factual_reporting": bias_data.get("factual_reporting"),
                    "score": self._credibility_to_score(bias_data.get("mbfc_credibility_rating", ""))
                }
                analysis.source_bias = bias_data.get("bias")

            # Step 3: Extract key facts and entities
            extraction = await self._extract_facts_and_entities(analysis)
            analysis.key_facts = extraction.get("key_facts", [])
            analysis.key_entities = extraction.get("key_entities", [])
            analysis.timeline = extraction.get("timeline", [])

            # Step 4: Find related articles for cross-referencing
            related_articles = await self._find_related_articles(
                analysis.title,
                analysis.summary,
                topic
            )
            analysis.related_articles_count = len(related_articles)
            analysis.cross_references = [
                {
                    "title": a.get("title"),
                    "source": a.get("news_source") or a.get("source"),
                    "url": a.get("url") or a.get("uri"),
                    "credibility": a.get("credibility_score", 50)
                }
                for a in related_articles[:10]
            ]

            # Step 5: Verify claims against related articles
            if analysis.key_facts and related_articles:
                verification_results = await self._verify_claims(
                    analysis.key_facts,
                    related_articles
                )
                analysis.verification_results = verification_results

                # Check for contradictions
                analysis.contradictions = await self._find_contradictions(
                    analysis,
                    related_articles
                )

            # Step 6: Assess impact
            analysis.impact_assessment = await self._assess_impact(analysis)

            # Step 7: Calculate confidence score
            analysis.confidence_score = self._calculate_confidence(analysis)

            # Step 8: Apply quality gates
            analysis.quality_gates = self._apply_quality_gates(analysis)

            logger.info(f"Analysis complete for {url}: confidence={analysis.confidence_score:.2f}")

        except Exception as e:
            logger.error(f"Error analyzing article {url}: {e}", exc_info=True)
            analysis.quality_gates = {
                "accuracy_passed": False,
                "context_passed": False,
                "sourcing_passed": False,
                "error": str(e)
            }

        return analysis

    async def analyze_cluster(
        self,
        articles: List[Dict],
        cluster_title: str,
        topic: Optional[str] = None
    ) -> ArticleAnalysis:
        """
        Analyze a cluster of related articles (an "event").

        This synthesizes information from multiple articles about the same event,
        cross-referencing and verifying across the cluster.

        Args:
            articles: List of article dicts in the cluster
            cluster_title: Descriptive title for the event
            topic: Optional topic context

        Returns:
            Synthesized ArticleAnalysis for the event
        """
        if not articles:
            raise ValueError("No articles provided for cluster analysis")

        logger.info(f"Analyzing cluster '{cluster_title}' with {len(articles)} articles")

        # Select best representative article
        representative = self._select_representative_article(articles)

        # Initialize analysis from representative
        analysis = ArticleAnalysis(
            url=representative.get("url") or representative.get("uri", ""),
            title=cluster_title,
            summary=""
        )

        try:
            # Collect all summaries for synthesis
            all_summaries = [
                a.get("summary", "") for a in articles if a.get("summary")
            ]

            # Synthesize summary from all articles
            analysis.summary = await self._synthesize_summaries(
                cluster_title,
                all_summaries
            )

            # Get credibility info for all sources
            source_credibilities = []
            for article in articles:
                source = article.get("news_source") or article.get("source", "")
                if source:
                    bias_data = self.media_bias.get_bias_for_source(source)
                    if bias_data:
                        source_credibilities.append({
                            "source": source,
                            "rating": bias_data.get("mbfc_credibility_rating"),
                            "bias": bias_data.get("bias")
                        })

            # Calculate average credibility
            if source_credibilities:
                scores = [
                    self._credibility_to_score(s.get("rating", ""))
                    for s in source_credibilities
                ]
                avg_score = sum(scores) / len(scores) if scores else 50
                analysis.source_credibility = {
                    "average_score": avg_score,
                    "sources_checked": len(source_credibilities),
                    "details": source_credibilities
                }

            # Extract facts from all articles in cluster
            extraction = await self._extract_facts_from_cluster(articles, cluster_title)
            analysis.key_facts = extraction.get("key_facts", [])
            analysis.key_entities = extraction.get("key_entities", [])
            analysis.timeline = extraction.get("timeline", [])

            # Cross-reference within cluster
            analysis.cross_references = [
                {
                    "title": a.get("title"),
                    "source": a.get("news_source") or a.get("source"),
                    "url": a.get("url") or a.get("uri")
                }
                for a in articles
            ]
            analysis.related_articles_count = len(articles)

            # Verify claims across cluster
            if analysis.key_facts:
                verification_results = await self._verify_claims_in_cluster(
                    analysis.key_facts,
                    articles
                )
                analysis.verification_results = verification_results

            # Find contradictions within cluster
            analysis.contradictions = await self._find_contradictions_in_cluster(articles)

            # Assess impact
            analysis.impact_assessment = await self._assess_impact(analysis)

            # Calculate confidence
            analysis.confidence_score = self._calculate_confidence(analysis)

            # Apply quality gates
            analysis.quality_gates = self._apply_quality_gates(analysis)

            logger.info(f"Cluster analysis complete: confidence={analysis.confidence_score:.2f}")

        except Exception as e:
            logger.error(f"Error analyzing cluster: {e}", exc_info=True)
            analysis.quality_gates = {
                "accuracy_passed": False,
                "context_passed": False,
                "sourcing_passed": False,
                "error": str(e)
            }

        return analysis

    async def _fetch_article(self, url: str, topic: Optional[str] = None) -> Dict:
        """Fetch article content, checking database first."""
        # Check if article exists in database
        try:
            article = self.db.facade.get_article_by_uri(url)
            if article:
                logger.debug(f"Found article in database: {url}")
                # Get raw content if available
                raw = self.db.facade.get_raw_article(url)
                return {
                    "title": article.get("title", ""),
                    "summary": article.get("summary", ""),
                    "content": raw.get("raw_markdown", "") if raw else "",
                    "source": article.get("news_source", ""),
                    "date": article.get("publication_date", "")
                }
        except Exception as e:
            logger.debug(f"Article not in database: {e}")

        # Fetch from web using research service
        try:
            result = await self.research.fetch_article_content(url)
            return {
                "title": result.get("title", ""),
                "summary": result.get("summary", ""),
                "content": result.get("markdown", "") or result.get("content", ""),
                "source": self._extract_domain(url),
                "date": result.get("date", "")
            }
        except Exception as e:
            logger.error(f"Failed to fetch article: {e}")
            return {"title": "", "summary": "", "content": ""}

    async def _extract_facts_and_entities(self, analysis: ArticleAnalysis) -> Dict:
        """Extract key facts, entities, and timeline from article."""
        content = analysis.full_content or analysis.summary
        if not content:
            return {"key_facts": [], "key_entities": [], "timeline": []}

        prompt = f"""Analyze this article and extract structured information.

Title: {analysis.title}
Content: {content[:8000]}

Extract:
1. KEY FACTS: Specific, verifiable factual claims (dates, numbers, quotes, events)
2. KEY ENTITIES: People, organizations, locations mentioned with their roles
3. TIMELINE: Chronological sequence of events if applicable

Respond with JSON:
{{
    "key_facts": [
        {{"fact": "specific claim", "type": "statistic|quote|event|decision", "importance": "high|medium|low"}}
    ],
    "key_entities": [
        {{"name": "Entity Name", "type": "person|organization|location", "role": "their role in the story"}}
    ],
    "timeline": [
        {{"time": "date or time reference", "event": "what happened"}}
    ]
}}"""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(self.config.extraction_model),
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.extraction_temperature,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            result = extract_json_response(response.choices[0].message.content)
            return result

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return {"key_facts": [], "key_entities": [], "timeline": []}

    async def _extract_facts_from_cluster(
        self,
        articles: List[Dict],
        cluster_title: str
    ) -> Dict:
        """Extract and consolidate facts from multiple articles."""
        # Combine article information
        combined_content = "\n\n---\n\n".join([
            f"Source: {a.get('news_source', 'Unknown')}\nTitle: {a.get('title', '')}\nSummary: {a.get('summary', '')}"
            for a in articles[:15]  # Limit for context
        ])

        prompt = f"""Analyze these related articles about "{cluster_title}" and extract consolidated information.

Articles:
{combined_content[:12000]}

Extract CONSOLIDATED information (merge duplicates, note where sources agree/disagree):
1. KEY FACTS: Specific claims that appear across sources (note how many sources confirm each)
2. KEY ENTITIES: People, organizations, locations with their roles
3. TIMELINE: Chronological sequence if applicable

Respond with JSON:
{{
    "key_facts": [
        {{"fact": "specific claim", "sources_count": 3, "importance": "high|medium|low"}}
    ],
    "key_entities": [
        {{"name": "Entity Name", "type": "person|organization|location", "role": "role", "mentions": 5}}
    ],
    "timeline": [
        {{"time": "date/time", "event": "what happened"}}
    ]
}}"""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(self.config.extraction_model),
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.extraction_temperature,
                max_tokens=3000,
                response_format={"type": "json_object"}
            )

            return extract_json_response(response.choices[0].message.content)

        except Exception as e:
            logger.error(f"Cluster extraction failed: {e}")
            return {"key_facts": [], "key_entities": [], "timeline": []}

    async def _find_related_articles(
        self,
        title: str,
        summary: str,
        topic: Optional[str] = None
    ) -> List[Dict]:
        """Find related articles for cross-referencing."""
        query = f"{title} {summary[:200]}"

        try:
            # Search internal database via vector search
            results = await self.search_router.execute_routed_search(
                query=query,
                topic=topic or "general",
                limit=self.config.max_related_articles,
                force_source=SearchSource.HYBRID,
                tools_service=self.tools
            )

            return results.get("articles", [])

        except Exception as e:
            logger.error(f"Related article search failed: {e}")
            return []

    async def _verify_claims(
        self,
        facts: List[Dict],
        related_articles: List[Dict]
    ) -> List[VerificationResult]:
        """Verify extracted facts against related articles."""
        if not facts or not related_articles:
            return []

        # Build context from related articles
        context = "\n".join([
            f"[{a.get('news_source', 'Unknown')}]: {a.get('title', '')} - {a.get('summary', '')[:300]}"
            for a in related_articles[:10]
        ])

        facts_text = "\n".join([
            f"{i+1}. {f.get('fact', '')}"
            for i, f in enumerate(facts[:10])
        ])

        prompt = f"""Verify these claims against the related articles.

CLAIMS TO VERIFY:
{facts_text}

RELATED ARTICLES:
{context}

For each claim, determine:
1. Is it SUPPORTED by any of these sources?
2. Is it CONTRADICTED by any of these sources?
3. What's the confidence level (0.0-1.0)?

Respond with JSON:
{{
    "verifications": [
        {{
            "claim_index": 1,
            "verified": true,
            "confidence": 0.9,
            "supporting_sources": ["Reuters", "AP"],
            "contradicting_sources": [],
            "notes": "Confirmed by multiple sources"
        }}
    ]
}}"""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(self.config.analysis_model),
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.analysis_temperature,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            result = extract_json_response(response.choices[0].message.content)

            verification_results = []
            for v in result.get("verifications", []):
                idx = v.get("claim_index", 1) - 1
                if 0 <= idx < len(facts):
                    verification_results.append(VerificationResult(
                        claim=facts[idx].get("fact", ""),
                        verified=v.get("verified", False),
                        confidence=v.get("confidence", 0.5),
                        supporting_sources=v.get("supporting_sources", []),
                        contradicting_sources=v.get("contradicting_sources", []),
                        notes=v.get("notes", "")
                    ))

            return verification_results

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return []

    async def _verify_claims_in_cluster(
        self,
        facts: List[Dict],
        articles: List[Dict]
    ) -> List[VerificationResult]:
        """Verify claims within an article cluster."""
        # Similar to _verify_claims but optimized for cluster context
        return await self._verify_claims(facts, articles)

    async def _find_contradictions(
        self,
        analysis: ArticleAnalysis,
        related_articles: List[Dict]
    ) -> List[Dict]:
        """Find contradictions between the article and related coverage."""
        if not related_articles:
            return []

        context = "\n".join([
            f"[{a.get('news_source', 'Unknown')}]: {a.get('summary', '')[:400]}"
            for a in related_articles[:8]
        ])

        prompt = f"""Compare the main article with related coverage and identify any contradictions.

MAIN ARTICLE:
Title: {analysis.title}
Summary: {analysis.summary}

RELATED ARTICLES:
{context}

Identify any contradictions (different facts, different interpretations, conflicting claims).

Respond with JSON:
{{
    "contradictions": [
        {{
            "topic": "what the contradiction is about",
            "main_article_says": "what the main article claims",
            "other_source": "source name",
            "other_source_says": "what the other source claims",
            "severity": "major|minor",
            "possible_explanation": "why they might differ"
        }}
    ]
}}"""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(self.config.analysis_model),
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.analysis_temperature,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )

            result = extract_json_response(response.choices[0].message.content)
            return result.get("contradictions", [])

        except Exception as e:
            logger.error(f"Contradiction analysis failed: {e}")
            return []

    async def _find_contradictions_in_cluster(
        self,
        articles: List[Dict]
    ) -> List[Dict]:
        """Find contradictions within an article cluster."""
        if len(articles) < 2:
            return []

        summaries = "\n".join([
            f"[{a.get('news_source', 'Unknown')}]: {a.get('summary', '')[:400]}"
            for a in articles[:10]
        ])

        prompt = f"""Analyze these articles about the same event and identify any contradictions.

ARTICLES:
{summaries}

Identify contradictions (different facts, numbers, quotes, or interpretations).

Respond with JSON:
{{
    "contradictions": [
        {{
            "topic": "what the contradiction is about",
            "source_a": "first source name",
            "source_a_says": "what source A claims",
            "source_b": "second source name",
            "source_b_says": "what source B claims",
            "severity": "major|minor"
        }}
    ]
}}"""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(self.config.analysis_model),
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.analysis_temperature,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )

            result = extract_json_response(response.choices[0].message.content)
            return result.get("contradictions", [])

        except Exception as e:
            logger.error(f"Cluster contradiction analysis failed: {e}")
            return []

    async def _synthesize_summaries(
        self,
        title: str,
        summaries: List[str]
    ) -> str:
        """Synthesize multiple summaries into one coherent summary."""
        if not summaries:
            return ""

        if len(summaries) == 1:
            return summaries[0]

        combined = "\n---\n".join(summaries[:10])

        prompt = f"""Synthesize these summaries about "{title}" into one comprehensive summary.

SUMMARIES:
{combined}

Write a single, coherent summary that captures the key information from all sources.
Be factual and balanced. Note if sources disagree on key points.
Keep it to 2-3 paragraphs."""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(self.config.extraction_model),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Summary synthesis failed: {e}")
            return summaries[0] if summaries else ""

    async def _assess_impact(self, analysis: ArticleAnalysis) -> Dict:
        """Assess the strategic impact of the article/event."""
        prompt = f"""Assess the strategic impact of this news event.

Title: {analysis.title}
Summary: {analysis.summary}
Key Facts: {json.dumps(analysis.key_facts[:5], indent=2)}
Sources: {analysis.related_articles_count} related articles found

Rate on these dimensions (0.0-1.0):
1. URGENCY: How time-sensitive is this? Does it require immediate attention?
2. SCALE: How many people/regions/sectors are affected?
3. CONSEQUENCE: What are the potential economic, political, social impacts?

Also categorize the strategic domain:
- economic_policy, geopolitics, security, technology, health, environment, social, other

Respond with JSON:
{{
    "urgency_score": 0.7,
    "urgency_rationale": "why this score",
    "scale_score": 0.8,
    "scale_rationale": "why this score",
    "consequence_score": 0.75,
    "consequence_rationale": "why this score",
    "overall_importance": 0.75,
    "strategic_category": "economic_policy",
    "key_stakeholders": ["list of who needs to know"],
    "time_sensitivity": "immediate|short_term|medium_term|long_term"
}}"""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(self.config.analysis_model),
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.analysis_temperature,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )

            return extract_json_response(response.choices[0].message.content)

        except Exception as e:
            logger.error(f"Impact assessment failed: {e}")
            return {
                "urgency_score": 0.5,
                "scale_score": 0.5,
                "consequence_score": 0.5,
                "overall_importance": 0.5,
                "error": str(e)
            }

    def _calculate_confidence(self, analysis: ArticleAnalysis) -> float:
        """Calculate overall confidence score for the analysis."""
        scores = []

        # Factor 1: Source credibility
        if analysis.source_credibility:
            cred_score = analysis.source_credibility.get("score") or \
                         analysis.source_credibility.get("average_score", 50)
            scores.append(cred_score / 100)

        # Factor 2: Verification success rate
        if analysis.verification_results:
            verified_count = sum(1 for v in analysis.verification_results if v.verified)
            total = len(analysis.verification_results)
            scores.append(verified_count / total if total > 0 else 0.5)

        # Factor 3: Cross-reference count
        if analysis.related_articles_count > 0:
            # More sources = higher confidence, capped at 10
            xref_score = min(analysis.related_articles_count / 10, 1.0)
            scores.append(xref_score)

        # Factor 4: Contradiction penalty
        if analysis.contradictions:
            major_contradictions = sum(
                1 for c in analysis.contradictions
                if c.get("severity") == "major"
            )
            contradiction_penalty = max(0, 1 - (major_contradictions * 0.15))
            scores.append(contradiction_penalty)

        # Calculate weighted average
        if scores:
            return sum(scores) / len(scores)
        return 0.5

    def _apply_quality_gates(self, analysis: ArticleAnalysis) -> Dict:
        """Apply BBC/Wiley quality gates to the analysis."""
        gates = {
            "accuracy_passed": True,
            "context_passed": True,
            "sourcing_passed": True,
            "issues": []
        }

        # Accuracy gate
        if analysis.verification_results:
            verified_ratio = sum(1 for v in analysis.verification_results if v.verified) / len(analysis.verification_results)
            if verified_ratio < self.config.accuracy_threshold:
                gates["accuracy_passed"] = False
                gates["issues"].append(f"Only {verified_ratio:.0%} of claims verified (threshold: {self.config.accuracy_threshold:.0%})")

        # Check for major contradictions
        major_contradictions = [c for c in analysis.contradictions if c.get("severity") == "major"]
        if major_contradictions:
            gates["accuracy_passed"] = False
            gates["issues"].append(f"{len(major_contradictions)} major contradiction(s) found")

        # Context gate
        if analysis.related_articles_count < self.config.min_cross_references:
            gates["context_passed"] = False
            gates["issues"].append(f"Only {analysis.related_articles_count} cross-references (minimum: {self.config.min_cross_references})")

        # Sourcing gate
        if analysis.source_credibility:
            score = analysis.source_credibility.get("score") or \
                    analysis.source_credibility.get("average_score", 0)
            if score < self.config.credibility_threshold:
                gates["sourcing_passed"] = False
                gates["issues"].append(f"Source credibility {score} below threshold {self.config.credibility_threshold}")

        # Overall
        gates["all_passed"] = all([
            gates["accuracy_passed"],
            gates["context_passed"],
            gates["sourcing_passed"]
        ])

        return gates

    def _select_representative_article(self, articles: List[Dict]) -> Dict:
        """Select the best representative article from a cluster."""
        if not articles:
            return {}

        # Score each article
        scored = []
        for article in articles:
            score = 0

            # Prefer longer summaries
            summary_len = len(article.get("summary", ""))
            score += min(summary_len / 500, 1) * 2

            # Prefer higher credibility
            cred = article.get("credibility_score", 50)
            score += (cred / 100) * 3

            # Prefer more recent
            # (would need date parsing - simplified here)
            score += 1

            scored.append((score, article))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else articles[0]

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except:
            return ""

    def _credibility_to_score(self, rating: str) -> int:
        """Convert MBFC credibility rating to numeric score."""
        rating_map = {
            "Very High": 95,
            "High": 85,
            "Mostly Factual": 70,
            "Mixed": 50,
            "Low": 30,
            "Very Low": 15
        }
        return rating_map.get(rating, 50)


# Singleton instance
_analyzer_instance: Optional[ArticleIntelligenceAnalyzer] = None


def get_article_intelligence_analyzer() -> ArticleIntelligenceAnalyzer:
    """Get the global article intelligence analyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = ArticleIntelligenceAnalyzer()
    return _analyzer_instance
