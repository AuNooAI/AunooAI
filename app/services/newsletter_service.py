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
        self.progress_callback = None

    def set_progress_callback(self, callback_fn):
        """
        Set a callback function for reporting progress.
        
        Args:
            callback_fn: Function that takes (progress, step, message) parameters
        """
        self.progress_callback = callback_fn

    def report_progress(self, progress: Optional[float], step: str, message: str = None):
        """
        Report progress of newsletter compilation.
        
        Args:
            progress: Percentage complete (0-100) or None to keep current progress
            step: Current step being processed
            message: Optional status message
        """
        if self.progress_callback:
            # If progress is None, don't update the progress percentage
            self.progress_callback(progress, step, message)

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
            
            # Report initial progress
            self.report_progress(5.0, "Initialized", "Date range calculated")
            
            # Initialize the markdown content
            markdown_content = self._create_header(request.frequency, request.topics, start_date, end_date)
            self.report_progress(10.0, "Header created", "Newsletter header generated")
            
            # Calculate total steps for progress tracking
            total_content_types = len(request.content_types)
            total_topics = len(request.topics)
            total_steps = total_topics * total_content_types
            current_step = 0
            
            # Process each topic and content type
            for topic_idx, topic in enumerate(request.topics):
                logger.info(f"Processing topic: {topic}")
                topic_content = f"## {topic}\n\n"
                self.report_progress(
                    10.0 + (topic_idx * 85.0 / total_topics), 
                    f"Processing topic {topic_idx+1} of {total_topics}",
                    f"Starting to process topic: {topic}"
                )
                
                for content_type_idx, content_type in enumerate(request.content_types):
                    current_step += 1
                    progress = 10.0 + (current_step * 85.0 / total_steps)
                    
                    logger.info(f"Generating content for topic '{topic}', type: '{content_type}'")
                    self.report_progress(
                        progress,
                        f"Content type {content_type}",
                        f"Generating '{self._get_content_type_display_name(content_type)}' for '{topic}'"
                    )
                    
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
                            topic_content += f"### {self._get_content_type_display_name(content_type)}\n\n"
                            topic_content += f"_No content available for this section._\n\n"
                    except Exception as e_section:
                        logger.error(f"Error generating section '{content_type}' for topic '{topic}': {str(e_section)}", exc_info=True)
                        topic_content += f"### {self._get_content_type_display_name(content_type)}\n\n"
                        topic_content += f"_Error generating this section: {str(e_section)}_\n\n"
                
                markdown_content += topic_content
                self.report_progress(
                    10.0 + ((topic_idx + 1) * 85.0 / total_topics),
                    f"Topic {topic_idx+1} completed",
                    f"Finished processing topic: {topic}"
                )
            
            logger.info(f"Newsletter compilation completed for request: {request.frequency}, topics: {request.topics}")
            # Final progress update
            self.report_progress(100.0, "Completed", "Newsletter compilation finished successfully")
            
            return markdown_content

        except Exception as e_compile:
            logger.error(f"Fatal error during newsletter compilation: {str(e_compile)}", exc_info=True)
            # Report error in progress
            self.report_progress(100.0, "Error", f"Error: {str(e_compile)}")
            
            # Return a basic error report rather than raising an exception
            error_markdown = f"# Newsletter Compilation Error\n\n"
            error_markdown += f"**Error Message:** {str(e_compile)}\n\n"
            error_markdown += f"**Request Details:**\n"
            error_markdown += f"- Frequency: {request.frequency}\n"
            error_markdown += f"- Topics: {', '.join(request.topics)}\n"
            error_markdown += f"- Content Types: {', '.join(request.content_types)}\n"
            error_markdown += f"- Date Range: {request.start_date} to {request.end_date}\n\n"
            error_markdown += f"Please check the server logs for more details about this error."
            return error_markdown

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
        
        # Add banner image (placeholder for now, would be replaced with uploaded banner)
        header = "<img src=\"/static/img/aunoonewsnetwork.png\" alt=\"Newsletter Banner\" width=\"100%\">\n\n"
        header += f"# {frequency.capitalize()} Newsletter: {topic_str}\n\n"
        header += f"Covering the period from {date_range}\n\n"
        header += f"Published on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
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
        content_type_name = self._get_content_type_display_name(content_type)
        
        # Report starting a specific content generation
        self.report_progress(
            None,  # Keep the current progress percentage
            f"Generating {content_type_name}",
            f"Fetching data for {content_type_name} section for {topic}"
        )
        
        try:
            result = None
            
            if content_type == "topic_summary":
                self.report_progress(None, f"Generating {content_type_name}", f"Analyzing articles for {topic} summary")
                result = await self._generate_topic_summary(topic, start_date, end_date)
            elif content_type == "key_charts":
                self.report_progress(None, f"Generating {content_type_name}", f"Creating data visualizations for {topic}")
                result = await self._generate_key_charts(topic, start_date, end_date)
            elif content_type == "trend_analysis":
                self.report_progress(None, f"Generating {content_type_name}", f"Analyzing trend patterns for {topic}")
                result = await self._generate_trend_analysis(topic, start_date, end_date)
            elif content_type == "article_insights":
                self.report_progress(None, f"Generating {content_type_name}", f"Identifying key themes in {topic} articles")
                result = await self._generate_article_insights(topic, start_date, end_date)
            elif content_type == "key_articles":
                self.report_progress(None, f"Generating {content_type_name}", f"Selecting most important articles for {topic}")
                # Add divider before key articles section
                result = "---\n\n" + await self._generate_key_articles_list(topic, start_date, end_date)
            elif content_type == "latest_podcast":
                self.report_progress(None, f"Generating {content_type_name}", f"Finding recent podcasts about {topic}")
                podcast_content = await self._generate_latest_podcast(topic)
                # Add divider after podcast summary
                result = podcast_content + "---\n\n"
            elif content_type == "ethical_societal_impact":
                self.report_progress(None, f"Generating {content_type_name}", f"Analyzing ethical implications of {topic}")
                result = await self._generate_ethical_societal_impact_section(topic, start_date, end_date)
            elif content_type == "business_impact":
                self.report_progress(None, f"Generating {content_type_name}", f"Assessing business impacts of {topic}")
                result = await self._generate_business_impact_section(topic, start_date, end_date)
            elif content_type == "market_impact":
                self.report_progress(None, f"Generating {content_type_name}", f"Evaluating market implications of {topic}")
                result = await self._generate_market_impact_section(topic, start_date, end_date)
            else:
                logger.warning(f"Unknown content type: {content_type}")
                return None
                
            self.report_progress(
                None,  # Keep the current progress percentage
                f"Completed {content_type_name}",
                f"Successfully generated {content_type_name} for {topic}"
            )
            
            return result
        except Exception as e:
            logger.error(f"Error generating {content_type_name} for {topic}: {str(e)}")
            self.report_progress(
                None,  # Keep the current progress percentage
                f"Error in {content_type_name}",
                f"Failed to generate {content_type_name} for {topic}: {str(e)}"
            )
            # Re-raise to be handled by the calling method
            raise

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
        
        # Get custom prompt from database or use default
        prompt_template = self._get_prompt_template("topic_summary")
        prompt = self._format_prompt(prompt_template, {
            "topic": topic, 
            "article_data": article_data
        })
        
        # Generate summary using AI model
        ai_model = get_ai_model(model_name="gpt-4o-mini")
        
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
            
        # Generate charts - removed volume chart, keep sentiment over time and radar chart
        sentiment_over_time_chart = self.chart_service.generate_sentiment_over_time_chart(
            articles, start_date, end_date
        )
        radar_chart = self.chart_service.generate_radar_chart(articles)
        
        # Combine charts into markdown - with updated headings
        result = ""
        result += "#### Sentiment Over Time\n"
        result += (
            f"![Sentiment Over Time Chart]({sentiment_over_time_chart})\n\n"
        )
        result += "#### Future Signals Analysis\n"
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
        
        # Format each section nicely for the prompt
        categories_str = "\\n".join([f"- {k}: {v}" for k, v in trend_data.get("categories", {}).items()])
        sentiments_str = "\\n".join([f"- {k}: {v}" for k, v in trend_data.get("sentiments", {}).items()])
        signals_str = "\\n".join([f"- {k}: {v}" for k, v in trend_data.get("future_signals", {}).items()])
        tti_str = "\\n".join([f"- {k}: {v}" for k, v in trend_data.get("time_to_impacts", {}).items()])
        
        tags_data = trend_data.get("tags", {})
        if isinstance(tags_data, dict):
            top_tags_list = sorted(tags_data.items(), key=lambda item: item[1], reverse=True)[:10]
        elif isinstance(tags_data, list):
            top_tags_list = sorted(tags_data, key=lambda item: item[1], reverse=True)[:10]
        else:
            top_tags_list = []
        tags_str = ", ".join([f"{k} ({v})" for k, v in top_tags_list])
        
        # Get custom prompt from database or use default
        prompt_template = self._get_prompt_template("trend_analysis")
        prompt = self._format_prompt(prompt_template, {
            "topic": topic,
            "categories_str": categories_str,
            "sentiments_str": sentiments_str,
            "signals_str": signals_str,
            "tti_str": tti_str,
            "tags_str": tags_str,
            "article_data_str": articles_for_citation_prompt_str
        })
        
        # Generate analysis using AI model
        ai_model = get_ai_model(model_name="gpt-4o-mini")
        
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
        ai_model = get_ai_model(model_name="gpt-4o-mini")  # Use available model
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
                try:
                    # Get the first non-None capturing group
                    matching_groups = [group for group in json_match.groups() if group is not None]
                    if matching_groups:
                        json_str = matching_groups[0]
                        llm_themes = json.loads(json_str)
                    else:
                        logger.warning("Regex matched but no capturing groups found")
                        llm_themes = []
                except Exception as json_ex:
                    logger.error(f"Error extracting JSON from regex match: {str(json_ex)}")
                    llm_themes = []
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
        
        result = "**Key Articles for Your Attention:**\n\n" 
        ai_model = get_ai_model(model_name="gpt-4o-mini") # Initialize model once

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

            # Use proper markdown formatting with the requested template:
            # ### [title](url)
            # **Source:** | {news_source} | **Date:** {date}
            # {summary}
            result += f"### [{title}]({uri})\n"
            result += f"**Source:** | {source} | **Date:** {pub_date}\n\n"
            result += f"{summary}\n\n"
            if why_merits_attention and why_merits_attention != "Analysis of importance pending.":
                result += f"**Why this matters:** {why_merits_attention}\n\n"
            if tag_str:
                result += f"**Tags:** {tag_str}\n\n"
            result += "---\n\n"
        
        return result

    def _create_why_merits_attention_prompt(self, article_title: str, article_summary: str) -> str:
        """Create prompt to explain why an article merits a decision maker's attention."""
        # Get custom prompt from database or use default
        prompt_template = self._get_prompt_template("key_articles")
        return self._format_prompt(prompt_template, {
            "article_title": article_title,
            "article_summary": article_summary
        })

    async def _generate_latest_podcast(self, topic: str) -> str:
        """
        Generate link to the latest podcast, including a clickable link if available,
        an image, and a brief description.
        """
        podcast_data = None
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # Get column information to handle table schema dynamically
            cursor.execute("PRAGMA table_info(podcasts)")
            table_info = cursor.fetchall()
            column_names = [col[1] for col in table_info]  # Column name is at index 1
            
            # Build a query that works with the available columns
            has_transcript = 'transcript_text' in column_names
            has_topic = 'topic' in column_names
            
            # Base columns we need
            select_columns = ["id", "title", "created_at"]
            if "audio_url" in column_names:
                select_columns.append("audio_url")
            if has_transcript:
                select_columns.append("transcript_text")
            
            # Build the query
            query = f"""
                SELECT {', '.join(select_columns)}
                FROM podcasts
            """
            
            # Add WHERE clause if topic column exists
            params = []
            if has_topic:
                query += "WHERE topic = ? OR topic IS NULL OR topic = 'General' "
                params.append(topic)
            
            # Add ORDER BY and LIMIT
            query += """
                ORDER BY created_at DESC
                LIMIT 1
            """
            
            # Execute the query
            cursor.execute(query, tuple(params))
            podcast_data = cursor.fetchone()

        if not podcast_data:
            return "No recent podcasts available for this topic."
        
        # Unpack data based on which columns we selected
        column_count = len(select_columns)
        podcast_id = podcast_data[0] if column_count > 0 else None
        title = podcast_data[1] if column_count > 1 else "Untitled Podcast"
        created_at = podcast_data[2] if column_count > 2 else None
        audio_url = podcast_data[3] if column_count > 3 and "audio_url" in select_columns else None
        transcript_text = podcast_data[4] if column_count > 4 and has_transcript else None
        
        # Set podcast summary
        podcast_summary = "Summary not available."
        
        # Try to generate summary if transcript is available
        if has_transcript and transcript_text and transcript_text.strip():
            try:
                ai_model = get_ai_model(model_name="gpt-4o-mini")
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
        else:
            podcast_summary = "Listen to the latest AI and Machine Learning insights from our podcast series."

        # Create better formatted podcast section with properly sized image
        # Use HTML img tag with direct width/height attributes instead of markdown attributes
        image_markdown = "<img src=\"/static/img/trend_daily_briefing_square.gif\" alt=\"Podcast Briefing\" width=\"400\" height=\"400\">\n\n"
        
        result = image_markdown
        # Handle created_at date formatting - it could be a string or datetime
        if created_at:
            try:
                if isinstance(created_at, str):
                    # Try to parse the string date
                    from datetime import datetime
                    # Try common formats
                    for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                        try:
                            date_obj = datetime.strptime(created_at, fmt)
                            date_str = date_obj.strftime('%Y-%m-%d')
                            break
                        except ValueError:
                            continue
                    else:
                        # If none of the formats match
                        date_str = created_at  # Use the original string
                else:
                    # It's already a datetime object
                    date_str = created_at.strftime('%Y-%m-%d')
            except Exception as e:
                logger.warning(f"Error formatting podcast date: {str(e)}")
                date_str = "Recent"
        else:
            date_str = "Recent"
        
        # Format podcast summary if available
        if audio_url:
            # Format as proper markdown with clickable button
            result += f"## Latest Podcast: {title}\n\n"
            result += f"**Published:** {date_str}\n\n"
            result += f"[**🎧 Listen Now**]({audio_url})\n\n"
            result += f"**Summary:** {podcast_summary}\n\n"
        else:
            # No audio URL available
            result += f"## Latest Podcast: {title}\n\n"
            result += f"**Published:** {date_str}\n\n"
            result += f"**Summary:** {podcast_summary}\n\n"
            result += f"_Link not available_\n\n"
        
        return result

    def _create_podcast_summary_prompt(self, podcast_title: str, transcript: str) -> str:
        """Create prompt for summarizing a podcast transcript."""
        # Take first N characters of transcript to avoid overly long prompts
        transcript_snippet = transcript[:3000] 
        
        # Get custom prompt from database or use default
        prompt_template = self._get_prompt_template("latest_podcast")
        
        return self._format_prompt(prompt_template, {
            "topic": podcast_title,  # Use podcast title as topic
            "podcast_title": podcast_title,
            "transcript": transcript_snippet
        })

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

    def _get_prompt_template(self, content_type_id: str) -> str:
        """
        Get prompt template for a content type from the database.
        
        If not found, returns a default prompt template.
        
        Args:
            content_type_id: The content type identifier
            
        Returns:
            str: The prompt template
        """
        prompt_data = self.db.get_newsletter_prompt(content_type_id)
        if prompt_data and prompt_data.get("prompt_template"):
            return prompt_data.get("prompt_template")
        
        # If not found in database, fall back to default templates
        if content_type_id == "topic_summary":
            return self._create_summary_prompt_template()
        elif content_type_id == "trend_analysis":
            return self._create_trend_analysis_prompt_template()
        elif content_type_id == "article_insights":
            return self._create_insights_prompt_template()
        elif content_type_id == "key_articles":
            return (
                "Article Title: \"{article_title}\"\n"
                "Article Summary: \"{article_summary}\"\n\n"
                "Based on the title and summary above, provide a single, concise sentence (max 25 words) explaining to a busy decision maker why this specific article merits their attention. Focus on its key insight, implication, or relevance for strategic thinking."
            )
        elif content_type_id == "ethical_societal_impact":
            return self._create_ethical_societal_impact_prompt_template()
        elif content_type_id == "business_impact":
            return self._create_business_impact_prompt_template()
        elif content_type_id == "market_impact":
            return self._create_market_impact_prompt_template()
        else:
            return f"Generate content about {content_type_id} for topic {{topic}}."

    def _format_prompt(self, template: str, variables: dict) -> str:
        """
        Format a prompt template by replacing variables.
        
        Args:
            template: The prompt template with {variable_name} placeholders
            variables: Dictionary of variable values
            
        Returns:
            str: The formatted prompt
        """
        try:
            return template.format(**variables)
        except KeyError as e:
            logger.warning(f"Missing variable in prompt template: {e}")
            # Replace missing variables with placeholders so the template doesn't fail
            formatted = template
            for key, value in variables.items():
                if f"{{{key}}}" in formatted:
                    formatted = formatted.replace(f"{{{key}}}", str(value))
            return formatted
        except Exception as e:
            logger.error(f"Error formatting prompt template: {str(e)}")
            # Return the template with basic topic substitution as a fallback
            topic = variables.get("topic", "the selected topic")
            return template.replace("{topic}", topic)

    def _create_summary_prompt_template(self) -> str:
        """Get default prompt template for topic summary generation."""
        return (
            "You are an AI assistant analyzing articles about '{topic}' for a busy decision-maker.\n"
            "Write a concise, structured summary based on the provided articles. Focus on the most critical information. Use bullet points for lists.\n"
            "Do not reference article numbers in your output.\n\n"
            "Use the following format:\n\n"
            "**Summary of {topic}**\n"
            "- Provide a brief (2-3 sentences) high-level overview of the current state of '{topic}'.\n"
            "- For EVERY fact or assertion, include a proper citation using this format: **[Article Title](Article URI)**\n"
            "- Each citation must be on its own line, not inline with text.\n"
            "- Ensure your overview is directly based on the articles provided, not general knowledge.\n\n"
            "**Top Three Developments**\n"
            "- Development 1: [Briefly state the development].\n  **Why this is need-to-know:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n"
            "- Development 2: [Briefly state the development].\n  **Why this is need-to-know:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n"
            "- Development 3: [Briefly state the development].\n  **Why this is need-to-know:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n\n"
            "**Top 3 Industry Trends**\n"
            "- Trend 1: [Briefly state the trend].\n  **Why this is interesting:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n"
            "- Trend 2: [Briefly state the trend].\n  **Why this is interesting:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n"
            "- Trend 3: [Briefly state the trend].\n  **Why this is interesting:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n\n"
            "**Strategic Takeaways for Decision Makers:**\n"
            "- Provide 2-3 high-level strategic implications or actionable insights derived from the above points that a decision maker should consider.\n\n"
            "Important: Always use the exact article titles and URIs from the data. Be very concise and focus on impact.\n"
            "Each section MUST include proper citation links to the original articles. DO NOT skip adding links.\n"
            "PUT LINKS ON THEIR OWN LINES - this is critical for rendering.\n\n"
            "Articles for analysis:\n{article_data}"
        )

    def _create_trend_analysis_prompt_template(self) -> str:
        """Get the default template for trend analysis prompt."""
        return (
            "Analyze the following trend data for '{topic}'. "
            "Provide a concise, structured analysis of trends and patterns, noting emerging themes and developments based on these data patterns.\n\n"
            "**Overall Trend Data for {topic}:**\n"
            "- Categories Distribution: {categories_str}\n"
            "- Sentiment Distribution: {sentiments_str}\n"
            "- Future Signal Distribution: {signals_str}\n"
            "- Time to Impact Distribution: {tti_str}\n"
            "- Top Tags (up to 10 with counts): {tags_str}\n\n"
            "**Analysis & Insights:**\n"
            "Begin with a 1-2 sentence overview of the general sentiment and activity level for '{topic}'.\n"
            "Then, for each of the following aspects, provide 2-3 bullet points highlighting key patterns, shifts, or noteworthy observations. If an observation is particularly illustrated by a specific article, cite it using **[Article Title](Article URI)** from the reference list below. Put each citation on its own line for proper rendering:\n"
            "  - **Category Insights:** (e.g., Dominant categories, significant shifts in category focus, surprising under/over-representation).\n"
            "    *Observation 1... \n"
            "    Cite if applicable.*\n"
            "    *Observation 2... \n"
            "    Cite if applicable.*\n"
            "  - **Sentiment Insights:** (e.g., Predominant sentiment, changes over time if inferable, sentiment drivers).\n"
            "    *Observation 1... \n"
            "    Cite if applicable.*\n"
            "    *Observation 2... \n"
            "    Cite if applicable.*\n"
            "  - **Future Outlook (Signals & TTI):** (e.g., Implications of future signals, common TTI, alignment or divergence between signals and TTI).\n"
            "    *Observation 1... \n"
            "    Cite if applicable.*\n"
            "    *Observation 2... \n"
            "    Cite if applicable.*\n"
            "  - **Key Tag Themes:** (e.g., Dominant tags and what they signify, clusters of related tags appearing frequently).\n"
            "    *Observation 1... \n"
            "    Cite if applicable.*\n"
            "    *Observation 2... \n"
            "    Cite if applicable.*\n\n"
            "Conclude with a 2-3 sentence synthesis on any connections between these different distributions or overall strategic insights valuable for decision-making.\n\n"
            "Reference Articles (for citation purposes only if applicable to the data patterns observed):\n{article_data_str}"
            "Be specific and data-driven. Avoid generic statements."
        )

    def _create_insights_prompt_template(self) -> str:
        """Get the default template for article insights prompt."""
        return (
            "Identify 3-5 major themes from the articles about \"{topic}\". For each theme:\n"
            "- Provide a theme title\n"
            "- Write a 1-2 sentence summary of the theme\n"
            "- List the relevant articles for the theme, each with:\n"
            "    - title\n"
            "    - url\n"
            "    - news source\n"
            "    - publication date\n"
            "    - a 1-2 sentence summary\n"
            "\n"
            "Do not reference article numbers. Do not mention 'Article X'.\n"
            "\n"
            "Format your response as a JSON list of themes, each with:\n"
            "- theme_name\n"
            "- theme_summary\n"
            "- articles: list of dicts with title, uri, news_source, publication_date, short_summary\n"
            "\n"
            "Articles:\n{article_data}"
        )

    def _create_ethical_societal_impact_prompt_template(self) -> str:
        """Get the default template for ethical and societal impact prompt."""
        return (
            "Analyze the ethical and societal impacts related to '{topic}' based on the following articles.\n"
            "Provide a concise analysis (2-3 paragraphs) highlighting key ethical dilemmas, societal consequences, and considerations. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**.\n\n"
            "Articles for analysis:\n{article_data}"
        )

    def _create_business_impact_prompt_template(self) -> str:
        """Get the default template for business impact prompt."""
        return (
            "Analyze the business impacts and opportunities related to '{topic}' based on the following articles.\n"
            "Provide a concise analysis (2-3 paragraphs) highlighting key business implications, potential opportunities, disruptions, and strategic considerations for businesses. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**.\n\n"
            "Articles for analysis:\n{article_data}"
        )

    def _create_market_impact_prompt_template(self) -> str:
        """Get the default template for market impact prompt."""
        return (
            "Analyze the market impacts, trends, and competitive landscape related to '{topic}' based on the following articles.\n"
            "Provide a concise analysis (2-3 paragraphs) highlighting key market trends, competitive dynamics, potential market shifts, and implications for market positioning. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**.\n\n"
            "Articles for analysis:\n{article_data}"
        )

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
        
        # Get custom prompt from database or use default
        prompt_template = self._get_prompt_template("ethical_societal_impact")
        prompt = self._format_prompt(prompt_template, {
            "topic": topic,
            "article_data": article_data
        })
        
        ai_model = get_ai_model(model_name="gpt-4o-mini")
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

    async def _generate_business_impact_section(self, topic: str, start_date: datetime.date, end_date: datetime.date) -> Optional[str]:
        articles = self._fetch_articles(topic, start_date, end_date, limit=15)
        if not articles:
            return "No articles found for Business Impact analysis."
        article_data = self._prepare_articles_data(articles)
        
        # Get custom prompt from database or use default
        prompt_template = self._get_prompt_template("business_impact")
        prompt = self._format_prompt(prompt_template, {
            "topic": topic,
            "article_data": article_data
        })
        
        ai_model = get_ai_model(model_name="gpt-4o-mini")
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

    async def _generate_market_impact_section(self, topic: str, start_date: datetime.date, end_date: datetime.date) -> Optional[str]:
        articles = self._fetch_articles(topic, start_date, end_date, limit=15)
        if not articles:
            return "No articles found for Market Impact analysis."
        article_data = self._prepare_articles_data(articles)
        
        # Get custom prompt from database or use default
        prompt_template = self._get_prompt_template("market_impact")
        prompt = self._format_prompt(prompt_template, {
            "topic": topic,
            "article_data": article_data
        })
        
        ai_model = get_ai_model(model_name="gpt-4o-mini")
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


# Factory function for dependency injection
def get_newsletter_service(db: Database = None) -> NewsletterService:
    """Get or create a NewsletterService instance."""
    return NewsletterService(db) 