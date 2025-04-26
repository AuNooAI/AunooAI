from typing import Optional, Dict, Any

from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse

from app.vector_store import search_articles, upsert_article
from app.database import Database, get_database_instance

router = APIRouter(prefix="/api", tags=["vector-search"])


@router.get("/vector-search")
def vector_search_endpoint(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(10, ge=1, le=100),
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
    timeline: dict[str, int] = Counter()

    for hit in results:
        meta = hit.get("metadata", {})
        # Facets for quick filters
        for field in ("topic", "category", "news_source"):
            val = meta.get(field)
            if val:
                facets[field][str(val)] += 1

        # Simple day-level histogram by publication_date (YYYY-MM-DD)
        pub_date = meta.get("publication_date")
        if pub_date:
            try:
                # Accept either date or datetime strings.
                date_obj = datetime.fromisoformat(str(pub_date))
                bucket = date_obj.date().isoformat()
                timeline[bucket] += 1
            except Exception:  # noqa: BLE001 – skip unparsable dates
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