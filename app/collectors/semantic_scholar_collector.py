import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from .base_collector import ArticleCollector
import logging
import os

logger = logging.getLogger(__name__)

class SemanticScholarCollector(ArticleCollector):
    """Semantic Scholar article collector implementation."""

    def __init__(self):
        self.api_key = os.getenv('SEMANTIC_SCHOLAR_API_KEY')  # Optional
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        self.requests_today = 0  # Track API requests for compatibility with keyword monitor

        # Mapping of our topics to Semantic Scholar fieldsOfStudy
        self.topic_field_mapping = {
            "magic and occultism": ["Psychology", "Sociology", "History", "Philosophy"],
            "AI and Machine Learning": ["Computer Science"],
            "Cloud Computing": ["Computer Science"],
            "Blockchain": ["Computer Science", "Economics"],
            "Quantum Computing": ["Computer Science", "Physics"],
            "Cybersecurity": ["Computer Science"],
            "Biotechnology": ["Biology", "Medicine"],
            "Climate Change": ["Environmental Science", "Geography"],
            "Neuroscience": ["Medicine", "Psychology", "Biology"],
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
        """Search Semantic Scholar papers using relevance search endpoint."""
        try:
            # Convert string dates to timezone-aware datetime objects
            now = datetime.now(timezone.utc)

            if start_date:
                if isinstance(start_date, str):
                    try:
                        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        start_dt = now - timedelta(days=30)  # Default to 30 days
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

            # Build API parameters
            params = {
                'query': query,
                'fields': 'title,abstract,authors,year,venue,url,paperId,publicationDate,citationCount,fieldsOfStudy',
                'limit': min(max_results, 100),  # API max is 100 per request
                'offset': 0
            }

            # Add fieldsOfStudy filter if topic has mapping
            if topic and topic in self.topic_field_mapping:
                fields = self.topic_field_mapping[topic]
                params['fieldsOfStudy'] = ','.join(fields)
                logger.info(f"Filtering Semantic Scholar search by fields: {fields}")

            # Add date range filter (format: YYYY-MM-DD:YYYY-MM-DD)
            date_range = f"{start_dt.strftime('%Y-%m-%d')}:{end_dt.strftime('%Y-%m-%d')}"
            params['publicationDateOrYear'] = date_range

            # Build headers
            headers = {}
            if self.api_key:
                headers['x-api-key'] = self.api_key
                logger.info("Using Semantic Scholar API key")
            else:
                logger.info("Using Semantic Scholar without API key (rate limits apply)")

            logger.info(f"Searching Semantic Scholar: query='{query}', date_range={date_range}")

            # Make API request
            self.requests_today += 1  # Increment request counter
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/paper/search",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:

                    if response.status == 429:
                        logger.warning("Semantic Scholar rate limit hit - consider adding API key")
                        return []

                    if response.status == 400:
                        error_text = await response.text()
                        logger.error(f"Semantic Scholar bad request: {error_text}")
                        return []

                    if response.status == 404:
                        logger.warning(f"Semantic Scholar returned 404 for query: {query}")
                        return []

                    if response.status != 200:
                        logger.error(f"Semantic Scholar API error: {response.status}")
                        return []

                    data = await response.json()
                    papers = data.get('data', [])
                    total = data.get('total', 0)

                    logger.info(f"Found {len(papers)} papers from Semantic Scholar (total available: {total})")

                    # Format to standard format
                    results = []
                    for paper in papers:
                        formatted = self._format_article(paper, topic)
                        if formatted:
                            results.append(formatted)

                    return results

        except aiohttp.ClientError as e:
            logger.error(f"Network error searching Semantic Scholar: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error searching Semantic Scholar: {str(e)}")
            return []

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """
        Fetch article metadata from Semantic Scholar.
        Note: Semantic Scholar does not provide full-text content.
        """
        try:
            # Extract paper ID from URL if it's a Semantic Scholar URL
            paper_id = None
            if 'semanticscholar.org/paper/' in url:
                paper_id = url.split('/paper/')[-1].split('?')[0]
            else:
                # Can't fetch non-S2 URLs
                return None

            # Build headers
            headers = {}
            if self.api_key:
                headers['x-api-key'] = self.api_key

            # Fetch paper details
            self.requests_today += 1  # Increment request counter
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/paper/{paper_id}",
                    params={'fields': 'title,abstract,authors,year,venue,url,publicationDate,citationCount'},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:

                    if response.status != 200:
                        logger.error(f"Error fetching Semantic Scholar paper {paper_id}: {response.status}")
                        return None

                    paper = await response.json()

                    # Format response
                    authors = []
                    if paper.get('authors'):
                        authors = [a.get('name', '') for a in paper['authors']]

                    return {
                        'title': paper.get('title', ''),
                        'content': paper.get('abstract', ''),  # S2 provides abstract as content
                        'authors': authors,
                        'published_date': paper.get('publicationDate', ''),
                        'url': paper.get('url', url),
                        'source': 'semantic_scholar',
                        'raw_data': {
                            'paper_id': paper.get('paperId', ''),
                            'citation_count': paper.get('citationCount', 0),
                            'venue': paper.get('venue', ''),
                            'year': paper.get('year', '')
                        }
                    }

        except Exception as e:
            logger.error(f"Error fetching Semantic Scholar article: {str(e)}")
            return None

    def _format_article(self, article: Dict, topic: str) -> Optional[Dict]:
        """Format Semantic Scholar response to standard project format."""
        try:
            # Extract authors
            authors = []
            if article.get('authors'):
                authors = [a.get('name', '') for a in article['authors']]

            # Get URL (construct from paperId if not provided)
            url = article.get('url')
            if not url and article.get('paperId'):
                url = f"https://www.semanticscholar.org/paper/{article['paperId']}"

            # Format publication date (already in ISO format if present)
            pub_date = article.get('publicationDate', '')
            if not pub_date and article.get('year'):
                pub_date = f"{article['year']}-01-01"

            # Require at least a title
            if not article.get('title'):
                return None

            return {
                'title': article.get('title', ''),
                'summary': article.get('abstract', ''),
                'authors': authors,
                'published_date': pub_date,
                'url': url,
                'source': 'semantic_scholar',
                'topic': topic,
                'raw_data': {
                    'paper_id': article.get('paperId', ''),
                    'citation_count': article.get('citationCount', 0),
                    'venue': article.get('venue', ''),
                    'year': article.get('year', ''),
                    'fields_of_study': article.get('fieldsOfStudy', []),
                    'source_name': 'Semantic Scholar'
                }
            }
        except Exception as e:
            logger.error(f"Error formatting Semantic Scholar article: {str(e)}")
            return None
