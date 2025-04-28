from typing import Optional, Dict, Any, List
import logging

from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse

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


@router.get("/vector-search")
def vector_search_endpoint(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(100, ge=1, le=500),
    topic: Optional[str] = None,
    category: Optional[str] = None,
    future_signal: Optional[str] = None,
    sentiment: Optional[str] = None,
    news_source: Optional[str] = None,
):
    """Semantic search endpoint backed by ChromaDB.

    Optional topic, category, future_signal and sentiment parameters map to
    metadata filters to narrow the search space.
    """
    metadata_filter: Dict[str, Any] = {}
    if topic:
        metadata_filter["topic"] = topic
    if category:
        metadata_filter["category"] = category
    if future_signal:
        metadata_filter["future_signal"] = future_signal
    if sentiment:
        metadata_filter["sentiment"] = sentiment
    if news_source:
        metadata_filter["news_source"] = news_source

    results = search_articles(q, top_k=top_k, metadata_filter=metadata_filter)

    # ------------------------------------------------------------------
    # Aggregate stats – mimic Splunk left-hand field list & time histogram
    # ------------------------------------------------------------------
    from collections import Counter, defaultdict
    from datetime import datetime

    facets: dict[str, dict[str, int]] = defaultdict(  # type: ignore[arg-type]
        Counter
    )
    # category -> Counter(date)
    timeline: dict[str, dict[str, int]] = defaultdict(Counter)

    for hit in results:
        meta = hit.get("metadata", {})
        # Facets for quick filters
        for field in (
            "topic",
            "category",
            "news_source",
            "driver_type",
            "sentiment",
        ):
            val = meta.get(field)
            if val:
                facets[field][str(val)] += 1

        # Simple day-level histogram by publication_date (YYYY-MM-DD)
        pub_date = meta.get("publication_date")
        if pub_date:
            try:
                date_obj = datetime.fromisoformat(str(pub_date))
                bucket = date_obj.date().isoformat()
                cat_key = meta.get("category", "Uncategorized")
                timeline[cat_key][bucket] += 1
            except Exception:
                pass

    return JSONResponse(
        content={
            "results": results,
            "facets": facets,
            "timeline": timeline,
        }
    )


@router.post("/vector-reindex")
async def vector_reindex(db: Database = Depends(get_database_instance)):
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
):
    """Return *top_k* articles most similar to the article with *uri*."""
    return {
        "results": similar_articles(uri, top_k=top_k),
    }


# ------------------------------------------------------------------
# Embedding visualisation helpers & endpoints
# ------------------------------------------------------------------


def _fetch_vectors(limit: int | None = None, where: Optional[Dict[str, Any]] = None):
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
    top_k: int = Query(
        500,
        ge=10,
        le=5000,
        description="Number of points to project",
    ),
    topic: Optional[str] = None,
    category: Optional[str] = None,
    future_signal: Optional[str] = None,
    sentiment: Optional[str] = None,
    news_source: Optional[str] = None,
) -> List[dict]:
    """Return a 2-D UMAP projection together with a lightweight cluster label.

    The caller receives a JSON list of objects – *one per vector* – each
    containing ``id``, ``x``, ``y``, ``cluster`` and a couple of handy
    metadata fields (currently ``title``).
    """
    # Build optional metadata filter using same semantics as vector-search
    where: Dict[str, Any] | None = None
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

    vectors, metas, ids = _fetch_vectors(
        limit=top_k,
        where=where,
    )
    if vectors.size == 0:
        return []

    import umap  # type: ignore  # pylint: disable=import-error
    from sklearn.cluster import MiniBatchKMeans  # type: ignore

    # 2-D dimensionality reduction (cosine preserves semantic distances)
    reducer = umap.UMAP(metric="cosine", random_state=42)
    coords = reducer.fit_transform(vectors)

    # Quick, approximate clustering.  Pick k based on dataset size.
    n_clusters = max(4, min(15, len(vectors) // 75))
    km = MiniBatchKMeans(n_clusters=n_clusters, random_state=42)
    clusters = km.fit_predict(coords)

    out: List[dict] = []
    for i, _id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        out.append(
            {
                "id": _id,
                "x": float(coords[i, 0]),
                "y": float(coords[i, 1]),
                "cluster": int(clusters[i]),
                "title": meta.get("title"),
            }
        )
    return out


@router.get("/embedding_neighbours")
def embedding_neighbours(
    id: str = Query(..., description="Vector/Article identifier (uri)"),
    top_k: int = Query(5, ge=1, le=50),
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


# ------------------------------------------------------------------
# Cleaning up completely (optional)
# ------------------------------------------------------------------


@router.post("/clean_collection")
async def clean_collection():
    """Delete and rebuild the collection.

    This is a helper endpoint to clean up completely.  It deletes the
    collection and then re-indexes all articles.
    """
    client = get_chroma_client()
    client.delete_collection("articles")     # drops only the vector index
    # now hit /api/vector-reindex 