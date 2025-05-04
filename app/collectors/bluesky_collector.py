import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from .base_collector import ArticleCollector
from atproto import Client
from atproto.exceptions import AtProtocolError


logger = logging.getLogger(__name__)


def serialize_bluesky_data(obj: Any) -> Any:
    """
    Custom serializer to handle Bluesky specific data types like IpldLink.
    Converts objects to serializable types for JSON.
    """
    if hasattr(obj, 'to_dict'):
        # Convert any object with to_dict method
        return obj.to_dict()
    elif hasattr(obj, '__dict__'):
        # Convert any object with __dict__ attribute 
        return obj.__dict__
    elif hasattr(obj, 'cid') and hasattr(obj, 'json'):
        # Handle IPLD Link objects which have cid and json methods
        return str(obj.cid)
    elif isinstance(obj, (list, tuple)):
        # Handle lists/tuples
        return [serialize_bluesky_data(item) for item in obj]
    elif isinstance(obj, dict):
        # Handle dictionaries
        return {k: serialize_bluesky_data(v) for k, v in obj.items()}
    else:
        # Return primitive types as is
        return obj


class BlueskyCollector(ArticleCollector):
    """Collector for Bluesky social network posts."""

    def __init__(self):
        self.username = os.getenv('PROVIDER_BLUESKY_USERNAME')
        self.password = os.getenv('PROVIDER_BLUESKY_PASSWORD')
        if not self.username or not self.password:
            logger.error("Bluesky credentials not found in environment")
            raise ValueError("Bluesky credentials not configured")
        
        self.client = Client()
        self._auth()

    def _auth(self):
        """Authenticate with Bluesky."""
        try:
            self.client.login(self.username, self.password)
            logger.info(
                f"Successfully authenticated to Bluesky as {self.username}"
            )
        except Exception as e:
            logger.error(f"Failed to authenticate to Bluesky: {str(e)}")
            raise ValueError(f"Bluesky authentication failed: {str(e)}")

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        language: str = None,
        sort_by: str = None,
        limit_to_followed: bool = False,
        search_fields: Optional[List[str]] = None,
        domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        **kwargs
    ) -> List[Dict]:
        """
        Search for Bluesky posts based on query and topic.
        
        Args:
            query: Search query string
            topic: Topic name from the application's topics
            max_results: Maximum number of results to return
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            language: Optional language filter (not used in Bluesky API)
            sort_by: Optional sorting method
            limit_to_followed: Only show posts from followed accounts
            search_fields: Optional fields to search in (not used in Bluesky API)
            domains: Optional domains to include (not used in Bluesky API)
            exclude_domains: Optional domains to exclude (not used in Bluesky API)
            **kwargs: Additional parameters (ignored)
            
        Returns:
            List of standardized article dictionaries
        """
        try:
            logger.info(f"Searching Bluesky for '{query}' on topic '{topic}'")
            
            # Check if authentication is valid, reauth if needed
            if not hasattr(self.client, 'me') or not self.client.me:
                self._auth()
            
            # Search posts using the Bluesky API
            params = {
                "q": query,
                "limit": max_results
            }
            
            # Add sort_by if specified (latest, trending, relevant)
            if sort_by:
                # Map sort options to what Bluesky API expects
                sort_mapping = {
                    "latest": "latest",
                    "trending": "trending", 
                    "relevant": "relevance",
                    "relevancy": "relevance"
                }
                if sort_by.lower() in sort_mapping:
                    params["sort"] = sort_mapping[sort_by.lower()]
            
            # Set limit_to_followed if specified
            if limit_to_followed:
                params["followersOf"] = self.client.me.did
                
            # Log the search parameters
            logger.debug(f"Searching Bluesky with params: {params}")
            
            response = self.client.app.bsky.feed.search_posts(params=params)
            
            if not response or not hasattr(response, 'posts'):
                logger.warning(f"No posts found for query '{query}'")
                return []
                
            posts = response.posts
            logger.info(
                f"Found {len(posts)} Bluesky posts for query '{query}'"
            )
            
            articles = []
            for post in posts:
                # Extract post data
                try:
                    # Use serialize_bluesky_data to ensure JSON-serializable output
                    serialized_post = serialize_bluesky_data(post)
                    
                    # Now work with the serialized post data
                    # Parse Bluesky post into our standard format
                    article = {
                        'title': f"Post by @{post.author.handle}",
                        'summary': (
                            post.record.text 
                            if hasattr(post.record, 'text') else ""
                        ),
                        'authors': [
                            post.author.display_name or post.author.handle
                        ],
                        'published_date': post.indexed_at,
                        'url': (
                            f"https://bsky.app/profile/{post.author.handle}/"
                            f"post/{post.uri.split('/')[-1]}"
                        ),
                        'source': 'bluesky',
                        'topic': topic,
                        'raw_data': {
                            'uri': str(post.uri),
                            'cid': str(post.cid),
                            'author_did': post.author.did,
                            'author_handle': post.author.handle,
                            'images': [],
                            'likes': getattr(post, 'like_count', 0),
                            'reposts': getattr(post, 'repost_count', 0),
                        }
                    }
                    
                    # Extract images if present
                    if (hasattr(post.record, 'embed') and 
                            hasattr(post.record.embed, 'images')):
                        article['raw_data']['images'] = [
                            {
                                'alt': img.alt if hasattr(img, 'alt') else '',
                                'url': str(img.image.ref) if hasattr(img.image, 'ref') else ''
                            }
                            for img in post.record.embed.images
                        ]
                    
                    articles.append(article)
                except Exception as e:
                    logger.error(f"Error processing Bluesky post: {str(e)}")
                    continue
                    
            return articles
                
        except AtProtocolError as e:
            logger.error(f"Bluesky API error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error searching Bluesky: {str(e)}")
            return []

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """
        Fetch full content of a Bluesky post.
        
        Args:
            url: Bluesky post URL
            
        Returns:
            Dictionary containing post content and metadata
        """
        try:
            # Extract post URI from URL
            # URL format: 
            # https://bsky.app/profile/username.bsky.social/post/3kl5gveb2pa2r
            parts = url.split('/')
            if len(parts) < 6:
                logger.error(f"Invalid Bluesky URL format: {url}")
                return None
                
            handle = parts[-3]
            post_id = parts[-1]
            
            # Resolve the DID for the handle
            try:
                params = {"handle": handle}
                did_response = self.client.com.atproto.identity.resolve_handle(
                    params=params
                )
                did = did_response.did
            except Exception as e:
                logger.error(
                    f"Could not resolve DID for handle {handle}: {str(e)}"
                )
                return None
            
            # Get the post
            post_uri = f"at://{did}/app.bsky.feed.post/{post_id}"
            thread_params = {"uri": post_uri}
            thread = self.client.app.bsky.feed.get_post_thread(
                params=thread_params
            )
            
            if (not thread or not hasattr(thread, 'thread') or 
                    not hasattr(thread.thread, 'post')):
                logger.error(f"Could not fetch post: {url}")
                return None
                
            post = thread.thread.post
            
            # Serialize the response to ensure it's JSON compatible
            serialized_post = serialize_bluesky_data(post)
            serialized_thread = serialize_bluesky_data(thread)
            
            return {
                'title': f"Post by @{post.author.handle}",
                'content': (
                    post.record.text 
                    if hasattr(post.record, 'text') else ""
                ),
                'authors': [post.author.display_name or post.author.handle],
                'published_date': post.indexed_at,
                'url': url,
                'source': 'bluesky',
                'raw_data': {
                    'uri': str(post.uri),
                    'cid': str(post.cid),
                    'thread': [
                        {
                            'text': reply.post.record.text if hasattr(reply.post.record, 'text') else "",
                            'author': reply.post.author.handle,
                            'indexed_at': reply.post.indexed_at
                        }
                        for reply in thread.thread.replies 
                        if hasattr(reply, 'post')
                    ] if hasattr(thread.thread, 'replies') else []
                }
            }
            
        except Exception as e:
            logger.error(f"Error fetching Bluesky post content: {str(e)}")
            return None 