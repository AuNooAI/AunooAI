"""
PostgreSQL pgvector-based vector store implementation.

This module replaces ChromaDB with native PostgreSQL pgvector for storing and searching
article embeddings. Benefits:
- No separate database synchronization needed
- Native PostgreSQL querying with vector operations
- Simpler architecture and better performance
- ACID compliance for embeddings

Vector column: articles.embedding vector(1536)
Embedding model: OpenAI text-embedding-3-small (1536 dimensions)
Distance metric: Cosine distance (<=> operator)
"""
import os
import logging
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime, timezone

try:
    import openai
except ImportError:
    openai = None

from sqlalchemy import text
from app.database import get_database_instance

# Import async database for native async operations
try:
    from app.services.async_db import AsyncDatabase
    _async_db_available = True
except ImportError:
    _async_db_available = False
    logger.warning("AsyncDatabase not available, async operations will use thread pool")

logger = logging.getLogger(__name__)

# Singleton OpenAI client for embeddings
_OPENAI_CLIENT: Optional[Any] = None


def _get_openai_client():
    """Get or create singleton OpenAI client for embeddings."""
    global _OPENAI_CLIENT

    if _OPENAI_CLIENT is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key and openai and hasattr(openai, "OpenAI"):
            _OPENAI_CLIENT = openai.OpenAI(api_key=api_key)
            logger.info("Created singleton OpenAI client for pgvector embeddings")
        else:
            logger.warning("OpenAI client not available for pgvector embeddings")

    return _OPENAI_CLIENT


def _truncate_text_for_embedding(text: str, max_tokens: int = 8000) -> str:
    """Truncate text to fit within OpenAI embedding token limits.

    Args:
        text: Input text to truncate
        max_tokens: Maximum tokens allowed (default 8000 for safety buffer)

    Returns:
        Truncated text that fits within token limit
    """
    try:
        import tiktoken
        encoding = tiktoken.encoding_for_model("text-embedding-3-small")

        tokens = encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        truncated_text = encoding.decode(truncated_tokens)

        logger.debug("Truncated text from %d to %d tokens", len(tokens), len(truncated_tokens))
        return truncated_text

    except ImportError:
        # Fallback to character-based estimation
        max_chars = max_tokens * 3
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]
        last_space = truncated.rfind(' ')
        if last_space > max_chars * 0.8:
            truncated = truncated[:last_space]

        logger.debug("Truncated text from %d to %d characters (estimated)", len(text), len(truncated))
        return truncated

    except Exception as exc:
        logger.warning("Token truncation failed, using conservative fallback: %s", exc)
        safe_chars = 20000
        return text[:safe_chars] if len(text) > safe_chars else text


def _embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed texts into vectors using OpenAI.

    Args:
        texts: List of texts to embed

    Returns:
        List of embedding vectors (1536 dimensions each)
    """
    # Clean and validate texts
    cleaned_texts = []
    for text in texts:
        if text is None:
            continue
        cleaned = str(text).strip()
        if cleaned:
            cleaned = _truncate_text_for_embedding(cleaned)
            cleaned_texts.append(cleaned)

    if not cleaned_texts:
        import numpy as np
        logger.warning("No valid texts to embed")
        return np.random.rand(1, 1536).tolist()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not openai:
        logger.warning("OpenAI not available, using random embeddings")
        import numpy as np
        return np.random.rand(len(cleaned_texts), 1536).tolist()

    try:
        client = _get_openai_client()
        if client is None:
            raise Exception("OpenAI client not available")

        logger.debug("Calling OpenAI embedding API with %d texts", len(cleaned_texts))
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=cleaned_texts,
        )

        embeddings_list = []
        for item in sorted(resp.data, key=lambda x: x.index):
            embeddings_list.append(item.embedding)

        return embeddings_list

    except Exception as exc:
        logger.warning("OpenAI embedding failed, falling back to random: %s", exc)
        import numpy as np
        return np.random.rand(len(cleaned_texts), 1536).tolist()


# --------------------------------------------------------------------------------------
# Public API - Compatible with ChromaDB vector_store.py interface
# --------------------------------------------------------------------------------------

def upsert_article(article: Dict[str, Any]) -> None:
    """Upsert an article's embedding into PostgreSQL.

    Args:
        article: Article dict with uri, title, summary, raw, etc.
    """
    conn = None
    try:
        # Get document text for embedding
        doc_text = (
            article.get("raw")
            or article.get("summary")
            or article.get("title")
            or ""
        )
        if not doc_text:
            logger.debug("No textual content for article %s – skipping vector index", article.get("uri"))
            return

        # Generate embedding
        embeddings = _embed_texts([doc_text])
        embedding = embeddings[0]

        # Update database with embedding
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Convert embedding to PostgreSQL array format
        embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'

        stmt = text("""
            UPDATE articles
            SET embedding = CAST(:embedding AS vector)
            WHERE uri = :uri
        """)

        conn.execute(stmt, {"embedding": embedding_str, "uri": article["uri"]})
        conn.commit()

        logger.debug("Upserted embedding for article %s", article.get("uri"))

    except Exception as exc:
        logger.error("Vector upsert failed for article %s: %s", article.get("uri"), exc)
        # CRITICAL FIX: Rollback failed transaction to prevent connection pool contamination
        if conn is not None:
            try:
                conn.rollback()
                logger.debug("Rolled back failed transaction for article %s", article.get("uri"))
            except Exception as rollback_error:
                logger.error("Rollback failed for article %s: %s", article.get("uri"), rollback_error)


async def upsert_article_async(article: Dict[str, Any]) -> None:
    """Native async implementation for upserting article embeddings.

    Args:
        article: Article dictionary with uri, title, summary, etc.
    """
    # Check if native async is available
    if not _async_db_available:
        # Fallback to thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, upsert_article, article)
        return

    try:
        # Get document text for embedding
        doc_text = (
            article.get("raw")
            or article.get("summary")
            or article.get("title")
            or ""
        )
        if not doc_text:
            logger.debug("No textual content for article %s – skipping vector index", article.get("uri"))
            return

        # Generate embedding (sync call, but relatively fast)
        embeddings = _embed_texts([doc_text])
        embedding = embeddings[0]

        # Convert embedding to PostgreSQL array format
        embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'

        # CRITICAL FIX: Use global singleton AsyncDatabase instance to avoid creating new connection pools
        from app.services.async_db import get_async_database_instance
        async_db = get_async_database_instance()
        async with async_db.get_connection() as conn:
            await conn.execute("""
                UPDATE articles
                SET embedding = $1::vector
                WHERE uri = $2
            """, embedding_str, article["uri"])

        logger.debug("Async upserted embedding for article %s", article.get("uri"))

    except Exception as exc:
        logger.error("Async vector upsert failed for article %s: %s", article.get("uri"), exc)


def search_articles(
    query: str,
    top_k: int = 10,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Semantic search in the pgvector index.

    Args:
        query: Search query text (use "*" for all articles)
        top_k: Number of results to return
        metadata_filter: Optional filters (e.g., {"topic": "AI"})

    Returns:
        List of dicts with id, score, and metadata
    """
    logger.info("Vector search: query='%s', top_k=%d, filters=%s", query, top_k, metadata_filter)

    # Handle wildcard query - return all articles (with filters) without vector similarity
    is_wildcard = query.strip() in ('*', '')

    conn = None
    try:
        query_embedding = None
        if not is_wildcard:
            # Generate query embedding for semantic search
            embeddings = _embed_texts([query])
            query_embedding = embeddings[0]

        # Build SQL query with filters
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build WHERE clause for filters
        where_clauses = ["embedding IS NOT NULL"]
        params = {"limit": top_k}

        if metadata_filter:
            # Handle complex $and filters from auspex_service.py
            if "$and" in metadata_filter:
                param_idx = 0
                for condition in metadata_filter["$and"]:
                    for key, value in condition.items():
                        if isinstance(value, dict):
                            # Handle comparison operators like {"$gte": "2025-01-01"}
                            for op, op_value in value.items():
                                param_name = f"param_{param_idx}"
                                if op == "$gte":
                                    where_clauses.append(f"{key} >= :{param_name}")
                                elif op == "$lte":
                                    where_clauses.append(f"{key} <= :{param_name}")
                                elif op == "$gt":
                                    where_clauses.append(f"{key} > :{param_name}")
                                elif op == "$lt":
                                    where_clauses.append(f"{key} < :{param_name}")
                                else:
                                    where_clauses.append(f"{key} = :{param_name}")
                                params[param_name] = op_value
                                param_idx += 1
                        else:
                            # Simple equality
                            param_name = f"param_{param_idx}"
                            where_clauses.append(f"{key} = :{param_name}")
                            params[param_name] = value
                            param_idx += 1
            else:
                # Handle simple {key: value} or {key: {$gte: value}} filters
                for key, value in metadata_filter.items():
                    if isinstance(value, dict):
                        # Handle comparison operators
                        for op, op_value in value.items():
                            if op == "$gte":
                                where_clauses.append(f"{key} >= :{key}")
                            elif op == "$lte":
                                where_clauses.append(f"{key} <= :{key}")
                            elif op == "$gt":
                                where_clauses.append(f"{key} > :{key}")
                            elif op == "$lt":
                                where_clauses.append(f"{key} < :{key}")
                            else:
                                where_clauses.append(f"{key} = :{key}")
                            params[key] = op_value
                    else:
                        where_clauses.append(f"{key} = :{key}")
                        params[key] = value

        where_clause = " AND ".join(where_clauses)

        if is_wildcard:
            # Wildcard query - return all articles matching filters, ordered by date
            stmt = text(f"""
                SELECT
                    uri as id,
                    0.0 as score,
                    title,
                    news_source,
                    category,
                    future_signal,
                    sentiment,
                    time_to_impact,
                    topic,
                    publication_date,
                    tags,
                    summary
                FROM articles
                WHERE {where_clause}
                ORDER BY publication_date DESC NULLS LAST
                LIMIT :limit
            """)
        else:
            # Convert embedding to PostgreSQL format
            embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
            params["query_embedding"] = embedding_str

            # Use cosine distance operator (<=>)
            # Lower distance = more similar (0 = identical, 2 = opposite)
            stmt = text(f"""
                SELECT
                    uri as id,
                    (embedding <=> CAST(:query_embedding AS vector)) as score,
                    title,
                    news_source,
                    category,
                    future_signal,
                    sentiment,
                    time_to_impact,
                    topic,
                    publication_date,
                    tags,
                    summary
                FROM articles
                WHERE {where_clause}
                ORDER BY embedding <=> CAST(:query_embedding AS vector)
                LIMIT :limit
            """)

        result = conn.execute(stmt, params)

        docs = []
        for row in result.mappings():
            docs.append({
                "id": row["id"],
                "score": float(row["score"]),
                "metadata": {
                    "title": row.get("title"),
                    "news_source": row.get("news_source"),
                    "category": row.get("category"),
                    "future_signal": row.get("future_signal"),
                    "sentiment": row.get("sentiment"),
                    "time_to_impact": row.get("time_to_impact"),
                    "topic": row.get("topic"),
                    "publication_date": row.get("publication_date"),
                    "tags": row.get("tags"),
                    "summary": row.get("summary"),
                    "uri": row["id"],
                }
            })

        logger.info("Vector search returned %d results", len(docs))
        return docs

    except Exception as exc:
        logger.error("Vector search failed for query '%s': %s", query, exc)
        # CRITICAL FIX: Rollback any failed transaction (read-only shouldn't create one, but safety first)
        if conn is not None:
            try:
                conn.rollback()
                logger.debug("Rolled back failed search transaction for query '%s'", query)
            except Exception as rollback_error:
                logger.error("Rollback failed for search query '%s': %s", query, rollback_error)
        return []


async def search_articles_async(
    query: str,
    top_k: int = 10,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Native async implementation of vector search using asyncpg.

    Args:
        query: Search query text
        top_k: Number of results to return
        metadata_filter: Optional metadata filter dictionary

    Returns:
        List of search results with id, score, and metadata
    """
    logger.info("Async vector search: query='%s', top_k=%d, filters=%s", query, top_k, metadata_filter)

    # Check if native async is available
    if not _async_db_available:
        # Fallback to thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, search_articles, query, top_k, metadata_filter)

    try:
        # Generate query embedding (this is still blocking, but relatively fast)
        embeddings = _embed_texts([query])
        query_embedding = embeddings[0]

        # Build WHERE clause for filters (asyncpg uses positional params $1, $2, etc.)
        where_clauses = ["embedding IS NOT NULL"]
        param_values = []  # Will be built as we process filters
        param_idx = 2  # Start at 2 since $1 is the embedding

        if metadata_filter:
            # Handle complex $and filters from auspex_service.py
            if "$and" in metadata_filter:
                for condition in metadata_filter["$and"]:
                    for key, value in condition.items():
                        if isinstance(value, dict):
                            # Handle comparison operators like {"$gte": "2025-01-01"}
                            for op, op_value in value.items():
                                if op == "$gte":
                                    where_clauses.append(f"{key} >= ${param_idx}")
                                elif op == "$lte":
                                    where_clauses.append(f"{key} <= ${param_idx}")
                                elif op == "$gt":
                                    where_clauses.append(f"{key} > ${param_idx}")
                                elif op == "$lt":
                                    where_clauses.append(f"{key} < ${param_idx}")
                                else:
                                    where_clauses.append(f"{key} = ${param_idx}")
                                param_values.append(op_value)
                                param_idx += 1
                        else:
                            # Simple equality
                            where_clauses.append(f"{key} = ${param_idx}")
                            param_values.append(value)
                            param_idx += 1
            else:
                # Handle simple {key: value} or {key: {$gte: value}} filters
                for key, value in metadata_filter.items():
                    if isinstance(value, dict):
                        # Handle comparison operators
                        for op, op_value in value.items():
                            if op == "$gte":
                                where_clauses.append(f"{key} >= ${param_idx}")
                            elif op == "$lte":
                                where_clauses.append(f"{key} <= ${param_idx}")
                            elif op == "$gt":
                                where_clauses.append(f"{key} > ${param_idx}")
                            elif op == "$lt":
                                where_clauses.append(f"{key} < ${param_idx}")
                            else:
                                where_clauses.append(f"{key} = ${param_idx}")
                            param_values.append(op_value)
                            param_idx += 1
                    else:
                        where_clauses.append(f"{key} = ${param_idx}")
                        param_values.append(value)
                        param_idx += 1

        where_clause = " AND ".join(where_clauses)
        limit_param_idx = param_idx

        # CRITICAL FIX: Use global singleton AsyncDatabase instance to avoid creating new connection pools
        from app.services.async_db import get_async_database_instance
        async_db = get_async_database_instance()
        async with async_db.get_connection() as conn:
            # Convert embedding to PostgreSQL array format
            embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

            # Execute query with asyncpg
            query_sql = f"""
                SELECT
                    uri as id,
                    (embedding <=> $1::vector) as score,
                    title,
                    news_source,
                    category,
                    future_signal,
                    sentiment,
                    time_to_impact,
                    topic,
                    publication_date,
                    tags,
                    summary
                FROM articles
                WHERE {where_clause}
                ORDER BY embedding <=> $1::vector
                LIMIT ${limit_param_idx}
            """

            # Build final params list: embedding, filter values, limit
            final_params = [embedding_str] + param_values + [top_k]

            rows = await conn.fetch(query_sql, *final_params)

            docs = []
            for row in rows:
                docs.append({
                    "id": row["id"],
                    "score": float(row["score"]),
                    "metadata": {
                        "title": row.get("title"),
                        "news_source": row.get("news_source"),
                        "category": row.get("category"),
                        "future_signal": row.get("future_signal"),
                        "sentiment": row.get("sentiment"),
                        "time_to_impact": row.get("time_to_impact"),
                        "topic": row.get("topic"),
                        "publication_date": row.get("publication_date"),
                        "tags": row.get("tags"),
                        "summary": row.get("summary"),
                        "uri": row["id"],
                    }
                })

            logger.info("Async vector search returned %d results", len(docs))
            return docs

    except Exception as exc:
        logger.error("Async vector search failed for query '%s': %s", query, exc)
        # Fallback to sync version on error
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, search_articles, query, top_k, metadata_filter)


def similar_articles(uri: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Find articles similar to the given URI.

    Args:
        uri: Article URI to find similar articles for
        top_k: Number of similar articles to return

    Returns:
        List of similar articles with id, score, and metadata
    """
    conn = None
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Get the embedding for the reference article
        stmt = text("""
            SELECT embedding
            FROM articles
            WHERE uri = :uri AND embedding IS NOT NULL
        """)

        result = conn.execute(stmt, {"uri": uri})
        row = result.first()

        if not row or row[0] is None:
            logger.warning("No embedding found for article %s", uri)
            return []

        # Extract the embedding once
        reference_embedding = row[0]

        # Find similar articles using the extracted embedding (avoiding subquery repetition)
        stmt = text("""
            SELECT
                uri as id,
                (embedding <=> CAST(:ref_embedding AS vector)) as score,
                title,
                news_source,
                category,
                topic
            FROM articles
            WHERE uri != :uri AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:ref_embedding AS vector)
            LIMIT :limit
        """)

        result = conn.execute(stmt, {
            "uri": uri,
            "ref_embedding": str(reference_embedding),
            "limit": top_k
        })

        docs = []
        for row in result.mappings():
            docs.append({
                "id": row["id"],
                "score": float(row["score"]),
                "metadata": {
                    "title": row.get("title"),
                    "news_source": row.get("news_source"),
                    "category": row.get("category"),
                    "topic": row.get("topic"),
                }
            })

        return docs

    except Exception as exc:
        logger.error("Similar articles search failed for %s: %s", uri, exc)
        # CRITICAL FIX: Rollback any failed transaction
        if conn is not None:
            try:
                conn.rollback()
                logger.debug("Rolled back failed similar_articles transaction for %s", uri)
            except Exception as rollback_error:
                logger.error("Rollback failed for similar_articles %s: %s", uri, rollback_error)
        return []


async def similar_articles_async(uri: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Native async implementation for finding similar articles.

    Args:
        uri: Article URI to find similar articles for
        top_k: Number of similar articles to return

    Returns:
        List of similar articles with id, score, and metadata
    """
    # Check if native async is available
    if not _async_db_available:
        # Fallback to thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, similar_articles, uri, top_k)

    try:
        # CRITICAL FIX: Use global singleton AsyncDatabase instance to avoid creating new connection pools
        from app.services.async_db import get_async_database_instance
        async_db = get_async_database_instance()
        async with async_db.get_connection() as conn:
            # Get the embedding for the reference article
            ref_row = await conn.fetchrow("""
                SELECT embedding
                FROM articles
                WHERE uri = $1 AND embedding IS NOT NULL
            """, uri)

            if not ref_row or ref_row["embedding"] is None:
                logger.warning("No embedding found for article %s", uri)
                return []

            # Extract embedding
            reference_embedding = str(ref_row["embedding"])

            # Find similar articles using native async query
            rows = await conn.fetch("""
                SELECT
                    uri as id,
                    (embedding <=> $1::vector) as score,
                    title,
                    news_source,
                    category,
                    topic
                FROM articles
                WHERE uri != $2 AND embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """, reference_embedding, uri, top_k)

            docs = []
            for row in rows:
                docs.append({
                    "id": row["id"],
                    "score": float(row["score"]),
                    "metadata": {
                        "title": row.get("title"),
                        "news_source": row.get("news_source"),
                        "category": row.get("category"),
                        "topic": row.get("topic"),
                    }
                })

            return docs

    except Exception as exc:
        logger.error("Async similar articles search failed for %s: %s", uri, exc)
        # Fallback to sync version
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, similar_articles, uri, top_k)


def cluster_articles_by_similarity(
    article_uris: List[str],
    similarity_threshold: float = 0.3,
    max_cluster_size: int = 4
) -> List[Dict[str, Any]]:
    """Cluster articles by semantic similarity using pgvector.

    Groups related articles together based on embedding similarity.
    Returns clusters where the first article is the "primary" and others are related.

    Args:
        article_uris: List of article URIs to cluster
        similarity_threshold: Maximum cosine distance to consider articles related (lower = more similar)
        max_cluster_size: Maximum articles per cluster (including primary)

    Returns:
        List of clusters, each containing:
        - primary: The main article dict
        - related: List of related article dicts with similarity scores
    """
    if not article_uris:
        return []

    conn = None
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Fetch all articles with their embeddings
        placeholders = ", ".join([f":uri_{i}" for i in range(len(article_uris))])
        params = {f"uri_{i}": uri for i, uri in enumerate(article_uris)}

        stmt = text(f"""
            SELECT
                uri, title, summary, news_source, publication_date,
                category, topic, sentiment, time_to_impact, tags,
                bias, factual_reporting, mbfc_credibility_rating,
                embedding
            FROM articles
            WHERE uri IN ({placeholders})
            AND embedding IS NOT NULL
            ORDER BY publication_date DESC
        """)

        result = conn.execute(stmt, params)
        articles = []
        for row in result.mappings():
            articles.append(dict(row))

        if not articles:
            return []

        # Track which articles have been assigned to clusters
        assigned = set()
        clusters = []

        # Process articles in order (newest first)
        for article in articles:
            if article['uri'] in assigned:
                continue

            # Start a new cluster with this article as primary
            cluster = {
                'primary': {k: v for k, v in article.items() if k != 'embedding'},
                'related': []
            }
            assigned.add(article['uri'])

            if article['embedding'] is None:
                clusters.append(cluster)
                continue

            # Find similar articles from remaining unassigned articles
            ref_embedding = str(article['embedding'])

            for candidate in articles:
                if candidate['uri'] in assigned:
                    continue
                if candidate['embedding'] is None:
                    continue
                if len(cluster['related']) >= max_cluster_size - 1:
                    break

                # Calculate similarity using pgvector
                sim_stmt = text("""
                    SELECT (CAST(:emb1 AS vector) <=> CAST(:emb2 AS vector)) as distance
                """)
                sim_result = conn.execute(sim_stmt, {
                    'emb1': ref_embedding,
                    'emb2': str(candidate['embedding'])
                })
                distance = sim_result.scalar()

                # Lower distance = more similar
                if distance is not None and distance < similarity_threshold:
                    related_article = {k: v for k, v in candidate.items() if k != 'embedding'}
                    related_article['similarity_score'] = 1.0 - float(distance)  # Convert to similarity
                    cluster['related'].append(related_article)
                    assigned.add(candidate['uri'])

            # Sort related by similarity
            cluster['related'].sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
            clusters.append(cluster)

        # Add any remaining unassigned articles as single-article clusters
        for article in articles:
            if article['uri'] not in assigned:
                clusters.append({
                    'primary': {k: v for k, v in article.items() if k != 'embedding'},
                    'related': []
                })

        logger.info(f"Clustered {len(article_uris)} articles into {len(clusters)} clusters")
        return clusters

    except Exception as exc:
        logger.error(f"Error clustering articles: {exc}")
        # Fallback: return each article as its own cluster
        return []
    finally:
        if conn:
            conn.close()


def get_vectors_by_metadata(
    limit: Optional[int] = None,
    where: Optional[Dict[str, Any]] = None
):
    """Fetch vectors and metadata based on a filter.

    Args:
        limit: Maximum number of results to fetch
        where: Metadata filter dictionary (e.g., {"topic": "AI"})

    Returns:
        Tuple of (vectors_array, metadatas_list, ids_list)
    """
    import numpy as np

    conn = None
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build WHERE clause
        where_clauses = ["embedding IS NOT NULL"]
        params = {}
        param_counter = 0

        if where:
            for key, value in where.items():
                if isinstance(value, dict) and "$in" in value:
                    # Handle $in operator (ChromaDB-style filter)
                    in_values = value["$in"]
                    if in_values:
                        placeholders = []
                        for i, v in enumerate(in_values):
                            param_name = f"in_{param_counter}_{i}"
                            placeholders.append(f":{param_name}")
                            params[param_name] = v
                        where_clauses.append(f"{key} IN ({', '.join(placeholders)})")
                    param_counter += 1
                else:
                    # Simple equality filter
                    where_clauses.append(f"{key} = :{key}")
                    params[key] = value

        if limit:
            params["limit"] = limit

        where_clause = " AND ".join(where_clauses)
        limit_clause = "LIMIT :limit" if limit else ""

        stmt = text(f"""
            SELECT
                uri,
                embedding,
                title,
                topic,
                category,
                news_source
            FROM articles
            WHERE {where_clause}
            {limit_clause}
        """)

        result = conn.execute(stmt, params)

        vectors = []
        metadatas = []
        ids = []

        for row in result.mappings():
            # Parse embedding from database format
            embedding = row["embedding"]
            if embedding:
                # pgvector returns embeddings as strings like '[0.1,0.2,...]'
                if isinstance(embedding, str):
                    embedding = [float(x) for x in embedding.strip('[]').split(',')]
                vectors.append(embedding)
                metadatas.append({
                    "title": row.get("title"),
                    "topic": row.get("topic"),
                    "category": row.get("category"),
                    "news_source": row.get("news_source"),
                })
                ids.append(row["uri"])

        vectors_array = np.array(vectors, dtype=np.float32) if vectors else np.empty((0, 0), dtype=np.float32)
        return vectors_array, metadatas, ids

    except Exception as exc:
        logger.error("get_vectors_by_metadata failed: %s", exc)
        # CRITICAL FIX: Rollback any failed transaction
        if conn is not None:
            try:
                conn.rollback()
                logger.debug("Rolled back failed get_vectors_by_metadata transaction")
            except Exception as rollback_error:
                logger.error("Rollback failed for get_vectors_by_metadata: %s", rollback_error)
        return np.empty((0, 0), dtype=np.float32), [], []


async def get_vectors_by_metadata_async(
    limit: Optional[int] = None,
    where: Optional[Dict[str, Any]] = None
):
    """Async wrapper for get_vectors_by_metadata.

    Args:
        limit: Maximum number of vectors to fetch
        where: Metadata filter dictionary

    Returns:
        Tuple of (vectors_array, metadatas_list, ids_list)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_vectors_by_metadata, limit, where)


def get_by_ids(
    ids: List[str],
    include: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Fetch articles by their URIs - ChromaDB-compatible interface.

    This function provides a ChromaDB-compatible interface for fetching articles
    by their IDs (URIs) from pgvector. It's used by legacy routes that still use
    the old ChromaDB API.

    Args:
        ids: List of article URIs to fetch
        include: List of fields to include ("metadatas", "documents", "embeddings")

    Returns:
        Dictionary with requested fields (ids, metadatas, documents, embeddings)
    """
    if not ids:
        return {"ids": [], "metadatas": [], "documents": [], "embeddings": []}

    include = include or ["metadatas"]

    conn = None
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build parameter placeholders
        placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
        params = {f"id{i}": uri for i, uri in enumerate(ids)}

        # Select fields based on include parameter
        select_fields = ["uri"]
        if "embeddings" in include:
            select_fields.append("embedding")

        # Always fetch all metadata fields
        metadata_fields = [
            "title", "summary", "news_source", "publication_date",
            "category", "sentiment", "sentiment_explanation",
            "future_signal", "driver_type", "time_to_impact",
            "topic", "bias", "factual_reporting", "mbfc_credibility_rating",
            "tags", "topic_alignment_score", "keyword_relevance_score",
            "confidence_score", "overall_match_explanation",
            "extracted_article_topics", "extracted_article_keywords"
        ]
        select_fields.extend(metadata_fields)

        select_clause = ", ".join(select_fields)

        stmt = text(f"""
            SELECT {select_clause}
            FROM articles
            WHERE uri IN ({placeholders})
        """)

        result = conn.execute(stmt, params)

        response = {
            "ids": [],
            "metadatas": [],
            "documents": [],
            "embeddings": []
        }

        for row in result.mappings():
            response["ids"].append(row["uri"])

            if "metadatas" in include:
                metadata = {}
                for field in metadata_fields:
                    value = row.get(field)
                    if value is not None:
                        metadata[field] = value
                response["metadatas"].append(metadata)

            if "documents" in include:
                # Use summary as document text
                response["documents"].append(row.get("summary") or "")

            if "embeddings" in include:
                embedding = row.get("embedding")
                if embedding:
                    # Parse pgvector format '[0.1,0.2,...]' to list
                    if isinstance(embedding, str):
                        embedding = [float(x) for x in embedding.strip('[]').split(',')]
                    response["embeddings"].append(embedding)
                else:
                    response["embeddings"].append(None)

        logger.debug("get_by_ids: Fetched %d articles out of %d requested", len(response["ids"]), len(ids))
        return response

    except Exception as exc:
        logger.error("get_by_ids failed: %s", exc)
        # CRITICAL FIX: Rollback any failed transaction
        if conn is not None:
            try:
                conn.rollback()
                logger.debug("Rolled back failed get_by_ids transaction")
            except Exception as rollback_error:
                logger.error("Rollback failed for get_by_ids: %s", rollback_error)
        return {"ids": [], "metadatas": [], "documents": [], "embeddings": []}


async def get_by_ids_async(
    ids: List[str],
    include: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Async wrapper for get_by_ids.

    Args:
        ids: List of article URIs to fetch
        include: List of fields to include

    Returns:
        Dictionary with ids, metadatas, documents, embeddings
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_by_ids, ids, include)


def delete_embeddings(ids: List[str]) -> int:
    """Delete embeddings for articles by their URIs.

    This sets the embedding column to NULL rather than deleting the article,
    matching the original ChromaDB behavior where deleting from the vector
    store didn't affect the relational database.

    Args:
        ids: List of article URIs to delete embeddings for

    Returns:
        Number of articles affected
    """
    if not ids:
        return 0

    conn = None
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
        params = {f"id{i}": uri for i, uri in enumerate(ids)}

        stmt = text(f"""
            UPDATE articles
            SET embedding = NULL
            WHERE uri IN ({placeholders})
        """)

        result = conn.execute(stmt, params)
        conn.commit()

        affected = result.rowcount
        logger.info("Deleted embeddings for %d articles", affected)
        return affected

    except Exception as exc:
        logger.error("delete_embeddings failed: %s", exc)
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return 0
    finally:
        if conn:
            conn.close()


def count_embeddings() -> int:
    """Count the number of articles with embeddings.

    Returns:
        Number of articles with non-null embeddings
    """
    conn = None
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        result = conn.execute(text(
            "SELECT COUNT(*) FROM articles WHERE embedding IS NOT NULL"
        ))
        count = result.scalar() or 0
        return count

    except Exception as exc:
        logger.error("count_embeddings failed: %s", exc)
        return 0
    finally:
        if conn:
            conn.close()


def check_pgvector_health() -> Dict[str, Any]:
    """Check pgvector health and return status information.

    Returns:
        Dictionary with health status
    """
    health_status = {
        "healthy": False,
        "extension_installed": False,
        "articles_with_embeddings": 0,
        "total_articles": 0,
        "error": None
    }

    conn = None
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Check if pgvector extension is installed
        result = conn.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'"))
        if result.first():
            health_status["extension_installed"] = True

        # Count articles with embeddings
        result = conn.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE embedding IS NOT NULL) as with_embeddings,
                COUNT(*) as total
            FROM articles
        """))
        row = result.first()
        if row:
            health_status["articles_with_embeddings"] = row[0]
            health_status["total_articles"] = row[1]

        health_status["healthy"] = True
        logger.info("pgvector health check passed")

    except Exception as exc:
        health_status["error"] = str(exc)
        logger.error(f"pgvector health check failed: {exc}")
        # CRITICAL FIX: Rollback any failed transaction
        if conn is not None:
            try:
                conn.rollback()
                logger.debug("Rolled back failed pgvector health check transaction")
            except Exception as rollback_error:
                logger.error("Rollback failed for pgvector health check: %s", rollback_error)

    return health_status
