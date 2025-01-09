import requests
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
from app.ai_models import get_ai_model, get_available_models as ai_get_available_models
from app.database import Database 
import re
    
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
        self.available_models = ai_get_available_models()
        self.ai_model = None
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
            raise ValueError("Firecrawl API key is missing in the settings file")
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
            # Check if the article already exists
            existing_article = self.db.get_raw_article(uri)
            
            if existing_article:
                logger.info(f"Article already exists in database: {uri}")
                return {
                    "content": existing_article['raw_markdown'],
                    "source": self.extract_source(uri),
                    "publication_date": existing_article['submission_date'],
                    "exists": True
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
                # Save the raw markdown with current topic
                self.db.save_raw_article(uri, content, self.current_topic)
                
                # Extract and parse publication date
                publication_date = None
                raw_date = scrape_result.get('date') or scrape_result.get('published_date') or scrape_result.get('pubDate')
                
                if raw_date:
                    logger.info(f"Raw date from scraper: {raw_date}")
                    # Try common date formats
                    date_formats = [
                        '%Y-%m-%d',           # 2024-03-14
                        '%Y/%m/%d',           # 2024/03/14
                        '%d-%m-%Y',           # 14-03-2024
                        '%d/%m/%Y',           # 14/03/2024
                        '%Y-%m-%dT%H:%M:%S',  # 2024-03-14T15:30:00
                        '%Y-%m-%dT%H:%M:%S.%f%z',  # 2024-03-14T15:30:00.000Z
                        '%Y-%m-%dT%H:%M:%SZ', # 2024-03-14T15:30:00Z
                        '%B %d, %Y',          # March 14, 2024
                        '%d %B %Y',           # 14 March 2024
                        '%d %B, %Y',          # 14 March, 2024
                        '%Y-%m-%d %H:%M:%S',  # 2024-03-14 15:30:00
                        '%d %B %Y',           # 06 December 2024
                        '%d-%B-%Y',           # 06-December-2024
                        '%d %b %Y',           # 06 Dec 2024
                        '%d-%b-%Y',           # 06-Dec-2024
                        '%b %d, %Y',          # Dec 06, 2024
                        '%B %d, %Y',          # December 06, 2024
                    ]
                    
                    for date_format in date_formats:
                        try:
                            parsed_date = datetime.strptime(raw_date, date_format)
                            publication_date = parsed_date.date().isoformat()
                            logger.info(f"Successfully parsed date {raw_date} with format {date_format}")
                            break
                        except ValueError:
                            continue
                    
                    if not publication_date:
                        logger.warning(f"Could not parse date {raw_date} with any known format")
                
                if not publication_date:
                    # If we still don't have a date, try to extract it from the content
                    # This is a fallback mechanism
                    date_patterns = [
                        r'\d{4}-\d{2}-\d{2}',  # Match YYYY-MM-DD
                        r'\d{2}/\d{2}/\d{4}',  # Match DD/MM/YYYY
                        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}'  # Match Month DD, YYYY
                    ]
                    
                    for pattern in date_patterns:
                        matches = re.findall(pattern, content[:1000])  # Look in first 1000 chars
                        if matches:
                            try:
                                # Try to parse the first match
                                if '-' in matches[0]:
                                    parsed_date = datetime.strptime(matches[0], '%Y-%m-%d')
                                elif '/' in matches[0]:
                                    parsed_date = datetime.strptime(matches[0], '%d/%m/%Y')
                                else:
                                    parsed_date = datetime.strptime(matches[0], '%B %d, %Y')
                                publication_date = parsed_date.date().isoformat()
                                logger.info(f"Extracted date from content: {publication_date}")
                                break
                            except ValueError:
                                continue
                
                if not publication_date:
                    # If all else fails, use current date
                    publication_date = datetime.now(timezone.utc).date().isoformat()
                    logger.warning(f"Using current date as fallback for {uri}: {publication_date}")
                
                source = self.extract_source(uri)
                return {"content": content, "source": source, "publication_date": publication_date, "exists": False}
            else:
                logger.error(f"Failed to fetch content for {uri}")
                content = "Failed to fetch article content."
                publication_date = datetime.now(timezone.utc).date().isoformat()

            source = self.extract_source(uri)
            return {"content": content, "source": source, "publication_date": publication_date, "exists": False}
        except Exception as e:
            logger.error(f"Error fetching article content: {str(e)}", exc_info=True)
            return {"content": "Failed to fetch article content.", "source": self.extract_source(uri), "publication_date": datetime.now(timezone.utc).date().isoformat(), "exists": False}
        
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
        """Update analyze_article to use topic-specific configurations."""
        # Set the topic before analysis
        self.set_topic(topic)
        
        # Set the AI model based on the selected model_name
        self.set_ai_model(model_name)

        if not article_text:
            article_content = await self.fetch_article_content(uri)
            article_text = article_content["content"]
            source = article_content["source"]
            publication_date = article_content["publication_date"]  # Get publication_date from the response
        else:
            source = self.extract_source(uri)
            publication_date = datetime.now(timezone.utc).date().isoformat()

        # Truncate article text to roughly fit within model's context length
        # Assuming average token length is ~4 characters, and leaving room for prompt
        max_chars = 65000  # This should be adapted to the model's context length
        if len(article_text) > max_chars:
            article_text = article_text[:max_chars] + "..."
            logger.info(f"Article text truncated to {max_chars} characters")

        # Improved title extraction
        title_prompt = f"""
        Extract or generate an appropriate title for the following article. Follow these guidelines:

        1. If there's a clear, existing title in the text, extract and use it.
        2. If there's no clear title, create a concise and informative title based on the main topic of the article.
        3. The title should be attention-grabbing but not clickbait.
        4. Keep the title under 15 words.
        5. Capitalize the first letter of each major word (except articles, conjunctions, and prepositions unless they're the first or last word).
        6. Do not use quotation marks in the title unless they're part of a quote that's central to the article.

        Article text:
        {article_text[:2000]}  # Using first 2000 characters to provide more context

        Respond with only the title, nothing else.
        """

        title_response = self.ai_model.generate_response([
            {"role": "system", "content": "You are an expert editor skilled at creating and extracting perfect titles for news articles."},
            {"role": "user", "content": title_prompt}
        ])
        title = title_response.strip()

        # Convert summary_length to words
        try:
            summary_length_words = int(summary_length)
        except ValueError:
            summary_length_words = 50  # Default to 50 words if conversion fails

        main_prompt = f"""
        Summarize the following news article in {summary_length} words, using the voice of a {summary_voice}.

        Title: {title}
        Source: {source}
        URL: {uri}
        Content: {article_text}

        Provide a summary with the following characteristics:
        Length: Maximum {summary_length_words} words
        Voice: {summary_voice}
        Type: {summary_type}

        Summarize the content using the specified characteristics. Format your response as follows:
        Summary: [Your summary here]

        Then, provide the following analyses:

        1. Category:
        Classify the article into one of these categories:
        {', '.join(self.CATEGORIES)}
        If none of these categories fit, suggest a new category or classify it as "Other".

        2. Future Signal:
        Classify the article into one of these Future Signals:
        {', '.join(self.FUTURE_SIGNALS)}
        Base your classification on the overall tone and content of the article regarding the future of AI.
        Provide a brief explanation for your classification.

        3. Sentiment:
        Classify the sentiment as one of:
        {', '.join(self.SENTIMENT)}
        Provide a brief explanation for your classification.

        4. Time to Impact:
        Classify the time to impact as one of:
        {', '.join(self.TIME_TO_IMPACT)}
        Provide a brief explanation for your classification.

        5. Driver Type:
        Classify the article into one of these Driver Types:
        {', '.join(self.DRIVER_TYPES)}
        Provide a brief explanation for your classification.

        6. Relevant tags:
        Generate 3-5 relevant tags for the article. These should be concise keywords or short phrases that capture the main topics or themes of the article.

        Format your response as follows:
        Title: [Your title here]
        Summary: [Your summary here]
        Category: [Your classification here]
        Future Signal: [Your classification here]
        Future Signal Explanation: [Your explanation here]
        Sentiment: [Your classification here]
        Sentiment Explanation: [Your explanation here]
        Time to Impact: [Your classification here]
        Time to Impact Explanation: [Your explanation here]
        Driver Type: [Your classification here]
        Driver Type Explanation: [Your explanation here]
        Tags: [tag1, tag2, tag3, ...]
        """

        analysis = self.ai_model.generate_response([
            {"role": "system", "content": f"You are an expert assistant that analyzes and summarizes articles. Provide summaries in the style of {summary_voice} and format of {summary_type}."},
            {"role": "user", "content": main_prompt}
        ])

        # Parse the analysis text to extract the required fields
        parsed_analysis = {}
        for line in analysis.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                parsed_analysis[key.strip()] = value.strip()

        # Verify summary length and truncate if necessary
        summary = parsed_analysis.get("Summary", "")
        summary_words = summary.split()
        if len(summary_words) > summary_length_words:
            summary = ' '.join(summary_words[:summary_length_words])

        return {
            "title": title,
            "news_source": source,
            "uri": uri,
            "summary": summary,
            "sentiment": parsed_analysis.get("Sentiment", ""),
            "sentiment_explanation": parsed_analysis.get("Sentiment Explanation", ""),
            "time_to_impact": parsed_analysis.get("Time to Impact", ""),
            "time_to_impact_explanation": parsed_analysis.get("Time to Impact Explanation", ""),
            "category": parsed_analysis.get("Category", ""),
            "future_signal": parsed_analysis.get("Future Signal", ""),
            "future_signal_explanation": parsed_analysis.get("Future Signal Explanation", ""),
            "publication_date": publication_date,
            "tags": parsed_analysis.get("Tags", "").strip('[]').replace(' ', '').split(','),
            "driver_type": parsed_analysis.get("Driver Type", ""),
            "driver_type_explanation": parsed_analysis.get("Driver Type Explanation", ""),
            "topic": topic  
        }

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

                # Extract the date from Firecrawl's output
                publication_date = scrape_result.get('date')
                logger.debug(f"Raw publication date from scraper: {publication_date}")
                
                if publication_date:
                    # Try to parse the date in various formats
                    for date_format in ['%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y']:
                        try:
                            parsed_date = datetime.strptime(publication_date, date_format)
                            publication_date = parsed_date.date().isoformat()
                            logger.debug(f"Successfully parsed date {publication_date} using format {date_format}")
                            break
                        except ValueError:
                            continue
                    else:
                        logger.warning(f"Could not parse date {publication_date}, using current date")
                        publication_date = datetime.now(timezone.utc).date().isoformat()
                else:
                    logger.info("No publication date provided, using current date")
                    publication_date = datetime.now(timezone.utc).date().isoformat()
            else:
                logger.error(f"Failed to fetch content for {uri}")
                content = "Failed to fetch article content."
                publication_date = datetime.now(timezone.utc).date().isoformat()

            source = self.extract_source(uri)
            logger.info(f"Article processing complete. Source: {source}, Publication date: {publication_date}")
            return {"content": content, "source": source, "publication_date": publication_date}
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
        if not self.available_models:
            raise ValueError("No AI models are configured. Please add a model in the configuration section.")
        if model_name not in [model['name'] for model in self.available_models]:
            raise ValueError(f"Model {model_name} is not configured. Please select a configured model.")
        self.ai_model = get_ai_model(model_name)

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










