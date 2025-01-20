from typing import List, Dict
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from app.research import Research
from app.database import Database
from app.ai_models import get_ai_model
from app.analyzers.article_analyzer import ArticleAnalyzer
import logging
import traceback
import datetime
import json
import os

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class BulkResearch:
    def __init__(self, db):
        logger.debug("Initializing BulkResearch class")
        logger.debug(f"Input db type: {type(db)}")
        
        try:
            if isinstance(db, Session):
                # Create a new Database instance without passing the session
                self.db = Database()
                self.session = db
            elif isinstance(db, Database):
                self.db = db
                self.session = None
            else:
                raise TypeError(f"Expected Session or Database, got {type(db)}")
            
            # Create Research instance with the appropriate db object
            self.research = Research(self.db)
            logger.debug("BulkResearch initialized successfully")
            
        except Exception as e:
            logger.error(f"Error in BulkResearch initialization: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    async def analyze_bulk_urls(self, urls: List[str], summary_type: str, 
                                 model_name: str, summary_length: str, 
                                 summary_voice: str, topic: str) -> List[Dict]:
        results = []
        logger.info(f"Starting analysis of {len(urls)} URLs with topic: {topic}")
        
        try:
            # Set the topic before starting analysis
            self.research.set_topic(topic)
            self.research.set_ai_model(model_name)
            
            # Create cache directory if it doesn't exist
            os.makedirs("cache", exist_ok=True)
            
            # Initialize ArticleAnalyzer with the AI model
            self.article_analyzer = ArticleAnalyzer(self.research.ai_model)
            
        except Exception as e:
            logger.error(f"Error setting up analysis: {str(e)}")
            raise ValueError(f"Error in setup: {str(e)}")

        for url in urls:
            try:
                logger.debug(f"Processing URL: {url} for topic: {topic}")
                
                # Fetch article content
                article_content = await self.research.fetch_article_content(url)
                if not article_content or not article_content.get("content"):
                    raise ValueError(f"Failed to fetch content for URL: {url}")

                # Extract title if not present
                title = article_content.get("title", "")
                if not title:
                    title = self.article_analyzer.extract_title(article_content["content"])

                # Get publication date from article_content
                publication_date = self.article_analyzer.extract_publication_date(article_content["content"])

                # Analyze article using ArticleAnalyzer
                result = self.article_analyzer.analyze_content(
                    article_text=article_content["content"],
                    title=title,
                    source=self.extract_source(url),
                    uri=url,
                    summary_length=int(summary_length),
                    summary_voice=summary_voice,
                    summary_type=summary_type,
                    categories=self.research.CATEGORIES,
                    future_signals=self.research.FUTURE_SIGNALS,
                    sentiment_options=self.research.SENTIMENT,
                    time_to_impact_options=self.research.TIME_TO_IMPACT,
                    driver_types=self.research.DRIVER_TYPES
                )

                logger.debug(f"Analysis result for {url}: {json.dumps(result, indent=2)}")

                # Add news source, publication date and submission date
                result["news_source"] = self.extract_source(url)
                result["publication_date"] = publication_date
                result["submission_date"] = datetime.datetime.now().date().isoformat()
                result["uri"] = url  # Ensure URL is included
                results.append(result)
                logger.debug(f"Successfully analyzed URL: {url}")
                logger.debug(f"Final result with metadata: {json.dumps(result, indent=2)}")
                
            except Exception as e:
                logger.error(f"Error processing URL {url}: {str(e)}")
                logger.error(traceback.format_exc())
                
                results.append({
                    "uri": url,
                    "error": str(e),
                    "title": "Error",
                    "summary": f"Failed to analyze: {str(e)}",
                    "sentiment": "N/A",
                    "future_signal": "N/A",
                    "future_signal_explanation": "N/A",
                    "time_to_impact": "N/A",
                    "time_to_impact_explanation": "N/A",
                    "driver_type": "N/A",
                    "driver_type_explanation": "N/A",
                    "category": "N/A",
                    "tags": [],
                    "news_source": "N/A",
                    "publication_date": self.article_analyzer.extract_publication_date(""),  # Will return today's date as fallback
                    "submission_date": datetime.datetime.now().date().isoformat(),
                    "topic": topic
                })

        logger.info(f"Completed analysis of {len(urls)} URLs")
        return results

    async def save_bulk_articles(self, articles: List[Dict]) -> Dict:
        results = {
            "success": [],
            "errors": []
        }
        
        for article in articles:
            try:
                logger.debug(f'Attempting to save article: {article}')
                
                # Validate required fields
                required_fields = [
                    'title', 'uri', 'news_source', 'summary', 'sentiment', 'time_to_impact',
                    'category', 'future_signal', 'future_signal_explanation', 'publication_date',
                    'sentiment_explanation', 'time_to_impact_explanation', 'tags', 'driver_type',
                    'driver_type_explanation', 'submission_date', 'topic'
                ]
                
                # Validate required fields
                missing_fields = [field for field in required_fields if not article.get(field)]
                if missing_fields:
                    raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
                
                # Format tags if they're a string
                if isinstance(article['tags'], str):
                    article['tags'] = [tag.strip() for tag in article['tags'].split(',') if tag.strip()]
                
                # Ensure dates are in ISO format
                for date_field in ['publication_date', 'submission_date']:
                    if article.get(date_field):
                        try:
                            # Try to parse and reformat the date
                            date_obj = datetime.fromisoformat(article[date_field].replace('Z', '+00:00'))
                            article[date_field] = date_obj.date().isoformat()
                        except (ValueError, AttributeError):
                            logger.warning(f"Invalid date format for {date_field}: {article[date_field]}")
                            article[date_field] = datetime.datetime.now().date().isoformat()

                # Use the research instance to save the article
                saved_article = await self.research.save_article(article)
                logger.info(f"Successfully saved article: {article['uri']}")
                results["success"].append(saved_article)
                
            except Exception as e:
                logger.error(f"Error saving article {article.get('uri', 'Unknown URL')}: {str(e)}")
                logger.error(f"Article data: {json.dumps(article, indent=2)}")
                results["errors"].append({
                    "uri": article.get('uri', 'Unknown URL'),
                    "error": str(e)
                })
        
        return results
    
    def extract_source(self, uri):
        domain = urlparse(uri).netloc
        return domain.replace('www.', '')

    def set_ai_model(self, model_name: str):
        self.ai_model = get_ai_model(model_name)
