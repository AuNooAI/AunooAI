"""The one brand-inclusion rule every Brand Watcher reader uses.

docs/BRAND_RELEVANCE_SPEC.md, "Every consumer must use the same inclusion
rules". A row that carries a scoped brand label for this brand counts as
earned coverage only when the label is subject or notable and the source is
independent of this brand. Any other label, an unknown label or a deferred
row is not earned. A row with no label keeps the reader's legacy condition,
so nothing changes until labels exist and nothing is rescored.

Every function degrades to the legacy SQL when the br_001 columns are absent,
so code copied to a site ahead of its migration cannot break a query.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EARNED = ("subject", "notable")
_COLUMN_TTL_NEG = 300.0
_cols: Dict[str, Any] = {"ok": None, "at": 0.0}


def labels_available(conn=None) -> bool:
    """True when keyword_article_matches has the brand decision columns.
    A positive answer is cached for the process; a negative one for five
    minutes, so a migration applied while the site runs is picked up."""
    if _cols["ok"] is True:
        return True
    if _cols["ok"] is False and time.monotonic() - _cols["at"] < _COLUMN_TTL_NEG:
        return False
    own = conn is None
    try:
        from sqlalchemy import text
        if own:
            from app.database import get_database_instance
            conn = get_database_instance()._temp_get_connection()
        # Distinct columns in the schemas this connection actually reads: a
        # second copy of the table elsewhere (a backup schema) must not count.
        n = conn.execute(text("""
            SELECT count(DISTINCT column_name) FROM information_schema.columns
             WHERE table_name = 'keyword_article_matches'
               AND table_schema = ANY(current_schemas(false))
               AND column_name IN ('brand_relation', 'source_relation')
        """)).scalar()
        _cols.update(ok=(n == 2), at=time.monotonic())
    except Exception as e:  # noqa: BLE001
        logger.debug("brand_coverage: column check failed: %s", e)
        _cols.update(ok=False, at=time.monotonic())
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    return bool(_cols["ok"])


def labels_active(conn=None) -> bool:
    """Readers honour labels only with the site flag on and the columns
    present. Flag off restores the previous reading exactly; stored labels
    stay where they are (rollback, docs/BRAND_RELEVANCE_SPEC.md)."""
    from app.services.brand_decision import enabled
    return enabled() and labels_available(conn)


def brand_topics(display_name: str) -> List[str]:
    """Both topic naming forms a brand's groups use."""
    n = (display_name or "").strip()
    return [f"Brand Monitoring {n}", f"{n} - Brand Watch"] if n else []


# --- fragments keyed by a topics parameter (classification pass) -------------

def _scoped(alias: str, topics_param: str, cond: str) -> str:
    return (f"EXISTS (SELECT 1 FROM keyword_article_matches bcm"
            f" JOIN keyword_groups bcg ON bcg.id = bcm.group_id"
            f" WHERE bcm.article_uri = {alias}.uri AND bcg.topic = ANY(:{topics_param}) AND {cond})")


def labelled_earned_sql(alias: str = "a", topics_param: str = "bc_topics") -> str:
    """The article carries an earned label for this brand."""
    if not labels_active():
        return "FALSE"
    return _scoped(alias, topics_param,
                   "bcm.brand_relation IN ('subject','notable') AND bcm.source_relation = 'independent'")


def label_veto_sql(alias: str = "a", topics_param: str = "bc_topics") -> str:
    """No label for this brand says the article is not earned."""
    if not labels_active():
        return "TRUE"
    return "NOT " + _scoped(alias, topics_param,
                            "bcm.brand_relation IS NOT NULL AND NOT (bcm.brand_relation IN ('subject','notable')"
                            " AND bcm.source_relation = 'independent')")


def labels_for(conn, uris: List[str], topics: List[str]) -> Dict[str, Dict[str, Any]]:
    """{uri: {brand_relation, source_relation, relevance_status}} for labelled
    rows of these articles under these topics."""
    if not uris or not topics or not labels_active(conn):
        return {}
    from sqlalchemy import text
    rows = conn.execute(text("""
        SELECT m.article_uri, m.brand_relation, m.source_relation, m.relevance_status
          FROM keyword_article_matches m JOIN keyword_groups g ON g.id = m.group_id
         WHERE m.article_uri = ANY(:u) AND g.topic = ANY(:t) AND m.brand_relation IS NOT NULL
    """), {"u": list(uris), "t": list(topics)}).mappings().all()
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        prev = out.get(r["article_uri"])
        # Two groups of one brand disagreeing: the non-earned reading wins.
        if prev is None or (prev["brand_relation"] in EARNED and r["brand_relation"] not in EARNED):
            out[r["article_uri"]] = dict(r)
    return out


# --- fragments keyed by the classification row's brand (readers) ------------

def _bac_scoped(alias: str, bac: str, cond: str) -> str:
    return (f"EXISTS (SELECT 1 FROM keyword_article_matches bcm"
            f" JOIN keyword_groups bcg ON bcg.id = bcm.group_id"
            f" JOIN bw_brands bcb ON bcb.id = {bac}.brand_id"
            f" WHERE bcm.article_uri = {alias}.uri"
            f" AND bcg.topic IN ('Brand Monitoring ' || bcb.display_name, bcb.display_name || ' - Brand Watch')"
            f" AND {cond})")


def earned_news_scoped_sql(alias: str = "a", bac: str = "bac") -> str:
    """earned_news_sql with ownership decided per brand where a label exists.

    Legacy rule: analysed, not social, and not tagged as owned publishing.
    Scoped override: a page tagged as owned (by its own company) is still
    earned coverage of this brand when this brand's label says independent;
    a page this brand's label calls owned is never earned for it.
    """
    from app.services.social_sources import earned_news_sql, owned_src_sql, social_src_sql
    if not labels_active():
        return earned_news_sql(alias)
    indep = _bac_scoped(alias, bac, "bcm.source_relation = 'independent' AND bcm.brand_relation IN ('subject','notable')")
    owned = _bac_scoped(alias, bac, "bcm.source_relation = 'owned'")
    return (f"{alias}.analyzed = true AND NOT {social_src_sql(alias + '.news_source')}"
            f" AND (NOT {owned_src_sql(alias + '.bias_source')} OR {indep})"
            f" AND NOT {owned}")


def alert_earned_sql(alias: str = "a", bac: str = "bac") -> str:
    """The shared earned rule for the news sentiment alerts and digests,
    which today apply no social or owned filter at all. Measured 2026-10-06
    over 30 days: on sunstar 227 alert-pool rows, of which 45 are earned
    under the legacy rule; on abm 313 and 107. Applying it changes alert
    volume whether or not labels exist, so it follows the per-site flag:
    flag off keeps today's behaviour exactly (rollback)."""
    from app.services.brand_decision import enabled
    if not enabled():
        return "TRUE"
    return earned_news_scoped_sql(alias, bac)


class LazySql:
    """A SQL fragment decided at query time, for module constants used in
    f-strings (``f"... {_EARNED_NEWS} ..."``). Formatting calls the builder,
    so the column check runs against the live database, not at import."""

    def __init__(self, builder, *args):
        self._builder, self._args = builder, args

    def __str__(self) -> str:
        return self._builder(*self._args)

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)


# --- the separate sector and owned views -------------------------------------

def coverage_split(conn, display_name: str, days: int = 30, relation: Optional[str] = None,
                   limit: int = 50) -> Dict[str, Any]:
    """Counts per coverage bucket for one brand, and the rows of one bucket.

    Buckets: earned (independent subject/notable), owned (the brand's own
    relevant content), fan (listed fan and recipe sites), sector, passing, other, deferred, unavailable. One
    article counts once per brand. Rows decided before labels existed are
    reported as 'unlabelled', not guessed.
    """
    from sqlalchemy import text
    topics = brand_topics(display_name)
    if not labels_available(conn):
        return {"available": False, "reason": "brand labels are not installed on this site", "counts": {}, "rows": []}
    bucket = """
        CASE
          WHEN m.relevance_status = 'relevance_check_failed' AND m.brand_relation IS NULL THEN 'unavailable'
          WHEN m.relevance_status = 'deferred' THEN 'deferred'
          WHEN m.brand_relation IS NULL THEN 'unlabelled'
          WHEN m.brand_relation NOT IN ('subject','notable','sector','passing','other') THEN 'invalid'
          WHEN m.source_relation = 'owned' AND m.brand_relation IN ('subject','notable','sector') THEN 'owned'
          WHEN m.decision_evidence ? 'fan_content' THEN 'fan'
          WHEN m.brand_relation IN ('subject','notable') AND m.source_relation = 'independent' THEN 'earned'
          ELSE m.brand_relation
        END
    """
    # Market Monitor vendor decisions (docs/BRAND_RELEVANCE_MARKET_VENDORS.md)
    # live in their own table, one row per article and vendor; mapped to the
    # match-row shape so one bucket rule serves both.
    market_rows = ""
    if conn.execute(text("SELECT to_regclass('brand_article_decisions') IS NOT NULL")).scalar():
        market_rows = """
          UNION ALL
          SELECT d.article_uri, d.brand_relation, d.source_relation,
                 CASE d.outcome WHEN 'unavailable' THEN 'relevance_check_failed'
                                WHEN 'deferred' THEN 'deferred' END,
                 d.decision_evidence, d.decided_at
            FROM brand_article_decisions d
           WHERE d.brand_id IN (SELECT id FROM bw_brands WHERE display_name = :n)
        """
    base = f"""
        SELECT DISTINCT ON (m.article_uri) m.article_uri AS uri, {bucket} AS bucket,
               m.brand_relation, m.source_relation, m.relevance_status, m.decision_evidence,
               a.title, a.news_source, a.publication_date, a.submission_date
          FROM (
          SELECT km.article_uri, km.brand_relation, km.source_relation, km.relevance_status,
                 km.decision_evidence, km.scored_at
            FROM keyword_article_matches km
            JOIN keyword_groups g ON g.id = km.group_id
           WHERE g.topic = ANY(:t)
          {market_rows}
          ) m (article_uri, brand_relation, source_relation, relevance_status, decision_evidence, scored_at)
          JOIN articles a ON a.uri = m.article_uri
         WHERE (a.social_meta IS NULL OR a.social_meta::text = 'null')
           AND COALESCE(m.scored_at, NOW()) >= NOW() - make_interval(days => :d)
         ORDER BY m.article_uri, m.scored_at DESC NULLS LAST
    """
    params = {"t": topics, "d": int(days), "n": display_name}
    counts = {r["bucket"]: int(r["n"]) for r in conn.execute(text(
        f"SELECT bucket, count(*) AS n FROM ({base}) x GROUP BY bucket"), params).mappings()}
    rows: List[Dict[str, Any]] = []
    if relation:
        for r in conn.execute(text(
                f"SELECT * FROM ({base}) x WHERE bucket = :b ORDER BY submission_date DESC NULLS LAST LIMIT :l"),
                dict(params, b=relation, l=int(limit))).mappings():
            ev = r["decision_evidence"] or {}
            if isinstance(ev, str):
                import json
                try:
                    ev = json.loads(ev)
                except ValueError:
                    ev = {}
            rows.append({
                "uri": r["uri"], "title": r["title"], "source": r["news_source"],
                "published": r["publication_date"], "bucket": r["bucket"],
                "relation": r["brand_relation"], "source_relation": r["source_relation"],
                "limited_evidence": (ev or {}).get("quality") == "title_only",
                "reason": (ev or {}).get("reason"), "matched": (ev or {}).get("alias"),
                "evidence_field": (ev or {}).get("field"), "provenance": (ev or {}).get("provenance"),
            })
    return {"available": True, "brand": display_name, "days": int(days), "counts": counts, "rows": rows,
            "note": ("Each article counts once for this brand. 'earned' is independent coverage where the brand "
                     "is the subject or plays a real part; 'owned' is the brand's own content; 'sector' names the "
                     "market without the brand; 'unlabelled' rows were decided before labels existed.")}
