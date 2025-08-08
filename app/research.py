from typing import Any, Dict
from urllib.parse import urlparse
import logging
import os
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.env_loader import load_environment, ensure_model_env_vars
from app.analyzers.article_analyzer import ArticleAnalyzer
from dotenv import load_dotenv
from app.database_query_facade import DatabaseQueryFacade

# Add import for the collector factory
from app.collectors.collector_factory import CollectorFactory

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class Research:
    DEFAULT_TOPIC = "AI and Machine Learning"

    def __init__(self, db, model_name=None):
        try:
            logger.debug(f"Initializing Research with DB type: {type(db).__name__}")
            
            # Ensure db exposes necessary methods
            
            if isinstance(db, Session):
                logger.debug("Converting Session to Database")
                from app.database import Database
                self.db = Database()
                self.session = db
            elif hasattr(db, 'get_connection'):  # Check for the main required method
                logger.debug("Using provided Database instance")
                self.db = db
                self.session = None
            else:
                logger.error(f"Invalid database instance. Missing required methods.")
                raise TypeError("Database instance must implement required methods")
                
            self.current_topic = self.DEFAULT_TOPIC
            self.topic_configs = {}
            self.firecrawl_app = None  # Initialize to None explicitly
            
            logger.debug(f"Default topic set to: {self.DEFAULT_TOPIC}")
            
        except Exception as e:
            logger.error(f"Error in Research initialization: {str(e)}", exc_info=True)
            raise
        
        # Load environment variables using centralized loader
        try:
            logger.debug("Loading environment variables")
            load_environment()
            logger.debug("Ensuring model environment variables")
            ensure_model_env_vars()
            
            # Log important environment variables (masked)
            for key in ['FIRECRAWL_API_KEY', 'PROVIDER_FIRECRAWL_KEY', 'OPENAI_API_KEY', 
                       'ANTHROPIC_API_KEY', 'AZURE_OPENAI_API_KEY']:
                value = os.getenv(key)
                if value:
                    masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "[SET]"
                    logger.info(f"Found environment variable: {key}={masked}")
                else:
                    logger.warning(f"Environment variable not found: {key}")
        except Exception as e:
            logger.warning(f"Error loading environment variables: {str(e)}.")
        
        # Initialize AI models
        try:
            # Import here to avoid circular imports
            from app.ai_models import get_available_models, get_ai_model
            
            self.available_models = get_available_models()
            logger.info(f"Available AI models: {[model['name'] for model in self.available_models]}")
            
            if not self.available_models:
                logger.warning("No AI models found after environment setup!")
            
            # Initialize AI model to use
            self.ai_model = None
            self.article_analyzer = None
            
            # Set AI model - use provided model_name or default to first available
            if self.available_models:
                target_model = model_name if model_name else self.available_models[0]['name']
                self.set_ai_model(target_model)
                logger.info(f"Set AI model to: {target_model}")
            else:
                logger.warning("No AI models are available. Some functionality will be limited.")
                
        except Exception as e:
            logger.error(f"Error initializing AI models: {str(e)}", exc_info=True)
            self.available_models = []
            self.ai_model = None
        
        # Initialize Firecrawl
        self.firecrawl_app = self.initialize_firecrawl()
        if self.firecrawl_app:
            logger.info("Firecrawl initialized successfully")
        else:
            logger.warning("Firecrawl initialization failed")
            
        # Load topic configurations
        try:
            self.load_config()
            logger.info(f"Loaded {len(self.topic_configs)} topic configurations")
            logger.info(f"Available topics: {list(self.topic_configs.keys())}")
        except Exception as e:
            logger.error(f"Error loading topic configurations: {str(e)}", exc_info=True)
            # Create a default topic configuration if loading fails
            if not self.topic_configs:
                logger.warning("Creating default topic configuration")
                self.topic_configs = {
                    self.DEFAULT_TOPIC: {
                        "name": self.DEFAULT_TOPIC,
                        "categories": ["General AI", "Machine Learning Research", "AI Applications"],
                        "future_signals": ["AI advances rapidly", "AI progress stalls", "AI regulated heavily"],
                        "sentiment": ["Positive", "Neutral", "Negative"],
                        "time_to_impact": ["Immediate", "Short-term", "Mid-term", "Long-term"],
                        "driver_types": ["Accelerator", "Inhibitor", "Catalyst"]
                    }
                }

    def load_config(self):
        """Load configuration with support for topics."""
        from app.config.config import load_config
        
        config = load_config()
        
        self.topic_configs = {topic['name']: topic for topic in config['topics']}
        
        if self.DEFAULT_TOPIC not in self.topic_configs:
            logger.error(f"Default topic '{self.DEFAULT_TOPIC}' not found in configuration")
            if self.topic_configs:
                # Use the first available topic as the default
                self.current_topic = next(iter(self.topic_configs))
                logger.warning(f"Using '{self.current_topic}' as the default topic instead")
                logger.info(f"Available topics: {list(self.topic_configs.keys())}")
                logger.info("To fix this permanently, run: python scripts/restore_default_topic.py")
            else:
                raise ValueError("No topics found in configuration")
            
    def set_topic(self, topic_name: str):
        """Set the current topic for analysis."""
        logger.debug(f"Setting topic to: {topic_name}")
        if not topic_name:
            logger.warning("Attempted to set empty topic name")
            return
        
        if topic_name not in self.topic_configs:
            # Attempt to reload configuration in case topics were added at runtime
            logger.warning(
                "Invalid topic received: %s. Attempting to reload configuration.",
                topic_name,
            )
            try:
                self.load_config()
            except Exception as reload_err:
                logger.error("Error reloading configuration: %s", str(reload_err))

            # After reloading, check again
            if topic_name not in self.topic_configs:
                logger.warning(
                    "Topic still not found after configuration reload: %s. "
                    "Retaining current topic '%s'",
                    topic_name,
                    self.current_topic,
                )
                return
            
        if self.current_topic != topic_name:
            self.current_topic = topic_name
            logger.info(f"Set current topic to: {topic_name}")
            logger.debug(f"Topic config: {self.topic_configs[topic_name]}")

    @property
    def CATEGORIES(self):
        """Get categories for current topic."""
        return self.topic_configs[self.current_topic]['categories']

    @property
    def FUTURE_SIGNALS(self):
        """Get future signals for current topic."""
        return self.topic_configs[self.current_topic]['future_signals']

    @property
    def SENTIMENT(self):
        """Get sentiment options for current topic."""
        return self.topic_configs[self.current_topic]['sentiment']

    @property
    def TIME_TO_IMPACT(self):
        """Get time to impact options for current topic."""
        return self.topic_configs[self.current_topic]['time_to_impact']

    @property
    def DRIVER_TYPES(self):
        """Get driver types for current topic."""
        return self.topic_configs[self.current_topic]['driver_types']

    def get_topics(self):
        """Get list of available topics."""
        topics = list(self.topic_configs.keys())
        return topics

    def initialize_firecrawl(self):
        """Initialize the Firecrawl service. Returns None if it can't be initialized."""
        # If we already have a working Firecrawl instance, just return it
        if hasattr(self, 'firecrawl_app') and self.firecrawl_app:
            logger.debug("Using existing Firecrawl instance")
            return self.firecrawl_app
            
        try:
            # First explicitly load environment variables to ensure keys are available
            load_dotenv(override=True)
            
            # Import firecrawl directly rather than via dynamic imports
            try:
                from firecrawl import FirecrawlApp
                logger.info("Successfully imported FirecrawlApp module")
            except ImportError as ie:
                logger.error(f"Firecrawl module not installed: {str(ie)}")
                logger.error("Try installing it with: pip install firecrawl")
                return None
                
            # Get API key directly from environment with detailed logging
            firecrawl_key = os.environ.get("FIRECRAWL_API_KEY")
            provider_key = os.environ.get("PROVIDER_FIRECRAWL_KEY")
            
            logger.info(f"FIRECRAWL_API_KEY present: {'Yes' if firecrawl_key else 'No'}")
            logger.info(f"PROVIDER_FIRECRAWL_KEY present: {'Yes' if provider_key else 'No'}")
            
            # Use any available key
            api_key = provider_key or firecrawl_key
            
            if not api_key:
                logger.error("No Firecrawl API key found in environment variables.")
                logger.error("Please set FIRECRAWL_API_KEY or PROVIDER_FIRECRAWL_KEY in your .env file.")
                return None
            
            # Create the FirecrawlApp instance
            masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "[SET]"
            logger.info(f"Initializing Firecrawl with API key: {masked_key}")
            
            firecrawl_instance = FirecrawlApp(api_key=api_key)
            logger.info("Successfully created FirecrawlApp instance")
            
            # Test the instance with a basic request
            try:
                logger.info("Testing Firecrawl instance with a basic request...")
                test_result = firecrawl_instance.scrape_url(
                    "https://example.com",
                    formats=["markdown"]
                )
                # Normalise Firecrawl response (v1 returns content under 'data')
                test_data = test_result.get('data', test_result) if isinstance(test_result, dict) else {}
                if 'markdown' in test_data:
                    logger.info("Firecrawl test successful!")
                else:
                    logger.warning("Firecrawl test returned unexpected response format")
            except Exception as test_error:
                logger.warning(f"Firecrawl test request failed: {str(test_error)}")
                # Continue anyway since the instance was created
                
            return firecrawl_instance
        except Exception as e:
            logger.error(f"Error initializing Firecrawl: {str(e)}", exc_info=True)
            return None

    def check_article_exists(self, uri: str) -> bool:
        """Check if an article exists in the raw_articles table."""
        try:
            result = self.db.get_raw_article(uri)
            return result is not None
        except Exception as e:
            logger.error(f"Error checking if article exists: {str(e)}")
            # If the error is about missing table, return False without further errors
            if "no such table: raw_articles" in str(e):
                logger.warning("raw_articles table does not exist yet. Will be created on the next save.")
                return False
            return False

    def is_bluesky_url(self, uri: str) -> bool:
        """Check if a URL is from the Bluesky platform."""
        parsed_uri = urlparse(uri)
        domain = parsed_uri.netloc.lower()
        # Check for bsky.app domain or any subdomain ending with .bsky.social
        return domain == 'bsky.app' or domain.endswith('.bsky.social')

    async def fetch_article_content(self, uri: str, save_with_topic=False):
        """Fetch article content using Firecrawl or from the database if available."""
        try:
            logger.debug(f"Fetching article content for URI: {uri}")
            
            # Make sure we have models configured before proceeding
            if not self.available_models:
                logger.error("No AI models available. Trying to reload environment variables.")
                # Reload environment and try to get models again
                load_environment()
                from app.ai_models import get_available_models
                self.available_models = get_available_models()
                logger.info(f"Available AI models after reload: {[model['name'] for model in self.available_models if model]}")
                
                if not self.available_models:
                    raise ValueError("No AI models are configured")
                    
            # Ensure ArticleAnalyzer is initialized
            if not hasattr(self, 'article_analyzer') or not self.article_analyzer:
                if not self.ai_model:
                    # Use the first available model as default if none is set
                    if not self.available_models:
                        raise ValueError("No AI models available")
                    self.set_ai_model(self.available_models[0]['name'])
                else:
                    self.article_analyzer = ArticleAnalyzer(self.ai_model, use_cache=True)
                    logger.info(f"Created ArticleAnalyzer with caching for model: {self.ai_model.model_name}")

            # Check for existing article first
            existing_article = self.db.get_raw_article(uri)
            if existing_article:
                logger.info(f"Found existing article content for URI: {uri}")
                return {
                    "content": existing_article.get('raw_markdown', ""),
                    "source": self.extract_source(uri),
                    "publication_date": existing_article.get(
                        'submission_date', 
                        datetime.now(timezone.utc).date().isoformat()
                    ),
                    "exists": True
                }
            
            # Check if this is a Bluesky URL
            if self.is_bluesky_url(uri):
                logger.info(f"Detected Bluesky URL: {uri}")
                try:
                    # Get the BlueskyCollector from the factory
                    bluesky_collector = CollectorFactory.get_collector('bluesky')
                    
                    # Fetch the content using the collector
                    content_result = await bluesky_collector.fetch_article_content(uri)
                    
                    if content_result:
                        # Format the result to match expected structure
                        content = content_result.get('content', '')
                        
                        # Extract publication date or use the one from result
                        publication_date = content_result.get(
                            'published_date', 
                            self.article_analyzer.extract_publication_date(content)
                        )
                        
                        # Save to database if requested and content was successfully extracted
                        if save_with_topic and content:
                            try:
                                logger.debug(
                                    f"Saving Bluesky content to database for URI: {uri}"
                                )
                                
                                # Extract title from content using helper method
                                title = self.extract_title_from_content(content, f"Bluesky Post - {self.extract_source(uri)}")
                                
                                # Only save if we have real content - no placeholders
                                article = (DatabaseQueryFacade(self.db, logger)).get_article_by_url(uri)
                                if not article:
                                    # Create real article entry with extracted content
                                    (DatabaseQueryFacade(self.db, logger)).create_article_with_extracted_content((uri, title, self.extract_source(uri),
                                          self.current_topic, False, content[:500] + "..." if len(content) > 500 else content))

                                # Save raw content
                                self.db.save_raw_article(uri, content, self.current_topic)
                                logger.info(
                                    f"Successfully saved Bluesky article with real content: {title}"
                                )
                            except Exception as save_error:
                                logger.error(
                                    f"Failed to save Bluesky content: {str(save_error)}"
                                )
                        
                        return {
                            "content": content,
                            "source": content_result.get('source', self.extract_source(uri)),
                            "publication_date": publication_date,
                            "exists": False
                        }
                    else:
                        logger.warning(f"BlueskyCollector returned no content for {uri}")
                except Exception as bluesky_error:
                    logger.error(f"Error using BlueskyCollector: {str(bluesky_error)}")
                    return {
                        "content": f"Failed to fetch Bluesky content: {str(bluesky_error)}",
                        "source": self.extract_source(uri),
                        "publication_date": datetime.now(timezone.utc).date().isoformat(),
                        "error": str(bluesky_error)
                    }
            
            # If article doesn't exist and it's not Bluesky, try to scrape it with Firecrawl
            # Check if Firecrawl is available or try to initialize it
            if not self.firecrawl_app:
                logger.info("Firecrawl not initialized, attempting to initialize")
                self.firecrawl_app = self.initialize_firecrawl()
                
            # If still not available after initialization, return error
            if not self.firecrawl_app:
                logger.warning("Firecrawl is not configured. Cannot fetch article content.")
                return {
                    "content": "Article content cannot be fetched. Firecrawl is not configured.",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "error": "Firecrawl not configured"
                }
                
            # Try to scrape with Firecrawl
            try:
                logger.info(f"Using Firecrawl to scrape content for URI: {uri}")
                scrape_result = self.firecrawl_app.scrape_url(
                    uri,
                    formats=["markdown"]
                )
                scrape_data = self._normalize_scrape_result(scrape_result)
                
                # Extract content
                if isinstance(scrape_data, dict) and 'markdown' in scrape_data:
                    content = scrape_data['markdown']
                    
                    # Extract publication date using ArticleAnalyzer
                    publication_date = self.article_analyzer.extract_publication_date(content)
                    
                    # Only save with topic if explicitly requested
                    if save_with_topic:
                        try:
                            logger.debug(f"Attempting to save raw article for URI: {uri} with topic: {self.current_topic}")
                            
                            # Extract title from content using helper method
                            title = self.extract_title_from_content(content, self.extract_source(uri))
                            
                            # Only create article entry if we have real content - no placeholders
                            article = (DatabaseQueryFacade(self.db, logger)).get_article(uri)
                            if not article:
                                # Create real article entry with extracted content
                                (DatabaseQueryFacade(self.db, logger)).create_article_with_extracted_content((uri, title, self.extract_source(uri), self.current_topic, False,
                                      content[:500] + "..." if len(content) > 500 else content))
                                logger.debug(f"Created article entry with real content for URI: {uri}, title: {title}")
                            
                            # Now save the raw article
                            self.db.save_raw_article(uri, content, self.current_topic)
                            logger.info(f"Successfully saved article with real content: {title}")
                        except Exception as save_error:
                            logger.error(f"Failed to save article to database: {str(save_error)}")
                            logger.error(f"This is a database error, but we'll continue with analysis using the scraped content")
                    else:
                        logger.debug(f"Skipping saving raw article with topic (save_with_topic=False)")
                    
                    return {
                        "content": content,
                        "source": self.extract_source(uri),
                        "publication_date": publication_date,
                        "exists": False
                    }
                else:
                    logger.warning(f"Unexpected response format from Firecrawl for URI: {uri}")
                    return {
                        "content": "Failed to fetch article content. Unexpected response format.",
                        "source": self.extract_source(uri),
                        "publication_date": datetime.now(timezone.utc).date().isoformat(),
                        "exists": False
                    }
            except Exception as scrape_error:
                logger.error(f"Error scraping with Firecrawl: {str(scrape_error)}")
                return {
                    "content": "Failed to fetch article content.",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "success": False
                }
            
        except Exception as e:
            logger.error(f"Error in scraping: {str(e)}", exc_info=True)
            return {
                "content": f"Failed to scrape article content: {str(e)}",
                "source": self.extract_source(uri),
                "publication_date": datetime.now(timezone.utc).date().isoformat(),
                "success": False
            }

    async def _do_scrape(self, uri):
        """Actually perform the scraping operation."""
        logger.debug(f"Starting _do_scrape for URI: {uri}")
        
        try:
            # Check if Firecrawl is available or try to initialize it
            if not self.firecrawl_app:
                logger.info("Firecrawl not initialized, attempting to initialize")
                self.firecrawl_app = self.initialize_firecrawl()
                
            # If still not available after initialization, return error
            if not self.firecrawl_app:
                logger.warning("Firecrawl is not configured. Cannot fetch article content.")
                return {
                    "content": "Article content cannot be fetched. Firecrawl is not configured.",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "error": "Firecrawl not configured",
                    "success": False
                }
            
            # Try to scrape with Firecrawl
            logger.info(f"Using Firecrawl to scrape content for URI: {uri}")
            scrape_result = self.firecrawl_app.scrape_url(
                uri,
                formats=["markdown"]
            )
            scrape_data = self._normalize_scrape_result(scrape_result)
            
            logger.debug(f"Scrape result type: {type(scrape_result)}")
            logger.debug(f"Scrape result keys: {scrape_data.keys() if isinstance(scrape_data, dict) else 'Not a dict'}")
            
            # Extract content
            if isinstance(scrape_data, dict) and 'markdown' in scrape_data:
                content = scrape_data['markdown']
                logger.debug(f"Content length: {len(content) if content else 0} chars")
                
                # Extract publication date using ArticleAnalyzer if available
                publication_date = datetime.now(timezone.utc).date().isoformat()
                if hasattr(self, 'article_analyzer') and self.article_analyzer:
                    try:
                        publication_date = self.article_analyzer.extract_publication_date(content)
                        logger.debug(f"Extracted publication date: {publication_date}")
                    except Exception as date_error:
                        logger.error(f"Error extracting publication date: {str(date_error)}")
                
                return {
                    "content": content,
                    "source": self.extract_source(uri),
                    "publication_date": publication_date,
                    "success": True
                }
            else:
                logger.warning(f"Unexpected response format from Firecrawl for URI: {uri}")
                return {
                    "content": "Failed to fetch article content. Unexpected response format.",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "success": False
                }
        except Exception as scrape_error:
            logger.error(f"Error in _do_scrape: {str(scrape_error)}", exc_info=True)
            return {
                "content": f"Failed to fetch article content: {str(scrape_error)}",
                "source": self.extract_source(uri),
                "publication_date": datetime.now(timezone.utc).date().isoformat(),
                "success": False
            }

    def get_existing_article_content(self, uri: str):
        """Retrieve existing article content from the database."""
        try:
            raw_article = self.db.get_raw_article(uri)
            if raw_article:
                content = raw_article['raw_markdown']
                source = self.extract_source(uri)
                publication_date = raw_article['submission_date']
                return {"content": content, "source": source, "publication_date": publication_date}
            else:
                raise ValueError("Article not found in the database.")
        except Exception as e:
            logger.error(f"Error retrieving existing article content: {str(e)}")
            return None

    async def analyze_article(self, uri, article_text, summary_length, summary_voice, summary_type, topic, model_name):
        logger.debug(f"Starting analyze_article for URI: {uri}, topic: {topic}, model: {model_name}")
        
        # Set topic and AI model
        self.set_topic(topic)
        model_set_success = self.set_ai_model(model_name)
        logger.debug(f"Model set success: {model_set_success}")
        
        if not model_set_success:
            logger.error(f"Failed to set AI model to {model_name}")
            # Continue anyway as the code might use a fallback model
        
        # If we need to make sure the ArticleAnalyzer has caching enabled
        if not hasattr(self, 'article_analyzer') or not self.article_analyzer:
            from app.analyzers.article_analyzer import ArticleAnalyzer
            self.article_analyzer = ArticleAnalyzer(self.ai_model, use_cache=True)
            logger.info(f"Created ArticleAnalyzer with caching in analyze_article")
        
        if not article_text:
            logger.debug("No article text provided, fetching from URI")
            article_content = await self.fetch_article_content(uri, save_with_topic=True)
            
            # Add fail-fast check here
            if (
                not article_content or 
                not article_content.get("content") or 
                article_content.get("content").startswith("Article cannot be scraped") or
                article_content.get("content").startswith("Failed to fetch article content")
            ):
                logger.error(f"Failed to fetch article content for {uri}")
                logger.debug(f"Article content response: {article_content}")
                raise ValueError(f"Failed to fetch article content: {article_content.get('content', 'Unknown error')}")
            
            logger.debug(f"Successfully fetched article content, length: {len(article_content.get('content', ''))}")
            article_text = article_content["content"]
            source = article_content["source"]
            publication_date = article_content["publication_date"]
        else:
            logger.debug(f"Using provided article text, length: {len(article_text)}")
            source = self.extract_source(uri)
            publication_date = self.article_analyzer.extract_publication_date(article_text)

        # Truncate article text
        original_length = len(article_text)
        article_text = self.article_analyzer.truncate_text(article_text)
        logger.debug(f"Truncated article text from {original_length} to {len(article_text)} chars")

        # Extract title
        title = self.article_analyzer.extract_title(article_text)
        logger.debug(f"Extracted title: {title}")

        # Convert summary_length to words
        try:
            summary_length_words = int(summary_length)
            logger.debug(f"Summary length set to {summary_length_words} words")
        except ValueError:
            summary_length_words = 50  # Default to 50 words if conversion fails
            logger.warning(f"Could not convert summary length '{summary_length}' to int, using default: 50")

        # Analyze content
        logger.debug("Starting content analysis with ArticleAnalyzer")
        try:
            parsed_analysis = self.article_analyzer.analyze_content(
                article_text=article_text,
                title=title,
                source=source,
                uri=uri,
                summary_length=summary_length_words,
                summary_voice=summary_voice,
                summary_type=summary_type,
                categories=self.CATEGORIES,
                future_signals=self.FUTURE_SIGNALS,
                sentiment_options=self.SENTIMENT,
                time_to_impact_options=self.TIME_TO_IMPACT,
                driver_types=self.DRIVER_TYPES
            )
            logger.debug(f"Analysis complete, received {len(parsed_analysis.keys()) if parsed_analysis else 0} fields")
        except Exception as analysis_error:
            logger.error(f"Article analysis failed: {str(analysis_error)}", exc_info=True) 
            raise
        
        # Verify and format summary
        summary = self.article_analyzer.truncate_summary(
            parsed_analysis.get("summary", ""),
            summary_length_words
        )
        logger.debug(f"Summary length: {len(summary.split())} words")

        # Format tags
        tags = self.article_analyzer.format_tags(parsed_analysis.get("tags", ""))
        logger.debug(f"Formatted tags: {tags}")

        analysis_result = {
            "title": title,
            "news_source": source,
            "uri": uri,
            "summary": summary,
            "sentiment": parsed_analysis.get("sentiment", ""),
            "sentiment_explanation": parsed_analysis.get("sentiment_explanation", ""),
            "time_to_impact": parsed_analysis.get("time_to_impact", ""),
            "time_to_impact_explanation": parsed_analysis.get("time_to_impact_explanation", ""),
            "category": parsed_analysis.get("category", ""),
            "future_signal": parsed_analysis.get("future_signal", ""),
            "future_signal_explanation": parsed_analysis.get("future_signal_explanation", ""),
            "publication_date": publication_date,
            "tags": tags,
            "driver_type": parsed_analysis.get("driver_type", ""),
            "driver_type_explanation": parsed_analysis.get("driver_type_explanation", ""),
            "topic": topic,
            "analyzed": True  # Add analyzed flag
        }

        # Add media bias data
        from app.models.media_bias import MediaBias
        media_bias = MediaBias(self.db)
        domain = self.extract_source(uri)
        bias_data = media_bias.get_bias_for_source(domain)
        
        if bias_data:
            logger.debug(f"Adding media bias data for {domain} to analysis result")
            analysis_result['bias'] = bias_data.get('bias')
            analysis_result['factual_reporting'] = bias_data.get('factual_reporting')
            analysis_result['mbfc_credibility_rating'] = bias_data.get('mbfc_credibility_rating')
            analysis_result['bias_source'] = bias_data.get('source')
            analysis_result['bias_country'] = bias_data.get('country')
            analysis_result['press_freedom'] = bias_data.get('press_freedom')
            analysis_result['media_type'] = bias_data.get('media_type')
            analysis_result['popularity'] = bias_data.get('popularity')
        else:
            logger.debug(f"No media bias data found for {domain}")

        return analysis_result

    def extract_source(self, uri):
        parsed = urlparse(uri)
        return parsed.netloc

    def extract_title_from_content(self, content: str, fallback_source: str = "Unknown") -> str:
        """Extract a meaningful title from article content."""
        if not content:
            return f"Article from {fallback_source}"
        
        # Try to use article analyzer if available
        if hasattr(self, 'article_analyzer') and self.article_analyzer:
            try:
                title = self.article_analyzer.extract_title(content)
                if title and title.strip():
                    return title.strip()
            except Exception as e:
                logger.debug(f"Article analyzer title extraction failed: {e}")
        
        # Fallback: extract from content structure
        lines = content.split('\n')
        
        # Look for markdown headers
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line.startswith('# ') and len(line) > 2:
                return line[2:].strip()
            elif line.startswith('## ') and len(line) > 3:
                return line[3:].strip()
        
        # Look for the first substantial line that's not a URL or date
        for line in lines[:5]:
            line = line.strip()
            if (line and 
                len(line) > 10 and 
                not line.startswith('http') and 
                not line.startswith('Posted on') and
                not line.startswith('By ') and
                not line.isdigit()):
                return line[:100]  # Limit title length
        
        # Final fallback
        return f"Article from {fallback_source}"

    async def get_recent_articles(self, limit=10):
        return self.db.get_recent_articles(limit)

    async def save_article(self, article_data):
        try:
            logger.debug(f"Attempting to save article with data: {json.dumps(article_data, indent=2)}")
            
            # Validate required fields
            required_fields = ['title', 'uri', 'news_source', 'summary', 'sentiment', 'time_to_impact', 
                              'category', 'future_signal', 'future_signal_explanation', 'publication_date', 'topic',
                              'sentiment_explanation', 'time_to_impact_explanation', 'tags', 'driver_type', 
                              'driver_type_explanation']
            
            missing_fields = [field for field in required_fields if field not in article_data]
            if missing_fields:
                raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

            # Convert tags list to string if necessary
            if isinstance(article_data.get('tags'), list):
                article_data['tags'] = ', '.join(article_data['tags'])

            # Additional validation
            if not article_data.get('news_source'):
                logger.warning("Article saved without news source")
                article_data['news_source'] = "Unknown"
            
            # Add media bias data if not already present
            if article_data.get('news_source') and not article_data.get('bias'):
                try:
                    from app.models.media_bias import MediaBias
                    media_bias = MediaBias(self.db)
                    
                    # Check if media bias enrichment is enabled
                    status = media_bias.get_status()
                    if status.get('enabled', False):
                        logger.debug(f"Media bias enrichment is enabled, looking up data for {article_data['news_source']}")
                        
                        # Get bias data for this source
                        bias_data = media_bias.get_bias_for_source(article_data['news_source'])
                        
                        if bias_data:
                            logger.debug(f"Found media bias data for {article_data['news_source']}: {bias_data}")
                            
                            # Add bias data to article
                            article_data['bias'] = bias_data.get('bias', '')
                            article_data['factual_reporting'] = bias_data.get('factual_reporting', '')
                            article_data['mbfc_credibility_rating'] = bias_data.get('mbfc_credibility_rating', '')
                            article_data['bias_source'] = bias_data.get('source', '')
                            article_data['bias_country'] = bias_data.get('country', '')
                            article_data['press_freedom'] = bias_data.get('press_freedom', '')
                            article_data['media_type'] = bias_data.get('media_type', '')
                            article_data['popularity'] = bias_data.get('popularity', '')
                        else:
                            logger.debug(f"No media bias data found for {article_data['news_source']}")
                except Exception as e:
                    logger.error(f"Error enriching article with media bias data: {str(e)}")
                    # Don't fail if media bias enrichment fails

            # Add analyzed field if not present  
            if 'analyzed' not in article_data:
                article_data['analyzed'] = True
            
            # Add timestamp for submission_date if not present
            if 'submission_date' not in article_data:
                article_data['submission_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Save to database
            self.db.save_article(article_data)
                
            # Save raw markdown if available
            if 'raw_markdown' in article_data and article_data['raw_markdown']:
                self.db.save_raw_article(
                    article_data['uri'], 
                    article_data['raw_markdown'],
                    article_data.get('topic', '')
                )
            
            # ✅ ADD AUTOMATIC VECTOR INDEXING
            try:
                from app.vector_store import upsert_article
                
                # Create a copy of article_data for vector indexing
                vector_article = article_data.copy()
                
                # Add raw content if available (upsert_article looks for 'raw' field)
                raw_content = article_data.get('raw_markdown', '')
                if not raw_content:
                    # Try to get from database
                    try:
                        raw_article = self.db.get_raw_article(article_data['uri'])
                        if raw_article:
                            raw_content = raw_article.get('raw_markdown', '')
                    except Exception:
                        pass
                
                if raw_content:
                    vector_article['raw'] = raw_content
                
                # Ensure we have some content for indexing
                if vector_article.get('raw') or vector_article.get('summary') or vector_article.get('title'):
                    # Index into vector database with correct function signature
                    upsert_article(vector_article)
                    logger.info(f"Successfully indexed article into vector database: {article_data['title']}")
                else:
                    logger.warning(f"No content available for vector indexing: {article_data['uri']}")
                    
            except Exception as vector_error:
                logger.error(f"Failed to index article into vector database: {str(vector_error)}")
                # Don't fail the entire save operation if vector indexing fails
                logger.warning("Article saved to database but not indexed in vector store")
            
            logger.info(f"Article saved successfully: {article_data['title']}")
            return True
        except Exception as e:
            logger.error(f"Error saving article: {str(e)}")
            raise

    async def get_categories(self, topic=None):
        logger.debug(f"get_categories called for topic: {topic}")
        try:
            if topic:
                self.set_topic(topic)
            categories = self.CATEGORIES
            logger.debug(f"Returning categories for topic {self.current_topic}: {categories}")
            return categories
        except Exception as e:
            logger.error(f"Error getting categories for topic {topic}: {str(e)}")
            return []

    async def get_future_signals(self, topic=None):
        logger.debug(f"get_future_signals called for topic: {topic}")
        try:
            if topic:
                self.set_topic(topic)
            signals = self.FUTURE_SIGNALS
            logger.debug(f"Returning future signals for topic {self.current_topic}: {signals}")
            return signals
        except Exception as e:
            logger.error(f"Error getting future signals for topic {topic}: {str(e)}")
            return []

    async def get_sentiments(self, topic=None):
        logger.debug(f"get_sentiments called for topic: {topic}")
        try:
            if topic:
                self.set_topic(topic)
            sentiments = self.SENTIMENT
            logger.debug(f"Returning sentiments for topic {self.current_topic}: {sentiments}")
            return sentiments
        except Exception as e:
            logger.error(f"Error getting sentiments for topic {topic}: {str(e)}")
            return []

    async def get_time_to_impact(self, topic=None):
        logger.debug(f"get_time_to_impact called for topic: {topic}")
        try:
            if topic:
                self.set_topic(topic)
            time_to_impact = self.TIME_TO_IMPACT
            logger.debug(f"Returning time to impact for topic {self.current_topic}: {time_to_impact}")
            return time_to_impact
        except Exception as e:
            logger.error(f"Error getting time to impact for topic {topic}: {str(e)}")
            return []

    async def get_driver_types(self, topic=None):
        logger.debug(f"get_driver_types called for topic: {topic}")
        try:
            if topic:
                self.set_topic(topic)
            driver_types = self.DRIVER_TYPES
            logger.debug(f"Returning driver types for topic {self.current_topic}: {driver_types}")
            return driver_types
        except Exception as e:
            logger.error(f"Error getting driver types for topic {topic}: {str(e)}")
            return []

    async def get_article(self, uri: str):
        return self.db.get_article(uri)

    def delete_article(self, uri):
        return self.db.delete_article(uri)

    async def scrape_article(self, uri: str):
        """Scrape article content using Firecrawl."""
        try:
            logger.info(f"Starting article scrape for URI: {uri}")
            
            # Check if this is a Bluesky URL
            if self.is_bluesky_url(uri):
                logger.info(f"Detected Bluesky URL: {uri}")
                try:
                    # Get the BlueskyCollector from the factory
                    bluesky_collector = CollectorFactory.get_collector('bluesky')
                    
                    # Fetch the content using the collector
                    content_result = await bluesky_collector.fetch_article_content(uri)
                    
                    if content_result:
                        # Format the result to match expected structure
                        content = content_result.get('content', '')
                        title = content_result.get('title', '')
                        
                        # Extract publication date or use the one from result
                        publication_date = content_result.get(
                            'published_date',
                            self.article_analyzer.extract_publication_date(content)
                        )
                        
                        # Try to save the article but don't fail if it can't be saved
                        try:
                            self.db.save_raw_article(uri, content, self.current_topic)
                            logger.info(
                                f"Successfully saved Bluesky content: {self.current_topic}"
                            )
                        except Exception as save_error:
                            logger.error(
                                f"Failed to save Bluesky content: {str(save_error)}"
                            )
                        
                        # Get metadata
                        metadata = {
                            'title': title,
                            'published_date': publication_date,
                            'author': (content_result.get('authors', [''])[0] 
                                      if content_result.get('authors') else '')
                        }
                        
                        return {
                            "content": content,
                            "source": content_result.get('source', self.extract_source(uri)),
                            "publication_date": publication_date,
                            "metadata": metadata
                        }
                    else:
                        logger.warning(f"BlueskyCollector returned no content for {uri}")
                        return {
                            "content": "Failed to fetch Bluesky content. No content returned.",
                            "source": self.extract_source(uri),
                            "publication_date": datetime.now(timezone.utc).date().isoformat(),
                            "error": "No content returned from Bluesky collector"
                        }
                except Exception as bluesky_error:
                    logger.error(f"Error using BlueskyCollector: {str(bluesky_error)}")
                    return {
                        "content": f"Failed to fetch Bluesky content: {str(bluesky_error)}",
                        "source": self.extract_source(uri),
                        "publication_date": datetime.now(timezone.utc).date().isoformat(),
                        "error": str(bluesky_error)
                    }
            
            # If not Bluesky, proceed with Firecrawl
            # Reload environment and check if Firecrawl is available
            if not self.firecrawl_app:
                logger.info("Firecrawl not configured, attempting to initialize")
                self.firecrawl_app = self.initialize_firecrawl()
                
            # If still not available after initialization attempt, return error
            if not self.firecrawl_app:
                logger.warning("Firecrawl is not configured. Cannot scrape article.")
                return {
                    "content": "Article cannot be scraped. Firecrawl is not configured.",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "error": "Firecrawl not configured"
                }
            
            # Check if the URI is valid
            parsed_uri = urlparse(uri)
            if not parsed_uri.scheme or not parsed_uri.netloc:
                logger.warning(f"Invalid URI format: {uri}")
                return {
                    "content": f"Invalid URI format: {uri}. URI must start with http:// or https://",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "error": "Invalid URI format"
                }
            
            # Use Firecrawl to scrape the article
            try:
                logger.info(f"Using Firecrawl to scrape {uri}")
                scrape_result = self.firecrawl_app.scrape_url(
                    uri,
                    formats=["markdown"]
                )
                scrape_data = self._normalize_scrape_result(scrape_result)
            except Exception as scrape_error:
                logger.error(f"Firecrawl API error: {str(scrape_error)}")
                return {
                    "content": f"Error scraping article: {str(scrape_error)}",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "error": f"Firecrawl API error: {str(scrape_error)}"
                }
            
            # Process the response if it's a dictionary containing 'markdown'
            if isinstance(scrape_data, dict) and 'markdown' in scrape_data:
                content = scrape_data['markdown']
                
                # Check if content is empty or too short
                if not content or len(content.strip()) < 10:
                    logger.warning(f"Received empty or too short content from Firecrawl for {uri}")
                    return {
                        "content": "Received empty or too short content from Firecrawl.",
                        "source": self.extract_source(uri),
                        "publication_date": datetime.now(timezone.utc).date().isoformat(),
                        "error": "Empty content"
                    }
                
                # Try to save the article but don't fail if it can't be saved
                try:
                    self.db.save_raw_article(uri, content, self.current_topic)
                    logger.info(f"Successfully saved raw article with topic: {self.current_topic}")
                except Exception as save_error:
                    logger.error(f"Failed to save raw article: {str(save_error)}")
                    logger.error(f"Current topic: {self.current_topic}")
                    # Continue even if saving fails - we still want to return the content
                
                try:
                    # Extract the date using ArticleAnalyzer
                    publication_date = self.article_analyzer.extract_publication_date(content)
                    logger.debug(f"Publication date extracted: {publication_date}")
                except Exception as date_error:
                    logger.error(f"Error extracting publication date: {str(date_error)}")
                    publication_date = datetime.now(timezone.utc).date().isoformat()

                source = self.extract_source(uri)
                logger.info(f"Article processing complete. Source: {source}, Publication date: {publication_date}")
                
                # Get metadata if available
                metadata = {}
                if 'title' in scrape_data:
                    metadata['title'] = scrape_data['title']
                if 'published_date' in scrape_data:
                    metadata['published_date'] = scrape_data['published_date']
                if 'author' in scrape_data:
                    metadata['author'] = scrape_data['author']
                
                return {
                    "content": content,
                    "source": source,
                    "publication_date": publication_date,
                    "metadata": metadata
                }
            else:
                # Log the actual response format received
                logger.error(f"Unexpected response format from Firecrawl: {scrape_data}")
                return {
                    "content": "Failed to fetch article content. Unexpected response format.", 
                    "source": self.extract_source(uri), 
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "error": "Unexpected response format"
                }
            
        except Exception as e:
            logger.error(f"Error scraping article: {str(e)}", exc_info=True)
            return {
                "content": f"Failed to scrape article content: {str(e)}", 
                "source": self.extract_source(uri), 
                "publication_date": datetime.now(timezone.utc).date().isoformat(),
                "error": str(e)
            }

    def get_recent_articles_by_topic(self, topic_name, limit=10):
        try:
            articles = self.db.get_recent_articles_by_topic(topic_name, limit)
            return articles
        except Exception as e:
            logger.error(f"Error getting recent articles by topic: {str(e)}")
            return []

    def set_ai_model(self, model_name):
        """
        Set the AI model for analysis.
        
        Args:
            model_name: The name of the model to use
        """
        from app.ai_models import get_ai_model, get_available_models
        
        try:
            # If available_models is empty, try to reload models list
            if not self.available_models:
                logger.warning("Available models list is empty, reloading...")
                self.available_models = get_available_models()
                if not self.available_models:
                    # Log all environment variables for debugging
                    logger.error("Still no AI models available after reload. Environment vars:")
                    for key, value in os.environ.items():
                        if 'API_KEY' in key:
                            masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "[SET]"
                            logger.error(f"  {key}={masked}")
                    
                    # Add more detailed logging about API keys
                    logger.error(f"OPENAI_API_KEY configured: {'Yes' if os.environ.get('OPENAI_API_KEY') else 'No'}")
                    logger.error(f"ANTHROPIC_API_KEY configured: {'Yes' if os.environ.get('ANTHROPIC_API_KEY') else 'No'}")
                    logger.error(f"AZURE_OPENAI_API_KEY configured: {'Yes' if os.environ.get('AZURE_OPENAI_API_KEY') else 'No'}")
                    
                    raise ValueError(f"No AI models available. Cannot set model to {model_name}")
            
            logger.info(f"Setting AI model to {model_name}")
            
            available_model_names = [model['name'] for model in self.available_models]
            logger.debug(f"Available model names: {available_model_names}")
            
            if model_name not in available_model_names:
                logger.error(f"Model {model_name} not in available models: {available_model_names}")
                if available_model_names:
                    logger.info(f"Setting default model to {available_model_names[0]}")
                    model_name = available_model_names[0]
                else:
                    raise ValueError(f"No AI models available")
            
            # Load the model
            logger.debug(f"Getting AI model instance for {model_name}")
            self.ai_model = get_ai_model(model_name)
            if self.ai_model is None:
                logger.warning("Model not found in static config; falling back to LiteLLM dynamic router")
                try:
                    from app.ai_models import LiteLLMModel
                    self.ai_model = LiteLLMModel.get_instance(model_name)
                    logger.info("Instantiated LiteLLMModel for %s", model_name)
                except Exception as llm_err:
                    logger.error("Failed to create LiteLLMModel: %s", llm_err)
                    raise
            else:
                logger.debug(f"AI model instance created: {type(self.ai_model).__name__}")
            
            # Initialize the article analyzer with the new model
            from app.analyzers.article_analyzer import ArticleAnalyzer
            
            # Only create new ArticleAnalyzer if it doesn't exist
            if not hasattr(self, 'article_analyzer') or not self.article_analyzer:
                self.article_analyzer = ArticleAnalyzer(self.ai_model, use_cache=True)
                logger.debug(f"Created new ArticleAnalyzer with caching for model: {model_name}")
            else:
                # Update existing analyzer with new model while preserving cache
                self.article_analyzer.ai_model = self.ai_model
                self.article_analyzer.model_name = model_name
                logger.debug(f"Updated existing ArticleAnalyzer with model: {model_name}")
            
            logger.info(f"Successfully set AI model to {model_name}")
            return True
        except Exception as e:
            logger.error(f"Error setting AI model to {model_name}: {str(e)}", exc_info=True)
            return False

    def get_available_models(self):
        return self.available_models

    def _load_categories(self):
        try:
            categories = self.db.get_categories()
            logger.debug(f"Loaded categories from database: {categories}")
            return categories
        except Exception as e:
            logger.error(f"Error loading categories: {str(e)}", exc_info=True)
            return []

    def reload_environment(self):
        """Reload environment variables and reinitialize clients."""
        try:
            logger.info("Reloading environment for Research instance")
            
            # Reload environment variables
            env_path = load_environment()
            
            # Log important keys (masked)
            # Prioritize PROVIDER_FIRECRAWL_KEY over FIRECRAWL_API_KEY
            firecrawl_key = os.environ.get("PROVIDER_FIRECRAWL_KEY") or os.environ.get("FIRECRAWL_API_KEY")
            newsapi_key = os.environ.get("PROVIDER_NEWSAPI_KEY") or os.environ.get("NEWSAPI_KEY")
            openai_key = os.environ.get("OPENAI_API_KEY")
            
            if firecrawl_key:
                masked_key = firecrawl_key[:4] + "..." + firecrawl_key[-4:] if len(firecrawl_key) > 8 else "[SET]"
                logger.info(f"Firecrawl API key loaded: {masked_key}")
            
            if newsapi_key:
                masked_key = newsapi_key[:4] + "..." + newsapi_key[-4:] if len(newsapi_key) > 8 else "[SET]"
                logger.info(f"NewsAPI key loaded: {masked_key}")
            
            if openai_key:
                masked_key = openai_key[:4] + "..." + openai_key[-4:] if len(openai_key) > 8 else "[SET]"
                logger.info(f"OpenAI API key loaded: {masked_key}")
            
            # Re-initialize API clients
            self.firecrawl_app = self.initialize_firecrawl()
            
            # Reinitialize AI models
            try:
                from app.ai_models import ensure_model_env_vars, get_available_models
                ensure_model_env_vars()
                self.available_models = get_available_models()
                
                # Set the default model if we have available models
                if self.available_models and len(self.available_models) > 0:
                    # The available_models is a list of dictionaries, not a dictionary
                    default_model = self.available_models[0]['name']
                    self.set_ai_model(default_model)
                    logger.info(f"Default AI model set to {default_model}")
                else:
                    logger.warning("No AI models available after environment reload")
            except Exception as e:
                logger.error(f"Error reloading AI models: {str(e)}")
            
            # Reinitialize the article analyzer if we have an AI model
            if hasattr(self, 'ai_model') and self.ai_model:
                self.article_analyzer = ArticleAnalyzer(self.ai_model, use_cache=True)
                logger.info(f"Reinitialized ArticleAnalyzer with caching for model: {self.ai_model.model_name}")
            
            logger.info("Research environment reload completed")
            return True
        except Exception as e:
            logger.error(f"Error reloading environment: {str(e)}")
            return False

    def _normalize_scrape_result(self, scrape_result: Any) -> Dict[str, Any]:
        """Convert Firecrawl scrape result to a plain dict with markdown, etc."""
        if isinstance(scrape_result, dict):
            return scrape_result.get("data", scrape_result)

        # Check for `.data` attribute (SDK object)
        data_attr = getattr(scrape_result, "data", None)
        if isinstance(data_attr, dict):
            return data_attr

        # Check for Pydantic `model_dump()`
        if hasattr(scrape_result, "model_dump"):
            try:
                dumped = scrape_result.model_dump()
                if isinstance(dumped, dict):
                    return dumped.get("data", dumped)
            except Exception:
                pass

        # Fallback to __dict__ if available
        if hasattr(scrape_result, "__dict__"):
            return scrape_result.__dict__.get("data", scrape_result.__dict__)

        return {}

    def check_vector_indexing_status(self, uri: str) -> Dict[str, Any]:
        """Debug utility to check if an article is indexed in the vector database."""
        try:
            from app.vector_store import _get_collection
            
            collection = _get_collection()
            
            # Try to get the article from vector database
            result = collection.get(
                ids=[uri],
                include=['metadatas', 'documents']
            )
            
            if result and result.get('ids') and uri in result['ids']:
                idx = result['ids'].index(uri)
                return {
                    "indexed": True,
                    "uri": uri,
                    "metadata": result.get('metadatas', [{}])[idx] if result.get('metadatas') else {},
                    "has_content": bool(result.get('documents', [''])[idx]) if result.get('documents') else False,
                    "content_length": len(result.get('documents', [''])[idx] or '') if result.get('documents') else 0
                }
            else:
                return {
                    "indexed": False,
                    "uri": uri,
                    "message": "Article not found in vector database"
                }
                
        except Exception as e:
            logger.error(f"Error checking vector indexing status: {str(e)}")
            return {
                "indexed": False,
                "uri": uri,
                "error": str(e)
            }












