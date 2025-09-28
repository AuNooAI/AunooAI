from typing import Optional, Dict, Any, List
import logging
from dateutil.parser import parse as dt_parse  # add top of file
import json
from pathlib import Path
import os
import urllib.parse

from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.security.session import verify_session, verify_session_optional
from app.vector_store import (
    search_articles,
    upsert_article,
    similar_articles,
    _get_collection as _vector_collection,
    get_chroma_client,
)
from app.database import Database, get_database_instance

# Heavy numeric/ML dependencies are imported lazily inside the functions that
# need them.  This avoids hard runtime failures when the optional packages are
# not installed and keeps the application lightweight for routes that do not
# rely on them.

router = APIRouter(prefix="/api", tags=["vector-search"])

logger = logging.getLogger(__name__)


@router.get("/vector-search")
def vector_search_endpoint(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(100, ge=1),
    topic: Optional[str] = None,
    category: Optional[str] = None,
    future_signal: Optional[str] = None,
    sentiment: Optional[str] = None,
    news_source: Optional[str] = None,
    cluster: Optional[int] = None,
    session=Depends(verify_session),
):
    """Semantic search endpoint backed by ChromaDB.

    Optional topic, category, future_signal and sentiment parameters map to
    metadata filters to narrow the search space. The query string can include
    KISSQL syntax for advanced filtering and logic operations.
    """
    # Import the KISSQL module
    from app.kissql.parser import parse_full_query, Constraint, MetaControl
    from app.kissql.executor import execute_query
    
    # Parse the query using KISSQL
    query_obj = parse_full_query(q)
    
    # Log the incoming parameters and parsed query for debugging
    logger = logging.getLogger(__name__)
    logger.info(
        "Vector search: q=%s, topic=%s, category=%s, sentiment=%s",
        q, topic, category, sentiment
    )
    logger.info(
        "Also news_source=%s, cluster=%s",
        news_source, cluster
    )
    logger.info(
        "Parsed %d constraints and %d meta controls", 
        len(query_obj.constraints), 
        len(query_obj.meta_controls)
    )
    
    # Check if parameters are already in constraints to avoid double filtering
    existing_fields = {
        constraint.field.lower(): constraint.value 
        for constraint in query_obj.constraints 
        if constraint.operator == '='
    }
    
    # Add any query parameters that were passed explicitly and not already 
    # present
    if topic and 'topic' not in existing_fields:
        query_obj.constraints.append(
            Constraint(field="topic", operator="=", value=topic)
        )
    if category and 'category' not in existing_fields:
        query_obj.constraints.append(
            Constraint(field="category", operator="=", value=category)
        )
    if future_signal and 'future_signal' not in existing_fields:
        query_obj.constraints.append(
            Constraint(
                field="future_signal", 
                operator="=", 
                value=future_signal
            )
        )
    if sentiment and 'sentiment' not in existing_fields:
        query_obj.constraints.append(
            Constraint(field="sentiment", operator="=", value=sentiment)
        )
    if news_source and 'news_source' not in existing_fields:
        query_obj.constraints.append(
            Constraint(field="news_source", operator="=", value=news_source)
        )
    
    # Add the cluster parameter if it was passed explicitly
    if cluster is not None:
        query_obj.meta_controls.append(
            MetaControl(name='cluster', value=str(cluster))
        )

    # Execute the query using the KISSQL executor
    result = execute_query(query_obj, top_k=top_k)
    
    # Ensure we return a JSON response with the expected structure
    return JSONResponse(
        content={
            "results": result.get("results", []),
            "facets": result.get("facets", {}),
            "timeline": result.get("timeline", {}),
            "comparison": result.get("comparison", {}),
            "filtered_facets": result.get("filtered_facets", {})
        }
    )


@router.post("/vector-reindex")
async def vector_reindex(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session),
):
    """Re-index all articles currently stored in the relational DB.

    Returns the number of articles sent to the vector store.  This can be
    triggered after first enabling Chroma or when the collection has been
    wiped.
    """
    articles = db.get_all_articles()
    indexed = 0
    for article in articles:
        try:
            upsert_article(article)
            indexed += 1
        except Exception as exc:  # pragma: no cover – continue on error
            print(f"Vector upsert failed for {article.get('uri')}: {exc}")
    return {"indexed": indexed, "total": len(articles)}


# ------------------------------------------------------------------
# Similar articles endpoint (nearest neighbours)
# ------------------------------------------------------------------


@router.get("/vector-similar")
def vector_similar_endpoint(
    uri: str = Query(..., description="Article URI"),
    top_k: int = Query(5, ge=1, le=50),
    session=Depends(verify_session),
):
    """Return *top_k* articles most similar to the article with *uri*."""
    return {
        "results": similar_articles(uri, top_k=top_k),
    }


# ------------------------------------------------------------------
# Embedding visualisation helpers & endpoints
# ------------------------------------------------------------------


# Helper to fetch vectors with optional metadata filter.
# Split parameters onto separate lines to satisfy line-length limit.

def _fetch_vectors(
    limit: int | None = None,
    where: Optional[Dict[str, Any]] = None,
):
    """Return `(vectors, metadatas, ids)` truncated to *limit* items.

    Vectors are returned as an ``np.ndarray`` of shape ``(n, dim)`` to
    allow efficient downstream numeric work.  We always request
    *embeddings* and *metadatas* so callers can build richer responses.
    """
    import numpy as np  # Local import to avoid module-level dependency

    collection = _vector_collection()
    try:
        kw = {"include": ["embeddings", "metadatas"]}
        if limit:
            kw["limit"] = limit  # type: ignore[assignment]
        if where:
            kw["where"] = where  # type: ignore[assignment]
        res = collection.get(**kw)  # type: ignore[arg-type]
    except Exception as exc:  # Fallback – corrupted records without embeddings
        logging.getLogger(__name__).error(
            "Chroma get() failed: %s", exc
        )
        return np.empty((0, 0), dtype=np.float32), [], []

    vectors = np.asarray(res.get("embeddings", []), dtype=np.float32)
    metadatas = res.get("metadatas", [])
    ids = res.get("ids", [])
    return vectors, metadatas, ids


@router.get("/embedding_projection")
def embedding_projection(
    q: Optional[str] = Query(None, description="Search query"),
    method: str = Query(
        "umap",
        regex="^(umap|tsne|pca)$",
        description="Dimensionality reduction method",
    ),
    dims: int = Query(
        2,
        ge=2,
        le=3,
        description="Output dimensionality (2 or 3)",
    ),
    top_k: int = Query(
        2500,
        ge=10,
        le=10000,
        description="Number of points to project",
    ),
    n_clusters: int = Query(
        30,
        ge=2,
        le=5000,
        description="Desired cluster count (k-means)",
    ),
    topic: Optional[str] = None,
    category: Optional[str] = None,
    future_signal: Optional[str] = None,
    sentiment: Optional[str] = None,
    news_source: Optional[str] = None,
    session=Depends(verify_session),
) -> Dict[str, Any]:
    """Return a 2-D UMAP projection together with a lightweight cluster label.

    The caller receives a JSON list of objects – *one per vector* – each
    containing ``id``, ``x``, ``y``, ``cluster`` and a couple of handy
    metadata fields (currently ``title``).
    """
    # Set up logging outside try block to ensure it's always available
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Embedding projection called with query: {q or 'None'}")
        
        # Build metadata filter 
        where = None
        if any([topic, category, sentiment, news_source, future_signal]):
            where = {}
            if topic:
                where["topic"] = topic
            if category:
                where["category"] = category
            if sentiment:
                where["sentiment"] = sentiment
            if news_source:
                where["news_source"] = news_source
            if future_signal:
                where["future_signal"] = future_signal
        
        # Handle pipe operators through executor if present
        if q and "|" in q:
            from app.kissql.parser import parse_full_query
            from app.kissql.executor import execute_query
            
            logger.info("Query contains pipe operators")
            
            # Parse and execute the query with KISSQL
            query_obj = parse_full_query(q)
            result = execute_query(query_obj, top_k=top_k)
            
            # Extract IDs from the filtered results
            filtered_results = result.get("results", [])
            filtered_ids = [r["id"] for r in filtered_results]
            
            # Handle case with no results after filtering
            if not filtered_ids:
                logger.warning("No results after pipe filtering")
                return {"points": [], "explain": {}, "centroids": {}}
                
            # Add URI filter to where clause
            if where is None:
                where = {}
            where["uri"] = {"$in": filtered_ids}
            
            logger.info(f"Applied pipe filtering: {len(filtered_ids)} results")

        # Get vectors from Chroma – fetch a bit more than requested but cap at 10k
        fetch_limit = min(max(top_k * 2, 5000), 10000)

        vecs, metas, ids = _fetch_vectors(limit=fetch_limit, where=where)
        logger.info(f"📦 Fetched {len(vecs) if vecs.size > 0 else 0} vectors from database")
        
        if vecs.size == 0:
            logger.warning("⚠️ No vectors found!")
            return {"points": [], "explain": {}, "centroids": {}}
        
        # Log data characteristics
        logger.info(f"📊 Processing {len(vecs)} vectors with shape {vecs.shape}")
        logger.info(f"💾 Memory usage: {vecs.nbytes / 1024 / 1024:.1f} MB")
        
        # Auto-downsample large datasets for performance
        MAX_UMAP_SIZE = 5000  # UMAP becomes very slow above this
        if len(vecs) > MAX_UMAP_SIZE and method == "umap":
            logger.warning(f"⚡ Dataset too large ({len(vecs)} > {MAX_UMAP_SIZE}), downsampling for performance...")
            
            # Stratified sampling to preserve data distribution
            import numpy as np
            np.random.seed(42)  # Reproducible sampling
            indices = np.random.choice(len(vecs), size=MAX_UMAP_SIZE, replace=False)
            indices = np.sort(indices)  # Keep original order
            
            vecs = vecs[indices]
            metas = [metas[i] for i in indices]
            ids = [ids[i] for i in indices]
            
            logger.info(f"📉 Downsampled to {len(vecs)} vectors for UMAP performance")
        
        # Projection
        from sklearn.cluster import MiniBatchKMeans
        import numpy as np
        
        # Choose reducer based on method
        if method == "tsne":
            from sklearn.manifold import TSNE
            reducer = TSNE(
                n_components=dims,
                metric="cosine",
                random_state=42,
                init="random",
                learning_rate="auto",
            )
        elif method == "pca":
            from sklearn.decomposition import PCA
            reducer = PCA(n_components=dims, random_state=42)
        else:  # default UMAP
            import umap
            logger.info("🎯 Starting UMAP dimensionality reduction...")
            
            # Enable numba logging to match working version
            import os
            os.environ['NUMBA_ENABLE_CUDASIM'] = '0'  # Ensure CUDA sim is off
            
            # Set numba logging to match working version behavior
            numba_logger = logging.getLogger('numba')
            numba_logger.setLevel(logging.DEBUG)
            
            # Clear numba cache to avoid compilation issues
            try:
                import numba
                logger.info("🧹 Clearing numba cache to avoid compilation conflicts...")
                # Force fresh compilation
                os.environ['NUMBA_CACHE_DIR'] = ''  # Disable cache temporarily
            except Exception as e:
                logger.warning(f"Could not configure numba cache: {e}")
            
            # Use simple UMAP configuration like working version
            reducer = umap.UMAP(
                n_components=dims,
                metric="cosine",
                random_state=42,
            )
            logger.info("⚙️ UMAP initialized, starting fit_transform...")
        
        # Do dimensionality reduction with timeout monitoring
        import time
        import threading
        
        start_time = time.time()
        result_container = [None]
        error_container = [None]
        
        def reduction_task():
            try:
                result_container[0] = reducer.fit_transform(vecs)
            except Exception as e:
                error_container[0] = e
        
        # Start reduction in thread so we can monitor progress
        thread = threading.Thread(target=reduction_task)
        thread.daemon = True
        thread.start()
        
        # Monitor progress with warnings
        while thread.is_alive():
            elapsed = time.time() - start_time
            if elapsed > 10 and elapsed % 10 < 0.1:  # Every 10 seconds
                logger.warning(f"⏰ UMAP still running after {elapsed:.0f} seconds...")
            if elapsed > 120:  # 2 minute timeout
                logger.error("💥 UMAP timeout after 2 minutes - switching to PCA fallback")
                from sklearn.decomposition import PCA
                pca_reducer = PCA(n_components=dims, random_state=42)
                coords = pca_reducer.fit_transform(vecs)
                logger.info(f"✅ PCA fallback completed! Output shape: {coords.shape}")
                break
            time.sleep(0.1)
        else:
            # Thread completed normally
            if error_container[0]:
                raise error_container[0]
            coords = result_container[0]
            logger.info(f"✅ Dimensionality reduction completed! Output shape: {coords.shape}")
        
        # Clustering
        from sklearn.decomposition import PCA
        
        # Dimensionality reduction for clustering
        if vecs.shape[1] > 50:
            max_comps = min(50, vecs.shape[0], vecs.shape[1])
            try:
                pca50 = PCA(n_components=max_comps, random_state=42)
                vec_for_cluster = pca50.fit_transform(vecs)
            except ValueError:
                vec_for_cluster = vecs
        else:
            vec_for_cluster = vecs
        
        # K-means clustering
        n_clusters = max(2, min(n_clusters, len(vec_for_cluster)))
        km = MiniBatchKMeans(n_clusters=n_clusters, random_state=42)
        clusters = km.fit_predict(vec_for_cluster)
        
        # Generate enhanced cluster explanations
        import re
        from collections import Counter, defaultdict
        from sklearn.feature_extraction import text as _sk_text
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np
        
        STOP_WORDS = set(_sk_text.ENGLISH_STOP_WORDS)
        
        # Enhanced STOP_WORDS with common news terms that don't add meaning
        ENHANCED_STOP_WORDS = STOP_WORDS | {
            'said', 'says', 'according', 'report', 'reports', 'news', 'new', 'latest',
            'today', 'yesterday', 'week', 'month', 'year', 'time', 'years', 'months',
            'company', 'companies', 'people', 'person', 'world', 'country', 'countries',
            'government', 'state', 'states', 'city', 'way', 'ways', 'day', 'days',
            'first', 'second', 'third', 'last', 'next', 'previous', 'current', 'recent',
            'major', 'large', 'small', 'big', 'high', 'low', 'good', 'bad', 'better',
            'best', 'worst', 'long', 'short', 'old', 'young', 'early', 'late', 'local',
            'national', 'international', 'global', 'public', 'private', 'official',
            'officials', 'sources', 'source', 'including', 'include', 'includes',
            'part', 'parts', 'group', 'groups', 'number', 'numbers', 'total', 'many',
            'several', 'various', 'different', 'similar', 'same', 'other', 'others',
            'million', 'billion', 'thousand', 'million', 'percent', 'percentage'
        }
        
        # Collect documents and metadata by cluster
        cluster_documents = defaultdict(list)
        cluster_metadata = defaultdict(list)
        
        for idx, lbl in enumerate(clusters):
            meta = metas[idx] if idx < len(metas) else {}
            title = meta.get('title', '')
            summary = meta.get('summary', '')
            
            # Combine title and summary with title weighted more heavily
            document = f"{title} {title} {summary}"  # Title appears twice for emphasis
            
            cluster_documents[int(lbl)].append(document)
            cluster_metadata[int(lbl)].append(meta)
        
        # Generate enhanced explanations using TF-IDF and contextual analysis
        explain = {}
        
        for lbl, docs in cluster_documents.items():
            if not docs:
                explain[lbl] = ["empty cluster"]
                continue
                
            cluster_metas = cluster_metadata[lbl]
            
            # Method 1: TF-IDF based keyword extraction
            combined_text = " ".join(docs)
            
            # Clean and tokenize
            tokens = [
                t.lower() for t in re.findall(r"\b[a-zA-Z]{3,}\b", combined_text)
                if t.lower() not in ENHANCED_STOP_WORDS and len(t) >= 3
            ]
            
            if not tokens:
                explain[lbl] = ["misc content"]
                continue
            
            # Get top keywords by frequency
            keyword_counts = Counter(tokens)
            top_keywords = [w for w, c in keyword_counts.most_common(15) if c >= 2]
            
            # Method 2: Extract domain-specific patterns
            domain_patterns = []
            
            # Extract named entities and proper nouns (capitalized words)
            named_entities = set()
            for doc in docs:
                entities = re.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b", doc)
                for entity in entities:
                    if len(entity.split()) <= 3 and entity.lower() not in ENHANCED_STOP_WORDS:
                        named_entities.add(entity.lower())
            
            # Extract common phrases (2-3 word combinations)
            phrase_counts = Counter()
            for doc in docs:
                words = re.findall(r"\b[a-zA-Z]{3,}\b", doc.lower())
                clean_words = [w for w in words if w not in ENHANCED_STOP_WORDS]
                
                # Extract bigrams and trigrams
                for i in range(len(clean_words) - 1):
                    bigram = f"{clean_words[i]} {clean_words[i+1]}"
                    phrase_counts[bigram] += 1
                    
                for i in range(len(clean_words) - 2):
                    trigram = f"{clean_words[i]} {clean_words[i+1]} {clean_words[i+2]}"
                    phrase_counts[trigram] += 1
            
            # Get meaningful phrases (appearing at least twice)
            meaningful_phrases = [phrase for phrase, count in phrase_counts.most_common(5) if count >= 2]
            
            # Method 3: Analyze metadata patterns
            categories = [meta.get('category') for meta in cluster_metas if meta.get('category')]
            topics = [meta.get('topic') for meta in cluster_metas if meta.get('topic')]
            sentiments = [meta.get('sentiment') for meta in cluster_metas if meta.get('sentiment')]
            
            category_pattern = Counter(categories).most_common(1)
            topic_pattern = Counter(topics).most_common(1)
            sentiment_pattern = Counter(sentiments).most_common(1)
            
            # Generate human-readable cluster title and description
            cluster_info = {
                "keywords": [],
                "title": "",
                "summary": "",
                "count": len(cluster_metas)
            }
            
            # Analyze dominant themes for title generation
            title_components = []
            summary_components = []
            
            # Priority 1: Category context for title
            if category_pattern and len(category_pattern[0]) > 0:
                cat, cat_count = category_pattern[0]
                if cat_count >= len(cluster_metas) * 0.4:  # At least 40% of articles
                    title_components.append(cat.title())
            
            # Priority 2: Topic context for title
            if topic_pattern and len(topic_pattern[0]) > 0:
                topic, topic_count = topic_pattern[0]
                if topic_count >= len(cluster_metas) * 0.4:
                    title_components.append(topic.title())
            
            # Priority 3: Most meaningful phrases for title
            if meaningful_phrases:
                # Use the most common meaningful phrase as part of title
                best_phrase = meaningful_phrases[0].title()
                if len(best_phrase.split()) <= 3:  # Keep titles concise
                    title_components.append(best_phrase)
            
            # Priority 4: Top keywords for title if nothing else
            if not title_components and top_keywords:
                title_components.append(top_keywords[0].title())
            
            # Generate human-readable title
            if title_components:
                # Create a natural title
                if len(title_components) == 1:
                    cluster_title = f"{title_components[0]} News"
                elif len(title_components) == 2:
                    cluster_title = f"{title_components[0]} & {title_components[1]}"
                else:
                    cluster_title = f"{title_components[0]} Topics"
            else:
                cluster_title = "Mixed Content"
            
            # Generate summary description
            summary_parts = []
            
            # Add article count context
            article_count = len(cluster_metas)
            if article_count > 1:
                summary_parts.append(f"{article_count} articles about")
            
            # Add main themes
            if meaningful_phrases:
                main_themes = [phrase for phrase in meaningful_phrases[:2] if len(phrase.split()) <= 4]
                if main_themes:
                    summary_parts.append(" and ".join(main_themes))
            elif top_keywords:
                main_themes = top_keywords[:3]
                summary_parts.append(", ".join(main_themes))
            
            # Add category/topic context to summary
            context_parts = []
            if category_pattern and len(category_pattern[0]) > 0:
                cat, cat_count = category_pattern[0]
                if cat_count >= len(cluster_metas) * 0.3:
                    context_parts.append(f"in {cat.lower()}")
            
            if topic_pattern and len(topic_pattern[0]) > 0:
                topic, topic_count = topic_pattern[0]
                if topic_count >= len(cluster_metas) * 0.3 and topic.lower() not in " ".join(context_parts).lower():
                    context_parts.append(f"related to {topic.lower()}")
            
            if context_parts:
                summary_parts.extend(context_parts)
            
            # Add sentiment if very dominant
            if sentiment_pattern and len(sentiment_pattern[0]) > 0:
                sent, sent_count = sentiment_pattern[0]
                if sent_count >= len(cluster_metas) * 0.7:  # At least 70% of articles
                    summary_parts.append(f"with {sent.lower()} sentiment")
            
            # Create final summary
            if summary_parts:
                cluster_summary = " ".join(summary_parts).capitalize()
                if not cluster_summary.endswith('.'):
                    cluster_summary += "."
            else:
                cluster_summary = f"Collection of {article_count} related articles."
            
            # Collect keywords for legacy compatibility and detailed view
            description_parts = []
            
            # Add top meaningful phrases
            description_parts.extend(meaningful_phrases[:2])
            
            # Add top keywords
            description_parts.extend(top_keywords[:6])
            
            # Add named entities
            description_parts.extend(list(named_entities)[:2])
            
            # Clean up and deduplicate keywords
            unique_parts = []
            seen = set()
            for part in description_parts:
                if part and part not in seen and len(part.strip()) > 2:
                    unique_parts.append(part.strip())
                    seen.add(part)
            
            final_keywords = unique_parts[:8] if unique_parts else top_keywords[:5]
            if not final_keywords:
                final_keywords = ["misc content"]
            
            # Store enhanced cluster information
            cluster_info["keywords"] = final_keywords
            cluster_info["title"] = cluster_title
            cluster_info["summary"] = cluster_summary
            
            explain[lbl] = cluster_info
        
        # Calculate centroids
        centroids = {}
        if dims == 2:
            for lbl in set(clusters):
                idxs = np.where(clusters == lbl)[0]
                if idxs.size:
                    centroids[int(lbl)] = [
                        float(coords[idxs, 0].mean()),
                        float(coords[idxs, 1].mean()),
                    ]
        
        # Generate final points
        points = []
        for i, _id in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            point = {
                "id": _id,
                "x": float(coords[i, 0]),
                "y": float(coords[i, 1]),
                "cluster": int(clusters[i]),
                "title": meta.get("title"),
                "sentiment": meta.get("sentiment"),
                "driver_type": meta.get("driver_type"),
                "category": meta.get("category"),
                "time_to_impact": meta.get("time_to_impact"),
            }
            if dims == 3:
                point["z"] = float(coords[i, 2])
            points.append(point)
        
        logger.info(f"Generated projection with {len(points)} points")
        return {
            "points": points,
            "explain": explain,
            "centroids": centroids,
        }
    except Exception as e:
        logger.exception(f"Error in embedding projection: {e}")
        # Return valid response even on error
        return {"points": [], "explain": {}, "centroids": {}, "error": str(e)}


@router.get("/embedding_neighbours")
def embedding_neighbours(
    id: str = Query(..., description="Vector/Article identifier (uri)"),
    top_k: int = Query(5, ge=1, le=50),
    session=Depends(verify_session),
):
    """Return the *top_k* nearest neighbours for a given vector ``id``.

    The response mirrors the minimal structure needed by the front-end –
    a list of ``{"id": str, "distance": float}`` objects.
    """
    neighbours = [
        {"id": r["id"], "distance": r["score"]}
        for r in similar_articles(id, top_k=top_k)
    ]
    return neighbours


@router.get("/patterns")
def patterns_endpoint(
    q: Optional[str] = Query(
        None,
        description="Optional search query to seed the article set",
    ),
    top_k: int = Query(
        1000,
        ge=10,
        le=10000,
        description="Number of articles to analyse for patterns (max 10000)",
    ),
    topic: Optional[str] = None,
    category: Optional[str] = None,
    future_signal: Optional[str] = None,
    sentiment: Optional[str] = None,
    news_source: Optional[str] = None,
    session=Depends(verify_session),
):
    """Return simple textual pattern stats.

    We compute top unigrams/bigrams and a tiny co-occurrence matrix.
    The pattern extraction logic works only on *title* and *summary*.
    """
    try:
        logger = logging.getLogger(__name__)
        logger.info(f"Patterns endpoint called with query: {q or 'None'}")
        
        # Build metadata filter
        meta_filter = {}
        if topic:
            meta_filter["topic"] = topic
        if category:
            meta_filter["category"] = category
        if future_signal:
            meta_filter["future_signal"] = future_signal
        if sentiment:
            meta_filter["sentiment"] = sentiment
        if news_source:
            meta_filter["news_source"] = news_source
    
        # Get base articles
        query_str = q or "*"
        
        MAX_TOP_K = 10000
        if top_k > MAX_TOP_K:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Requested top_k={top_k} exceeds maximum {MAX_TOP_K}. "
                    "Reduce the value or use paging."
                ),
            )

        # Handle pipe operators through executor if present
        if q and "|" in q:
            from app.kissql.parser import parse_full_query
            from app.kissql.executor import execute_query
            
            logger.info("Query contains pipe operators")
            query_obj = parse_full_query(q)
            result = execute_query(query_obj, top_k=top_k)
            articles = result.get("results", [])
            logger.info(f"Applied pipe filtering: {len(articles)} articles")
        else:
            # Standard search without pipe operators
            articles = search_articles(
                query_str,
                top_k=top_k,
                metadata_filter=meta_filter,
            )
    
        # Process articles to extract patterns
        from collections import Counter, defaultdict
        import re
        from sklearn.feature_extraction import text as _sk_text
    
        STOP_WORDS = set(_sk_text.ENGLISH_STOP_WORDS)
        unigram_counts = Counter()
        bigram_counts = Counter()
        cooc_mat = defaultdict(Counter)
        tag_counts = Counter()
        tag_sentiment = defaultdict(Counter)
    
        for art in articles:
            meta = art["metadata"]
            text_parts = [
                meta.get("title", ""),
                meta.get("summary", ""),
            ]
            text = " ".join([t for t in text_parts if t])
            tokens = [
                t.lower()
                for t in re.findall(r"\b\w{3,}\b", text)
                if t.lower() not in STOP_WORDS
            ]
            if not tokens:
                continue
    
            # Update counts
            unigram_counts.update(tokens)
            bigram_counts.update(
                " ".join(pair) for pair in zip(tokens, tokens[1:])
            )
    
            # Co-occurrence
            uniq = set(tokens)
            for t1 in uniq:
                for t2 in uniq:
                    if t1 == t2:
                        continue
                    cooc_mat[t1][t2] += 1
    
            # Tags
            tags_raw = meta.get("tags")
            if tags_raw:
                tags = (tags_raw if isinstance(tags_raw, list)
                        else [t.strip() for t in tags_raw.split(",")])
                tag_counts.update(tags)
                for tg in tags:
                    tag_sentiment[tg][meta.get("sentiment", "unknown")] += 1
    
        # Generate final result
        top_unigrams = unigram_counts.most_common(20)
        top_bigrams = bigram_counts.most_common(20)
        ngrams = [
            {"text": w, "count": c} for w, c in (top_unigrams + top_bigrams)
        ]
    
        top_terms = [w for w, _ in unigram_counts.most_common(10)]
        cooccurrence = {}
        for term in top_terms:
            neigh = cooc_mat.get(term, {})
            cooccurrence[term] = dict(neigh.most_common(5))
    
        tag_stats = {
            tg: {
                "total": cnt,
                "sentiment": dict(tag_sentiment[tg]),
            }
            for tg, cnt in tag_counts.most_common(30)
        }
    
        logger.info(f"Generated patterns with {len(ngrams)} ngrams")
        return {
            "ngrams": ngrams,
            "cooccurrence": cooccurrence,
            "tag_stats": tag_stats,
        }
    except Exception as e:
        logger.exception(f"Error in patterns endpoint: {e}")
        return {
            "ngrams": [],
            "cooccurrence": {},
            "tag_stats": {},
            "error": str(e)
        }


@router.get("/statistics")
def statistics_endpoint(
    q: Optional[str] = Query(None),
    top_k: int = Query(500, ge=10, le=1000),
    topic: Optional[str] = None,
    category: Optional[str] = None,
    future_signal: Optional[str] = None,
    sentiment: Optional[str] = None,
    news_source: Optional[str] = None,
    session=Depends(verify_session),
):
    """Return descriptive statistics for the current article subset."""

    try:
        meta_filter: Dict[str, Any] = {}
        if topic:
            meta_filter["topic"] = topic
        if category:
            meta_filter["category"] = category
        if future_signal:
            meta_filter["future_signal"] = future_signal
        if sentiment:
            meta_filter["sentiment"] = sentiment
        if news_source:
            meta_filter["news_source"] = news_source

        query_str = q or "*"
        results = search_articles(
            query_str,
            top_k=top_k,
            metadata_filter=meta_filter,
        )

        from collections import Counter, defaultdict
        from statistics import mean
        from datetime import datetime

        total = len(results)
        if total == 0:
            return {
                "total": 0,
                "by_category": {},
                "by_sentiment": {},
                "avg_score": 0,
                "date_range": [None, None],
            }

        cat_counter: Counter[str] = Counter()
        sent_counter: Counter[str] = Counter()
        scores: list[float] = []
        dates: list[datetime] = []

        for hit in results:
            meta = hit.get("metadata", {})
            cat = meta.get("category")
            if cat:
                cat_counter[str(cat)] += 1
            sent = meta.get("sentiment")
            if sent:
                sent_counter[str(sent)] += 1
            scores.append(float(hit.get("score", 0)))
            pub_date = meta.get("publication_date")
            if pub_date:
                try:
                    # Convert to a date object (skip tz/offset handling)
                    dates.append(dt_parse(str(pub_date)).date())
                except Exception:
                    pass

        date_min = min(dates).isoformat() if dates else None
        date_max = max(dates).isoformat() if dates else None

        # ---------------- Tag aggregation ----------------
        tag_counts: Counter[str] = Counter()
        tag_sentiment: dict[str, Counter[str]] = defaultdict(Counter)

        for hit in results:
            meta = hit.get("metadata", {})
            tags_raw = meta.get("tags")
            if not tags_raw:
                continue
            tags = (
                tags_raw
                if isinstance(tags_raw, list)
                else [t.strip() for t in str(tags_raw).split(",")]
            )
            tag_counts.update(tags)
            for tg in tags:
                tag_sentiment[tg][meta.get("sentiment", "unknown")] += 1

        tag_stats = {
            tg: {
                "total": cnt,
                "sentiment": dict(tag_sentiment[tg]),
            }
            for tg, cnt in tag_counts.most_common(30)
        }

        return {
            "total": total,
            "by_category": dict(cat_counter),
            "by_sentiment": dict(sent_counter),
            "avg_score": mean(scores) if scores else 0,
            "date_range": [date_min, date_max],
            "tag_stats": tag_stats,
        }
    except Exception as exc:  # pragma: no cover
        logging.getLogger(__name__).error("/statistics failed: %s", exc)
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ------------------------------------------------------------------
# Cleaning up completely (optional)
# ------------------------------------------------------------------


@router.post("/clean_collection")
async def clean_collection(session=Depends(verify_session)):
    """Delete and rebuild the collection.

    This is a helper endpoint to clean up completely.  It deletes the
    collection and then re-indexes all articles.
    """
    client = get_chroma_client()
    # Drop only the vector index (does not touch relational DB)
    client.delete_collection("articles")
    # To rebuild, hit /api/vector-reindex afterwards

# Tag metadata ingestion lives in ``app/vector_store._build_metadata``.
# Anomaly-detection helpers should sit in a dedicated module.
# Placeholders removed.

# ------------------------------------------------------------------
# Anomaly detection – Isolation Forest on embeddings
# ------------------------------------------------------------------


@router.get("/embedding_anomalies")
def embedding_anomalies(
    q: Optional[str] = Query(None, description="Optional search query"),
    top_k: int = Query(
        2500,
        ge=1,
        description="Number of anomalies to return (max 5000)",
    ),
    topic: Optional[str] = None,
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    news_source: Optional[str] = None,
    session=Depends(verify_session),
):
    """Return the *top_k* most isolated articles within the filter scope.

    Isolation Forest runs on the raw vectors (high-dim).  The *score*
    returned is the anomaly score. Higher values mean more anomalous.
    """
    try:
        logger = logging.getLogger(__name__)
        logger.info(f"Anomalies endpoint called with query: {q or 'None'}")
        
        # Build where filter
        where = None
        if any([topic, category, sentiment, news_source]):
            where = {}
            if topic:
                where["topic"] = topic
            if category:
                where["category"] = category
            if sentiment:
                where["sentiment"] = sentiment
            if news_source:
                where["news_source"] = news_source
    
        # Handle pipe operators through executor if present
        if q and "|" in q:
            from app.kissql.parser import parse_full_query
            from app.kissql.executor import execute_query
            
            logger.info("Query contains pipe operators")
            query_obj = parse_full_query(q)
            result = execute_query(query_obj, top_k=5000)
            
            # Extract IDs from the results
            filtered_results = result.get("results", [])
            filtered_ids = [r["id"] for r in filtered_results]
            
            # Add URI filter
            if not filtered_ids:
                logger.warning("No results after pipe filtering")
                return []
                
            # Add URI filter to where clause
            if where is None:
                where = {}
            where["uri"] = {"$in": filtered_ids}
            
            logger.info(f"Applied pipe filtering: {len(filtered_ids)} results")
    
        # Enforce a sensible upper limit to protect the service
        MAX_TOP_K = 5000  # hard ceiling for performance – tweak as needed
        if top_k > MAX_TOP_K:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Requested top_k={top_k} exceeds maximum {MAX_TOP_K}. "
                    "Reduce the value or use paging."
                ),
            )

        # Fetch enough vectors for anomaly detection (cap at MAX_TOP_K)
        fetch_limit = min(max(top_k * 2, 5000), MAX_TOP_K)

        vecs, metas, ids = _fetch_vectors(limit=fetch_limit, where=where)
        if vecs.size == 0:
            return []
    
        # Run anomaly detection
        from sklearn.ensemble import IsolationForest
        import numpy as np
    
        iso = IsolationForest(contamination=0.02, random_state=42)
        anomaly_score = -iso.fit(vecs).decision_function(vecs)
    
        idx_sorted = np.argsort(anomaly_score)[::-1][:top_k]
    
        anomaly_results = [
            {
                "id": ids[i],
                "score": float(anomaly_score[i]),
                "metadata": metas[i],
            }
            for i in idx_sorted
        ]
        
        logger.info(f"Generated {len(anomaly_results)} anomaly results")
        return anomaly_results
    except Exception as e:
        logger.exception(f"Error in anomalies endpoint: {e}")
        return [{"error": str(e)}]

# ------------------------------------------------------------------
# Auspex summarisation endpoint – summarise arbitrary article IDs
# ------------------------------------------------------------------


class _SummaryRequest(BaseModel):
    """Payload for /vector-summary."""

    ids: list[str] = Field(..., description="IDs")
    model: str | None = Field(None, description="LLM name (optional)")


@router.post("/vector-summary")
async def vector_summary(
    req: _SummaryRequest,
    session=Depends(verify_session),
):
    """Return a markdown summary of the supplied *ids* using the configured AI.

    The endpoint fetches article metadata (title, summary etc.) from Chroma's
    metadatas and feeds a condensed context to the LLM.  We cap the context
    to 100 articles server-side to avoid prompt explosions.  Use the *ids*
    parameter to control the subset.
    """

    from textwrap import shorten  # noqa: E501

    # --------------------------------------------------------------------------------
    # 1. Fetch metadata for the requested IDs from the vector store (Chroma)
    # --------------------------------------------------------------------------------
    collection = _vector_collection()
    try:
        # Fetch metadata for the requested IDs (max 100)
        res = collection.get(  # type: ignore[arg-type]
            ids=req.ids[:100],
            include=["metadatas"],
        )
    except Exception as exc:
        logger = logging.getLogger(__name__)
        logger.error("Chroma get failed for summary: %s", exc)
        raise HTTPException(status_code=500, detail="Vector store error")

    metas: list[dict] = res.get("metadatas", [])

    if not metas:
        raise HTTPException(
            status_code=404,
            detail="No metadata found for the given ids",
        )

    # --------------------------------------------------------------------------------
    # 2. Build a concise context – send only fields relevant for summary
    # --------------------------------------------------------------------------------
    lines: list[str] = []
    for idx, m in enumerate(metas, start=1):
        title = m.get("title") or "Untitled"
        summary = m.get("summary") or ""
        summary_short = shorten(summary, width=300, placeholder="…")
        cat = m.get("category") or "?"
        sentiment = m.get("sentiment") or "?"
        sent_expl = m.get("sentiment_explanation") or ""
        source = m.get("news_source") or "Unknown"
        date = m.get("publication_date") or ""
        bias = m.get("bias") or ""
        factual = m.get("factual_reporting") or ""
        cred = m.get("mbfc_credibility_rating") or ""
        driver = m.get("driver_type") or ""
        tti = m.get("time_to_impact") or ""
        signal = m.get("future_signal") or ""
        url = m.get("uri") or ""

        parts: list[str] = [
            f"{idx}. Title: {title}",
            f"Source: {source}",
        ]
        if date:
            parts.append(f"Date: {date}")
        if url:
            parts.append(f"URL: {url}")
        parts.append(f"Category: {cat}")
        line_sent = f"Sentiment: {sentiment}"
        if sent_expl:
            line_sent += f" - {sent_expl}"
        parts.append(line_sent)
        if bias:
            parts.append(f"Bias: {bias}")
        if factual:
            parts.append(f"Factual reporting: {factual}")
        if cred:
            parts.append(f"Credibility: {cred}")
        if driver:
            parts.append(f"Driver type: {driver}")
        if tti:
            parts.append(f"Time to impact: {tti}")
        if signal:
            parts.append(f"Future signal: {signal}")
        parts.append(f"Summary: {summary_short}")

        lines.append("\n".join(parts) + "\n")

    joined = "\n".join(lines)

    # --------------------------------------------------------------------------------
    # 3. Query LLM directly using litellm (same approach as six articles generation)
    # --------------------------------------------------------------------------------
    import litellm
    logger = logging.getLogger(__name__)

    # Use provided model or default to gpt-4o-mini (lightweight)
    model_name = req.model or "gpt-4o-mini"
    
    logger.info(f"Vector summary requested with model: {model_name}")

    # Choose prompt based on number of articles to preserve backward compatibility
    is_single_article = len(metas) == 1
    if is_single_article:
        # Article-focused prompt with explicit sections – ignore line-length linting  # noqa: E501
        system_msg = (
            "You are Auspex – an expert news analyst. Analyze the provided article using only the supplied metadata and summary. "
            "Produce a single-article analysis; do not reference clusters or multiple articles. "
            "Respond in markdown with the following exact sections and headings, concise and factual:\n\n"
            "## What is the article about?\n"
            "## Who does it concern?\n"
            "## Key takeaways\n- 3–6 bullet points\n"
            "## Summary\n- 3–5 sentences\n"
            "## Key themes\n- 2–5 bullet points\n\n"
            "Avoid speculation; prefer neutral tone. Omit sections or bullets only if information is unavailable. Limit to ~400 words."
        )
    else:
        # Legacy cluster-style prompt for multi-article inputs
        system_msg = (
            "You are Auspex – an expert analyst. "
            "The user supplied a set of news articles in bullet-point form. "
            "The articles are part of a cluster determined by a cluster analysis."
            "The user wants to know more about the cluster."
            "Provide a concise markdown summary covering key insights, any "
            "recurring themes, trends, or outliers. Start with a "
            "one-sentence summary. Then use bullet points and short sections "
            "(Key Themes, Sentiment, Notable Articles). Limit to about 500 words."
        )

    if is_single_article:
        user_intro = "Here is the article context (metadata + summary):\n\n"
    else:
        user_intro = "Here are the articles (metadata + summaries):\n\n"

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"{user_intro}{joined}"},
    ]

    try:
        # Use litellm directly (same as six articles generation)
        response = await litellm.acompletion(
            model=model_name,
            messages=messages,
            temperature=0.3,
            max_tokens=2000
        )
        
        summary = response.choices[0].message.content
        logger.info(f"Vector summary generated successfully with model: {model_name}")
        
    except Exception as exc:
        logger.error(f"LLM summary failed with model {model_name}: {exc}")
        raise HTTPException(status_code=500, detail=f"LLM error with model {model_name}: {str(exc)}")

    return {"response": summary}


# ------------------------------------------------------------------
# Raw-text summarisation endpoint – uses full article documents
# ------------------------------------------------------------------


class _SummaryRawRequest(BaseModel):
    """Payload for /vector-summary-raw."""

    ids: list[str] = Field(..., description="IDs")
    model: str | None = Field(None, description="LLM name (optional)")


@router.post("/vector-summary-raw")
async def vector_summary_raw(
    req: _SummaryRawRequest,
    session=Depends(verify_session),
):
    """Return a detailed markdown analysis using raw article documents.

    Single article → five-section analysis (article-focused).
    Multiple articles → legacy cluster-style analysis.
    """

    import litellm
    logger = logging.getLogger(__name__)

    # 1) Fetch documents + metadata from Chroma
    collection = _vector_collection()
    try:
        res = collection.get(  # type: ignore[arg-type]
            ids=req.ids[:20],
            include=["metadatas", "documents"],
        )
    except Exception as exc:
        logger.error("Chroma get failed for raw summary: %s", exc)
        raise HTTPException(status_code=500, detail="Vector store error")

    metas: list[dict] = res.get("metadatas", [])
    docs: list[str] = res.get("documents", [])
    if not metas or not docs:
        raise HTTPException(
            status_code=404,
            detail="No documents found for the given ids",
        )

    def _truncate(text: str, max_chars: int = 16000) -> str:
        if not text:
            return ""
        text = str(text)
        return text if len(text) <= max_chars else text[:max_chars]

    blocks: list[str] = []
    for idx, (m, d) in enumerate(zip(metas, docs), start=1):
        title = m.get("title") or "Untitled"
        source = m.get("news_source") or "Unknown"
        date = m.get("publication_date") or ""
        url = m.get("uri") or ""
        category = m.get("category") or ""
        sentiment = m.get("sentiment") or ""
        sent_expl = m.get("sentiment_explanation") or ""
        bias = m.get("bias") or ""
        factual = m.get("factual_reporting") or ""
        cred = m.get("mbfc_credibility_rating") or ""

        header_lines = [
            f"{idx}. Title: {title}",
            f"Source: {source}",
        ]
        if date:
            header_lines.append(f"Date: {date}")
        if url:
            header_lines.append(f"URL: {url}")
        if category:
            header_lines.append(f"Category: {category}")
        if sentiment:
            line = f"Sentiment: {sentiment}"
            if sent_expl:
                line += f" - {sent_expl}"
            header_lines.append(line)
        if bias:
            header_lines.append(f"Bias: {bias}")
        if factual:
            header_lines.append(f"Factual reporting: {factual}")
        if cred:
            header_lines.append(f"Credibility: {cred}")

        full_text = _truncate(d)
        blocks.append("\n".join(header_lines) + f"\nFull text:\n{full_text}\n")

    joined = "\n\n".join(blocks)

    # 2) Prompt selection
    model_name = req.model or "gpt-4o-mini"
    is_single_article = len(metas) == 1

    if is_single_article:
        system_msg = (
            "You are Auspex – an expert news analyst. Analyze the provided article using only the supplied content. "
            "Produce a concrete single-article analysis; do not reference clusters or multiple articles. "
            "Name specific companies, organizations, tickers, people, products, and any financial figures or dates mentioned. "
            "If a requested detail is not present, explicitly write 'Not stated'. Respond in markdown with these sections:\n\n"
            "## What is the article about?\n"
            "## Who does it concern?\n"
            "## Key takeaways\n- 3–6 bullets, each with concrete nouns/numbers where possible\n"
            "## Summary\n- 3–5 sentences, specific details over generalities\n"
            "## Key themes\n- 2–5 bullets capturing underlying ideas\n\n"
            "Keep neutral tone and avoid speculation. Limit to ~500 words."
        )
        user_intro = "Here is the article (metadata + full text):\n\n"
    else:
        system_msg = (
            "You are Auspex – an expert analyst. The user supplied multiple articles. "
            "Provide a concise markdown cluster summary: one-sentence overview, then Key Themes, Sentiment, Notable Articles."
        )
        user_intro = "Here are the articles (metadata + full text):\n\n"

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"{user_intro}{joined}"},
    ]

    try:
        resp = await litellm.acompletion(
            model=model_name,
            messages=messages,
            temperature=0.2,
            max_tokens=2000,
        )
        content = resp.choices[0].message.content
        logger.info("Vector raw summary generated successfully with model: %s", model_name)
        return {"response": content}
    except Exception as exc:
        logger.error("LLM raw summary failed with model %s: %s", model_name, exc)
        raise HTTPException(status_code=500, detail=f"LLM error with model {model_name}: {str(exc)}")

# ------------------------------------------------------------------
# Article insights endpoint – themes, insights, and follow-ups
# ------------------------------------------------------------------


class _ArticleInsightsRequest(BaseModel):
    """Payload for /article-insights."""

    ids: list[str] = Field(..., description="Article IDs (URIs) to analyze")
    model: str | None = Field(None, description="LLM name (optional)")
    structured: bool = Field(False, description="Return structured JSON instead of markdown")


@router.post("/article-insights")
async def article_insights(
    req: _ArticleInsightsRequest,
    session=Depends(verify_session),
):
    """Generate concise themes, insights, and follow-up prompts for given articles.

    - Single article → article-focused insights
    - Multiple articles → cluster-focused insights
    """

    import litellm
    logger = logging.getLogger(__name__)

    # 1) Fetch metadatas (and summaries) from Chroma
    collection = _vector_collection()
    try:
        res = collection.get(  # type: ignore[arg-type]
            ids=req.ids[:100],
            include=["metadatas"],
        )
    except Exception as exc:
        logger.error("Chroma get failed for article-insights: %s", exc)
        raise HTTPException(status_code=500, detail="Vector store error")

    metas: list[dict] = res.get("metadatas", [])
    if not metas:
        raise HTTPException(status_code=404, detail="No metadata found for the given ids")

    # 2) Build concise context
    from textwrap import shorten
    lines: list[str] = []
    for idx, m in enumerate(metas, start=1):
        title = m.get("title") or "Untitled"
        source = m.get("news_source") or "Unknown"
        date = m.get("publication_date") or ""
        url = m.get("uri") or ""
        category = m.get("category") or ""
        sentiment = m.get("sentiment") or ""
        signal = m.get("future_signal") or ""
        driver = m.get("driver_type") or ""
        tti = m.get("time_to_impact") or ""
        summary = shorten(m.get("summary") or "", width=400, placeholder="…")

        parts: list[str] = [
            f"{idx}. Title: {title}",
            f"Source: {source}",
        ]
        if date:
            parts.append(f"Date: {date}")
        if url:
            parts.append(f"URL: {url}")
        if category:
            parts.append(f"Category: {category}")
        if sentiment:
            parts.append(f"Sentiment: {sentiment}")
        if signal:
            parts.append(f"Future signal: {signal}")
        if driver:
            parts.append(f"Driver type: {driver}")
        if tti:
            parts.append(f"Time to impact: {tti}")
        parts.append(f"Summary: {summary}")

        lines.append("\n".join(parts) + "\n")

    joined = "\n".join(lines)

    # 3) Prompt and LLM call
    model_name = req.model or "gpt-4o-mini"
    is_single_article = len(metas) == 1

    if is_single_article:
        system_msg = (
            "You are Auspex – an expert news analyst. Based only on the provided article metadata and summary, "
            "identify research themes that warrant deeper investigation. Respond in markdown with EXACT section:\n\n"
            "## Research themes\n- 4–8 bullets: each a specific research topic (2–5 words) suitable for comprehensive Auspex analysis\n\n"
            "Focus ONLY on identifying themes for deep research. Each theme should be broad enough to find multiple related articles."
        )
        user_intro = "Here is the article context (metadata + summary):\n\n"
    else:
        system_msg = (
            "You are Auspex – an expert analyst. The user provided multiple related articles as metadata+summaries. "
            "Identify research themes for deep investigation. Respond in markdown with EXACT section:\n\n"
            "## Research themes\n- 5–10 bullets: each a specific research topic (2–5 words) suitable for Auspex analysis\n\n"
            "Focus ONLY on identifying themes that warrant investigation beyond these articles."
        )
        user_intro = "Here are the articles (metadata + summaries):\n\n"

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"{user_intro}{joined}"},
    ]

    try:
        from datetime import datetime
        generated_at = datetime.utcnow().isoformat() + "Z"
        
        resp = await litellm.acompletion(
            model=model_name,
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
        )
        content = resp.choices[0].message.content
        logger.info("Article insights generated successfully with model: %s", model_name)
        
        # Return structured JSON if requested
        if req.structured:
            try:
                import re
                # Parse markdown sections into structured data
                research_themes = []
                
                # Extract research themes - try multiple header variations
                themes_patterns = [
                    r'## Research themes\n(.*?)(?=\n##|\n$)',
                    r'## Research Themes\n(.*?)(?=\n##|\n$)', 
                    r'##\s*Research\s*[Tt]hemes\s*\n(.*?)(?=\n##|\n$)',
                    r'Research themes:?\n(.*?)(?=\n##|\n$)',
                    r'Research Themes:?\n(.*?)(?=\n##|\n$)'
                ]
                
                research_themes = []
                for pattern in themes_patterns:
                    themes_match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                    if themes_match:
                        matched_content = themes_match.group(1)
                        logger.info(f"Pattern matched: {pattern}")
                        logger.info(f"Matched content: '{matched_content[:200]}...'")
                        
                        # Extract lines that start with - or *
                        lines = matched_content.split('\n')
                        logger.info(f"Processing {len(lines)} lines from matched content")
                        for i, line in enumerate(lines):
                            original_line = line
                            line = line.strip()
                            logger.debug(f"Line {i}: '{original_line}' -> stripped: '{line}'")
                            if line.startswith('-') or line.startswith('*'):
                                # Remove the bullet point more reliably
                                if line.startswith('-'):
                                    theme = line[1:].strip()  # Remove first character and strip
                                elif line.startswith('*'):
                                    theme = line[1:].strip()  # Remove first character and strip
                                else:
                                    theme = line.strip()
                                
                                logger.debug(f"Extracted theme: '{theme}'")
                                if theme and len(theme) > 2:  # Only add non-empty themes
                                    research_themes.append(theme)
                                    logger.info(f"Added theme: '{theme}'")
                        
                        logger.info(f"Successfully extracted {len(research_themes)} themes: {research_themes}")
                        break
                
                if not research_themes:
                    logger.warning(f"No research themes found in content. Content preview: {content[:500]}...")
                    # Try a more aggressive extraction as last resort
                    lines = content.split('\n')
                    in_themes_section = False
                    for line in lines:
                        line = line.strip()
                        if 'research themes' in line.lower():
                            in_themes_section = True
                            continue
                        if in_themes_section and line.startswith('#'):
                            break  # End of section
                        if in_themes_section and (line.startswith('-') or line.startswith('*')):
                            theme = line.lstrip('- *').strip()
                            if theme and len(theme) > 2:
                                research_themes.append(theme)
                    
                    if research_themes:
                        logger.info(f"Fallback extraction found {len(research_themes)} themes: {research_themes}")
                
                # Cache the themes analysis
                try:
                    from app.database import get_database_instance
                    db = get_database_instance()
                    
                    # Save themes to cache
                    cache_metadata = {"research_themes": research_themes}
                    db.save_article_analysis_cache(
                        article_uri=req.ids[0] if req.ids else "unknown",
                        analysis_type="themes",
                        content=content,
                        model_used=req.model,
                        metadata=cache_metadata
                    )
                    logger.info(f"Cached themes analysis for article {req.ids[0] if req.ids else 'unknown'} with model {req.model}")
                except Exception as cache_exc:
                    logger.warning(f"Failed to cache themes analysis: {cache_exc}")
                
                return {
                    "generated_at": generated_at,
                    "research_themes": research_themes,
                    "raw_response": content
                }
            except Exception as parse_exc:
                logger.warning("Failed to parse structured insights, falling back to markdown: %s", parse_exc)
                return {"response": content, "generated_at": generated_at}
        
        # Save to database cache
        try:
            from app.database import get_database_instance
            db = get_database_instance()
            
            # Save both structured and raw response
            cache_metadata = {"research_themes": research_themes} if research_themes else {}
            db.save_article_analysis_cache(
                article_uri=req.ids[0],
                analysis_type="themes",
                content=content,
                model_used=model_name,
                metadata=cache_metadata
            )
        except Exception as cache_exc:
            logger.warning(f"Failed to cache themes analysis: {cache_exc}")
        
        return {"response": content, "generated_at": generated_at}
    except Exception as exc:
        logger.error("LLM article-insights failed with model %s: %s", model_name, exc)
        raise HTTPException(status_code=500, detail=f"LLM error with model {model_name}: {str(exc)}")


# ------------------------------------------------------------------
# Incident tracking endpoint for entity/event grouping
# ------------------------------------------------------------------

class _IncidentTrackingRequest(BaseModel):
    """Request for incident tracking analysis."""
    topic: str = Field(..., description="Topic to analyze for incidents")
    days_limit: int = Field(14, ge=1, le=90, description="Days back to analyze")
    start_date: Optional[str] = Field(None, description="Start date YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="End date YYYY-MM-DD")
    max_articles: int = Field(100, ge=10, le=300, description="Maximum articles to analyze")
    model: str = Field("gpt-4o-mini", description="AI model to use for analysis")
    force_regenerate: bool = Field(False, description="Force regeneration bypassing cache")
    domain: Optional[str] = Field(
        None,
        description="Ontology domain key. Use 'vanilla' for default; e.g., 'scientific_publisher'"
    )
    profile_id: Optional[int] = Field(None, description="Organizational profile ID for contextualized analysis")
    test_articles: Optional[List[Dict]] = Field(None, description="Optional test articles to analyze instead of database query")

@router.post("/incident-tracking")
async def analyze_incidents(
    req: _IncidentTrackingRequest,
    session=Depends(verify_session_optional),
):
    """Track specific incidents, entities, and events for threat hunting."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        # Check cache first
        cache_key = f"incident_tracking_{req.topic}_{req.start_date or 'no_start'}_{req.end_date or 'no_end'}_{req.days_limit}"
        
        # Get articles for analysis
        from datetime import datetime, timedelta
        
        if req.start_date and req.end_date:
            start_date_dt = datetime.strptime(req.start_date, '%Y-%m-%d')
            end_date_dt = datetime.strptime(req.end_date, '%Y-%m-%d')
        else:
            end_date_dt = datetime.now()
            start_date_dt = end_date_dt - timedelta(days=req.days_limit)
        
        # Query articles - use same approach as working news feed service
        query = """
        SELECT uri, title, summary, news_source, publication_date, category, sentiment,
               bias, factual_reporting, mbfc_credibility_rating, bias_source
        FROM articles 
        WHERE publication_date >= ? AND publication_date <= ?
        AND category IS NOT NULL AND sentiment IS NOT NULL
        """
        
        params = [start_date_dt.isoformat(), end_date_dt.isoformat()]
        
        if req.topic:
            query += " AND (topic = ? OR title LIKE ? OR summary LIKE ?)"
            topic_pattern = f"%{req.topic}%"
            params.extend([req.topic, topic_pattern, topic_pattern])
        
        query += " ORDER BY publication_date DESC LIMIT ?"
        params.append(req.max_articles)
        
        # Use test articles if provided, otherwise query database
        if req.test_articles:
            logger.info(f"Using {len(req.test_articles)} test articles instead of database query")
            articles = req.test_articles
        else:
            articles = db.fetch_all(query, params)
        
        if not articles:
            return {"incidents": [], "message": f"No articles found for topic '{req.topic}' in date range {start_date_dt.strftime('%Y-%m-%d')} to {end_date_dt.strftime('%Y-%m-%d')}"}
        
        # Define cache_uri for later use
        cache_uri = articles[0]['uri'] if hasattr(articles[0], '__getitem__') else articles[0].uri
        
        # Check cache using first article as anchor (unless force regenerate)
        if not req.force_regenerate:
            cached = db.get_article_analysis_cache(
                article_uri=cache_uri,
                analysis_type=f"incident_tracking_{req.topic}",
                model_used="incident_analysis"
            )
            
            if cached and cached.get("metadata", {}).get("cache_key") == cache_key:
                logger.info(f"Cache HIT: incident tracking for {req.topic}")
                import json
                return json.loads(cached["content"])
        
        if req.force_regenerate:
            logger.info(f"Force regenerating incident tracking for {req.topic} (bypassing cache)")
        
        # Prepare articles for LLM analysis with credibility markers
        def _norm(value):
            return (value or '').strip() if isinstance(value, str) else (value or '')

        articles_text = "\n\n".join([
            (
                lambda a: (
                    f"Article {i+1}:\n"
                    f"Title: {a['title']}\n"
                    f"Source: {a['news_source']}\n"
                    f"Date: {a['publication_date']}\n"
                    f"Category: {a['category']} | Sentiment: {a['sentiment']}\n"
                    f"Credibility: factual_reporting={_norm(a.get('factual_reporting')) or 'unknown'}, "
                    f"mbfc={_norm(a.get('mbfc_credibility_rating')) or 'unknown'}, bias={_norm(a.get('bias')) or 'unknown'}\n"
                    f"Summary: {a['summary']}\n"
                    f"URI: {a['uri']}"
                )
            )(
                a if isinstance(a, dict) else {
                    'uri': a[0], 'title': a[1], 'summary': a[2], 'news_source': a[3], 'publication_date': a[4],
                    'category': a[5], 'sentiment': a[6], 'bias': a[7] if len(a) > 7 else None,
                    'factual_reporting': a[8] if len(a) > 8 else None,
                    'mbfc_credibility_rating': a[9] if len(a) > 9 else None,
                    'bias_source': a[10] if len(a) > 10 else None,
                }
            )
            for i, a in enumerate(articles)
        ])
        
        # Build ontology guidance
        def _build_incident_event_ontology(topic: str, domain: Optional[str]) -> str:
            t = (topic or '').lower()
            d = (domain or '').lower() if domain else ''
            is_scientific_publisher = ('publisher' in t and 'scientific' in t) or d == 'scientific_publisher'

            base = (
                "\nONTOLOGY — Types and Subtypes\n"
                "Valid types: incident | event | entity | expertise | informed_insider | trend_signal | strategic_shift\n\n"
                "Definitions:\n"
                "- incident: Discrete occurrence with material operational/strategic/risk impact that may warrant response, remediation, or escalation.\n"
                "- event: Noteworthy occurrence (signals, milestones, announcements) that informs context or trends but is not itself a disruptive incident.\n"
                "- entity: Organization, person, product, venue, dataset (things we track, not occurrences).\n"
                "- expertise: Expert analysis, predictions, or authoritative insights from recognized industry leaders, analysts, or researchers.\n"
                "- informed_insider: Insider perspectives, leaked information, or privileged insights from people with direct access to relevant information.\n"
                "- trend_signal: Market trends, behavioral shifts, or emerging patterns that indicate future developments.\n"
                "- strategic_shift: Major strategic changes, policy pivots, or directional changes by key organizations or governments.\n\n"
                "Recommended subtypes:\n"
                "- incident: regulatory_action, compliance_breach, data_security, legal_ip, mna, layoffs, funding_cut, rd_spend_change, governance_change, market_disruption\n"
                "- event: product_launch, feature_update, partnership_mou, funding_round, hiring, award, conference_announcement, roadmap_teaser, benchmark_result, pilot_program\n"
                "- entity: company, person, product, dataset, venue, regulator, research_institution, government_agency\n"
                "- expertise: industry_analysis, market_prediction, technical_assessment, strategic_forecast, expert_warning, research_finding\n"
                "- informed_insider: leaked_strategy, internal_memo, insider_trading, confidential_roadmap, private_meeting, executive_communication\n"
                "- trend_signal: adoption_trend, market_shift, behavioral_change, technology_uptake, regulatory_momentum, competitive_dynamic\n"
                "- strategic_shift: policy_pivot, strategic_realignment, market_repositioning, technology_focus_change, regulatory_approach_change\n\n"
                "Assignment rules:\n"
                "- Use 'incident' for events requiring immediate attention or response (layoffs, breaches, regulatory actions, major failures).\n"
                "- Use 'event' for announcements and developments (product launches, funding, partnerships, pilot programs).\n"
                "- Use 'entity' for organizations, people, or products being tracked.\n"
                "- Use 'expertise' when article features expert analysis, predictions, or authoritative insights from recognized leaders.\n"
                "- Use 'informed_insider' when article contains insider information, leaks, or privileged access insights.\n"
                "- Use 'trend_signal' when article identifies emerging patterns, market trends, or behavioral shifts.\n"
                "- Use 'strategic_shift' when article describes major strategic changes, policy pivots, or directional changes.\n"
                "- Always include a 'subtype' from the lists above.\n"
                "- Be inclusive rather than restrictive - classify newsworthy content appropriately.\n"
            )

            # Domain overlays (vanilla = no overlay)
            overlay = ""
            if d and d != 'vanilla' and is_scientific_publisher:
                overlay = (
                    "\nDomain overlay — scientific_publisher:\n"
                    "- Treat as incident: legal_ip (patent disputes, licensing changes), rd_spend_change (material increases/decreases, major lab closures), regulatory_action affecting IP/open access policy, acquisition of critical editorial/data assets.\n"
                    "- Treat as event: competitor product_launch (new journal/platform/analytics offering), feature_update, conference_announcement, partnership_mou.\n"
                    "Examples:\n"
                    "  - 'Elsevier raises R&D spend by 25% in AI editorial tooling' → type=incident, subtype=rd_spend_change, significance=high.\n"
                    "  - 'Wiley launches a new open-access analytics platform' → type=event, subtype=product_launch, significance=medium.\n"
                )

            examples = (
                "\nLabeling examples (JSON objects):\n"
                "{\"name\": \"SoftBank Vision Fund layoffs amid AI strategy shift\", \"type\": \"incident\", \"subtype\": \"layoffs\"}\n"
                "{\"name\": \"Citi launches agentic AI pilot program\", \"type\": \"event\", \"subtype\": \"pilot_program\"}\n"
                "{\"name\": \"Eric Schmidt warns about AI competitiveness\", \"type\": \"expertise\", \"subtype\": \"expert_warning\"}\n"
                "{\"name\": \"Inside Tony Blair Institute AI strategy discussions\", \"type\": \"informed_insider\", \"subtype\": \"private_meeting\"}\n"
                "{\"name\": \"Growing enterprise adoption of agentic AI\", \"type\": \"trend_signal\", \"subtype\": \"adoption_trend\"}\n"
                "{\"name\": \"SoftBank shifts focus from consumer to enterprise AI\", \"type\": \"strategic_shift\", \"subtype\": \"strategic_realignment\"}\n"
                "{\"name\": \"SoftBank Vision Fund\", \"type\": \"entity\", \"subtype\": \"company\"}\n"
            )

            return base + overlay + examples

        ontology_text = _build_incident_event_ontology(req.topic, req.domain)

        # Get organizational profile context if provided
        profile_context = ""
        if req.profile_id:
            try:
                from app.database_query_facade import DatabaseQueryFacade
                profile_row = DatabaseQueryFacade(db, logger).get_organisational_profile(req.profile_id)
                if profile_row:
                    import json
                    profile = {
                        'name': profile_row[1],
                        'industry': profile_row[3],
                        'organization_type': profile_row[4],
                        'region': profile_row[5],
                        'key_concerns': json.loads(profile_row[6]) if profile_row[6] else [],
                        'strategic_priorities': json.loads(profile_row[7]) if profile_row[7] else [],
                        'risk_tolerance': profile_row[8],
                        'innovation_appetite': profile_row[9],
                        'decision_making_style': profile_row[10],
                        'stakeholder_focus': json.loads(profile_row[11]) if profile_row[11] else [],
                        'competitive_landscape': json.loads(profile_row[12]) if profile_row[12] else [],
                        'regulatory_environment': json.loads(profile_row[13]) if profile_row[13] else [],
                        'custom_context': profile_row[14]
                    }
                    
                    # Build profile context
                    key_concerns = ', '.join(profile['key_concerns']) if profile['key_concerns'] else 'General business concerns'
                    strategic_priorities = ', '.join(profile['strategic_priorities']) if profile['strategic_priorities'] else 'Growth and sustainability'
                    stakeholder_focus = ', '.join(profile['stakeholder_focus']) if profile['stakeholder_focus'] else 'Customers and employees'
                    competitive_landscape = ', '.join(profile['competitive_landscape']) if profile['competitive_landscape'] else 'Industry competitors'
                    regulatory_environment = ', '.join(profile['regulatory_environment']) if profile['regulatory_environment'] else 'Standard regulations'
                    
                    profile_context = f"""
ORGANIZATIONAL CONTEXT:
Organization: {profile['name']} ({profile.get('organization_type', 'Organization')} in {profile.get('industry', 'General')})
Region: {profile.get('region', 'Not specified')}
Risk Tolerance: {profile.get('risk_tolerance', 'Medium')} | Innovation Appetite: {profile.get('innovation_appetite', 'Moderate')}
Decision Making: {profile.get('decision_making_style', 'Collaborative')}

Key Concerns: {key_concerns}
Strategic Priorities: {strategic_priorities}
Key Stakeholders: {stakeholder_focus}
Competitive Landscape: {competitive_landscape}
Regulatory Environment: {regulatory_environment}

Custom Context: {profile.get('custom_context', 'No additional context specified')}

ANALYSIS INSTRUCTIONS:
- Prioritize incidents and events that align with {profile['name']}'s key concerns: {key_concerns}
- Assess significance based on {profile.get('risk_tolerance', 'medium')} risk tolerance and {profile.get('decision_making_style', 'collaborative')} decision-making style
- Consider impact on key stakeholders: {stakeholder_focus}
- Account for competitive positioning relative to: {competitive_landscape}
- Evaluate regulatory implications considering: {regulatory_environment}
- Tailor investigation leads to {profile.get('industry', 'industry')} context and organizational priorities

"""
                    logger.info(f"Using organizational profile: {profile['name']} ({profile.get('industry', 'General')})")
            except Exception as e:
                logger.error(f"Error loading organizational profile {req.profile_id}: {str(e)}")

        # Try to get custom configuration from request or use defaults
        # TODO: In future, load saved configuration from database
        # For now, use the enhanced default configuration
        
        # Default analysis instructions (AI Guidance)
        analysis_instructions = """Focus on extracting actionable intelligence from news articles. Prioritize:

1. Material business impacts and strategic changes (layoffs, restructuring, major funding changes)
2. Regulatory actions and compliance issues (government policies, regulatory warnings)
3. Security incidents and data breaches (cybersecurity events, data leaks)
4. Significant funding, M&A, or operational changes (acquisitions, major investments, closures)
5. Technology launches and competitive developments (new products, platform launches, AI model releases)
6. Leadership changes and strategic pivots (CEO changes, strategic direction shifts)
7. Market warnings and competitive threats (expert warnings, competitive analysis)

Classification Guidelines:
- INCIDENT: Events requiring immediate attention or response (layoffs, breaches, regulatory actions, major failures)
- EVENT: Significant announcements and developments (product launches, funding rounds, partnerships, strategic initiatives)  
- ENTITY: Organizations, people, or products being tracked (companies mentioned, key executives, new technologies)
- EXPERTISE: Expert analysis, predictions, or authoritative insights from recognized industry leaders
- INFORMED_INSIDER: Insider perspectives, leaked information, or privileged insights
- TREND_SIGNAL: Market trends, behavioral shifts, or emerging patterns
- STRATEGIC_SHIFT: Major strategic changes, policy pivots, or directional changes

Be inclusive rather than restrictive - if an article discusses something newsworthy, classify it appropriately."""

        # Default quality guidelines (AI Guidance)
        quality_guidelines = """Credibility Assessment:
- High credibility: Major news outlets, verified sources, multiple independent confirmations
- Mixed credibility: Single source reporting, unverified claims, industry blogs
- Low credibility: Social media rumors, fringe sources, extraordinary claims without evidence

Extraordinary Claims Protocol:
- Flag claims that seem too good to be true or represent major breakthroughs
- Require independent verification for significant technical achievements
- Down-rank significance for self-reported successes without third-party validation"""

        # Create incident tracking prompt with AI Guidance integration
        system_prompt = f"""
        You are a threat intelligence analyst tracking incidents, entities, and events in {req.topic}.

        IMPORTANT: Assess credibility and plausibility. Treat extraordinary, self-reported breakthroughs with skepticism.
        Use factual_reporting, MBFC credibility, and bias indicators. Down-rank or flag items from low/mixed credibility or fringe bias sources.

        {profile_context}

        {analysis_instructions}

        {quality_guidelines}

        {ontology_text}

        Required fields for each item:
        - name
        - type: incident | entity | event | expertise | informed_insider | trend_signal | strategic_shift
        - subtype: from the allowed list for the chosen type
        - description
        - article_uris
        - timeline
        - significance: low | medium | high (reduce if credibility concerns exist)
        - investigation_leads
        - related_entities
        - plausibility: likely | questionable | implausible
        - source_quality: high | mixed | low
        - misinfo_flags: [] e.g., "extraordinary_claim", "no_independent_verification", "low_factuality_source", "fringe_bias"
        - credibility_summary: 1-2 sentence rationale

        Devil's Advocate Smell Test:
        - Add a "devils_advocate" field with brief caution if the claim appears hyperbolic or extraordinary relative to typical evidence.
        - Use label "Hyperbolic Claim" when applicable.

        Output a pure JSON array only.
        """
        
        user_prompt = f"Analyze these {req.topic} articles for threat hunting incidents, entities, and events:\n\n{articles_text}"
        
        # Generate analysis
        from app.ai_models import LiteLLMModel
        from fastapi.concurrency import run_in_threadpool
        
        model_name = req.model  # Use model from frontend
        ai_model = LiteLLMModel.get_instance(model_name)
        if not ai_model:
            raise HTTPException(status_code=500, detail=f"Failed to initialize model {model_name}")
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response_str = await run_in_threadpool(ai_model.generate_response, messages)
        
        # Parse response
        incidents = []
        if response_str and not ("⚠️" in response_str or "unavailable" in response_str.lower()):
            try:
                import re
                import json as json_module
                json_match = re.search(r'\[.*\]', response_str, re.DOTALL)
                if json_match:
                    incidents = json_module.loads(json_match.group())
            except json_module.JSONDecodeError as je:
                logger.error(f"Failed to parse incident tracking response: {je}")
                return {"incidents": [], "error": "Failed to parse LLM response"}

        # --- Credibility post-processing and safeguards ---
        # Build URI -> credibility map from fetched articles
        def _norm_str(val):
            return (val or '').strip().lower() if isinstance(val, str) else ''

        def _row_to_dict(row):
            if isinstance(row, dict):
                return row
            return {
                'uri': row[0], 'title': row[1], 'summary': row[2], 'news_source': row[3],
                'publication_date': row[4], 'category': row[5], 'sentiment': row[6],
                'bias': row[7] if len(row) > 7 else None,
                'factual_reporting': row[8] if len(row) > 8 else None,
                'mbfc_credibility_rating': row[9] if len(row) > 9 else None,
                'bias_source': row[10] if len(row) > 10 else None,
            }

        article_dicts = [_row_to_dict(a) for a in articles]
        uri_to_cred = {}
        for a in article_dicts:
            factual = _norm_str(a.get('factual_reporting'))
            cred = _norm_str(a.get('mbfc_credibility_rating'))
            bias = _norm_str(a.get('bias'))
            is_low_factual = factual in {'low', 'mixed', 'questionable'}
            is_low_cred = cred in {'low', 'mixed', 'questionable'}
            is_fringe = any(t in bias for t in ['extreme', 'conspiracy', 'fringe', 'propaganda'])
            source_quality = 'high'
            if is_low_factual or is_low_cred:
                source_quality = 'mixed'
            if is_low_factual and is_low_cred:
                source_quality = 'low'
            flags = []
            if is_low_factual:
                flags.append('low_factuality_source')
            if is_low_cred:
                flags.append('low_credibility_source')
            if is_fringe:
                flags.append('fringe_bias')
            uri_to_cred[a['uri']] = {
                'source_quality': source_quality,
                'factual_reporting': a.get('factual_reporting'),
                'mbfc_credibility_rating': a.get('mbfc_credibility_rating'),
                'bias': a.get('bias'),
                'flags': flags,
                'news_source': a.get('news_source'),
                'title': a.get('title')
            }

        def _is_extraordinary(text: str) -> bool:
            t = (text or '').lower()
            return any(k in t for k in ['sovereign agi', 'artificial general intelligence', 'agi achieved', 'cryptographic proof of agi', 'self-declared agi'])

        # Enrich incidents: add plausibility/source_quality/misinfo_flags, adjust significance
        for inc in incidents or []:
            name = inc.get('name') or ''
            desc = inc.get('description') or ''
            uris = []
            if isinstance(inc.get('article_uris'), list):
                uris.extend([u for u in inc['article_uris'] if u])
            if isinstance(inc.get('articles'), list):
                for a in inc['articles']:
                    if isinstance(a, dict) and a.get('uri'):
                        uris.append(a['uri'])
            # Aggregate credibility
            qualities = [uri_to_cred[u]['source_quality'] for u in uris if u in uri_to_cred]
            has_low = any(q == 'low' for q in qualities)
            has_mixed = any(q == 'mixed' for q in qualities)
            derived_source_quality = 'high'
            if has_low:
                derived_source_quality = 'low'
            elif has_mixed:
                derived_source_quality = 'mixed'

            # Merge flags
            flags = set(inc.get('misinfo_flags') or [])
            for u in uris:
                credinfo = uri_to_cred.get(u)
                if credinfo:
                    for f in credinfo['flags']:
                        flags.add(f)

            # Extraordinary claim heuristic
            if _is_extraordinary(name) or _is_extraordinary(desc):
                flags.add('extraordinary_claim')
                if derived_source_quality != 'high':
                    flags.add('no_independent_verification')

            # Determine plausibility
            explicit_plaus = (inc.get('plausibility') or '').lower()
            if explicit_plaus in {'likely', 'questionable', 'implausible'}:
                plausibility = explicit_plaus
            else:
                if 'extraordinary_claim' in flags and derived_source_quality != 'high':
                    plausibility = 'implausible'
                elif derived_source_quality == 'mixed':
                    plausibility = 'questionable'
                elif derived_source_quality == 'low':
                    plausibility = 'implausible'
                else:
                    plausibility = 'likely'

            # Adjust significance conservatively on low credibility
            sig = (inc.get('significance') or '').lower()
            if sig in {'high', 'medium', 'low'}:
                if plausibility == 'implausible' or derived_source_quality == 'low':
                    sig = 'low'
                elif plausibility == 'questionable' or derived_source_quality == 'mixed':
                    if sig == 'high':
                        sig = 'medium'
            else:
                sig = 'low' if derived_source_quality != 'high' else 'medium'

            # Credibility summary
            summary_bits = []
            if derived_source_quality != 'high':
                summary_bits.append(f"source_quality={derived_source_quality}")
            if 'extraordinary_claim' in flags:
                summary_bits.append('extraordinary_claim')
            if 'no_independent_verification' in flags:
                summary_bits.append('no_independent_verification')
            credibility_summary = inc.get('credibility_summary') or (
                ('; '.join(summary_bits) or 'sources appear credible')
            )

            # Write back
            inc['source_quality'] = derived_source_quality
            inc['plausibility'] = plausibility
            inc['misinfo_flags'] = sorted(list(flags))
            inc['credibility_summary'] = credibility_summary
            inc['significance'] = sig
        
        result = {
            "incidents": incidents,
            "total_articles": len(articles),
            "analysis_period": f"{start_date_dt.strftime('%Y-%m-%d')} to {end_date_dt.strftime('%Y-%m-%d')}",
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        # Cache the results
        try:
            import json as json_module
            cache_content = json_module.dumps(result, ensure_ascii=False, default=str)
            cache_metadata = {
                "cache_key": cache_key,
                "topic": req.topic,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "days_limit": req.days_limit,
                "analysis_type": "incident_tracking"
            }
            
            success = db.save_article_analysis_cache(
                article_uri=cache_uri,
                analysis_type=f"incident_tracking_{req.topic}",
                content=cache_content,
                model_used="incident_analysis",
                metadata=cache_metadata
            )
            
            if success:
                logger.info(f"Cache SAVE: incident tracking for {req.topic}")
        except Exception as cache_error:
            logger.warning(f"Failed to cache incident tracking: {cache_error}")
        
        # Get incident statuses and filter out deleted ones
        incident_statuses = db.get_incident_status(req.topic)
        
        # Filter out deleted incidents and mark seen ones
        filtered_incidents = []
        for incident in incidents:
            incident_name = incident.get('name', '')
            status = incident_statuses.get(incident_name, 'active')
            
            if status != 'deleted':
                incident['status'] = status
                filtered_incidents.append(incident)
        
        result = {
            "incidents": filtered_incidents,
            "total_articles": len(articles),
            "analysis_period": f"{start_date_dt.strftime('%Y-%m-%d')} to {end_date_dt.strftime('%Y-%m-%d')}",
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        # Cache the results
        try:
            import json as json_module
            cache_content = json_module.dumps(result, ensure_ascii=False, default=str)
            cache_metadata = {
                "cache_key": cache_key,
                "topic": req.topic,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "days_limit": req.days_limit,
                "analysis_type": "incident_tracking"
            }
            
            success = db.save_article_analysis_cache(
                article_uri=cache_uri,
                analysis_type=f"incident_tracking_{req.topic}",
                content=cache_content,
                model_used="incident_analysis",
                metadata=cache_metadata
            )
            
            if success:
                logger.info(f"Cache SAVE: incident tracking for {req.topic}")
        except Exception as cache_error:
            logger.warning(f"Failed to cache incident tracking: {cache_error}")
        
        return result
        
    except Exception as exc:
        logger.error("Error in incident tracking: %s", exc)
        raise HTTPException(status_code=500, detail="Incident tracking error")

@router.post("/incident-status/{incident_name}")
async def update_incident_status(
    incident_name: str,
    status: str = Query(..., description="New status: seen, deleted, or active"),
    topic: str = Query(..., description="Topic the incident belongs to"),
    session=Depends(verify_session),
):
    """Update incident status (seen/deleted/active)."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        if status not in ['seen', 'deleted', 'active']:
            raise HTTPException(status_code=400, detail="Invalid status. Must be 'seen', 'deleted', or 'active'")
        
        success = db.update_incident_status(incident_name, topic, status)
        
        if success:
            return {"success": True, "message": f"Incident status updated to {status}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update incident status")
            
    except Exception as exc:
        logger.error("Error updating incident status: %s", exc)
        raise HTTPException(status_code=500, detail="Incident status update error")

# ------------------------------------------------------------------
# Signal instructions endpoints for threat hunting
# ------------------------------------------------------------------

class _SignalInstructionRequest(BaseModel):
    """Request for saving signal instructions."""
    name: str = Field(..., description="Name of the signal instruction")
    description: str = Field("", description="Description of what this signal watches for")
    instruction: str = Field(..., description="LLM instruction for detecting this signal")
    topic: Optional[str] = Field(None, description="Topic to apply this signal to")
    is_active: bool = Field(True, description="Whether this signal is active")

@router.post("/signal-instructions")
async def save_signal_instruction(
    req: _SignalInstructionRequest,
    session=Depends(verify_session),
):
    """Save a custom signal instruction for threat hunting."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        success = db.save_signal_instruction(
            name=req.name,
            description=req.description,
            instruction=req.instruction,
            topic=req.topic,
            is_active=req.is_active
        )
        
        if success:
            return {"success": True, "message": f"Signal instruction '{req.name}' saved successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to save signal instruction")
            
    except Exception as exc:
        logger.error("Error saving signal instruction: %s", exc)
        raise HTTPException(status_code=500, detail="Signal instruction save error")

@router.get("/signal-instructions")
async def get_signal_instructions(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    active_only: bool = Query(True, description="Only return active instructions"),
    session=Depends(verify_session_optional),
):
    """Get signal instructions for threat hunting."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        instructions = db.get_signal_instructions(topic=topic, active_only=active_only)
        
        return {
            "success": True,
            "instructions": instructions,
            "count": len(instructions)
        }
        
    except Exception as exc:
        logger.error("Error getting signal instructions: %s", exc)
        raise HTTPException(status_code=500, detail="Signal instruction retrieval error")

@router.delete("/signal-instructions/{instruction_id}")
async def delete_signal_instruction(
    instruction_id: int,
    session=Depends(verify_session),
):
    """Delete a signal instruction."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        success = db.delete_signal_instruction(instruction_id)
        
        if success:
            return {"success": True, "message": "Signal instruction deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Signal instruction not found")
            
    except Exception as exc:
        logger.error("Error deleting signal instruction: %s", exc)
        raise HTTPException(status_code=500, detail="Signal instruction deletion error")

class _RealTimeSignalsRequest(BaseModel):
    """Request for real-time signals analysis."""
    topic: str = Field(..., description="Topic to analyze")
    days_limit: int = Field(7, ge=1, le=30, description="Days back to analyze")
    start_date: Optional[str] = Field(None, description="Start date YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="End date YYYY-MM-DD")
    max_articles: int = Field(50, ge=10, le=200, description="Maximum articles to analyze")
    instruction_ids: Optional[List[int]] = Field(None, description="Specific signal instruction IDs to use")
    model: str = Field("gpt-4o-mini", description="AI model to use for analysis")
    force_regenerate: bool = Field(False, description="Force regeneration bypassing cache")

@router.post("/real-time-signals")
async def analyze_real_time_signals(
    req: _RealTimeSignalsRequest,
    session=Depends(verify_session_optional),
):
    """Analyze articles for real-time signals using custom instructions."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        # Get signal instructions first to include in cache key
        if req.instruction_ids:
            # Get specific instructions
            all_instructions = db.get_signal_instructions(topic=req.topic, active_only=False)
            instructions = [inst for inst in all_instructions if inst['id'] in req.instruction_ids and inst['is_active']]
        else:
            # Get all active instructions for this topic
            instructions = db.get_signal_instructions(topic=req.topic, active_only=True)
        
        # Include instruction IDs in cache key so cache invalidates when instructions change
        instruction_ids_str = ','.join(str(inst['id']) for inst in instructions)
        cache_key = f"realtime_signals_{req.topic}_{req.start_date or 'no_start'}_{req.end_date or 'no_end'}_{req.days_limit}_{instruction_ids_str}"
        
        logger.info(f"Real-time signals analysis - Topic: {req.topic}")
        logger.info(f"Instructions found: {len(instructions)} - IDs: {[inst['id'] for inst in instructions]}")
        logger.info(f"Instruction names: {[inst['name'] for inst in instructions]}")
        
        # Check if quantum computing instruction is in the list
        quantum_instructions = [inst for inst in instructions if 'quantum' in inst['name'].lower()]
        logger.info(f"Quantum instructions found: {len(quantum_instructions)}")
        if quantum_instructions:
            for qi in quantum_instructions:
                logger.info(f"Quantum instruction: '{qi['name']}' - Active: {qi['is_active']} - Topic: {qi.get('topic')}")
        else:
            logger.warning("No quantum computing instructions found in active set!")
        logger.info(f"Cache key: {cache_key}")
        logger.info(f"Force regenerate: {req.force_regenerate}")
        
        # Get articles for analysis
        from datetime import datetime, timedelta
        
        if req.start_date and req.end_date:
            start_date_dt = datetime.strptime(req.start_date, '%Y-%m-%d')
            end_date_dt = datetime.strptime(req.end_date, '%Y-%m-%d')
        else:
            end_date_dt = datetime.now()
            start_date_dt = end_date_dt - timedelta(days=req.days_limit)
        
        # Query recent articles - use same approach as working news feed service
        query = """
        SELECT uri, title, summary, news_source, publication_date, category, sentiment
        FROM articles 
        WHERE publication_date >= ? AND publication_date <= ?
        AND category IS NOT NULL AND sentiment IS NOT NULL
        """
        
        params = [start_date_dt.isoformat(), end_date_dt.isoformat()]
        
        if req.topic:
            query += " AND (topic = ? OR title LIKE ? OR summary LIKE ?)"
            topic_pattern = f"%{req.topic}%"
            params.extend([req.topic, topic_pattern, topic_pattern])
        
        query += " ORDER BY publication_date DESC LIMIT ?"
        params.append(req.max_articles)
        
        articles = db.fetch_all(query, params)
        
        if not articles:
            return {"signals": [], "message": f"No articles found for topic '{req.topic}' in date range {start_date_dt.strftime('%Y-%m-%d')} to {end_date_dt.strftime('%Y-%m-%d')}"}
        
        # Instructions already loaded above for cache key
        if not instructions:
            return {"signals": [], "message": "No active signal instructions found"}
        
        # Define cache_uri for later use
        cache_uri = articles[0]['uri'] if hasattr(articles[0], '__getitem__') else articles[0].uri
        
        # Check cache using first article as anchor (unless force regenerate)
        if not req.force_regenerate:
            cached = db.get_article_analysis_cache(
                article_uri=cache_uri,
                analysis_type=f"realtime_signals_{req.topic}",
                model_used="signal_analysis"
            )
            
            if cached and cached.get("metadata", {}).get("cache_key") == cache_key:
                logger.info(f"Cache HIT: real-time signals for {req.topic}")
                import json
                return json.loads(cached["content"])
        
        if req.force_regenerate:
            logger.info(f"Force regenerating real-time signals for {req.topic} (bypassing cache)")
        
        # Analyze articles with each signal instruction
        from app.ai_models import LiteLLMModel
        
        model_name = req.model  # Use model from frontend
        ai_model = LiteLLMModel.get_instance(model_name)
        if not ai_model:
            raise HTTPException(status_code=500, detail=f"Failed to initialize model {model_name}")
        
        detected_signals = []
        
        logger.info(f"Processing {len(instructions)} signal instructions:")
        logger.info(f"Articles being analyzed: {len(articles)} articles from {start_date_dt.strftime('%Y-%m-%d')} to {end_date_dt.strftime('%Y-%m-%d')}")
        
        # Debug: Log sample article titles to see what's being analyzed
        sample_titles = [article.get('title') if hasattr(article, 'get') else article['title'] for article in articles[:10]]
        logger.info(f"Sample article titles: {sample_titles}")
        
        # Special debug for quantum computing
        quantum_articles = [article for article in articles if 'quantum' in (article.get('title') if hasattr(article, 'get') else article['title']).lower()]
        logger.info(f"Quantum articles found in dataset: {len(quantum_articles)}")
        if quantum_articles:
            for qa in quantum_articles:
                title = qa.get('title') if hasattr(qa, 'get') else qa['title']
                date = qa.get('publication_date') if hasattr(qa, 'get') else qa['publication_date']
                logger.info(f"Quantum article: '{title}' - Date: {date}")
        
        for i, instruction in enumerate(instructions):
            logger.info(f"Processing instruction {i+1}/{len(instructions)}: '{instruction['name']}' (ID: {instruction['id']})")
            logger.info(f"Instruction text: {instruction['instruction'][:100]}...")
            
            # Prepare articles text for analysis
            articles_text = "\n\n".join([
                f"Article {i+1}:\nTitle: {article.get('title') if hasattr(article, 'get') else article['title']}\n"
                f"Source: {article.get('news_source') if hasattr(article, 'get') else article['news_source']}\n"
                f"Date: {article.get('publication_date') if hasattr(article, 'get') else article['publication_date']}\n"
                f"Summary: {article.get('summary') if hasattr(article, 'get') else article['summary']}\n"
                f"URI: {article.get('uri') if hasattr(article, 'get') else article['uri']}"
                for i, article in enumerate(articles[:20])  # Limit to 20 articles per instruction
            ])
            
            # Create analysis prompt
            system_prompt = f"""
            You are a threat intelligence analyst. Analyze the provided articles using this specific signal instruction:
            
            SIGNAL: {instruction['name']}
            DESCRIPTION: {instruction['description']}
            INSTRUCTION: {instruction['instruction']}
            
            Return a JSON response with:
            {{
                "signal_detected": true/false,
                "confidence": 0.0-1.0,
                "matching_articles": ["uri1", "uri2", ...],
                "summary": "Brief explanation of what was detected",
                "threat_level": "low"|"medium"|"high",
                "recommended_action": "What should analysts do next"
            }}
            """
            
            user_prompt = f"Analyze these articles for the signal '{instruction['name']}':\n\n{articles_text}"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            try:
                from fastapi.concurrency import run_in_threadpool
                response_str = await run_in_threadpool(ai_model.generate_response, messages)
                
                # Parse response
                logger.info(f"LLM response for '{instruction['name']}': {response_str[:500]}...")
                
                # Special debug for quantum computing
                if 'quantum' in instruction['name'].lower():
                    logger.info(f"QUANTUM DEBUG - Full response: {response_str}")
                if response_str and not ("⚠️" in response_str or "unavailable" in response_str.lower()):
                    try:
                        import re
                        import json as json_module
                        json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
                        if json_match:
                            signal_result = json_module.loads(json_match.group())
                            signal_result['instruction_name'] = instruction['name']
                            signal_result['instruction_id'] = instruction['id']
                            detected_signals.append(signal_result)
                            logger.info(f"Signal processed: {instruction['name']} - Detected: {signal_result.get('signal_detected', False)}")
                        else:
                            logger.warning(f"No JSON found in response for {instruction['name']}")
                    except json_module.JSONDecodeError as je:
                        logger.warning(f"Failed to parse signal response for {instruction['name']}: {je}")
                else:
                    logger.warning(f"LLM returned error/empty response for {instruction['name']}: {response_str[:100]}...")
                        
            except Exception as signal_error:
                logger.error(f"Error analyzing signal {instruction['name']}: {signal_error}")
        
        result = {
            "signals": detected_signals,
            "total_articles": len(articles),
            "instructions_used": len(instructions),
            "signals_detected": len([s for s in detected_signals if s.get('signal_detected')]),
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        # Cache the results
        try:
            import json as json_module
            cache_content = json_module.dumps(result, ensure_ascii=False, default=str)
            cache_metadata = {
                "cache_key": cache_key,
                "topic": req.topic,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "days_limit": req.days_limit,
                "instructions_count": len(instructions)
            }
            
            success = db.save_article_analysis_cache(
                article_uri=cache_uri,
                analysis_type=f"realtime_signals_{req.topic}",
                content=cache_content,
                model_used="signal_analysis",
                metadata=cache_metadata
            )
            
            if success:
                logger.info(f"Cache SAVE: real-time signals for {req.topic}")
        except Exception as cache_error:
            logger.warning(f"Failed to cache real-time signals: {cache_error}")
        
        return result
        
    except Exception as exc:
        logger.error("Error in real-time signals analysis: %s", exc)
        raise HTTPException(status_code=500, detail="Real-time signals analysis error")

# ------------------------------------------------------------------
# Debug endpoint for checking available data
# ------------------------------------------------------------------

@router.get("/debug-articles")
async def debug_articles(
    topic: Optional[str] = Query(None, description="Topic to check"),
    session=Depends(verify_session_optional),
):
    """Debug endpoint to check what articles and topics are available."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        # Also check signal alerts
        alerts_query = "SELECT COUNT(*) FROM signal_alerts"
        with db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(alerts_query)
                alerts_count = cursor.fetchone()[0] if cursor.fetchone() else 0
            except:
                alerts_count = 0
        
        logger.info(f"Debug: Found {alerts_count} total signal alerts in database")
    except Exception as e:
        logger.error(f"Error checking alerts count: {e}")
        alerts_count = "unknown"
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        # Get all distinct topics
        topics_query = "SELECT DISTINCT topic, COUNT(*) as count FROM articles GROUP BY topic ORDER BY count DESC LIMIT 10"
        topics = db.fetch_all(topics_query)
        
        # Get recent articles for the specified topic
        recent_articles = []
        if topic:
            articles_query = """
            SELECT uri, title, publication_date, topic, category, sentiment
            FROM articles 
            WHERE (topic = ? OR topic LIKE ? OR title LIKE ? OR summary LIKE ?)
            AND category IS NOT NULL AND sentiment IS NOT NULL
            ORDER BY publication_date DESC
            LIMIT 10
            """
            topic_pattern = f"%{topic}%"
            recent_articles = db.fetch_all(articles_query, (topic, topic_pattern, topic_pattern, topic_pattern))
        
        # Get date range info
        date_range_query = """
        SELECT 
            MIN(DATE(publication_date)) as earliest_date,
            MAX(DATE(publication_date)) as latest_date,
            COUNT(*) as total_articles
        FROM articles 
        WHERE category IS NOT NULL AND sentiment IS NOT NULL
        """
        date_info = db.fetch_one(date_range_query)
        
        # Also get recent signal alerts for debugging
        alerts_debug_query = "SELECT id, article_uri, instruction_name, detected_at, is_acknowledged FROM signal_alerts ORDER BY detected_at DESC LIMIT 10"
        recent_alerts = []
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(alerts_debug_query)
                recent_alerts = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting recent alerts: {e}")
        
        return {
            "available_topics": [dict(t) for t in topics],
            "recent_articles": [dict(a) for a in recent_articles] if recent_articles else [],
            "date_range_info": dict(date_info) if date_info else {},
            "query_topic": topic,
            "signal_alerts_count": alerts_count,
            "recent_alerts": recent_alerts
        }
        
    except Exception as exc:
        logger.error("Error in debug articles: %s", exc)
        return {"error": str(exc)}

# ------------------------------------------------------------------
# Independent signal runner for real-time monitoring
# ------------------------------------------------------------------

class _RunSignalRequest(BaseModel):
    """Request for running specific signal instructions."""
    instruction_ids: List[int] = Field(..., description="Signal instruction IDs to run")
    topic: Optional[str] = Field(None, description="Topic filter for articles")
    days_back: int = Field(7, ge=1, le=30, description="Days back to analyze")
    max_articles: int = Field(100, ge=10, le=500, description="Maximum articles to analyze")
    model: str = Field("gpt-4o-mini", description="AI model to use")
    tag_flagged_articles: bool = Field(True, description="Tag articles that match signals")

@router.post("/run-signals")
async def run_signal_instructions(
    req: _RunSignalRequest,
    session=Depends(verify_session),
):
    """Run specific signal instructions against recent articles independently."""
    try:
        from app.database import get_database_instance
        from datetime import datetime, timedelta
        
        db = get_database_instance()
        
        # Get the specific signal instructions
        all_instructions = db.get_signal_instructions(topic=req.topic, active_only=False)
        instructions = [inst for inst in all_instructions if inst['id'] in req.instruction_ids and inst['is_active']]
        
        if not instructions:
            return {"success": False, "message": "No active signal instructions found with provided IDs"}
        
        # Get articles for the specified time range
        end_date_dt = datetime.now()
        start_date_dt = end_date_dt - timedelta(days=req.days_back)
        
        # Query articles using same approach as working code
        query = """
        SELECT uri, title, summary, news_source, publication_date, category, sentiment
        FROM articles 
        WHERE publication_date >= ? AND publication_date <= ?
        AND category IS NOT NULL AND sentiment IS NOT NULL
        """
        
        params = [start_date_dt.isoformat(), end_date_dt.isoformat()]
        
        if req.topic:
            query += " AND (topic = ? OR title LIKE ? OR summary LIKE ?)"
            topic_pattern = f"%{req.topic}%"
            params.extend([req.topic, topic_pattern, topic_pattern])
        
        query += " ORDER BY publication_date DESC LIMIT ?"
        params.append(req.max_articles)
        
        articles = db.fetch_all(query, params)
        
        if not articles:
            return {
                "success": False, 
                "message": f"No articles found for analysis in the last {req.days_back} days",
                "alerts": [],
                "instructions_run": 0
            }
        
        # Initialize LLM
        from app.ai_models import LiteLLMModel
        from fastapi.concurrency import run_in_threadpool
        
        ai_model = LiteLLMModel.get_instance(req.model)
        if not ai_model:
            raise HTTPException(status_code=500, detail=f"Failed to initialize model {req.model}")
        
        # Run each signal instruction
        alerts_created = []
        total_matches = 0
        
        for instruction in instructions:
            logger.info(f"Running signal instruction: {instruction['name']} (ID: {instruction['id']})")
            
            # Prepare articles for this instruction
            articles_text = "\n\n".join([
                f"Article {i+1}:\n"
                f"Title: {article.get('title') if hasattr(article, 'get') else article['title']}\n"
                f"Source: {article.get('news_source') if hasattr(article, 'get') else article['news_source']}\n"
                f"Date: {article.get('publication_date') if hasattr(article, 'get') else article['publication_date']}\n"
                f"Summary: {article.get('summary') if hasattr(article, 'get') else article['summary']}\n"
                f"URI: {article.get('uri') if hasattr(article, 'get') else article['uri']}"
                for i, article in enumerate(articles[:50])  # Limit to 50 articles per instruction
            ])
            
            # Create analysis prompt
            system_prompt = f"""
            You are a threat intelligence analyst. Analyze the provided articles using this signal instruction:
            
            SIGNAL: {instruction['name']}
            DESCRIPTION: {instruction['description']}
            INSTRUCTION: {instruction['instruction']}
            
            For EACH article that matches the signal, return a separate JSON object:
            {{
                "article_uri": "exact_uri_from_input",
                "signal_detected": true,
                "confidence": 0.0-1.0,
                "summary": "Why this article matches the signal",
                "threat_level": "low"|"medium"|"high",
                "recommended_action": "What analysts should do"
            }}
            
            Return a JSON array of all matching articles: [{{}}, {{}}, ...]
            If no articles match, return an empty array: []
            """
            
            user_prompt = f"Analyze these articles for the signal '{instruction['name']}':\n\n{articles_text}"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            try:
                response_str = await run_in_threadpool(ai_model.generate_response, messages)
                
                if response_str and not ("⚠️" in response_str or "unavailable" in response_str.lower()):
                    try:
                        import re
                        import json as json_module
                        
                        # Look for JSON array
                        json_match = re.search(r'\[.*\]', response_str, re.DOTALL)
                        if json_match:
                            matches = json_module.loads(json_match.group())
                            
                            # Process each match
                            for match in matches:
                                if isinstance(match, dict) and match.get('signal_detected'):
                                    article_uri = match.get('article_uri')
                                    confidence = match.get('confidence', 0.5)
                                    threat_level = match.get('threat_level', 'medium')
                                    summary = match.get('summary', 'Signal detected')
                                    
                                    # Save alert to database
                                    alert_saved = db.save_signal_alert(
                                        article_uri=article_uri,
                                        instruction_id=instruction['id'],
                                        instruction_name=instruction['name'],
                                        confidence=confidence,
                                        threat_level=threat_level,
                                        summary=summary
                                    )
                                    
                                    if alert_saved:
                                        alerts_created.append({
                                            'article_uri': article_uri,
                                            'instruction_name': instruction['name'],
                                            'confidence': confidence,
                                            'threat_level': threat_level,
                                            'summary': summary
                                        })
                                        total_matches += 1
                                        
                                        # Tag the article if requested
                                        if req.tag_flagged_articles:
                                            tag_name = f"SIGNAL_{instruction['name'].replace(' ', '_').upper()}"
                                            db.add_article_tag(article_uri, tag_name, "signal")
                            
                            logger.info(f"Signal '{instruction['name']}' found {len(matches)} matches")
                        else:
                            logger.warning(f"No JSON array found in response for {instruction['name']}")
                            
                    except json_module.JSONDecodeError as je:
                        logger.error(f"Failed to parse signal response for {instruction['name']}: {je}")
                else:
                    logger.warning(f"LLM returned error for signal {instruction['name']}: {response_str[:100]}...")
                    
            except Exception as signal_error:
                logger.error(f"Error running signal {instruction['name']}: {signal_error}")
        
        return {
            "success": True,
            "message": f"Analyzed {len(articles)} articles with {len(instructions)} signal instructions",
            "alerts_created": alerts_created,
            "total_matches": total_matches,
            "instructions_run": len(instructions),
            "articles_analyzed": len(articles),
            "analysis_period": f"{start_date_dt.strftime('%Y-%m-%d')} to {end_date_dt.strftime('%Y-%m-%d')}"
        }
        
    except Exception as exc:
        logger.error("Error in run signal instructions: %s", exc)
        raise HTTPException(status_code=500, detail="Signal runner error")

@router.get("/signal-alerts")
async def get_signal_alerts(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    instruction_id: Optional[int] = Query(None, description="Filter by instruction ID"),
    acknowledged: Optional[str] = Query(None, description="Filter by acknowledgment status (true/false/null)"),
    limit: int = Query(100, ge=1, le=10000, description="Maximum alerts to return"),
    session=Depends(verify_session_optional),
):
    """Get signal alerts for the dashboard."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        logger.info(f"Signal alerts request - topic: {topic}, instruction_id: {instruction_id}, acknowledged: {acknowledged}, limit: {limit}")
        
        # Convert string boolean to actual boolean
        acknowledged_bool = None
        if acknowledged is not None:
            if acknowledged.lower() == 'true':
                acknowledged_bool = True
            elif acknowledged.lower() == 'false':
                acknowledged_bool = False
            else:
                logger.warning(f"Invalid acknowledged value: {acknowledged}")
        
        logger.info(f"Converted acknowledged_bool: {acknowledged_bool}")
        
        alerts = db.get_signal_alerts(
            topic=topic,
            instruction_id=instruction_id,
            acknowledged=acknowledged_bool,
            limit=limit
        )
        
        return {
            "success": True,
            "alerts": alerts,
            "total": len(alerts)
        }
        
    except Exception as exc:
        logger.error("Error getting signal alerts: %s", exc)
        raise HTTPException(status_code=500, detail="Signal alerts retrieval error")

@router.post("/acknowledge-alert/{alert_id}")
async def acknowledge_alert(
    alert_id: int,
    session=Depends(verify_session),
):
    """Acknowledge a signal alert."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        success = db.acknowledge_signal_alert(alert_id)
        
        if success:
            return {"success": True, "message": "Alert acknowledged successfully"}
        else:
            raise HTTPException(status_code=404, detail="Alert not found")
            
    except Exception as exc:
        logger.error("Error acknowledging alert: %s", exc)
        raise HTTPException(status_code=500, detail="Alert acknowledgment error")

# ------------------------------------------------------------------
# Analysis cache endpoints
# ------------------------------------------------------------------


@router.get("/analysis-cache/{article_uri:path}")
async def get_analysis_cache(
    article_uri: str,
    analysis_type: str = Query(..., description="Type of analysis (summary, themes, etc.)"),
    model: str = Query(None, description="Specific model used"),
    session=Depends(verify_session_optional),
):
    """Get cached analysis for an article."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        cached = db.get_article_analysis_cache(
            article_uri=urllib.parse.unquote(article_uri),
            analysis_type=analysis_type,
            model_used=model
        )
        
        if cached:
            return {
                "cached": True,
                "content": cached["content"],
                "model_used": cached["model_used"],
                "generated_at": cached["generated_at"],
                "metadata": cached.get("metadata", {})
            }
        else:
            return {"cached": False}
            
    except Exception as exc:
        logger.error("Error getting analysis cache: %s", exc)
        raise HTTPException(status_code=500, detail="Cache retrieval error")


# Alternate endpoint using query parameter for article_uri to avoid any URL path matching issues
@router.get("/analysis-cache")
async def get_analysis_cache_qp(
    article_uri: str = Query(..., description="Full article URI"),
    analysis_type: str = Query(..., description="Type of analysis (summary, themes, etc.)"),
    model: str = Query(None, description="Specific model used"),
    session=Depends(verify_session_optional),
):
    """Get cached analysis for an article (article_uri as query param)."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()

        # Decode the URI to match what's stored in the database
        decoded_uri = urllib.parse.unquote(article_uri)
        
        # Debug logging to help troubleshoot cache issues
        logger.info(f"Cache lookup - Original URI: {article_uri}")
        logger.info(f"Cache lookup - Decoded URI: {decoded_uri}")
        logger.info(f"Cache lookup - Analysis type: {analysis_type}, Model: {model}")

        cached = db.get_article_analysis_cache(
            article_uri=decoded_uri,  # Use decoded URI to match database storage
            analysis_type=analysis_type,
            model_used=model,
        )
        
        if cached:
            logger.info(f"Cache HIT for {decoded_uri}")
            return {
                "cached": True,
                "content": cached["content"],
                "model_used": cached["model_used"],
                "generated_at": cached["generated_at"],
                "metadata": cached.get("metadata", {}),
            }
        else:
            logger.info(f"Cache MISS for {decoded_uri}")
            
        return {"cached": False}
    except Exception as exc:
        logger.error("Error getting analysis cache (qp): %s", exc)
        raise HTTPException(status_code=500, detail="Cache retrieval error")


class _SaveAnalysisCacheRequest(BaseModel):
    """Payload for saving analysis cache."""
    
    article_uri: str = Field(..., description="Article URI")
    analysis_type: str = Field(..., description="Type of analysis")
    content: str = Field(..., description="Analysis content")
    model_name: str = Field(..., description="Model used for analysis")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


@router.post("/save-analysis-cache")
async def save_analysis_cache(
    req: _SaveAnalysisCacheRequest,
    session=Depends(verify_session_optional),
):
    """Save analysis result to database cache."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        # Debug logging to help troubleshoot cache saves
        logger.info(f"Cache save - URI: {req.article_uri}")
        logger.info(f"Cache save - Analysis type: {req.analysis_type}, Model: {req.model_name}")
        logger.info(f"Cache save - Content length: {len(req.content)} chars")
        
        success = db.save_article_analysis_cache(
            article_uri=req.article_uri,
            analysis_type=req.analysis_type,
            content=req.content,
            model_used=req.model_name,
            metadata=req.metadata
        )
        
        if success:
            logger.info(f"Cache SAVE SUCCESS for {req.article_uri}")
            return {"success": True, "message": "Analysis cached successfully"}
        else:
            logger.warning(f"Cache SAVE FAILED for {req.article_uri}")
            raise HTTPException(status_code=500, detail="Failed to cache analysis")
            
    except Exception as exc:
        logger.error("Error saving analysis cache: %s", exc)
        raise HTTPException(status_code=500, detail="Cache save error")

# ------------------------------------------------------------------
# Article deep-dive endpoint – uses deepdiveprompt.md template
# ------------------------------------------------------------------


class _ArticleDeepDiveRequest(BaseModel):
    """Payload for /article-deep-dive."""

    ids: list[str] = Field(..., description="Single article ID (URI)")
    model: str | None = Field(None, description="LLM name (optional)")


@router.post("/article-deep-dive")
async def article_deep_dive(
    req: _ArticleDeepDiveRequest,
    session=Depends(verify_session),
):
    """Produce a deep-dive analysis for a single article using the template in deepdiveprompt.md."""

    import litellm
    logger = logging.getLogger(__name__)

    if len(req.ids) != 1:
        raise HTTPException(status_code=400, detail="Provide exactly one id for deep-dive analysis")

    # Load template content
    try:
        template_path = (Path(__file__).parent.parent.parent / "deepdiveprompt.md").resolve()
        with open(template_path, "r", encoding="utf-8") as f:
            template_text = f.read()
    except Exception as exc:
        logger.warning("Failed to load deepdiveprompt.md, using fallback instructions: %s", exc)
        template_text = (
            "Use the provided structure to produce a comprehensive deep-dive with sections for definition/context,"
            " multi-dimensional analysis (4-5 dimensions), strategic summary, consensus vs narrative comparison,"
            " strategic/sentiment breakdown, notable examples, conclusion, and final thoughts. Limit 900–1200 words."
        )

    # Fetch document + metadata for the article
    collection = _vector_collection()
    try:
        res = collection.get(ids=req.ids[:1], include=["metadatas", "documents"])  # type: ignore[arg-type]
    except Exception as exc:
        logger.error("Chroma get failed for article-deep-dive: %s", exc)
        raise HTTPException(status_code=500, detail="Vector store error")

    metas: list[dict] = res.get("metadatas", [])
    docs: list[str] = res.get("documents", [])
    if not metas or not docs:
        raise HTTPException(status_code=404, detail="No document found for the given id")

    meta = metas[0]
    doc = docs[0] or ""

    # Construct context
    title = meta.get("title") or "Untitled"
    source = meta.get("news_source") or "Unknown"
    date = meta.get("publication_date") or ""
    url = meta.get("uri") or ""
    category = meta.get("category") or ""
    sentiment = meta.get("sentiment") or ""
    context_header = [
        f"Title: {title}",
        f"Source: {source}",
    ]
    if date:
        context_header.append(f"Date: {date}")
    if url:
        context_header.append(f"URL: {url}")
    if category:
        context_header.append(f"Category: {category}")
    if sentiment:
        context_header.append(f"Sentiment: {sentiment}")

    # Truncate long documents conservatively
    def _truncate(text: str, max_chars: int = 20000) -> str:
        text = str(text or "")
        return text if len(text) <= max_chars else text[:max_chars]

    article_block = "\n".join(context_header) + "\n\n" + _truncate(doc)

    model_name = req.model or "gpt-4o-mini"
    system_msg = (
        "You are Auspex – an expert strategic analyst. Follow the provided template strictly;"
        " ground every point in the article content. Do not invent data."
    )
    user_msg = (
        "Deep-Dive Template Follows (use its structure and headings), then the Article Content:\n\n"
        "=== TEMPLATE START ===\n" + template_text + "\n=== TEMPLATE END ===\n\n"
        "=== ARTICLE START ===\n" + article_block + "\n=== ARTICLE END ===\n\n"
        "Write a 900–1200 word deep-dive tailored to this single article."
    )

    try:
        from datetime import datetime
        generated_at = datetime.utcnow().isoformat() + "Z"
        
        resp = await litellm.acompletion(
            model=model_name,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=2500,
        )
        content = resp.choices[0].message.content
        logger.info("Article deep-dive generated successfully with model: %s", model_name)
        return {"response": content, "generated_at": generated_at}
    except Exception as exc:
        logger.error("LLM article-deep-dive failed with model %s: %s", model_name, exc)
        raise HTTPException(status_code=500, detail=f"LLM error with model {model_name}: {str(exc)}")

# ------------------------------------------------------------------
# Endpoint for retrieving fun news facts
# ------------------------------------------------------------------

# Determine the absolute path to the config directory
_CONFIG_DIR = Path(__file__).parent.parent / "config"
_NEWS_FACTS_FILE = _CONFIG_DIR / "news_facts.json"


@router.get("/news-facts")
async def get_news_facts(session=Depends(verify_session)):
    """Return a list of interesting facts about news and journalism."""
    logger = logging.getLogger(__name__)
    try:
        logger.info(f"Attempting to read news facts from: {_NEWS_FACTS_FILE}")
        if not _NEWS_FACTS_FILE.is_file():
            logger.error(
                f"News facts file not found at path: {_NEWS_FACTS_FILE}"
            )
            raise FileNotFoundError(
                f"Facts file not found at {_NEWS_FACTS_FILE}"
            )
        with open(_NEWS_FACTS_FILE, "r", encoding="utf-8") as f:
            logger.info("News facts file opened successfully.")
            data = json.load(f)
            logger.info("News facts JSON parsed successfully.")
        if "facts" not in data or not isinstance(data["facts"], list):
            logger.error(
                "Invalid format in news_facts.json: "
                "'facts' key missing or not a list."
            )
            raise ValueError(
                "Invalid format: 'facts' key missing or not a list."
            )
        return data  # Return the whole structure {"facts": [...]}
    except FileNotFoundError as exc:
        logger.error("News facts file error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="News facts configuration file not found."
        )
    except json.JSONDecodeError as exc:
        logger.error("News facts JSON decode error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Error reading news facts configuration."
        )
    except ValueError as exc:
        logger.error("News facts file format error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Invalid format in news facts file."
        )
    except Exception as exc:
        logger.error("Failed to get news facts: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred retrieving news facts."
        )

@router.get("/api/news-facts")
async def get_news_facts_endpoint(session=Depends(verify_session)):
    """Return facts about news data from the facts JSON file."""
    try:
        facts_path = os.path.join("app", "config", "news_facts.json")
        if not os.path.exists(facts_path):
            return {"facts": ["News facts file not found."]}
        
        with open(facts_path, "r") as f:
            facts_data = json.load(f)
        
        return {"facts": facts_data.get("facts", [])}
    except Exception as e:
        logging.getLogger(__name__).error(
            "Error loading news facts: %s", str(e)
        )
        return {
            "facts": ["Did you know? There was an error loading news facts."]
        }

@router.delete("/vector-delete/{article_id}")
async def delete_article_from_vector(
    article_id: str,
    session=Depends(verify_session),
):
    """Delete an article from the vector database.
    
    This removes the article from the ChromaDB collection but does not affect
    the relational database. Use this when you want to remove articles from
    vector search results while keeping them in the main database.
    """
    logger = logging.getLogger(__name__)
    
    # Decode the article_id in case it's URL encoded
    try:
        decoded_id = urllib.parse.unquote(article_id)
        logger.info(f"Delete request - Original: {article_id}")
        logger.info(f"Delete request - Decoded: {decoded_id}")
    except Exception as e:
        logger.warning(f"Could not decode article_id: {e}")
        decoded_id = article_id
    
    try:
        collection = _vector_collection()
        
        # First, let's try a broader search to find the article
        # by searching for articles that contain the domain or part of the URL
        found_id = None
        
        # Try both the original and decoded versions first
        article_ids_to_try = [article_id, decoded_id]
        if article_id != decoded_id:
            article_ids_to_try = [decoded_id, article_id]  # Try decoded first
        else:
            article_ids_to_try = [article_id]
        
        # Try direct ID lookup first
        for try_id in article_ids_to_try:
            try:
                logger.info(f"Checking if article exists with ID: {try_id}")
                result = collection.get(ids=[try_id], include=["metadatas"])
                if result.get("ids") and try_id in result["ids"]:
                    found_id = try_id
                    logger.info(f"Found article with direct ID lookup: {found_id}")
                    break
                else:
                    logger.info(f"Article not found with ID: {try_id}")
            except Exception as e:
                logger.warning(
                    f"Error checking article with ID '{try_id}': {e}"
                )
                continue
        
        # If direct lookup failed, try searching by metadata
        if not found_id:
            logger.info("Direct ID lookup failed, trying metadata search")
            try:
                # Extract domain and path for searching
                if "://" in decoded_id:
                    # Try to find by searching for the URL in metadata
                    # Get a larger sample to search through
                    all_results = collection.get(
                        limit=1000, 
                        include=["metadatas"],
                        where=None
                    )
                    ids = all_results.get("ids", [])
                    metadatas = all_results.get("metadatas", [])
                    
                    logger.info(f"Searching through {len(ids)} articles for match")
                    
                    # Look for exact matches or close matches
                    for i, (stored_id, metadata) in enumerate(zip(ids, metadatas)):
                        # Check if the stored ID matches our target
                        if stored_id == decoded_id or stored_id == article_id:
                            found_id = stored_id
                            logger.info(f"Found exact match: {found_id}")
                            break
                        
                        # Check if URI in metadata matches
                        stored_uri = metadata.get("uri", "")
                        if stored_uri == decoded_id or stored_uri == article_id:
                            found_id = stored_id
                            logger.info(f"Found by URI metadata: {found_id}")
                            break
                        
                        # Check for partial URL matches (domain + path)
                        if (decoded_id in stored_id or stored_id in decoded_id or
                            decoded_id in stored_uri or stored_uri in decoded_id):
                            found_id = stored_id
                            logger.info(f"Found by partial match: {found_id}")
                            break
                    
                    # Log some debug info about what we found
                    if not found_id:
                        domain = decoded_id.split("://")[1].split("/")[0]
                        domain_matches = [
                            id for id in ids if domain in id
                        ]
                        logger.info(f"No exact match found. Found {len(domain_matches)} articles from {domain}")
                        if domain_matches:
                            logger.info(f"Sample {domain} articles: {domain_matches[:3]}")
                            
            except Exception as search_e:
                logger.warning(f"Error during metadata search: {search_e}")
        
        if not found_id:
            # Get some debug info about what IDs actually exist
            try:
                sample_results = collection.get(limit=10, include=["metadatas"])
                existing_ids = sample_results.get("ids", [])
                logger.info(f"Vector DB contains articles, sample IDs: {existing_ids[:3]}")
                
                # Count total
                total_count = collection.count()
                logger.info(f"Total articles in vector DB: {total_count}")
                
            except Exception as debug_e:
                logger.warning(f"Could not get debug info: {debug_e}")
            
            raise HTTPException(
                status_code=404, 
                detail=(
                    f"Article not found in vector database. "
                    f"Searched for: {article_ids_to_try}. "
                    f"The article appears in search results but cannot be found "
                    f"for deletion. This might indicate an ID format mismatch. "
                    f"Try running a vector reindex to sync the databases."
                )
            )
        
        # Delete the article from the vector database
        try:
            collection.delete(ids=[found_id])
            logger.info(
                f"Successfully deleted article '{found_id}' from vector "
                f"database"
            )
            
            return {
                "success": True,
                "message": "Article deleted from vector database",
                "deleted_id": found_id,
                "original_id": article_id,
                "search_method": "direct" if found_id in article_ids_to_try else "metadata_search"
            }
            
        except Exception as e:
            logger.error("Error deleting article from vector database: %s", e)
            raise HTTPException(
                status_code=500, 
                detail=(
                    "Failed to delete article from vector database: "
                    f"{str(e)}"
                )
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error("Unexpected error in delete_article_from_vector: %s", e)
        raise HTTPException(
            status_code=500, 
            detail="Internal server error while deleting article"
        )


@router.get("/vector-debug")
async def vector_debug_info(
    session=Depends(verify_session),
):
    """Debug endpoint to check what articles exist in the vector database."""
    logger = logging.getLogger(__name__)
    
    try:
        collection = _vector_collection()
        
        # Get all articles (limited to 100 for debugging)
        result = collection.get(limit=100, include=["metadatas"])
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        
        # Count total articles
        total_count = collection.count()
        
        # Group by domain
        domain_counts = {}
        for article_id in ids:
            if "://" in article_id:
                domain = article_id.split("://")[1].split("/")[0]
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        return {
            "total_articles": total_count,
            "sample_articles": [
                {
                    "id": ids[i] if i < len(ids) else None,
                    "title": metadatas[i].get("title") if i < len(metadatas) else None,
                    "domain": ids[i].split("://")[1].split("/")[0] if i < len(ids) and "://" in ids[i] else "unknown"
                }
                for i in range(min(10, len(ids)))
            ],
            "domain_counts": domain_counts,
            "message": f"Showing first 10 of {len(ids)} articles retrieved (total: {total_count})"
        }
        
    except Exception as e:
        logger.error("Error in vector debug: %s", e)
        return {
            "error": str(e),
            "message": "Could not retrieve vector database information"
        }


# ===== Incident Configuration Management =====

class IncidentConfigRequest(BaseModel):
    """Request model for incident tracking configuration."""
    systemPrompt: str = Field(..., description="System prompt template")
    userPrompt: str = Field(..., description="User prompt template")
    baseOntology: str = Field(..., description="Base ontology definition")
    domainKey: Optional[str] = Field("", description="Domain key for specialized overlays")
    domainOverlay: Optional[str] = Field("", description="Domain-specific overlay rules")
    ontologyExamples: str = Field(..., description="Classification examples")
    analysisInstructions: str = Field(..., description="Analysis guidance")
    qualityGuidelines: str = Field(..., description="Quality control guidelines")
    outputFormat: str = Field(..., description="Output format requirements")
    profileContextTemplate: str = Field(..., description="Organizational profile context template")
    enableProfileIntegration: bool = Field(True, description="Enable organizational profile integration")


@router.get("/incident-config")
async def get_incident_configuration(session=Depends(verify_session_optional)):
    """Get current incident tracking configuration."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        # Try to get user-specific configuration from database
        # For now, we'll return a default structure that matches the frontend expectations
        # In a full implementation, this would query a configurations table
        
        return {
            "success": True,
            "config": {
                # Return empty config to let frontend use localStorage/defaults
            }
        }
        
    except Exception as e:
        logger.error(f"Error retrieving incident configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve configuration: {str(e)}")


@router.post("/incident-config")
async def save_incident_configuration(
    config: IncidentConfigRequest,
    session=Depends(verify_session_optional)
):
    """Save incident tracking configuration."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        
        # For now, we'll just validate the configuration and return success
        # In a full implementation, this would save to a configurations table
        
        # Validate required fields
        if not config.systemPrompt or not config.userPrompt:
            raise HTTPException(status_code=400, detail="System prompt and user prompt are required")
        
        if not config.baseOntology:
            raise HTTPException(status_code=400, detail="Base ontology is required")
        
        # Validate placeholders in system prompt
        required_placeholders = ['{topic}', '{ontology_text}']
        if config.enableProfileIntegration:
            required_placeholders.append('{profile_context}')
        
        missing_placeholders = []
        for placeholder in required_placeholders:
            if placeholder not in config.systemPrompt:
                missing_placeholders.append(placeholder)
        
        if missing_placeholders:
            raise HTTPException(
                status_code=400, 
                detail=f"System prompt missing required placeholders: {', '.join(missing_placeholders)}"
            )
        
        # Validate user prompt placeholders
        user_required = ['{topic}', '{articles_text}']
        missing_user = []
        for placeholder in user_required:
            if placeholder not in config.userPrompt:
                missing_user.append(placeholder)
        
        if missing_user:
            raise HTTPException(
                status_code=400,
                detail=f"User prompt missing required placeholders: {', '.join(missing_user)}"
            )
        
        # TODO: Save to database
        # For now, we rely on localStorage in the frontend
        
        return {
            "success": True,
            "message": "Incident configuration saved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving incident configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")


@router.post("/incident-config/validate")
async def validate_incident_configuration(
    config: IncidentConfigRequest,
    session=Depends(verify_session_optional)
):
    """Validate incident tracking configuration."""
    try:
        validation_issues = []
        
        # Check system prompt
        if not config.systemPrompt:
            validation_issues.append("System prompt is required")
        else:
            required_system_placeholders = ['{topic}', '{ontology_text}']
            if config.enableProfileIntegration:
                required_system_placeholders.append('{profile_context}')
            
            for placeholder in required_system_placeholders:
                if placeholder not in config.systemPrompt:
                    validation_issues.append(f"System prompt missing {placeholder} placeholder")
            
            if 'json' not in config.systemPrompt.lower():
                validation_issues.append("System prompt should specify JSON output format")
        
        # Check user prompt
        if not config.userPrompt:
            validation_issues.append("User prompt is required")
        else:
            required_user_placeholders = ['{topic}', '{articles_text}']
            for placeholder in required_user_placeholders:
                if placeholder not in config.userPrompt:
                    validation_issues.append(f"User prompt missing {placeholder} placeholder")
        
        # Check base ontology
        if not config.baseOntology:
            validation_issues.append("Base ontology is required")
        else:
            required_types = ['incident', 'event', 'entity']
            for type_name in required_types:
                if type_name.lower() not in config.baseOntology.lower():
                    validation_issues.append(f"Base ontology missing '{type_name}' type definition")
        
        # Check ontology examples format
        if config.ontologyExamples:
            try:
                lines = config.ontologyExamples.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('{') and line.endswith('}'):
                        json.loads(line)
            except json.JSONDecodeError:
                validation_issues.append("Invalid JSON format in ontology examples")
        
        # Check profile context template if enabled
        if config.enableProfileIntegration and config.profileContextTemplate:
            profile_placeholders = [
                '{profile_name}', '{industry}', '{organization_type}', 
                '{key_concerns}', '{strategic_priorities}'
            ]
            missing_profile = []
            for placeholder in profile_placeholders:
                if placeholder not in config.profileContextTemplate:
                    missing_profile.append(placeholder)
            
            if missing_profile:
                validation_issues.append(f"Profile context template missing recommended placeholders: {', '.join(missing_profile[:3])}...")
        
        return {
            "valid": len(validation_issues) == 0,
            "issues": validation_issues,
            "message": "Configuration is valid" if len(validation_issues) == 0 else f"Found {len(validation_issues)} validation issues"
        }
        
    except Exception as e:
        logger.error(f"Error validating incident configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to validate configuration: {str(e)}")


@router.get("/incident-config/defaults")
async def get_incident_configuration_defaults(session=Depends(verify_session_optional)):
    """Get default incident tracking configuration templates."""
    
    default_system_prompt = """You are a threat intelligence analyst tracking incidents, entities, and events in {topic}.

IMPORTANT: Assess credibility and plausibility. Treat extraordinary, self-reported breakthroughs with skepticism.
Use factual_reporting, MBFC credibility, and bias indicators. Down-rank or flag items from low/mixed credibility or fringe bias sources.

{profile_context}

{ontology_text}

Required fields for each item:
- name
- type: incident | entity | event
- subtype: from the allowed list for the chosen type
- description
- article_uris
- timeline
- significance: low | medium | high (reduce if credibility concerns exist)
- investigation_leads
- related_entities
- plausibility: likely | questionable | implausible
- source_quality: high | mixed | low
- misinfo_flags: [] e.g., "extraordinary_claim", "no_independent_verification", "low_factuality_source", "fringe_bias"
- credibility_summary: 1-2 sentence rationale

Devil's Advocate Smell Test:
- Add a "devils_advocate" field with brief caution if the claim appears hyperbolic or extraordinary relative to typical evidence.
- Use label "Hyperbolic Claim" when applicable.

Output a pure JSON array only."""

    default_user_prompt = """Analyze these {topic} articles for threat hunting incidents, entities, and events:

{articles_text}"""

    default_base_ontology = """ONTOLOGY — Types and Subtypes
Valid types: incident | event | entity

Definitions:
- incident: Discrete occurrence with material operational/strategic/risk impact that may warrant response, remediation, or escalation.
- event: Noteworthy occurrence (signals, milestones, announcements) that informs context or trends but is not itself a disruptive incident.
- entity: Organization, person, product, venue, dataset (things we track, not occurrences).

Recommended subtypes:
- incident: regulatory_action, compliance_breach, data_security, legal_ip, mna, layoffs, funding_cut, rd_spend_change, governance_change
- event: product_launch, feature_update, partnership_mou, funding_round, hiring, award, conference_announcement, roadmap_teaser, benchmark_result
- entity: company, person, product, dataset, venue, regulator

Assignment rules:
- Prefer 'incident' only when direct impact or required action is likely within the analysis window.
- Prefer 'event' for announcements and market signals absent direct disruptions or obligations.
- Always include a 'subtype' from the lists above."""

    default_profile_context_template = """ORGANIZATIONAL CONTEXT:
Organization: {profile_name} ({organization_type} in {industry})
Region: {region}
Risk Tolerance: {risk_tolerance} | Innovation Appetite: {innovation_appetite}
Decision Making: {decision_making_style}

Key Concerns: {key_concerns}
Strategic Priorities: {strategic_priorities}
Key Stakeholders: {stakeholder_focus}
Competitive Landscape: {competitive_landscape}
Regulatory Environment: {regulatory_environment}

Custom Context: {custom_context}

ANALYSIS INSTRUCTIONS:
- Prioritize incidents and events that align with the organization's key concerns and strategic priorities
- Assess significance based on the organization's risk tolerance and decision-making style  
- Consider impact on key stakeholders and competitive positioning
- Account for relevant regulatory and compliance implications
- Tailor investigation leads to organizational context and priorities"""

    return {
        "success": True,
        "defaults": {
            "systemPrompt": default_system_prompt,
            "userPrompt": default_user_prompt,
            "baseOntology": default_base_ontology,
            "domainKey": "",
            "domainOverlay": "",
            "ontologyExamples": """Labeling examples (JSON objects):
{"name": "Patent infringement suit filed against AlphaBio", "type": "incident", "subtype": "legal_ip"}
{"name": "Competitor releases LLM-based summarizer", "type": "event", "subtype": "product_launch"}
{"name": "AlphaBio", "type": "entity", "subtype": "company"}""",
            "analysisInstructions": """Focus on extracting actionable intelligence from news articles. Prioritize:

1. Material business impacts and strategic changes
2. Regulatory actions and compliance issues
3. Security incidents and data breaches
4. Significant funding, M&A, or operational changes
5. Technology launches and competitive developments

Avoid over-classifying routine announcements as incidents unless they have clear material impact.""",
            "qualityGuidelines": """Credibility Assessment:
- High credibility: Major news outlets, verified sources, multiple independent confirmations
- Mixed credibility: Single source reporting, unverified claims, industry blogs
- Low credibility: Social media rumors, fringe sources, extraordinary claims without evidence

Extraordinary Claims Protocol:
- Flag claims that seem too good to be true or represent major breakthroughs
- Require independent verification for significant technical achievements
- Down-rank significance for self-reported successes without third-party validation""",
            "outputFormat": """Output must be a valid JSON array with each incident object containing all required fields.
Ensure proper JSON escaping of quotes and special characters.
Do not include any explanatory text outside the JSON array.""",
            "profileContextTemplate": default_profile_context_template,
            "enableProfileIntegration": True
        }
        } 
