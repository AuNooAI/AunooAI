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

# Add pathlib import
import pathlib 

def _get_embedding_function():
    """Return an embedding function for ChromaDB.

    If OPENAI_API_KEY is set we return an
    :class:`OpenAIEmbeddingFunction` so that Chroma will automatically
    embed texts.  Otherwise we fall back to *None* and the caller must
    supply *embeddings* explicitly when upserting/querying.
    """
    api_key = os.getenv("OPENAI_API_KEY")

    # 1. Scan env for any variable that *contains* OPENAI_API_KEY (covers
    #    suffixes such as OPENAI_API_KEY_GPT_4O).
    if not api_key:
        for name, val in os.environ.items():
            if "OPENAI_API_KEY" in name and val:
                api_key = val
                break

    # 2. Still nothing?  Peek inside LiteLLM config for a key reference or
    #    literal token.
    if not api_key:
        import yaml  # type: ignore
        from pathlib import Path

        cfg_path = Path(__file__).parent / "config" / "litellm_config.yaml"
        if cfg_path.exists():
            try:
                with cfg_path.open("r", encoding="utf-8") as fh:
                    cfg = yaml.safe_load(fh)
                for entry in cfg.get("model_list", []):
                    params: dict = entry.get("litellm_params", {})
                    if params.get("model", "").startswith("openai/"):
                        api_spec = params.get("api_key")
                        if not api_spec:
                            continue
                        if api_spec.startswith("os.environ/"):
                            env_var = api_spec.split("/", 1)[1]
                            api_key = os.getenv(env_var)
                        else:
                            api_key = api_spec
                        if api_key:
                            break
            except Exception as exc:  # pragma: no cover – config optional
                logger.warning("Failed to read litellm_config.yaml: %s", exc)

    if api_key and openai:
        logger.info("Vector store: using OpenAI embeddings (text-embedding-3-small)")
        return OpenAIEmbeddingFunction(api_key, model_name="text-embedding-3-small")

    # Diagnostic logging – explain why we cannot use OpenAI
    if not api_key:
        logger.warning(
            "Vector store: no OPENAI_API_KEY* env var found – falling back to the "
            "built-in ONNX mini-LM embedder."
        )
    elif not openai:
        logger.warning(
            "Vector store: 'openai' package not installed – falling back to ONNX embedder."
        )
    else:
        logger.warning(
            "Vector store: unknown reason prevented OpenAI embedder – falling back to ONNX."
        )

    return None  # Caller will embed manually.


def get_chroma_client() -> chromadb.Client:
    """Return a (singleton) ChromaDB client instance."""
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is None:
        # --- MODIFICATION START ---
        # Get the directory where vector_store.py resides
        current_file_dir = pathlib.Path(__file__).parent.resolve()
        # Assume chromadb is in the parent directory (project root) relative to this file's parent (app/)
        # Adjust this logic if your chromadb directory is elsewhere relative to vector_store.py
        project_root = current_file_dir.parent
        chroma_path = project_root / os.getenv("CHROMA_DB_DIR", "chromadb")
        chroma_path_str = str(chroma_path.resolve()) # Get absolute path string
        logger.info(f"Attempting to connect to ChromaDB at absolute path: {chroma_path_str}")
        _CHROMA_CLIENT = chromadb.PersistentClient(
            # path=os.getenv("CHROMA_DB_DIR", "./chromadb") # Original relative path
            path=chroma_path_str # Use absolute path
        )
        # --- MODIFICATION END ---
    return _CHROMA_CLIENT


def _get_collection() -> chromadb.Collection:
    """Return (and create if necessary) the Chroma collection for articles."""
    client = get_chroma_client()

    # We try to get it; if it does not exist we create it with an optional embedder
    try:
        col = client.get_collection(name=_COLLECTION_NAME)
        # Note: ChromaDB collections have their embedding function set at creation time
        # and cannot be modified afterwards. If we need a different embedding function,
        # we would need to recreate the collection.
        return col
    except (ValueError, ChromaNotFoundError):  # Collection absent → create
        return client.create_collection(
            name=_COLLECTION_NAME,
            embedding_function=_get_embedding_function(),
            metadata={"hnsw:space": "cosine"}  # Use cosine distance for 0-1 similarity scores
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
    # Ensure all texts are strings and filter out None/empty values
    raw_texts = [str(text) for text in texts if text is not None]
    
    # Clean and validate texts
    cleaned_texts = []
    for text in raw_texts:
        # Strip whitespace and ensure it's not empty
        cleaned = text.strip()
        if cleaned:  # Only add non-empty strings
            # Truncate very long texts (OpenAI has an 8191 token limit for text-embedding-3-small)
            # Roughly 4 chars per token, so limit to ~30000 chars to be safe
            if len(cleaned) > 30000:
                cleaned = cleaned[:30000]
            cleaned_texts.append(cleaned)
    
    # Handle empty texts list
    if not cleaned_texts:
        import numpy as np
        logger.warning("No valid texts to embed after cleaning")
        return np.random.rand(1, 1536).tolist()  # Return single random vector
    
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and openai:
        try:
            # Log the texts being embedded for debugging
            logger.debug("Embedding %d texts, first text (truncated): %s", 
                        len(cleaned_texts), 
                        cleaned_texts[0][:50] if cleaned_texts else "")
            
            if hasattr(openai, "OpenAI"):  # Official >=1.0 client
                client = openai.OpenAI(api_key=api_key)  # type: ignore
                
                logger.debug("Calling OpenAI embedding API with %d texts", len(cleaned_texts))
                resp = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=cleaned_texts,
                )
                data = resp.data  # type: ignore[attr-defined]
            else:  # Legacy 0.x SDK
                openai.api_key = api_key  # type: ignore[attr-defined]
                resp = getattr(openai, "Embedding").create(  # type: ignore[attr-defined]
                    model="text-embedding-3-small",
                    input=cleaned_texts,
                )
                data = resp["data"]

            def _get_idx(it):
                return it["index"] if isinstance(it, dict) else it.index  # type: ignore[attr-defined]

            embeddings_list = []
            for it in sorted(data, key=_get_idx):
                emb = it["embedding"] if isinstance(it, dict) else it.embedding  # type: ignore[attr-defined]
                embeddings_list.append(emb)

            return embeddings_list
        except Exception as exc:
            logger.warning(
                "OpenAI embedding failed, falling back to random. Error: %s",
                exc,
            )
    # Fallback – random vectors (fixed dimensionality of 1536 for compatibility)
    import numpy as np  # Lazy import to avoid dependency if not needed.

    return np.random.rand(len(cleaned_texts), 1536).tolist()

# --------------------------------------------------------------------------------------
# Public API – upsert & search
# --------------------------------------------------------------------------------------

# Define internal helper _fetch_vectors *before* functions that use it
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
    
    # Use the singleton getter
    collection = _get_collection()
    
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

# --- Public function to fetch vectors by metadata filter ---
def get_vectors_by_metadata(limit: Optional[int] = None, where: Optional[Dict[str, Any]] = None):
    """Public interface to fetch vectors and metadata based on a filter.

    Args:
        limit: Maximum number of results to fetch.
        where: Metadata filter dictionary (e.g., {"topic": "some_topic"}).

    Returns:
        Tuple containing (vectors_numpy_array, metadatas_list, ids_list).
        Returns (empty_array, [], []) on error or if no data found.
    """
    # Lazy import numpy here if not already imported at module level
    import numpy as np 
    try:
        # Call the internal function (now defined above)
        vecs, metas, ids = _fetch_vectors(limit=limit, where=where)
        return vecs, metas, ids
    except Exception as e:
        logger.error(f"Error in get_vectors_by_metadata: {e}", exc_info=True)
        # Return empty structures consistent with _fetch_vectors error handling
        return np.empty((0, 0), dtype=np.float32), [], []

def similar_articles(uri: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Return *top_k* articles most similar to the one with *uri*.

    The first result returned by Chroma is the reference article itself – we
    skip it and return the next closest matches.
    """
    try:
        collection = _get_collection()

        doc_data = collection.get(ids=[uri], include=["documents"])  # type: ignore[arg-type]
        if not doc_data.get("ids"):
            return []

        doc_text = doc_data["documents"][0]

        # Always embed locally (1536-dim) to avoid relying on the collection's
        # attached embedder which may differ in dimensionality.
        embeds = _embed_texts([doc_text])
        res = collection.query(
            query_embeddings=embeds,
            n_results=top_k + 1,
            include=["metadatas", "distances"],
        )

        out: List[Dict[str, Any]] = []
        for idx, _id in enumerate(res["ids"][0]):
            if _id == uri:
                continue
            out.append(
                {
                    "id": _id,
                    "score": res["distances"][0][idx],
                    "metadata": res["metadatas"][0][idx],
                }
            )
            if len(out) >= top_k:
                break
        return out
    except Exception as exc:  # pragma: no cover – log & degrade gracefully
        logger.error("Vector similarity search failed for %s – %s", uri, exc)
        return []

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
            # Always embed locally to avoid relying on whatever embedder the
            # collection happens to have attached (which may differ in
            # dimensionality).  This guarantees consistent 1536-dim vectors.
            embs = _embed_texts([doc_text])
            col.upsert(
                ids=[article["uri"]],
                documents=[doc_text],
                embeddings=embs,
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
    meta = {
        "title": article.get("title"),
        "news_source": article.get("news_source"),
        "category": article.get("category"),
        "future_signal": article.get("future_signal"),
        "sentiment": article.get("sentiment"),
        "time_to_impact": article.get("time_to_impact"),
        "topic": article.get("topic"),
        "publication_date": article.get("publication_date"),
        "tags": article.get("tags"),
        "summary": article.get("summary"),
        "uri": article.get("uri"),
        "driver_type": article.get("driver_type"),
    }
    # Remove keys whose value is ``None`` – Chroma only accepts str, int, float bool.
    return {k: v for k, v in meta.items() if v is not None}


def search_articles(
    query: str,
    top_k: int = 10,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Semantic search in the vector index.

    Returns a list of dictionaries with ``id``, ``score`` and ``metadata``.
    """
    logger.info(
        "Vector search called with query: '%s', top_k: %d, metadata_filter: %s",
        query, top_k, metadata_filter
    )
    
    try:
        collection = _get_collection()
        
        # If we have filters, check what actual values exist in the database first
        # This will help us construct an accurate filter
        if metadata_filter:
            # Inspect existing values for each filter field
            for field in metadata_filter:
                try:
                    # Get distinct values for this field
                    logger.info("Checking values for field: %s", field)
                    # Get a sample of data to check actual field values
                    sample = collection.get(limit=1000, include=["metadatas"])
                    if not sample.get("metadatas"):
                        logger.warning("No sample data found for field inspection")
                        continue
                        
                    # Collect all values that exist for this field
                    field_values = set()
                    for meta in sample["metadatas"]:
                        if field in meta and meta[field]:
                            field_values.add(meta[field])
                    
                    if field_values:
                        logger.info(
                            "Field '%s' has %d unique values in DB: %s", 
                            field, len(field_values), 
                            list(field_values)[:20] if len(field_values) > 20 
                            else list(field_values)
                        )
                except Exception as e:
                    logger.error("Error inspecting field values: %s", e)

        # Build query kwargs dynamically to avoid passing an *empty* ``where``
        # dict – newer Chroma versions treat an empty filter as invalid and
        # raise "Expected where to have exactly one operator".
        query_kwargs: dict[str, Any] = {
            "n_results": top_k,
            "include": ["metadatas", "distances"],
        }
        if metadata_filter:
            # Log the incoming filter for debugging
            logger.info("Processing metadata filter: %s", metadata_filter)
            
            # Special case handling for common values with known variants
            processed_filter = {}
            for k, v in metadata_filter.items():
                # Exact value for most fields
                processed_value = v
                
                # Special cases for known problematic values
                if k.lower() == "category" and isinstance(v, str):
                    v_lower = v.lower()
                    # Handle common category variants
                    if "ai business" in v_lower:
                        processed_value = "AI Business"
                    elif "ai at work" in v_lower or "ai and employment" in v_lower:
                        processed_value = "AI at Work and Employment"
                    elif "ai society" in v_lower:
                        processed_value = "AI and Society"
                    elif "ai trust" in v_lower or "risk" in v_lower:
                        processed_value = "AI Trust, Risk, and Security Management"
                    elif "data center" in v_lower:
                        processed_value = "AI in the Data Center"
                
                processed_filter[k] = processed_value
                
                # Log if we changed the value
                if processed_value != v:
                    logger.info(
                        "Normalized filter value for %s: '%s' -> '%s'", 
                        k, v, processed_value
                    )
            
            # Use the processed filters
            query_kwargs["where"] = processed_filter
            
            # Log the actual where filter after processing
            logger.info("Using Chroma where clause: %s", query_kwargs["where"])
        else:
            logger.info("No metadata filter applied")

        try:
            embeds = _embed_texts([query])
            res = collection.query(
                query_embeddings=embeds,
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

def embedding_projection(vecs: List[List[float]]) -> Dict[str, Any]:
    """Cluster the vectors using MiniBatchKMeans and return centroids and sizes."""
    from sklearn.cluster import MiniBatchKMeans
    from collections import Counter

    km = MiniBatchKMeans(n_clusters=3, random_state=42)
    clusters = km.fit_predict(vecs)
    centroids = km.cluster_centers_.tolist()
    sizes = Counter(clusters)

    out = []
    for i, cluster in enumerate(clusters):
        out.append({
            "x": vecs[i][0],
            "y": vecs[i][1],
            "cluster": cluster,
            "size": sizes[cluster],
        })

    return {
        "points": out,
        "centroids": centroids,
        "sizes": sizes,
    } 