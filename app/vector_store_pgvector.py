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
        query: Search query text
        top_k: Number of results to return
        metadata_filter: Optional filters (e.g., {"topic": "AI"})

    Returns:
        List of dicts with id, score, and metadata
    """
    logger.info("Vector search: query='%s', top_k=%d, filters=%s", query, top_k, metadata_filter)

    try:
        # Generate query embedding
        embeddings = _embed_texts([query])
        query_embedding = embeddings[0]

        # Build SQL query with filters
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Convert embedding to PostgreSQL format
        embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

        # Build WHERE clause for filters
        where_clauses = ["embedding IS NOT NULL"]
        params = {"query_embedding": embedding_str, "limit": top_k}

        if metadata_filter:
            for key, value in metadata_filter.items():
                where_clauses.append(f"{key} = :{key}")
                params[key] = value

        where_clause = " AND ".join(where_clauses)

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

        # Build WHERE clause for filters
        where_clauses = ["embedding IS NOT NULL"]
        params = {"limit": top_k}

        if metadata_filter:
            for key, value in metadata_filter.items():
                where_clauses.append(f"{key} = ${len(params) + 1}")
                params[key] = value

        where_clause = " AND ".join(where_clauses)

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
                LIMIT ${len(params) + 1}
            """

            # Build params list for asyncpg (positional)
            param_values = [embedding_str]
            if metadata_filter:
                param_values.extend(metadata_filter.values())
            param_values.append(top_k)

            rows = await conn.fetch(query_sql, *param_values)

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

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build WHERE clause
        where_clauses = ["embedding IS NOT NULL"]
        params = {}

        if where:
            for key, value in where.items():
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
        import numpy as np
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

    return health_status
