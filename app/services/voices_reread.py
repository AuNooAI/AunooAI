"""Re-read the author role on past posts after the site's personas change.

Started from the persona settings page. Reads roles only, never relevance: a
relevance re-score on wbm (25 Sep) dropped real ISBN-bot book listings because
they do not name the brand. Uses the site's role reader (Jev where
VOICES_ROLE_MODEL=jev, else the social evaluation model), in batches that
commit as they go, so a site that closes connections idle in a transaction
(wileytest: one minute) does not lose the work.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, Dict, List

from sqlalchemy import text

logger = logging.getLogger(__name__)

DAYS = 180
BATCH = 150
# Rough cost per post, for the estimate on the page.
USD_PER_POST = {"jev": 0.00003, "model": 0.001}

_job: Dict[str, Any] = {"state": "idle"}


def _jev():
    """The Jev role module, or None on a site that does not have it (wileytest)."""
    try:
        from app.services import author_role_jev
        return author_role_jev
    except ImportError:
        return None


def candidates(conn, days: int = DAYS) -> List[Dict[str, Any]]:
    """On-brand social posts in the window, from the topic read and, where the
    site has it, the per-mention read. Same selection as the backfill script."""
    from app.services.social_eval_service import SOCIAL_SOURCES
    src = " OR ".join(f"LOWER(a.news_source) LIKE :s{i}" for i in range(len(SOCIAL_SOURCES)))
    params: Dict[str, Any] = {"cutoff": str(days)}
    for i, s in enumerate(SOCIAL_SOURCES):
        params[f"s{i}"] = f"%{s}%"
    rows = conn.execute(text(f"""
        SELECT a.uri, a.title, a.summary, COALESCE(a.social_meta->>'author', ''), a.topic
          FROM articles a
         WHERE ({src}) AND a.news_source <> 'Glassdoor'
           AND a.topic_alignment_score >= 0.4 AND a.topic LIKE 'Brand Monitoring %'
           AND a.publication_date >= to_char(NOW() - CAST(:cutoff || ' days' AS INTERVAL), 'YYYY-MM-DD')
    """), params).fetchall()
    found = {r[0]: {"uri": r[0], "title": r[1], "summary": r[2], "author": r[3], "topic": r[4]} for r in rows}
    if conn.execute(text("SELECT to_regclass('bw_entity_mentions') IS NOT NULL")).scalar():
        mrows = conn.execute(text("""
            SELECT a.uri, a.title, a.summary, COALESCE(a.social_meta->>'author', ''),
                   'Brand Monitoring ' || b.display_name
              FROM bw_entity_mentions m
              JOIN articles a ON a.uri = m.article_uri
              JOIN bw_brands b ON b.id = m.brand_id
             WHERE m.channel IN ('public_social', 'community')
               AND m.status <> 'false_positive' AND m.relevance >= 0.4
               AND a.publication_date >= to_char(NOW() - CAST(:cutoff || ' days' AS INTERVAL), 'YYYY-MM-DD')
        """), {"cutoff": str(days)}).fetchall()
        for r in mrows:
            found.setdefault(r[0], {"uri": r[0], "title": r[1], "summary": r[2], "author": r[3], "topic": r[4]})
    return list(found.values())


def estimate() -> Dict[str, Any]:
    from app.database import get_database_instance
    from app.services.social_eval_service import SocialEvalService
    conn = get_database_instance()._temp_get_connection()
    try:
        n = len(candidates(conn))
    finally:
        conn.close()
    jev = _jev()
    reader = "jev" if jev is not None and jev.enabled() else "model"
    return {"posts": n, "days": DAYS,
            "reader": "Jev" if reader == "jev" else SocialEvalService().model_name,
            "usd": round(n * USD_PER_POST[reader], 2)}


def status() -> Dict[str, Any]:
    return dict(_job)


async def run(started_by: str) -> None:
    """Re-read every candidate's role. One run at a time per process."""
    from app.database import get_database_instance
    from app.services.social_eval_service import SocialEvalService, _brand_context_for_topic
    jev = _jev()
    db = get_database_instance()
    conn = db._temp_get_connection()
    _job.update(state="running", started_by=started_by, started_at=time.time(),
                done=0, total=0, written=0, error=None)
    try:
        posts = await asyncio.to_thread(candidates, conn)
        conn.commit()
        _job["total"] = len(posts)
        svc = SocialEvalService()
        # Older trees' classify_roles takes no competitors argument.
        takes_rivals = "competitors" in inspect.signature(svc.classify_roles).parameters
        for topic in sorted({p["topic"] for p in posts}):
            batch = [p for p in posts if p["topic"] == topic]
            brand = topic.replace("Brand Monitoring ", "", 1)
            ctx = _brand_context_for_topic(db, topic)
            rivals = jev.rival_names(db, brand) if jev is not None else []
            conn.commit()
            try:
                db.facade.connection.commit()
            except Exception:  # noqa: BLE001 - nothing open on that connection
                pass
            for i in range(0, len(batch), BATCH):
                part = batch[i:i + BATCH]
                kwargs = {"brand_context": ctx["description"]}
                if takes_rivals:
                    kwargs["competitors"] = rivals
                got = await svc.classify_roles(part, brand, **kwargs)
                for g in got:
                    conn.execute(text("UPDATE articles SET author_role = :r, author_role_reason = :w WHERE uri = :u"),
                                 {"r": g["author_role"], "w": g.get("author_role_reason"), "u": g["uri"]})
                conn.commit()
                _job["done"] += len(part)
                _job["written"] += len(got)
        _job.update(state="done", finished_at=time.time())
        try:
            from app.routes.brand_watcher_routes import bw_cache_clear
            bw_cache_clear()
        except Exception:  # noqa: BLE001 - the cache ages out anyway
            pass
    except Exception as e:  # noqa: BLE001
        logger.exception("voices re-read failed")
        _job.update(state="failed", error=str(e)[:300], finished_at=time.time())
    finally:
        conn.close()
