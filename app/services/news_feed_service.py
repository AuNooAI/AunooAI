import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import asyncio
import time

from app.schemas.news_feed import (
    DailyOverview, SixArticlesReport, TopStory, NewsArticle, 
    RelatedArticle, ArticleSource, BiasRating, FactualityRating,
    NewsFeedRequest, NewsFeedResponse
)
from app.database import Database
from app.services.auspex_service import get_auspex_service
from app.database_query_facade import DatabaseQueryFacade

logger = logging.getLogger(__name__)


class NewsFeedService:
    """
    Service for generating Techmeme-style daily news feeds using AI analysis.
    Leverages the existing Auspex service for AI content generation.
    """
    
    def __init__(self, db: Database):
        self.db = db
        self.facade = DatabaseQueryFacade(db, logger)
        self.auspex = get_auspex_service()
    
    async def generate_daily_feed(self, request: NewsFeedRequest) -> NewsFeedResponse:
        """Generate both overview and six articles report"""
        start_time = time.time()
        
        # Use today if no date specified
        target_date = request.date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get articles for the day
        articles_data = await self._get_articles_for_date(target_date, request.max_articles, request.topic)
        
        if not articles_data:
            raise ValueError("No articles found for the specified date and criteria")
        
        # Generate article list and six articles report concurrently
        article_list_task = self._generate_article_list(articles_data, target_date, request, page=1, per_page=20)
        six_articles_task = self._generate_six_articles_report_cached(articles_data, target_date, request)
        
        article_list, six_articles = await asyncio.gather(article_list_task, six_articles_task)
        
        processing_time = time.time() - start_time
        
        return NewsFeedResponse(
            overview=article_list,
            six_articles=six_articles,
            processing_time_seconds=processing_time
        )
    
    async def _get_articles_for_date(self, date: datetime, max_articles: int, topic: Optional[str] = None) -> List[Dict]:
        """Get articles for a specific date with bias and factuality data"""
        
        # Ensure we're working with the start of the day (midnight) for the target date
        target_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate date range (24 hours from the target date)
        start_date = target_date
        end_date = target_date + timedelta(days=1)
        
        logger.info(f"Getting articles for date range: {start_date.isoformat()} to {end_date.isoformat()}")
        
        # Build query with bias and factuality fields
        # Use DATE() function to ensure we're matching the exact date regardless of time
        target_date_str = target_date.strftime('%Y-%m-%d')
        query = """
        SELECT 
            uri, title, summary, news_source, publication_date, submission_date,
            category, sentiment, sentiment_explanation, time_to_impact, tags,
            bias, factual_reporting, mbfc_credibility_rating, bias_source, 
            bias_country, press_freedom, media_type, popularity,
            future_signal, driver_type
        FROM articles 
        WHERE DATE(publication_date) = ?
        AND category IS NOT NULL
        AND sentiment IS NOT NULL 
        AND bias IS NOT NULL
        AND factual_reporting IS NOT NULL
        """
        params = [target_date_str]
        
        if topic:
            query += " AND (topic = ? OR title LIKE ? OR summary LIKE ?)"
            topic_pattern = f"%{topic}%"
            params.extend([topic, topic_pattern, topic_pattern])
        
        # Order by quality and recency (all articles have complete metadata)
        query += """ 
        ORDER BY 
            CASE WHEN factual_reporting = 'High' THEN 3
                 WHEN factual_reporting = 'Mostly Factual' THEN 2
                 ELSE 1 END DESC,
            publication_date DESC 
        LIMIT ?
        """
        params.append(max_articles)
        
        try:
            results = self.db.fetch_all(query, params)
            logger.info(f"Found {len(results)} articles for date {date.date()}")
            
            # Convert sqlite3.Row objects to dictionaries
            articles_list = []
            for row in results:
                if hasattr(row, 'keys'):  # Check if it's a Row object
                    article_dict = dict(row)
                    articles_list.append(article_dict)
                else:
                    articles_list.append(row)  # Already a dict
            
            return articles_list
        except Exception as e:
            logger.error(f"Error fetching articles: {e}")
            return []
    
    async def _get_total_articles_count_for_date(self, date: datetime, topic: Optional[str] = None) -> int:
        """Get the total count of articles for a specific date (without limit)"""
        
        # Ensure we're working with the start of the day (midnight) for the target date
        target_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate date range (24 hours from the target date)
        start_date = target_date
        end_date = target_date + timedelta(days=1)
        
        # Build count query with same filtering as _get_articles_for_date
        # Use DATE() function to ensure we're matching the exact date regardless of time
        target_date_str = target_date.strftime('%Y-%m-%d')
        query = """
        SELECT COUNT(*) 
        FROM articles 
        WHERE DATE(publication_date) = ?
        AND category IS NOT NULL
        AND sentiment IS NOT NULL 
        AND bias IS NOT NULL
        AND factual_reporting IS NOT NULL
        """
        params = [target_date_str]
        
        if topic:
            query += " AND (topic = ? OR title LIKE ? OR summary LIKE ?)"
            topic_pattern = f"%{topic}%"
            params.extend([topic, topic_pattern, topic_pattern])
        
        try:
            result = self.db.fetch_one(query, params)
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting total articles count: {e}")
            return 0
    
    async def _generate_article_list(self, articles_data: List[Dict], date: datetime, request: NewsFeedRequest, page: int = 1, per_page: int = 20) -> Dict:
        """Generate paginated article list similar to topic dashboard"""
        
        # Get the actual total count from database (not limited by max_articles)
        total_articles = await self._get_total_articles_count_for_date(date, request.topic)
        
        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_articles = articles_data[start_idx:end_idx]
        
        # Convert articles to the expected format
        article_items = []
        for article in paginated_articles:
            # Convert sqlite3.Row to dict if needed
            if hasattr(article, 'keys'):
                article_dict = dict(article)
            else:
                article_dict = article
                
            article_items.append({
                'uri': article_dict.get('uri', ''),
                'title': article_dict.get('title', 'Untitled'),
                'summary': article_dict.get('summary', 'No summary available'),
                'news_source': article_dict.get('news_source', 'Unknown Source'),
                'publication_date': article_dict.get('publication_date'),
                'category': article_dict.get('category'),
                'sentiment': article_dict.get('sentiment'),
                'sentiment_explanation': article_dict.get('sentiment_explanation'),
                'time_to_impact': article_dict.get('time_to_impact'),
                'driver_type': article_dict.get('driver_type'),
                'tags': article_dict.get('tags', '').split(',') if article_dict.get('tags') else [],
                'url': article_dict.get('url', ''),  # For archive links
                'bias': article_dict.get('bias'),
                'factual_reporting': article_dict.get('factual_reporting'),
                'mbfc_credibility_rating': article_dict.get('mbfc_credibility_rating'),
                'bias_source': article_dict.get('bias_source'),
                'bias_country': article_dict.get('bias_country'),
                'press_freedom': article_dict.get('press_freedom'),
                'media_type': article_dict.get('media_type'),
                'popularity': article_dict.get('popularity'),
                'future_signal': article_dict.get('future_signal')
            })
        
        return {
            'items': article_items,
            'total_items': total_articles,  # Match the field name expected by frontend
            'total_articles': total_articles,  # Keep for backward compatibility
            'page': page,
            'per_page': per_page,
            'total_pages': (total_articles + per_page - 1) // per_page,
            'date': date.isoformat()
        }
    
    async def _generate_six_articles_report(self, articles_data: List[Dict], date: datetime, request: NewsFeedRequest) -> List[Dict]:
        """Generate detailed six articles report using specific analyst prompt"""
        
        # Create AI prompt for six articles analysis
        prompt = self._build_six_articles_analyst_prompt(articles_data, date)
        
        # Use AI service directly (bypass Auspex chat sessions to avoid foreign key issues)
        try:
            import litellm
            
            # Create messages for the AI
            messages = [
                {"role": "system", "content": "You are a news analysis AI that creates detailed news reports. Analyze articles from different perspectives including bias and factuality."},
                {"role": "user", "content": prompt}
            ]
            
            # Get AI response using litellm directly
            response = await litellm.acompletion(
                model=request.model,
                messages=messages,
                temperature=0.7,
                max_tokens=4000
            )
            
            response_text = response.choices[0].message.content
            
            # Parse AI response - now returns array directly
            articles_data_parsed = self._parse_six_articles_response(response_text)
            
            # If parsing failed (empty array), use fallback
            if not articles_data_parsed:
                logger.info("JSON parsing returned empty array, using fallback articles")
                return self._create_fallback_six_articles(articles_data, date)
            
            # Convert to structured data using new format
            articles = []
            for article_data in articles_data_parsed:
                # Create article from new format
                article = self._create_six_article_from_analyst_data(article_data)
                if article:
                    articles.append(article)
            
            # If no valid articles were created, use fallback
            if not articles:
                logger.info("No valid articles created from parsed data, using fallback articles")
                return self._create_fallback_six_articles(articles_data, date)
            
            # Return just the articles array for the new format
            return articles
            
        except Exception as e:
            logger.error(f"Error generating six articles report: {e}")
            # Fallback to simple report
            return self._create_fallback_six_articles(articles_data, date)
    
    async def _generate_six_articles_report_cached(self, articles_data: List[Dict], date: datetime, request: NewsFeedRequest) -> List[Dict]:
        """Generate six articles report with caching and enhanced political analysis"""
        
        # Create cache key based on date, topic, and article count
        cache_key = f"six_articles_{date.strftime('%Y-%m-%d')}_{request.topic or 'all'}_{len(articles_data)}"
        
        # Try to get from cache first (implement simple in-memory cache)
        if hasattr(self, '_six_articles_cache') and cache_key in self._six_articles_cache:
            cache_entry = self._six_articles_cache[cache_key]
            # Check if cache is less than 1 hour old
            if (datetime.now() - cache_entry['timestamp']).seconds < 3600:
                logger.info(f"Using cached six articles for {cache_key}")
                return cache_entry['data']
        
        # Generate new analysis with enhanced political analysis
        six_articles = await self._generate_six_articles_with_political_analysis(articles_data, date, request)
        
        # Cache the result
        if not hasattr(self, '_six_articles_cache'):
            self._six_articles_cache = {}
        
        self._six_articles_cache[cache_key] = {
            'data': six_articles,
            'timestamp': datetime.now()
        }
        
        # Keep cache size reasonable (max 10 entries)
        if len(self._six_articles_cache) > 10:
            # Remove oldest entry
            oldest_key = min(self._six_articles_cache.keys(), 
                           key=lambda k: self._six_articles_cache[k]['timestamp'])
            del self._six_articles_cache[oldest_key]
        
        return six_articles
    
    async def _generate_six_articles_with_political_analysis(self, articles_data: List[Dict], date: datetime, request: NewsFeedRequest) -> List[Dict]:
        """Generate six articles with enhanced political analysis based on related articles"""
        
        # Group articles by news source and bias to find related articles with political leanings
        articles_by_source = {}
        articles_with_bias = []
        
        for article in articles_data:
            source = article.get('news_source', 'Unknown')
            bias = article.get('bias')
            
            if source not in articles_by_source:
                articles_by_source[source] = []
            articles_by_source[source].append(article)
            
            if bias and bias.lower() in ['left', 'left-center', 'right', 'right-center', 'mixed']:
                articles_with_bias.append(article)
        
        # Enhanced prompt that considers related articles and political leanings
        prompt = self._build_enhanced_six_articles_analyst_prompt(articles_data, articles_with_bias, articles_by_source, date)
        
        try:
            # Generate AI analysis
            response = await litellm.acompletion(
                model=request.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=3000
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"AI response for enhanced six articles: {content[:200]}...")
            
            # Parse response
            articles = self._parse_six_articles_response(content)
            
            # If parsing failed (empty array), use fallback
            if not articles:
                logger.info("JSON parsing returned empty array in cached version, using fallback articles")
                return self._create_fallback_six_articles(articles_data, date)
            
            # Convert to the expected format
            result_articles = []
            for article_data in articles:
                article = self._create_six_article_from_analyst_data(article_data)
                if article:
                    result_articles.append(article)
            
            # If no valid articles were created, use fallback
            if not result_articles:
                logger.info("No valid articles created from parsed data in cached version, using fallback articles")
                return self._create_fallback_six_articles(articles_data, date)
            
            return result_articles
            
        except Exception as e:
            logger.error(f"Error generating enhanced six articles report: {e}")
            # Fallback to original method
            return await self._generate_six_articles_report(articles_data, date, request)
    
    def _build_overview_prompt(self, articles_data: List[Dict], date: datetime) -> str:
        """Build AI prompt for daily overview generation"""
        
        # Prepare article summaries for AI
        articles_summary = self._prepare_articles_for_prompt(articles_data, max_articles=20)
        
        return f"""
Create a Techmeme-style daily news overview for {date.strftime('%B %d, %Y')}.

ARTICLES DATA:
{articles_summary}

REQUIREMENTS:
- Generate 3-5 top stories in Techmeme style (concise, impactful headlines)
- Each story should have a compelling headline and 2-3 sentence summary
- Focus on the most significant, interesting, or trending stories
- Include brief topic descriptions that explain why each story matters
- Maintain journalistic objectivity while highlighting key insights

OUTPUT FORMAT (JSON):
{{
    "title": "Daily News Overview - {date.strftime('%B %d, %Y')}",
    "top_stories": [
        {{
            "headline": "Compelling headline that captures the essence",
            "summary": "2-3 sentence summary of the key points and implications",
            "primary_article_uri": "URI of the main article",
            "topic_description": "Why this story matters and its broader context",
            "related_article_uris": ["URI1", "URI2"]
        }}
    ]
}}

Focus on stories with:
- High impact or significance
- Broad interest or unique insights  
- Clear relevance to current events
- Good source credibility

Return ONLY the JSON response."""
    
    def _build_six_articles_analyst_prompt(self, articles_data: List[Dict], date: datetime) -> str:
        """Build AI prompt for six articles detailed analysis"""
        
        # Prepare all articles for comprehensive analysis
        articles_summary = self._prepare_articles_for_prompt(articles_data, max_articles=50)
        
        return f"""You are an analyst selecting the 6 most important articles published in the last 24 hours for a general organization that is interested in Artificial Intelligence (AI) and its strategic, technical, and societal impacts.

## Audience Profile (Defaults)
- Risk Appetite: Moderate (balanced between innovation and caution)
- Strategic Interests: AI regulation, enterprise adoption, model scaling limits, market shifts, workforce impact, security & safety
- Sector: General (public + private sector relevance)
- Political/Cultural Orientation: Centrist (consider diverse viewpoints)

## Instructions
From the provided article corpus (news reports, press releases, blogs, filings, research), select the **6 most important articles** for this organization based on:
- Strategic relevance (impact on policy, markets, regulation, technology, workforce, security)
- Novelty (new information, shifts, or evidence)
- Credibility (reliable sources, verifiable data)
- Representativeness (captures major debates or trends)

## Article Corpus
{articles_summary}

For each of the 6 articles, output the following fields:

### 1. Title & Source
**Title** (Source, Date, Author)

### 2. Summary
2–3 sentences covering the core facts, developments, or claims.

### 3. Why It's Interesting / Matters
Explain why this matters strategically, operationally, or competitively for the organization (1–2 sentences).

### 4. Devil's Advocate
One paragraph outlining why this might be overhyped, flawed, misinterpreted, or low-impact (contrarian take).

### 5. Political & Ideological Perspectives
- **Left-leaning framing** — how progressive / left media or experts are likely to frame this
- **Centrist framing** — how mainstream / establishment outlets might frame it
- **Right-leaning framing** — how conservative / market-oriented outlets might frame it

---

## Output Format
Return as a JSON array with 6 objects like this:

[
  {{
    "title": "",
    "source": "",
    "date": "",
    "summary": "",
    "why_interesting": "",
    "devils_advocate": "",
    "perspectives": {{
      "left": "",
      "center": "",
      "right": ""
    }}
  }}
]

## Notes
- Be concise but analytical (each field < 100 words).
- Prefer primary reporting and expert commentary over speculation or marketing.
- Avoid redundant articles (each should cover a different angle or domain of AI developments).
- Ensure all JSON strings are properly escaped (use \\" for quotes inside strings).
- Do not include any text before or after the JSON array.
- The response must be valid JSON that can be parsed directly.

Return ONLY the JSON array with no additional text, explanations, or markdown formatting."""

    def _build_enhanced_six_articles_analyst_prompt(self, articles_data: List[Dict], articles_with_bias: List[Dict], articles_by_source: Dict, date: datetime) -> str:
        """Build enhanced AI prompt that considers related articles and political leanings"""
        
        # Prepare all articles for analysis
        articles_summary = self._prepare_articles_for_prompt(articles_data, max_articles=50)
        
        # Prepare bias analysis context
        bias_context = ""
        if articles_with_bias:
            bias_breakdown = {}
            for article in articles_with_bias:
                bias = article.get('bias', 'Unknown')
                if bias not in bias_breakdown:
                    bias_breakdown[bias] = []
                bias_breakdown[bias].append(f"- {article.get('title', 'Untitled')} ({article.get('news_source', 'Unknown')})")
            
            bias_context = "\n## Political Bias Context Available\n"
            for bias, articles_list in bias_breakdown.items():
                bias_context += f"\n**{bias} Sources:**\n" + "\n".join(articles_list[:3]) + "\n"
        
        # Prepare source grouping context
        source_context = ""
        if len(articles_by_source) > 1:
            source_context = "\n## Source Distribution\n"
            for source, source_articles in articles_by_source.items():
                if len(source_articles) > 1:
                    source_context += f"- {source}: {len(source_articles)} articles\n"
        
        return f"""You are an analyst selecting the 6 most important articles published in the last 24 hours for a general organization that is interested in Artificial Intelligence (AI) and its strategic, technical, and societal impacts.

## Enhanced Analysis Instructions

**CRITICAL: Use the actual political bias data provided below to inform your political perspective analysis. Do not assume political leanings - only analyze perspectives where you have actual bias information from the source data.**

{bias_context}

{source_context}

## Audience Profile (Defaults)
- Risk Appetite: Moderate (balanced between innovation and caution)
- Strategic Interests: AI regulation, enterprise adoption, model scaling limits, market shifts, workforce impact, security & safety
- Sector: General (public + private sector relevance)
- Political/Cultural Orientation: Centrist (consider diverse viewpoints)

## Instructions
From the provided article corpus, select the **6 most important articles** based on:
- Strategic relevance (impact on policy, markets, regulation, technology, workforce, security)
- Novelty (new information, shifts, or evidence)
- Credibility (reliable sources, verifiable data)
- Representativeness (captures major debates or trends)
- **Availability of diverse political perspectives** (prioritize topics where you have articles from different bias sources)

## Article Corpus
{articles_summary}

For each of the 6 articles, output the following fields:

### 1. Title & Source
**Title** (Source, Date, Author)

### 2. Summary
2–3 sentences covering the core facts, developments, or claims.

### 3. Why It's Interesting / Matters
Explain why this matters strategically, operationally, or competitively for the organization (1–2 sentences).

### 4. Devil's Advocate
One paragraph outlining why this might be overhyped, flawed, misinterpreted, or low-impact (contrarian take).

### 5. Political & Ideological Perspectives
**IMPORTANT**: Only provide perspective analysis where you have actual source bias data. If no bias information is available for related articles, state "Insufficient bias data for perspective analysis" instead of making assumptions.

- **Left-leaning framing** — Based on actual left/left-center sources in the corpus
- **Centrist framing** — Based on actual least biased/mixed sources in the corpus  
- **Right-leaning framing** — Based on actual right/right-center sources in the corpus

---

## Output Format
Return as a JSON array with 6 objects like this:

[
  {{
    "title": "",
    "source": "",
    "date": "",
    "summary": "",
    "why_interesting": "",
    "devils_advocate": "",
    "perspectives": {{
      "left": "",
      "center": "",
      "right": ""
    }}
  }}
]

## Notes
- Be concise but analytical (each field < 100 words).
- **Ground political analysis in actual source bias data - do not speculate**.
- Prefer primary reporting and expert commentary over speculation or marketing.
- Avoid redundant articles (each should cover a different angle or domain of AI developments).
- When possible, select articles that have related coverage from sources with different political leanings.

Return ONLY the JSON array."""

    def _prepare_articles_for_prompt(self, articles_data: List[Dict], max_articles: int = 50) -> str:
        """Prepare articles data for AI prompt"""
        
        articles_text = []
        for i, article in enumerate(articles_data[:max_articles]):
            bias_info = f"Bias: {article.get('bias', 'Unknown')}" if article.get('bias') else ""
            factuality_info = f"Factuality: {article.get('factual_reporting', 'Unknown')}" if article.get('factual_reporting') else ""
            
            article_text = f"""
Article {i+1}:
URI: {article.get('uri', '')}
Title: {article.get('title', '')}
Source: {article.get('news_source', '')} {bias_info} {factuality_info}
Published: {article.get('publication_date', '')}
Category: {article.get('category', '')}
Summary: {article.get('summary', '')[:300]}...
Sentiment: {article.get('sentiment', '')}
Time to Impact: {article.get('time_to_impact', '')}
Tags: {article.get('tags', '')}
"""
            articles_text.append(article_text.strip())
        
        return "\n\n".join(articles_text)
    
    def _parse_overview_response(self, response_text: str) -> Dict[str, Any]:
        """Parse AI response for overview"""
        try:
            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing overview JSON: {e}")
        
        # Fallback structure
        return {
            "title": f"Daily News Overview",
            "top_stories": []
        }
    
    def _parse_six_articles_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse AI response for six articles report with robust error handling"""
        try:
            # Clean the response text
            response_text = response_text.strip()
            
            # Try multiple parsing strategies
            
            # Strategy 1: Look for JSON array in code blocks
            import re
            json_match = re.search(r'```json\s*(\[.*?\])\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass
            
            # Strategy 2: Look for plain JSON array
            json_match = re.search(r'(\[.*?\])', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass
            
            # Strategy 3: Extract JSON array from response (original method)
            json_start = response_text.find('[')
            json_end = response_text.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                # Clean common JSON issues
                json_str = json_str.replace('\n', ' ').replace('\t', ' ')
                # Remove trailing commas before closing brackets/braces
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                return json.loads(json_str)
                
        except Exception as e:
            logger.warning(f"Error parsing six articles JSON, using fallback: {e}")
            logger.debug(f"Response text (first 500 chars): {response_text[:500]}")
        
        # Fallback structure - return empty array
        logger.info("Using empty array fallback for six articles parsing")
        return []
    
    def _create_six_article_from_analyst_data(self, article_data: Dict[str, Any]) -> Optional[Dict]:
        """Create article object from new analyst format"""
        try:
            return {
                'title': article_data.get('title', 'Untitled'),
                'source': article_data.get('source', 'Unknown Source'),
                'date': article_data.get('date', ''),
                'summary': article_data.get('summary', ''),
                'why_interesting': article_data.get('why_interesting', ''),
                'devils_advocate': article_data.get('devils_advocate', ''),
                'perspectives': {
                    'left': article_data.get('perspectives', {}).get('left', ''),
                    'center': article_data.get('perspectives', {}).get('center', ''),
                    'right': article_data.get('perspectives', {}).get('right', '')
                }
            }
        except Exception as e:
            logger.error(f"Error creating article from analyst data: {e}")
            return None
    
    async def _create_top_story(self, story_data: Dict[str, Any], articles_data: List[Dict]) -> Optional[TopStory]:
        """Create TopStory object from AI-generated data and article database"""
        
        primary_uri = story_data.get('primary_article_uri', '')
        if not primary_uri:
            return None
        
        # Find primary article in data
        primary_article_data = None
        for article in articles_data:
            if article.get('uri') == primary_uri:
                primary_article_data = article
                break
        
        if not primary_article_data:
            logger.warning(f"Primary article not found: {primary_uri}")
            return None
        
        # Create primary article object
        primary_article = self._create_news_article(primary_article_data)
        
        # Find related articles
        related_articles = []
        related_uris = story_data.get('related_article_uris', [])
        for uri in related_uris:
            for article in articles_data:
                if article.get('uri') == uri:
                    related_article = RelatedArticle(
                        title=article.get('title', ''),
                        source=article.get('news_source', ''),
                        url=article.get('uri'),
                        bias=self._map_bias(article.get('bias')),
                        summary=article.get('summary', '')[:200] + "..." if len(article.get('summary', '')) > 200 else article.get('summary', '')
                    )
                    related_articles.append(related_article)
                    break
        
        # Extract bias analysis from story data
        bias_analysis = story_data.get('bias_analysis', {})
        perspective_breakdown = story_data.get('perspective_breakdown', {})
        
        return TopStory(
            headline=story_data.get('headline', ''),
            summary=story_data.get('summary', ''),
            primary_article=primary_article,
            related_articles=related_articles,
            topic_description=story_data.get('topic_description', ''),
            bias_analysis=bias_analysis,
            factuality_assessment=bias_analysis.get('factuality_assessment', ''),
            perspective_breakdown=perspective_breakdown
        )
    
    def _create_news_article(self, article_data: Dict) -> NewsArticle:
        """Create NewsArticle object from database data"""
        
        source = ArticleSource(
            name=article_data.get('news_source', ''),
            bias=self._map_bias(article_data.get('bias')),
            factuality=self._map_factuality(article_data.get('factual_reporting')),
            credibility_rating=article_data.get('mbfc_credibility_rating'),
            country=article_data.get('bias_country')
        )
        
        # Parse publication date
        pub_date = None
        if article_data.get('publication_date'):
            try:
                pub_date = datetime.fromisoformat(article_data['publication_date'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        
        # Parse tags
        tags = []
        if article_data.get('tags'):
            tags = [tag.strip() for tag in article_data['tags'].split(',') if tag.strip()]
        
        return NewsArticle(
            uri=article_data.get('uri', ''),
            title=article_data.get('title', ''),
            summary=article_data.get('summary', ''),
            url=article_data.get('uri'),
            publication_date=pub_date,
            source=source,
            sentiment=article_data.get('sentiment'),
            category=article_data.get('category'),
            time_to_impact=article_data.get('time_to_impact'),
            tags=tags
        )
    
    def _map_bias(self, bias_str: Optional[str]) -> Optional[BiasRating]:
        """Map bias string to BiasRating enum"""
        if not bias_str:
            return None
        
        bias_mapping = {
            'left': BiasRating.LEFT,
            'left-center': BiasRating.LEFT_CENTER,
            'center': BiasRating.CENTER,
            'right-center': BiasRating.RIGHT_CENTER,
            'right': BiasRating.RIGHT,
            'mixed': BiasRating.MIXED
        }
        
        return bias_mapping.get(bias_str.lower())
    
    def _map_factuality(self, factuality_str: Optional[str]) -> Optional[FactualityRating]:
        """Map factuality string to FactualityRating enum"""
        if not factuality_str:
            return None
        
        factuality_mapping = {
            'very high': FactualityRating.VERY_HIGH,
            'high': FactualityRating.HIGH,
            'mostly factual': FactualityRating.MOSTLY_FACTUAL,
            'mixed': FactualityRating.MIXED,
            'low': FactualityRating.LOW,
            'very low': FactualityRating.VERY_LOW
        }
        
        return factuality_mapping.get(factuality_str.lower())
    
    def _calculate_bias_distribution(self, articles_data: List[Dict]) -> Dict[str, int]:
        """Calculate bias distribution from articles"""
        bias_counts = {}
        for article in articles_data:
            bias = article.get('bias') or 'unknown'  # Handle None values
            bias_counts[bias] = bias_counts.get(bias, 0) + 1
        return bias_counts
    
    def _calculate_factuality_distribution(self, articles_data: List[Dict]) -> Dict[str, int]:
        """Calculate factuality distribution from articles"""
        factuality_counts = {}
        for article in articles_data:
            factuality = article.get('factual_reporting') or 'unknown'  # Handle None values
            factuality_counts[factuality] = factuality_counts.get(factuality, 0) + 1
        return factuality_counts


    def _create_fallback_overview(self, articles_data: List[Dict], date: datetime) -> DailyOverview:
        """Create a simple fallback overview when AI generation fails"""
        
        # Create simple top stories from the most recent articles
        top_stories = []
        for i, article in enumerate(articles_data[:5]):  # Take top 5 articles
            try:
                # Create basic story structure
                primary_article = NewsArticle(
                    uri=article.get('uri', ''),
                    title=article.get('title', 'Unknown Title'),
                    summary=article.get('summary', 'No summary available'),
                    url=article.get('uri', ''),
                    publication_date=datetime.fromisoformat(article.get('publication_date', datetime.now().isoformat())),
                    source=ArticleSource(
                        name=article.get('news_source', 'Unknown Source'),
                        bias=self._map_bias(article.get('bias')),
                        factuality=self._map_factuality(article.get('factual_reporting'))
                    ),
                    sentiment=article.get('sentiment'),
                    category=article.get('category'),
                    time_to_impact=article.get('time_to_impact')
                )
                
                top_story = TopStory(
                    headline=article.get('title', 'Unknown Title'),
                    summary=article.get('summary', 'No summary available')[:200] + "..." if len(article.get('summary', '')) > 200 else article.get('summary', ''),
                    primary_article=primary_article,
                    related_articles=[],
                    topic_description=f"Story #{i+1} from {article.get('news_source', 'Unknown Source')}",
                    factuality_assessment=f"Factuality: {article.get('factual_reporting', 'Unknown')}"
                )
                
                top_stories.append(top_story)
                
            except Exception as e:
                logger.warning(f"Error creating fallback story for article {i}: {e}")
                continue
        
        return DailyOverview(
            title=f"Daily News Overview - {date.strftime('%B %d, %Y')}",
            date=date,
            generated_at=datetime.now(),
            top_stories=top_stories,
            total_articles_analyzed=len(articles_data),
            summary="Fallback overview generated due to AI processing error."
        )
    
    def _create_fallback_six_articles(self, articles_data: List[Dict], date: datetime) -> List[Dict]:
        """Create a simple fallback six articles report when AI generation fails"""
        
        # Create simple articles in the new format
        articles = []
        for i, article_data in enumerate(articles_data[:6]):  # Take top 6 articles
            try:
                article = {
                    'title': article_data.get('title', 'Unknown Title'),
                    'source': article_data.get('news_source', 'Unknown Source'),
                    'date': article_data.get('publication_date', ''),
                    'summary': article_data.get('summary', 'No summary available'),
                    'why_interesting': f"Article #{i+1} - Selected from available articles for analysis",
                    'devils_advocate': "This article may not represent the most strategic information available",
                    'perspectives': {
                        'left': 'Analysis not available in fallback mode',
                        'center': 'Analysis not available in fallback mode', 
                        'right': 'Analysis not available in fallback mode'
                    }
                }
                
                articles.append(article)
                
            except Exception as e:
                logger.warning(f"Error creating fallback article {i}: {e}")
                continue
        
        return articles


# Singleton instance
_news_feed_service = None

def get_news_feed_service(db: Database) -> NewsFeedService:
    """Get or create news feed service instance"""
    global _news_feed_service
    if _news_feed_service is None:
        _news_feed_service = NewsFeedService(db)
    return _news_feed_service
