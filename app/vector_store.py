import os
import logging
from typing import List, Dict, Any, Optional

import chromadb
try:
    # Try new ChromaDB import path first
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
except ImportError:
    try:
        # Fallback to older import path
        from chromadb.embedding_functions import OpenAIEmbeddingFunction
    except ImportError:
        # Final fallback - define a dummy function
        class OpenAIEmbeddingFunction:
            def __init__(self, *args, **kwargs):
                pass

try:
    from chromadb.errors import NotFoundError as ChromaNotFoundError
except ImportError:
    # Fallback for older ChromaDB versions
    ChromaNotFoundError = Exception

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

_CHROMA_CLIENT: Optional[Any] = None  # ChromaDB client - type varies by version
_COLLECTION_NAME = "articles"
_OPENAI_CLIENT: Optional[Any] = None  # Singleton OpenAI client for embeddings

# Add pathlib import
import pathlib

def _get_openai_client():
    """Get or create singleton OpenAI client for embeddings.

    This prevents creating a new client (and leaking file descriptors)
    on every embedding call.
    """
    global _OPENAI_CLIENT

    if _OPENAI_CLIENT is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key and openai and hasattr(openai, "OpenAI"):
            _OPENAI_CLIENT = openai.OpenAI(api_key=api_key)
            logger.info("Created singleton OpenAI client for embeddings")
        else:
            logger.warning("OpenAI client not available - will use fallback embeddings")

    return _OPENAI_CLIENT

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


def get_chroma_client():
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


def _get_collection():
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

def _truncate_text_for_embedding(text: str, max_tokens: int = 8000) -> str:
    """Truncate text to fit within OpenAI embedding token limits.
    
    Uses tiktoken for accurate token counting if available, otherwise falls back
    to conservative character-based estimation.
    
    Args:
        text: Input text to truncate
        max_tokens: Maximum tokens allowed (default 8000 for safety buffer)
    
    Returns:
        Truncated text that fits within token limit
    """
    try:
        # Try to use tiktoken for accurate token counting
        import tiktoken
        encoding = tiktoken.encoding_for_model("text-embedding-3-small")
        
        # Check if text is already within limits
        tokens = encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        
        # Truncate to max_tokens and decode back to text
        truncated_tokens = tokens[:max_tokens]
        truncated_text = encoding.decode(truncated_tokens)
        
        logger.debug("Truncated text from %d to %d tokens using tiktoken", 
                    len(tokens), len(truncated_tokens))
        return truncated_text
        
    except ImportError:
        # Fallback to character-based estimation if tiktoken not available
        logger.debug("tiktoken not available, using character-based truncation")
        
        # Conservative estimation: 3 characters per token (safer than 4)
        # This accounts for varying token densities in different texts
        max_chars = max_tokens * 3
        
        if len(text) <= max_chars:
            return text
        
        # Truncate at word boundary when possible
        truncated = text[:max_chars]
        last_space = truncated.rfind(' ')
        if last_space > max_chars * 0.8:  # If we find a space in the last 20%
            truncated = truncated[:last_space]
        
        logger.debug("Truncated text from %d to %d characters (estimated %d tokens)", 
                    len(text), len(truncated), len(truncated) // 3)
        return truncated
        
    except Exception as exc:
        # Ultra-safe fallback - very conservative character limit
        logger.warning("Token truncation failed, using ultra-conservative fallback: %s", exc)
        safe_chars = 20000  # Very conservative limit
        if len(text) <= safe_chars:
            return text
        return text[:safe_chars]

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
            # Handle token limits for OpenAI text-embedding-3-small (8192 tokens max)
            cleaned = _truncate_text_for_embedding(cleaned)
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
                # Use singleton client instead of creating new one every time
                client = _get_openai_client()
                if client is None:
                    raise Exception("OpenAI client not available")

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
    from datetime import datetime, timezone
    import re
    
    # Convert publication_date to timestamp for ChromaDB date filtering
    publication_date = article.get("publication_date")
    publication_date_timestamp = None
    
    if publication_date:
        try:
            # Handle different date formats robustly
            if isinstance(publication_date, str):
                # Clean the date string
                date_str = publication_date.strip()
                
                # Format 1: ISO datetime with microseconds: 2025-07-03T12:34:56.123456
                iso_match = re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.(\d+))?(?:Z|[+-]\d{2}:\d{2})?', date_str)
                if iso_match:
                    date_part = iso_match.group(1)  # Extract just the date part
                    # Parse as UTC to avoid timezone issues
                    parsed_date = datetime.strptime(date_part, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    publication_date_timestamp = int(parsed_date.timestamp())
                    logger.debug(f"Parsed ISO datetime '{date_str}' -> timestamp {publication_date_timestamp}")
                
                # Format 2: Date with time: 2025-07-03 12:34:56
                elif ' ' in date_str and len(date_str) > 10:
                    date_part = date_str.split(' ')[0]
                    if re.match(r'\d{4}-\d{2}-\d{2}', date_part):
                        parsed_date = datetime.strptime(date_part, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                        publication_date_timestamp = int(parsed_date.timestamp())
                        logger.debug(f"Parsed datetime '{date_str}' -> timestamp {publication_date_timestamp}")
                
                # Format 3: Simple date: 2025-07-03
                elif re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                    parsed_date = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    publication_date_timestamp = int(parsed_date.timestamp())
                    logger.debug(f"Parsed simple date '{date_str}' -> timestamp {publication_date_timestamp}")
                
                # Format 4: Other common formats
                else:
                    # Try other common date formats
                    date_formats = [
                        '%Y/%m/%d',           # 2025/07/03
                        '%d-%m-%Y',           # 03-07-2025
                        '%d/%m/%Y',           # 03/07/2025
                        '%B %d, %Y',          # July 03, 2025
                        '%d %B %Y',           # 03 July 2025
                        '%d %b %Y',           # 03 Jul 2025
                    ]
                    
                    for fmt in date_formats:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                            publication_date_timestamp = int(parsed_date.timestamp())
                            logger.debug(f"Parsed date '{date_str}' with format '{fmt}' -> timestamp {publication_date_timestamp}")
                            break
                        except ValueError:
                            continue
                    
                    if publication_date_timestamp is None:
                        logger.warning(f"Could not parse date format: '{date_str}' - trying fallback")
                        # Fallback: try to extract YYYY-MM-DD pattern from anywhere in the string
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
                        if date_match:
                            date_part = date_match.group(1)
                            parsed_date = datetime.strptime(date_part, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                            publication_date_timestamp = int(parsed_date.timestamp())
                            logger.debug(f"Fallback extracted date '{date_part}' from '{date_str}' -> timestamp {publication_date_timestamp}")
                        else:
                            # Ultimate fallback: use current date but log it
                            logger.warning(f"Using current date as fallback for unparseable date: '{date_str}'")
                            publication_date_timestamp = int(datetime.now(timezone.utc).timestamp())
            
            elif isinstance(publication_date, datetime):
                # Handle datetime objects - ensure they have timezone info
                if publication_date.tzinfo is None:
                    publication_date = publication_date.replace(tzinfo=timezone.utc)
                publication_date_timestamp = int(publication_date.timestamp())
                logger.debug(f"Converted datetime object -> timestamp {publication_date_timestamp}")
            
            # Validation: ensure timestamp is reasonable (not too far in past/future)
            if publication_date_timestamp:
                current_time = datetime.now(timezone.utc)
                timestamp_date = datetime.fromtimestamp(publication_date_timestamp, tz=timezone.utc)
                
                # Check if date is more than 10 years in past or 1 year in future
                years_diff = (current_time - timestamp_date).days / 365.25
                
                if years_diff > 10:
                    logger.warning(f"Date seems too old ({years_diff:.1f} years ago): {timestamp_date} from '{publication_date}'")
                elif years_diff < -1:
                    logger.warning(f"Date seems to be in future ({abs(years_diff):.1f} years): {timestamp_date} from '{publication_date}'")
                    
        except Exception as e:
            logger.warning(f"Could not convert publication_date '{publication_date}' to timestamp: {e}")
            # CRITICAL: Don't fall back to string value - use None instead
            # ChromaDB requires numeric values for comparison operations
            publication_date_timestamp = None
    
    # Handle tags - convert list to string if necessary for ChromaDB compatibility
    tags = article.get("tags")
    if isinstance(tags, list):
        tags = ', '.join(tags) if tags else ""
    elif tags is None:
        tags = ""
    
    meta = {
        "title": article.get("title"),
        "news_source": article.get("news_source"),
        "category": article.get("category"),
        "future_signal": article.get("future_signal"),
        "sentiment": article.get("sentiment"),
        "time_to_impact": article.get("time_to_impact"),
        "topic": article.get("topic"),
        "publication_date": publication_date,  # Keep original for compatibility
        "publication_date_ts": publication_date_timestamp,  # Add timestamp for filtering (only if numeric)
        "tags": tags,  # Now guaranteed to be a string
        "summary": article.get("summary"),
        "uri": article.get("uri"),
        "driver_type": article.get("driver_type"),
    }
    # Remove keys whose value is ``None`` – Chroma only accepts str, int, float bool.
    # This is critical for publication_date_ts to avoid ChromaDB filtering errors
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
    
#    if not query or not query.strip():
#       logger.warning("Search skipped for empty query.")
#        return []
    
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