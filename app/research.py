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
    
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Research:
    def __init__(self, db=None):
        if db is None:
            self.db = Database()
        else:
            self.db = db
        self.load_config()
        if not os.path.exists('.env'):
            raise FileNotFoundError("The .env file does not exist. Please create it and add the necessary environment variables.")
        load_dotenv()
        self.available_models = ai_get_available_models()
        self.ai_model = None  # We'll set this when a model is selected
        self.firecrawl_app = self.initialize_firecrawl()

    def load_config(self):
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.json')
        logger.debug(f"Loading config from: {config_path}")
        with open(config_path, 'r') as f:
            config = json.load(f)
        self.CATEGORIES = config['categories']
        logger.debug(f"Loaded categories: {self.CATEGORIES}")
        self.FUTURE_SIGNALS = config['future_signals']
        self.SENTIMENT = config['sentiment']
        self.TIME_TO_IMPACT = config['time_to_impact']
        self.DRIVER_TYPES = config['driver_types']

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
            article_exists = self.check_article_exists(uri)
            
            if article_exists:
                logger.info(f"Article already exists in database: {uri}")
                return {"exists": True, "uri": uri}
            
            logger.info(f"Article does not exist in database, scraping: {uri}")
            # If the article doesn't exist, proceed with scraping
            scrape_result = self.firecrawl_app.scrape_url(
                uri,
                params={
                    'formats': ['markdown']
                }
            )
            
            logger.debug(f"Scrape result: {scrape_result}")
            
            if 'markdown' in scrape_result:
                content = scrape_result['markdown']
                # Save the raw markdown
                self.db.save_raw_article(uri, content)
                # Extract the date from Firecrawl's output
                publication_date = scrape_result.get('date')
                if publication_date:
                    # Try to parse the date in various formats
                    for date_format in ['%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y']:
                        try:
                            parsed_date = datetime.strptime(publication_date, date_format)
                            publication_date = parsed_date.date().isoformat()
                            break
                        except ValueError:
                            continue
                    else:
                        # If no format matches, use current date
                        publication_date = datetime.now(timezone.utc).date().isoformat()
                else:
                    # If no date is provided, use current date
                    publication_date = datetime.now(timezone.utc).date().isoformat()
            else:
                logger.error(f"Failed to fetch content for {uri}")
                content = "Failed to fetch article content."
                publication_date = datetime.now(timezone.utc).date().isoformat()

            source = self.extract_source(uri)
            return {"content": content, "source": source, "publication_date": publication_date}
        except Exception as e:
            logger.error(f"Error fetching article content: {str(e)}", exc_info=True)
            return {"content": "Failed to fetch article content.", "source": self.extract_source(uri), "publication_date": datetime.now(timezone.utc).date().isoformat()}

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
        # Set the AI model based on the selected model_name
        self.set_ai_model(model_name)

        if not article_text:
            article_text, source, publication_date = await self.fetch_article_content(uri)
        else:
            source = self.extract_source(uri)
            publication_date = datetime.now(timezone.utc).date().isoformat()

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
        Positive, Neutral, Negative
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
            "topic": topic  # Make sure this line is present
        }

    def extract_source(self, uri):
        domain = urlparse(uri).netloc
        return domain.replace('www.', '')

    async def get_recent_articles(self, limit=10):
        return self.db.get_recent_articles(limit)

    async def save_article(self, article_data):
        # Ensure all required fields are present
        required_fields = ['title', 'uri', 'news_source', 'summary', 'sentiment', 'time_to_impact', 
                           'category', 'future_signal', 'future_signal_explanation', 'publication_date', 
                           'sentiment_explanation', 'time_to_impact_explanation', 'tags', 'driver_type', 'driver_type_explanation']
        
        for field in required_fields:
            if field not in article_data:
                raise ValueError(f"Missing required field: {field}")

        # Convert tags list to string if necessary
        if isinstance(article_data['tags'], list):
            article_data['tags'] = ','.join(article_data['tags'])
        
        return await self.db.save_article(article_data)

    async def get_categories(self):
        logger.debug(f"get_categories called, returning: {self.CATEGORIES}")
        return self.CATEGORIES

    async def get_future_signals(self):
        return self.FUTURE_SIGNALS + ["New", "Other"]

    async def get_sentiments(self):
        return self.SENTIMENT + ["New", "Other"]

    async def get_time_to_impact(self):
        return self.TIME_TO_IMPACT + ["New", "Other"]

    async def get_driver_types(self):
        return self.DRIVER_TYPES + ["New", "Other"]

    async def get_article(self, uri: str):
        return self.db.get_article(uri)

    def delete_article(self, uri):
        return self.db.delete_article(uri)

    async def scrape_article(self, uri: str):
        """Scrape the article using Firecrawl."""
        try:
            scrape_result = self.firecrawl_app.scrape_url(
                uri,
                params={
                    'formats': ['markdown']
                }
            )
            
            if 'markdown' in scrape_result:
                content = scrape_result['markdown']
                # Save the raw markdown
                self.db.save_raw_article(uri, content)
                # Extract the date from Firecrawl's output
                publication_date = scrape_result.get('date')
                if publication_date:
                    # Try to parse the date in various formats
                    for date_format in ['%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y']:
                        try:
                            parsed_date = datetime.strptime(publication_date, date_format)
                            publication_date = parsed_date.date().isoformat()
                            break
                        except ValueError:
                            continue
                    else:
                        # If no format matches, use current date
                        publication_date = datetime.now(timezone.utc).date().isoformat()
                else:
                    # If no date is provided, use current date
                    publication_date = datetime.now(timezone.utc).date().isoformat()
            else:
                logger.error(f"Failed to fetch content for {uri}")
                content = "Failed to fetch article content."
                publication_date = datetime.now(timezone.utc).date().isoformat()

            source = self.extract_source(uri)
            return {"content": content, "source": source, "publication_date": publication_date}
        except Exception as e:
            logger.error(f"Error scraping article: {str(e)}")
            return {"content": "Failed to scrape article content.", "source": self.extract_source(uri), "publication_date": datetime.now(timezone.utc).date().isoformat()}

    def get_topics(self):
        return self.db.get_topics()

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
