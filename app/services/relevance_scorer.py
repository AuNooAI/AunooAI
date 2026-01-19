"""
Relevance Scorer Service
Scores articles for relevance to research queries and objectives using LLM-based evaluation.

This service helps filter out irrelevant search results before synthesis,
ensuring only highly relevant articles contribute to the final research report.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

import litellm

logger = logging.getLogger(__name__)


@dataclass
class RelevanceScoringConfig:
    """Configuration for relevance scoring."""

    # Scoring thresholds
    relevance_threshold: float = 0.6  # Minimum score to include article
    high_relevance_threshold: float = 0.8  # Score for prioritized articles

    # Model settings
    model: str = "gpt-4.1-mini"  # Fast model for scoring
    temperature: float = 0.1  # Low temperature for consistent scoring

    # Batching
    batch_size: int = 10  # Articles per batch for efficiency
    max_concurrent_batches: int = 3  # Parallel batch processing

    # Timeouts
    timeout_per_batch: int = 30  # Seconds per batch


class RelevanceScorer:
    """Scores articles for relevance to research queries using LLM evaluation."""

    def __init__(self, config: Optional[RelevanceScoringConfig] = None):
        self.config = config or RelevanceScoringConfig()

    async def score_articles(
        self,
        articles: List[Dict],
        query: str,
        objectives: List[Dict],
        filter_below_threshold: bool = True
    ) -> List[Dict]:
        """
        Score articles for relevance and optionally filter irrelevant ones.

        Args:
            articles: List of article dictionaries
            query: The main research query
            objectives: List of research objective dictionaries
            filter_below_threshold: Whether to remove low-scoring articles

        Returns:
            List of articles with relevance_score added, optionally filtered
        """
        if not articles:
            return []

        logger.info(f"Scoring {len(articles)} articles for relevance to: {query[:50]}...")

        # Create batches for efficient processing
        batches = self._create_batches(articles)

        # Format objectives for prompt
        objectives_text = self._format_objectives(objectives)

        # Process batches with concurrency control
        semaphore = asyncio.Semaphore(self.config.max_concurrent_batches)

        async def process_batch_with_semaphore(batch: List[Dict], batch_idx: int):
            async with semaphore:
                return await self._score_batch(batch, query, objectives_text, batch_idx)

        # Process all batches
        tasks = [
            process_batch_with_semaphore(batch, i)
            for i, batch in enumerate(batches)
        ]

        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine results
        scored_articles = []
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.warning(f"Batch {i} scoring failed: {result}")
                # On failure, assign neutral score and keep articles
                for article in batches[i]:
                    article["relevance_score"] = 0.5
                    article["relevance_reasoning"] = "Scoring failed, using default"
                    scored_articles.append(article)
            else:
                scored_articles.extend(result)

        # Sort by relevance score (highest first)
        scored_articles.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

        # Apply filtering if requested
        if filter_below_threshold:
            original_count = len(scored_articles)
            scored_articles = [
                a for a in scored_articles
                if a.get("relevance_score", 0) >= self.config.relevance_threshold
            ]
            filtered_count = original_count - len(scored_articles)
            if filtered_count > 0:
                logger.info(
                    f"Relevance filtering: {original_count} -> {len(scored_articles)} articles "
                    f"(removed {filtered_count} below threshold {self.config.relevance_threshold})"
                )

        # Log statistics
        self._log_statistics(scored_articles)

        return scored_articles

    def _create_batches(self, articles: List[Dict]) -> List[List[Dict]]:
        """Split articles into batches for processing."""
        batches = []
        for i in range(0, len(articles), self.config.batch_size):
            batches.append(articles[i:i + self.config.batch_size])
        return batches

    def _format_objectives(self, objectives: List[Dict]) -> str:
        """Format objectives for the scoring prompt."""
        if not objectives:
            return "No specific objectives provided"

        lines = []
        for obj in objectives:
            obj_id = obj.get("id", "unknown")
            objective = obj.get("objective", "")
            priority = obj.get("priority", "medium")
            lines.append(f"- [{obj_id}] ({priority} priority): {objective}")

        return "\n".join(lines)

    async def _score_batch(
        self,
        batch: List[Dict],
        query: str,
        objectives_text: str,
        batch_idx: int
    ) -> List[Dict]:
        """Score a batch of articles using LLM."""

        # Prepare article summaries for scoring
        article_summaries = []
        for i, article in enumerate(batch):
            summary = {
                "idx": i,
                "title": article.get("title", "Untitled")[:200],
                "summary": (article.get("summary") or article.get("content", ""))[:400],
                "source": article.get("news_source") or article.get("source", "Unknown"),
                "date": article.get("publication_date", "Unknown"),
                "category": article.get("category", "Unknown")
            }
            article_summaries.append(summary)

        system_prompt = """You are a research relevance evaluator. Your job is to score articles for relevance to a research query and objectives.

For each article, provide:
1. A relevance score from 0.0 to 1.0 where:
   - 0.0-0.3: Not relevant (different topic, geography, or time period)
   - 0.4-0.5: Tangentially related (some keyword overlap but different focus)
   - 0.6-0.7: Moderately relevant (addresses related aspects)
   - 0.8-0.9: Highly relevant (directly addresses query or objectives)
   - 1.0: Perfectly relevant (exactly what the research is looking for)

2. A brief reasoning (1 sentence) explaining the score

Consider:
- Geographic specificity: An article about Japan is NOT relevant to a query about Minnesota
- Topic specificity: An article about general AI is NOT relevant to a query about specific company deployments
- Time relevance: Historical articles may be less relevant to queries about current developments
- Entity match: Articles mentioning the same entities/organizations are more relevant

Respond with JSON array:
[{"idx": 0, "score": 0.85, "reasoning": "Directly discusses the topic"}]"""

        user_prompt = f"""Research Query: {query}

Research Objectives:
{objectives_text}

Articles to Score:
{json.dumps(article_summaries, indent=2)}

Score each article for relevance. Return JSON array with scores."""

        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=self.config.temperature,
                    max_tokens=1000,
                    response_format={"type": "json_object"}
                ),
                timeout=self.config.timeout_per_batch
            )

            result_text = response.choices[0].message.content

            # Parse scores - handle both direct array and wrapped object
            try:
                parsed = json.loads(result_text)
                if isinstance(parsed, list):
                    scores = parsed
                elif isinstance(parsed, dict):
                    # Look for "scores", "articles", "results" keys
                    for key in ["scores", "articles", "results"]:
                        if key in parsed and isinstance(parsed[key], list):
                            scores = parsed[key]
                            break
                    else:
                        # Try to find first list value in the dict
                        scores = []
                        for value in parsed.values():
                            if isinstance(value, list):
                                scores = value
                                break
                else:
                    scores = []
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse scoring response for batch {batch_idx}")
                scores = []

            # Apply scores to articles
            score_map = {s["idx"]: s for s in scores if isinstance(s, dict)}

            for i, article in enumerate(batch):
                if i in score_map:
                    article["relevance_score"] = float(score_map[i].get("score", 0.5))
                    article["relevance_reasoning"] = score_map[i].get("reasoning", "")
                else:
                    article["relevance_score"] = 0.5
                    article["relevance_reasoning"] = "No score returned"

            logger.debug(f"Batch {batch_idx}: Scored {len(batch)} articles")
            return batch

        except asyncio.TimeoutError:
            logger.warning(f"Batch {batch_idx} scoring timed out")
            for article in batch:
                article["relevance_score"] = 0.5
                article["relevance_reasoning"] = "Scoring timed out"
            return batch

        except Exception as e:
            logger.error(f"Batch {batch_idx} scoring failed: {e}")
            raise

    def _log_statistics(self, articles: List[Dict]):
        """Log statistics about scored articles."""
        if not articles:
            return

        scores = [a.get("relevance_score", 0) for a in articles]
        avg_score = sum(scores) / len(scores)

        high_relevance = sum(1 for s in scores if s >= self.config.high_relevance_threshold)
        medium_relevance = sum(1 for s in scores if self.config.relevance_threshold <= s < self.config.high_relevance_threshold)
        low_relevance = sum(1 for s in scores if s < self.config.relevance_threshold)

        logger.info(
            f"Relevance scoring complete: {len(articles)} articles, "
            f"avg score: {avg_score:.2f}, "
            f"high: {high_relevance}, medium: {medium_relevance}, low: {low_relevance}"
        )

    async def get_top_articles(
        self,
        articles: List[Dict],
        query: str,
        objectives: List[Dict],
        top_n: int = 30
    ) -> List[Dict]:
        """
        Score and return only the top N most relevant articles.

        Useful for quickly reducing a large result set to the most relevant articles.
        """
        scored = await self.score_articles(
            articles, query, objectives, filter_below_threshold=False
        )
        return scored[:top_n]


# Singleton instance
_scorer_instance: Optional[RelevanceScorer] = None


def get_relevance_scorer(config: Optional[RelevanceScoringConfig] = None) -> RelevanceScorer:
    """Get the global relevance scorer instance."""
    global _scorer_instance
    if _scorer_instance is None or config is not None:
        _scorer_instance = RelevanceScorer(config)
    return _scorer_instance
