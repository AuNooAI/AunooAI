import arxiv
from datetime import datetime, timezone, timedelta
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
        end_date: Optional[datetime] = None,
        language: Optional[str] = None,
        sort_by: Optional[str] = None,
        search_fields: Optional[List[str]] = None,
        page: Optional[int] = None,
        **kwargs
    ) -> List[Dict]:
        """Search ArXiv articles."""
        try:
            # Convert string dates to timezone-aware datetime objects and adjust future dates
            now = datetime.now(timezone.utc)
            
            if start_date:
                if isinstance(start_date, str):
                    try:
                        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        start_dt = now - timedelta(days=30)
                else:
                    start_dt = start_date
                start_dt = start_dt.replace(tzinfo=timezone.utc)
                if start_dt > now:
                    start_dt = now - timedelta(days=30)
            else:
                start_dt = now - timedelta(days=30)

            if end_date:
                if isinstance(end_date, str):
                    try:
                        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        end_dt = now
                else:
                    end_dt = end_date
                end_dt = end_dt.replace(tzinfo=timezone.utc)
                if end_dt > now:
                    end_dt = now
            else:
                end_dt = now

            # Build search query parts
            search_query_parts = []
            
            # Add date range to query
            date_query = f"submittedDate:[{start_dt.strftime('%Y%m%d')}0000 TO {end_dt.strftime('%Y%m%d')}2359]"
            search_query_parts.append(date_query)

            # Add field-specific searches
            if search_fields:
                field_mapping = {
                    'title': 'ti',
                    'abstract': 'abs',
                    'author': 'au',
                    'comments': 'co',
                    'journal_ref': 'jr'
                }
                
                field_queries = []
                for field in search_fields:
                    if field in field_mapping:
                        field_queries.append(f"{field_mapping[field]}:{query}")
                if field_queries:
                    search_query_parts.append(f"({' OR '.join(field_queries)})")
            else:
                search_query_parts.append(f"all:{query}")

            # Add category filters
            categories = self.topic_category_mapping.get(topic, [
                "cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE", "cs.RO"
            ])
            category_filter = " OR ".join(f"cat:{cat}" for cat in categories)
            if category_filter:
                search_query_parts.append(f"({category_filter})")

            # Combine all parts
            final_query = " AND ".join(f"({part})" for part in search_query_parts if part)
            
            logger.info(f"Final arXiv query: {final_query}")

            # Map sort_by to arxiv.SortCriterion
            sort_criterion = arxiv.SortCriterion.Relevance
            if sort_by:
                sort_mapping = {
                    'relevance': arxiv.SortCriterion.Relevance,
                    'lastUpdatedDate': arxiv.SortCriterion.LastUpdatedDate,
                    'submittedDate': arxiv.SortCriterion.SubmittedDate
                }
                sort_criterion = sort_mapping.get(sort_by, arxiv.SortCriterion.Relevance)

            # Create the search
            search = arxiv.Search(
                query=final_query,
                max_results=max_results,
                sort_by=sort_criterion
            )

            results = []
            for result in self.client.results(search):
                article = {
                    'title': result.title,
                    'summary': result.summary,
                    'authors': [author.name for author in result.authors],
                    'published_date': result.published.isoformat(),
                    'url': result.entry_id,
                    'source': 'arXiv',
                    'topic': topic,
                    'raw_data': {
                        'arxiv_id': result.entry_id,
                        'primary_category': result.primary_category,
                        'categories': result.categories,
                        'links': {
                            'abstract': result.entry_id,
                            'pdf': result.pdf_url,
                        },
                        'source_name': 'arXiv'
                    }
                }
                results.append(article)
                
                if len(results) >= max_results:
                    break

            logger.info(f"Found {len(results)} articles matching criteria")
            return results

        except Exception as e:
            logger.error(f"Error searching ArXiv: {str(e)}")
            raise ValueError(f"ArXiv search failed: {str(e)}")

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