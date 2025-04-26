import os
import logging
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from chromadb.errors import NotFoundError as ChromaNotFoundError  # type: ignore

try:
    import openai  # Optional; only required if OPENAI_API_KEY configured
except ImportError:  # pragma: no cover
    openai = None  # type: ignore

logger = logging.getLogger(__name__)

# pylint: disable=line-too-long
# flake8: noqa: E501

# --------------------------------------------------------------------------------------
# Singleton helpers
# --------------------------------------------------------------------------------------

_CHROMA_CLIENT: Optional[chromadb.Client] = None
_COLLECTION_NAME = "articles"


def _get_embedding_function():
    """Return an embedding function for ChromaDB.

    If OPENAI_API_KEY is set we return an
    :class:`OpenAIEmbeddingFunction` so that Chroma will automatically
    embed texts.  Otherwise we fall back to *None* and the caller must
    supply *embeddings* explicitly when upserting/querying.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and openai:
        return OpenAIEmbeddingFunction(
            api_key, model_name="text-embedding-3-small"
        )
    return None  # Caller will embed manually.


def get_chroma_client() -> chromadb.Client:
    """Return a (singleton) ChromaDB client instance."""
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is None:
        _CHROMA_CLIENT = chromadb.PersistentClient(
            path=os.getenv("CHROMA_DB_DIR", "./chromadb")
        )
    return _CHROMA_CLIENT


def _get_collection() -> chromadb.Collection:
    """Return (and create if necessary) the Chroma collection for articles."""
    client = get_chroma_client()

    # We try to get it; if it does not exist we create it with an optional embedder
    try:
        return client.get_collection(name=_COLLECTION_NAME)
    except (ValueError, ChromaNotFoundError):  # Collection absent → create
        return client.create_collection(
            name=_COLLECTION_NAME,
            embedding_function=_get_embedding_function(),
        )

# --------------------------------------------------------------------------------------
# Embedding helpers
# --------------------------------------------------------------------------------------

def _embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed *texts* into vectors.

    We try to use OpenAI if the key is present, otherwise we fall back to random
    vectors so the pipeline still works in dev scenarios without an embedding
    provider.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and openai:
        openai.api_key = api_key
        try:
            resp = openai.Embedding.create(
                model="text-embedding-3-small",
                input=texts,
            )
            # The response ordering is guaranteed to match the input order.
            return [
                item["embedding"]
                for item in sorted(resp["data"], key=lambda x: x["index"])
            ]
        except Exception as exc:
            logger.warning(
                "OpenAI embedding failed, falling back to random. Error: %s",
                exc,
            )
    # Fallback – random vectors (fixed dimensionality of 1536 for compatibility)
    import numpy as np  # Lazy import to avoid dependency if not needed.

    return np.random.rand(len(texts), 1536).tolist()

# --------------------------------------------------------------------------------------
# Public API – upsert & search
# --------------------------------------------------------------------------------------

def upsert_article(article: Dict[str, Any]) -> None:
    """Upsert an *article* into the Chroma collection.

    Parameters
    ----------
    article : dict
        Article dict *after* saving in the relational DB.  Must include at least
        ``uri`` as the unique identifier.  We use ``summary`` or ``raw`` (if
        provided) as the document text.
    """
    try:
        collection = _get_collection()

        doc_text = (
            article.get("raw")
            or article.get("summary")
            or article.get("title")
            or ""
        )
        if not doc_text:
            logger.debug(
                "No textual content for article %s – skipping vector index.",
                article.get("uri"),
            )
            return

        def _do_upsert(col):
            if col._embedding_function is None:  # type: ignore[attr-defined]
                embs = _embed_texts([doc_text])
                col.upsert(
                    ids=[article["uri"]],
                    documents=[doc_text],
                    embeddings=embs,
                    metadatas=[_build_metadata(article)],
                )
            else:
                col.upsert(
                    ids=[article["uri"]],
                    documents=[doc_text],
                    metadatas=[_build_metadata(article)],
                )

        try:
            _do_upsert(collection)
        except (ValueError, ChromaNotFoundError) as err:
            if "does not exists" in str(err):
                # Recreate collection and retry once.
                logger.warning("Collection missing during upsert; recreating…")
                col2 = _get_collection()
                _do_upsert(col2)
            else:
                raise
    except Exception as exc:
        if "does not exists" in str(exc):
            # Expected during the very first start-up when multiple workers race
            # before the collection catalogue is fully initialised.
            logger.warning(
                "Vector upsert skipped for article %s – collection absent.",
                article.get("uri"),
            )
        else:
            logger.error(
                "Vector upsert failed for article %s – %s",
                article.get("uri"),
                exc,
            )


def _build_metadata(article: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a subset of article fields to use as vector metadata."""
    return {
        "title": article.get("title"),
        "news_source": article.get("news_source"),
        "category": article.get("category"),
        "future_signal": article.get("future_signal"),
        "sentiment": article.get("sentiment"),
        "time_to_impact": article.get("time_to_impact"),
        "topic": article.get("topic"),
        "publication_date": article.get("publication_date"),
        "summary": article.get("summary"),
        "uri": article.get("uri"),
    }


def search_articles(
    query: str,
    top_k: int = 10,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Semantic search in the vector index.

    Returns a list of dictionaries with ``id``, ``score`` and ``metadata``.
    """
    try:
        collection = _get_collection()

        # Build query kwargs dynamically to avoid passing an *empty* ``where``
        # dict – newer Chroma versions treat an empty filter as invalid and
        # raise "Expected where to have exactly one operator".
        query_kwargs: dict[str, Any] = {
            "n_results": top_k,
            "include": ["metadatas", "distances"],
        }
        if metadata_filter:
            query_kwargs["where"] = metadata_filter

        try:
            if collection._embedding_function is None:  # type: ignore[attr-defined]
                embeds = _embed_texts([query])
                res = collection.query(
                    query_embeddings=embeds,
                    **query_kwargs,
                )
            else:
                res = collection.query(
                    query_texts=[query],
                    **query_kwargs,
                )
        except (ValueError, ChromaNotFoundError) as err:
            if "does not exists" in str(err):
                logger.warning("Collection missing; recreating…")
                _get_collection()
                return []
            raise

        # Convert to a friendlier structure
        result_docs = []
        for idx, _id in enumerate(res["ids"][0]):
            result_docs.append(
                {
                    "id": _id,
                    "score": res["distances"][0][idx],
                    "metadata": res["metadatas"][0][idx],
                }
            )
        return result_docs
    except Exception as exc:
        # Downgrade the log level when the root cause is the (expected) missing
        # collection during the very first boot-strap / migration phase.  This
        # avoids frightening ERROR lines when the system is still warming up.
        if "does not exists" in str(exc):
            logger.warning(
                "Vector search failed for query '%s' – collection is absent; returning empty list.",
                query,
            )
            return []

        logger.error(
            "Vector search failed for query '%s' – %s", query, exc
        )
        return [] 