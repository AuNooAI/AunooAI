from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime
from collections import defaultdict
import hashlib
import json

from app.security.session import verify_session
from app.database import Database, get_database_instance
from app.vector_store import get_chroma_client
from app.services.topic_map_service import TopicMapService

# Setup templates instance (shared throughout the app)
templates = Jinja2Templates(directory="templates")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/topic-map", tags=["topic-map"])

# Simple in-memory cache for reference graphs
_reference_graph_cache = {}
_cache_ttl = 300  # 5 minutes


def _get_cache_key(category: str, query: str, limit: int) -> str:
    """Generate a cache key for the reference graph."""
    cache_data = {
        'category': category or '',
        'query': query or '',
        'limit': limit
    }
    cache_str = json.dumps(cache_data, sort_keys=True)
    return hashlib.md5(cache_str.encode()).hexdigest()


def _get_cached_graph(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached reference graph if available and not expired."""
    if cache_key in _reference_graph_cache:
        cached_data, timestamp = _reference_graph_cache[cache_key]
        if datetime.now().timestamp() - timestamp < _cache_ttl:
            logger.info(
                f"Returning cached reference graph for key: {cache_key}"
            )
            return cached_data
        else:
            # Remove expired cache
            del _reference_graph_cache[cache_key]
    return None


def _cache_graph(cache_key: str, graph_data: Dict[str, Any]) -> None:
    """Cache the reference graph data."""
    _reference_graph_cache[cache_key] = (graph_data, datetime.now().timestamp())
    logger.info(f"Cached reference graph for key: {cache_key}")


@router.get("/generate")
async def generate_topic_map(
    topic_filter: Optional[str] = Query(None, description="Filter by topic"),
    category_filter: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(500, ge=10, le=2000, description="Maximum articles to analyze"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
) -> Dict[str, Any]:
    """Generate a topic map from ingested articles."""
    
    try:
        # Initialize services
        vector_store = get_chroma_client()
        topic_map_service = TopicMapService(db, vector_store)
        
        # Generate topic map
        result = topic_map_service.get_topic_map_data(
            topic_filter=topic_filter,
            category_filter=category_filter,
            limit=limit
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        logger.info(f"Generated topic map with {len(result.get('nodes', []))} nodes")
        return result
        
    except Exception as e:
        logger.error(f"Error generating topic map: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate topic map: {str(e)}")


@router.get("/topic-details/{topic_id}")
async def get_topic_details(
    topic_id: str,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
) -> Dict[str, Any]:
    """Get detailed information about a specific topic node."""
    
    try:
        vector_store = get_chroma_client()
        topic_map_service = TopicMapService(db, vector_store)
        
        # Get articles for context
        articles = topic_map_service.extract_topics_from_articles(limit=1000)
        
        # Get topic details
        details = topic_map_service.get_topic_details(topic_id, articles)
        
        return details
        
    except Exception as e:
        logger.error(f"Error getting topic details: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get topic details: {str(e)}")


@router.get("/statistics")
async def get_topic_statistics(
    topic_filter: Optional[str] = Query(None, description="Filter by topic"),
    category_filter: Optional[str] = Query(None, description="Filter by category"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
) -> Dict[str, Any]:
    """Get topic statistics for the current dataset."""
    
    try:
        vector_store = get_chroma_client()
        topic_map_service = TopicMapService(db, vector_store)
        
        # Extract articles
        articles = topic_map_service.extract_topics_from_articles(
            topic_filter=topic_filter,
            category_filter=category_filter,
            limit=2000
        )
        
        # Calculate statistics
        stats = topic_map_service._calculate_topic_statistics(articles)
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting statistics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@router.get("/filter-options")
async def get_filter_options(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
) -> Dict[str, Any]:
    """Get available topics and categories for filter dropdowns."""
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get unique topics
            cursor.execute("""
                SELECT DISTINCT topic 
                FROM articles 
                WHERE topic IS NOT NULL AND topic != '' AND analyzed = 1
                ORDER BY topic
            """)
            topics = [row[0] for row in cursor.fetchall()]
            
            # Get unique categories
            cursor.execute("""
                SELECT DISTINCT category 
                FROM articles 
                WHERE category IS NOT NULL AND category != '' AND analyzed = 1
                ORDER BY category
            """)
            categories = [row[0] for row in cursor.fetchall()]
            
            return {
                "topics": topics,
                "categories": categories
            }
            
    except Exception as e:
        logger.error(f"Error getting filter options: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get filter options: {str(e)}")


# ---------- UI Page ---------- #
page_router = APIRouter(tags=["topic-map-page"])


@page_router.get("/topic-map", response_class=HTMLResponse)
async def topic_map_visualization(
    request: Request,
    session=Depends(verify_session),
):
    """Render the interactive topic map visualization."""
    return templates.TemplateResponse(
        "topic_map.html",
        {
            "request": request,
            "session": request.session,
        },
    )


@page_router.get("/topic-map-editor", response_class=HTMLResponse)
async def topic_map_editor(
    request: Request,
    topic: str | None = None,
    session=Depends(verify_session),
):
    """Render the drag-and-drop topic map editor."""
    return templates.TemplateResponse(
        "topic_map_editor.html",
        {
            "request": request,
            "topic": topic,
            "session": request.session,
        },
    )


# Alias route with underscore for backwards-compatibility
@page_router.get(
    "/topic_map_editor",
    response_class=HTMLResponse,
)
async def topic_map_editor_alias(
    request: Request,
    topic: str | None = None,
    session=Depends(verify_session),
):
    """Alias to `topic_map_editor` using underscore URL."""
    return await topic_map_editor(request=request, topic=topic, session=session)


@router.post("/guided-generate")
async def generate_guided_topic_map(
    request: dict,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
) -> Dict[str, Any]:
    """Generate topic map using Guided BERTopic with seed topics."""
    
    try:
        # Extract parameters
        limit = request.get('limit', 500)
        topic_filter = request.get('topic_filter')
        category_filter = request.get('category_filter')
        seed_topics = request.get('seed_topics', [])
        
        if not seed_topics:
            return {"error": "Seed topics are required for guided modeling"}
        
        # Validate seed topics format
        if not isinstance(seed_topics, list) or not all(isinstance(topic, list) for topic in seed_topics):
            return {"error": "Seed topics must be a list of lists (e.g., [['ai', 'technology'], ['health', 'medical']])"}
        
        topic_map_service = TopicMapService(db, None)
        
        result = topic_map_service.get_topic_map_data(
            topic_filter=topic_filter,
            category_filter=category_filter,
            limit=limit,
            use_guided=True,
            seed_topics=seed_topics
        )
        
        logger.info(f"Generated guided topic map with {len(result.get('nodes', []))} nodes")
        return result
        
    except Exception as e:
        logger.error(f"Error generating guided topic map: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/visualizations")
async def get_topic_visualizations(
    limit: int = 100,
    topic_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
) -> Dict[str, Any]:
    """Get debugging visualizations for topic analysis."""
    
    try:
        topic_map_service = TopicMapService(db, None)
        
        # First get the basic topic map data
        articles = topic_map_service.extract_topics_from_articles(
            limit=limit,
            topic_filter=topic_filter,
            category_filter=category_filter
        )
        
        if not articles or len(articles) < 10:
            return {"error": "Not enough articles for visualization analysis"}
        
        # Try to build topic model for visualization
        if topic_map_service.embedding_model is None:
            return {"error": "BERTopic not available - visualizations require topic model"}
        
        # Build a topic model for visualization
        documents = [article['enhanced_text'] for article in articles]
        
        from bertopic import BERTopic
        from sklearn.feature_extraction.text import CountVectorizer
        from hdbscan import HDBSCAN
        from bertopic.representation import KeyBERTInspired
        
        # Quick topic model for visualization
        hdbscan_model = HDBSCAN(min_cluster_size=max(3, len(documents) // 20), min_samples=2)
        vectorizer_model = CountVectorizer(
            ngram_range=(1, 2),
            stop_words=list(topic_map_service.custom_stopwords),
            max_features=300,
            min_df=2,
            max_df=0.8
        )
        
        topic_model = BERTopic(
            embedding_model=topic_map_service.embedding_model,
            hdbscan_model=hdbscan_model,
            vectorizer_model=vectorizer_model,
            representation_model=KeyBERTInspired(),
            verbose=False
        )
        
        topics, _ = topic_model.fit_transform(documents)
        
        # Generate visualizations
        visualizations = topic_map_service.generate_topic_visualizations(articles, topic_model, topics)
        
        logger.info(f"Generated {len(visualizations)} visualization datasets")
        return {
            "visualizations": visualizations,
            "metadata": {
                "total_articles": len(articles),
                "total_topics": len(set(topics)),
                "generated_at": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating topic visualizations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug-info")
async def get_debug_info(
    limit: int = 50,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
) -> Dict[str, Any]:
    """Get debugging information about topic modeling setup."""
    
    try:
        topic_map_service = TopicMapService(db, None)
        
        # Check BERTopic availability
        bertopic_available = topic_map_service.embedding_model is not None
        
        # Get sample articles
        articles = topic_map_service.extract_topics_from_articles(limit=limit)
        
        # Analyze article content
        text_lengths = [len(article.get('text', '')) for article in articles]
        categories = list(set([article.get('category', 'Unknown') for article in articles]))
        topics = list(set([article.get('topic', 'Unknown') for article in articles]))
        
        # Check for problematic terms
        problematic_terms = []
        for article in articles[:10]:  # Sample check
            text = article.get('text', '').lower()
            if any(term in text for term in ['positive', 'negative', 'sentiment']):
                problematic_terms.append("Sentiment terms found in content")
            if any(term in text for term in ['driver', 'economic', 'social']):
                problematic_terms.append("Driver type terms found in content")
        
        return {
            "bertopic_available": bertopic_available,
            "embedding_model": "all-MiniLM-L6-v2" if bertopic_available else None,
            "custom_stopwords_count": len(topic_map_service.custom_stopwords),
            "article_analysis": {
                "total_articles": len(articles),
                "avg_text_length": sum(text_lengths) / len(text_lengths) if text_lengths else 0,
                "min_text_length": min(text_lengths) if text_lengths else 0,
                "max_text_length": max(text_lengths) if text_lengths else 0,
                "unique_categories": len(categories),
                "unique_topics": len(topics),
                "categories": categories[:10],  # First 10
                "topics": topics[:10]  # First 10
            },
            "potential_issues": list(set(problematic_terms)),
            "recommendations": [
                "Use guided modeling if specific topics are expected",
                "Ensure article summaries are substantial (>50 chars)",
                "Filter out metadata terms from article content",
                "Consider custom seed topics for domain-specific analysis"
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting debug info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reference-graph")
async def get_reference_graph(
    category: Optional[str] = Query(None, description="Root category filter"),
    query: Optional[str] = Query(None, description="Semantic query within category"),
    limit: int = Query(200, ge=10, le=1000, description="Maximum articles to analyze"),
    use_cache: bool = Query(True, description="Use cached results if available"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
) -> Dict[str, Any]:
    """Generate NotebookLM-style reference graph with user/LLM categories as root and BERTopic subclusters."""
    
    try:
        # Check cache first
        cache_key = _get_cache_key(category or '', query or '', limit)
        if use_cache:
            cached_result = _get_cached_graph(cache_key)
            if cached_result:
                return cached_result
        
        # Initialize services
        vector_store = get_chroma_client()
        topic_map_service = TopicMapService(db, vector_store)
        
        # Step 1: Get articles by category (or all if no category specified)
        articles = topic_map_service.extract_topics_from_articles(
            category_filter=category,
            limit=limit
        )
        
        if not articles:
            return {"error": "No articles found for the specified criteria"}
        
        # Step 2: Optional semantic filtering with vector search
        if query:
            filtered_articles = await _filter_articles_by_semantic_query(
                articles, query, vector_store, limit
            )
            if filtered_articles:
                articles = filtered_articles
        
        # Step 3: Build hierarchical reference graph
        reference_graph = await _build_reference_graph(articles, topic_map_service)
        
        # Cache the result
        if use_cache:
            _cache_graph(cache_key, reference_graph)
        
        logger.info(f"Generated reference graph with {len(reference_graph.get('nodes', []))} nodes")
        return reference_graph
        
    except Exception as e:
        logger.error(f"Error generating reference graph: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate reference graph: {str(e)}")


async def _filter_articles_by_semantic_query(
    articles: List[Dict[str, Any]], 
    query: str, 
    vector_store, 
    limit: int
) -> List[Dict[str, Any]]:
    """Filter articles using semantic similarity to query."""
    try:
        from app.vector_store import _embed_texts
        
        # Embed the query
        query_embedding = _embed_texts([query])[0]
        
        # Get article URIs for vector search
        article_uris = [article['uri'] for article in articles]
        
        # Perform vector search
        results = vector_store.query(
            query_embeddings=[query_embedding],
            n_results=min(limit, len(articles)),
            where={"uri": {"$in": article_uris}}
        )
        
        if results and results['ids']:
            # Create a set of relevant URIs
            relevant_uris = set()
            for ids_list in results['ids']:
                relevant_uris.update(ids_list)
            
            # Filter articles to only include semantically relevant ones
            filtered_articles = [
                article for article in articles 
                if article['uri'] in relevant_uris
            ]
            
            logger.info(f"Semantic filtering reduced articles from {len(articles)} to {len(filtered_articles)}")
            return filtered_articles
            
    except Exception as e:
        logger.warning(f"Semantic filtering failed: {e}")
    
    return articles


async def _build_reference_graph(
    articles: List[Dict[str, Any]], 
    topic_map_service: TopicMapService
) -> Dict[str, Any]:
    """Build NotebookLM-style reference graph with categories as root nodes."""
    
    nodes = []
    edges = []
    
    # Step 1: Group articles by user/LLM-defined categories (root level)
    category_groups = defaultdict(list)
    for i, article in enumerate(articles):
        category = article.get('category', 'General')
        category_groups[category].append(i)
    
    # Step 2: For each category, run BERTopic to get subclusters
    category_id = 0
    for category, article_indices in category_groups.items():
        if len(article_indices) < 3:  # Skip categories with too few articles
            continue
            
        # Create root category node
        category_node_id = f"cat_{category_id}"
        nodes.append({
            'id': category_node_id,
            'label': category,
            'type': 'category',
            'layer': 1,
            'size': min(100, 50 + len(article_indices) * 2),
            'color': _get_category_color(category_id),
            'article_count': len(article_indices),
            'expandable': True,
            'articles': article_indices
        })
        
        # Step 3: Run BERTopic on articles within this category
        category_articles = [articles[i] for i in article_indices]
        subclusters = await _create_bertopic_subclusters(
            category_articles, topic_map_service, category_node_id, category_id
        )
        
        # Add subcluster nodes and edges
        nodes.extend(subclusters['nodes'])
        edges.extend(subclusters['edges'])
        
        category_id += 1
    
    # Step 4: Add cross-category connections for related topics
    cross_connections = _create_cross_category_connections(nodes, articles)
    edges.extend(cross_connections)
    
    return {
        'nodes': nodes,
        'edges': edges,
        'metadata': {
            'total_articles': len(articles),
            'total_categories': len(category_groups),
            'method': 'NotebookLM-style Reference Graph',
            'generated_at': datetime.now().isoformat()
        }
    }


async def _create_bertopic_subclusters(
    category_articles: List[Dict[str, Any]], 
    topic_map_service: TopicMapService,
    parent_category_id: str,
    category_id: int
) -> Dict[str, Any]:
    """Create BERTopic subclusters within a category using title + summary."""
    
    nodes = []
    edges = []
    
    # Use BERTopic even for smaller categories (minimum 3 articles)
    if len(category_articles) < 3:
        # Only fall back for very small categories
        return _create_simple_subclusters(
            category_articles, parent_category_id, category_id
        )
    
    try:
        # Extract documents for BERTopic using title + summary for better clustering
        documents = []
        for article in category_articles:
            # Combine title and summary for better topic modeling
            title = article.get('title', '')
            summary = article.get('summary', '')
            text = article.get('text', '')
            
            # Prioritize title + summary, fall back to text if needed
            if title and summary:
                doc = f"{title}. {summary}"
            elif title:
                doc = title
            elif summary:
                doc = summary
            elif text:
                doc = text[:500]  # Use first 500 chars of text if no title/summary
            else:
                doc = "No content available"
            
            documents.append(doc)
        
        article_uris = [article['uri'] for article in category_articles]
        
        # Generate embeddings with multiple fallback options
        embeddings = None
        
        # Try to use existing embeddings first
        if hasattr(topic_map_service, '_leverage_existing_vectors'):
            try:
                embeddings = topic_map_service._leverage_existing_vectors(article_uris)
                if embeddings is not None:
                    logger.info(f"Using existing embeddings for {len(embeddings)} articles")
            except Exception as e:
                logger.warning(f"Failed to leverage existing vectors: {e}")
        
        # Generate new embeddings if needed
        if embeddings is None:
            if hasattr(topic_map_service, '_embed_documents_with_openai'):
                try:
                    embeddings = topic_map_service._embed_documents_with_openai(documents)
                    if embeddings is not None:
                        logger.info(f"Generated new embeddings for {len(embeddings)} documents")
                except Exception as e:
                    logger.warning(f"Failed to generate OpenAI embeddings: {e}")
        
        # Use sentence transformers as final fallback
        if embeddings is None:
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer('all-MiniLM-L6-v2')
                embeddings = model.encode(documents)
                logger.info(f"Generated sentence transformer embeddings for {len(embeddings)} documents")
            except Exception as e:
                logger.warning(f"Failed to generate sentence transformer embeddings: {e}")
        
        # Only fall back to sentiment clustering if all embedding methods fail
        if embeddings is None:
            logger.warning("All embedding methods failed, using fallback clustering")
            return _create_simple_subclusters(
                category_articles, parent_category_id, category_id
            )

        # Configure BERTopic for subclustering
        from bertopic import BERTopic
        from hdbscan import HDBSCAN
        from sklearn.feature_extraction.text import CountVectorizer
        from bertopic.representation import KeyBERTInspired
        from umap import UMAP
        
        # Adjust parameters based on dataset size to avoid scipy errors
        n_docs = len(documents)
        
        # For very small datasets, use different approach
        if n_docs < 10:
            # Use simple clustering for very small datasets
            return _create_simple_subclusters(
                category_articles, parent_category_id, category_id
            )
        
        # Configure UMAP to avoid dimensionality issues
        umap_model = UMAP(
            n_neighbors=min(5, n_docs - 1),
            n_components=min(5, n_docs - 1),
            min_dist=0.0,
            metric='cosine',
            random_state=42
        )
        
        # Configure HDBSCAN with safer parameters
        hdbscan_model = HDBSCAN(
            min_cluster_size=max(2, min(n_docs // 3, 5)),
            min_samples=1,
            metric='euclidean',
            cluster_selection_method='eom'
        )
        
        # Get custom stopwords if available
        custom_stopwords = list(topic_map_service.custom_stopwords) if hasattr(
            topic_map_service, 'custom_stopwords'
        ) else None
        
        vectorizer_model = CountVectorizer(
            ngram_range=(1, 2),
            stop_words=custom_stopwords,
            max_features=300,
            min_df=1,
            max_df=0.95
        )
        
        # Create topic model with proper dimensionality reduction
        topic_model = BERTopic(
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            vectorizer_model=vectorizer_model,
            representation_model=KeyBERTInspired(),
            verbose=False,
            calculate_probabilities=False
        )
        
        # Fit model with pre-computed embeddings
        topics, _ = topic_model.fit_transform(documents, embeddings)
        
        # Create subcluster nodes
        topic_info = topic_model.get_topic_info()
        topic_count = 0
        used_articles = set()  # Track articles already assigned to topics
        
        for _, row in topic_info.iterrows():
            topic_id = int(row['Topic'])
            if topic_id == -1:  # Skip outliers for now
                continue
                
            # Get articles in this topic, excluding already used ones
            topic_articles = [i for i, t in enumerate(topics) 
                            if t == topic_id and i not in used_articles]
            if len(topic_articles) < 1:  # Allow single-article topics for small datasets
                continue
            
            # Create beautiful topic label
            topic_words = topic_model.get_topic(topic_id)
            if topic_words:
                # Use LLM to create a beautiful label
                top_words = [word for word, score in topic_words[:3]]
                topic_label = await _beautify_topic_label(
                    top_words, category_articles, topic_articles
                )
                
                # Create topic node with unique ID
                topic_node_id = f"topic_{category_id}_{topic_count}"
                nodes.append({
                    'id': topic_node_id,
                    'label': topic_label,
                    'type': 'topic',
                    'layer': 2,
                    'size': min(70, 30 + len(topic_articles) * 3),
                    'color': _lighten_color(_get_category_color(category_id)),
                    'article_count': len(topic_articles),
                    'expandable': True,
                    'topic_words': top_words
                })
                
                # Connect to parent category
                edges.append({
                    'source': parent_category_id,
                    'target': topic_node_id,
                    'type': 'category_to_topic',
                    'weight': len(topic_articles)
                })
                
                # Create article leaf nodes and mark articles as used
                for article_idx in topic_articles:
                    article = category_articles[article_idx]
                    article_node_id = f"art_{category_id}_{topic_count}_{article_idx}"
                    
                    nodes.append({
                        'id': article_node_id,
                        'label': article['title'][:40] + (
                            '...' if len(article['title']) > 40 else ''
                        ),
                        'type': 'article',
                        'layer': 3,
                        'size': 20,
                        'color': '#F0F8FF',
                        'article_data': article,
                        'url': article.get('url', '#')
                    })
                    
                    edges.append({
                        'source': topic_node_id,
                        'target': article_node_id,
                        'type': 'topic_to_article'
                    })
                    
                    # Mark this article as used
                    used_articles.add(article_idx)
                
                topic_count += 1
        
        # Handle outliers (-1 topic) by creating an "Other" topic if significant
        outliers = [i for i, t in enumerate(topics) if t == -1 and i not in used_articles]
        if len(outliers) >= 1 and topic_count > 0:  # Allow single outlier topics
            topic_node_id = f"topic_{category_id}_other"
            nodes.append({
                'id': topic_node_id,
                'label': 'Other Topics',
                'type': 'topic',
                'layer': 2,
                'size': min(50, 25 + len(outliers) * 2),
                'color': _lighten_color(_get_category_color(category_id), 0.5),
                'article_count': len(outliers),
                'expandable': True,
                'topic_words': ['miscellaneous', 'various', 'other']
            })
            
            edges.append({
                'source': parent_category_id,
                'target': topic_node_id,
                'type': 'category_to_topic',
                'weight': len(outliers)
            })
            
            for article_idx in outliers:
                article = category_articles[article_idx]
                article_node_id = f"art_{category_id}_other_{article_idx}"
                
                nodes.append({
                    'id': article_node_id,
                    'label': article['title'][:40] + (
                        '...' if len(article['title']) > 40 else ''
                    ),
                    'type': 'article',
                    'layer': 3,
                    'size': 20,
                    'color': '#F5F5F5',
                    'article_data': article,
                    'url': article.get('url', '#')
                })
                
                edges.append({
                    'source': topic_node_id,
                    'target': article_node_id,
                    'type': 'topic_to_article'
                })
        
        # If no topics were created, fall back to simple clustering
        if topic_count == 0:
            logger.warning("BERTopic found no topics, using fallback clustering")
            return _create_simple_subclusters(
                category_articles, parent_category_id, category_id
            )
        
    except Exception as e:
        logger.warning(f"BERTopic subclustering failed: {e}")
        # Fallback to simple clustering
        return _create_simple_subclusters(
            category_articles, parent_category_id, category_id
        )
    
    return {'nodes': nodes, 'edges': edges}


def _create_simple_subclusters(
    category_articles: List[Dict[str, Any]],
    parent_category_id: str,
    category_id: int
) -> Dict[str, Any]:
    """Create content-based subclusters when BERTopic fails or for small categories."""
    
    nodes = []
    edges = []
    
    # Strategy 1: Create content-based topics using title + summary analysis
    from collections import Counter
    import re
    
    # For small categories, create meaningful groupings based on content themes
    if len(category_articles) <= 5:
        # Create a single comprehensive topic for very small categories
        topic_node_id = f"topic_{category_id}_0"
        
        # Create a meaningful label based on the category and content
        category_name = category_articles[0].get('category', 'General')
        topic_label = f"{category_name} Articles"
        
        nodes.append({
            'id': topic_node_id,
            'label': topic_label,
            'type': 'topic',
            'layer': 2,
            'size': min(60, 30 + len(category_articles) * 3),
            'color': _lighten_color(_get_category_color(category_id)),
            'article_count': len(category_articles),
            'expandable': True,
            'topic_words': [category_name.lower(), 'articles', 'content']
        })
        
        edges.append({
            'source': parent_category_id,
            'target': topic_node_id,
            'type': 'category_to_topic',
            'weight': len(category_articles)
        })
        
        # Add all articles to this topic
        for i, article in enumerate(category_articles):
            article_node_id = f"art_{category_id}_0_{i}"
            
            nodes.append({
                'id': article_node_id,
                'label': article['title'][:40] + (
                    '...' if len(article['title']) > 40 else ''
                ),
                'type': 'article',
                'layer': 3,
                'size': 20,
                'color': '#F0F8FF',
                'article_data': article,
                'url': article.get('url', '#')
            })
            
            edges.append({
                'source': topic_node_id,
                'target': article_node_id,
                'type': 'topic_to_article'
            })
        
        return {'nodes': nodes, 'edges': edges}
    
    # For larger categories, try to find meaningful themes
    # Extract key terms from titles and summaries
    all_words = []
    article_keywords = []
    
    # Enhanced stopwords list
    stopwords = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 
        'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 
        'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'who', 'boy', 
        'did', 'she', 'use', 'way', 'will', 'with', 'this', 'that', 'they',
        'from', 'have', 'more', 'what', 'were', 'been', 'said', 'each', 'which',
        'their', 'time', 'would', 'there', 'could', 'other', 'after', 'first',
        'well', 'water', 'very', 'what', 'know', 'just', 'where', 'most', 'some'
    }
    
    for article in category_articles:
        title = article.get('title', '')
        summary = article.get('summary', '')
        text = f"{title} {summary}".lower()
        
        # Extract meaningful words (3+ chars, not in stopwords)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
        words = [w for w in words if w not in stopwords]
        
        article_keywords.append(words)
        all_words.extend(words)
    
    # Find most common meaningful keywords
    word_counts = Counter(all_words)
    common_words = [word for word, count in word_counts.most_common(8) if count >= 2]
    
    # Group articles by dominant keywords
    keyword_groups = defaultdict(list)
    used_articles = set()
    
    for keyword in common_words:
        for i, keywords in enumerate(article_keywords):
            if i not in used_articles and keyword in keywords:
                keyword_groups[keyword].append(i)
                used_articles.add(i)
    
    # Create remaining articles group
    remaining_articles = [i for i in range(len(category_articles)) if i not in used_articles]
    
    topic_count = 0
    
    # Create keyword-based topics
    for keyword, article_indices in keyword_groups.items():
        if len(article_indices) >= 2:
            topic_node_id = f"topic_{category_id}_{topic_count}"
            
            # Create a nice label for the keyword
            keyword_label = keyword.title()
            if len(keyword) > 15:
                keyword_label = keyword[:15] + "..."
            
            nodes.append({
                'id': topic_node_id,
                'label': keyword_label,
                'type': 'topic',
                'layer': 2,
                'size': min(60, 30 + len(article_indices) * 2),
                'color': _lighten_color(_get_category_color(category_id)),
                'article_count': len(article_indices),
                'expandable': True,
                'topic_words': [keyword, 'content', 'analysis']
            })
            
            edges.append({
                'source': parent_category_id,
                'target': topic_node_id,
                'type': 'category_to_topic',
                'weight': len(article_indices)
            })
            
            # Add articles
            for idx in article_indices:
                article = category_articles[idx]
                article_node_id = f"art_{category_id}_{topic_count}_{idx}"
                
                nodes.append({
                    'id': article_node_id,
                    'label': article['title'][:40] + (
                        '...' if len(article['title']) > 40 else ''
                    ),
                    'type': 'article',
                    'layer': 3,
                    'size': 20,
                    'color': '#F0F8FF',
                    'article_data': article,
                    'url': article.get('url', '#')
                })
                
                edges.append({
                    'source': topic_node_id,
                    'target': article_node_id,
                    'type': 'topic_to_article'
                })
            
            topic_count += 1
    
    # Handle remaining articles
    if len(remaining_articles) >= 2 or (len(remaining_articles) > 0 and topic_count == 0):
        # If we have no other topics, include all remaining articles
        topic_node_id = f"topic_{category_id}_{topic_count}"
        
        nodes.append({
            'id': topic_node_id,
            'label': "General Discussion",
            'type': 'topic',
            'layer': 2,
            'size': min(60, 30 + len(remaining_articles) * 2),
            'color': _lighten_color(_get_category_color(category_id)),
            'article_count': len(remaining_articles),
            'expandable': True,
            'topic_words': ['general', 'various', 'topics']
        })
        
        edges.append({
            'source': parent_category_id,
            'target': topic_node_id,
            'type': 'category_to_topic',
            'weight': len(remaining_articles)
        })
        
        for idx in remaining_articles:
            article = category_articles[idx]
            article_node_id = f"art_{category_id}_{topic_count}_{idx}"
            
            nodes.append({
                'id': article_node_id,
                'label': article['title'][:40] + (
                    '...' if len(article['title']) > 40 else ''
                ),
                'type': 'article',
                'layer': 3,
                'size': 20,
                'color': '#F0F8FF',
                'article_data': article,
                'url': article.get('url', '#')
            })
            
            edges.append({
                'source': topic_node_id,
                'target': article_node_id,
                'type': 'topic_to_article'
            })
    
    # If still no topics created, create a single topic with all articles
    if len(nodes) == 0:
        topic_node_id = f"topic_{category_id}_0"
        
        nodes.append({
            'id': topic_node_id,
            'label': "All Articles",
            'type': 'topic',
            'layer': 2,
            'size': min(60, 30 + len(category_articles) * 2),
            'color': _lighten_color(_get_category_color(category_id)),
            'article_count': len(category_articles),
            'expandable': True,
            'topic_words': ['articles', 'content', 'information']
        })
        
        edges.append({
            'source': parent_category_id,
            'target': topic_node_id,
            'type': 'category_to_topic',
            'weight': len(category_articles)
        })
        
        for i, article in enumerate(category_articles):
            article_node_id = f"art_{category_id}_0_{i}"
            
            nodes.append({
                'id': article_node_id,
                'label': article['title'][:40] + (
                    '...' if len(article['title']) > 40 else ''
                ),
                'type': 'article',
                'layer': 3,
                'size': 20,
                'color': '#F0F8FF',
                'article_data': article,
                'url': article.get('url', '#')
            })
            
            edges.append({
                'source': topic_node_id,
                'target': article_node_id,
                'type': 'topic_to_article'
            })
    
    return {'nodes': nodes, 'edges': edges}


async def _beautify_topic_label(
    top_words: List[str], 
    category_articles: List[Dict[str, Any]], 
    topic_articles: List[int]
) -> str:
    """Use LLM to create beautiful topic labels from keywords."""
    try:
        # Sample article titles from this topic for context
        sample_titles = [category_articles[i]['title'] for i in topic_articles[:3]]
        
        # Try to use LLM service if available
        try:
            from app.services.topic_map_service import TopicMapService
            service = TopicMapService(None, None)  # We only need the labeling method
            
            # Get category context
            category_context = None
            if category_articles and topic_articles:
                category_context = category_articles[topic_articles[0]].get('category', 'General')
            
            # Use the enhanced LLM labeling
            return await service.beautify_topic_label_with_llm(
                top_words, sample_titles, category_context
            )
        except Exception as llm_error:
            logger.warning(f"LLM topic labeling failed: {llm_error}")
            # Fall back to heuristic labeling
            pass
        
        # Fallback heuristic labeling
        if len(top_words) >= 2:
            primary_word = top_words[0].title()
            secondary_word = top_words[1].title()
            
            # Simple heuristics for better labels
            if any(word in top_words for word in ['ai', 'artificial', 'intelligence']):
                return f"AI & {secondary_word}"
            elif any(word in top_words for word in ['market', 'business', 'economic']):
                return f"Market {secondary_word}"
            elif any(word in top_words for word in ['social', 'society', 'people']):
                return f"Social {secondary_word}"
            else:
                return f"{primary_word} & {secondary_word}"
        else:
            return top_words[0].title() if top_words else "Unnamed Topic"
            
    except Exception as e:
        logger.warning(f"Topic label beautification failed: {e}")
        return " & ".join(word.title() for word in top_words[:2]) if top_words else "Unnamed Topic"


def _create_cross_category_connections(
    nodes: List[Dict[str, Any]], 
    articles: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Create connections between related topics across categories."""
    edges = []
    
    # Find topic nodes
    topic_nodes = [node for node in nodes if node['type'] == 'topic']
    
    # Create connections based on shared keywords
    for i, node1 in enumerate(topic_nodes):
        for node2 in topic_nodes[i+1:]:
            if node1.get('topic_words') and node2.get('topic_words'):
                # Check for shared words
                words1 = set(node1['topic_words'])
                words2 = set(node2['topic_words'])
                shared_words = words1.intersection(words2)
                
                if len(shared_words) >= 1:  # At least one shared word
                    edges.append({
                        'source': node1['id'],
                        'target': node2['id'],
                        'type': 'cross_category_relation',
                        'weight': len(shared_words),
                        'style': 'dashed',
                        'color': '#CCCCCC'
                    })
    
    return edges


def _get_category_color(category_id: int) -> str:
    """Get distinct colors for categories."""
    colors = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
        '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9'
    ]
    return colors[category_id % len(colors)]


def _lighten_color(hex_color: str, factor: float = 0.3) -> str:
    """Lighten a hex color."""
    try:
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        
        return f'#{r:02x}{g:02x}{b:02x}'
    except Exception:
        return '#E0E0E0'


@page_router.get("/reference-graph", response_class=HTMLResponse)
async def reference_graph_page(
    request: Request,
    session=Depends(verify_session),
):
    """Render the NotebookLM-style reference graph visualization page."""
    return templates.TemplateResponse(
        "reference_graph.html",
        {
            "request": request,
            "session": request.session,
        },
    ) 