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
    changed = 0
    for bid, doms in domains.items():
        for dom in doms:
            sql = (f"UPDATE articles SET bias_source = :tag WHERE bias_source IS NULL"
                   f" AND ({_HOST_SQL} = :dom OR {_HOST_SQL} = :www OR {_HOST_SQL} LIKE :sub)")
            params = {"tag": f"owned:{dom}", "dom": dom, "www": f"www.{dom}", "sub": f"%.{dom}"}
            if uris:
                sql += " AND uri = ANY(:uris)"
                params["uris"] = list(uris)
            try:
                changed += conn.execute(text(sql), params).rowcount or 0
            except Exception as e:
                logger.warning("bw_owned: tagging %s failed: %s", dom, e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                return changed
    if commit and changed:
        conn.commit()
    if changed:
        logger.info("bw_owned: %d article(s) marked as the company's own publishing", changed)
    return changed
