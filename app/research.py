from openai import OpenAI
from typing import Optional
from urllib.parse import urlparse
import logging
import os
import json
from firecrawl import FirecrawlApp
from app.config import settings
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database import Database, SessionLocal
from app.env_loader import load_environment, ensure_model_env_vars
from app.database import Database 
from app.analyzers.article_analyzer import ArticleAnalyzer
import importlib
from dotenv import load_dotenv

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class Research:
    DEFAULT_TOPIC = "AI and Machine Learning"

    def __init__(self, db):
        try:
            # Update required methods to match actual Database class methods
            required_methods = ['get_connection', 'save_raw_article', 'get_raw_article']
            
            if isinstance(db, Session):
                #logger.debug("Converting Session to Database")
                from app.database import Database
                self.db = Database()
                self.session = db
            elif hasattr(db, 'get_connection'):  # Check for the main required method
                self.db = db
                self.session = None
            else:
                logger.error(f"Invalid database instance. Missing required methods.")
                raise TypeError("Database instance must implement required methods")
                
            self.current_topic = self.DEFAULT_TOPIC
            self.topic_configs = {}
            self.firecrawl_app = None  # Initialize to None explicitly
            
        except Exception as e:
            logger.error(f"Error in Research initialization: {str(e)}", exc_info=True)
            raise
        
        # Load environment variables using centralized loader
        try:
            load_environment()
            ensure_model_env_vars()
            
            # Log important environment variables (masked)
            for key in ['FIRECRAWL_API_KEY', 'PROVIDER_FIRECRAWL_KEY', 'OPENAI_API_KEY']:
                value = os.getenv(key)
                if value:
                    masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "[SET]"
                    logger.info(f"Found environment variable: {key}={masked}")
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
            
            if self.available_models:
                self.set_ai_model(self.available_models[0]['name'])
                logger.info(f"Set default AI model to: {self.available_models[0]['name']}")
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
                self.current_topic = next(iter(self.topic_configs))
            else:
                raise ValueError("No topics found in configuration")
            
    def set_topic(self, topic_name: str):
        """Set the current topic for analysis."""
        logger.debug(f"Setting topic to: {topic_name}")
        if not topic_name:
            logger.warning("Attempted to set empty topic name")
            return
        
        if topic_name not in self.topic_configs:
            logger.error(f"Invalid topic: {topic_name}")
            raise ValueError(f"Invalid topic: {topic_name}")
            
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
                    params={'formats': ['markdown']}
                )
                if 'markdown' in test_result:
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

    async def fetch_article_content(self, uri: str):
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
                
                self.article_analyzer = ArticleAnalyzer(self.ai_model)
                logger.info(f"Created ArticleAnalyzer with model: {self.ai_model.model_name}")

            # Check for existing article first
            existing_article = self.db.get_raw_article(uri)
            if existing_article:
                logger.info(f"Found existing article content for URI: {uri}")
                return {
                    "content": existing_article['content'],
                    "source": self.extract_source(uri),
                    "publication_date": existing_article.get('submission_date', datetime.now(timezone.utc).date().isoformat()),
                    "exists": True
                }
            
            # If article doesn't exist, try to scrape it
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
                    params={'formats': ['markdown']}
                )
                
                # Extract content
                if isinstance(scrape_result, dict) and 'markdown' in scrape_result:
                    content = scrape_result['markdown']
                    
                    # Extract publication date using ArticleAnalyzer
                    publication_date = self.article_analyzer.extract_publication_date(content)
                    
                    # Save the raw markdown with current topic
                    self.db.save_raw_article(uri, content, self.current_topic)
                    
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

    async def fetch_article_content(self, uri: str):
        """Fetch article content, checking DB first then scraping if needed."""
        logger.debug(f"Fetching article content for URI: {uri}")
        try:
            # Check for existing article first
            existing_article = self.db.get_raw_article(uri)
            
            if existing_article:
                logger.info(f"Article already exists in database: {uri}")
                return {
                    "content": existing_article['raw_markdown'],
                    "source": self.extract_source(uri),
                    "publication_date": existing_article['submission_date'],
                    "exists": True
                }
            
            # If article doesn't exist, scrape it
            logger.info(f"Article does not exist in database, scraping: {uri}")
            scrape_result = await self._do_scrape(uri)
            
            if scrape_result.get("success", False):
                # Save to database
                self.db.save_raw_article(uri, scrape_result["content"], self.current_topic)
                
            return {
                "content": scrape_result["content"],
                "source": scrape_result["source"],
                "publication_date": scrape_result["publication_date"],
                "exists": False
            }
            
        except Exception as e:
            logger.error(f"Error fetching article content: {str(e)}", exc_info=True)
            return {
                "content": "Failed to fetch article content.",
                "source": self.extract_source(uri),
                "publication_date": datetime.now(timezone.utc).date().isoformat(),
                "exists": False
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
        self.set_topic(topic)
        self.set_ai_model(model_name)

        if not article_text:
            article_content = await self.fetch_article_content(uri)
            
            # Add fail-fast check here
            if (
                not article_content or 
                not article_content.get("content") or 
                article_content.get("content").startswith("Article cannot be scraped") or
                article_content.get("content").startswith("Failed to fetch article content")
            ):
                logger.error(f"Failed to fetch article content for {uri}")
                raise ValueError(f"Failed to fetch article content: {article_content.get('content', 'Unknown error')}")
            
            article_text = article_content["content"]
            source = article_content["source"]
            publication_date = article_content["publication_date"]
        else:
            source = self.extract_source(uri)
            publication_date = self.article_analyzer.extract_publication_date(article_text)

        # Truncate article text
        article_text = self.article_analyzer.truncate_text(article_text)

        # Extract title
        title = self.article_analyzer.extract_title(article_text)

        # Convert summary_length to words
        try:
            summary_length_words = int(summary_length)
        except ValueError:
            summary_length_words = 50  # Default to 50 words if conversion fails

        # Analyze content
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

        # Verify and format summary
        summary = self.article_analyzer.truncate_summary(
            parsed_analysis.get("summary", ""),
            summary_length_words
        )

        # Format tags
        tags = self.article_analyzer.format_tags(parsed_analysis.get("tags", ""))

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

        return analysis_result

    def extract_source(self, uri):
        domain = urlparse(uri).netloc
        return domain.replace('www.', '')

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
            if isinstance(article_data['tags'], list):
                article_data['tags'] = ','.join(article_data['tags'])
            
            result = await self.db.save_article(article_data)
            logger.debug(f"Successfully saved article: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in save_article at {datetime.datetime.now().isoformat()}: {str(e)}")
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
                    params={
                        'formats': ['markdown']
                    }
                )
                logger.debug(f"Firecrawl response keys: {scrape_result.keys() if isinstance(scrape_result, dict) else 'Not a dict'}")
            except Exception as scrape_error:
                logger.error(f"Firecrawl API error: {str(scrape_error)}")
                return {
                    "content": f"Error scraping article: {str(scrape_error)}",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "error": f"Firecrawl API error: {str(scrape_error)}"
                }
            
            # Process the response if it's a dictionary containing 'markdown'
            if isinstance(scrape_result, dict) and 'markdown' in scrape_result:
                content = scrape_result['markdown']
                
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
                if 'title' in scrape_result:
                    metadata['title'] = scrape_result['title']
                if 'published_date' in scrape_result:
                    metadata['published_date'] = scrape_result['published_date']
                if 'author' in scrape_result:
                    metadata['author'] = scrape_result['author']
                
                return {
                    "content": content,
                    "source": source,
                    "publication_date": publication_date,
                    "metadata": metadata
                }
            else:
                # Log the actual response format received
                logger.error(f"Unexpected response format from Firecrawl: {scrape_result}")
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
                    raise ValueError(f"No AI models available. Cannot set model to {model_name}")
            
            logger.info(f"Setting AI model to {model_name}")
            
            available_model_names = [model['name'] for model in self.available_models]
            if model_name not in available_model_names:
                logger.error(f"Model {model_name} not in available models: {available_model_names}")
                if available_model_names:
                    logger.info(f"Setting default model to {available_model_names[0]}")
                    model_name = available_model_names[0]
                else:
                    raise ValueError(f"No AI models available")
                    
            # Load the model
            self.ai_model = get_ai_model(model_name)
            
            # Initialize the article analyzer with the new model
            from app.analyzers.article_analyzer import ArticleAnalyzer
            self.article_analyzer = ArticleAnalyzer(self.ai_model)
            
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

    async def move_alert_to_articles(self, url: str) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # First get the alert article
            cursor.execute("""
                SELECT * FROM keyword_alert_articles 
                WHERE url = ? AND moved_to_articles = FALSE
            """, (url,))
            alert = cursor.fetchone()
            
            if alert:
                # Insert into articles table with analyzed flag
                cursor.execute("""
                    INSERT INTO articles (url, title, summary, source, topic, analyzed)
                    VALUES (?, ?, ?, ?, ?, FALSE)
                """, (alert['url'], alert['title'], alert['summary'], 
                     alert['source'], alert['topic']))
                
                # Mark as moved
                cursor.execute("""
                    UPDATE keyword_alert_articles 
                    SET moved_to_articles = TRUE
                    WHERE url = ?
                """, (url,))

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
                self.article_analyzer = ArticleAnalyzer(self.ai_model)
                logger.info(f"Reinitialized ArticleAnalyzer with model: {self.ai_model.model_name}")
            
            logger.info("Research environment reload completed")
            return True
        except Exception as e:
            logger.error(f"Error reloading environment: {str(e)}")
            return False










