import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
import pandas as pd
from pydantic import BaseModel, Field
import os
import asyncio
from dotenv import load_dotenv
from app.database import Database
from app.config.config import load_config, get_topic_config

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class Article(BaseModel):
    """Pydantic model for article data"""
    uri: str
    title: Optional[str] = None
    news_source: Optional[str] = None
    publication_date: Optional[str] = None
    submission_date: Optional[str] = None
    summary: Optional[str] = None
    topic: Optional[str] = None
    topic_alignment_score: Optional[float] = None
    keyword_relevance_score: Optional[float] = None
    confidence_score: Optional[float] = None
    overall_match_explanation: Optional[str] = None
    extracted_article_topics: Optional[List[str]] = None
    extracted_article_keywords: Optional[List[str]] = None

class ArticleProcessor:
    def __init__(self):
        self.db = Database()
        self.config = load_config()
        self.topics = {topic['name']: topic for topic in self.config.get('topics', [])}
        
    def extract_from_input(self, input_file: str) -> List[Article]:
        """Extract article data from input file"""
        logger.debug(f"Reading input file: {input_file}")
        df = pd.read_csv(input_file)
        articles = []
        
        for _, row in df.iterrows():
            try:
                article = Article(
                    uri=row['url'],
                    title=row.get('title'),
                    news_source=row.get('source'),
                    publication_date=row.get('publication_date'),
                    summary=row.get('summary')
                )
                articles.append(article)
            except Exception as e:
                logger.error(f"Error processing row: {e}")
                continue
                
        return articles

    async def scrape_article(self, article: Article) -> Optional[str]:
        """Scrape article content using BrightData API"""
        logger.debug(f"Scraping article: {article.uri}")
        
        try:
            url = "https://api.brightdata.com/datasets/v3/trigger"
            headers = {
                "Authorization": f"Bearer {os.getenv('BRIGHTDATA_API_KEY')}",
                "Content-Type": "application/json",
            }
            params = {
                "dataset_id": os.getenv('BRIGHTDATA_DATASET_ID'),
                "include_errors": "true",
            }
            data = {
                "deliver": {
                    "type": "s3",
                    "filename": {"template": "{[snapshot_id]}", "extension": "json"},
                    "bucket": "",
                    "directory": ""
                },
                "input": [{"url": article.uri}]
            }

            response = requests.post(url, headers=headers, params=params, json=data)
            if response.status_code != 200:
                logger.error(f"BrightData API error: {response.text}")
                return None

            content = response.json().get('content')
            if not content:
                logger.error("No content returned from BrightData API")
                return None

            return content

        except Exception as e:
            logger.error(f"Error scraping article: {e}")
            return None

    def assess_relevance(self, article: Article, content: str) -> Article:
        """Assess article relevance using existing keyword monitoring system"""
        logger.debug(f"Assessing relevance for article: {article.uri}")
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get all keyword groups and their keywords
                cursor.execute("""
                    SELECT kg.id, kg.topic, mk.keyword
                    FROM keyword_groups kg
                    JOIN monitored_keywords mk ON kg.group_id = kg.id
                """)
                keyword_data = cursor.fetchall()
                
                # Group keywords by topic
                topic_keywords = {}
                for group_id, topic, keyword in keyword_data:
                    if topic not in topic_keywords:
                        topic_keywords[topic] = {'keywords': [], 'group_ids': set()}
                    topic_keywords[topic]['keywords'].append(keyword)
                    topic_keywords[topic]['group_ids'].add(group_id)
                
                # Find best matching topic
                best_topic = None
                best_score = 0
                best_keywords = []
                best_group_id = None
                
                for topic, data in topic_keywords.items():
                    keywords = data['keywords']
                    matched_keywords = []
                    
                    # Check for keyword matches in title and content
                    for keyword in keywords:
                        if (
                            (article.title and keyword.lower() in article.title.lower()) or
                            (content and keyword.lower() in content.lower())
                        ):
                            matched_keywords.append(keyword)
                    
                    # Calculate relevance score
                    score = len(matched_keywords) / len(keywords) if keywords else 0
                    
                    if score > best_score:
                        best_score = score
                        best_topic = topic
                        best_keywords = matched_keywords
                        best_group_id = next(iter(data['group_ids']))  # Use first group ID for the topic
                
                if best_topic and best_score > 0:
                    article.topic = best_topic
                    article.keyword_relevance_score = best_score
                    article.topic_alignment_score = best_score  # For simplicity, use same score
                    article.confidence_score = best_score
                    article.overall_match_explanation = f"Matched {len(best_keywords)} keywords: {', '.join(best_keywords)}"
                    article.extracted_article_keywords = best_keywords
                    
                    # Save keyword matches
                    if best_group_id:
                        keyword_ids = []
                        for keyword in best_keywords:
                            cursor.execute(
                                "SELECT id FROM monitored_keywords WHERE group_id = ? AND keyword = ?",
                                (best_group_id, keyword)
                            )
                            result = cursor.fetchone()
                            if result:
                                keyword_ids.append(str(result[0]))
                        
                        if keyword_ids:
                            cursor.execute("""
                                INSERT INTO keyword_article_matches (
                                    article_uri, keyword_ids, group_id, detected_at
                                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                            """, (article.uri, ','.join(keyword_ids), best_group_id))
                
                return article

        except Exception as e:
            logger.error(f"Error assessing relevance: {e}")
            return article

    def save_to_database(self, article: Article, content: str) -> bool:
        """Save article and raw content to database"""
        logger.debug(f"Saving article to database: {article.uri}")
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Save article
                cursor.execute("""
                    INSERT INTO articles (
                        uri, title, news_source, publication_date, submission_date,
                        summary, topic, topic_alignment_score, keyword_relevance_score,
                        confidence_score, overall_match_explanation,
                        extracted_article_topics, extracted_article_keywords
                    ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    article.uri, article.title, article.news_source,
                    article.publication_date, article.summary, article.topic,
                    article.topic_alignment_score, article.keyword_relevance_score,
                    article.confidence_score, article.overall_match_explanation,
                    json.dumps(article.extracted_article_topics or []),
                    json.dumps(article.extracted_article_keywords or [])
                ))
                
                # Save raw content
                cursor.execute("""
                    INSERT INTO raw_articles (
                        uri, raw_markdown, submission_date, topic
                    ) VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                """, (article.uri, content, article.topic))
                
                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Error saving to database: {e}")
            return False

async def main():
    """Main function to run the article processing pipeline"""
    try:
        # Initialize processor
        processor = ArticleProcessor()
        
        # Process input file
        input_file = "input_articles.csv"  # Update with your input file path
        articles = processor.extract_from_input(input_file)
        
        logger.info(f"Processing {len(articles)} articles")
        
        for article in articles:
            try:
                # Scrape content
                content = await processor.scrape_article(article)
                if not content:
                    logger.warning(f"Could not scrape content for {article.uri}")
                    continue
                
                # Assess relevance
                article = processor.assess_relevance(article, content)
                
                # Save to database
                if processor.save_to_database(article, content):
                    logger.info(f"Successfully processed article: {article.uri}")
                else:
                    logger.error(f"Failed to save article: {article.uri}")
                
            except Exception as e:
                logger.error(f"Error processing article {article.uri}: {e}")
                continue
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 