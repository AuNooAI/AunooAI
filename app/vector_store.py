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
        _CHROMA_CLIENT = chromadb.PersistentClient(
            path=os.getenv("CHROMA_DB_DIR", "./chromadb")
        )
    return _CHROMA_CLIENT


def _get_collection() -> chromadb.Collection:
    """Return (and create if necessary) the Chroma collection for articles."""
    client = get_chroma_client()

    # We try to get it; if it does not exist we create it with an optional embedder
    try:
        col = client.get_collection(name=_COLLECTION_NAME)
        # If the collection was created earlier without an embedder, attach one
        # dynamically so we no longer need to supply embeddings manually.
        if col._embedding_function is None:  # type: ignore[attr-defined]
            emb_fn = _get_embedding_function()
            if emb_fn is not None:
                col.add_embedding_function(emb_fn)  # type: ignore[attr-defined]
        return col
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
        try:
            if hasattr(openai, "OpenAI"):  # Official >=1.0 client
                client = openai.OpenAI(api_key=api_key)  # type: ignore
                resp = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts,
                )
                data = resp.data  # type: ignore[attr-defined]
            else:  # Legacy 0.x SDK
                openai.api_key = api_key  # type: ignore[attr-defined]
                resp = getattr(openai, "Embedding").create(  # type: ignore[attr-defined]
                    model="text-embedding-3-small",
                    input=texts,
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

    return np.random.rand(len(texts), 1536).tolist()

# --------------------------------------------------------------------------------------
# Public API – upsert & search
# --------------------------------------------------------------------------------------

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
        "summary": article.get("summary"),
        "uri": article.get("uri"),
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
            query_kwargs["where"] = (
                metadata_filter
                if len(metadata_filter) == 1
                else {"$and": [{k: v} for k, v in metadata_filter.items()]}
            )

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