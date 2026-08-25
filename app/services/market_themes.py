"""What the matched corpus is actually talking about, grouped by embedding.

``market_corpus.cluster()`` finds near-duplicates — the same story reported
by five outlets. This finds something coarser: which broad subjects the
period's coverage falls into, whether or not any two articles say the same
thing. K-means over the stored embedding does the grouping; a model narrates
what each group has in common afterwards.

Two stages, same split as market_briefing.py: the clusters and the sample
titles inside them are computed facts, arithmetic and reproducible (a fixed
random_state, so the same corpus produces the same groups). The model only
names and describes a group from the titles it is shown — it cannot add a
company or an event that is not in the sample, because a title it invented
would have no cluster to belong to.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Below this, k-means has too little to work with — a handful of articles is
# a list, not a set of themes.
MIN_ARTICLES_FOR_THEMES = 8

# Matches market_briefing's default: cheap enough to run per-narration
# without a sign-off, per the project's cost-conscious model guidance.
DEFAULT_MODEL = "gpt-5.4-mini"


def _k_for(n: int) -> int:
    """Cluster count that keeps roughly 15-25 items per theme.

    Below ~35 articles this always returns 2 — k-means on three articles per
    cluster does not find a theme, it just draws lines between points.
    """
    return max(2, min(8, n // 18))


def _embeddings(conn, uris: List[str]) -> Dict[str, List[float]]:
    """This connection has no pgvector type adapter registered, so the driver
    hands back the column's text form (``"[0.1,0.2,...]"``) rather than a
    list — the same thing ``vector_store_pgvector.py`` works around with
    ``str(embedding)`` before re-casting it in SQL. json.loads parses it
    straight to floats since that text form is valid JSON."""
    import json

    if not uris:
        return {}
    rows = conn.execute(text("""
        SELECT uri, embedding FROM articles
        WHERE uri = ANY(:uris) AND embedding IS NOT NULL
    """), {"uris": uris}).fetchall()
    out: Dict[str, List[float]] = {}
    for uri, emb in rows:
        if emb is None:
            continue
        out[uri] = json.loads(emb) if isinstance(emb, str) else list(emb)
    return out


def cluster(conn, market_id: int, *, scope: str = "all", days: int = 30,
           limit: int = 400) -> Dict[str, Any]:
    """K-means over embeddings for the market's matched corpus.

    ``scope='vendor'`` restricts to vendor-originated posts (blog and social,
    the same "review pass judged it states a fact" gate the Coverage view
    uses) — what vendors are saying about themselves, not what is said about
    them. ``scope='all'`` is the whole matched conversation.
    """
    from app.services import market_corpus as mcorp

    import numpy as np

    classes = ["vendor", "social"] if scope == "vendor" else None
    rows = mcorp.articles(conn, market_id, limit=limit, days=days,
                          classes=classes, require_signal_for_social=True)
    if not rows:
        return {"scope": scope, "n": 0, "k": 0, "clusters": []}

    embeddings = _embeddings(conn, [r["uri"] for r in rows])
    usable = [r for r in rows if r["uri"] in embeddings]
    if len(usable) < MIN_ARTICLES_FOR_THEMES:
        return {"scope": scope, "n": len(usable), "k": 0, "clusters": [],
                "reason": "too few matched articles with a stored embedding "
                         "to group into themes"}

    from sklearn.cluster import KMeans

    matrix = np.array([embeddings[r["uri"]] for r in usable])
    k = _k_for(len(usable))
    labels = KMeans(n_clusters=k, n_init=4, random_state=0).fit_predict(matrix)

    clusters: List[Dict[str, Any]] = []
    for c in range(k):
        members = [usable[i] for i in range(len(usable)) if labels[i] == c]
        if not members:
            continue
        members.sort(key=lambda r: r.get("published") or "", reverse=True)
        vendor_counts: Dict[str, int] = {}
        for m in members:
            for v in m.get("vendors", []):
                vendor_counts[v["vendor"]] = vendor_counts.get(v["vendor"], 0) + 1
        top_vendors = sorted(vendor_counts.items(), key=lambda x: -x[1])[:5]
        clusters.append({
            "id": c, "size": len(members),
            "sample": [{"uri": m["uri"], "title": m["title"],
                        "source": m.get("news_source"),
                        "published": m.get("published")}
                       for m in members[:8]],
            "top_vendors": [{"vendor": v, "n": n} for v, n in top_vendors],
            "date_range": [members[-1].get("published"), members[0].get("published")],
        })
    clusters.sort(key=lambda c: -c["size"])
    return {"scope": scope, "n": len(usable), "k": k, "clusters": clusters}


async def narrate(clusters_result: Dict[str, Any], market_name: str, scope: str,
                  model: Optional[str] = None) -> str:
    """Name and describe each cluster, grounded in its sample titles only."""
    from app.routes.vector_routes import _generate_report_with_retry
    from app.ai_models import LiteLLMModel
    from app.services.report_style import CLINICAL_STYLE

    clusters = clusters_result.get("clusters", [])
    if not clusters:
        return ("Not enough matched coverage with a stored embedding yet to "
                "group into themes.")

    lines: List[str] = []
    for c in clusters:
        vendors = ", ".join(v["vendor"] for v in c["top_vendors"][:3])
        lines.append(f"\nTHEME {c['id']} — {c['size']} items"
                     + (f", led by {vendors}" if vendors else "") + ":")
        for s in c["sample"]:
            lines.append(f"- {s['title']} ({s.get('source') or 'vendor post'}, "
                         f"{(s.get('published') or '')[:10]})")
    facts_block = "\n".join(lines)

    what = ("what competitors are posting about themselves"
           if scope == "vendor" else "what the market's coverage is about")

    # Deliberately no organisation persona here, unlike market_briefing.py's
    # narration. That persona addresses a reader across a full report; this
    # prompt asks for one short name and description per numbered theme, and
    # the persona derails it into unrelated commentary instead of naming
    # them — tried once, seen in the output, dropped.
    prompt = f"""These are {len(clusters)} groups of article titles from {market_name}'s
matched coverage, grouped by embedding similarity — not by hand, so no group
has a name yet. For each numbered theme, write:
1. A short name (3-6 words) for what the titles in it have in common.
2. One or two sentences on {what}, grounded only in the titles shown.

Do not invent a company, product or event that is not implied by the titles.
If a group's titles do not obviously share a theme, say so instead of forcing
one — a forced theme is worse than an admitted miscellany. Do not add any
section beyond the themes themselves — no introduction, no closing summary,
no commentary about who is reading this.

{CLINICAL_STYLE}

{facts_block}
"""
    messages = [
        {"role": "system",
         "content": "You name and describe clusters of article titles from "
                    "evidence only, never inventing a company, product or "
                    "event the titles do not support, and never writing "
                    "anything beyond the themes you were asked for."},
        {"role": "user", "content": prompt},
    ]
    content = await _generate_report_with_retry(
        LiteLLMModel.get_instance(model or DEFAULT_MODEL), messages,
        label=f"market themes {market_name} {scope}")
    return content or "The model returned nothing usable for these themes."
