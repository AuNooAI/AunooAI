from openai import OpenAI
from typing import Optional
from urllib.parse import urlparse
import logging
import os
import json
from firecrawl import FirecrawlApp
from config import settings
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database import Database, SessionLocal
from dotenv import load_dotenv
from app.ai_models import get_ai_model, get_available_models
from app.database import Database 
from app.analyzers.article_analyzer import ArticleAnalyzer

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
            self.load_config()
            
        except Exception as e:
            logger.error(f"Error in Research initialization: {str(e)}", exc_info=True)
            raise
        if not os.path.exists('.env'):
            raise FileNotFoundError("The .env file does not exist. Please create it and add the necessary environment variables.")
        load_dotenv()
        self.available_models = get_available_models()
        self.ai_model = None
        self.article_analyzer = None
        self.firecrawl_app = self.initialize_firecrawl()

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
        firecrawl_api_key = settings.FIRECRAWL_API_KEY
        if not firecrawl_api_key:
            logger.warning("Firecrawl API key is missing. Some functionality will be limited.")
            return None
        return FirecrawlApp(api_key=firecrawl_api_key)

    def check_article_exists(self, uri: str) -> bool:
        """Check if an article exists in the raw_articles table."""
        try:
            result = self.db.get_raw_article(uri)
            return result is not None
        except Exception as e:
            logger.error(f"Error checking if article exists: {str(e)}")
            return False

    async def fetch_article_content(self, uri: str):
        logger.debug(f"Fetching article content for URI: {uri}")
        try:
            # Ensure ArticleAnalyzer is initialized
            if not hasattr(self, 'article_analyzer') or not self.article_analyzer:
                if not self.ai_model:
                    # Use the first available model as default if none is set
                    if not self.available_models:
                        raise ValueError("No AI models are configured")
                    self.set_ai_model(self.available_models[0]['name'])
                else:
                    self.article_analyzer = ArticleAnalyzer(self.ai_model)

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
            
            # Check if Firecrawl is available
            if not self.firecrawl_app:
                logger.warning("Firecrawl is not configured. Cannot fetch article content.")
                return {
                    "content": "Article content cannot be fetched. Firecrawl is not configured.",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "error": "Firecrawl not configured"
                }
            
            logger.info(f"Article does not exist in database, scraping: {uri}")
            scrape_result = self.firecrawl_app.scrape_url(
                uri,
                params={
                    'formats': ['markdown']
                }
            )
            
            if 'markdown' in scrape_result:
                content = scrape_result['markdown']
                
                # Extract publication date using ArticleAnalyzer
                raw_date = scrape_result.get('date') or scrape_result.get('published_date') or scrape_result.get('pubDate')
                publication_date = self.article_analyzer.extract_publication_date(content)
                
                # Save the raw markdown with current topic
                self.db.save_raw_article(uri, content, self.current_topic)
                
                source = self.extract_source(uri)
                return {
                    "content": content, 
                    "source": source, 
                    "publication_date": publication_date, 
                    "exists": False
                }
            else:
                logger.error(f"Failed to fetch content for {uri}")
                return {
                    "content": "Failed to fetch article content.",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
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
            article_text = article_content["content"]
            source = article_content["source"]
            publication_date = article_content["publication_date"]
        else:
            source = self.extract_source(uri)
            # Use ArticleAnalyzer to extract date from provided text
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
        """Scrape the article using Firecrawl."""
        try:
            logger.info(f"Starting article scrape for URI: {uri}")
            
            # Check if Firecrawl is available
            if not self.firecrawl_app:
                logger.warning("Firecrawl is not configured. Cannot scrape article.")
                return {
                    "content": "Article cannot be scraped. Firecrawl is not configured.",
                    "source": self.extract_source(uri),
                    "publication_date": datetime.now(timezone.utc).date().isoformat(),
                    "error": "Firecrawl not configured"
                }
            
            scrape_result = self.firecrawl_app.scrape_url(
                uri,
                params={
                    'formats': ['markdown']
                }
            )
            
            if 'markdown' in scrape_result:
                logger.info(f"Successfully scraped content from {uri}")
                content = scrape_result['markdown']
                # Save the raw markdown
                try:
                    self.db.save_raw_article(uri, content, self.current_topic)
                    logger.info(f"Successfully saved raw article with topic: {self.current_topic}")
                except Exception as save_error:
                    logger.error(f"Failed to save raw article: {str(save_error)}")
                    logger.error(f"Current topic: {self.current_topic}")
                    raise save_error

                # Extract the date using ArticleAnalyzer
                publication_date = self.article_analyzer.extract_publication_date(content)
                logger.debug(f"Publication date extracted: {publication_date}")

                source = self.extract_source(uri)
                logger.info(f"Article processing complete. Source: {source}, Publication date: {publication_date}")
                return {"content": content, "source": source, "publication_date": publication_date}
            else:
                logger.error(f"Failed to fetch content for {uri}")
                return {
                    "content": "Failed to fetch article content.", 
                    "source": self.extract_source(uri), 
                    "publication_date": datetime.now(timezone.utc).date().isoformat()
                }
            
        except Exception as e:
            logger.error(f"Error scraping article: {str(e)}", exc_info=True)
            logger.error(f"URI: {uri}, Current topic: {self.current_topic}")
            return {
                "content": "Failed to scrape article content.", 
                "source": self.extract_source(uri), 
                "publication_date": datetime.now(timezone.utc).date().isoformat()
            }

    def get_recent_articles_by_topic(self, topic_name, limit=10):
        try:
            articles = self.db.get_recent_articles_by_topic(topic_name, limit)
            return articles
        except Exception as e:
            logger.error(f"Error getting recent articles by topic: {str(e)}")
            return []

    def set_ai_model(self, model_name):
        logger.debug(f"Setting AI model to: {model_name}")
        if not self.available_models:
            raise ValueError("No AI models are configured. Please add a model in the configuration section.")
        available_names = [model['name'] for model in self.available_models]
        logger.debug(f"Available models: {available_names}")
        if model_name not in available_names:
            raise ValueError(f"Model {model_name} is not configured. Please select a configured model.")
        
        # If we're changing models, disable cache for the next analysis
        use_cache = True
        if hasattr(self, 'ai_model') and self.ai_model and getattr(self.ai_model, 'model_name', None) != model_name:
            logger.debug(f"Switching models from {getattr(self.ai_model, 'model_name', 'None')} to {model_name}")
            use_cache = False

        logger.debug(f"CACHE STATUS AFTER SETTING AI MODEL: use_cache={use_cache}")

        self.ai_model = get_ai_model(model_name)
        logger.debug(f"Successfully set AI model to: {model_name}")
        # Initialize ArticleAnalyzer if not already initialized
        if not hasattr(self, 'article_analyzer') or not self.article_analyzer or not use_cache:
            logger.debug(f"Creating new ArticleAnalyzer with use_cache={use_cache}")
            self.article_analyzer = ArticleAnalyzer(self.ai_model, use_cache=use_cache)

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










