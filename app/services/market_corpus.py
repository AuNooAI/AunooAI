"""Matching the existing article corpus against a market's own language.

The gap this closes: Brand Watcher classifies articles by **vendor name**. Ask
it for SOC-automation coverage and it returns articles that named Crogl or
Dropzone. An article about autonomous SOC adoption that names no vendor is
invisible to it — correctly, because it is answering "who was mentioned".

A market monitor needs the other question: which articles are *about this
category*, whoever they name. That is a match against the market's own phrases
("SOC automation", "agentic SOC", "SOAR platform"), not against a company.

Everything here reads articles that were already collected, analysed and paid
for. It calls no provider and collects nothing.

Scoring is deliberately arithmetic rather than a model call. A market's terms
are hand-written and few, the corpus is large, and an operator has to be able
to look at a match and say why it is there. A number that came out of an LLM
cannot be argued with; a list of matched phrases can.
"""

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

# A phrase in the headline is the article's subject. The same phrase in the
# summary may be an aside. Both count; they do not count the same.
TITLE_WEIGHT = 34.0
BODY_WEIGHT = 12.0

# Below this a match is one glancing mention of one phrase in a summary, which
# is not enough to call an article part of the market's coverage.
DEFAULT_MIN_SCORE = 12.0

# Guard against a scan of the whole corpus in one transaction.
DEFAULT_LIMIT = 5000


def _term_regex(term: str) -> str:
    """A word-boundary Postgres regex for one phrase.

    Spaces become ``\\s+`` so "SOC  automation" and a line break both match.
    ``\\m``/``\\M`` are Postgres's word-start and word-end assertions; without
    them "SOAR" matches inside "soaring".
    """
    words = [re.escape(w) for w in term.split() if w]
    if not words:
        return ""
    return r"\m" + r"\s+".join(words) + r"\M"


def compile_terms(terms: Sequence[str]) -> Tuple[str, List[Tuple[str, re.Pattern]]]:
    """Return ``(one Postgres alternation, [(term, python pattern)])``.

    The alternation runs in the database so the corpus is filtered there. The
    per-term Python patterns run only over rows that already matched, which is
    a few hundred rows rather than two hundred thousand.
    """
    pg_parts: List[str] = []
    py_terms: List[Tuple[str, re.Pattern]] = []
    for term in terms:
        t = (term or "").strip()
        if not t:
            continue
        rx = _term_regex(t)
        if not rx:
            continue
        pg_parts.append(f"({rx})")
        words = [re.escape(w) for w in t.split() if w]
        py_terms.append((t, re.compile(r"\b" + r"\s+".join(words) + r"\b", re.I)))
    return "|".join(pg_parts), py_terms


def score_article(title: str, summary: str,
                  py_terms: Sequence[Tuple[str, re.Pattern]]
                  ) -> Tuple[List[str], int, int, float]:
    """``(matched terms, title hits, body hits, score)`` for one article.

    Distinct phrases, not occurrences. An article that says "SOC automation"
    nine times is one phrase's worth of evidence, not nine.
    """
    t = title or ""
    s = summary or ""
    matched: List[str] = []
    title_hits = 0
    body_hits = 0
    for term, pattern in py_terms:
        in_title = bool(pattern.search(t))
        in_body = bool(pattern.search(s))
        if not (in_title or in_body):
            continue
        matched.append(term)
        if in_title:
            title_hits += 1
        else:
            body_hits += 1
    score = min(100.0, TITLE_WEIGHT * title_hits + BODY_WEIGHT * body_hits)
    return matched, title_hits, body_hits, round(score, 2)


# Phrases that describe the category without naming a vendor. These are
# *corpus-only*: they match articles already collected for other topics, and
# they never drive paid collection, so a broad one costs nothing but recall
# noise. A market overrides them with ``bw_markets.config['context_terms']``.
#
# What is deliberately absent is as important as what is here. A bare acronym
# collides: ``SOAR`` matched "Bible Sales Soar" and "Japan Bond Yields Soar",
# and ``MDR`` matched multidrug-resistant tuberculosis papers. Between them
# they accounted for 241 of 594 matches on a first pass, essentially all wrong.
# Acronyms only appear here when the string itself is unambiguous (SIEM, XDR)
# or carries a qualifier ("SOAR platform", which lives in the collection terms).
DEFAULT_CONTEXT_TERMS: List[str] = [
    "security operations center",
    "security operations",
    "SOC analyst",
    "SOC team",
    "SOC modernization",
    "AI SOC",
    "SIEM",
    "XDR",
    "threat hunting",
    "detection engineering",
    "alert triage",
    "alert fatigue",
    "tier 1 analyst",
    "managed detection and response",
    "incident response automation",
    "security automation",
    "autonomous security",
]


def context_terms(conn, market_id: int) -> List[str]:
    """The market's context phrases, from config or the default list."""
    cfg = conn.execute(text(
        "SELECT config FROM bw_markets WHERE id = :m"), {"m": market_id}).scalar()
    cfg = cfg if isinstance(cfg, dict) else {}
    terms = cfg.get("context_terms")
    if isinstance(terms, list):
        return [str(t).strip() for t in terms if str(t).strip()]
    return list(DEFAULT_CONTEXT_TERMS)


def corpus_terms(conn, market_id: int) -> List[str]:
    """Everything the corpus scan matches on.

    The market's collection terms *plus* its context terms. Collection terms
    are what we pay a provider to go and fetch; context terms only ever read
    what is already here. Keeping them in one list for matching and two lists
    in config is the point — widening context is free, widening collection is
    not.
    """
    from app.services import market_collect as mc

    seen: List[str] = []
    for term in list(mc.market_terms(conn, market_id)) + context_terms(conn, market_id):
        t = (term or "").strip()
        if t and t.lower() not in {x.lower() for x in seen}:
            seen.append(t)
    return seen


# ---------------------------------------------------------------------------
# What kind of thing an article is
# ---------------------------------------------------------------------------
#
# A market aggregator that mixes a trade-press story, a vendor's own blog post
# and a vendor's LinkedIn update into one undifferentiated list is misleading,
# because the three carry very different weight. A vendor saying it solved a
# problem is not evidence that the problem is solved.
#
#   news     — a third-party publication
#   vendor   — published by a tracked vendor on its own site
#   social   — a tracked vendor's LinkedIn post
#   research — an academic paper
#
# Vendor is decided by domain against the registry, which is exact. Nothing
# here is inferred from the wording.

ARTICLE_CLASSES = ("news", "vendor", "social", "discussion", "research")

# Practitioner social — Bluesky, X, Reddit — as opposed to ``social``, which
# is a tracked vendor posting about itself. The distinction is the whole point:
# a vendor saying its product works and a practitioner saying it does not are
# both "social posts" and are not remotely the same evidence.
_DISCUSSION_SOURCES = ("bluesky", "bsky", "xpoz", "reddit", "mastodon")

# Feeds that are papers rather than press.
_RESEARCH_SOURCES = {"semantic_scholar", "arxiv", "pubmed", "biorxiv"}


def vendor_domains(conn, market_id: int) -> set:
    """Registered domains for every vendor in the market, excluded ones too.

    An excluded vendor's blog is still that vendor's blog. Dropping it from
    this set would relabel its posts as third-party news, which is the one
    mistake this function exists to prevent.
    """
    rows = conn.execute(text("""
        SELECT DISTINCT i.normalized_value
        FROM bw_vendor_identifiers i
        JOIN bw_market_brands mb ON mb.brand_id = i.brand_id
                                 AND mb.market_id = :m
        WHERE i.kind = 'domain' AND i.valid_to IS NULL
    """), {"m": market_id}).fetchall()
    out = set()
    for (value,) in rows:
        host = (value or "").strip().lower().lstrip(".")
        if host.startswith("www."):
            host = host[4:]
        if host:
            out.add(host)
    return out


def _host(uri: str) -> str:
    from urllib.parse import urlparse

    try:
        host = (urlparse(uri or "").hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def classify_article(uri: str, news_source: Optional[str],
                     bias_source: Optional[str], domains: set) -> str:
    """Which kind of thing this article is."""
    if (bias_source or "") == "vendor:linkedin":
        return "social"
    source = (news_source or "").strip().lower()
    if source in _RESEARCH_SOURCES:
        return "research"
    # Checked before the domain match: a practitioner post that happens to link
    # a vendor's site is still a practitioner post.
    if any(source == d or source.startswith(d + ":") for d in _DISCUSSION_SOURCES):
        return "discussion"
    host = _host(uri)
    if host and any(host == d or host.endswith("." + d) for d in domains):
        return "vendor"
    return "news"


def market_topic_name(market: Dict[str, Any]) -> str:
    cfg = market.get("config") if isinstance(market.get("config"), dict) else {}
    topic = ((cfg or {}).get("collection") or {}).get("topic_name")
    return topic or f"Market Monitoring {market.get('name')}"


def scan(conn, market_id: int, *,
         terms: Optional[Sequence[str]] = None,
         topic_name: Optional[str] = None,
         days: Optional[int] = None,
         limit: int = DEFAULT_LIMIT,
         min_score: float = DEFAULT_MIN_SCORE,
         require_analyzed: bool = False,
         dry_run: bool = False) -> Dict[str, Any]:
    """Match the corpus against the market's terms and record what matched.

    ``require_analyzed`` defaults to **off**, unlike Brand Watcher's classifier,
    which only reads rows where ``analyzed = true``. That gate is why a
    classification run over a 206,000-article corpus processed eleven articles:
    it was reading the small set the AI analysis step had already finished, not
    the corpus. Term matching needs a title and a summary and nothing else, so
    it has no reason to inherit that limit.

    Writes nothing when ``dry_run``, so an operator can see what a set of terms
    would pull in before committing to it.
    """
    if terms is None:
        terms = corpus_terms(conn, market_id)
    terms = [t for t in (terms or []) if str(t).strip()]
    if not terms:
        return {"error": "market has no collection terms", "terms": 0,
                "scanned": 0, "matched": 0, "inserted": 0, "updated": 0}

    pg_pattern, py_terms = compile_terms(terms)
    if not pg_pattern:
        return {"error": "no usable terms", "terms": 0, "scanned": 0,
                "matched": 0, "inserted": 0, "updated": 0}

    where = ["(COALESCE(a.title,'') || ' ' || COALESCE(a.summary,'')) ~* :pat"]
    params: Dict[str, Any] = {"pat": pg_pattern, "lim": int(limit)}
    if require_analyzed:
        where.append("a.analyzed = true")
    if days:
        # publication_date is TEXT in this schema. ISO text compares correctly
        # against an ISO bound, so no cast is needed and no index is lost.
        where.append("COALESCE(a.publication_date, a.submission_date) >= :since")
        params["since"] = _iso_days_ago(days)

    rows = conn.execute(text(f"""
        SELECT a.uri, a.title, a.summary, a.topic, a.news_source,
               COALESCE(a.publication_date, a.submission_date) AS published
        FROM articles a
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(a.publication_date, a.submission_date) DESC
        LIMIT :lim
    """), params).mappings().all()

    topic = topic_name or ""
    inserted = 0
    updated = 0
    matched = 0
    below = 0
    samples: List[Dict[str, Any]] = []

    for row in rows:
        terms_hit, title_hits, body_hits, score = score_article(
            row["title"], row["summary"], py_terms)
        if not terms_hit:
            continue
        if score < min_score:
            below += 1
            continue
        matched += 1
        origin = "collected" if (topic and row["topic"] == topic) else "corpus"
        if len(samples) < 25:
            samples.append({
                "uri": row["uri"], "title": row["title"],
                "source": row["news_source"], "published": row["published"],
                "topic": row["topic"], "score": score, "origin": origin,
                "matched_terms": terms_hit,
            })
        if dry_run:
            continue
        result = conn.execute(text("""
            INSERT INTO bw_market_articles
                (market_id, article_uri, matched_terms, title_terms,
                 body_terms, score, method, origin)
            VALUES (:m, :uri, :terms, :tt, :bt, :score, 'term_match', :origin)
            ON CONFLICT (market_id, article_uri) DO UPDATE SET
                matched_terms = EXCLUDED.matched_terms,
                title_terms   = EXCLUDED.title_terms,
                body_terms    = EXCLUDED.body_terms,
                score         = EXCLUDED.score,
                origin        = EXCLUDED.origin,
                matched_at    = NOW()
            RETURNING (xmax = 0) AS is_insert
        """), {"m": market_id, "uri": row["uri"], "terms": terms_hit,
               "tt": title_hits, "bt": body_hits, "score": score,
               "origin": origin}).scalar()
        if result:
            inserted += 1
        else:
            updated += 1

    return {
        "terms": len(terms),
        "scanned": len(rows),
        "matched": matched,
        "below_min_score": below,
        "inserted": inserted,
        "updated": updated,
        "min_score": min_score,
        "days": days,
        "limit": limit,
        "truncated": len(rows) >= int(limit),
        "dry_run": dry_run,
        "samples": samples,
    }


def _iso_days_ago(days: int) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime(
        "%Y-%m-%dT%H:%M:%S")


def summary(conn, market_id: int, *, days: int = 30) -> Dict[str, Any]:
    """Counts, top terms and top sources for the market's matched corpus."""
    since = _iso_days_ago(days)
    totals = conn.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE origin = 'collected') AS collected,
               COUNT(*) FILTER (WHERE origin = 'corpus') AS corpus,
               MAX(matched_at) AS last_scan
        FROM bw_market_articles WHERE market_id = :m
    """), {"m": market_id}).mappings().first()

    recent = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m
          AND COALESCE(a.publication_date, a.submission_date) >= :since
    """), {"m": market_id, "since": since}).scalar() or 0

    top_terms = conn.execute(text("""
        SELECT term, COUNT(*) AS n
        FROM bw_market_articles ma, UNNEST(ma.matched_terms) AS term
        WHERE ma.market_id = :m
        GROUP BY term ORDER BY n DESC, term LIMIT 20
    """), {"m": market_id}).mappings().all()

    top_sources = conn.execute(text("""
        SELECT COALESCE(a.news_source, 'unknown') AS source, COUNT(*) AS n
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m
        GROUP BY 1 ORDER BY n DESC LIMIT 15
    """), {"m": market_id}).mappings().all()

    by_week = conn.execute(text("""
        SELECT TO_CHAR(
                   DATE_TRUNC('week',
                       COALESCE(a.publication_date, a.submission_date)::timestamp),
                   'YYYY-MM-DD') AS week,
               COUNT(*) AS n
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m
          AND COALESCE(a.publication_date, a.submission_date) >= :since
        GROUP BY 1 ORDER BY 1
    """), {"m": market_id, "since": _iso_days_ago(max(days, 90))}
    ).mappings().all()

    domains = vendor_domains(conn, market_id)
    kinds: Dict[str, int] = {c: 0 for c in ARTICLE_CLASSES}
    for uri, source, bias in conn.execute(text("""
        SELECT a.uri, a.news_source, a.bias_source
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m
    """), {"m": market_id}).fetchall():
        kinds[classify_article(uri, source, bias, domains)] += 1

    verdicts = dict(conn.execute(text("""
        SELECT COALESCE(review_verdict, 'unreviewed'), COUNT(*)
        FROM bw_market_articles WHERE market_id = :m
        GROUP BY 1
    """), {"m": market_id}).fetchall())

    signal_kinds = [dict(r) for r in conn.execute(text("""
        SELECT review_kind AS kind, COUNT(*) AS n
        FROM bw_market_articles
        WHERE market_id = :m AND review_verdict = 'signal'
        GROUP BY 1 ORDER BY n DESC, kind
    """), {"m": market_id}).mappings().all()]

    return {
        "by_class": kinds,
        "by_verdict": verdicts,
        "signal_kinds": signal_kinds,
        "total": (totals or {}).get("total", 0),
        "collected": (totals or {}).get("collected", 0),
        "corpus": (totals or {}).get("corpus", 0),
        "last_scan": (totals or {}).get("last_scan"),
        "recent_days": days,
        "recent": recent,
        "top_terms": [dict(r) for r in top_terms],
        "top_sources": [dict(r) for r in top_sources],
        "by_week": [dict(r) for r in by_week],
    }


def articles(conn, market_id: int, *, limit: int = 50, offset: int = 0,
             days: Optional[int] = None, origin: Optional[str] = None,
             min_score: float = 0.0,
             classes: Optional[Sequence[str]] = None,
             require_signal_for_social: bool = True) -> List[Dict[str, Any]]:
    """The matched corpus, newest first.

    ``require_signal_for_social`` is the rule that lets vendor LinkedIn posts
    back in. They were excluded wholesale because 562 of them against 122 news
    articles buries everything, but the review pass found 107 that state a real
    fact — 42 launches, 16 partnerships, 11 named customers, 2 raises and an
    acquisition. So a post is included when it was read and judged to carry
    something, and left out otherwise. Set it False to see every post
    including the ones judged noise.
    """
    # The kind of an article is decided in Python, from the URL's host against
    # the vendor registry. So when a caller filters by kind the SQL limit has
    # to be loosened first, or "give me 100 news items" silently returns the
    # news items that happened to be inside the first 100 rows of every kind.
    fetch = min(limit * 5, 2000) if classes else limit
    where = ["ma.market_id = :m", "ma.score >= :ms"]
    params: Dict[str, Any] = {"m": market_id, "ms": min_score,
                              "lim": fetch, "off": offset}
    if days:
        where.append("COALESCE(a.publication_date, a.submission_date) >= :since")
        params["since"] = _iso_days_ago(days)
    if origin in ("collected", "corpus"):
        where.append("ma.origin = :origin")
        params["origin"] = origin
    if require_signal_for_social:
        # An unreviewed *vendor* post is not yet known to be worth showing, so
        # it is left out with the ones judged noise. Practitioner posts are not
        # covered by this: nobody is marketing in them, so the relevance floor
        # at collection is the gate that matters.
        where.append("(COALESCE(a.bias_source, '') <> 'vendor:linkedin'"
                     " OR ma.review_verdict = 'signal')")

    rows = conn.execute(text(f"""
        SELECT a.uri, a.title, a.summary, a.news_source, a.topic,
               COALESCE(a.publication_date, a.submission_date) AS published,
               a.sentiment, a.category, a.analyzed, a.bias_source,
               ma.score, ma.matched_terms, ma.origin, ma.title_terms,
               ma.review_verdict, ma.review_kind, ma.review_reason
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(a.publication_date, a.submission_date) DESC,
                 ma.score DESC
        LIMIT :lim OFFSET :off
    """), params).mappings().all()

    domains = vendor_domains(conn, market_id)
    wanted = {c for c in (classes or ()) if c in ARTICLE_CLASSES}
    out: List[Dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        row["article_class"] = classify_article(
            row["uri"], row["news_source"], row.pop("bias_source", None),
            domains)
        if wanted and row["article_class"] not in wanted:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out
