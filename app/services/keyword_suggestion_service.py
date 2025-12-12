"""
Keyword Suggestion Service

Analyzes keyword performance based on relevance scores and suggests improvements
using LLM analysis of low-relevance articles.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from litellm import completion

logger = logging.getLogger(__name__)

# Minimum articles required before suggesting improvements
MIN_ARTICLES_FOR_ANALYSIS = 5

# Relevance thresholds
LOW_RELEVANCE_THRESHOLD = 0.4
HIGH_RELEVANCE_THRESHOLD = 0.7

# Prompt for analyzing keyword performance and suggesting improvements
# This is the basic prompt - provider-specific rules are added dynamically
SUGGESTION_PROMPT_BASE = """You are analyzing keyword performance for a news monitoring system.

Current keyword: "{keyword}"
Topic being monitored: "{topic}"
{description_line}

This keyword was used to search for news articles. Here are some article titles that were matched by this keyword but had LOW relevance scores (< 0.4 on a 0-1 scale), meaning they were not actually relevant to the topic:

{low_relevance_titles}

The keyword is bringing back too many irrelevant articles. Analyze WHY this is happening and suggest improvements.

{keyword_rules}

You can suggest TWO types of improvements:
1. REPLACEMENTS: A more focused keyword/query to replace the current one (MUST follow the keyword rules above)
2. EXCLUSIONS: Terms to exclude that will filter out irrelevant results

Respond with ONLY valid JSON:

{{
    "analysis": "Brief explanation of why the current keyword has low relevance",
    "suggested_replacements": [
        {{"keyword": "YOUR_REPLACEMENT_KEYWORD_HERE", "reason": "why this is better"}}
    ],
    "suggested_exclusions": [
        {{"keyword": "-term", "reason": "what it filters out"}}
    ],
    "confidence": 0.85
}}

CRITICAL: Replace YOUR_REPLACEMENT_KEYWORD_HERE with an actual keyword following the rules above. Respond with ONLY the JSON."""

# Provider-specific keyword rules
KEYWORD_RULES_THENEWSAPI = """CRITICAL: This API uses TheNewsAPI boolean query syntax.

REQUIRED FORMAT for all suggested keywords:
(term1 | term2) + (term3 | term4)

Where | means OR and + means AND. Use quotes for phrases.

Example: If the topic is "AI regulation", a valid suggestion is:
("AI regulation" | "AI law") + (EU | US | policy)

NOT valid: "AI regulation law" (missing boolean operators)

Analyze which OR terms in the current query are causing irrelevant matches, then suggest a more focused boolean query that removes those problematic terms."""

KEYWORD_RULES_SIMPLE = """IMPORTANT - All suggested keywords must follow these rules (for news API compatibility):
1. Use SIMPLE, SINGLE-WORD or TWO-WORD keywords only
2. NO Boolean operators (AND, OR, NOT, |, +)
3. NO parentheses, brackets, or special characters
4. NO quoted phrases
5. Keep each keyword under 30 characters
6. For exclusions, prefix with minus sign: -term"""

# Map provider names to their rules
PROVIDER_KEYWORD_RULES = {
    'thenewsapi': KEYWORD_RULES_THENEWSAPI,
    'newsdata': KEYWORD_RULES_SIMPLE,
    'newsapi': KEYWORD_RULES_SIMPLE,  # NewsAPI has limited boolean support
    'default': KEYWORD_RULES_SIMPLE,
}


class KeywordSuggestionService:
    """Service for analyzing keyword performance and suggesting improvements."""

    def __init__(self, db):
        self.db = db

    async def analyze_keyword_performance(
        self,
        keyword_id: int,
        group_id: int
    ) -> Dict[str, Any]:
        """
        Get detailed performance metrics for a specific keyword.

        Args:
            keyword_id: ID of the monitored keyword
            group_id: ID of the keyword group

        Returns:
            Dictionary with performance metrics
        """
        try:
            # Get keyword details
            keyword_info = self.db.facade.get_monitored_keyword_by_id(keyword_id)
            if not keyword_info:
                return {"error": "Keyword not found"}

            keyword_text = keyword_info.get('keyword', '')

            # Get relevance statistics for this keyword
            stats = self.db.facade.get_keyword_relevance_stats_single(keyword_id)

            if not stats:
                return {
                    "keyword_id": keyword_id,
                    "keyword": keyword_text,
                    "total_matches": 0,
                    "avg_relevance": 0,
                    "high_relevance_count": 0,
                    "low_relevance_count": 0,
                    "low_relevance_pct": 0,
                    "status": "no_data",
                    "message": "No articles matched this keyword yet"
                }

            total = stats.get('total_matches', 0)
            avg_rel = stats.get('avg_relevance', 0)
            high_count = stats.get('high_relevance_count', 0)
            low_count = stats.get('low_relevance_count', 0)

            low_pct = (low_count / total * 100) if total > 0 else 0
            high_pct = (high_count / total * 100) if total > 0 else 0

            # Determine status
            if total < MIN_ARTICLES_FOR_ANALYSIS:
                status = "insufficient_data"
            elif avg_rel >= HIGH_RELEVANCE_THRESHOLD:
                status = "excellent"
            elif avg_rel >= 0.5:
                status = "good"
            elif avg_rel >= LOW_RELEVANCE_THRESHOLD:
                status = "needs_attention"
            else:
                status = "poor"

            return {
                "keyword_id": keyword_id,
                "keyword": keyword_text,
                "group_id": group_id,
                "total_matches": total,
                "avg_relevance": round(avg_rel, 3),
                "high_relevance_count": high_count,
                "high_relevance_pct": round(high_pct, 1),
                "low_relevance_count": low_count,
                "low_relevance_pct": round(low_pct, 1),
                "status": status
            }

        except Exception as e:
            logger.error(f"Error analyzing keyword performance: {e}", exc_info=True)
            return {"error": str(e)}

    async def suggest_keyword_improvements(
        self,
        keyword_id: int,
        group_id: int,
        model: str = None
    ) -> Dict[str, Any]:
        """
        Use LLM to analyze low-relevance articles and suggest keyword improvements.

        Args:
            keyword_id: ID of the monitored keyword
            group_id: ID of the keyword group
            model: LLM model to use (if None, uses configured default from settings)

        Returns:
            Dictionary with analysis and suggestions
        """
        try:
            # Get keyword and topic info
            keyword_info = self.db.facade.get_monitored_keyword_by_id(keyword_id)
            if not keyword_info:
                return {"error": "Keyword not found"}

            keyword_text = keyword_info.get('keyword', '')

            group_info = self.db.facade.get_keyword_group_by_id(group_id)
            topic = group_info.get('topic', '') if group_info else ''

            # Get model from settings if not provided
            if not model:
                try:
                    settings = self.db.facade.get_keyword_monitor_settings_by_id(1)
                    model = settings.get('default_llm_model', 'gpt-4o-mini') if settings else 'gpt-4o-mini'
                except Exception:
                    model = 'gpt-4o-mini'

            # Get topic description if available
            topic_description = ""
            try:
                topic_config = self.db.facade.get_topic_config(topic)
                if topic_config:
                    topic_description = topic_config.get('description', '')
            except Exception:
                pass

            # Get performance stats
            performance = await self.analyze_keyword_performance(keyword_id, group_id)

            if performance.get('total_matches', 0) < MIN_ARTICLES_FOR_ANALYSIS:
                return {
                    "keyword_id": keyword_id,
                    "keyword": keyword_text,
                    "status": "insufficient_data",
                    "message": f"Need at least {MIN_ARTICLES_FOR_ANALYSIS} matched articles to analyze. Currently have {performance.get('total_matches', 0)}."
                }

            # Get low relevance articles with URLs for analysis
            low_relevance_articles = self.db.facade.get_low_relevance_articles_for_keyword(
                keyword_id,
                threshold=LOW_RELEVANCE_THRESHOLD,
                limit=15
            )

            if not low_relevance_articles:
                return {
                    "keyword_id": keyword_id,
                    "keyword": keyword_text,
                    "current_performance": performance,
                    "status": "good",
                    "message": "This keyword has good relevance. No low-relevance articles found to analyze."
                }

            # Format titles for LLM prompt (just titles, not URLs)
            titles_text = "\n".join([f"- {article['title']}" for article in low_relevance_articles[:15]])

            description_line = f"Topic description: {topic_description}" if topic_description else ""

            # Get provider from keyword_monitor_settings (this is what's actually used for searches)
            # Fall back to group's provider if settings not available
            provider = ''
            try:
                settings = self.db.facade.get_keyword_monitor_settings_by_id(1)
                if settings:
                    provider = (settings.get('provider') or '').lower()
                    logger.debug(f"Got provider from settings: {provider}")
            except Exception as e:
                logger.warning(f"Could not get provider from settings: {e}")

            # Fallback to group's provider if settings unavailable
            if not provider and group_info:
                provider = (group_info.get('provider') or '').lower()
                logger.debug(f"Using fallback provider from group: {provider}")

            keyword_rules = PROVIDER_KEYWORD_RULES.get(provider, PROVIDER_KEYWORD_RULES['default'])

            logger.info(f"Using keyword rules for provider '{provider}': {'compound queries allowed' if provider == 'thenewsapi' else 'simple keywords only'}")

            # Build prompt with provider-specific rules
            prompt = SUGGESTION_PROMPT_BASE.format(
                keyword=keyword_text,
                topic=topic,
                description_line=description_line,
                low_relevance_titles=titles_text,
                keyword_rules=keyword_rules
            )

            # Call LLM
            logger.info(f"Requesting keyword improvement suggestions for '{keyword_text}' using model {model}")

            messages = [
                {"role": "system", "content": "You are a JSON-only assistant. Respond with valid JSON only, no explanations."},
                {"role": "user", "content": prompt}
            ]

            response = completion(
                model=model,
                messages=messages,
                max_tokens=1000,
                temperature=0.3
            )

            raw_content = response.choices[0].message.content.strip()
            logger.debug(f"LLM response: {raw_content}")

            # Parse JSON response
            try:
                suggestions = json.loads(raw_content)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{[\s\S]*\}', raw_content)
                if json_match:
                    suggestions = json.loads(json_match.group())
                else:
                    logger.error(f"Could not parse LLM response as JSON: {raw_content}")
                    return {
                        "keyword_id": keyword_id,
                        "keyword": keyword_text,
                        "error": "Failed to parse LLM response"
                    }

            # Normalize suggested keywords (but skip for TheNewsAPI which supports boolean syntax)
            if provider != 'thenewsapi':
                from app.utils.keyword_normalizer import normalize_keyword

                for suggestion_list in ['suggested_replacements', 'suggested_additions', 'suggested_exclusions']:
                    if suggestion_list in suggestions:
                        for item in suggestions[suggestion_list]:
                            if 'keyword' in item:
                                normalized = normalize_keyword(item['keyword'])
                                if normalized:
                                    item['keyword'] = normalized
            else:
                # For TheNewsAPI, just clean up whitespace but preserve boolean syntax
                for suggestion_list in ['suggested_replacements', 'suggested_additions', 'suggested_exclusions']:
                    if suggestion_list in suggestions:
                        for item in suggestions[suggestion_list]:
                            if 'keyword' in item:
                                # Just trim whitespace, preserve boolean operators
                                item['keyword'] = ' '.join(item['keyword'].split())

            # Include full article data with URLs for the UI
            sample_articles = [
                {
                    "title": article['title'],
                    "url": article.get('url', ''),
                    "relevance_score": round(article.get('keyword_relevance_score', 0) * 100)
                }
                for article in low_relevance_articles[:5]
            ]

            return {
                "keyword_id": keyword_id,
                "keyword": keyword_text,
                "group_id": group_id,
                "topic": topic,
                "current_performance": performance,
                "analysis": suggestions.get("analysis", ""),
                "suggestions": {
                    "replacements": suggestions.get("suggested_replacements", []),
                    "additions": suggestions.get("suggested_additions", []),
                    "exclusions": suggestions.get("suggested_exclusions", [])
                },
                "confidence": suggestions.get("confidence", 0.5),
                "sample_low_relevance_articles": sample_articles,
                # Keep titles for backwards compatibility
                "sample_low_relevance_titles": [a['title'] for a in low_relevance_articles[:5]],
                "analyzed_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error suggesting keyword improvements: {e}", exc_info=True)
            return {"error": str(e)}

    async def get_group_performance_report(
        self,
        group_id: int
    ) -> Dict[str, Any]:
        """
        Get comprehensive performance report for all keywords in a group.

        Args:
            group_id: ID of the keyword group

        Returns:
            Dictionary with group performance summary
        """
        try:
            # Get group info
            group_info = self.db.facade.get_keyword_group_by_id(group_id)
            if not group_info:
                return {"error": "Keyword group not found"}

            group_name = group_info.get('name', '')
            topic = group_info.get('topic', '')

            # Get all keywords in group
            keywords = self.db.facade.get_keywords_for_group(group_id)

            if not keywords:
                return {
                    "group_id": group_id,
                    "group_name": group_name,
                    "topic": topic,
                    "message": "No keywords in this group"
                }

            # Analyze each keyword
            keyword_reports = []
            total_articles = 0
            keywords_needing_attention = 0
            relevance_sum = 0
            keywords_with_data = 0

            for kw in keywords:
                kw_id = kw.get('id')
                performance = await self.analyze_keyword_performance(kw_id, group_id)

                if performance.get('total_matches', 0) > 0:
                    keywords_with_data += 1
                    total_articles += performance.get('total_matches', 0)
                    relevance_sum += performance.get('avg_relevance', 0)

                    if performance.get('status') in ['needs_attention', 'poor']:
                        keywords_needing_attention += 1

                keyword_reports.append({
                    "keyword_id": kw_id,
                    "keyword": kw.get('keyword', ''),
                    "status": performance.get('status', 'no_data'),
                    "avg_relevance": performance.get('avg_relevance', 0),
                    "total_matches": performance.get('total_matches', 0),
                    "low_relevance_pct": performance.get('low_relevance_pct', 0)
                })

            overall_avg = relevance_sum / keywords_with_data if keywords_with_data > 0 else 0

            return {
                "group_id": group_id,
                "group_name": group_name,
                "topic": topic,
                "summary": {
                    "total_keywords": len(keywords),
                    "keywords_with_data": keywords_with_data,
                    "keywords_needing_attention": keywords_needing_attention,
                    "overall_avg_relevance": round(overall_avg, 3),
                    "total_articles": total_articles
                },
                "keywords": sorted(keyword_reports, key=lambda x: x.get('avg_relevance', 0)),
                "auto_suggestions_available": keywords_needing_attention > 0,
                "generated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error generating group performance report: {e}", exc_info=True)
            return {"error": str(e)}

    async def save_suggestion(
        self,
        keyword_id: int,
        group_id: int,
        suggestion_type: str,
        suggested_keyword: str,
        reason: str,
        confidence: float,
        analyzed_articles: int,
        avg_relevance: float
    ) -> Optional[int]:
        """
        Save a suggestion to the database for user review.

        Args:
            keyword_id: ID of the original keyword
            group_id: ID of the keyword group
            suggestion_type: 'replace', 'add', or 'exclude'
            suggested_keyword: The suggested keyword
            reason: Explanation for the suggestion
            confidence: Confidence score (0-1)
            analyzed_articles: Number of articles analyzed
            avg_relevance: Average relevance at time of suggestion

        Returns:
            Suggestion ID if saved successfully, None otherwise
        """
        try:
            suggestion_id = self.db.facade.save_keyword_suggestion(
                keyword_id=keyword_id,
                group_id=group_id,
                suggestion_type=suggestion_type,
                suggested_keyword=suggested_keyword,
                reason=reason,
                confidence=confidence,
                analyzed_articles=analyzed_articles,
                avg_relevance=avg_relevance
            )
            return suggestion_id
        except Exception as e:
            logger.error(f"Error saving suggestion: {e}", exc_info=True)
            return None

    async def apply_suggestion(
        self,
        suggestion_id: int,
        action: str,
        username: str
    ) -> Dict[str, Any]:
        """
        Apply or reject a suggestion.

        Args:
            suggestion_id: ID of the suggestion
            action: 'approve' or 'reject'
            username: User who made the decision

        Returns:
            Result of the action
        """
        try:
            suggestion = self.db.facade.get_keyword_suggestion_by_id(suggestion_id)
            if not suggestion:
                return {"error": "Suggestion not found"}

            if suggestion.get('status') != 'pending':
                return {"error": f"Suggestion already {suggestion.get('status')}"}

            if action == 'reject':
                self.db.facade.update_keyword_suggestion_status(
                    suggestion_id=suggestion_id,
                    status='rejected',
                    resolved_by=username
                )
                return {
                    "success": True,
                    "message": "Suggestion rejected",
                    "suggestion_id": suggestion_id
                }

            elif action == 'approve':
                keyword_id = suggestion.get('keyword_id')
                group_id = suggestion.get('group_id')
                suggestion_type = suggestion.get('suggestion_type')
                suggested_keyword = suggestion.get('suggested_keyword')

                if suggestion_type == 'replace':
                    # Update the existing keyword
                    self.db.facade.update_monitored_keyword_text(
                        keyword_id=keyword_id,
                        new_keyword=suggested_keyword
                    )
                    message = f"Keyword replaced with '{suggested_keyword}'"

                elif suggestion_type == 'add':
                    # Add new keyword to the group
                    self.db.facade.add_keywords_to_group(group_id, suggested_keyword)
                    message = f"Added new keyword '{suggested_keyword}'"

                elif suggestion_type == 'exclude':
                    # Add exclusion keyword to the group
                    self.db.facade.add_keywords_to_group(group_id, suggested_keyword)
                    message = f"Added exclusion '{suggested_keyword}'"

                else:
                    return {"error": f"Unknown suggestion type: {suggestion_type}"}

                # Mark suggestion as approved
                self.db.facade.update_keyword_suggestion_status(
                    suggestion_id=suggestion_id,
                    status='approved',
                    resolved_by=username
                )

                return {
                    "success": True,
                    "message": message,
                    "suggestion_id": suggestion_id,
                    "applied_keyword": suggested_keyword
                }

            else:
                return {"error": f"Unknown action: {action}"}

        except Exception as e:
            logger.error(f"Error applying suggestion: {e}", exc_info=True)
            return {"error": str(e)}
