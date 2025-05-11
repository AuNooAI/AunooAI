"""Newsletter compilation service module."""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.database import Database
from app.ai_models import get_ai_model
from app.schemas.newsletter import NewsletterRequest
from app.services.chart_service import ChartService

logger = logging.getLogger(__name__)


class NewsletterService:
    """Service for generating newsletter content."""

    def __init__(self, db: Database):
        self.db = db
        self.chart_service = ChartService()

    async def compile_newsletter(self, request: NewsletterRequest) -> str:
        """
        Compile newsletter content based on the provided request.
        
        Args:
            request: The newsletter compilation request with parameters
            
        Returns:
            str: Compiled markdown content
        """
        logger.info(f"Received newsletter compilation request: {request.model_dump_json(indent=2)}")
        
        try:
            # Calculate effective date range if not provided
            start_date, end_date = self._calculate_date_range(
                request.frequency, 
                request.start_date, 
                request.end_date
            )
            logger.info(f"Calculated date range: {start_date} to {end_date}")
            
            # Initialize the markdown content
            markdown_content = self._create_header(request.frequency, request.topics, start_date, end_date)
            
            # Process each topic and content type
            for topic in request.topics:
                logger.info(f"Processing topic: {topic}")
                topic_content = f"## {topic}\n\n"
                
                for content_type in request.content_types:
                    logger.info(f"Generating content for topic '{topic}', type: '{content_type}'")
                    try:
                        section_content = await self._generate_content_section(
                            topic, 
                            content_type, 
                            start_date, 
                            end_date
                        )
                        if section_content:
                            logger.info(f"Successfully generated content for '{topic}' - '{content_type}'")
                            topic_content += f"### {self._get_content_type_display_name(content_type)}\n\n"
                            topic_content += f"{section_content}\n\n"
                        else:
                            logger.warning(f"No content generated or returned for '{topic}' - '{content_type}'")
                    except Exception as e_section:
                        logger.error(f"Error generating section '{content_type}' for topic '{topic}': {str(e_section)}", exc_info=True)
                        topic_content += f"### {self._get_content_type_display_name(content_type)}\n\n"
                        topic_content += f"_Error generating this section._\n\n"
                
                markdown_content += topic_content
            
            logger.info(f"Newsletter compilation completed for request: {request.frequency}, topics: {request.topics}")
            # logger.debug(f"Final Markdown (first 500 chars):\n{markdown_content[:500]}") # Optional: log snippet of content
            return markdown_content

        except Exception as e_compile:
            logger.error(f"Fatal error during newsletter compilation: {str(e_compile)}", exc_info=True)
            # Reraise the exception so FastAPI can handle it and return a 500, or return a generic error message string
            # For now, let it propagate to ensure the 500 error is still triggered if not caught by FastAPI's error handling
            raise

    def _calculate_date_range(
        self, 
        frequency: str, 
        start_date: Optional[datetime.date] = None, 
        end_date: Optional[datetime.date] = None
    ) -> tuple:
        """
        Calculate the effective date range based on frequency.
        
        Args:
            frequency: daily, weekly, or monthly
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            tuple: (start_date, end_date)
        """
        today = datetime.now().date()
        
        if start_date and end_date:
            return start_date, end_date
        
        if frequency == "daily":
            # Default is last 24 hours
            return today - timedelta(days=1), today
        elif frequency == "weekly":
            # Default is last 7 days
            return today - timedelta(days=7), today
        elif frequency == "monthly":
            # Default is last 30 days
            return today - timedelta(days=30), today
        else:
            # Default to last 7 days for unknown frequencies
            return today - timedelta(days=7), today

    def _create_header(
        self, 
        frequency: str, 
        topics: List[str], 
        start_date: datetime.date, 
        end_date: datetime.date
    ) -> str:
        """
        Create the newsletter header with title and date range.
        
        Args:
            frequency: Newsletter frequency
            topics: List of included topics
            start_date: Start date
            end_date: End date
            
        Returns:
            str: Markdown header content
        """
        topic_str = ", ".join(topics)
        date_format = "%Y-%m-%d"
        date_range = f"{start_date.strftime(date_format)} to {end_date.strftime(date_format)}"
        
        header = f"# {frequency.capitalize()} Newsletter: {topic_str}\n\n"
        header += f"**Period**: {date_range}\n\n"
        header += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        header += "---\n\n"
        
        return header

    async def _generate_content_section(
        self, 
        topic: str, 
        content_type: str, 
        start_date: datetime.date, 
        end_date: datetime.date
    ) -> Optional[str]:
        """
        Generate content for a specific section based on type.
        
        Args:
            topic: Topic name
            content_type: Type of content to generate
            start_date: Start date for content
            end_date: End date for content
            
        Returns:
            Optional[str]: Markdown content for the section or None if no content
        """
        if content_type == "topic_summary":
            return await self._generate_topic_summary(topic, start_date, end_date)
        elif content_type == "key_charts":
            return await self._generate_key_charts(topic, start_date, end_date)
        elif content_type == "trend_analysis":
            return await self._generate_trend_analysis(topic, start_date, end_date)
        elif content_type == "article_insights":
            return await self._generate_article_insights(topic, start_date, end_date)
        elif content_type == "key_articles":
            return await self._generate_key_articles_list(topic, start_date, end_date)
        elif content_type == "latest_podcast":
            return await self._generate_latest_podcast(topic)
        elif content_type == "ethical_societal_impact":
            return await self._generate_ethical_societal_impact_section(topic, start_date, end_date)
        elif content_type == "business_impact":
            return await self._generate_business_impact_section(topic, start_date, end_date)
        elif content_type == "market_impact":
            return await self._generate_market_impact_section(topic, start_date, end_date)
        else:
            logger.warning(f"Unknown content type: {content_type}")
            return None

    async def _generate_topic_summary(
        self, 
        topic: str, 
        start_date: datetime.date, 
        end_date: datetime.date
    ) -> str:
        """
        Generate a summary of a topic based on recent articles.
        
        Args:
            topic: Topic to summarize
            start_date: Start date for articles
            end_date: End date for articles
            
        Returns:
            str: Markdown summary content
        """
        # Fetch articles for the topic within date range
        articles = self._fetch_articles(topic, start_date, end_date)
        
        if not articles:
            return "No articles found for this period."
        
        # Prepare articles data for the LLM
        article_data = self._prepare_articles_data(articles)
        
        # Generate summary using AI model
        ai_model = get_ai_model(model_name="gpt-3.5-turbo")
        prompt = self._create_summary_prompt(topic, article_data)
        
        try:
            response = await ai_model.generate(prompt)
            # Extract content from response object
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                return response.message.content
            elif hasattr(response, 'content'):
                return response.content
            else:
                return str(response)
        except Exception as e:
            logger.error(f"Error generating topic summary for '{topic}': {str(e)}", exc_info=True)
            return "Error generating topic summary."

    async def _generate_key_charts(
        self, 
        topic: str, 
        start_date: datetime.date, 
        end_date: datetime.date
    ) -> str:
        """
        Generate key charts section with actual chart images.
        """
        # Fetch articles for the topic within date range
        articles = self._fetch_articles(topic, start_date, end_date)
        
        if not articles:
            return "No articles found for chart generation in this period."
            
        # Generate charts
        volume_chart = self.chart_service.generate_volume_chart(
            articles, start_date, end_date
        )
        sentiment_chart = self.chart_service.generate_sentiment_chart(articles)
        radar_chart = self.chart_service.generate_radar_chart(articles)
        
        # Combine charts into markdown
        result = "### Key Charts\n\n"
        result += "#### Volume Over Time\n"
        result += (
            f"![Volume Chart]({volume_chart})\n\n"
        )
        result += "#### Sentiment Distribution\n"
        result += (
            f"![Sentiment Chart]({sentiment_chart})\n\n"
        )
        result += "#### Signal Analysis\n"
        result += (
            f"![Radar Chart]({radar_chart})\n\n"
        )
        
        return result

    async def _generate_trend_analysis(
        self, 
        topic: str, 
        start_date: datetime.date, 
        end_date: datetime.date
    ) -> str:
        """
        Generate trend analysis based on article metadata, now with article citations.
        
        Args:
            topic: Topic to analyze
            start_date: Start date for articles
            end_date: End date for articles
            
        Returns:
            str: Markdown trend analysis
        """
        # Fetch articles for the topic within date range - limit for metadata and prompt
        articles = self._fetch_articles(topic, start_date, end_date, limit=50) # Fetch up to 50 for metadata
        
        if not articles:
            return "No articles found for trend analysis in this period."
            
        # Extract trend data (sentiment, categories, future signals, etc.)
        trend_data = self._extract_trend_data(articles)
        
        # Prepare a concise list of article titles and URIs for citation in the prompt
        articles_for_citation_prompt_str = ""
        for art in articles[:15]: # Use first 15 articles for citation context
            title = art.get("title", "Untitled")
            uri = art.get("uri", "#")
            articles_for_citation_prompt_str += f"- Title: {title}, URI: {uri}\\n"
        
        # Generate analysis using AI model
        ai_model = get_ai_model(model_name="gpt-3.5-turbo")
        prompt = self._create_trend_analysis_prompt(topic, trend_data, articles_for_citation_prompt_str)
        
        try:
            response = await ai_model.generate(prompt)
            # Extract content from response object
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                return response.message.content
            elif hasattr(response, 'content'):
                return response.content
            else:
                return str(response)
        except Exception as e:
            logger.error(f"Error generating trend analysis for '{topic}': {str(e)}", exc_info=True)
            return "Error generating trend analysis."

    async def _generate_article_insights(
        self, 
        topic: str, 
        start_date: datetime.date, 
        end_date: datetime.date
    ) -> str:
        """
        Generate insights from articles with thematic analysis, styled like the dashboard.
        Uses direct database and AI processing like the dashboard.
        """
        # Fetch articles for the topic within date range - limit to reasonable number for analysis
        article_limit = 30
        articles = self._fetch_articles(topic, start_date, end_date, article_limit)
        
        if not articles or len(articles) < 3:  # Need enough articles for meaningful themes
            return "Not enough articles found for meaningful theme analysis."
        
        # 1. Create a mapping of URI to article data for easy lookup
        uri_to_article_map = {art.get('uri'): {
            'title': art.get('title'),
            'summary': art.get('summary'),
            'news_source': art.get('news_source'),
            'publication_date': art.get('publication_date'),
            'tags': art.get('tags')
        } for art in articles if art.get('uri')}
        
        # 2. Prepare article details for LLM analysis
        article_details_for_llm = []
        for i, art in enumerate(articles):
            detail = (
                f"Article {i+1}:\n"
                f"  Title: {art.get('title') or 'Untitled'}\n"
                f"  Source: {art.get('news_source') or 'Unknown'}\n"
                f"  Published: {art.get('publication_date') or 'N/A'}\n"
                f"  Summary: {art.get('summary') or 'No summary available'}\n"
                f"  URI: {art.get('uri')}"
            )
            article_details_for_llm.append(detail)
        
        combined_article_text = "\n---\n".join(article_details_for_llm)
        
        # 3. Initialize LLM and create prompt for thematic analysis
        ai_model = get_ai_model(model_name="gpt-3.5-turbo")  # Use available model
        if not ai_model:
            return "Failed to initialize AI model for article insights."
        
        # 4. Create prompt for thematic analysis - following dashboard approach
        system_prompt = (
            f"You are an expert research analyst specializing in '{topic}'. "
            f"Analyze the provided articles and identify 3-5 common themes or patterns that emerge. "
            f"For each theme you identify:"
            f"\n1. Give it a concise, descriptive name"
            f"\n2. Write a summary paragraph explaining the theme (2-3 sentences)"
            f"\n3. List the URIs of 2-5 articles that best exemplify this theme"
            f"\nFormat your response as JSON with the structure:"
            f"\n[{{"
            f"\n  \"theme_name\": \"Name of Theme\","
            f"\n  \"theme_summary\": \"Summary explanation of the theme...\","
            f"\n  \"article_uris\": [\"uri1\", \"uri2\", ...] // URIs exactly as provided"
            f"\n}}, {{ ... next theme ... }}]"
        )
        
        user_prompt = f"Here are recent articles about '{topic}' to analyze for common themes:\n\n{combined_article_text}\n\nIdentify 3-5 themes and format as specified JSON."
        
        # Format messages correctly based on the model implementation
        # Some models use a list of role/content dictionaries, while others just take a prompt string
        try:
            # 5. Call LLM to identify themes
            response = None
            
            # Check if the model expects a message-style format or a simple prompt
            if hasattr(ai_model, 'generate_response'):
                # This is likely the standard LiteLLM-based model
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
                # The generate_response method could be synchronous or asynchronous
                # Handle both cases properly
                response_text = ai_model.generate_response(messages)
                # If it's not an awaitable (coroutine), we don't need to await it
                if not hasattr(response_text, '__await__'):
                    # It's a string or another direct value, not a coroutine
                    pass
                else:
                    # It's an awaitable, so we need to await it
                    response_text = await response_text
            else:
                # Fallback to simple prompt approach - concatenate prompts
                combined_prompt = f"{system_prompt}\n\n{user_prompt}"
                response = await ai_model.generate(combined_prompt)
                
                # Extract content based on response format
                if hasattr(response, 'message') and hasattr(response.message, 'content'):
                    response_text = response.message.content
                elif hasattr(response, 'content'):
                    response_text = response.content
                else:
                    response_text = str(response)
            
            # 6. Parse LLM response to extract themes
            import json
            import re
            llm_themes = []
            
            # Try to extract JSON from the response - handle both clean JSON and markdown code blocks
            json_match = re.search(r'```json\s*(\[\s*\{.*\}\s*\])\s*```|```(\[\s*\{.*\}\s*\])```|\[\s*\{.*\}\s*\]', response_text, re.DOTALL)
            if json_match:
                # Get the first non-None capturing group
                json_str = next(group for group in json_match.groups() if group is not None)
                llm_themes = json.loads(json_str)
            else:
                # Fallback - try parsing the whole response as JSON
                try:
                    llm_themes = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.error(f"Could not parse LLM response as JSON: {response_text[:200]}...")
                    return "Error: Could not parse AI response. Please try again."
            
            # 7. Build themed insights from LLM analysis
            final_themed_insights = []
            for llm_theme_data in llm_themes:
                if not isinstance(llm_theme_data, dict) or \
                   "theme_name" not in llm_theme_data or \
                   "theme_summary" not in llm_theme_data or \
                   "article_uris" not in llm_theme_data or \
                   not isinstance(llm_theme_data["article_uris"], list):
                    logger.warning(f"Skipping malformed theme data from LLM")
                    continue
                
                theme_articles = []
                for uri in llm_theme_data["article_uris"]:
                    original_article_data = uri_to_article_map.get(uri)
                    if original_article_data:
                        # Ensure summary is a string and truncate for short_summary
                        summary_text = original_article_data.get('summary', '')
                        short_s = (summary_text[:150] + '...') \
                            if summary_text and len(summary_text) > 150 else summary_text
                        
                        theme_articles.append({
                            "uri": uri,
                            "title": original_article_data.get('title'),
                            "news_source": original_article_data.get('news_source'),
                            "publication_date": original_article_data.get('publication_date'),
                            "short_summary": short_s
                        })
                
                if theme_articles:
                    final_themed_insights.append({
                        "theme_name": llm_theme_data["theme_name"],
                        "theme_summary": llm_theme_data["theme_summary"],
                        "articles": theme_articles
                    })
            
            # 8. Format the themed insights as markdown
            return self._format_article_insights_from_api(final_themed_insights)
                
        except Exception as e:
            logger.error(f"Error generating article insights for '{topic}': {str(e)}", exc_info=True)
            return f"Error generating article insights: {str(e)}"

    def _format_article_insights_from_api(self, themed_insights: list) -> str:
        """
        Format themed article insights from the API as markdown.
        Matches the style used in the topic dashboard.
        """
        if not themed_insights or len(themed_insights) == 0:
            return "No thematic article insights available for this period."
            
        result = ""
        
        for theme in themed_insights:
            # Add theme heading and summary
            result += f"#### {theme.get('theme_name', 'Unnamed Theme')} _(Theme)_\n\n"
            result += f"{theme.get('theme_summary', 'No summary provided for this theme.')}\n\n"
            
            # Add articles under this theme
            articles = theme.get('articles', [])
            if articles:
                for article in articles:
                    title = article.get('title', 'Untitled Article')
                    uri = article.get('uri', '#')
                    source = article.get('news_source', 'Unknown Source')
                    date = article.get('publication_date', 'N/A')
                    summary = article.get('short_summary', '')
                    
                    result += f"- **[{title}]({uri})**  \n"
                    result += f"  *{source} - {date}*  \n"
                    if summary:
                        result += f"  _{summary}_\n\n"
                    else:
                        result += "\n"
            else:
                result += "_No specific articles listed for this theme._\n\n"
            
            result += "\n"
            
        return result

    async def _generate_key_articles_list(
        self, 
        topic: str, 
        start_date: datetime.date, 
        end_date: datetime.date,
        limit: int = 6
    ) -> str:
        """
        Generate a list of key articles with links and brief summaries using the report markdown template.
        """
        articles = self._fetch_articles(topic, start_date, end_date, limit=limit)
        if not articles:
            return "No key articles found for this period."
        
        result = "**Key Articles for Your Attention:**\\n\\n" 
        ai_model = get_ai_model(model_name="gpt-3.5-turbo") # Initialize model once

        for idx, article in enumerate(articles, 1):
            title = article.get("title", "Untitled")
            uri = article.get("uri", "#")
            source = article.get("news_source", "Unknown source")
            pub_date = article.get("publication_date", "Unknown date")
            summary = article.get("summary", "No summary available.")
            tags = article.get("tags", "")
            tag_str = ""
            if tags:
                if isinstance(tags, list):
                    tag_str = ", ".join(tags)
                elif isinstance(tags, str):
                    tag_str = tags

            # Generate 'Why this merits your attention' blurb
            why_merits_attention = "Analysis of importance pending."
            if summary != "No summary available.":
                try:
                    attention_prompt = self._create_why_merits_attention_prompt(title, summary)
                    response = await ai_model.generate(attention_prompt)
                    if hasattr(response, 'message') and hasattr(response.message, 'content'):
                        why_merits_attention = response.message.content.strip()
                    elif hasattr(response, 'content'):
                        why_merits_attention = response.content.strip()
                    else:
                        why_merits_attention = str(response).strip()
                except Exception as e:
                    logger.error(f"Error generating 'why merits attention' for '{title}': {str(e)}", exc_info=True)
                    why_merits_attention = "Could not generate importance analysis."
            else:
                why_merits_attention = "Full summary not available to determine specific importance."

            result += (
                f"- **[{title}]({uri})**\\n"
                f"  *Source:* {source}  |  *Date:* {pub_date}\\n"
                f"  *Summary:* {summary}\\n"
                f"  *Why this merits your attention:* {why_merits_attention}\\n"
                f"  {'\*Tags:* ' + tag_str if tag_str else ''}\\n\\n"
            )
        return result

    def _create_why_merits_attention_prompt(self, article_title: str, article_summary: str) -> str:
        """Create prompt to explain why an article merits a decision maker's attention."""
        return (
            f"Article Title: \"{article_title}\"\n"
            f"Article Summary: \"{article_summary}\"\n\n"
            f"Based on the title and summary above, provide a single, concise sentence (max 25 words) explaining to a busy decision maker why this specific article merits their attention. Focus on its key insight, implication, or relevance for strategic thinking."
        )

    async def _generate_latest_podcast(self, topic: str) -> str:
        """
        Generate link to the latest podcast, including a clickable link if available,
        an image, and an AI-generated summary of its transcript.
        """
        podcast_data = None
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # Assuming a 'transcript_text' field exists in the podcasts table
            cursor.execute(
                """
                SELECT id, title, created_at, audio_url, transcript_text 
                FROM podcasts
                WHERE topic = ? OR topic IS NULL OR topic = 'General' # Added topic filter, fallback to NULL or General
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (topic,)
            )
            podcast_data = cursor.fetchone()

        if not podcast_data:
            return "No recent podcasts available for this topic."
        
        podcast_id, title, created_at, audio_url, transcript_text = podcast_data
        
        podcast_summary = "Summary not available."
        if transcript_text and transcript_text.strip():
            try:
                ai_model = get_ai_model(model_name="gpt-3.5-turbo")
                summary_prompt = self._create_podcast_summary_prompt(title, transcript_text)
                response = await ai_model.generate(summary_prompt)
                if hasattr(response, 'message') and hasattr(response.message, 'content'):
                    podcast_summary = response.message.content.strip()
                elif hasattr(response, 'content'):
                    podcast_summary = response.content.strip()
                else:
                    podcast_summary = str(response).strip()
            except Exception as e:
                logger.error(f"Error generating podcast summary for '{title}': {str(e)}", exc_info=True)
                podcast_summary = "Could not generate summary."
        elif not transcript_text or not transcript_text.strip():
             podcast_summary = "Transcript not available for summarization."

        # Image markdown - assuming static path
        image_markdown = "![Podcast Briefing](/static/img/trend_daily_briefing_square.gif)\\n"
        
        result = image_markdown
        result += f"**Latest Podcast: {title}** (Published: {created_at.strftime('%Y-%m-%d')})\\n"
        if audio_url:
            result += f"[Listen Now]({audio_url})\\n"
        result += f"*Summary:* {podcast_summary}\\n"
        
        return result

    def _create_podcast_summary_prompt(self, podcast_title: str, transcript: str) -> str:
        """Create prompt for summarizing a podcast transcript."""
        # Take first N characters of transcript to avoid overly long prompts
        transcript_snippet = transcript[:3000] 
        return (
            f"Podcast Title: \"{podcast_title}\"\n"
            f"Transcript Snippet:\n\"{transcript_snippet}...\"\n\n"
            f"Based on the podcast title and transcript snippet, provide a concise 2-3 sentence summary highlighting the key topics or insights discussed. Focus on what would be most relevant for a busy decision maker."
        )

    def _fetch_articles(
        self, 
        topic: str, 
        start_date: datetime.date, 
        end_date: datetime.date,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Fetch articles for a topic within a date range.
        
        Args:
            topic: Topic to fetch articles for
            start_date: Start date
            end_date: End date
            limit: Optional limit of articles to return
            
        Returns:
            List[Dict]: List of article data dictionaries
        """
        # Convert dates to strings for SQL
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        # SQL limit clause
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT * FROM articles 
                WHERE topic = ? 
                AND publication_date BETWEEN ? AND ?
                ORDER BY publication_date DESC
                {limit_clause}
                """,
                (topic, start_str, end_str)
            )
            articles = cursor.fetchall()
            
        # Convert to list of dictionaries with column names
        column_names = [description[0] for description in cursor.description]
        result = []
        
        for row in articles:
            article_dict = dict(zip(column_names, row))
            result.append(article_dict)
            
        logger.info(f"Fetched {len(articles)} articles for topic '{topic}' between {start_str} and {end_str}.")
        return result

    def _prepare_articles_data(self, articles: List[Dict]) -> str:
        """
        Prepare articles data for use in AI prompts.
        
        Args:
            articles: List of article dictionaries
            
        Returns:
            str: Formatted article data as text
        """
        result = ""
        
        for i, article in enumerate(articles, 1):
            title = article.get("title", "Untitled")
            source = article.get("news_source", "Unknown source")
            pub_date = article.get("publication_date", "Unknown date")
            summary = article.get("summary", "No summary available.")
            
            result += f"Article {i}:\n"
            result += f"Title: {title}\n"
            result += f"Source: {source}\n"
            result += f"Date: {pub_date}\n"
            result += f"Summary: {summary}\n\n"
            
        return result

    def _extract_trend_data(self, articles: List[Dict]) -> Dict:
        """
        Extract trend data from articles for analysis.
        
        Args:
            articles: List of article dictionaries
            
        Returns:
            Dict: Trend data including counts, distributions, etc.
        """
        # Initialize counters
        categories = {}
        future_signals = {}
        sentiments = {}
        time_to_impacts = {}
        tags = {}
        
        # Count occurrences
        for article in articles:
            category = article.get("category")
            if category:
                categories[category] = categories.get(category, 0) + 1
                
            future_signal = article.get("future_signal")
            if future_signal:
                future_signals[future_signal] = future_signals.get(future_signal, 0) + 1
                
            sentiment = article.get("sentiment")
            if sentiment:
                sentiments[sentiment] = sentiments.get(sentiment, 0) + 1
                
            time_to_impact = article.get("time_to_impact")
            if time_to_impact:
                time_to_impacts[time_to_impact] = time_to_impacts.get(time_to_impact, 0) + 1
                
            article_tags = article.get("tags")
            if article_tags and isinstance(article_tags, list):
                for tag in article_tags:
                    tags[tag] = tags.get(tag, 0) + 1
            elif article_tags and isinstance(article_tags, str):
                # Handle tags stored as comma-separated string
                for tag in article_tags.split(","):
                    clean_tag = tag.strip()
                    if clean_tag:
                        tags[clean_tag] = tags.get(clean_tag, 0) + 1
        
        return {
            "total_articles": len(articles),
            "categories": categories,
            "future_signals": future_signals,
            "sentiments": sentiments,
            "time_to_impacts": time_to_impacts,
            "tags": tags
        }

    def _create_summary_prompt(self, topic: str, article_data: str) -> str:
        """
        Create prompt for topic summary generation with explicit structure and links,
        tailored for a decision-making audience.
        """
        return (
            f"You are an AI assistant analyzing articles about '{topic}' for a busy decision-maker.\n"
            f"Write a concise, structured summary based on the provided articles. Focus on the most critical information. Use bullet points for lists.\n"
            f"Do not reference article numbers in your output.\n\n"
            f"Use the following format:\n\n"
            f"**Summary of {topic}**\n"
            f"- Provide a brief (2-3 sentences) high-level overview of the current state of '{topic}'.\n\n"
            f"**Top Three Developments**\n"
            f"- Development 1: [Briefly state the development]. **Why this is need-to-know:** [Explain its significance in 1-2 sentences]. Cite: **[Relevant Article Title](Article URI)**\n"
            f"- Development 2: [Briefly state the development]. **Why this is need-to-know:** [Explain its significance in 1-2 sentences]. Cite: **[Relevant Article Title](Article URI)**\n"
            f"- Development 3: [Briefly state the development]. **Why this is need-to-know:** [Explain its significance in 1-2 sentences]. Cite: **[Relevant Article Title](Article URI)**\n\n"
            f"**Top 3 Industry Trends**\n"
            f"- Trend 1: [Briefly state the trend]. **Why this is interesting:** [Explain its significance in 1-2 sentences]. Cite: **[Relevant Article Title](Article URI)**\n"
            f"- Trend 2: [Briefly state the trend]. **Why this is interesting:** [Explain its significance in 1-2 sentences]. Cite: **[Relevant Article Title](Article URI)**\n"
            f"- Trend 3: [Briefly state the trend]. **Why this is interesting:** [Explain its significance in 1-2 sentences]. Cite: **[Relevant Article Title](Article URI)**\n\n"
            f"**Strategic Takeaways for Decision Makers:**\n"
            f"- Provide 2-3 high-level strategic implications or actionable insights derived from the above points that a decision maker should consider.\n\n"
            f"Important: Always use the exact article titles and URIs from the data. Be very concise and focus on impact.\n\n"
            f"Articles for analysis:\n{article_data}"
        )

    def _create_trend_analysis_prompt(self, topic: str, trend_data: Dict, article_data_str: str) -> str:
        """
        Create prompt for trend analysis content with insight-driven format,
        now including a placeholder for article data for citation.
        """
        # Format data for prompt
        categories = trend_data.get("categories", {})
        sentiments = trend_data.get("sentiments", {})
        future_signals = trend_data.get("future_signals", {})
        time_to_impacts = trend_data.get("time_to_impacts", {})
        # Ensure top_tags is a list of tuples/lists if it comes from items()
        tags_data = trend_data.get("tags", {})
        if isinstance(tags_data, dict):
            # Sort tags by count and take top N, e.g., top 10
            top_tags_list = sorted(tags_data.items(), key=lambda item: item[1], reverse=True)[:10]
        elif isinstance(tags_data, list): # Assuming it might already be a list of [tag, count] pairs
            top_tags_list = sorted(tags_data, key=lambda item: item[1], reverse=True)[:10]
        else:
            top_tags_list = [] # Default to empty list if format is unexpected

        # Format each section nicely for the prompt
        categories_str = "\\n".join([f"- {k}: {v}" for k, v in categories.items()])
        sentiments_str = "\\n".join([f"- {k}: {v}" for k, v in sentiments.items()])
        signals_str = "\\n".join([f"- {k}: {v}" for k, v in future_signals.items()])
        tti_str = "\\n".join([f"- {k}: {v}" for k, v in time_to_impacts.items()])
        tags_str = ", ".join([f"{k} ({v})" for k, v in top_tags_list]) # Show count for tags as well
        
        return (
            f"Analyze the following trend data for '{topic}'. "
            f"Provide a concise, structured analysis of trends and patterns, noting emerging themes and developments based on these data patterns.\n\n"
            f"**Overall Trend Data for {topic}:**\n"
            f"- Categories Distribution: {categories_str}\n"
            f"- Sentiment Distribution: {sentiments_str}\n"
            f"- Future Signal Distribution: {signals_str}\n"
            f"- Time to Impact Distribution: {tti_str}\n"
            f"- Top Tags (up to 10 with counts): {tags_str}\n\n"
            f"**Analysis & Insights:**\n"
            f"Begin with a 1-2 sentence overview of the general sentiment and activity level for '{topic}'.\n"
            f"Then, for each of the following aspects, provide 2-3 bullet points highlighting key patterns, shifts, or noteworthy observations. If an observation is particularly illustrated by a specific article, cite it using **[Article Title](Article URI)** from the reference list below:\n"
            f"  - **Category Insights:** (e.g., Dominant categories, significant shifts in category focus, surprising under/over-representation).\
          *Observation 1... Cite if applicable.*\
          *Observation 2... Cite if applicable.*\n"
            f"  - **Sentiment Insights:** (e.g., Predominant sentiment, changes over time if inferable, sentiment drivers).\
          *Observation 1... Cite if applicable.*\
          *Observation 2... Cite if applicable.*\n"
            f"  - **Future Outlook (Signals & TTI):** (e.g., Implications of future signals, common TTI, alignment or divergence between signals and TTI).\
          *Observation 1... Cite if applicable.*\
          *Observation 2... Cite if applicable.*\n"
            f"  - **Key Tag Themes:** (e.g., Dominant tags and what they signify, clusters of related tags appearing frequently).\
          *Observation 1... Cite if applicable.*\
          *Observation 2... Cite if applicable.*\n\n"
            f"Conclude with a 2-3 sentence synthesis on any connections between these different distributions or overall strategic insights valuable for decision-making.\n\n"
            f"Reference Articles (for citation purposes only if applicable to the data patterns observed):\n{article_data_str}"
            f"Be specific and data-driven. Avoid generic statements."
        )

    def _create_insights_prompt(self, topic: str, article_data: str) -> str:
        """
        Create prompt for article insights generation, dashboard style (no article numbers).
        This is kept for backward compatibility but no longer used.
        """
        return f"""
        Identify 3-5 major themes from the articles about "{topic}". For each theme:
        - Provide a theme title
        - Write a 1-2 sentence summary of the theme
        - List the relevant articles for the theme, each with:
            - title
            - url
            - news source
            - publication date
            - a 1-2 sentence summary
        
        Do not reference article numbers. Do not mention 'Article X'.
        
        Format your response as a JSON list of themes, each with:
        - theme_name
        - theme_summary
        - articles: list of dicts with title, uri, news_source, publication_date, short_summary
        
        Articles:
        {article_data}
        """

    def _get_content_type_display_name(self, content_type: str) -> str:
        """
        Get user-friendly display name for content type.
        
        Args:
            content_type: Content type identifier
            
        Returns:
            str: Display name
        """
        display_names = {
            "topic_summary": "Topic Summary",
            "key_charts": "Key Charts",
            "trend_analysis": "Trend Analysis",
            "article_insights": "Article Insights",
            "key_articles": "Key Articles",
            "latest_podcast": "Latest Podcast",
            "ethical_societal_impact": "Ethical & Societal Impact",
            "business_impact": "Business Impact",
            "market_impact": "Market Impact"
        }
        
        return display_names.get(content_type, content_type.replace("_", " ").title())

    # Placeholder for new impact section generators and their prompts
    async def _generate_ethical_societal_impact_section(self, topic: str, start_date: datetime.date, end_date: datetime.date) -> Optional[str]:
        articles = self._fetch_articles(topic, start_date, end_date, limit=15)
        if not articles:
            return "No articles found for Ethical & Societal Impact analysis."
        article_data = self._prepare_articles_data(articles)
        ai_model = get_ai_model(model_name="gpt-3.5-turbo")
        prompt = self._create_ethical_societal_impact_prompt(topic, article_data)
        try:
            response = await ai_model.generate(prompt)
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                return response.message.content
            elif hasattr(response, 'content'):
                return response.content
            return str(response)
        except Exception as e:
            logger.error(f"Error generating ethical/societal impact section for '{topic}': {str(e)}", exc_info=True)
            return "Error generating ethical/societal impact section."

    def _create_ethical_societal_impact_prompt(self, topic: str, article_data: str) -> str:
        return (
            f"Analyze the ethical and societal impacts related to '{topic}' based on the following articles.\n"
            f"Provide a concise analysis (2-3 paragraphs) highlighting key ethical dilemmas, societal consequences, and considerations. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**.\n\n"
            f"Articles for analysis:\n{article_data}"
        )

    async def _generate_business_impact_section(self, topic: str, start_date: datetime.date, end_date: datetime.date) -> Optional[str]:
        articles = self._fetch_articles(topic, start_date, end_date, limit=15)
        if not articles:
            return "No articles found for Business Impact analysis."
        article_data = self._prepare_articles_data(articles)
        ai_model = get_ai_model(model_name="gpt-3.5-turbo")
        prompt = self._create_business_impact_prompt(topic, article_data)
        try:
            response = await ai_model.generate(prompt)
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                return response.message.content
            elif hasattr(response, 'content'):
                return response.content
            return str(response)
        except Exception as e:
            logger.error(f"Error generating business impact section for '{topic}': {str(e)}", exc_info=True)
            return "Error generating business impact section."

    def _create_business_impact_prompt(self, topic: str, article_data: str) -> str:
        return (
            f"Analyze the business impacts and opportunities related to '{topic}' based on the following articles.\n"
            f"Provide a concise analysis (2-3 paragraphs) highlighting key business implications, potential opportunities, disruptions, and strategic considerations for businesses. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**.\n\n"
            f"Articles for analysis:\n{article_data}"
        )

    async def _generate_market_impact_section(self, topic: str, start_date: datetime.date, end_date: datetime.date) -> Optional[str]:
        articles = self._fetch_articles(topic, start_date, end_date, limit=15)
        if not articles:
            return "No articles found for Market Impact analysis."
        article_data = self._prepare_articles_data(articles)
        ai_model = get_ai_model(model_name="gpt-3.5-turbo")
        prompt = self._create_market_impact_prompt(topic, article_data)
        try:
            response = await ai_model.generate(prompt)
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                return response.message.content
            elif hasattr(response, 'content'):
                return response.content
            return str(response)
        except Exception as e:
            logger.error(f"Error generating market impact section for '{topic}': {str(e)}", exc_info=True)
            return "Error generating market impact section."

    def _create_market_impact_prompt(self, topic: str, article_data: str) -> str:
        return (
            f"Analyze the market impacts, trends, and competitive landscape related to '{topic}' based on the following articles.\n"
            f"Provide a concise analysis (2-3 paragraphs) highlighting key market trends, competitive dynamics, potential market shifts, and implications for market positioning. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**.\n\n"
            f"Articles for analysis:\n{article_data}"
        )


# Factory function for dependency injection
def get_newsletter_service(db: Database = None) -> NewsletterService:
    """Get or create a NewsletterService instance."""
    return NewsletterService(db) 