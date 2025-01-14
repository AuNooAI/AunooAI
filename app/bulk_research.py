from typing import List, Dict
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from app.research import Research
from app.database import Database
from app.analysis_types import get_analysis_type
from app.ai_models import get_ai_model
import logging
import traceback
import datetime
import json

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

                # Analyze article
                result = await self.research.analyze_article(
                    uri=url,
                    article_text=article_content["content"],
                    summary_length=summary_length,
                    summary_voice=summary_voice,
                    summary_type=summary_type,
                    topic=topic,
                    model_name=model_name
                )

                # Add news source and submission date
                result["news_source"] = self.extract_source(url)
                result["submission_date"] = datetime.datetime.now().date().isoformat()
                results.append(result)
                logger.debug(f"Successfully analyzed URL: {url}")
                
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
                    "publication_date": "N/A",
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

    def parse_analysis(self, analysis: str, summary_type: str) -> Dict:
        if summary_type == "curious_ai":
            return self.parse_curious_ai_analysis(analysis)
        elif summary_type == "axios":
            return self.parse_axios_analysis(analysis)
        else:
            raise ValueError(f"Unknown summary type: {summary_type}")

    def parse_curious_ai_analysis(self, analysis: str) -> Dict:
        parsed_analysis = {}
        for line in analysis.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                parsed_analysis[key.strip()] = value.strip()

        return {
            "title": parsed_analysis.get("Title", ""),
            "summary": parsed_analysis.get("Summary", ""),
            "news_source": parsed_analysis.get("Source", ""),
            "category": parsed_analysis.get("Category", ""),
            "future_signal": parsed_analysis.get("Future Signal", ""),
            "future_signal_explanation": parsed_analysis.get("Future Signal Explanation", ""),
            "sentiment": parsed_analysis.get("Sentiment", ""),
            "sentiment_explanation": parsed_analysis.get("Sentiment Explanation", ""),
            "time_to_impact": parsed_analysis.get("Time to Impact", ""),
            "time_to_impact_explanation": parsed_analysis.get("Time to Impact Explanation", ""),
            "driver_type": parsed_analysis.get("Driver Type", ""),
            "driver_type_explanation": parsed_analysis.get("Driver Type Explanation", ""),
            "tags": parsed_analysis.get("Tags", "").strip('[]').replace(' ', '').split(','),
            #"topic": topic  
        }

    def parse_axios_analysis(self, analysis: str) -> Dict:
        parsed_analysis = {}
        current_key = None
        for line in analysis.split('\n'):
            if line.startswith('Headline:'):
                parsed_analysis['title'] = line.split(':', 1)[1].strip()
            elif line.startswith('Main Point:'):
                parsed_analysis['summary'] = line.split(':', 1)[1].strip()
            elif line.startswith('Key Takeaways:'):
                current_key = 'key_takeaways'
                parsed_analysis[current_key] = []
            elif line.startswith('Go deeper:'):
                parsed_analysis['go_deeper'] = line.split(':', 1)[1].strip()
            elif line.strip().startswith('•') and current_key == 'key_takeaways':
                parsed_analysis[current_key].append(line.strip()[2:].strip())

        return parsed_analysis
