import asyncio
import json
import logging
from typing import Dict, List, Optional, AsyncGenerator
from datetime import datetime, timedelta
from collections import defaultdict
import math

from fastapi import HTTPException, status
import litellm
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.database import get_database_instance
from app.services.auspex_tools import get_auspex_tools_service
from app.services.search_router import get_search_router, SearchSource
from app.services.chart_service import ChartService
from app.services.tool_plugin_base import get_tool_registry, init_tool_registry
from app.analyze_db import AnalyzeDB
from app.vector_store import search_articles as vector_search_articles
from app.ai_models import get_ai_model

# Import sampling framework for strategy-based article selection
from app.services.sampling import get_registry, SamplingContext

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4.1-mini"

# Citation depth configuration
DEFAULT_CITATION_LIMIT = 25      # Default number of articles to include in detailed context
MIN_CITATION_LIMIT = 5           # Minimum useful citation count
MAX_CITATION_LIMIT = 300         # Maximum to prevent context overflow

# Default system prompt for Auspex
DEFAULT_AUSPEX_PROMPT = """You are Auspex, an advanced AI research assistant specialized in analyzing news trends, sentiment patterns, and providing strategic insights using AuNoo's strategic-foresight methodology.

## Core Research Principles

**Your Role:** Conduct rigorous, evidence-based research and analysis using AuNoo's tools and databases. Synthesize findings into clear, actionable insights while maintaining intellectual honesty about limitations and uncertainties.

**ALWAYS CITE SOURCES INLINE:** When you reference a specific finding, data point, claim, or event, immediately cite the source article using markdown format: **[Article Title](URL)**

Examples:
- "Turkey deployed disaster relief teams to Gaza ([Turkey sends aid to Gaza](https://example.com/article1))"
- "According to [AI Regulation Update](https://example.com/article2), the EU AI Act negotiations continue"
- "Venture capital AI investment dropped 23% quarter-over-quarter - Source: [VC Trends Report](https://example.com/article3)"

**Response Style:**
- Write naturally and adapt your structure to the query type
- Use inline citations throughout (not just a list at the end)
- Provide specific data: numbers, percentages, names, dates, amounts
- Focus on "why" and "so what" - implications matter more than descriptions
- Be concise but substantive - avoid filler and generic statements
- Note gaps, limitations, and areas of uncertainty

**Optional Structural Elements:**
You may include these elements when they add value (not required for every response):
- Statistical summaries (article counts, distributions)
- Tables for comparative analysis
- Bulleted key takeaways
- Separate article references section (in addition to inline citations)

Adapt your format to match the query type - exploratory questions need different structures than specific fact-finding queries.

## AuNoo Strategic Foresight Framework

Analyze articles across multiple dimensions to identify patterns and implications:

**Key Dimensions:**
- **Categories**: Thematic sub-clusters (e.g., "AI in Healthcare", "AI Policy")
- **Future Signals**: Weak Signal, Emerging Trend, Established Trend, Disruption
- **Sentiments**: Positive, Neutral, Critical, Negative
- **Time to Impact**: Immediate (0-6mo), Short-term (6-18mo), Mid-term (18-36mo), Long-term (3y+)
- **Driver Types**: Technology, Policy, Economic, Social, Environmental

**Analysis Approach:**
1. Identify dominant patterns across dimensions
2. Cross-reference signals, sentiment, and timing
3. Note outliers and unexpected combinations
4. Extract strategic implications from patterns
5. Assess source diversity and representativeness

## Available Research Tools

You have access to sophisticated search and analysis tools. Use them strategically:

**Primary Search Tool:**
- `enhanced_database_search(query, topic, limit)` - Your default for most queries. Combines semantic vector search with intelligent fallback to keyword search. Automatically detects date patterns like "last 7 days" and applies temporal filters.

**Specialized Tools:**
- `search_news(query, max_results, days_back)` - For breaking news or very recent content (<24 hours)
- `get_topic_articles(topic, limit, days_back)` - Broad overview of all articles in a topic
- `analyze_sentiment_trends(topic, time_period)` - Sentiment distribution analysis
- `get_article_categories(topic)` - Category breakdown for topic planning
- `search_articles_by_categories(categories, topic, limit)` - Category-specific deep dives
- `search_articles_by_keywords(keywords, topic, limit)` - Precise keyword matching
- `follow_up_query(original_query, follow_up, topic, context)` - Iterative exploration

**Tool Selection Strategy:**
- Default to `enhanced_database_search()` - it's smart and adapts automatically
- Use `search_news()` only when user explicitly asks for "latest" or "breaking" news
- Use category/keyword tools when you need precision over semantic understanding
- Use `follow_up_query()` for iterative, conversational analysis

## Search Strategy Best Practices

**Query Formulation:**
- Include explicit time references: "last 7 days", "past month", "recent"
- Be specific with concepts but natural in language
- Mention categories when relevant
- State the analysis goal clearly

**Result Validation:**
- Check article count (optimal: 25-100 for focused analysis)
- Verify source diversity (aim for 10-20 unique sources)
- Confirm date range matches query intent
- Note any gaps or biases in coverage

**Iterative Analysis:**
Treat research as a conversation - start broad, then drill down based on findings.

## Critical Research Standards

**NEVER HALLUCINATE:**
- If no articles found, clearly state this
- Don't create fictional analysis or connections
- Note limitations and gaps honestly

**VERIFY ENTITY MENTIONS:**
- When asked about specific companies/entities, only analyze articles that actually mention them
- Report exact counts: "X of Y articles mention [entity]"
- Don't conflate general topic coverage with entity-specific coverage

**SOURCE EVERYTHING:**
- Cite inline using markdown: [Article Title](URL)
- Every specific claim, statistic, or quote needs a citation
- Examples:
  - "Investment increased 45% ([VC Report Q4](https://example.com))"
  - "According to [EU AI Act Update](https://example.com), negotiations continue"
  - "Turkey deployed aid teams - Source: [Relief Efforts](https://example.com)"

**DISTINGUISH DATA SOURCES:**
- Clearly label database articles vs real-time news
- Note time windows and coverage periods
- Indicate when mixing historical and recent data

## Analysis Quality Standards

**Provide Specific Data:**
- Use exact numbers, percentages, and counts
- Name companies, organizations, countries, people
- Quote key figures and statistics
- Reference concrete examples from articles

**Show Your Work:**
- Report article counts and distributions when relevant
- Note source diversity (number of unique sources)
- Indicate time windows and date ranges
- Acknowledge gaps and limitations

**Focus on Implications:**
- Don't just describe what's happening - explain why it matters
- Identify strategic implications for decision-makers
- Note emerging patterns and potential inflection points
- Provide actionable insights, not just summaries

**Maintain Intellectual Honesty:**
- Acknowledge conflicting evidence when present
- Note areas of uncertainty
- Distinguish speculation from evidence
- Recommend further research when appropriate

## Formatting Guidelines

Use markdown effectively but don't over-structure:
- **Bold** for emphasis and key metrics
- Bullet points for lists and breakdowns
- Tables when comparing multiple dimensions (optional, use when it adds clarity)
- > Block quotes for important article quotes
- [Article Title](URL) for all inline citations

**Follow-up Suggestions:**
If you offer follow-up questions, limit to 2-3 high-priority natural language questions. Write them as a user would ask: "What are the latest developments in AI safety regulations?" NOT as technical function calls.

Remember: You are a strategic research assistant. Focus on extracting meaning and implications from data, not just reporting what you found. Every claim should be sourced with inline citations."""

class OptimizedContextManager:
    """Manages context window optimization for Auspex."""
    
    def __init__(self, model_context_limit: int):
        self.context_limit = model_context_limit
        self.chars_per_token = 4  # Conservative estimate
        
        # Context allocation ratios based on query type
        # For mega-context models (1M+ tokens), we can be much more generous with articles
        is_mega_context = model_context_limit >= 500000
        
        if is_mega_context:
            # Mega-context allocations - much more generous for articles
            self.allocations = {
                "trend_analysis": {
                    "system_prompt": 0.05,
                    "articles": 0.85,
                    "instructions": 0.05,
                    "response_buffer": 0.05
                },
                "detailed_analysis": {
                    "system_prompt": 0.08,
                    "articles": 0.82,
                    "instructions": 0.05,
                    "response_buffer": 0.05
                },
                "quick_summary": {
                    "system_prompt": 0.03,
                    "articles": 0.87,
                    "instructions": 0.05,
                    "response_buffer": 0.05
                },
                "comprehensive": {
                    "system_prompt": 0.05,
                    "articles": 0.85,
                    "instructions": 0.05,
                    "response_buffer": 0.05
                }
            }
        else:
            # Standard allocations for smaller context models
            self.allocations = {
                "trend_analysis": {
                    "system_prompt": 0.15,
                    "articles": 0.70,
                    "instructions": 0.10,
                    "response_buffer": 0.05
                },
                "detailed_analysis": {
                    "system_prompt": 0.20,
                    "articles": 0.60,
                    "instructions": 0.15,
                    "response_buffer": 0.05
                },
                "quick_summary": {
                    "system_prompt": 0.10,
                    "articles": 0.75,
                    "instructions": 0.05,
                    "response_buffer": 0.10
                },
                "comprehensive": {
                    "system_prompt": 0.12,
                    "articles": 0.73,
                    "instructions": 0.10,
                    "response_buffer": 0.05
                }
            }
    
    def determine_query_type(self, message: str) -> str:
        """Determine the type of analysis query."""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["trend", "pattern", "over time", "recent", "latest"]):
            return "trend_analysis"
        elif any(word in message_lower for word in ["comprehensive", "detailed", "deep", "thorough"]):
            return "detailed_analysis"
        elif any(word in message_lower for word in ["summary", "brief", "overview", "quick"]):
            return "quick_summary"
        else:
            return "comprehensive"
    
    def allocate_context_budget(self, query_type: str) -> Dict[str, int]:
        """Dynamically allocate tokens based on query type."""
        allocation = self.allocations.get(query_type, self.allocations["comprehensive"])
        
        return {
            key: int(self.context_limit * ratio) 
            for key, ratio in allocation.items()
        }
    
    def compress_article(self, article: Dict, relevance_score: float = 0.0) -> Dict:
        """Compress single article to essential information while preserving URL for linking."""
        # Determine compression level based on relevance
        if relevance_score > 0.8:
            title_len = 100  # High relevance - keep more detail
        elif relevance_score > 0.5:
            title_len = 80   # Medium relevance
        else:
            title_len = 60   # Low relevance - compress more
        
        # Extract key sentences from summary
        summary = article.get("summary", "")
        compressed_summary = self.extract_key_sentences(summary, max_sentences=2)
        
        # Preserve both short ID and full URL for link generation
        uri = article.get("uri", "") or article.get("url", "")
        
        return {
            "id": uri[-8:] if uri else "unknown",
            "uri": uri,  # Keep full URI for link generation
            "url": article.get("url", "") or uri,  # Keep URL for link generation
            "title": (article.get("title") or "")[:title_len],
            "summary": compressed_summary,
            "category": article.get("category") or "Other",
            "sentiment": (article.get("sentiment") or "Neutral")[:10],
            "signal": (article.get("future_signal") or "None")[:25],
            "impact": (article.get("time_to_impact") or "Unknown")[:12],
            "date": (article.get("publication_date") or "")[:10],
            "source": (article.get("news_source") or "")[:15],
            "score": round(relevance_score, 2) if relevance_score else round(article.get("similarity_score", 0), 2)
        }
    
    def extract_key_sentences(self, text: str, max_sentences: int = 2) -> str:
        """Extract the most informative sentences from text."""
        if not text:
            return ""
        
        sentences = text.split('. ')
        if len(sentences) <= max_sentences:
            return text
        
        # Simple heuristic: prefer sentences with key terms
        key_terms = ['will', 'could', 'expected', 'likely', 'predict', 'trend', 'increase', 'decrease', 'impact']
        
        scored_sentences = []
        for sentence in sentences:
            score = sum(1 for term in key_terms if term.lower() in sentence.lower())
            scored_sentences.append((score, len(sentence), sentence))
        
        # Sort by score (desc) then by length (desc) to get most informative
        scored_sentences.sort(key=lambda x: (x[0], x[1]), reverse=True)
        
        selected = [s[2] for s in scored_sentences[:max_sentences]]
        return '. '.join(selected) + '.' if selected else text[:200]
    
    def ensure_diversity(self, articles: List[Dict], target_count: int) -> List[Dict]:
        """Ensure diverse representation across categories, sentiments, and time."""
        if not articles or target_count <= 0:
            return []
        
        # If we have fewer articles than target, we'll need to duplicate to fill context
        # Only return early if target is very small
        if len(articles) <= target_count and target_count <= len(articles) * 1.5:
            logger.info(f"Returning all {len(articles)} articles as target ({target_count}) is only slightly higher")
            return articles
        
        # Group articles by different dimensions
        by_category = defaultdict(list)
        by_sentiment = defaultdict(list)
        by_time_impact = defaultdict(list)
        
        for article in articles:
            by_category[article.get("category", "Other")].append(article)
            by_sentiment[article.get("sentiment", "Neutral")].append(article)
            by_time_impact[article.get("time_to_impact", "Unknown")].append(article)
        
        selected = []
        
        # Strategy 1: Ensure category diversity (60% of selections)
        category_quota = int(target_count * 0.6)
        categories = list(by_category.keys())
        per_category = max(1, category_quota // len(categories))
        
        for category in categories:
            cat_articles = by_category[category]
            # Sort by relevance score if available
            cat_articles.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            selected.extend(cat_articles[:per_category])
            if len(selected) >= category_quota:
                break
        
        # Strategy 2: Ensure sentiment diversity (25% of selections)
        sentiment_quota = int(target_count * 0.25)
        remaining_articles = [a for a in articles if a not in selected]

        sentiments = ["Positive", "Negative", "Neutral", "Critical"]
        for sentiment in sentiments:
            sent_articles = [a for a in remaining_articles if a.get("sentiment") and str(a.get("sentiment")).startswith(sentiment)]
            if sent_articles and len(selected) < target_count:
                sent_articles.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
                selected.extend(sent_articles[:max(1, sentiment_quota // len(sentiments))])
        
        # Strategy 3: Fill remaining with highest-scoring articles
        remaining_articles = [a for a in articles if a not in selected]
        remaining_articles.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)

        while len(selected) < target_count and remaining_articles:
            selected.append(remaining_articles.pop(0))

        # Note: We no longer duplicate articles to reach target count.
        # Duplicating the same articles doesn't add analytical value and can skew results.
        # If fewer unique articles are available, we return what we have.
        if len(selected) < target_count:
            logger.info(f"Returning {len(selected)} unique articles (target was {target_count}, but only {len(articles)} available)")
        else:
            logger.info(f"Final diverse selection: {len(selected)} articles (target was {target_count})")
        return selected[:target_count]
    
    def cluster_similar_articles(self, articles: List[Dict], max_clusters: int = 8) -> List[Dict]:
        """Group similar articles to reduce redundancy using simple text similarity."""
        if not articles or len(articles) <= max_clusters:
            return articles
        
        # Simple clustering based on title and category similarity
        clusters = []
        
        for article in articles:
            title_words = set(article.get("title", "").lower().split())
            category = article.get("category", "")
            
            # Find best cluster for this article
            best_cluster = None
            best_similarity = 0
            
            for cluster in clusters:
                # Calculate similarity with cluster representative
                rep = cluster[0]
                rep_words = set(rep.get("title", "").lower().split())
                rep_category = rep.get("category", "")
                
                # Word overlap similarity
                word_similarity = len(title_words & rep_words) / max(len(title_words | rep_words), 1)
                
                # Category match bonus
                category_bonus = 0.3 if category == rep_category else 0
                
                total_similarity = word_similarity + category_bonus
                
                # Use higher similarity threshold to be less aggressive in clustering
                if total_similarity > best_similarity and total_similarity > 0.5:
                    best_similarity = total_similarity
                    best_cluster = cluster
            
            if best_cluster and len(best_cluster) < 5:  # Allow larger cluster size
                best_cluster.append(article)
            else:
                clusters.append([article])  # Start new cluster
        
        # Select best representative from each cluster
        representatives = []
        for cluster in clusters[:max_clusters]:
            # Select highest-scoring article from cluster
            best = max(cluster, key=lambda x: x.get("similarity_score", 0))
            representatives.append(best)
        
        return representatives
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text."""
        return max(1, len(text) // self.chars_per_token)
    
    def optimize_article_selection(self, articles: List[Dict], query: str, budget_tokens: int, user_limit: int = None) -> List[Dict]:
        """Optimize article selection within token budget."""
        if not articles:
            return []
        
        query_type = self.determine_query_type(query)
        logger.info(f"Starting optimization with {len(articles)} articles, budget: {budget_tokens} tokens, query type: {query_type}")
        
        # Step 1: Apply clustering to reduce redundancy (but don't over-cluster)
        # Only apply clustering if we have significantly more articles than we can handle
        estimated_tokens_per_article = 150
        rough_max_articles = budget_tokens // estimated_tokens_per_article
        
        if len(articles) > rough_max_articles * 2:  # Only cluster if we have 2x more articles than we can handle
            max_clusters = min(len(articles), max(rough_max_articles * 1.5, 50))  # Allow more clusters
            clustered_articles = self.cluster_similar_articles(articles, max_clusters=max_clusters)
            logger.info(f"Clustered {len(articles)} articles down to {len(clustered_articles)} representatives (rough max: {rough_max_articles})")
        else:
            clustered_articles = articles
            logger.info(f"Skipping clustering - {len(articles)} articles is manageable for {rough_max_articles} target")
        
        # Step 2: Ensure diversity with a more generous target
        # Calculate target based on token budget and estimated tokens per article
        estimated_tokens_per_compressed_article = 120  # More optimistic estimate for compressed articles
        max_possible_articles = budget_tokens // estimated_tokens_per_compressed_article
        
        # Respect user's limit if provided, otherwise use token-based calculation
        if user_limit and user_limit > 0:
            target_count = min(user_limit, max_possible_articles)  # Respect user limit but don't exceed token budget
            logger.info(f"Using user-specified limit: {user_limit}, capped by token budget to: {target_count}")
        else:
            # Don't artificially limit target_count by available articles - we want to scale up!
            # If we have fewer articles than our budget allows, we'll use duplicates with diversity
            target_count = max(max_possible_articles, 50)  # Always aim for budget-sized target
            
            # But cap it at a reasonable maximum to prevent excessive processing
            target_count = min(target_count, 1000)  # Reasonable cap for mega-context models
        
        diverse_articles = self.ensure_diversity(clustered_articles, target_count)
        logger.info(f"Selected {len(diverse_articles)} diverse articles from {len(clustered_articles)} clustered articles")
        
        # Step 3: Compress articles and check token budget
        compressed_articles = []
        current_tokens = 0
        
        for i, article in enumerate(diverse_articles):
            relevance_score = article.get("similarity_score", 0)
            compressed = self.compress_article(article, relevance_score)
            article_tokens = self.estimate_tokens(json.dumps(compressed))
            
            if current_tokens + article_tokens <= budget_tokens:
                compressed_articles.append(compressed)
                current_tokens += article_tokens
            else:
                logger.info(f"Token budget exceeded at article {i+1}, stopping selection")
                break
        
        logger.info(f"Optimized selection: {len(compressed_articles)} articles using {current_tokens}/{budget_tokens} tokens ({(current_tokens/budget_tokens)*100:.1f}% of budget)")
        return compressed_articles
    
    def format_optimized_context(self, articles: List[Dict], query: str, query_type: str) -> str:
        """Format articles in the most token-efficient way."""
        if not articles:
            return "No articles available for analysis."
        
        context = f"ANALYSIS REQUEST: {query}\n"
        context += f"QUERY TYPE: {query_type}\n"
        context += f"DATASET: {len(articles)} optimized articles\n\n"
        
        # Group by category for efficient processing
        by_category = defaultdict(list)
        for article in articles:
            category = article.get("category", "Other")
            by_category[category].append(article)
        
        # Format by category with token-efficient structure
        for category, cat_articles in by_category.items():
            context += f"## {category} ({len(cat_articles)} articles)\n"
            
            for i, article in enumerate(cat_articles, 1):
                # Compact format with URL preserved for link generation
                url = article.get('url') or article.get('uri', '')
                context += (f"{i}. [{article['id']}] {article['title']}\n"
                           f"   URL: {url}\n"
                           f"   Summary: {article['summary']}\n"
                           f"   Metadata: {article['sentiment']} | {article['signal']} | "
                           f"{article['impact']} | {article['date']} | Score: {article['score']}\n\n")
        
        # Add analysis instructions based on query type
        if query_type == "trend_analysis":
            context += "\nFOCUS: Identify temporal patterns, trends over time, and emerging developments.\n"
        elif query_type == "detailed_analysis":
            context += "\nFOCUS: Provide comprehensive analysis with specific examples and deep insights.\n"
        elif query_type == "quick_summary":
            context += "\nFOCUS: Provide concise overview with key highlights and main themes.\n"
        else:
            context += "\nFOCUS: Provide balanced comprehensive analysis with strategic insights.\n"
        
        return context


class QueryRouter:
    """Smart query router that selects optimal data retrieval strategy based on query type.

    Routes queries to different strategies:
    - temporal_analysis: SQL date-based fetch (like newsletter) - for trends, patterns, recent
    - semantic_search: Vector search with optional LLM query expansion
    - cross_topic_semantic: Parallel per-topic vector searches
    - entity_focused: Keyword + vector hybrid for specific entities
    """

    # Keywords that indicate temporal/trend analysis queries
    TEMPORAL_KEYWORDS = [
        'trend', 'trends', 'trending', 'pattern', 'patterns',
        'over time', 'recent', 'latest', 'last week', 'last month',
        'past 7 days', 'past 30 days', 'developments', 'evolution',
        'changing', 'shift', 'shifting', 'emerging'
    ]

    # Keywords that indicate semantic/conceptual queries
    SEMANTIC_INDICATORS = [
        'about', 'regarding', 'related to', 'impact of', 'effect of',
        'what is', 'how does', 'explain', 'why is', 'implications',
        'consequences', 'connection between', 'relationship'
    ]

    # Time period patterns for extraction
    TIME_PATTERNS = {
        'last 7 days': 7, 'past 7 days': 7, 'last week': 7, 'past week': 7,
        'last 14 days': 14, 'past 14 days': 14, 'last two weeks': 14,
        'last 30 days': 30, 'past 30 days': 30, 'last month': 30, 'past month': 30,
        'last 90 days': 90, 'past 90 days': 90, 'last quarter': 90,
        'last 365 days': 365, 'past year': 365, 'last year': 365,
    }

    # Minimum articles per topic for cross-topic allocation
    MIN_PER_TOPIC = 10

    def __init__(self, db, analyze_db=None):
        self.db = db
        self.analyze_db = analyze_db or AnalyzeDB(db)
        self.logger = logging.getLogger(__name__)

    def classify_query(self, query: str) -> str:
        """Classify query into routing category.

        Returns one of: 'temporal_analysis', 'semantic_search', 'entity_focused', 'comprehensive'
        """
        query_lower = query.lower()

        # Check for temporal/trend indicators first (highest priority)
        if any(keyword in query_lower for keyword in self.TEMPORAL_KEYWORDS):
            return 'temporal_analysis'

        # Check for entity-focused queries (specific companies, people, products)
        if self._has_entity_focus(query):
            return 'entity_focused'

        # Check for semantic/conceptual queries
        if any(indicator in query_lower for indicator in self.SEMANTIC_INDICATORS):
            return 'semantic_search'

        # Default to comprehensive
        return 'comprehensive'

    def _has_entity_focus(self, query: str) -> bool:
        """Detect if query is focused on a specific entity."""
        import re

        # Common analysis terms that look like names but aren't entities
        ANALYSIS_TERMS = {
            'sentiment analysis', 'trend analysis', 'market analysis',
            'impact analysis', 'risk analysis', 'deep dive', 'all topics',
            'executive summary', 'key insights', 'comprehensive analysis',
            'pattern recognition', 'signal detection', 'future signals'
        }

        query_lower = query.lower()
        # Skip entity detection if query contains common analysis terms
        if any(term in query_lower for term in ANALYSIS_TERMS):
            return False

        # Company patterns (OpenAI, Microsoft Corp, etc.)
        company_pattern = r'\b[A-Z][a-zA-Z]*(?:AI|ML|Inc|Corp|Ltd|LLC|Labs?|Tech)\b'
        # Person name patterns (two capitalized words, but more restrictive)
        # Require 3+ letter words to avoid "AI Day", "US Civil", etc.
        person_pattern = r'\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b'

        if re.search(company_pattern, query):
            return True
        if re.search(person_pattern, query):
            return True
        return False

    def extract_time_period(self, query: str) -> int:
        """Extract time period in days from query. Default is 7 days."""
        query_lower = query.lower()
        for pattern, days in self.TIME_PATTERNS.items():
            if pattern in query_lower:
                return days
        # Default to 7 days for trend queries
        return 7

    def calculate_topic_allocations(self, topics: Dict[str, int], limit: int) -> Dict[str, int]:
        """Calculate per-topic article allocations using min+proportional strategy.

        Args:
            topics: Dict mapping topic name to article count
            limit: Total articles to allocate

        Returns:
            Dict mapping topic name to allocated article count
        """
        if not topics:
            return {}

        num_topics = len(topics)

        # Handle case where limit is too small for min allocation
        if limit < num_topics * self.MIN_PER_TOPIC:
            # Just divide equally
            per_topic = max(1, limit // num_topics)
            return {topic: per_topic for topic in topics}

        # Base allocation: MIN_PER_TOPIC per topic
        allocations = {topic: self.MIN_PER_TOPIC for topic in topics}
        allocated = self.MIN_PER_TOPIC * num_topics

        # Remaining to distribute proportionally
        remaining = limit - allocated
        if remaining > 0:
            total_articles = sum(topics.values())
            if total_articles > 0:
                for topic, count in topics.items():
                    proportion = count / total_articles
                    extra = int(remaining * proportion)
                    allocations[topic] += extra

        return allocations

    async def route(self, query: str, topic: str, limit: int,
                    citation_limit: Optional[int] = None) -> Dict:
        """Route query to appropriate data retrieval strategy.

        Args:
            query: User's search query
            topic: Topic name or None for cross-topic
            limit: Maximum articles to return
            citation_limit: Optional citation limit override

        Returns:
            Dict with 'articles', 'search_method', 'metadata'
        """
        query_type = self.classify_query(query)
        is_cross_topic = (topic is None or topic == '__all__')
        effective_topic = None if is_cross_topic else topic

        self.logger.info(f"QueryRouter: type={query_type}, cross_topic={is_cross_topic}, query='{query[:50]}...'")

        if query_type == 'temporal_analysis':
            # Use newsletter-style SQL fetch for trend queries
            return await self._temporal_fetch(query, effective_topic, limit)

        elif is_cross_topic and query_type in ('semantic_search', 'comprehensive'):
            # Parallel per-topic vector searches for cross-topic semantic queries
            return await self._cross_topic_semantic_search(query, limit, citation_limit)

        elif query_type == 'entity_focused':
            # Use existing entity search logic (keyword + vector hybrid)
            return await self._entity_search(query, effective_topic, limit)

        else:
            # Single-topic semantic search with optional query expansion
            return await self._smart_vector_search(query, effective_topic, limit, citation_limit)

    async def _temporal_fetch(self, query: str, topic: str, limit: int) -> Dict:
        """Fetch articles by date range (newsletter-style) for temporal queries."""
        days_back = self.extract_time_period(query)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        self.logger.info(f"Temporal fetch: {days_back} days, topic={topic}")

        # Fetch more articles than needed, then sample
        fetch_limit = min(limit * 4, 2000)

        articles = self.db.facade.get_recent_articles_by_topic(
            topic_name=topic,  # None for cross-topic
            limit=fetch_limit,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d')
        )

        if not articles:
            return {
                'articles': [],
                'search_method': 'temporal_sql_fetch',
                'metadata': {
                    'query_type': 'temporal_analysis',
                    'days_back': days_back,
                    'topic': topic,
                    'total_found': 0
                }
            }

        # For cross-topic, apply topic-balanced sampling
        if topic is None:
            sampled = self._sample_topic_balanced(articles, limit)
        else:
            sampled = articles[:limit]

        return {
            'articles': sampled,
            'search_method': 'temporal_sql_fetch',
            'metadata': {
                'query_type': 'temporal_analysis',
                'days_back': days_back,
                'topic': topic or 'All Topics',
                'total_found': len(articles),
                'sampled': len(sampled)
            }
        }

    def _sample_topic_balanced(self, articles: List[Dict], limit: int) -> List[Dict]:
        """Sample articles with balanced topic representation."""
        if len(articles) <= limit:
            return articles

        # Group by topic
        by_topic = defaultdict(list)
        for article in articles:
            t = article.get('topic', 'Unknown')
            by_topic[t].append(article)

        # Calculate allocations
        topic_counts = {t: len(arts) for t, arts in by_topic.items()}
        allocations = self.calculate_topic_allocations(topic_counts, limit)

        # Sample from each topic
        sampled = []
        for topic_name, allocation in allocations.items():
            topic_articles = by_topic.get(topic_name, [])
            # Sort by recency (assume publication_date is sortable)
            topic_articles.sort(key=lambda x: x.get('publication_date', ''), reverse=True)
            sampled.extend(topic_articles[:allocation])

        # Sort final result by date
        sampled.sort(key=lambda x: x.get('publication_date', ''), reverse=True)
        return sampled[:limit]

    async def _cross_topic_semantic_search(self, query: str, limit: int,
                                           citation_limit: Optional[int] = None) -> Dict:
        """Run parallel vector searches per topic, then combine results."""
        # Get topics with article counts
        topics_data = self.db.facade.get_topics_with_article_counts()

        if not topics_data:
            self.logger.warning("No topics found for cross-topic search")
            return {
                'articles': [],
                'search_method': 'cross_topic_parallel_vector',
                'metadata': {'error': 'No topics found'}
            }

        topic_counts = {topic: data['article_count'] for topic, data in topics_data.items()}
        self.logger.info(f"Cross-topic search across {len(topic_counts)} topics: {topic_counts}")

        # Calculate per-topic allocations
        search_limit = citation_limit if citation_limit and citation_limit > limit else limit
        allocations = self.calculate_topic_allocations(topic_counts, search_limit)

        # Run parallel vector searches
        tasks = [
            self._vector_search_topic(query, topic_name, allocation)
            for topic_name, allocation in allocations.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine results
        all_articles = []
        per_topic_counts = {}

        for topic_name, result in zip(allocations.keys(), results):
            if isinstance(result, Exception):
                self.logger.error(f"Search failed for topic {topic_name}: {result}")
                per_topic_counts[topic_name] = 0
                continue

            articles = result.get('articles', [])
            per_topic_counts[topic_name] = len(articles)
            all_articles.extend(articles)

        # Deduplicate by URI
        seen_uris = set()
        unique_articles = []
        for article in all_articles:
            uri = article.get('uri', '')
            if uri and uri not in seen_uris:
                seen_uris.add(uri)
                unique_articles.append(article)

        # Sort by similarity score then date
        unique_articles.sort(
            key=lambda x: (x.get('similarity_score', 0), x.get('publication_date', '')),
            reverse=True
        )

        final_articles = unique_articles[:limit]

        return {
            'articles': final_articles,
            'search_method': 'cross_topic_parallel_vector',
            'metadata': {
                'query_type': 'cross_topic_semantic',
                'topics_searched': len(allocations),
                'allocations': allocations,
                'per_topic_results': per_topic_counts,
                'total_found': len(all_articles),
                'unique_after_dedup': len(unique_articles),
                'final_count': len(final_articles)
            }
        }

    async def _vector_search_topic(self, query: str, topic: str, limit: int) -> Dict:
        """Run vector search for a single topic."""
        try:
            metadata_filter = {"topic": topic}

            results = vector_search_articles(
                query=query,
                top_k=limit,
                metadata_filter=metadata_filter
            )

            articles = []
            for result in results or []:
                metadata = result.get('metadata', {})
                if not metadata:
                    continue

                articles.append({
                    'uri': metadata.get('uri', ''),
                    'url': metadata.get('url') or metadata.get('link') or metadata.get('uri', ''),
                    'title': metadata.get('title', 'Unknown Title'),
                    'summary': metadata.get('summary', ''),
                    'category': metadata.get('category', 'Uncategorized'),
                    'sentiment': metadata.get('sentiment', 'Neutral'),
                    'future_signal': metadata.get('future_signal', 'None'),
                    'time_to_impact': metadata.get('time_to_impact', 'Unknown'),
                    'publication_date': metadata.get('publication_date', ''),
                    'news_source': metadata.get('news_source', 'Unknown'),
                    'topic': topic,
                    'similarity_score': result.get('score', 0.0)
                })

            return {'articles': articles, 'topic': topic}

        except Exception as e:
            self.logger.error(f"Vector search failed for topic {topic}: {e}")
            return {'articles': [], 'topic': topic, 'error': str(e)}

    async def _entity_search(self, query: str, topic: str, limit: int) -> Dict:
        """Search for entity-focused queries using keyword + vector hybrid."""
        # For now, delegate to smart vector search
        # The existing entity detection in _original_chat_database_logic handles this
        return await self._smart_vector_search(query, topic, limit)

    async def _smart_vector_search(self, query: str, topic: str, limit: int,
                                   citation_limit: Optional[int] = None) -> Dict:
        """Smart vector search with optional LLM query expansion for complex queries."""
        search_limit = citation_limit if citation_limit and citation_limit > limit else limit

        # For simple queries, just do direct vector search
        if len(query.split()) <= 5 or self._is_simple_query(query):
            return await self._direct_vector_search(query, topic, search_limit)

        # For complex queries, use LLM to generate multiple search queries
        generated_queries = await self._generate_search_queries(query, topic)

        if not generated_queries or len(generated_queries) <= 1:
            # Fallback to direct search
            return await self._direct_vector_search(query, topic, search_limit)

        # Run searches for each generated query
        all_articles = []
        per_query = max(10, search_limit // len(generated_queries))

        for gen_query in generated_queries:
            result = await self._direct_vector_search(gen_query, topic, per_query)
            all_articles.extend(result.get('articles', []))

        # Deduplicate and rank
        seen_uris = set()
        unique_articles = []
        for article in all_articles:
            uri = article.get('uri', '')
            if uri and uri not in seen_uris:
                seen_uris.add(uri)
                unique_articles.append(article)

        # Sort by similarity score
        unique_articles.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)

        return {
            'articles': unique_articles[:limit],
            'search_method': 'smart_vector_expanded',
            'metadata': {
                'query_type': 'semantic_search',
                'original_query': query,
                'generated_queries': generated_queries,
                'total_found': len(all_articles),
                'unique_after_dedup': len(unique_articles)
            }
        }

    def _is_simple_query(self, query: str) -> bool:
        """Check if query is simple enough to skip LLM expansion."""
        # Simple queries: short, no complex structure
        if len(query) < 50:
            return True
        # Queries with clear search terms
        if not any(word in query.lower() for word in ['and', 'or', 'between', 'compare', 'versus']):
            return True
        return False

    async def _direct_vector_search(self, query: str, topic: str, limit: int) -> Dict:
        """Direct vector search without query expansion."""
        metadata_filter = {"topic": topic} if topic else {}

        try:
            results = vector_search_articles(
                query=query,
                top_k=limit,
                metadata_filter=metadata_filter
            )

            articles = []
            for result in results or []:
                metadata = result.get('metadata', {})
                if not metadata:
                    continue

                articles.append({
                    'uri': metadata.get('uri', ''),
                    'url': metadata.get('url') or metadata.get('link') or metadata.get('uri', ''),
                    'title': metadata.get('title', 'Unknown Title'),
                    'summary': metadata.get('summary', ''),
                    'category': metadata.get('category', 'Uncategorized'),
                    'sentiment': metadata.get('sentiment', 'Neutral'),
                    'future_signal': metadata.get('future_signal', 'None'),
                    'time_to_impact': metadata.get('time_to_impact', 'Unknown'),
                    'publication_date': metadata.get('publication_date', ''),
                    'news_source': metadata.get('news_source', 'Unknown'),
                    'topic': topic or metadata.get('topic', 'Unknown'),
                    'similarity_score': result.get('score', 0.0)
                })

            return {
                'articles': articles,
                'search_method': 'direct_vector',
                'metadata': {'query': query, 'topic': topic}
            }

        except Exception as e:
            self.logger.error(f"Direct vector search failed: {e}")
            return {'articles': [], 'search_method': 'direct_vector', 'error': str(e)}

    async def _generate_search_queries(self, query: str, topic: str) -> List[str]:
        """Generate multiple targeted search queries using LLM (for complex queries only)."""
        try:
            # Get topic context for better query generation
            topic_context = self.analyze_db.get_topic_options(topic) if topic else {}
            categories = topic_context.get('categories', [])[:10]

            prompt = f"""Generate 3-5 focused search queries to find articles relevant to this user question.
Each query should target a different aspect or angle of the topic.

User question: "{query}"
Topic: {topic or 'All Topics'}
Available categories: {', '.join(categories) if categories else 'Various'}

Return ONLY a JSON array of search query strings, nothing else.
Example: ["AI healthcare diagnosis", "machine learning medical imaging", "AI drug discovery"]

Search queries:"""

            ai_model = get_ai_model('gpt-4.1-mini')
            response = ai_model.generate_response([
                {"role": "system", "content": "You are a search query optimizer. Return only valid JSON arrays."},
                {"role": "user", "content": prompt}
            ])

            # Parse response
            import re
            # Find JSON array in response
            match = re.search(r'\[.*?\]', response, re.DOTALL)
            if match:
                queries = json.loads(match.group())
                if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                    self.logger.info(f"Generated {len(queries)} search queries: {queries}")
                    return queries[:5]  # Max 5 queries

        except Exception as e:
            self.logger.warning(f"Query generation failed: {e}")

        # Fallback: return original query
        return [query]


class AuspexService:
    """Enhanced Auspex service with MCP integration and chat persistence."""

    def __init__(self):
        self.db = get_database_instance()
        self.tools = get_auspex_tools_service()
        self.search_router = get_search_router()
        self.chart_service = ChartService()

        # Initialize plugin tool registry
        self.tool_registry = init_tool_registry()
        logger.info(f"Loaded {len(self.tool_registry.get_all_tools())} plugin tools")

        # Initialize context optimization manager with a reasonable default
        # This will be updated dynamically based on the actual model used
        self.context_manager = OptimizedContextManager(model_context_limit=128000)  # Default to GPT-4o limit

        # Initialize smart query router for intelligent data retrieval
        self.query_router = QueryRouter(self.db)

        # Cache for last fetched articles - used for chart generation to avoid duplicate searches
        self._last_chat_articles: List[Dict] = []

        self._ensure_default_prompt()
    
    def _ensure_default_prompt(self):
        """Ensure default Auspex prompt exists in database."""
        try:
            existing = self.db.get_auspex_prompt("default")
            if not existing:
                self.db.create_auspex_prompt(
                    name="default",
                    title="Default Auspex Assistant",
                    content=DEFAULT_AUSPEX_PROMPT,
                    description="The default system prompt for Auspex AI assistant",
                    is_default=True
                )
        except Exception as e:
            logger.error(f"Error ensuring default prompt: {e}")

    def _extract_entity_names(self, query: str) -> List[str]:
        """Extract potential entity names (companies, people, products, etc.) from query."""
        import re
        
        # Patterns that indicate specific entity queries
        entity_patterns = [
            # Company/organization patterns (original)
            r'references to ([A-Z][A-Za-z\s]+(?:AI|Inc|Corp|LLC|Ltd|Company|Technologies|Tech|Security|Systems|Solutions|Software|Platform|Labs))\b',
            r'articles.*about ([A-Z][A-Za-z\s]+(?:AI|Inc|Corp|LLC|Ltd|Company|Technologies|Tech|Security|Systems|Solutions|Software|Platform|Labs))\b',
            r'summarize.*([A-Z][A-Za-z\s]+(?:AI|Inc|Corp|LLC|Ltd|Company|Technologies|Tech|Security|Systems|Solutions|Software|Platform|Labs))\b',
            r'\b([A-Z][A-Za-z]+\s+(?:AI|Inc|Corp|LLC|Ltd|Company|Technologies|Tech|Security|Systems|Solutions|Software|Platform|Labs))\b',
            r'\b([A-Z][A-Za-z]+(?:AI|Security|Tech|Systems|Solutions|Software|Platform|Labs))\b',
            
            # Person name patterns - more precise
            r'mentioning\s+([A-Z][A-Za-z]+(?:\s+[A-Z]\.?[A-Za-z]*)*(?:\s+[A-Z][A-Za-z]+)*)\b',  # "mentioning Neil Armstrong"
            r'references to\s+([A-Z][A-Za-z]+(?:\s+[A-Z]\.?[A-Za-z]*)*(?:\s+[A-Z][A-Za-z]+)*)\b',  # "references to J.R.R. Tolkien"
            r'about\s+([A-Z][A-Za-z]+(?:\s+[A-Z]\.?[A-Za-z]*)*(?:\s+[A-Z][A-Za-z]+)*)\b',  # "about John Smith"
        ]
        
        entities = []
        for pattern in entity_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                if not match:  # Skip None or empty matches
                    continue
                entity = match.strip() if isinstance(match, str) else str(match).strip()
                if not entity:  # Skip if empty after stripping
                    continue
                # More sophisticated filtering
                entity_lower = entity.lower()
                # Skip common false positives and partial words
                skip_patterns = ['the', 'and', 'for', 'with', 'from', 'about', 'articles', 'news', 'data', 'information',
                               'n ai', 'in ai', 'te articles', 'le references', 'an ai', 'on ai', 'ai', 'to ai',
                               'these topics', 'this topic', 'the topic', 'topic area', 'research focus', 'analysis focus',
                               'context from', 'research on', 'analysis of', 'focus on', 'investigation of']
                
                if (len(entity) > 2 and 
                    entity_lower not in skip_patterns and
                    (not entity_lower.endswith(' ai') or entity_lower in ['openai', 'simbian ai', 'anthropic ai']) and
                    len(entity.split()) <= 5 and
                    not entity.startswith(('n ', 'te ', 'le ', 'an ', 'on '))):  # Avoid partial word matches
                    entities.append(entity)
        
        # Additional check: if query contains "mentioning" or "about" followed by a capitalized name, extract it
        # But skip if it's part of a research prompt template
        if not any(phrase in query.lower() for phrase in ['research focus:', 'topic area:', 'context from', 'please use your tools']):
            simple_patterns = [
                r'mentioning\s+([A-Z][A-Za-z]+(?:\s+[A-Z]\.?[A-Za-z]*)*(?:\s+[A-Z][A-Za-z]+)*)',
                r'about\s+([A-Z][A-Za-z]+(?:\s+[A-Z]\.?[A-Za-z]*)*(?:\s+[A-Z][A-Za-z]+)*)',
                r'regarding\s+([A-Z][A-Za-z]+(?:\s+[A-Z]\.?[A-Za-z]*)*(?:\s+[A-Z][A-Za-z]+)*)',
            # Special patterns for names with periods/initials (flexible)
            r'about\s+([A-Z]\.(?:[A-Z]\.)*[A-Z]\.?\s+[A-Z][A-Za-z]+)',  # "about J.R.R. Tolkien"
            r'mentioning\s+([A-Z]\.(?:[A-Z]\.)*[A-Z]\.?\s+[A-Z][A-Za-z]+)',  # "mentioning J.R.R. Tolkien"
            r'references to\s+([A-Z]\.(?:[A-Z]\.)*[A-Z]\.?\s+[A-Z][A-Za-z]+)',  # "references to J.R.R. Tolkien"
            # Patterns for initials without periods (e.g., "J.R.R tolkien") - flexible case
            r'about\s+([A-Z]\.?[A-Z]\.?[A-Z]\.?\s+[A-Za-z]+)',  # "about J.R.R tolkien" or "about JRR Tolkien"
            r'mentioning\s+([A-Z]\.?[A-Z]\.?[A-Z]\.?\s+[A-Za-z]+)',  # "mentioning J.R.R tolkien"
            r'references to\s+([A-Z]\.?[A-Z]\.?[A-Z]\.?\s+[A-Za-z]+)',  # "references to J.R.R tolkien"
            ]
            
            for pattern in simple_patterns:
                matches = re.findall(pattern, query)
                for match in matches:
                    entity = match.strip()
                    if (len(entity) > 2 and 
                        not entity.lower() in ['the', 'and', 'for', 'with', 'from', 'articles', 'news', 'these topics', 'this topic'] and
                        len(entity.split()) <= 4):
                        entities.append(entity)
        
        return list(set(entities))  # Remove duplicates

    def _validate_entity_in_sql_database(self, entities: List[str], topic: str) -> int:
        """Validate if entities exist in SQL database by performing comprehensive search."""
        if not entities:
            return 0
        
        total_articles_found = 0
        
        for entity in entities:
            logger.info(f"SQL validation: Searching for entity '{entity}' in topic '{topic}'")
            
            try:
                # Search using the database's search_articles method with keyword search
                articles, count = self.db.search_articles(
                    topic=topic,
                    keyword=entity,  # This searches title, summary, category, future_signal, sentiment, tags
                    page=1,
                    per_page=100  # Get a reasonable sample to validate existence
                )
                
                if articles:
                    # Double-check that the articles actually contain the entity (case-insensitive)
                    entity_lower = entity.lower()
                    verified_articles = 0
                    
                    for article in articles:
                        title = article.get('title', '').lower()
                        summary = article.get('summary', '').lower()
                        content_to_search = f"{title} {summary}"
                        
                        if entity_lower in content_to_search:
                            verified_articles += 1
                    
                    logger.info(f"SQL validation: Found {count} articles for '{entity}', {verified_articles} verified to contain entity")
                    total_articles_found += verified_articles
                else:
                    logger.info(f"SQL validation: No articles found for entity '{entity}' in topic '{topic}'")
                    
            except Exception as e:
                logger.error(f"SQL validation error for entity '{entity}': {e}")
        
        logger.info(f"SQL validation complete: {total_articles_found} total articles found containing entities {entities}")
        return total_articles_found

    def _get_entity_articles_from_sql(self, entities: List[str], topic: str, limit: int) -> List[Dict]:
        """Retrieve articles from SQL database that actually contain the specified entities."""
        if not entities:
            return []
        
        all_articles = []
        seen_uris = set()
        
        for entity in entities:
            try:
                # Search using the database's search_articles method
                articles, count = self.db.search_articles(
                    topic=topic,
                    keyword=entity,
                    page=1,
                    per_page=limit * 2  # Get more to allow for filtering
                )
                
                # Filter to only include articles that actually contain the entity
                entity_lower = entity.lower()
                for article in articles:
                    # Skip duplicates
                    uri = article.get('uri')
                    if uri in seen_uris:
                        continue
                    
                    title = article.get('title', '').lower()
                    summary = article.get('summary', '').lower()
                    content_to_search = f"{title} {summary}"
                    
                    if entity_lower in content_to_search:
                        # Convert to the same format as vector articles
                        formatted_article = {
                            "uri": uri,
                            "title": article.get("title", "Unknown Title"),
                            "url": article.get("url") or article.get("link") or uri,  # Use uri as fallback
                            "summary": article.get("summary", "No summary available"),
                            "category": article.get("category", "Uncategorized"),
                            "sentiment": article.get("sentiment", "Neutral"),
                            "future_signal": article.get("future_signal", "None"),
                            "time_to_impact": article.get("time_to_impact", "Unknown"),
                            "publication_date": article.get("publication_date", "Unknown"),
                            "news_source": article.get("news_source", "Unknown"),
                            "tags": article.get("tags", "").split(",") if article.get("tags") else [],
                            "similarity_score": 1.0  # High score since it's an exact match
                        }
                        all_articles.append(formatted_article)
                        seen_uris.add(uri)
                        
                        if len(all_articles) >= limit:
                            break
                            
            except Exception as e:
                logger.error(f"Error retrieving SQL articles for entity '{entity}': {e}")
        
        logger.info(f"Retrieved {len(all_articles)} articles from SQL database for entities: {entities}")
        return all_articles[:limit]

    def _filter_articles_by_entity_content(self, articles: List[Dict], entities: List[str]) -> List[Dict]:
        """Filter articles to only include those that actually mention the specified entities."""
        if not entities:
            return articles
        
        filtered_articles = []
        entity_patterns = []
        
        # Create case-insensitive patterns for each entity
        for entity in entities:
            # Create flexible patterns that handle variations
            entity_clean = entity.replace(' AI', '').replace(' Inc', '').replace(' Corp', '').strip()
            patterns = [
                entity.lower(),  # Exact match
                entity_clean.lower(),  # Without suffix
                entity.replace(' ', '').lower(),  # No spaces
            ]
            entity_patterns.extend(patterns)
        
        logger.info(f"Filtering articles for entities: {entities}")
        logger.info(f"Using search patterns: {entity_patterns}")
        
        for article in articles:
            # Check title and summary for entity mentions
            title = article.get('title', '').lower()
            summary = article.get('summary', '').lower()
            content_to_search = f"{title} {summary}"
            
            # Check if any entity pattern is found in the content
            entity_found = any(pattern in content_to_search for pattern in entity_patterns)
            
            if entity_found:
                filtered_articles.append(article)
                logger.debug(f"Entity found in article: {article.get('title', 'Unknown')}")
        
        logger.info(f"Filtered {len(articles)} articles down to {len(filtered_articles)} articles containing specified entities")
        return filtered_articles

    async def create_chat_session(self, topic: str, user_id: str = None, title: str = None, profile_id: int = None) -> int:
        """Create a new chat session with optional organizational profile."""
        try:
            if not title:
                title = f"Chat about {topic}"

            # For OAuth users or users not in the users table, use None for user_id
            # This avoids foreign key constraint issues
            oauth_user_identifier = None
            if user_id:
                # If user_id is a dict (OAuth user), extract username and set user_id to None
                if isinstance(user_id, dict):
                    oauth_user_identifier = user_id.get('username') or user_id.get('email')
                    logger.info(f"OAuth user {oauth_user_identifier} detected, creating chat without user_id")
                    user_id = None
                else:
                    # Check if user exists in users table
                    user_exists = self.db.get_user(user_id)
                    if not user_exists:
                        logger.info(f"User {user_id} not found in users table, creating chat without user_id")
                        oauth_user_identifier = user_id  # Store OAuth user identifier
                        user_id = None

            metadata = {
                "created_at": datetime.now().isoformat(),
                "profile_id": profile_id
            }
            if oauth_user_identifier:
                metadata["oauth_user"] = oauth_user_identifier

            chat_id = self.db.create_auspex_chat(
                topic=topic,
                title=title,
                user_id=user_id,
                profile_id=profile_id,
                metadata=metadata
            )

            # Add system message with current prompt
            prompt = self.get_system_prompt()
            self.db.add_auspex_message(
                chat_id=chat_id,
                role="system",
                content=prompt['content'],
                metadata={"prompt_name": prompt['name']}
            )

            return chat_id
        except Exception as e:
            logger.error(f"Error creating chat session: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create chat session")

    def get_chat_sessions(self, topic: str = None, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get chat sessions."""
        try:
            return self.db.get_auspex_chats(topic=topic, user_id=user_id, limit=limit)
        except Exception as e:
            logger.error(f"Error getting chat sessions: {e}")
            return []

    def get_chat_history(self, chat_id: int) -> List[Dict]:
        """Get chat history for a session."""
        try:
            return self.db.get_auspex_messages(chat_id)
        except Exception as e:
            logger.error(f"Error getting chat history: {e}")
            return []

    def delete_chat_session(self, chat_id: int) -> bool:
        """Delete a chat session."""
        try:
            return self.db.delete_auspex_chat(chat_id)
        except Exception as e:
            logger.error(f"Error deleting chat session: {e}")
            return False

    def get_citation_limit(self, total_articles: int, user_override: Optional[int] = None) -> int:
        """
        Determine citation limit based on user preference or default.

        Args:
            total_articles: Total number of articles available
            user_override: User-specified limit (takes precedence if provided)

        Returns:
            int: Number of articles to include in detailed context
        """
        # User override takes precedence
        if user_override is not None:
            limit = max(MIN_CITATION_LIMIT, min(user_override, MAX_CITATION_LIMIT))
            logger.info(f"Using user-specified citation limit: {limit}")
            return min(limit, total_articles)  # Can't cite more than available

        # Use default
        limit = min(DEFAULT_CITATION_LIMIT, total_articles)
        logger.info(f"Using default citation limit: {limit} (available: {total_articles})")
        return limit

    async def chat_with_tools(self, chat_id: int, message: str, model: str = None, limit: int = 50, tools_config: Dict = None, profile_id: int = None, custom_prompt: str = None, article_detail_limit: Optional[int] = None, include_charts: bool = False, sampling_strategy: str = None) -> AsyncGenerator[str, None]:
        """Chat with Auspex with optional tool usage and custom system prompt override.

        Args:
            sampling_strategy: Optional sampling strategy preset name (e.g., 'recency_diversity', 'quality_first').
                              If None, uses intelligent defaults based on context.
        """
        if not model:
            model = DEFAULT_MODEL

        # Clear cached articles from previous requests
        self._last_chat_articles = []

        # Update context manager for the specific model being used
        self._update_context_manager_for_model(model)

        try:
            # Get chat history
            messages = self.db.get_auspex_messages(chat_id)

            # Build conversation history for LLM
            conversation = []
            for msg in messages:
                if msg['role'] != 'system':  # Skip system messages in conversation
                    conversation.append({
                        "role": msg['role'],
                        "content": msg['content']
                    })

            # Add current user message
            conversation.append({
                "role": "user",
                "content": message
            })

            # Save user message to database
            self.db.add_auspex_message(
                chat_id=chat_id,
                role="user",
                content=message
            )

            # Update chat session with profile_id if provided
            if profile_id:
                try:
                    self.db.update_auspex_chat_profile(chat_id, profile_id)
                    logger.info(f"Updated chat {chat_id} with profile_id {profile_id}")
                except Exception as e:
                    logger.warning(f"Could not update chat profile: {e}")

            # Use custom prompt if provided, otherwise get enhanced system prompt
            if custom_prompt:
                logger.info(f"Using custom system prompt for chat {chat_id}")
                system_prompt_content = custom_prompt
            else:
                # Get system prompt and enhance it with topic information and profile context
                # Pass include_charts to let Auspex know it can use chart visualizations
                system_prompt = self.get_enhanced_system_prompt(chat_id, tools_config, include_charts)
                system_prompt_content = system_prompt['content']

            # Prepare messages with system prompt
            llm_messages = [
                {"role": "system", "content": system_prompt_content},
                *conversation
            ]
            
            # Check if we need to use tools based on the message content and tools_config
            use_tools = tools_config and any(tools_config.values()) if tools_config else True
            needs_tools = use_tools and await self._should_use_tools(message)

            # Check for explicit chart request in message (e.g., "show me a chart")
            # Note: include_charts toggle is handled AFTER plugin tools, to avoid duplicating
            # when plugins like Trend Analysis already generate their own charts
            chart_type = self._detect_chart_request(message)
            chart_marker = None
            logger.info(f"Chart detection result for message '{message}': chart_type={chart_type}, include_charts={include_charts}")

            plugin_final_response = None
            plugin_chart_markers = []  # Store chart markers from plugin tools - initialize outside if block
            if needs_tools:
                # First check for plugin tools that might handle this query
                chat = self.db.get_auspex_chat(chat_id)
                topic = chat['topic'] if chat else ""
                # Handle cross-topic mode: __all__ means search all topics
                if topic == '__all__':
                    topic = None  # Set to None to skip topic filtering in tools

                plugin_results, is_final_response = await self._check_plugin_tools(message, topic, chat_id)
                if plugin_results:
                    if is_final_response:
                        # Plugin produced a complete LLM response - return directly
                        plugin_final_response = plugin_results
                        logger.info(f"Plugin produced final response, skipping main LLM")
                    else:
                        # Plugin produced context for main LLM
                        llm_messages.append({
                            "role": "assistant",
                            "content": plugin_results
                        })
                        # Extract chart markers from plugin results to yield directly to user
                        import re
                        chart_pattern = r'<!-- CHART_DATA:.*?:END_CHART -->'
                        plugin_chart_markers = re.findall(chart_pattern, plugin_results, re.DOTALL)
                        if plugin_chart_markers:
                            logger.info(f"Extracted {len(plugin_chart_markers)} chart markers from plugin results")

                # Only use additional tools if plugin didn't produce a final response
                if not plugin_final_response:
                    # Use standard tools to gather information with citation limit
                    tool_results = await self._use_mcp_tools(message, chat_id, limit, tools_config, article_detail_limit, sampling_strategy)
                    if tool_results:
                        # Add tool results as assistant context to avoid overriding system instructions
                        llm_messages.append({
                            "role": "assistant",
                            "content": f"[TOOLS] {tool_results}"
                        })

                    # Only generate a chart if explicitly requested in the user's message
                    # The include_charts toggle affects the system prompt to tell Auspex it CAN use charts,
                    # but doesn't auto-generate them. Plugin tools generate their own charts.
                    # If chart request detected, generate chart from articles
                    # For cross-topic mode (topic=None), we can still generate charts
                    if chart_type:
                        chart_topic_label = topic if topic else "All Topics"
                        logger.info(f"Chart request detected: generating {chart_type} chart for topic '{chart_topic_label}'")

                        # Use cached articles from the main query (same articles used for LLM context)
                        # This avoids a duplicate vector search and ensures chart matches the analysis
                        if self._last_chat_articles:
                            chart_articles = self._last_chat_articles
                            logger.info(f"Using {len(chart_articles)} cached articles for chart generation (same as LLM context)")
                        else:
                            # Fallback to separate search if cache is empty (shouldn't happen normally)
                            logger.warning("No cached articles available, falling back to separate search")
                            chart_articles = await self._get_articles_for_chart(topic, limit)
                            logger.info(f"Retrieved {len(chart_articles)} articles for chart generation via fallback")

                        if chart_articles:
                            chart_title = f"Sentiment Distribution for {chart_topic_label}" if chart_type == "sentiment_donut" else None
                            chart_marker = self._generate_chart_for_articles(chart_articles, chart_type, chart_title)
                            logger.info(f"Generated chart marker for {chart_type}: {len(chart_marker) if chart_marker else 0} chars")
                        else:
                            logger.warning(f"No articles found for chart generation (topic: {topic})")

            # Generate response using LLM or return plugin response directly
            full_response = ""

            # Add plugin tool chart markers to chart_marker
            for marker in plugin_chart_markers:
                if chart_marker:
                    chart_marker += "\n" + marker
                else:
                    chart_marker = marker

            # If we have a chart, yield it first as a special marker
            if chart_marker:
                full_response += chart_marker + "\n\n"
                yield chart_marker + "\n\n"

            if plugin_final_response:
                # Yield plugin response directly (already LLM-generated)
                full_response += plugin_final_response
                yield plugin_final_response
            else:
                # Generate response using main LLM
                async for chunk in self._generate_streaming_response(llm_messages, model):
                    full_response += chunk
                    yield chunk
            
            # Save assistant response to database
            self.db.add_auspex_message(
                chat_id=chat_id,
                role="assistant",
                content=full_response,
                model_used=model,
                metadata={"used_tools": needs_tools, "tools_config": tools_config}
            )
            
        except Exception as e:
            logger.error(f"Error in chat_with_tools: {e}")
            error_msg = f"I apologize, but I encountered an error: {str(e)}"
            yield error_msg
            
            # Save error message
            try:
                self.db.add_auspex_message(
                    chat_id=chat_id,
                    role="assistant",
                    content=error_msg,
                    model_used=model,
                    metadata={"error": True, "tools_config": tools_config}
                )
            except:
                pass

    def get_enhanced_system_prompt(self, chat_id: int, tools_config: Dict = None, include_charts: bool = False) -> Dict:
        """Get enhanced system prompt with topic-specific information and organizational profile.

        Args:
            chat_id: The chat ID to get context for
            tools_config: Optional tools configuration
            include_charts: If True, tells Auspex it can request chart visualizations
        """
        try:
            # Get base prompt
            base_prompt = self.get_system_prompt()
            
            # Get chat info to determine topic and profile
            chat = self.db.get_auspex_chat(chat_id)
            if not chat:
                return base_prompt
                
            topic = chat['topic']
            # Handle cross-topic mode: __all__ means search all topics
            is_cross_topic = (topic == '__all__')
            topic_display = "All Topics" if is_cross_topic else topic
            topic_for_query = None if is_cross_topic else topic
            # Support both new schema (column) and old schema (metadata.profile_id)
            profile_id = chat.get('profile_id') or ((chat.get('metadata') or {}).get('profile_id'))
            
            # Get organizational profile context if available
            profile_context = ""
            if profile_id:
                try:
                    from app.database_query_facade import DatabaseQueryFacade
                    profile_row = DatabaseQueryFacade(self.db, logger).get_organisational_profile(profile_id)
                    if profile_row:
                        import json
                        profile = {
                            'name': profile_row['name'],
                            'industry': profile_row['industry'],
                            'organization_type': profile_row['organization_type'],
                            'key_concerns': json.loads(profile_row['key_concerns']) if profile_row['key_concerns'] else [],
                            'strategic_priorities': json.loads(profile_row['strategic_priorities']) if profile_row['strategic_priorities'] else [],
                            'risk_tolerance': profile_row['risk_tolerance'],
                            'innovation_appetite': profile_row['innovation_appetite'],
                            'decision_making_style': profile_row['decision_making_style'],
                            'stakeholder_focus': json.loads(profile_row['stakeholder_focus']) if profile_row['stakeholder_focus'] else [],
                            'competitive_landscape': json.loads(profile_row['competitive_landscape']) if profile_row['competitive_landscape'] else [],
                            'regulatory_environment': json.loads(profile_row['regulatory_environment']) if profile_row['regulatory_environment'] else []
                        }
                        
                        profile_context = f"""

CRITICAL: You are analyzing from the perspective of {profile['name']} ({profile.get('organization_type', 'Organization')} in {profile.get('industry', 'General')}).

ORGANIZATIONAL PRIORITIES:
- Key Concerns: {', '.join(profile['key_concerns']) if profile['key_concerns'] else 'General business concerns'}
- Strategic Priorities: {', '.join(profile['strategic_priorities']) if profile['strategic_priorities'] else 'Growth and sustainability'}
- Risk Tolerance: {profile.get('risk_tolerance', 'Medium')} (adjust significance assessment accordingly)
- Innovation Appetite: {profile.get('innovation_appetite', 'Moderate')}
- Decision Making Style: {profile.get('decision_making_style', 'Collaborative')}
- Key Stakeholders: {', '.join(profile['stakeholder_focus']) if profile['stakeholder_focus'] else 'Customers and employees'}
- Competitive Landscape: {', '.join(profile['competitive_landscape']) if profile['competitive_landscape'] else 'Industry competitors'}
- Regulatory Environment: {', '.join(profile['regulatory_environment']) if profile['regulatory_environment'] else 'Standard regulations'}

MANDATORY ANALYSIS ADJUSTMENTS:
1. PRIORITIZE insights directly relevant to {profile['name']}'s key concerns: {', '.join(profile['key_concerns']) if profile['key_concerns'] else 'general concerns'}
2. FRAME all analysis in terms of impact on: {', '.join(profile['stakeholder_focus']) if profile['stakeholder_focus'] else 'key stakeholders'}
3. ASSESS significance using {profile.get('risk_tolerance', 'medium')} risk tolerance (conservative = higher significance for regulatory/compliance issues)
4. TAILOR recommendations to {profile.get('decision_making_style', 'collaborative')} decision-making approach
5. FOCUS on {profile.get('industry', 'industry')}-specific implications, competitive positioning, and regulatory compliance
6. HIGHLIGHT opportunities and threats specific to {profile['name']}'s strategic priorities and competitive landscape

When analyzing sentiment patterns, trends, or providing insights, ALWAYS consider how they specifically impact {profile['name']}'s business model, stakeholder relationships, and strategic objectives.
"""
                        logger.info(f"Using organizational profile: {profile['name']} for Auspex chat")
                except Exception as e:
                    logger.error(f"Error loading organizational profile {profile_id}: {str(e)}")
            
            # Get topic options from database
            try:
                analyze_db = AnalyzeDB(self.db)
                topic_options = analyze_db.get_topic_options(topic_for_query)

                # Add null check for topic_options
                if not topic_options:
                    logger.warning(f"No topic options found for topic: {topic_display}")
                    topic_options = {
                        'categories': [],
                        'sentiments': [],
                        'futureSignals': [],
                        'timeToImpacts': [],
                        'driverTypes': []
                    }

                # Enhanced system prompt with profile context prioritized
                # Insert organizational context early in the prompt for maximum impact
                base_content = base_prompt['content']
                
                # Find a good insertion point after the initial role definition
                insertion_point = base_content.find("CRITICAL RESPONSE FORMAT REQUIREMENTS:")
                if insertion_point == -1:
                    insertion_point = base_content.find("STRATEGIC FORESIGHT FRAMEWORK:")
                if insertion_point == -1:
                    insertion_point = len(base_content) // 4  # Insert after first quarter if no markers found
                
                # Insert profile context prominently
                enhanced_content = f"""{base_content[:insertion_point]}
{profile_context}

{base_content[insertion_point:]}

TOPIC-SPECIFIC CONTEXT FOR {topic_display.upper()}:

Available Categories in this topic:
{', '.join(topic_options.get('categories', []))}

Available Sentiments:
{', '.join(topic_options.get('sentiments', []))}

Available Future Signals:
{', '.join(topic_options.get('futureSignals', []))}

Available Time to Impact Options:
{', '.join(topic_options.get('timeToImpacts', []))}

TOOLS STATUS: {self._format_tools_status(tools_config)}

CURRENT SESSION CONTEXT:
- Topic: {topic_display}
- Profile: {profile.get('name', 'None') if profile_id else 'None'}
- Tools: {self._format_active_tools(tools_config)}
- Charts: {'ENABLED - You can include chart visualizations (pie charts, bar charts, etc.) in your analysis when appropriate. Request charts by mentioning them in your response.' if include_charts else 'Not enabled'}
- Focus: {'Cross-topic analysis using strategic foresight methodology' if is_cross_topic else f'Apply strategic foresight methodology specific to {topic_display}'} with organizational context"""

                return {
                    "name": f"enhanced_{topic_display.lower().replace(' ', '_')}",
                    "title": f"Enhanced Auspex for {topic_display}",
                    "content": enhanced_content
                }
                
            except Exception as e:
                logger.warning(f"Could not get topic options for {topic_display}: {e}")
                # Fallback: still inject organizational profile context even without topic options
                try:
                    base_content = base_prompt['content']
                    if profile_context:
                        insertion_point = base_content.find("CRITICAL RESPONSE FORMAT REQUIREMENTS:")
                        if insertion_point == -1:
                            insertion_point = base_content.find("STRATEGIC FORESIGHT FRAMEWORK:")
                        if insertion_point == -1:
                            insertion_point = len(base_content) // 4
                        enhanced_content = f"""{base_content[:insertion_point]}
{profile_context}

{base_content[insertion_point:]}"""
                        return {
                            "name": f"enhanced_{topic_display.lower().replace(' ', '_')}",
                            "title": f"Enhanced Auspex for {topic_display}",
                            "content": enhanced_content
                        }
                except Exception:
                    pass
                return base_prompt
                
        except Exception as e:
            logger.error(f"Error getting enhanced system prompt: {e}")
            return self.get_system_prompt()

    async def _should_use_tools(self, message: str) -> bool:
        """Determine if message requires tool usage."""
        tool_keywords = [
            "search", "find", "latest", "recent", "news", "articles", "trends",
            "sentiment", "analyze", "data", "statistics", "categories", "compare",
            "what's happening", "current", "update", "insights", "patterns",
            "comprehensive", "detailed", "deep", "thorough", "analysis", "themes",
            "follow up", "more", "details", "expand", "elaborate", "investigate",
            "chart", "graph", "pie", "visualization", "visualize", "plot", "donut",
            # Plugin tool triggers
            "future", "impact", "prediction", "forecast", "outlook", "risk", "opportunity",
            "bias", "partisan", "political", "left", "right", "liberal", "conservative"
        ]
        
        message_lower = message.lower()
        should_use = any(keyword in message_lower for keyword in tool_keywords)
        
        logger.info(f"Tool detection for message '{message}': {should_use}")
        if should_use:
            found_keywords = [kw for kw in tool_keywords if kw in message_lower]
            logger.info(f"Found keywords: {found_keywords}")

        return should_use

    def _detect_chart_request(self, message: str) -> Optional[str]:
        """
        Detect if the user is requesting a chart/visualization.

        Returns the chart type if detected, None otherwise.
        """
        message_lower = message.lower()

        # Chart type detection patterns
        chart_patterns = {
            "sentiment_donut": [
                "pie chart", "pie graph", "donut chart", "donut graph",
                "sentiment pie", "sentiment donut", "sentiment distribution chart",
                "show sentiment as pie", "sentiment breakdown chart"
            ],
            "sentiment_timeline": [
                "sentiment over time", "sentiment timeline", "sentiment trends chart",
                "sentiment line chart", "sentiment graph over time", "sentiment trend chart"
            ],
            "volume": [
                "article volume", "volume chart", "volume over time",
                "article count chart", "how many articles chart", "publication volume"
            ],
            "category_bar": [
                "category chart", "category bar", "categories bar chart",
                "top categories chart", "category distribution chart"
            ],
            "radar": [
                "radar chart", "spider chart", "signal radar",
                "signal analysis chart", "future signals radar"
            ]
        }

        # Generic chart keywords that default to sentiment_donut
        generic_chart_keywords = [
            "chart of sentiment", "sentiment chart", "visualize sentiment",
            "graph sentiment", "show me a chart", "create a chart",
            "generate a chart", "make a chart", "pie chart", "donut chart",
            "[include charts]"  # Charts mode toggle prefix
        ]

        # Check for specific chart type patterns
        for chart_type, patterns in chart_patterns.items():
            for pattern in patterns:
                if pattern in message_lower:
                    logger.info(f"Detected chart request: {chart_type} (pattern: {pattern})")
                    return chart_type

        # Check for generic chart request (default to sentiment donut)
        for keyword in generic_chart_keywords:
            if keyword in message_lower:
                logger.info(f"Detected generic chart request, defaulting to sentiment_donut (keyword: {keyword})")
                return "sentiment_donut"

        return None

    def _generate_chart_for_articles(self, articles: List[Dict], chart_type: str, title: str = None) -> Optional[str]:
        """
        Generate a chart marker for the given articles and chart type.

        Returns the chart marker string or None if generation fails.
        """
        if not articles:
            logger.warning("Cannot generate chart: no articles provided")
            return None

        try:
            # Use the chart_service to generate the chart marker
            chart_marker = self.chart_service.generate_chart_marker(
                chart_type=chart_type,
                articles=articles,
                title=title
            )
            logger.info(f"Generated {chart_type} chart for {len(articles)} articles")
            return chart_marker
        except Exception as e:
            logger.error(f"Error generating chart: {e}")
            return None

    async def _get_articles_for_chart(self, topic: str = None, limit: int = 100) -> List[Dict]:
        """
        Get articles for chart generation.

        Uses vector search to get articles with sentiment data for the given topic.
        If topic is None (cross-topic mode), searches across all topics.
        """
        try:
            # Build metadata filter for topic (skip for cross-topic mode)
            metadata_filter = {"topic": topic} if topic else {}

            # Use vector search to get articles
            search_query = f"articles about {topic}" if topic else "recent news articles trends analysis"
            vector_results = vector_search_articles(
                query=search_query,
                top_k=limit,
                metadata_filter=metadata_filter
            )

            articles = []
            if vector_results and isinstance(vector_results, list):
                for result in vector_results:
                    if not result or not isinstance(result, dict):
                        continue

                    metadata = result.get("metadata")
                    if not metadata or not isinstance(metadata, dict):
                        continue

                    # Only add articles with valid data
                    uri = metadata.get("uri")
                    if not uri:
                        continue

                    articles.append({
                        "uri": uri,
                        "title": metadata.get("title", "Unknown Title"),
                        "url": metadata.get("url") or metadata.get("link") or uri,
                        "summary": metadata.get("summary", ""),
                        "category": metadata.get("category", "Uncategorized"),
                        "sentiment": metadata.get("sentiment", "neutral"),
                        "future_signal": metadata.get("future_signal", "None"),
                        "time_to_impact": metadata.get("time_to_impact", "Unknown"),
                        "publication_date": metadata.get("publication_date", "Unknown"),
                        "news_source": metadata.get("news_source", "Unknown"),
                    })

            logger.info(f"Retrieved {len(articles)} articles for chart generation (topic: {topic})")
            return articles

        except Exception as e:
            logger.error(f"Error getting articles for chart: {e}")
            return []

    async def _check_plugin_tools(self, message: str, topic: str, chat_id: int = None) -> tuple[Optional[str], bool]:
        """
        Check if any plugin tools should handle this message.

        Returns:
            tuple: (result_string, is_final_response)
            - result_string: Tool results as formatted string, or None if no plugin handles it
            - is_final_response: True if result should be returned directly (not re-processed by LLM)
        """
        # Find matching plugin tools
        matches = self.tool_registry.find_matching_tools(message, min_score=0.5)

        if not matches:
            return None, False

        best_tool, score = matches[0]
        logger.info(f"Plugin tool match: {best_tool.name} (score: {score})")

        # Check if handler is available
        if not self.tool_registry.get_handler(best_tool.name):
            logger.warning(f"No handler for plugin tool: {best_tool.name}")
            return None, False

        # Load organizational profile context if available
        profile_context = ""
        if chat_id:
            try:
                chat = self.db.get_auspex_chat(chat_id)
                profile_id = chat.get('profile_id') or ((chat.get('metadata') or {}).get('profile_id'))
                if profile_id:
                    from app.database_query_facade import DatabaseQueryFacade
                    profile_row = DatabaseQueryFacade(self.db, logger).get_organisational_profile(profile_id)
                    if profile_row:
                        profile = {
                            'name': profile_row['name'],
                            'industry': profile_row['industry'],
                            'organization_type': profile_row['organization_type'],
                            'key_concerns': json.loads(profile_row['key_concerns']) if profile_row['key_concerns'] else [],
                            'strategic_priorities': json.loads(profile_row['strategic_priorities']) if profile_row['strategic_priorities'] else [],
                            'risk_tolerance': profile_row['risk_tolerance'],
                            'stakeholder_focus': json.loads(profile_row['stakeholder_focus']) if profile_row['stakeholder_focus'] else [],
                        }
                        profile_context = f"""
ORGANIZATIONAL CONTEXT:
You are generating this content for {profile['name']} ({profile.get('organization_type', 'Organization')} in {profile.get('industry', 'General')}).

Key Concerns: {', '.join(profile['key_concerns']) if profile['key_concerns'] else 'General business concerns'}
Strategic Priorities: {', '.join(profile['strategic_priorities']) if profile['strategic_priorities'] else 'Growth and sustainability'}
Risk Tolerance: {profile.get('risk_tolerance', 'Medium')}
Key Stakeholders: {', '.join(profile['stakeholder_focus']) if profile['stakeholder_focus'] else 'Customers and employees'}

PRIORITIZE insights relevant to these concerns and tailor analysis to this organization's perspective.
"""
                        logger.info(f"Plugin using organizational profile: {profile['name']}")
            except Exception as e:
                logger.warning(f"Could not load organizational profile for plugin: {e}")

        # Build execution context
        context = {
            "topic": topic,
            "db": self.db,
            "vector_store": vector_search_articles,
            "ai_model": get_ai_model,
            "profile_context": profile_context
        }

        # Build params from the message (basic extraction)
        params = {
            "topic": topic
        }

        # Try to extract time period from message
        time_patterns = [
            (r'last\s*(\d+)\s*days?', lambda m: f"{m.group(1)}d"),
            (r'past\s*(\d+)\s*days?', lambda m: f"{m.group(1)}d"),
            (r'last\s*week', lambda m: "7d"),
            (r'last\s*month', lambda m: "30d"),
            (r'last\s*quarter', lambda m: "90d"),
            (r'last\s*year', lambda m: "365d"),
        ]

        import re
        for pattern, extractor in time_patterns:
            match = re.search(pattern, message.lower())
            if match:
                params["time_period"] = extractor(match)
                break

        # Execute the tool
        try:
            result = await self.tool_registry.execute_tool(
                best_tool.name,
                params,
                context
            )

            if result.success:
                # Check if this is a prompt-only tool with an LLM-generated response
                # These should be returned directly, not re-processed
                is_final = False
                analysis = result.data.get('analysis')
                if isinstance(analysis, str) and len(analysis) > 200:
                    # This is an LLM-generated response - return directly
                    is_final = True
                    logger.info(f"Plugin tool {best_tool.name} produced final LLM response ({len(analysis)} chars)")

                    # Append chart markers if chart_data exists
                    response = analysis
                    if 'chart_data' in result.data:
                        import json
                        chart_data = result.data['chart_data']
                        for chart_name, chart_config in chart_data.items():
                            chart_marker = {
                                "type": chart_name,
                                "format": "json",
                                "title": chart_config.get("layout", {}).get("title", chart_name.replace("_", " ").title()),
                                "data": chart_config
                            }
                            response += f"\n\n<!-- CHART_DATA:{json.dumps(chart_marker)}:END_CHART -->"
                        logger.info(f"Appended {len(chart_data)} chart markers to final response")

                    return response, is_final

                # Format result for inclusion in LLM context
                return self._format_plugin_result(best_tool.name, result), is_final
            else:
                logger.error(f"Plugin tool failed: {result.error}")
                return None, False

        except Exception as e:
            logger.error(f"Error executing plugin tool: {e}", exc_info=True)
            return None, False

    def _format_plugin_result(self, tool_name: str, result) -> str:
        """Format plugin tool result for LLM context."""
        from app.services.tool_plugin_base import ToolResult

        output_parts = [f"\n[TOOL: {tool_name}]"]

        if result.message:
            output_parts.append(f"Status: {result.message}")

        data = result.data

        # Format based on tool type
        if "summary" in data:
            output_parts.append(f"\nSummary:\n{data['summary']}")

        if "trends" in data:
            output_parts.append("\nKey Trends:")
            for trend in data.get("trends", [])[:5]:
                output_parts.append(f"- {trend.get('description', '')}")

        if "analysis" in data:
            analysis = data["analysis"]

            if "sentiment" in analysis:
                sent = analysis["sentiment"]
                output_parts.append(f"\nSentiment: {sent.get('trend_direction', 'stable')}")
                if "distribution" in sent:
                    dist = sent["distribution"]
                    output_parts.append(f"  Distribution: {dist}")

            if "categories" in analysis:
                cats = analysis["categories"]
                if cats.get("emerging"):
                    output_parts.append("\nEmerging Categories:")
                    for cat in cats["emerging"][:3]:
                        output_parts.append(f"  - {cat['category']} (+{cat['growth']}%)")

        if "article_count" in data:
            output_parts.append(f"\nArticles analyzed: {data['article_count']}")

        output_parts.append(f"\nExecution time: {result.execution_time_ms}ms")
        output_parts.append("[/TOOL]\n")

        # Add chart markers if chart_data is present
        if "chart_data" in data:
            import json
            chart_data = data["chart_data"]
            for chart_name, chart_config in chart_data.items():
                chart_marker = {
                    "type": chart_name,
                    "format": "json",  # Must be 'json' to match frontend check
                    "title": chart_config.get("layout", {}).get("title", chart_name.replace("_", " ").title()),
                    "data": chart_config
                }
                output_parts.append(f"\n<!-- CHART_DATA:{json.dumps(chart_marker)}:END_CHART -->")

        return "\n".join(output_parts)

    def get_available_plugin_tools(self) -> List[Dict]:
        """Get list of available plugin tools for UI display."""
        tools = []
        for tool_def in self.tool_registry.get_all_tools():
            tools.append({
                "name": tool_def.name,
                "version": tool_def.version,
                "description": tool_def.description,
                "category": tool_def.category,
                "has_handler": self.tool_registry.get_handler(tool_def.name) is not None,
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "required": p.required,
                        "default": p.default,
                        "description": p.description
                    }
                    for p in tool_def.parameters
                ]
            })
        return tools

    async def _extract_search_query(self, message: str) -> str:
        """Extract the actual search query from a complex message that may contain both instructions and search intent.

        This is useful when users paste large custom prompt templates that include AI instructions
        along with the actual search query. We use a fast LLM to extract just the search intent.
        """
        # If the message is short (< 500 chars), it's probably a direct query
        if len(message) < 500:
            return message

        # Check if message looks like a template (has multiple sections, markdown headers, etc.)
        template_indicators = ['##', '###', 'template', 'instruction', 'format', 'section', 'structure']
        has_template_markers = sum(1 for indicator in template_indicators if indicator in message.lower()) >= 2

        if not has_template_markers:
            return message

        # Use a fast LLM to extract search intent
        logger.info(f"Message appears to be a complex template ({len(message)} chars). Extracting search intent...")

        try:
            extraction_prompt = """You are analyzing a user message to extract the core search query.

The user may have pasted a large template with AI instructions, formatting requirements, and other metadata. Your job is to identify the ACTUAL search query - what articles they want to find.

Extract ONLY the search query portion. This should be:
- A concise phrase or sentence describing what articles to search for
- Include any time constraints (e.g., "past 7 days", "last month")
- Include any topic/category constraints
- Remove ALL formatting instructions, template structure, output requirements, and AI instructions

If there is NO clear search query (it's pure instructions), return "general recent articles".

User message:
---
{message}
---

Extracted search query (respond with ONLY the query, no explanation):"""

            response = litellm.completion(
                model="gpt-4.1-mini",  # Fast and cheap model for extraction
                messages=[
                    {"role": "user", "content": extraction_prompt.format(message=message[:3000])}  # Limit to 3000 chars to avoid huge costs
                ],
                temperature=0.0,
                max_tokens=100
            )

            extracted_query = response.choices[0].message.content.strip()
            logger.info(f"Extracted search query: '{extracted_query}'")
            return extracted_query

        except Exception as e:
            logger.error(f"Error extracting search query: {e}. Using original message.")
            return message

    async def _use_mcp_tools(self, message: str, chat_id: int, limit: int, tools_config: Dict = None, citation_limit: Optional[int] = None, sampling_strategy: str = None) -> Optional[str]:
        """Use the original sophisticated database navigation logic from chat_routes.py"""
        logger.info(f"_use_mcp_tools called for message: '{message}', chat_id: {chat_id}, citation_limit: {citation_limit}, sampling_strategy: {sampling_strategy}")

        try:
            # Get chat info to determine topic
            chat = self.db.get_auspex_chat(chat_id)
            if not chat:
                logger.error(f"Chat not found for chat_id: {chat_id}")
                return None

            topic = chat['topic']
            # Handle cross-topic mode: __all__ means search all topics
            is_cross_topic = (topic == '__all__')
            if is_cross_topic:
                logger.info("Chat mode: Cross-topic (searching all topics)")
                topic = None  # Set to None to skip topic filtering
            else:
                logger.info(f"Chat topic: {topic}")

            # Use the original sophisticated search logic with sampling strategy
            return await self._original_chat_database_logic(message, topic, limit, citation_limit, sampling_strategy)

        except Exception as e:
            logger.error(f"Error in _use_mcp_tools: {e}")
            return None

    def _format_tools_status(self, tools_config: Dict = None) -> str:
        """Format tools status for system prompt."""
        if not tools_config:
            return "DISABLED - Provide analysis based on your knowledge and any provided context"
        
        enabled_tools = [tool for tool, enabled in tools_config.items() if enabled]
        if not enabled_tools:
            return "DISABLED - All tools are turned off"
        
        if len(enabled_tools) == len(tools_config):
            return "FULLY ENABLED - You can access all available tools for real-time data and advanced analysis"
        
        return f"PARTIALLY ENABLED - You have access to these tools: {', '.join(enabled_tools)}"

    def _format_active_tools(self, tools_config: Dict = None) -> str:
        """Format active tools list for system prompt."""
        if not tools_config:
            return "None available"
        
        enabled_tools = [tool for tool, enabled in tools_config.items() if enabled]
        if not enabled_tools:
            return "All disabled"
        
        tool_descriptions = {
            'get_topic_articles': 'Topic Articles',
            'semantic_search_and_analyze': 'Semantic Search',
            'search_articles_by_keywords': 'Keyword Search',
            'follow_up_query': 'Follow-up Query',
            'analyze_sentiment_trends': 'Sentiment Analysis',
            'get_article_categories': 'Category Analysis',
            'search_news': 'Real-time News'
        }
        
        active_descriptions = [tool_descriptions.get(tool, tool) for tool in enabled_tools]
        return f"Active: {', '.join(active_descriptions)}"

    async def _original_chat_database_logic(self, message: str, topic: str, limit: int, citation_limit: Optional[int] = None, sampling_strategy: str = None) -> Optional[str]:
        # Initialize topic_options outside try block to ensure it's available in exception handler
        topic_options = {
            'categories': [],
            'sentiments': [],
            'futureSignals': [],
            'timeToImpacts': []
        }

        try:
            analyze_db = AnalyzeDB(self.db)
            ai_model = get_ai_model(DEFAULT_MODEL)

            # Validate inputs (topic can be None for cross-topic search)
            if not message or not limit:
                logger.error(f"Invalid inputs: message='{message}', topic='{topic}', limit={limit}")
                return f"## Search Error\nInvalid search parameters. Please ensure you have entered a message."

            # Get available options for this topic (original logic)
            try:
                topic_options_result = analyze_db.get_topic_options(topic)
                if topic_options_result:
                    topic_options = topic_options_result
            except Exception as e:
                logger.warning(f"Error getting topic options for {topic}: {e}")

            # Log if using default options
            if not topic_options or not any(topic_options.values()):
                logger.warning(f"Using default empty topic options for topic: {topic}")

            # Extract the actual search query from complex messages (e.g., custom prompts)
            search_query = await self._extract_search_query(message)
            logger.info(f"Using search query: '{search_query}' (original message length: {len(message)} chars)")

            # NEW: Use QueryRouter for intelligent data retrieval
            # This handles temporal queries (SQL-based) and cross-topic parallel searches
            query_type = self.query_router.classify_query(search_query)
            is_cross_topic = (topic is None or topic == '__all__')

            # Use QueryRouter for temporal queries OR cross-topic semantic queries
            use_smart_routing = (
                query_type == 'temporal_analysis' or
                (is_cross_topic and query_type in ('semantic_search', 'comprehensive'))
            )

            if use_smart_routing:
                logger.info(f"Using QueryRouter: type={query_type}, cross_topic={is_cross_topic}")
                effective_topic = None if is_cross_topic else topic

                router_result = await self.query_router.route(
                    query=search_query,
                    topic=effective_topic,
                    limit=limit,
                    citation_limit=citation_limit
                )

                vector_articles = router_result.get('articles', [])
                search_method = router_result.get('search_method', 'query_router')
                router_metadata = router_result.get('metadata', {})

                logger.info(f"QueryRouter returned {len(vector_articles)} articles via {search_method}")
                logger.info(f"Router metadata: {router_metadata}")

                # Skip the old vector search logic since QueryRouter handled it
                # Jump to the context optimization and response generation below

            else:
                # Fall back to original vector search logic for single-topic queries
                logger.info(f"Using original vector search logic: type={query_type}, topic={topic}")

            # Enhanced search strategy: Use both SQL and vector search (original logic)
            # First, try vector search for semantic understanding
            # NOTE: This block only runs if use_smart_routing is False
            if not use_smart_routing:
                vector_articles = []
                explicit_days_back = None  # Initialize for use in fallback filtering
                try:
                    # If citation_limit is specified and higher than limit, use it for vector search
                    # This ensures we fetch enough articles to meet the citation requirement
                    search_limit = limit
                    if citation_limit and citation_limit > limit:
                        search_limit = min(citation_limit, 500)  # Cap at 500 to prevent excessive searches
                        logger.info(f"Increasing search limit from {limit} to {search_limit} to meet citation_limit of {citation_limit}")

                    # Build metadata filter for vector search (skip topic filter for cross-topic mode)
                    metadata_filter = {"topic": topic} if topic else {}

                    # EXPLICIT CHECK for common date patterns (safety net)
                    # Use the extracted search query for pattern matching
                    explicit_date_patterns = {
                        "trends from the last 7 days": 7,
                        "trends from the past 7 days": 7,
                        "trends in the last 7 days": 7,
                        "trends over the last 7 days": 7,
                        "trends past 7 days": 7,
                        "last 7 days": 7,
                        "past 7 days": 7,
                        "last week": 7,
                        "past week": 7,
                        "last month": 30,
                        "past month": 30,
                        "last 30 days": 30,
                        "past 30 days": 30,
                    }

                    # Use search_query (not original message) for date pattern detection
                    search_query_lower = search_query.lower()
                    for pattern, days in explicit_date_patterns.items():
                        if pattern in search_query_lower:
                            explicit_days_back = days
                            logger.info(f"EXPLICIT DATE PATTERN MATCH: '{pattern}' -> {days} days")
                            break

                    if explicit_days_back:
                        cutoff_datetime = datetime.now() - timedelta(days=explicit_days_back)
                        # Format as date string to match publication_date column format (YYYY-MM-DD HH:MM:SS)
                        cutoff_date_str = cutoff_datetime.strftime('%Y-%m-%d %H:%M:%S')
                        # Use string comparison with publication_date (text column)
                        # For cross-topic mode (topic=None), only filter by date
                        if topic:
                            metadata_filter = {
                                "$and": [
                                    {"topic": topic},
                                    {"publication_date": {"$gte": cutoff_date_str}}
                                ]
                            }
                        else:
                            metadata_filter = {"publication_date": {"$gte": cutoff_date_str}}
                        logger.info(f"EXPLICIT date filter applied: publication_date >= '{cutoff_date_str}'")
                        logger.info(f"Final metadata_filter: {metadata_filter}")
                    else:
                        # No date filter - use topic filter if available, empty dict for cross-topic
                        metadata_filter = {"topic": topic} if topic else {}

                    # Use extracted search_query (not original message) for vector search
                    vector_results = vector_search_articles(
                        query=search_query,
                        top_k=search_limit,  # Use search_limit which may be increased by citation_limit
                        metadata_filter=metadata_filter
                    )

                    # Convert vector results to article format with comprehensive null checks
                    if vector_results and isinstance(vector_results, list):
                        for result in vector_results:
                            if not result or not isinstance(result, dict):
                                continue

                            metadata = result.get("metadata")
                            if not metadata or not isinstance(metadata, dict):
                                continue

                            # Only add articles with valid URI
                            uri = metadata.get("uri")
                            if not uri:
                                continue

                            vector_articles.append({
                                "uri": uri,
                                "title": metadata.get("title", "Unknown Title"),
                                "url": metadata.get("url") or metadata.get("link") or uri,  # Use uri as fallback
                                "summary": metadata.get("summary", "No summary available"),
                                "category": metadata.get("category", "Uncategorized"),
                                "sentiment": metadata.get("sentiment", "Neutral"),
                                "future_signal": metadata.get("future_signal", "None"),
                                "time_to_impact": metadata.get("time_to_impact", "Unknown"),
                                "publication_date": metadata.get("publication_date", "Unknown"),
                                "news_source": metadata.get("news_source", "Unknown"),
                                "tags": metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                                "similarity_score": result.get("score", 0.0)
                            })

                    logger.debug(f"Vector search found {len(vector_articles)} semantically relevant articles")

                    # NEW: Add entity-specific filtering for queries asking about specific companies/vendors
                    # SKIP entity filtering for system-generated thematic category queries
                    # Use search_query (not original message) for entity detection
                    is_thematic_query = "comprehensive consensus analysis" in search_query.lower() or "comprehensive analysis" in search_query.lower()
                    detected_entities = self._extract_entity_names(search_query) if not is_thematic_query else []
                    if detected_entities:
                        logger.info(f"Detected entity-specific query. Entities: {detected_entities}")
                        vector_articles_before_filter = len(vector_articles)
                        vector_articles = self._filter_articles_by_entity_content(vector_articles, detected_entities)
                        logger.info(f"Entity filtering: {vector_articles_before_filter} -> {len(vector_articles)} articles")

                        # If no articles contain the specific entity, validate with SQL database before giving up
                        if len(vector_articles) == 0:
                            logger.info(f"No articles found in vector search for entities: {detected_entities}")
                            logger.info("Performing comprehensive SQL database validation...")

                            # Perform comprehensive SQL search to validate entity existence
                            sql_articles_found = self._validate_entity_in_sql_database(detected_entities, topic)

                            if sql_articles_found == 0:
                                return f"""## No Articles Found for Specific Entity

I searched both the vector database and SQL database for articles mentioning **{', '.join(detected_entities)}** in the topic "{topic}" but found **0 articles** that actually reference this entity.

**Comprehensive Search Results:**
- **Vector database**: Found {vector_articles_before_filter} articles in "{topic}", 0 mentioning the entity
- **SQL database**: Searched all articles in topic, 0 mentioning the entity
- **Entity search patterns used**: {', '.join(detected_entities)}

**This means:**
- The entity "{', '.join(detected_entities)}" is not mentioned in any articles in our database for this topic
- I performed a comprehensive search across both vector and SQL databases
- The database contains articles about the topic "{topic}" but none specifically reference this entity

**Suggestions:**
- Check the spelling of the entity name (e.g., "J.R.R. Tolkien" vs "Tolkien")
- Try searching for the entity in a different topic
- Ask "What companies/people are mentioned in {topic}?" to see available entities
- Search for broader terms related to this entity's industry or function

I cannot provide analysis about "{', '.join(detected_entities)}" because no articles in the database actually mention this entity."""
                            else:
                                logger.warning(f"SQL database found {sql_articles_found} articles but vector search found none. This suggests a vector/SQL sync issue.")
                                logger.info("Attempting to retrieve articles from SQL database as fallback...")

                                # Try to get the actual articles from SQL database
                                sql_articles = self._get_entity_articles_from_sql(detected_entities, topic, limit)
                                if sql_articles:
                                    logger.info(f"Retrieved {len(sql_articles)} articles from SQL database as fallback")
                                    vector_articles = sql_articles  # Use SQL articles instead of empty vector results
                                else:
                                    logger.warning("SQL database validation found articles but couldn't retrieve them")

                    # Fallback date filtering for articles that might lack timestamp metadata
                    if explicit_days_back and len(vector_articles) > 0:
                        cutoff_date = datetime.now() - timedelta(days=explicit_days_back)
                        original_count = len(vector_articles)

                        # Filter articles by publication_date string (fallback for articles without timestamp)
                        filtered_vector_articles = []
                        for article in vector_articles:
                            article_date_str = article.get('publication_date', '')
                            if article_date_str:
                                try:
                                    if ' ' in article_date_str:
                                        date_part = article_date_str.split(' ')[0]
                                    else:
                                        date_part = article_date_str[:10]

                                    article_date = datetime.strptime(date_part, '%Y-%m-%d')
                                    if article_date >= cutoff_date:
                                        filtered_vector_articles.append(article)
                                    else:
                                        logger.debug(f"Fallback filter: excluded article from {date_part}: {article.get('title', 'Unknown')[:50]}...")
                                except Exception as e:
                                    logger.warning(f"Could not parse date '{article_date_str}' for article {article.get('uri', 'unknown')}: {e}")
                                    filtered_vector_articles.append(article)  # Include on error
                            else:
                                filtered_vector_articles.append(article)  # Include articles without dates

                        if original_count != len(filtered_vector_articles):
                            logger.info(f"Fallback date filtering: {original_count} -> {len(filtered_vector_articles)} articles (past {explicit_days_back} days, cutoff: {cutoff_date.strftime('%Y-%m-%d')})")
                            vector_articles = filtered_vector_articles
                        else:
                            logger.info(f"Fallback date filtering: No articles filtered out (all {original_count} articles are recent)")

                except Exception as e:
                    logger.warning(f"Vector search failed, falling back to SQL search: {e}")
                    vector_articles = []

            # If vector search found good results, use them with optimization
            if len(vector_articles) >= 10:
                # Apply sampling strategy if specified (pre-filter before context optimization)
                articles_for_optimization = vector_articles
                strategy_applied = None
                if sampling_strategy:
                    try:
                        registry = get_registry()
                        pipeline = registry.create_pipeline_from_preset(sampling_strategy)
                        if pipeline:
                            # Create context for sampling
                            sampling_context = SamplingContext(topic=topic)
                            sampling_context.update_stats(vector_articles)
                            # Store similarity scores
                            for article in vector_articles:
                                sim = article.get('similarity_score')
                                if sim is not None:
                                    article_id = str(article.get('id') or article.get('uri', ''))
                                    sampling_context.similarity_scores[article_id] = sim
                            # Apply the pipeline with a generous limit (actual limit applied by context manager)
                            articles_for_optimization = pipeline.execute(vector_articles, limit * 3, sampling_context)
                            strategy_applied = sampling_strategy
                            logger.info(f"Applied sampling strategy '{sampling_strategy}': {len(vector_articles)} -> {len(articles_for_optimization)} articles")
                    except Exception as e:
                        logger.warning(f"Failed to apply sampling strategy '{sampling_strategy}': {e}. Using default selection.")

                # Apply advanced context optimization
                query_type = self.context_manager.determine_query_type(message)
                budget = self.context_manager.allocate_context_budget(query_type)
                logger.info(f"Context budget allocation: {budget}")
                logger.info(f"Articles budget: {budget['articles']} tokens for {len(articles_for_optimization)} articles")

                # Use optimized article selection with user limit
                optimized_articles = self.context_manager.optimize_article_selection(
                    articles_for_optimization, message, budget["articles"], user_limit=limit
                )

                # Cache articles for chart generation (avoid duplicate searches)
                self._last_chat_articles = optimized_articles
                logger.info(f"Cached {len(optimized_articles)} articles for potential chart generation")

                # Format with optimized context
                optimized_context = self.context_manager.format_optimized_context(
                    optimized_articles, message, query_type
                )
                
                total_count = len(vector_articles)
                search_method = "optimized semantic vector search"
                
                # Enhanced search summary with optimization details
                search_summary = f"""## Search Method: Context-Optimized Semantic Search
- **Query**: "{message}"
- **Query Type**: {query_type}
- **Topic Filter**: {topic}
- **Found**: {total_count} semantically relevant articles
- **Optimized to**: {len(optimized_articles)} diverse, compressed articles
- **Token Efficiency**: Context optimized for {query_type} analysis

{optimized_context}

CITATION INSTRUCTIONS: When referencing articles in your analysis, create proper markdown links using the provided URLs. For example:
- Instead of writing "[d2794684]" or similar artifacts
- Use proper format like: "according to [article title](URL)" or "[Source reporting](URL)"
- Each article has a URL field provided - use these for creating clickable links
- Reference articles by their meaningful titles, not their ID codes

ANALYSIS INSTRUCTIONS: Analyze these optimized articles using the EXACT format template provided in your system prompt. The articles have been compressed and selected for maximum relevance and diversity. Count articles by category, sentiment, future signals, and time to impact. Provide specific examples, data points, and strategic insights. Use the structured format with detailed sections, table, and comprehensive conclusion."""
                
                logger.debug(f"Sending {len(optimized_articles)} optimized articles to LLM for analysis")
                return search_summary
            else:
                # Fall back to original SQL-based search logic
                # First, let the LLM determine if this is a search request and what parameters to use
                available_options = f"""Available search options:
1. Categories: {', '.join(topic_options['categories'])}
2. Sentiments: {', '.join(topic_options['sentiments'])}
3. Future Signals: {', '.join(topic_options['futureSignals'])}
4. Time to Impact: {', '.join(topic_options['timeToImpacts'])}
5. Keywords in title, summary, or tags
6. Date ranges (last week/month/year)"""

                search_intent_messages = [
                    {"role": "system", "content": f"""You are an AI assistant that helps search through articles about {topic}.
Your job is to create effective search queries based on user questions.

{available_options}

IMPORTANT: You must follow these exact steps in order:

1. SPECIAL QUERY TYPES:
   a) For trend analysis requests:
      - Do NOT use keywords like "trends" or "patterns"
      - Instead, use ONLY the date_range parameter
      - Return ALL articles within that timeframe
      Example:
      {{
          "queries": [
              {{
                  "description": "Get all articles from the last 90 days for trend analysis",
                  "params": {{
                      "category": null,
                      "keyword": null,
                      "sentiment": null,
                      "future_signal": null,
                      "tags": null,
                      "date_range": "90"
                  }}
              }}
          ]
      }}

Return your search strategy in this format:
{{
    "queries": [
        {{
            "description": "Brief description of what this query searches for",
            "params": {{
                "category": ["Exact category names"] or null,
                "keyword": "main search term OR alternative term OR another term",
                "sentiment": "exact sentiment" or null,
                "future_signal": "exact signal" or null,
                "time_to_impact": "exact impact timing" or null,
                "tags": ["relevant", "search", "terms"],
                "date_range": "7/30/365" or null
            }}
        }}
    ]
}}"""},
                    {"role": "user", "content": message}
                ]

                # Get search parameters from LLM
                try:
                    search_response = ai_model.generate_response(search_intent_messages)
                    logger.debug(f"LLM search response: {search_response}")
                    
                    json_str = self._extract_json_from_response_original(search_response)
                    logger.debug(f"Extracted JSON: {json_str}")
                    search_strategy = json.loads(json_str)
                    logger.debug(f"Search strategy: {json.dumps(search_strategy, indent=2)}")
                    
                    # Add comprehensive null check for search_strategy
                    if not search_strategy or not isinstance(search_strategy, dict) or not search_strategy.get("queries"):
                        logger.warning(f"Invalid search strategy returned for message: {message}")
                        # Fallback to simple keyword search
                        try:
                            articles, total_count = self.db.search_articles(
                                topic=topic,
                                keyword=message,
                                page=1,
                                per_page=limit
                            )
                            search_method = "fallback keyword search"
                        except Exception as fallback_error:
                            logger.error(f"Fallback search also failed: {fallback_error}")
                            articles = []
                            total_count = 0
                            search_method = "error fallback"
                    else:
                        all_articles = []
                        total_count = 0
                        
                        queries = search_strategy.get("queries", [])
                        if not isinstance(queries, list):
                            logger.warning(f"Search strategy queries is not a list: {type(queries)}")
                            queries = []
                        
                        for query in queries:
                            if not query or not isinstance(query, dict):
                                logger.debug(f"Skipping invalid query: {query}")
                                continue
                                
                            params = query.get("params")
                            if not params or not isinstance(params, dict):
                                logger.debug(f"Skipping query with invalid params: {params}")
                                continue
                                
                            logger.debug(f"Executing query: {query.get('description', 'Unknown')}")
                            logger.debug(f"Query params: {json.dumps(params, indent=2)}")
                            
                            try:
                                # Calculate date range if specified
                                pub_date_start = None
                                pub_date_end = None
                                date_range = params.get("date_range")
                                if date_range and str(date_range) != "all":
                                    try:
                                        days = int(date_range)
                                        pub_date_end = datetime.now()
                                        pub_date_start = pub_date_end - timedelta(days=days)
                                        pub_date_end = pub_date_end.strftime('%Y-%m-%d')
                                        pub_date_start = pub_date_start.strftime('%Y-%m-%d')
                                    except (ValueError, TypeError) as date_error:
                                        logger.warning(f"Invalid date range value: {date_range}, error: {date_error}")

                                # Safe parameter extraction with null checks
                                category = params.get("category")
                                if category and not isinstance(category, list):
                                    category = [category] if category else None
                                
                                sentiment = params.get("sentiment")
                                if sentiment:
                                    sentiment = [sentiment] if not isinstance(sentiment, list) else sentiment
                                
                                future_signal = params.get("future_signal")
                                if future_signal:
                                    future_signal = [future_signal] if not isinstance(future_signal, list) else future_signal
                                
                                keyword = params.get("keyword")
                                tags = params.get("tags")
                                if tags and not isinstance(tags, list):
                                    tags = [tags] if tags else None

                                # If we have a category match, use only that
                                if category:
                                    articles_batch, count = self.db.search_articles(
                                        topic=topic,
                                        category=category,
                                        pub_date_start=pub_date_start,
                                        pub_date_end=pub_date_end,
                                        page=1,
                                        per_page=limit
                                    )
                                # Otherwise, use keyword search
                                else:
                                    articles_batch, count = self.db.search_articles(
                                        topic=topic,
                                        keyword=keyword,
                                        sentiment=sentiment,
                                        future_signal=future_signal,
                                        tags=tags,
                                        pub_date_start=pub_date_start,
                                        pub_date_end=pub_date_end,
                                        page=1,
                                        per_page=limit
                                    )
                                
                                logger.debug(f"Query returned {count} articles")
                                if articles_batch and isinstance(articles_batch, list):
                                    all_articles.extend(articles_batch)
                                    total_count += count
                            except Exception as query_error:
                                logger.error(f"Error executing individual query: {query_error}")
                                continue
                        
                        # Remove duplicates based on article URI
                        seen_uris = set()
                        unique_articles = []
                        for article in all_articles:
                            if article and isinstance(article, dict) and article.get('uri') and article['uri'] not in seen_uris:
                                seen_uris.add(article['uri'])
                                unique_articles.append(article)
                        
                        articles = unique_articles[:limit] if unique_articles else []  # Use user's selected limit
                        search_method = "structured keyword search"

                        # Format search criteria for display
                        active_filters = []
                        try:
                            for query in search_strategy.get("queries", []):
                                if not isinstance(query, dict):
                                    continue
                                params = query.get("params", {})
                                if not isinstance(params, dict):
                                    continue
                                if params.get("keyword"):
                                    keyword_text = str(params.get('keyword', ''))
                                    active_filters.append(f"Keywords: {keyword_text.replace('|', ' OR ')}")
                                if params.get("category"):
                                    categories = params.get('category', [])
                                    if isinstance(categories, list):
                                        active_filters.append(f"Categories: {', '.join(categories)}")
                                    else:
                                        active_filters.append(f"Categories: {categories}")
                                if params.get("sentiment"):
                                    active_filters.append(f"Sentiment: {params.get('sentiment')}")
                                if params.get("future_signal"):
                                    active_filters.append(f"Future Signal: {params.get('future_signal')}")
                                if params.get("tags"):
                                    tags = params.get('tags', [])
                                    if isinstance(tags, list):
                                        active_filters.append(f"Tags: {', '.join(tags)}")
                                    else:
                                        active_filters.append(f"Tags: {tags}")
                        except Exception as filter_error:
                            logger.error(f"Error formatting active filters: {filter_error}")
                            active_filters = ["Error formatting search criteria"]

                        search_summary = f"""## Search Method: {search_method.title()}
{chr(10).join(['- ' + f for f in active_filters]) if active_filters else '- No specific filters applied'}
- **Analysis Limit**: {limit} articles

## Results Overview
Found {total_count} total matching articles
Analyzing the {len(articles)} most recent articles
"""
                except Exception as e:
                    logger.error(f"Search error: {str(e)}", exc_info=True)
                    # Fallback to basic search
                    articles, total_count = self.db.search_articles(
                        topic=topic,
                        keyword=message,
                        page=1,
                        per_page=limit
                    )
                    search_method = "basic keyword search (fallback)"
                    search_summary = f"## Basic Search (Fallback)\nKeyword search for: {message}"

            # Check if we have any articles to analyze
            if not articles:
                return f"""## No Articles Found for Query: "{message}"

**Search Summary:**
- **Topic**: {topic}
- **Query**: "{message}"
- **Search Methods Attempted**: Vector search and structured keyword search
- **Results**: 0 articles found

**Possible Reasons:**
1. The query terms may not match any articles in the database for this topic
2. The topic "{topic}" may have limited article coverage
3. The search terms might be too specific

**Suggestions:**
1. Try broader search terms (e.g., "AI developments" instead of "recent AI trends")
2. Use more general keywords related to {topic}
3. Check if there are articles available for this topic by asking "What articles are available?"
4. Try searching for specific aspects like "AI research", "machine learning applications", etc.

I can help you reformulate your search or provide information about what topics and categories are available in the database."""

            # Determine citation limit
            actual_citation_limit = self.get_citation_limit(len(articles), citation_limit)
            logger.info(f"Using citation limit of {actual_citation_limit} for {len(articles)} total articles")

            # Format articles for context (original format) with citation limit
            articles_to_include = articles[:actual_citation_limit]
            remaining_articles_count = len(articles) - actual_citation_limit

            context = "\n\n".join([
                f"Title: {article.get('title', 'No title')}\n"
                f"URL: {article.get('url') or article.get('link') or article.get('uri', 'No URL')}\n"
                f"Summary: {article.get('summary', 'No summary')}\n"
                f"Category: {article.get('category', 'No category')}\n"
                f"Future Signal: {article.get('future_signal', 'No signal')}\n"
                f"Sentiment: {article.get('sentiment', 'No sentiment')}\n"
                f"Time to Impact: {article.get('time_to_impact', 'No impact time')}\n"
                f"Tags: {', '.join(article.get('tags', [])) if article.get('tags') else 'None'}\n"
                f"Publication Date: {article.get('publication_date', 'Unknown')}"
                + (f"\nSimilarity Score: {article.get('similarity_score', 'N/A')}" if 'similarity_score' in article else "")
                for article in articles_to_include if isinstance(article, dict)
            ])

            # Add note about remaining articles if any
            if remaining_articles_count > 0:
                context += f"\n\n... and {remaining_articles_count} more articles available (showing detailed context for {actual_citation_limit} most relevant)"

            # Build the final context with flexible analysis instructions
            final_context = f"""
{search_summary}

Here are the {actual_citation_limit} most relevant articles out of {total_count} total matches (detailed context provided for {actual_citation_limit}):

{context}

User Question: {message}

---

## Analysis Instructions

**Research Context:**
- Total articles found: {total_count}
- Articles with full context: {actual_citation_limit}
- Remaining articles: {remaining_articles_count} (summaries analyzed but not shown in detail)

**Your Task:**
Analyze these articles to answer the user's question. Apply your strategic foresight methodology and research principles.

**Critical Requirements:**

1. **CITE INLINE THROUGHOUT:**
   - Every specific claim, data point, or finding must cite the source article
   - Format: "Turkey deployed relief teams ([Turkey sends aid](https://example.com))"
   - Or: "According to [Article Title](URL), trend continues..."
   - Or: "Investment increased 45% - Source: [VC Report](https://example.com)"

2. **BE SPECIFIC:**
   - Use exact numbers from articles (not "many" or "several")
   - Name companies, countries, organizations, people
   - Quote key statistics and figures
   - Provide concrete examples

3. **ANALYZE, DON'T JUST SUMMARIZE:**
   - Explain why findings matter (implications)
   - Identify patterns across articles
   - Note emerging trends or shifts
   - Assess strategic significance
   - Consider multiple dimensions: categories, sentiments, timing, drivers

4. **SHOW YOUR WORK:**
   - Report distributions when relevant (e.g., "15 of 25 articles are positive sentiment")
   - Note source diversity (e.g., "covering 18 unique sources")
   - Acknowledge gaps or limitations
   - Flag conflicting information if present

5. **ADAPT YOUR FORMAT:**
   - Structure your response to fit the question type
   - Use tables only when they add clarity (optional)
   - Include statistical breakdowns when they're useful (optional)
   - Write naturally - don't force a rigid template

**Available Metadata to Consider:**
- Categories: {', '.join(topic_options.get('categories', [])[:10])}{"..." if len(topic_options.get('categories', [])) > 10 else ""}
- Sentiments: {', '.join(topic_options.get('sentiments', []))}
- Future Signals: {', '.join(topic_options.get('futureSignals', [])[:5])}{"..." if len(topic_options.get('futureSignals', [])) > 5 else ""}
- Time to Impact: {', '.join(topic_options.get('timeToImpacts', []))}

Use these dimensions to identify patterns, but don't force analysis into a rigid template. Focus on what's most relevant to answering the user's question.
"""

            logger.debug(f"Sending {len(articles)} articles to LLM for analysis using {search_method}")
            return final_context

        except Exception as e:
            logger.error(f"Error in original chat database logic: {e}", exc_info=True)
            # Fallback: Try simple search as last resort
            try:
                articles, count = self.db.search_articles(
                    topic=topic,
                    keyword=message,
                    page=1,
                    per_page=limit
                )
                if articles:
                    # Determine citation limit for fallback search
                    fallback_citation_limit = self.get_citation_limit(len(articles), citation_limit)

                    return f"""## Fallback Search Results
Found {count} articles using simple keyword search for "{message}" in topic {topic}.

## Articles Summary
{self._format_articles_summary(articles[:limit], "fallback search", fallback_citation_limit)}

## Analysis Instructions

Analyze these articles to answer the user's question. Remember to:
1. **Cite inline** - Every claim needs a source: [Article Title](URL)
2. **Be specific** - Use exact numbers, names, and data from articles
3. **Focus on implications** - Explain why findings matter, not just what they are
4. **Adapt your format** - Structure your response naturally to fit the question

Apply your strategic foresight methodology and research principles from your system prompt."""
                else:
                    return f"""## No Results Found
No articles found for query "{message}" in topic {topic}. 

Please try:
- Using different keywords
- Checking if the topic has articles in the database
- Using a broader search term

You can ask me for help with alternative search strategies."""
            except Exception as fallback_error:
                logger.error(f"Fallback search also failed: {fallback_error}")
                return f"""## Search Error
I encountered an error while searching for "{message}" in topic {topic}. 

Error details: {str(e)}

Please try rephrasing your question or contact support if the issue persists."""

    def _select_diverse_articles_original(self, articles, limit):
        """Original select_diverse_articles function from chat_routes.py"""
        if len(articles) <= limit:
            return articles
        
        # Sort by similarity score first (best matches first)
        sorted_articles = sorted(articles, key=lambda x: x.get('similarity_score', 1.0))
        
        selected = []
        seen_categories = set()
        seen_sources = set()
        
        # First pass: Select top articles ensuring category diversity
        for article in sorted_articles:
            if len(selected) >= limit:
                break
                
            category = article.get('category', 'Unknown')
            source = article.get('news_source', 'Unknown')
            
            # Prefer articles from new categories and sources
            category_bonus = 0 if category in seen_categories else 1
            source_bonus = 0 if source in seen_sources else 0.5
            
            # Add if we have space and it adds diversity, or if it's a very good match
            if (len(selected) < limit * 0.7 or  # Always fill 70% with top matches
                category_bonus > 0 or source_bonus > 0):
                selected.append(article)
                seen_categories.add(category)
                seen_sources.add(source)
        
        # Fill remaining slots with best remaining articles
        remaining_needed = limit - len(selected)
        if remaining_needed > 0:
            remaining_articles = [a for a in sorted_articles if a not in selected]
            selected.extend(remaining_articles[:remaining_needed])
        
        return selected[:limit]

    def _extract_json_from_response_original(self, response: str) -> str:
        """Original extract_json_from_response function from chat_routes.py"""
        try:
            # Try to find JSON object between curly braces
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                # Clean up double curly braces
                json_str = json_str.replace('{{', '{').replace('}}', '}')
                # Remove any leading/trailing whitespace
                json_str = json_str.strip()
                logger.debug(f"Cleaned JSON string: {json_str}")
                return json_str
            return response
        except Exception as e:
            logger.error(f"Error extracting JSON: {str(e)}")
            return response
            
        except Exception as e:
            logger.error(f"Error in comprehensive data gathering: {e}")
            return None

    def _determine_search_strategy(self, message: str, topic_options: Dict) -> List[Dict]:
        """Determine database search strategy based on message content and available options."""
        strategies = []
        message_lower = message.lower()
        
        # Check for trend analysis
        if any(word in message_lower for word in ["trend", "pattern", "over time", "temporal"]):
            strategies.append({
                "description": "Trend analysis - all recent articles",
                "params": {
                    "category": None,
                    "keyword": None,
                    "sentiment": None,
                    "future_signal": None,
                    "tags": None,
                    "date_range": "90"
                }
            })
        
        # Check for category-specific requests
        for category in topic_options.get('categories', []):
            if category.lower() in message_lower:
                strategies.append({
                    "description": f"Category-specific search: {category}",
                    "params": {
                        "category": [category],
                        "keyword": None,
                        "sentiment": None,
                        "future_signal": None,
                        "tags": None,
                        "date_range": "30"
                    }
                })
                break
        
        # Check for sentiment-specific requests
        for sentiment in topic_options.get('sentiments', []):
            if sentiment.lower() in message_lower:
                strategies.append({
                    "description": f"Sentiment-specific search: {sentiment}",
                    "params": {
                        "category": None,
                        "keyword": None,
                        "sentiment": sentiment,
                        "future_signal": None,
                        "tags": None,
                        "date_range": "30"
                    }
                })
                break
        
        # Check for future signal requests
        for signal in topic_options.get('futureSignals', []):
            if signal.lower() in message_lower:
                strategies.append({
                    "description": f"Future signal search: {signal}",
                    "params": {
                        "category": None,
                        "keyword": None,
                        "sentiment": None,
                        "future_signal": signal,
                        "tags": None,
                        "date_range": "60"
                    }
                })
                break
        
        # Default keyword search if no specific strategy found
        if not strategies:
            strategies.append({
                "description": "General keyword search",
                "params": {
                    "category": None,
                    "keyword": message,
                    "sentiment": None,
                    "future_signal": None,
                    "tags": None,
                    "date_range": "30"
                }
            })
        
        return strategies

    def _select_diverse_articles(self, articles: List[Dict], limit: int) -> List[Dict]:
        """Select diverse articles from a larger pool based on category, source, and relevance."""
        if len(articles) <= limit:
            return articles
        
        # Sort by similarity score first (best matches first)
        sorted_articles = sorted(articles, key=lambda x: x.get('similarity_score', 1.0))
        
        selected = []
        seen_categories = set()
        seen_sources = set()
        
        # First pass: Select top articles ensuring diversity
        for article in sorted_articles:
            if len(selected) >= limit:
                break
                
            category = article.get('category', 'Unknown')
            source = article.get('news_source', 'Unknown')
            
            # Prefer articles from new categories and sources
            category_bonus = 0 if category in seen_categories else 1
            source_bonus = 0 if source in seen_sources else 0.5
            
            # Add if we have space and it adds diversity, or if it's a very good match
            if (len(selected) < limit * 0.7 or  # Always fill 70% with top matches
                category_bonus > 0 or source_bonus > 0):
                selected.append(article)
                seen_categories.add(category)
                seen_sources.add(source)
        
        # Fill remaining slots with best remaining articles
        remaining_needed = limit - len(selected)
        if remaining_needed > 0:
            remaining_articles = [a for a in sorted_articles if a not in selected]
            selected.extend(remaining_articles[:remaining_needed])
        
        return selected[:limit]

    def _format_articles_summary(self, articles: List[Dict], search_type: str, detail_limit: Optional[int] = None) -> str:
        """
        Format articles into a structured summary for the LLM.

        Args:
            articles: List of article dictionaries
            search_type: Type of search performed
            detail_limit: Number of articles to include in detailed context.
                         If None, uses DEFAULT_CITATION_LIMIT.

        Returns:
            Formatted summary string with article statistics and details
        """
        if not articles:
            return f"No articles found via {search_type}"

        # Determine detail limit
        if detail_limit is None:
            detail_limit = DEFAULT_CITATION_LIMIT
            logger.debug(f"No detail_limit specified, using default: {detail_limit}")
        else:
            # Validate range
            detail_limit = max(MIN_CITATION_LIMIT, min(detail_limit, MAX_CITATION_LIMIT))
            logger.info(f"Using citation detail limit: {detail_limit}")

        # Cap at available articles
        detail_limit = min(detail_limit, len(articles))

        # Calculate statistics
        total_articles = len(articles)
        unique_sources = len(set(article.get('news_source', 'Unknown') for article in articles))

        # Date range
        dates = [article.get('publication_date') for article in articles if article.get('publication_date')]
        date_range = f"from {min(dates)} to {max(dates)}" if dates else "unknown date range"

        # Category distribution
        categories = {}
        for article in articles:
            cat = article.get('category', 'Unknown')
            categories[cat] = categories.get(cat, 0) + 1

        # Sentiment distribution
        sentiments = {}
        for article in articles:
            sent = article.get('sentiment', 'Unknown')
            sentiments[sent] = sentiments.get(sent, 0) + 1

        # Format summary
        category_dist = chr(10).join([f"- {cat}: {count} articles ({count/total_articles*100:.1f}%)" for cat, count in categories.items()])
        sentiment_dist = chr(10).join([f"- {sent}: {count} articles ({count/total_articles*100:.1f}%)" for sent, count in sentiments.items()])

        # Format article details with dynamic limit
        article_details = []
        for i, article in enumerate(articles[:detail_limit]):
            similarity_text = f" | Similarity: {article.get('similarity_score', 0):.3f}" if 'similarity_score' in article else ""
            url = article.get('url') or article.get('link') or article.get('uri', 'No URL')
            detail = (f"[{i+1}] {article['title'][:100]}...\n" +
                     f"    URL: {url}\n" +
                     f"    Category: {article.get('category', 'N/A')} | Sentiment: {article.get('sentiment', 'N/A')}" +
                     f" | Future Signal: {article.get('future_signal', 'N/A')}" + similarity_text +
                     f"\n    Summary: {article.get('summary', 'No summary')[:200]}...")
            article_details.append(detail)

        article_details_text = chr(10).join(article_details)

        # Dynamic "more articles" text
        remaining_count = len(articles) - detail_limit
        if remaining_count > 0:
            more_articles_text = f"\n\n... and {remaining_count} more articles available (showing detailed context for {detail_limit} most relevant)"
        else:
            more_articles_text = ""

        summary = f"""Search Method: {search_type}
Total Articles: {total_articles}
Detailed Context Provided: {detail_limit} articles
Unique Sources: {unique_sources}
Date Range: {date_range}

Category Distribution:
{category_dist}

Sentiment Distribution:
{sentiment_dist}

Article Details (First {detail_limit}):
{article_details_text}{more_articles_text}"""

        return summary

    async def _generate_streaming_response(self, messages: List[Dict], model: str) -> AsyncGenerator[str, None]:
        """Generate streaming response from LLM."""
        try:
            # Get model limits
            context_limit = self._get_model_context_limit(model)
            max_output_tokens = self._get_model_output_limit(model)
            
            # Estimate tokens used by input (rough approximation)
            input_text = " ".join([msg.get("content", "") for msg in messages])
            estimated_input_tokens = len(input_text) // 4  # Rough estimate: 4 chars per token
            
            # Calculate max_tokens based on model's actual output limit and available context
            available_context = context_limit - estimated_input_tokens - 1000  # Reserve 1000 for safety
            max_tokens = min(max_output_tokens, available_context)
            
            # Ensure we have at least some tokens for response
            max_tokens = max(500, max_tokens)
            
            logger.info(f"Model: {model}, Context limit: {context_limit}, Max output limit: {max_output_tokens}, Estimated input tokens: {estimated_input_tokens}, Final max_tokens: {max_tokens}")
            
            # Create the streaming response
            response_stream = await litellm.acompletion(
                model=model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=max_tokens
            )
            
            # Handle the async generator properly
            async for chunk in response_stream:
                try:
                    # Check if chunk has the expected structure
                    if (hasattr(chunk, 'choices') and 
                        len(chunk.choices) > 0 and 
                        hasattr(chunk.choices[0], 'delta') and 
                        hasattr(chunk.choices[0].delta, 'content') and
                        chunk.choices[0].delta.content is not None):
                        yield chunk.choices[0].delta.content
                except AttributeError as attr_err:
                    logger.warning(f"Unexpected chunk structure: {attr_err}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error generating streaming response: {e}")
            yield f"Error generating response: {str(e)}"

    async def generate_structured_analysis(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 3000
    ) -> str:
        """Generate structured JSON analysis.

        This method is designed for features that need structured output
        like Market Signals, Trend Convergence, etc.

        Args:
            system_prompt: System prompt defining the AI's role
            user_prompt: User prompt with analysis instructions
            model: LLM model to use
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens in response

        Returns:
            JSON string with analysis results

        Raises:
            HTTPException: If generation fails
        """
        try:
            logger.info(f"Generating structured analysis with model: {model}")

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # Use litellm completion with JSON mode if supported
            try:
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"}  # Force JSON output
                )
            except Exception as e:
                # Fallback without JSON mode if not supported
                logger.warning(f"JSON mode not supported for {model}, falling back to regular completion: {e}")
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )

            # Extract content from response
            if hasattr(response, 'choices') and len(response.choices) > 0:
                content = response.choices[0].message.content

                # Validate it's actually JSON
                try:
                    json.loads(content)  # Test parse
                    logger.info("Successfully generated and validated structured JSON response")
                    return content
                except json.JSONDecodeError as je:
                    logger.error(f"Response is not valid JSON: {je}")
                    logger.error(f"Response content: {content[:500]}...")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"AI returned invalid JSON: {str(je)}"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="No response from AI model"
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating structured analysis: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate analysis: {str(e)}"
            )

    def get_system_prompt(self, prompt_name: str = None) -> Dict:
        """Get system prompt for Auspex."""
        try:
            if prompt_name:
                prompt = self.db.get_auspex_prompt(prompt_name)
            else:
                prompt = self.db.get_default_auspex_prompt()
            
            if not prompt:
                # Return default if none found
                return {
                    "name": "default",
                    "title": "Default Auspex Assistant", 
                    "content": DEFAULT_AUSPEX_PROMPT
                }
            
            return prompt
        except Exception as e:
            logger.error(f"Error getting system prompt: {e}")
            return {
                "name": "default",
                "title": "Default Auspex Assistant",
                "content": DEFAULT_AUSPEX_PROMPT
            }

    def get_all_prompts(self) -> List[Dict]:
        """Get all available Auspex prompts."""
        try:
            return self.db.get_auspex_prompts()
        except Exception as e:
            logger.error(f"Error getting prompts: {e}")
            return []

    def create_prompt(self, name: str, title: str, content: str, description: str = None, user_created: str = None) -> int:
        """Create a new Auspex prompt."""
        try:
            return self.db.create_auspex_prompt(
                name=name,
                title=title,
                content=content,
                description=description,
                user_created=user_created
            )
        except Exception as e:
            logger.error(f"Error creating prompt: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create prompt")

    def update_prompt(self, name: str, title: str = None, content: str = None, description: str = None) -> bool:
        """Update an Auspex prompt."""
        try:
            return self.db.update_auspex_prompt(
                name=name,
                title=title,
                content=content,
                description=description
            )
        except Exception as e:
            logger.error(f"Error updating prompt: {e}")
            return False

    def delete_prompt(self, name: str) -> bool:
        """Delete an Auspex prompt."""
        try:
            return self.db.delete_auspex_prompt(name)
        except Exception as e:
            logger.error(f"Error deleting prompt: {e}")
            return False

    # Keep existing suggest_options method for backward compatibility
    def suggest_options(self, kind: str, scenario_name: str, scenario_description: str = None) -> List[str]:
        """Ask the LLM for a short list of options suitable for the given building-block kind."""
        # Background context for strategic foresight
        BACKGROUND_SNIPPET = (
            "AuNoo follows strategic-foresight methodology.\n"
            "Categories: thematic sub-clusters inside a topic.\n"
            "Future Signals: concise hypotheses about possible future states.\n"
            "Sentiments: Positive / Neutral / Negative plus nuanced variants.\n"
            "Time to Impact: Immediate; Short-Term (3-18m); Mid-Term (18-60m); "
            "Long-Term (5y+).\n"
            "Driver Types: Accelerators, Blockers, Catalysts, Delayers, Initiators, "
            "Terminators."
        )

        # Map block kind to extra context
        KIND_CONTEXT = {
            "categorization": (
                "Focus on concrete thematic clusters relevant to the scenario."
            ),
            "sentiment": (
                "Use Positive / Negative / Neutral or nuanced variants where helpful."
            ),
            "relationship": (
                "Think in terms of blocker, catalyst, accelerator, "
                "initiator or supporting datapoint."
            ),
            "weighting": (
                "Return objective scale descriptors "
                "(e.g., Highly objective, Anecdotal)."
            ),
            "classification": "Propose discrete, mutually exclusive classes.",
            "summarization": "No additional options required.",
            "keywords": "Return succinct single- or two-word tags.",
        }

        prompt_parts = [
            BACKGROUND_SNIPPET,
            KIND_CONTEXT.get(kind.lower(), ""),
            (
                "Generate a concise comma-separated list of options "
                f"for a building-block of type '{kind}'."
            ),
            f"Scenario name: {scenario_name}.",
        ]
        
        if scenario_description:
            prompt_parts.append(f"Scenario description: {scenario_description}.")

        prompt_parts.append(
            "Return ONLY the list in plain text, no numbering, no explanations.",
        )

        prompt = "\n".join(prompt_parts)

        try:
            response = litellm.completion(model=DEFAULT_MODEL, messages=[{"role": "user", "content": prompt}])
            text = response.choices[0].message["content"].strip()
            options = [o.strip() for o in text.replace("\n", ",").split(",") if o.strip()]
            if not options:
                raise ValueError("LLM returned empty list")
            return options[:10]
        except Exception as exc:
            logger.error("Auspex LLM call failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="LLM suggestion failed") from exc

    def _get_model_context_limit(self, model: str) -> int:
        """Get context window size for different models."""
        model_limits = {
            "gpt-3.5-turbo": 16385,
            "gpt-3.5-turbo-16k": 16385,
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-4-turbo": 128000,
            "gpt-4-turbo-preview": 128000,
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "gpt-4.1": 1000000,  # 1M context window
            "gpt-4.1-mini": 1000000,  # 1M context window
            "gpt-4.1-nano": 1000000,  # 1M context window
            "claude-3-opus": 200000,
            "claude-3-sonnet": 200000,
            "claude-3-haiku": 200000,
            "claude-3.5-sonnet": 200000,
            "claude-4": 200000,
            "claude-4-opus": 200000,
            "claude-4-sonnet": 200000,
            "claude-4-haiku": 200000,
            "gemini-pro": 32768,
            "gemini-1.5-pro": 2097152,
            "llama-2-70b": 4096,
            "llama-3-70b": 8192,
            "mixtral-8x7b": 32768
        }
        
        # Handle versioned model names
        base_model = model.split("-")[0:2]  # Get first two parts
        base_model_key = "-".join(base_model)
        
        # Try exact match first, then base model, then default
        return model_limits.get(model, model_limits.get(base_model_key, 16385))
    
    def _get_model_output_limit(self, model: str) -> int:
        """Get maximum output token limit for different models."""
        # Model-specific output token limits (different from context window)
        model_output_limits = {
            "gpt-4": 16384,      # GPT-4 max output tokens
            "gpt-4-32k": 16384,  # GPT-4-32k max output tokens
            "gpt-4-turbo": 16384,
            "gpt-4-turbo-preview": 16384,
            "gpt-4o": 16384,
            "gpt-4o-mini": 16384,
            "gpt-4.1": 32768,    # GPT-4.1 max output tokens
            "gpt-4.1-mini": 32768,
            "gpt-4.1-nano": 32768,
            "gpt-3.5-turbo": 4096,  # GPT-3.5 max output tokens
            "gpt-3.5-turbo-16k": 4096,
            # For other models, use reasonable defaults based on their context size
            "claude-3-opus": 8192,
            "claude-3-sonnet": 8192,
            "claude-3-haiku": 8192,
            "claude-3.5-sonnet": 8192,
            "claude-4": 8192,
            "claude-4-opus": 8192,
            "claude-4-sonnet": 8192,
            "claude-4-haiku": 8192,
            "gemini-pro": 8192,
            "gemini-1.5-pro": 8192,
            "llama-2-70b": 2048,
            "llama-3-70b": 2048,
            "mixtral-8x7b": 8192
        }
        
        # Handle versioned model names
        base_model = model.split("-")[0:2]  # Get first two parts
        base_model_key = "-".join(base_model)
        
        # Try exact match first, then base model, then reasonable default
        return model_output_limits.get(model, model_output_limits.get(base_model_key, 4096))
    
    def _update_context_manager_for_model(self, model: str):
        """Update context manager with correct model limits."""
        limit = self._get_model_context_limit(model)
        
        # Reinitialize context manager with proper model-aware allocations
        self.context_manager = OptimizedContextManager(model_context_limit=limit)
        
        logger.info(f"Updated context manager for model {model} with limit {limit:,} tokens")
        
        # Log the allocations being used
        is_mega = limit >= 500000
        allocation_type = "mega-context" if is_mega else "standard"
        logger.info(f"Using {allocation_type} allocations for {model}")
        
        # Log specific allocation for articles
        sample_allocation = self.context_manager.allocate_context_budget("comprehensive")
        articles_budget = sample_allocation.get("articles", 0)
        logger.info(f"Articles budget for comprehensive analysis: {articles_budget:,} tokens ({articles_budget/limit*100:.1f}% of context)")

# Global service instance
_service_instance = None

def get_auspex_service() -> AuspexService:
    """Get the global Auspex service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = AuspexService()
    return _service_instance 
