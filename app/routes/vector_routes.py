from typing import Optional, Dict, Any
import logging
from dateutil.parser import parse as dt_parse  # add top of file

from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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
    top_k: int = Query(100, ge=1),
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
        le=5000,
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
) -> Dict[str, Any]:
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
        return {}

    from sklearn.cluster import MiniBatchKMeans  # type: ignore

    # 2-D projection ---------------------------------------------------------
    if method == "tsne":
        from sklearn.manifold import TSNE  # type: ignore

        reducer = TSNE(
            n_components=dims,
            metric="cosine",
            random_state=42,
            init="random",
            learning_rate="auto",
        )
        coords = reducer.fit_transform(vectors)
    elif method == "pca":
        from sklearn.decomposition import PCA  # type: ignore

        reducer = PCA(n_components=dims, random_state=42)
        coords = reducer.fit_transform(vectors)
    else:  # default UMAP
        import umap  # type: ignore  # pylint: disable=import-error

        reducer = umap.UMAP(
            n_components=dims,
            metric="cosine",
            random_state=42,
        )
        coords = reducer.fit_transform(vectors)

    # ------------------
    # Clustering (PCA-50  →  k-means).
    # Keep UMAP/t-SNE/PCA 2-D *coords* for the plot but cluster on a
    # higher-dimensional representation to preserve structure.
    # ------------------
    from sklearn.decomposition import PCA  # type: ignore

    if vectors.shape[1] > 50:
        pca50 = PCA(n_components=50, random_state=42)
        vec_for_cluster = pca50.fit_transform(vectors)
    else:
        # The original space is already small; use it directly.
        vec_for_cluster = vectors

    # Use user-supplied cluster count capped by dataset size
    n_clusters = max(2, min(n_clusters, len(vec_for_cluster)))

    km = MiniBatchKMeans(n_clusters=n_clusters, random_state=42)
    clusters = km.fit_predict(vec_for_cluster)

    # ------------------ Explainability helpers ------------------
    import re
    from collections import Counter, defaultdict
    import numpy as np  # type: ignore
    from sklearn.feature_extraction import text as _sk_text  # type: ignore
    STOP_WORDS = set(_sk_text.ENGLISH_STOP_WORDS)

    tokens_by_cluster: dict[int, list[str]] = defaultdict(list)

    for idx, lbl in enumerate(clusters):
        meta = metas[idx] if idx < len(metas) else {}
        text = f"{meta.get('title', '')} {meta.get('summary', '')}"
        # Tokenise and drop common stop-words, keep words ≥3 chars.
        toks = [
            t.lower()
            for t in re.findall(r"\b\w{3,}\b", text)
            if t.lower() not in STOP_WORDS
        ]
        tokens_by_cluster[int(lbl)].extend(toks)

    explain: Dict[int, list[str]] = {}
    for lbl, toks in tokens_by_cluster.items():
        most_common = Counter(toks).most_common(5)
        explain[lbl] = [w for w, _ in most_common]

    # Centroids only make sense for 2-D visualisations.
    centroids: Dict[int, list[float]] = {}
    if dims == 2:
        for lbl in set(clusters):
            idxs = np.where(clusters == lbl)[0]
            if idxs.size:
                centroids[int(lbl)] = [
                    float(coords[idxs, 0].mean()),
                    float(coords[idxs, 1].mean()),
                ]

    points: list[dict] = []
    for i, _id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        point: dict[str, Any] = {
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

    return {
        "points": points,
        "explain": explain,
        "centroids": centroids,
    }


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


@router.get("/patterns")
def patterns_endpoint(
    q: Optional[str] = Query(
        None,
        description="Optional search query to seed the article set",
    ),
    top_k: int = Query(
        1000,
        ge=10,
        le=5000,
    ),
    topic: Optional[str] = None,
    category: Optional[str] = None,
    future_signal: Optional[str] = None,
    sentiment: Optional[str] = None,
    news_source: Optional[str] = None,
):
    """Return simple textual pattern stats.

    We compute top unigrams/bigrams and a tiny co-occurrence matrix.
    The pattern extraction logic
    works only on *title* and *summary* and avoids heavy NLP dependencies.
    """
    # --- Gather articles -----------------------------------------------------
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

    # When *q* is empty we still want some material –
    # fall back to a broad fetch
    query_str = q or "*"
    articles = search_articles(
        query_str,
        top_k=top_k,
        metadata_filter=meta_filter,
    )

    from collections import Counter, defaultdict
    import re
    from sklearn.feature_extraction import text as _sk_text  # type: ignore

    STOP_WORDS = set(_sk_text.ENGLISH_STOP_WORDS)

    unigram_counts: Counter[str] = Counter()
    bigram_counts: Counter[str] = Counter()
    # ``term -> Counter(co-occurring term)``
    cooc_mat: dict[str, Counter[str]] = defaultdict(Counter)
    tag_counts: Counter[str] = Counter()
    tag_sentiment: dict[str, Counter[str]] = defaultdict(Counter)

    for art in articles:
        meta = art["metadata"]
        text_parts = [
            meta.get("title", ""),
            meta.get("summary", ""),
        ]
        text = " ".join([t for t in text_parts if t])
        # Basic tokenisation – alphanum words, lowercase, length >=2
        tokens = [
            t.lower()
            for t in re.findall(r"\b\w{3,}\b", text)
            if t.lower() not in STOP_WORDS
        ]
        if not tokens:
            continue

        # Update unigram and bigram counts
        unigram_counts.update(tokens)
        bigram_counts.update(
            " ".join(pair) for pair in zip(tokens, tokens[1:])
        )

        # Co-occurrence: consider unique terms per article to avoid huge counts
        uniq = set(tokens)
        for t1 in uniq:
            for t2 in uniq:
                if t1 == t2:
                    continue
                cooc_mat[t1][t2] += 1

        tags_raw = meta.get("tags")
        if tags_raw:
            tags = (tags_raw if isinstance(tags_raw, list)
                    else [t.strip() for t in tags_raw.split(",")])
            tag_counts.update(tags)
            for tg in tags:
                tag_sentiment[tg][meta.get("sentiment", "unknown")] += 1

    # Select most common n-grams
    top_unigrams = unigram_counts.most_common(20)
    top_bigrams = bigram_counts.most_common(20)
    ngrams = [
        {"text": w, "count": c} for w, c in (top_unigrams + top_bigrams)
    ]

    # Restrict co-occurrence output: keep 10 seed terms &
    # their top 5 neighbours
    top_terms = [w for w, _ in unigram_counts.most_common(10)]
    cooccurrence: Dict[str, Dict[str, int]] = {}
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

    return {
        "ngrams": ngrams,
        "cooccurrence": cooccurrence,
        "tag_stats": tag_stats,
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
async def clean_collection():
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
    top_k: int = Query(20, ge=1, le=200),
    topic: Optional[str] = None,
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    news_source: Optional[str] = None,
):
    """Return the *top_k* most isolated articles within the filter scope.

    Isolation Forest runs on the raw vectors (high-dim).  The *score*
    returned is the anomaly score.
    Higher values mean the point is more anomalous.
    """

    where: Dict[str, Any] | None = None
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

    vecs, metas, ids = _fetch_vectors(limit=5000, where=where)
    if vecs.size == 0:
        return []

    from sklearn.ensemble import IsolationForest  # type: ignore
    import numpy as np  # lazy import for typing

    iso = IsolationForest(contamination=0.02, random_state=42)
    # decision_function gives an anomaly score.
    # Higher values mean the point is more anomalous.
    anomaly_score = -iso.fit(vecs).decision_function(vecs)

    idx_sorted = np.argsort(anomaly_score)[::-1][:top_k]

    return [
        {
            "id": ids[i],
            "score": float(anomaly_score[i]),
            "metadata": metas[i],
        }
        for i in idx_sorted
    ]

# ------------------------------------------------------------------
# Auspex summarisation endpoint – summarise arbitrary article IDs
# ------------------------------------------------------------------


class _SummaryRequest(BaseModel):
    """Payload for /vector-summary."""

    ids: list[str] = Field(..., description="IDs")
    model: str | None = Field(None, description="LLM name (optional)")


@router.post("/vector-summary")
async def vector_summary(req: _SummaryRequest):
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
        lines.append(
            f"{idx}. {title} "
            f"(category: {cat}, sentiment: {sentiment})\n"
            f"{summary_short}\n"
        )

    joined = "\n".join(lines)

    # --------------------------------------------------------------------------------
    # 3. Query Auspex (LLM) – pick requested or default model
    # --------------------------------------------------------------------------------
    from app.ai_models import (
        get_ai_model,
        ai_get_available_models,  # type: ignore
    )

    # Use provided model or default to gpt-4o-mini (lightweight)
    model_name = req.model or "gpt-4o-mini"

    # ai_get_available_models() returns a list of dicts → extract the names
    available_models = ai_get_available_models()
    available_names = [m["name"] for m in available_models]

    if model_name not in available_names:
        # Fallback to the first configured model name (if any)
        model_name = available_names[0] if available_names else "gpt-3.5-turbo"

    model = get_ai_model(model_name)
    if model is None:
        raise HTTPException(status_code=500, detail="AI model not configured")

    # Long but readable prompt – ignore line-length linting  # noqa: E501
    system_msg = (
        "You are Auspex – an expert analyst. "
        "The user supplied a set of news articles in bullet-point form. "
        "Provide a concise markdown summary covering key insights, recurring "
        "themes, outliers and trends. Start with a one-sentence summary. "
        "Then use bullet points and short sections (Key Themes, Sentiment, "
        "Notable Articles). Limit to about 300 words."
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"Here are the articles:\n\n{joined}"},
    ]

    try:
        summary = model.generate_response(messages)
    except Exception as exc:
        logging.getLogger(__name__).error(
            "LLM summary failed: %s", exc,
        )
        raise HTTPException(status_code=500, detail="LLM error")

    return {"response": summary} 