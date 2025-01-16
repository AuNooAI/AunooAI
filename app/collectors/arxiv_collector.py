import arxiv
from datetime import datetime
from typing import List, Dict, Optional
from .base_collector import ArticleCollector
import logging
from app.models.topic import Topic

logger = logging.getLogger(__name__)

class ArxivCollector(ArticleCollector):
    """ArXiv article collector implementation."""
    
    def __init__(self):
        self.client = arxiv.Client()
        # Mapping of our topics to arXiv categories
        self.topic_category_mapping = {
            "AI and Machine Learning": [
                "cs.AI",  # Artificial Intelligence
                "cs.LG",  # Machine Learning
                "cs.CL",  # Computation and Language
                "cs.CV",  # Computer Vision
                "cs.NE",  # Neural and Evolutionary Computing
                "cs.RO",  # Robotics
            ],
            "Cloud Computing": [
                "cs.DC",  # Distributed Computing
                "cs.NI",  # Networking and Internet Architecture
                "cs.OS",  # Operating Systems
                "cs.PF",  # Performance
            ]
        }

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Search ArXiv articles."""
        try:
            # Get arXiv categories for the topic
            categories = self.topic_category_mapping.get(topic, [
                "cs.AI",  # Artificial Intelligence
                "cs.LG",  # Machine Learning
                "cs.CL",  # Computation and Language
                "cs.CV",  # Computer Vision
                "cs.NE",  # Neural and Evolutionary Computing
                "cs.RO",  # Robotics
            ])
            if not categories:
                logger.warning(f"No ArXiv categories mapped for topic: {topic}")
                return []

            # Build the search query
            search_query = f"{query} AND ("
            search_query += " OR ".join(f"cat:{cat}" for cat in categories)
            search_query += ")"

            # Create the search
            search = arxiv.Search(
                query=search_query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate
            )

            results = []
            # Replace async for with regular iteration
            for result in self.client.results(search):
                # Filter by date if specified
                if start_date and result.published < start_date:
                    continue
                if end_date and result.published > end_date:
                    continue

                article = {
                    'title': result.title,
                    'summary': result.summary,
                    'authors': [author.name for author in result.authors],
                    'published_date': result.published.isoformat(),  # Convert to ISO format string
                    'url': result.pdf_url,  # Using PDF URL as main URL
                    'source': 'arxiv',
                    'topic': topic,
                    'raw_data': {
                        'arxiv_id': result.entry_id,
                        'primary_category': result.primary_category,
                        'categories': result.categories,
                        'links': {
                            'abstract': result.entry_id,
                            'pdf': result.pdf_url,
                        }
                    }
                }
                results.append(article)

            return results

        except Exception as e:
            logger.error(f"Error searching ArXiv: {str(e)}")
            return []

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Fetch article content from ArXiv."""
        try:
            # Extract arxiv ID from URL
            arxiv_id = url.split('/')[-1]
            search = arxiv.Search(id_list=[arxiv_id])
            
            # Replace async for with getting first result
            results = list(self.client.results(search))
            if results:
                result = results[0]
                return {
                    'title': result.title,
                    'content': result.summary,  # ArXiv provides abstract as content
                    'authors': [author.name for author in result.authors],
                    'published_date': result.published.isoformat(),  # Convert to ISO format string
                    'url': result.pdf_url,
                    'source': 'arxiv',
                    'raw_data': {
                        'arxiv_id': result.entry_id,
                        'primary_category': result.primary_category,
                        'categories': result.categories
                    }
                }
            
            return None

        except Exception as e:
            logger.error(f"Error fetching ArXiv article: {str(e)}")
            return None

    def get_latest_papers(self, topic: Topic, count: int = 5) -> List[Dict]:
        if not hasattr(topic, 'arxiv_categories') or not topic.arxiv_categories:
            # Use default categories if none are specified
            categories = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE", "cs.RO"]
        else:
            categories = topic.arxiv_categories
        
        category_filter = " OR ".join(f"cat:{cat}" for cat in categories)
        query = f"{topic.paper_query} AND ({category_filter})"