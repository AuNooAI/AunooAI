"""Brand Watcher story deduplication (#1).

Clusters a brand's near-duplicate / syndicated articles into a single "story"
so analytics count distinct stories, not raw republications. Ported from the
saasmvp ``app/features/brand_monitoring/service._assign_story_groups`` and
adapted to the monolith:

- keyed on ``article_uri`` (Text) rather than an integer ``article_id``;
- reads the pgvector ``articles.embedding`` column directly (no separate
  ``article_embeddings`` table);
- synchronous, operating on a ``db._temp_get_connection()`` connection so it can
  be called inline from the classification background task.

``story_group_id`` is the ``article_uri`` of the canonical (earliest) article in
the cluster. Articles without an embedding are simply never written here — at
read time ``COALESCE(s.story_group_id, bac.article_uri)`` makes them their own
single-article story.

NOTE ON THRESHOLD: the monolith embeds with OpenAI ``text-embedding-3-small``
(1536d), a different space than saasmvp's 768d DeBERTa, so ``DEFAULT_STORY_DISTANCE``
is set higher (0.10 → cosine sim >= 0.90) and is meant to be calibrated per
deployment via ``bw_brands.config.story_distance``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

DEFAULT_STORY_DISTANCE = 0.008     # cosine distance; sim_threshold = 1 - distance
# Calibration note (2026-06-23, measured on clean local DeBERTa 768d embeddings):
# DeBERTa-base is strongly anisotropic — within a single brand, *different*-story
# article pairs already sit very high (Wiley: p50=0.882, p90=0.941, p99=0.973,
# p99.9=0.990). True syndicated dupes only separate out at >=0.992 (verbatim /
# near-verbatim wire copies; e.g. "(WLY) to Release Quarterly" vs "(WLYB) to
# Release Quarterly"). So sim_threshold=0.992 (distance 0.008) — an order of
# magnitude tighter than saasmvp's 0.08, which would merge >10% of unrelated
# pairs on this space. Bias is deliberately conservative: a missed dupe just
# double-counts a story (mild); a false merge collapses distinct stories
# (corrupts analytics). Tune per brand via bw_brands.config.story_distance.
DEFAULT_STORY_WINDOW_DAYS = 3.0
# Bound per-call work so the first pass over a backlog never blocks a run.
MAX_ARTICLES_PER_CALL = 4000


def _coerce_vector(raw: Any) -> Optional[list]:
    """pgvector value -> list[float]. Handles list/tuple and the '[..]' string."""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        return list(raw)
    if isinstance(raw, str):
        s = raw.strip().lstrip('[').rstrip(']')
        if not s:
            return None
        try:
            return [float(x) for x in s.split(',')]
        except ValueError:
            return None
    return None


def _pub_ts(pub: Any) -> Optional[float]:
    """publication_date (Text ISO or datetime) -> epoch seconds, or None."""
    if pub is None:
        return None
    if isinstance(pub, datetime):
        return pub.timestamp()
    s = str(pub).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(fmt) + 2], fmt).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s[:19]).timestamp()
    except ValueError:
        return None


def assign_story_groups(conn, brand_id: int, cfg: Optional[dict] = None) -> int:
    """Assign story groups for a brand's not-yet-clustered articles.

    Returns the number of articles newly assigned. Caller owns the transaction
    (we ``conn.commit()`` at the end). Safe to call repeatedly — already-assigned
    articles are skipped via the ``NOT EXISTS`` guard + ``ON CONFLICT DO NOTHING``.
    """
    import numpy as np

    cfg = cfg or {}
    distance = float(cfg.get("story_distance", DEFAULT_STORY_DISTANCE))
    window_days = float(cfg.get("story_window_days", DEFAULT_STORY_WINDOW_DAYS))
    sim_threshold = 1.0 - distance
    window_secs = window_days * 86400.0

    def _norm(vec):
        arr = np.asarray(vec, dtype=np.float32)
        n = np.linalg.norm(arr)
        return arr / n if n else arr

    # Unassigned, embedding-bearing articles for this brand (one row per uri).
    new_rows = conn.execute(text("""
        SELECT DISTINCT a.uri, a.publication_date, a.embedding
        FROM bw_article_categories bac
        JOIN articles a ON a.uri = bac.article_uri
        WHERE bac.brand_id = :bid
          AND a.embedding IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM bw_article_stories s
              WHERE s.brand_id = :bid AND s.article_uri = bac.article_uri
          )
        ORDER BY a.publication_date DESC
        LIMIT :cap
    """), {"bid": brand_id, "cap": MAX_ARTICLES_PER_CALL}).fetchall()

    if not new_rows:
        return 0

    with_vec: list[tuple[str, Optional[float], Any]] = []
    for uri, pub, emb in new_rows:
        v = _coerce_vector(emb)
        if v is None:
            continue
        with_vec.append((uri, _pub_ts(pub), _norm(v)))

    if not with_vec:
        return 0

    # Existing cluster representatives for this brand within the horizon.
    horizon = (datetime.now(timezone.utc) - timedelta(days=window_days + 1)).strftime('%Y-%m-%d')
    rep_rows = conn.execute(text("""
        SELECT s.story_group_id, a.publication_date, a.embedding
        FROM bw_article_stories s
        JOIN articles a ON a.uri = s.story_group_id
        WHERE s.brand_id = :bid AND s.article_uri = s.story_group_id
          AND a.embedding IS NOT NULL
          AND a.publication_date >= :horizon
    """), {"bid": brand_id, "horizon": horizon}).fetchall()

    rep_gids: list[str] = []
    rep_ts: list[Optional[float]] = []
    rep_vecs: list[Any] = []
    for gid, pub, emb in rep_rows:
        v = _coerce_vector(emb)
        if v is None:
            continue
        rep_gids.append(gid)
        rep_ts.append(_pub_ts(pub))
        rep_vecs.append(_norm(v))

    # Process oldest-first so the earliest article becomes the canonical rep.
    with_vec.sort(key=lambda t: (t[1] is None, t[1] or 0.0))
    rep_matrix = np.asarray(rep_vecs, dtype=np.float32) if rep_vecs else None

    rows: list[dict] = []
    for uri, ts, v in with_vec:
        gid = uri  # default: opens its own cluster
        if rep_matrix is not None and len(rep_gids):
            sims = rep_matrix @ v
            if ts is not None:
                for i, rts in enumerate(rep_ts):
                    if rts is not None and abs(ts - rts) > window_secs:
                        sims[i] = -1.0
            best_i = int(np.argmax(sims))
            if float(sims[best_i]) >= sim_threshold:
                gid = rep_gids[best_i]
        if gid == uri:
            # New representative — later articles in this batch can join it.
            rep_gids.append(uri)
            rep_ts.append(ts)
            rep_vecs.append(v)
            rep_matrix = np.asarray(rep_vecs, dtype=np.float32)
        rows.append({"bid": brand_id, "uri": uri, "gid": gid})

    if rows:
        conn.execute(text("""
            INSERT INTO bw_article_stories (brand_id, article_uri, story_group_id)
            VALUES (:bid, :uri, :gid)
            ON CONFLICT (brand_id, article_uri) DO NOTHING
        """), rows)
        conn.commit()

    logger.info("BW story dedup: brand %s assigned %d articles (%d clusters seen)",
                brand_id, len(rows), len(rep_gids))
    return len(rows)
