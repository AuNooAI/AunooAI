"""Mark a company's own web publishing so it is not counted as coverage.

A Brand Watcher topic collects everything that names the brand, and that
includes the brand's own blog and press pages. On oviva, all 25 articles the
dashboard counted as Oviva "news" over 90 days were oviva.com recipe and
testimonial posts, so news sentiment and share of voice measured Oviva's
copywriters. This module stamps such rows ``bias_source = 'owned:<domain>'``
using the domain identifiers Entity Intelligence keeps per brand
(``bw_vendor_identifiers``, kind ``domain``), and the metric queries leave
owned rows out through ``social_sources.earned_news_sql``. The rows stay in
the article lists, flagged as owned, the way the market map shows a vendor's
own posts.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

_HOST_SQL = "LOWER(substring(uri from '://([^/@]+)'))"


def brand_domains(conn, brand_id: Optional[int] = None) -> Dict[int, List[str]]:
    """{brand_id: [domain, ...]} from the entity identifiers; empty on sites without the table."""
    try:
        where = "kind = 'domain' AND (valid_to IS NULL OR valid_to > NOW())"
        params = {}
        if brand_id is not None:
            where += " AND brand_id = :bid"
            params["bid"] = brand_id
        rows = conn.execute(text(
            f"SELECT brand_id, LOWER(normalized_value) FROM bw_vendor_identifiers WHERE {where}"
        ), params).fetchall()
    except Exception as e:  # table missing on older trees
        logger.debug("bw_owned: no brand domains available: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return {}
    out: Dict[int, List[str]] = {}
    for bid, dom in rows:
        dom = (dom or "").strip().lstrip("*.").removeprefix("www.")
        if dom:
            out.setdefault(int(bid), []).append(dom)
    return out


def tag_owned_articles(conn, brand_id: Optional[int] = None, uris: Optional[List[str]] = None,
                       commit: bool = True) -> int:
    """Stamp rows on a brand's own domains as ``owned:<domain>``.

    Only rows with no ``bias_source`` yet are touched, so the official-source
    poller's ``official:`` and the market's ``vendor:`` marks are kept.
    Returns the number of rows changed.
    """
    domains = brand_domains(conn, brand_id)
    if not domains:
        return 0
    doms = sorted({d for ds in domains.values() for d in ds})
    # One pass over the untagged rows for every domain at once. Each row's host
    # is split into itself and its parent domains (news.acme.com -> acme.com),
    # so an equality join covers the bare, www. and sub-domain cases. The old
    # loop ran one full-table scan per domain: 143 domains took up to 260s on
    # bugfixing, and it held the event loop the whole time.
    uri_filter = " AND uri = ANY(:uris)" if uris else ""
    sql = f"""
        WITH h AS (
            SELECT uri, string_to_array({_HOST_SQL}, '.') AS parts
            FROM articles WHERE bias_source IS NULL{uri_filter}
        ), m AS (
            SELECT DISTINCT ON (h.uri) h.uri, d.dom
            FROM h
            CROSS JOIN LATERAL generate_series(1, cardinality(h.parts)) AS i
            JOIN unnest(CAST(:doms AS text[])) AS d(dom)
              ON d.dom = array_to_string(h.parts[i:], '.')
            ORDER BY h.uri, length(d.dom) DESC
        )
        UPDATE articles a SET bias_source = 'owned:' || m.dom
        FROM m WHERE a.uri = m.uri AND a.bias_source IS NULL
    """
    params = {"doms": doms}
    if uris:
        params["uris"] = list(uris)
    try:
        changed = conn.execute(text(sql), params).rowcount or 0
    except Exception as e:
        logger.warning("bw_owned: tagging failed: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    if commit and changed:
        conn.commit()
    if changed:
        logger.info("bw_owned: %d article(s) marked as the company's own publishing", changed)
    return changed
