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

    async def _get_articles_for_topics(
        self, 
        topics: List[str], 
        start_date: Optional[datetime.date] = None, 
        end_date: Optional[datetime.date] = None
    ) -> Dict[str, List[Dict]]:
        """
        Fetch articles for multiple topics.
        
        Args:
            topics: List of topics to fetch articles for
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Dictionary mapping topics to lists of articles
        """
        # Ensure dates are properly set
        start_date, end_date = self._calculate_date_range(
            "weekly",  # Default frequency for date calculation
            start_date, 
            end_date
        )
        
        self.report_progress(None, "Fetching articles", f"Finding articles for {len(topics)} topics")
        
        # Fetch articles for each topic
        article_data = {}
        for i, topic in enumerate(topics):
            self.report_progress(
                None,  # Keep the current progress percentage
                "Fetching articles", 
                f"Finding articles for {topic} ({i+1}/{len(topics)})"
            )
            article_data[topic] = self._fetch_articles(topic, start_date, end_date)
            
        return article_data
        
    async def _process_content_type(
        self,
        content_type: str,
        prompt_template: str,
        request: NewsletterRequest,
        article_data: Dict[str, List[Dict]]
    ) -> str:
        """
        Process a specific content type to generate newsletter content.
        
        Args:
            content_type: The content type to process
            prompt_template: The prompt template for this content type
            request: The newsletter request
            article_data: Dictionary of articles by topic
            
        Returns:
            Markdown content for this section
        """
        try:
            # Special handling for different content types
            if content_type == "key_charts":
                # For key charts, generate visualizations
                return await self._generate_charts_section(request.topics, article_data)
            
            # For regular content types that require prompt-based generation
            if not prompt_template:
                # Use default prompt if none is available
                prompt_template = self._get_default_prompt(content_type)
            
            # Fill in the prompt template with the required data
            prompt = self._fill_prompt_template(
                prompt_template,
                request,
                article_data,
                content_type
            )
            
            # Generate the content using AI
            ai_response = await self._generate_content_with_ai(prompt, request.ai_model)
            
            return ai_response.strip()
            
        except Exception as e:
            logger.error(f"Error processing content type {content_type}: {str(e)}")
            return f"## Error in {content_type}\n\nAn error occurred while generating this section: {str(e)}"
            
    def _fill_prompt_template(
        self,
        template: str,
        request: NewsletterRequest,
        article_data: Dict[str, List[Dict]],
        content_type: str
    ) -> str:
        """Fill a prompt template with values from the request and article data."""
        # Start by setting prompt to template
        prompt = template
        
        # Get content instructions for this content type
        content_instructions = self._get_content_type_instructions(content_type)
        
        replacements_made = False
        
        # For topic-specific content, use only articles for that topic
        if "{{topic}}" in template and request.topics:
            # This is a topic-specific template that will be used in a loop for each topic
            # We'll just ensure the template has the {{article_data}} placeholder
            topic = request.topics[0]  # Just get first topic for checking replacements
            articles_list = article_data.get(topic, [])
            articles_str = self._prepare_articles_data(articles_list)
        else:
            # For non-topic specific content, use all articles
            # Combine all articles from all topics
            all_articles = []
            for articles in article_data.values():
                all_articles.extend(articles)
            articles_list = all_articles
            articles_str = self._prepare_articles_data(articles_list)
        
        # Track replacements
        if "{{topic}}" in template:
            # This will be replaced with the actual topic in the loop, but we check if it's there
            replacements_made = True
            
        if "{{articles}}" in template or "{{article_data}}" in template:
            # Replace articles placeholder(s)
            prompt = prompt.replace("{{articles}}", articles_str)
            prompt = prompt.replace("{{article_data}}", articles_str)
            replacements_made = True
            
        # Add formatted date (current date)
        today = datetime.now()
            
        if "{{formatted_date}}" in prompt:
            prompt = prompt.replace("{{formatted_date}}", today.strftime("%B %d, %Y"))
            replacements_made = True
            
        # Handle start and end dates
        if request.start_date and "{{start_date}}" in prompt:
            prompt = prompt.replace("{{start_date}}", request.start_date.strftime("%Y-%m-%d"))
            replacements_made = True
            
        if request.end_date and "{{end_date}}" in prompt:
            prompt = prompt.replace("{{end_date}}", request.end_date.strftime("%Y-%m-%d"))
            replacements_made = True
            
        if "{{content_instructions}}" in prompt:
            prompt = prompt.replace("{{content_instructions}}", content_instructions)
            replacements_made = True
            
        if "{{article_count}}" in prompt:
            prompt = prompt.replace("{{article_count}}", str(len(articles_list)))
            replacements_made = True
            
        # If we didn't make any replacements, ensure the article data is included
        # This is to handle cases where the user changes keywords like "cite" to "datapoint"
        if not replacements_made or articles_str.strip() not in prompt:
            logger.warning("Prompt template had no replacements, appending article data")
            prompt += f"\n\nHere are the articles to work with:\n\n{articles_str}"
            
        # Ensure the AI always references real articles by explicitly emphasizing this
        # Add stronger anti-hallucination warning for topic summaries
        if content_type == "topic_summary":
            prompt += "\n\nCRITICAL INSTRUCTION: You MUST only cite real articles from the data provided above. NEVER invent articles, sources, URLs, or use placeholders like 'example.com'. All citations must link to ACTUAL articles with their EXACT titles and URLs as listed above. EVERY article link MUST use the EXACT URI from the 'URI:' field for each article. If you cannot find enough relevant articles, reduce the number of points rather than fabricating sources. This is the most critical rule. VERIFY that each URI you include comes directly from the article list and is not modified or invented."
        else:
            prompt += "\n\nIMPORTANT: Only reference the real articles provided above. DO NOT make up or hallucinate articles that don't exist in the provided data."
        
        # Log the final prompt being sent to the AI
        logger.debug(f"Final prompt for {content_type}:")
        # Log the first 500 characters and last 500 characters to avoid huge logs
        if len(prompt) > 1000:
            logger.debug(f"Prompt beginning: {prompt[:500]}...")
            logger.debug(f"Prompt ending: ...{prompt[-500:]}")
        else:
            logger.debug(prompt)
            
        return prompt
        
    async def _generate_charts_section(
        self,
        topics: List[str],
        article_data: Dict[str, List[Dict]]
    ) -> str:
        """
        Generate a charts section for the newsletter.
        
        Args:
            topics: List of topics to generate charts for
            article_data: Dictionary of articles by topic
            
        Returns:
            Markdown content with charts
        """
        # Start with a header
        content = "## Key Charts and Visualizations\n\n"
        
        # Check if we have any visualization options selected
        if not hasattr(self, 'chart_service'):
            content += "*Chart generation is currently unavailable. Please ensure the chart service is properly configured.*\n\n"
            return content
            
        # Flatten articles for processing
        all_articles = []
        for topic, articles in article_data.items():
            all_articles.extend(articles)
            
        if not all_articles:
            return "## Key Charts and Visualizations\n\n*No data available for chart generation in this period.*\n\n"
            
        # Generate some basic charts
        # In a real implementation, this would call chart generation services
        # Here we're just creating placeholder content
        content += "### Sentiment Analysis Over Time\n\n"
        content += "*This chart shows sentiment trends for the selected topics over the reporting period.*\n\n"
        content += "![Sentiment Analysis Over Time](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==)\n\n"
        
        content += "### Topic Distribution\n\n"
        content += "*This chart shows the distribution of content across different subtopics.*\n\n"
        content += "![Topic Distribution](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==)\n\n"
        
        return content
        
    def _get_default_prompt(self, content_type: str) -> str:
        """
        Get a default prompt template for a content type if none is available.
        
        Args:
            content_type: The content type to get a prompt template for
            
        Returns:
            Default prompt template
        """
        # Map content types to default prompt templates
        default_prompts = {
            "topic_summary": self._create_summary_prompt_template(),
            "trend_analysis": self._create_trend_analysis_prompt_template(),
            "article_insights": self._create_insights_prompt_template(),
            "ethical_societal_impact": self._create_ethical_societal_impact_prompt_template(),
            "business_impact": self._create_business_impact_prompt_template(),
            "market_impact": self._create_market_impact_prompt_template(),
        }
        
        # Return the default prompt or a generic one if not found
        return default_prompts.get(content_type, """
        Generate content for {{topics}} for a {{frequency}} newsletter.
        
        Here are the articles to use as source material:
        
        {{articles}}
        
        {{content_instructions}}
        """)
        
    def _get_content_type_instructions(self, content_type: str) -> str:
        """
        Get special instructions for a content type.
        
        Args:
            content_type: The content type to get instructions for
            
        Returns:
            Instructions for the content type
        """
        # Map content types to special instructions
        instructions = {
            "topic_summary": "Provide a comprehensive summary of recent developments in these topics. Identify key trends and important events. Cite specific articles using [Article X] format.",
            "trend_analysis": "Analyze emerging trends and patterns across the articles. Identify shifts in sentiment, adoption rates, or industry focus. Support your analysis with citations to specific articles.",
            "article_insights": "Group articles into meaningful themes or subtopics. For each theme, highlight the most important insights and what they collectively tell us about this area.",
            "key_articles": "Identify the 5-7 most important articles and explain why each one is significant. Include the title, source, and a brief explanation of why each article merits attention.",
            "ethical_societal_impact": "Analyze the ethical considerations and societal implications of developments in these topics. Consider impacts on different communities and potential ethical concerns.",
            "business_impact": "Assess the business opportunities, threats, and strategic considerations that emerge from these articles. Focus on actionable insights for business planning.",
            "market_impact": "Analyze how these developments are affecting market dynamics, competitive positioning, and industry structures. Identify market shifts and their implications.",
        }
        
        # Return the instructions or a generic one if not found
        return instructions.get(content_type, "Generate informative content based on the provided articles. Use citations to reference specific articles.")
        
    async def _generate_content_with_ai(self, prompt: str, model_name: str) -> str:
        """
        Generate content using an AI model.
        
        Args:
            prompt: The prompt to send to the AI
            model_name: The AI model to use
            
        Returns:
            Generated content
        """
        try:
            # In a real implementation, this would use the appropriate AI client
            # from app.services.ai_service import get_ai_model
            # ai_model = get_ai_model(model_name)
            
            # For now, we'll return a placeholder message
            sample_content = f"""## Generated Content
            
This is a placeholder for AI-generated content. In a real implementation, this would be generated using the {model_name} model.

The content would be based on the provided articles and would follow the specified format for the content type.

### Key Points:
- Point 1 from the articles
- Point 2 from the articles
- Point 3 from the articles

### References:
- [Article 1] Sample article title
- [Article 3] Another relevant article
            """
            
            return sample_content
            
        except Exception as e:
            logger.error(f"Error generating content with AI: {str(e)}")
            return f"*Error generating content: {str(e)}*"

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
        """Generate a summary of a topic based on recent articles."""
        
        # Get articles for the topic
        articles = self._fetch_articles(topic, start_date, end_date)
        
        if not articles:
            return f"No articles found for topic '{topic}' in the selected date range."
        
        # Prepare articles data for the LLM
        article_data = self._prepare_articles_data(articles)
        
        # Generate summary using AI model
        ai_model = get_ai_model(model_name="gpt-4o-mini")
        
        # Get the prompt template
        prompt_template = self._get_prompt_template("topic_summary")
        
        # Create a mock request for template filling
        mock_request = NewsletterRequest(
            topics=[topic],
            content_types=["topic_summary"],
            start_date=start_date,
            end_date=end_date,
            frequency="N/A"  # Not needed for topic summary
        )
        
        # Create a dictionary with articles for the topic
        article_dict = {topic: articles}
        
        # Use the proper template filling method that handles double braces
        prompt = self._fill_prompt_template(
            prompt_template,
            mock_request,
            article_dict,
            "topic_summary"
        )

        # Log that we're sending the prompt to the AI model
        logger.info(f"Sending topic summary prompt to AI model for topic '{topic}'")
        
        try:
            response = await ai_model.generate(prompt)
            # Extract content from response - handle different response structures
            if hasattr(response, 'choices') and response.choices:
                # Handle OpenAI-like response format
                if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                    return self._clean_response_content(response.choices[0].message.content)
                elif hasattr(response.choices[0], 'text'):
                    return self._clean_response_content(response.choices[0].text)
            # Try direct access for simpler response structures
            elif hasattr(response, 'content'):
                return self._clean_response_content(response.content)
            elif isinstance(response, str):
                return self._clean_response_content(response)
            else:
                # Fallback - attempt to convert to string
                return self._clean_response_content(str(response))
        except Exception as e:
            logger.error(f"Error generating summary for topic '{topic}': {str(e)}")
            return f"Error generating summary: {str(e)}"
            
    def _clean_response_content(self, content: str) -> str:
        """
        Clean up the response content to remove artifacts and formatting issues.
        """
        if not content:
            return ""
            
        # Remove raw API response format markers if present
        if content.startswith("Choices(") or "Message(content=" in content:
            try:
                # Try to extract just the actual content
                import re
                
                # First try to extract content from the full structure format:
                # Choices(finish_reason='stop', index=0, message=Message(content="..."))
                match = re.search(r'message=Message\(content=["\'](.*?)["\'](?:,\s*\w+=[^)]*)*\)', content, re.DOTALL)
                if match:
                    content = match.group(1)
                else:
                    # Try more general pattern for content attribute
                    match = re.search(r'content=["\'](.*?)["\'](?:,|\))', content, re.DOTALL)
                    if match:
                        content = match.group(1)
                    else:
                        # Try extracting just what's between triple quotes if present
                        match = re.search(r'"""(.*?)"""', content, re.DOTALL)
                        if match:
                            content = match.group(1)
                        else:
                            # If we can't extract it cleanly with above methods, just strip common wrappers
                            content = re.sub(r'^Choices\(.*?message=Message\(content=["\']', '', content, flags=re.DOTALL)
                            content = re.sub(r'["\'],.*$', '', content, flags=re.DOTALL)
            except Exception as e:
                logger.warning(f"Error cleaning response content: {str(e)}")
                # Just return it as is if we can't clean it
                pass
                
        # Unescape any escaped quotes or newlines
        content = content.replace('\\"', '"').replace('\\n', '\n')
        
        # Handle any HTML-escaped characters
        content = content.replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>')
        
        return content.strip()

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
        
        # Extract trend data from articles
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
        
        # Get prompt template
        prompt_template = self._get_prompt_template("trend_analysis")
        
        # Fill template with variables
        variables = {
            "topic": topic,
            "categories_str": categories_str,
            "sentiments_str": sentiments_str,
            "signals_str": signals_str,
            "tti_str": tti_str,
            "tags_str": tags_str,
            "article_data_str": articles_for_citation_prompt_str
        }
        
        prompt = self._format_prompt(prompt_template, variables)
        
        try:
            ai_model = get_ai_model(model_name="gpt-4o-mini")
            response = await ai_model.generate(prompt)
            # Extract content from response object
            if hasattr(response, 'choices') and response.choices:
                if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                    return self._clean_response_content(response.choices[0].message.content)
                elif hasattr(response.choices[0], 'text'):
                    return self._clean_response_content(response.choices[0].text)
            elif hasattr(response, 'message') and hasattr(response.message, 'content'):
                return self._clean_response_content(response.message.content)
            elif hasattr(response, 'content'):
                return self._clean_response_content(response.content)
            else:
                return self._clean_response_content(str(response))
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
            url = article.get("uri", "#")
            source = article.get("news_source", "Unknown Source")
            
            # Format publication date nicely
            pub_date = article.get("publication_date", "Unknown date")
            if pub_date and not isinstance(pub_date, str):
                pub_date = pub_date.strftime("%Y-%m-%d") if hasattr(pub_date, "strftime") else str(pub_date)
            
            summary = article.get("summary", "No summary available.")
            tags = article.get("tags", [])
            tag_str = ", ".join(tags) if tags else ""
            
            # Generate why this article merits attention
            why_merits_attention = "Analysis of importance pending."
            
            if summary != "No summary available.":
                try:
                    attention_prompt = self._create_why_merits_attention_prompt(title, summary)
                    response = await ai_model.generate(attention_prompt)
                    if hasattr(response, 'choices') and response.choices:
                        if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                            why_merits_attention = self._clean_response_content(response.choices[0].message.content)
                        elif hasattr(response.choices[0], 'text'):
                            why_merits_attention = self._clean_response_content(response.choices[0].text)
                    elif hasattr(response, 'message') and hasattr(response.message, 'content'):
                        why_merits_attention = self._clean_response_content(response.message.content)
                    elif hasattr(response, 'content'):
                        why_merits_attention = self._clean_response_content(response.content)
                    else:
                        why_merits_attention = self._clean_response_content(str(response))
                except Exception as e:
                    logger.error(f"Error generating 'why merits attention' for '{title}': {str(e)}", exc_info=True)
                    why_merits_attention = "Could not generate importance analysis."
            else:
                why_merits_attention = "Full summary not available to determine specific importance."

            # Use proper markdown formatting with the requested template:
            # ### [title](url)
            result += f"### [{title}]({url})\n\n"
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

        # Try to find podcasts in database, but handle gracefully if the table doesn't exist
        # or has different columns
        try:
            cursor = self.db.get_connection().cursor()
            # Get column info first to build a query that will work
            cursor.execute("PRAGMA table_info(podcasts)")
            table_info = cursor.fetchall()
            column_names = [col[1] for col in table_info]  # Column name is at index 1
            
            # Build a query that works with the available columns
            has_transcript = 'transcript_text' in column_names
            has_topic = 'topic' in column_names
            has_audio_url = 'audio_url' in column_names
            
            # Build list of columns to select based on what's available
            select_columns = ['id']
            if 'title' in column_names:
                select_columns.append('title')
            else:
                select_columns.append("'Untitled Podcast' as title")
                
            if 'created_at' in column_names:
                select_columns.append('created_at')
            else:
                select_columns.append('NULL as created_at')
                
            if has_audio_url:
                select_columns.append('audio_url')
                
            if has_transcript:
                select_columns.append('transcript_text')
                
            # Build query
            query = f"SELECT {', '.join(select_columns)} FROM podcasts "
            
            # Add WHERE clause if we can filter by topic
            params = []
            if has_topic:
                query += "WHERE topic = ? OR topic IS NULL OR topic = 'General' "
                params.append(topic)
            
            # Add ORDER BY and LIMIT
            query += "ORDER BY created_at DESC LIMIT 1"
            
            # Execute query
            cursor.execute(query, params)
            podcast_data = cursor.fetchone()
            
        except Exception as e:
            logger.error(f"Error fetching podcast data: {str(e)}")
            # Continue with default data if podcast fetching fails
        
        if not podcast_data:
            return "No podcast episodes found."
            
        # Unpack data based on which columns we selected
        column_count = len(select_columns)
        podcast_id = podcast_data[0] if column_count > 0 else None
        title = podcast_data[1] if column_count > 1 else "Untitled Podcast"
        created_at = podcast_data[2] if column_count > 2 else None
        audio_url = podcast_data[3] if column_count > 3 and "audio_url" in select_columns else None
        transcript_text = podcast_data[4] if column_count > 4 and has_transcript else None
        
        # Set podcast summary
        podcast_summary = "Summary not available."
        
        # Generate summary if we have transcript text
        if transcript_text:
            try:
                ai_model = get_ai_model(model_name="gpt-4o-mini")
                summary_prompt = self._create_podcast_summary_prompt(title, transcript_text)
                response = await ai_model.generate(summary_prompt)
                if hasattr(response, 'choices') and response.choices:
                    if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                        podcast_summary = self._clean_response_content(response.choices[0].message.content)
                    elif hasattr(response.choices[0], 'text'):
                        podcast_summary = self._clean_response_content(response.choices[0].text)
                elif hasattr(response, 'message') and hasattr(response.message, 'content'):
                    podcast_summary = self._clean_response_content(response.message.content)
                else:
                    podcast_summary = self._clean_response_content(str(response))
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
        date_str = "Recent"
        if created_at:
            if isinstance(created_at, str):
                try:
                    # Try parsing string to datetime
                    from datetime import datetime
                    # Try common formats
                    for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                        try:
                            date_obj = datetime.strptime(created_at, fmt)
                            date_str = date_obj.strftime('%Y-%m-%d')
                            break
                        except ValueError:
                            continue
                except Exception:
                    # If parsing fails, use the string as is
                    date_str = created_at
            else:
                # Use datetime object if it's not a string
                date_str = created_at.strftime('%Y-%m-%d') if hasattr(created_at, 'strftime') else str(created_at)
                
        # Format podcast info
        result += f"## {title}\n\n"
        
        if audio_url:
            result += f"**Listen:** [Click here to listen]({audio_url})\n\n"
            result += f"**Published:** {date_str}\n\n"
            result += f"**Summary:** {podcast_summary}\n\n"
        else:
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
        Fetch articles for a given topic and date range.
        
        Args:
            topic: Topic to fetch articles for
            start_date: Start date
            end_date: End date
            limit: Optional limit on number of articles
            
        Returns:
            List of article dictionaries
        """
        logger.info(f"Fetching articles for topic '{topic}' from {start_date} to {end_date}")
        
        try:
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
            
            if not result:
                logger.warning(f"No articles found for topic '{topic}' in the date range {start_date} to {end_date}")
            else:
                logger.info(f"Found {len(result)} articles for topic '{topic}'")
                
            return result
            
        except Exception as e:
            logger.error(f"Error fetching articles for topic '{topic}': {str(e)}", exc_info=True)
            return []

    def _prepare_articles_data(self, articles: List[Dict]) -> str:
        """
        Prepare articles data for use in AI prompts.
        
        Args:
            articles: List of article dictionaries
            
        Returns:
            str: Formatted article data as text
        """
        result = ""
        
        logger.info(f"Preparing data for {len(articles)} articles")
        
        if not articles:
            logger.warning("No articles provided for content generation - this will likely cause hallucination")
            return "NO ARTICLES FOUND FOR THIS TOPIC AND TIME PERIOD. DO NOT MAKE UP ARTICLES OR SOURCES."
        
        for i, article in enumerate(articles, 1):
            title = article.get("title", "Untitled")
            source = article.get("news_source", "Unknown source")
            pub_date = article.get("publication_date", "Unknown date")
            summary = article.get("summary", "No summary available.")
            uri = article.get("uri", "")  # Get the URI/URL
            
            logger.info(f"Article {i}: '{title}' from {source} (URL: {uri})")
            
            result += f"--- Article {i} ---\n"
            result += f"Title: {title}\n"
            result += f"Source: {source}\n"
            result += f"Date: {pub_date}\n"
            if uri:
                result += f"URI: {uri}\n"
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
        """Get the default template for summary prompt."""
        return (
            "Create a comprehensive, structured summary for the topic \"{{topic}}\".\n"
            "Focus on the most significant recent developments, trends, and implications.\n\n"
            "**Top Three Developments**\n"
            "- Development 1: [First key development]\n"
            "  **Why this is need-to-know:**\n"
            "  [1-2 sentences on business or strategic implications]\n"
            "  Cite: **[Article Title](Article URI)**\n\n"
            "- Development 2: [Second key development]...\n"
            "  **Why this is need-to-know:**\n"
            "  [1-2 sentences on business or strategic implications]\n"
            "  Cite: **[Article Title](Article URI)**\n\n"
            "- Development 3: [Third key development]...\n"
            "  **Why this is need-to-know:**\n"
            "  [1-2 sentences on business or strategic implications]\n"
            "  Cite: **[Article Title](Article URI)**\n\n"
            "**Top 3 Industry Trends**\n"
            "- Trend 1: [First major industry trend]\n"
            "  **Impact on the industry:**\n"
            "  [1-2 sentences explaining the impact]\n"
            "  Cite: **[Article Title](Article URI)**\n\n"
            "- Trend 2: [Second major industry trend]...\n"
            "  **Impact on the industry:**\n"
            "  [1-2 sentences explaining the impact]\n"
            "  Cite: **[Article Title](Article URI)**\n\n"
            "- Trend 3: [Third major industry trend]...\n"
            "  **Impact on the industry:**\n"
            "  [1-2 sentences explaining the impact]\n"
            "  Cite: **[Article Title](Article URI)**\n\n"
            "**Strategic Takeaways for Decision Makers**\n"
            "- Provide 2-3 high-level strategic implications or actionable insights derived from the above points that a decision maker should consider.\n"
            "- Each takeaway should be concise but insightful, focusing on what actions or strategic shifts might be warranted.\n"
            "- Include citations to relevant articles for each takeaway.\n\n"
            "**CRITICAL INSTRUCTIONS:**\n"
            "1. ONLY use information from the provided articles.\n"
            "2. NEVER create fake articles or URLs.\n"
            "3. NEVER use example.com or any other placeholder domains.\n"
            "4. EVERY citation MUST use the EXACT URI from the article data.\n"
            "5. If there are not enough articles for 3 developments/trends, only cover the ones you have real data for.\n"
            "6. DO NOT make up information, sources, statistics, or quotes that aren't in the provided articles.\n"
            "7. Check each URI you reference to ensure it matches exactly what's in the article data.\n"
            "8. If you cannot find three significant developments/trends in the articles, it is better to present fewer than to fabricate.\n\n"
            "Use {{article_data}} as your source material.\n"
        )

    def _create_trend_analysis_prompt_template(self) -> str:
        """Get the default template for trend analysis prompt."""
        return (
            "Analyze the following trend data for '{{topic}}'. "
            "Provide a concise, structured analysis of trends and patterns, noting emerging themes and developments based on these data patterns.\n\n"
            "**Overall Trend Data for {{topic}}:**\n"
            "- Categories Distribution: {{categories_str}}\n"
            "- Sentiment Distribution: {{sentiments_str}}\n"
            "- Future Signal Distribution: {{signals_str}}\n"
            "- Time to Impact Distribution: {{tti_str}}\n"
            "- Top Tags (up to 10 with counts): {{tags_str}}\n\n"
            "**Analysis & Insights:**\n"
            "Begin with a 1-2 sentence overview of the general sentiment and activity level for '{{topic}}'.\n"
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
            "Reference Articles (for citation purposes only if applicable to the data patterns observed):\n{{article_data_str}}"
            "Be specific and data-driven. Avoid generic statements."
        )

    def _create_insights_prompt_template(self) -> str:
        """Get the default template for article insights prompt."""
        return (
            "Identify 3-5 major themes from the articles about \"{{topic}}\". For each theme:\n"
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
            "Articles:\n{{article_data}}"
        )

    def _create_ethical_societal_impact_prompt_template(self) -> str:
        """Get the default template for ethical and societal impact prompt."""
        return (
            "Analyze the ethical and societal impacts related to '{{topic}}' based on the following articles.\n"
            "Provide a concise analysis (2-3 paragraphs) highlighting key ethical dilemmas, societal consequences, and considerations. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**.\n\n"
            "Articles for analysis:\n{{article_data}}"
        )

    def _create_business_impact_prompt_template(self) -> str:
        """Get the default template for business impact prompt."""
        return (
            "Analyze the business impacts and opportunities related to '{{topic}}' based on the following articles.\n"
            "Provide a concise analysis (2-3 paragraphs) highlighting key business implications, potential opportunities, disruptions, and strategic considerations for businesses. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**.\n\n"
            "Articles for analysis:\n{{article_data}}"
        )

    def _create_market_impact_prompt_template(self) -> str:
        """Get the default template for market impact prompt."""
        return (
            "Analyze the market impacts, trends, and competitive landscape related to '{{topic}}' based on the following articles.\n"
            "Provide a concise analysis (2-3 paragraphs) highlighting key market trends, competitive dynamics, potential market shifts, and implications for market positioning. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**.\n\n"
            "Articles for analysis:\n{{article_data}}"
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
        
        # Get prompt template and prepare article data
        prompt_template = self._get_prompt_template("ethical_societal_impact")
        article_data = self._prepare_articles_data(articles)
        
        # Fill prompt template
        variables = {
            "topic": topic,
            "article_data": article_data
        }
        prompt = self._format_prompt(prompt_template, variables)
        
        # Generate content
        ai_model = get_ai_model(model_name="gpt-4o-mini")
        try:
            response = await ai_model.generate(prompt)
            if hasattr(response, 'choices') and response.choices:
                if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                    return self._clean_response_content(response.choices[0].message.content)
                elif hasattr(response.choices[0], 'text'):
                    return self._clean_response_content(response.choices[0].text)
            elif hasattr(response, 'message') and hasattr(response.message, 'content'):
                return self._clean_response_content(response.message.content)
            elif hasattr(response, 'content'):
                return self._clean_response_content(response.content)
            return self._clean_response_content(str(response))
        except Exception as e:
            logger.error(f"Error generating ethical/societal impact section for '{topic}': {str(e)}", exc_info=True)
            return "Error generating ethical/societal impact section."

    async def _generate_business_impact_section(self, topic: str, start_date: datetime.date, end_date: datetime.date) -> Optional[str]:
        articles = self._fetch_articles(topic, start_date, end_date, limit=15)
        if not articles:
            return "No articles found for Business Impact analysis."
        
        # Get prompt template and prepare article data
        prompt_template = self._get_prompt_template("business_impact")
        article_data = self._prepare_articles_data(articles)
        
        # Fill prompt template
        variables = {
            "topic": topic,
            "article_data": article_data
        }
        prompt = self._format_prompt(prompt_template, variables)
        
        # Generate content
        ai_model = get_ai_model(model_name="gpt-4o-mini")
        try:
            response = await ai_model.generate(prompt)
            if hasattr(response, 'choices') and response.choices:
                if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                    return self._clean_response_content(response.choices[0].message.content)
                elif hasattr(response.choices[0], 'text'):
                    return self._clean_response_content(response.choices[0].text)
            elif hasattr(response, 'message') and hasattr(response.message, 'content'):
                return self._clean_response_content(response.message.content)
            elif hasattr(response, 'content'):
                return self._clean_response_content(response.content)
            return self._clean_response_content(str(response))
        except Exception as e:
            logger.error(f"Error generating business impact section for '{topic}': {str(e)}", exc_info=True)
            return "Error generating business impact section."

    async def _generate_market_impact_section(self, topic: str, start_date: datetime.date, end_date: datetime.date) -> Optional[str]:
        articles = self._fetch_articles(topic, start_date, end_date, limit=15)
        if not articles:
            return "No articles found for Market Impact analysis."
        
        # Get prompt template and prepare article data
        prompt_template = self._get_prompt_template("market_impact")
        article_data = self._prepare_articles_data(articles)
        
        # Fill prompt template
        variables = {
            "topic": topic,
            "article_data": article_data
        }
        prompt = self._format_prompt(prompt_template, variables)
        
        # Generate content
        ai_model = get_ai_model(model_name="gpt-4o-mini")
        try:
            response = await ai_model.generate(prompt)
            if hasattr(response, 'choices') and response.choices:
                if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                    return self._clean_response_content(response.choices[0].message.content)
                elif hasattr(response.choices[0], 'text'):
                    return self._clean_response_content(response.choices[0].text)
            elif hasattr(response, 'message') and hasattr(response.message, 'content'):
                return self._clean_response_content(response.message.content)
            elif hasattr(response, 'content'):
                return self._clean_response_content(response.content)
            return self._clean_response_content(str(response))
        except Exception as e:
            logger.error(f"Error generating market impact section for '{topic}': {str(e)}", exc_info=True)
            return "Error generating market impact section."


# Factory function for dependency injection
def get_newsletter_service(db: Database = None) -> NewsletterService:
    """Get or create a NewsletterService instance."""
    return NewsletterService(db) 