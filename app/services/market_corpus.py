"""Matching the existing article corpus against a market's own language.

The gap this closes: Brand Watcher classifies articles by **vendor name**. Ask
it for SOC-automation coverage and it returns articles that named Crogl or
Dropzone. An article about autonomous SOC adoption that names no vendor is
invisible to it — correctly, because it is answering "who was mentioned".

A market monitor needs the other question: which articles are *about this
category*, whoever they name. That is a match against the market's own phrases
("SOC automation", "agentic SOC", "SOAR platform"), not against a company.

It needs the first question answered too, and for a while it assumed Brand
Watcher was answering it. It was not: Brand Watcher's classifier had attributed
28 articles across 84 vendors in total, so every per-vendor "earned coverage"
figure in the market monitor was read from a store that was empty by
construction. :func:`attribute_vendors` now runs inside :func:`scan` and links
each article that names a vendor to that vendor, so "who was mentioned" and
"what is this about" are answered in the same pass over the same corpus.

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


def own_voice_sql(alias: str = "a") -> str:
    """SQL for "this post on a vendor's channel is really the vendor speaking".

    A reshare is the company amplifying somebody else, and a person's post is
    not the company's at all. Counting either as an owned post credits a vendor
    for words it did not write — 17% of this market's supposed vendor posts,
    and 32% for one vendor.

    ``entity_ingest._is_company_speaking`` is the same rule in Python, and the
    entity layer has applied it since the fields were retained. This is the
    expression the read paths need, defined once so the two cannot drift; a
    test asserts they agree row for row.

    A record with neither field — everything collected before they were kept —
    passes, which is how it was already treated. Changing that would relabel
    the historical corpus on no evidence.
    """
    return (
        f"(COALESCE({alias}.social_meta->>'is_repost', 'false') <> 'true'"
        f" AND (lower(COALESCE({alias}.social_meta->>'account_type',"
        f" 'organization')) IN ('organization', 'company')))"
    )


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


def vendor_domain_sql(article: str = "a", brand: Optional[str] = "bac",
                      market_param: str = ":m") -> str:
    """SQL for "this article was published on the vendor's own site".

    The SQL twin of the domain check in :func:`classify_article`, which has
    always got this right in Python and which the counting paths never
    consulted. They keyed owned-versus-earned on ``bias_source`` alone, and a
    vendor's blog carries no ``bias_source`` — so eleven of Dropzone AI's own
    blog posts, and one of Radiant Security's, were counted as third parties
    covering them. Half of this market's supposed earned coverage was vendors
    talking about themselves.

    ``brand`` is the alias holding the vendor the article is attributed to, and
    the match is against *that* vendor's domains. This is deliberate and it is
    the interesting part: Dropzone's blog writing about Crogl is Dropzone's own
    voice for Dropzone and genuine third-party coverage for Crogl. Pass
    ``brand=None`` where no vendor is in scope and any monitored vendor's domain
    should count as owned.

    Defined once here beside :func:`own_voice_sql` for the same reason: a second
    copy of a classification rule is a second thing to drift, and a test asserts
    this agrees with the Python row for row.
    """
    host = (f"lower(regexp_replace(COALESCE({article}.url, {article}.uri),"
            f" '^https?://(www\\.)?([^/]+).*$', '\\2'))")
    scope = (f"vi.brand_id = {brand}.brand_id" if brand else f"""
                 EXISTS (SELECT 1 FROM bw_market_brands vmb
                          WHERE vmb.brand_id = vi.brand_id
                            AND vmb.market_id = {market_param}
                            AND vmb.role <> 'excluded')""")
    return f"""EXISTS (
        SELECT 1 FROM bw_vendor_identifiers vi
         WHERE vi.kind = 'domain' AND vi.valid_to IS NULL
           AND {scope}
           AND ({host} = lower(vi.normalized_value)
                OR {host} LIKE '%.' || lower(vi.normalized_value)))"""


def earned_sql(article: str = "a", brand: Optional[str] = "bac",
               market_param: str = ":m") -> str:
    """SQL for "somebody other than this vendor published this".

    Earned coverage is the whole point of watching a market — it is the
    difference between a company saying it matters and anyone else agreeing —
    so it has to exclude both of the vendor's own channels, not just LinkedIn.
    """
    return (f"(COALESCE({article}.bias_source,'') <> 'vendor:linkedin'"
            f" AND NOT {vendor_domain_sql(article, brand, market_param)})")


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


# ---------------------------------------------------------------------------
# Which vendor an article names
# ---------------------------------------------------------------------------

#: ``bw_article_categories.classification_method`` for a row written here, so
#: a reader can tell a name match from Brand Watcher's LLM classification and
#: from a manual backfill, and so a re-run can find its own rows.
NAME_MATCH_METHOD = "market_name_match"

#: ``bw_market_articles.method`` for an article that reached the market corpus
#: only because it named a vendor, not because it used a market phrase.
NAME_MATCH_CORPUS_METHOD = "vendor_name"


def _strip_parenthetical(name: str) -> str:
    """"Variance (was Intrinsic)" -> "Variance"; "Strike48 (A Devo company)"
    -> "Strike48". The bracketed part is a note to the operator, not a name
    anyone would print in an article."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name or "").strip()


def vendor_name_terms(conn, market_id: int) -> List[Dict[str, Any]]:
    """The names each vendor in the market can be recognised by.

    ``bw_brands.brand_keywords`` and ``product_keywords`` are the reviewed
    alias table the spec asks for — an operator wrote "Cantina security" for
    Cantina and "Variance security" for Variance precisely because the bare
    word matches restaurants and statistics. They are used as written. Only a
    vendor with no keyword at all falls back to its display name, with any
    bracketed note stripped.

    Excluded vendors are left out: an article naming an out-of-scope company
    is not this market's coverage. ``config.news_keyword_excludes`` is carried
    through so the per-brand negative list Brand Watcher honours is honoured
    here too.
    """
    rows = conn.execute(text("""
        SELECT b.id, b.display_name, b.brand_keywords, b.product_keywords,
               b.config
          FROM bw_market_brands mb
          JOIN bw_brands b ON b.id = mb.brand_id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
         ORDER BY b.id
    """), {"m": market_id}).fetchall()
    out: List[Dict[str, Any]] = []
    for brand_id, display_name, brand_kw, product_kw, cfg in rows:
        terms: List[str] = []
        for source in (brand_kw, product_kw):
            for kw in (source or []) if isinstance(source, list) else []:
                t = str(kw or "").strip()
                if t and t.lower() not in {x.lower() for x in terms}:
                    terms.append(t)
        if not terms:
            fallback = _strip_parenthetical(display_name)
            if fallback:
                terms.append(fallback)
        cfg = cfg if isinstance(cfg, dict) else {}
        excludes = [str(x).strip() for x in (cfg.get("news_keyword_excludes") or [])
                    if str(x).strip()]
        if terms:
            out.append({"brand_id": int(brand_id), "vendor": display_name,
                        "terms": terms, "excludes": excludes})
    return out


def market_qualifier(conn, market_id: int) -> Optional[str]:
    """The one word the market's collection was qualified with ("security").

    Set at collection setup, in ``config.collection.qualifier``, to keep a
    vendor-name search from returning the wrong company. It does the same job
    here, on the corpus side.
    """
    cfg = conn.execute(text(
        "SELECT config FROM bw_markets WHERE id = :m"), {"m": market_id}).scalar()
    cfg = cfg if isinstance(cfg, dict) else {}
    q = ((cfg.get("collection") or {}).get("qualifier") or "").strip()
    return q or None


def context_patterns(conn, market_id: int) -> List[re.Pattern]:
    """What a third-party article has to contain, besides a vendor's name.

    A name on its own is not enough. Measured over ninety days of this corpus,
    "Joon" matched a K-drama cast list and a BTS story, "Andesite" matched a
    mining assay, and none of them was about the company. Requiring the market
    qualifier ("security") or one of the market's own phrases in the same text
    removed all three.

    It also removed fourteen articles that were about the vendor — its own blog
    posts, which talk about the product and never say "security", and a
    practitioner thanking "7AI" for a sponsorship. So the requirement is not
    applied everywhere: see :func:`attribute_vendors` for the two cases where
    the name is taken as it stands. The rule stays one an operator can read off
    the match — the vendor's name, plus the market's word, unless the name
    could not be anything else or the page is the vendor's own.
    """
    terms: List[str] = []
    q = market_qualifier(conn, market_id)
    if q:
        terms.append(q)
    terms.extend(corpus_terms(conn, market_id))
    _, py_terms = compile_terms(terms)
    return [pattern for _, pattern in py_terms]


def _distinctive(term: str) -> bool:
    """Whether a name could be nothing but a name.

    A token with a digit or a dot in it ("7ai", "Secure.com", "Strike48") is
    not a word in any language, so it needs no context to be believed. A bare
    word — "Joon", "Andesite", "Alpha Level" — does, because the corpus has
    shown it will match something else.
    """
    t = (term or "").strip()
    return bool(t) and any(ch.isdigit() or ch == "." for ch in t)


def _vendor_hits(text_content: str, vendors: Sequence[Dict[str, Any]]
                 ) -> List[Tuple[Dict[str, Any], str]]:
    """``[(vendor, term that matched)]`` for one article's text.

    Uses Brand Watcher's ``_mentions`` so the two paths agree on what a name
    match is: word-boundaried, and tolerant of a keyword that starts or ends
    with a non-word character ("7ai", "Secure.com").
    """
    from app.routes.brand_watcher_routes import _mentions

    hits: List[Tuple[Dict[str, Any], str]] = []
    for vendor in vendors:
        if any(_mentions(text_content, x) for x in vendor["excludes"]):
            continue
        for term in vendor["terms"]:
            if _mentions(text_content, term):
                hits.append((vendor, term))
                break
    return hits


def _link_entity(conn, uri: str, brand_id: int, term: str) -> None:
    """Tell the entity layer about a link the market just made.

    The vendor page's "External mentions" reads ``bw_entity_mentions``; the
    market overview's "earned" reads ``bw_article_categories``. The entity
    layer's own backlog matcher consults ``bw_article_categories`` when it
    first examines an article, so a fresh attribution reaches both stores —
    but it examines each article once, and 1,704 of them had already been
    examined and found to name nobody before this pass existed. Linking here
    keeps the two counts in step instead of leaving the vendor page reading 0
    while the overview reads 2 for the same vendor and the same articles.

    A fault in the entity layer must not undo an attribution, so the link is
    written inside a savepoint and rolled back to it on failure. Catching the
    exception alone is not enough: Postgres aborts the whole transaction on an
    error, and the scan's own writes would be lost with it at commit.
    """
    from app.services import entity_flags

    if not entity_flags.enabled():
        return
    conn.execute(text("SAVEPOINT market_entity_link"))
    try:
        from app.services import entity_ingest

        # "keyword" is the entity layer's name for a reviewed brand keyword
        # found in the text, which is what this is.
        entity_ingest.link_content(conn, uri, candidates=[{
            "brand_id": brand_id, "term": term,
            "attribution_method": "keyword",
            "mention_type": "explicit_name",
        }])
        conn.execute(text("RELEASE SAVEPOINT market_entity_link"))
    except Exception:                                           # noqa: BLE001
        conn.execute(text("ROLLBACK TO SAVEPOINT market_entity_link"))
        logger.exception("entity link failed for %s / brand %s", uri, brand_id)


def attribute_vendors(conn, market_id: int, *,
                      topic_name: Optional[str] = None,
                      days: Optional[int] = None,
                      limit: int = DEFAULT_LIMIT,
                      dry_run: bool = False) -> Dict[str, Any]:
    """Link every article that names a vendor to that vendor.

    Writes one ``bw_article_categories`` row per (article, vendor), never a
    second one for a pair any method has already linked — the overview and
    the benchmark count rows, and a second category on the same article would
    count one story twice. The article is also entered in
    ``bw_market_articles`` when the phrase scan did not already put it there,
    so the coverage feed and the post review see it.

    A third-party article must also carry the market's qualifier or one of
    its phrases (:func:`context_patterns`), unless the name is one that could
    not be a word (:func:`_distinctive`) or the page is on a tracked vendor's
    own domain. Everything the rule turns away is returned under ``rejected``.

    Reads titles and summaries. Writes nothing when ``dry_run``.
    """
    vendors = vendor_name_terms(conn, market_id)
    if not vendors:
        return {"vendors": 0, "scanned": 0, "matched": 0, "attributed": 0,
                "already_linked": 0, "without_context": 0, "corpus_added": 0,
                "samples": [], "rejected": []}

    pg_pattern, _ = compile_terms(
        [t for v in vendors for t in v["terms"]])
    contexts = context_patterns(conn, market_id)

    where = ["(COALESCE(a.title,'') || ' ' || COALESCE(a.summary,'')) ~* :pat",
             # A vendor's LinkedIn post is attributed when it lands, by the
             # account it came from, which is exact. Re-reading it here would
             # only re-find the vendor's name in the vendor's own words.
             "COALESCE(a.bias_source, '') <> 'vendor:linkedin'"]
    params: Dict[str, Any] = {"pat": pg_pattern, "lim": int(limit)}
    if days:
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

    from app.routes.brand_watcher_routes import _mentions
    from app.services.market_collect import _categorize

    domains = vendor_domains(conn, market_id)
    topic = topic_name or ""
    matched = attributed = already = without_context = corpus_added = 0
    samples: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    per_vendor: Dict[str, int] = {}
    for row in rows:
        content = f"{row['title'] or ''} {row['summary'] or ''}"
        hits = _vendor_hits(content, vendors)
        if not hits:
            continue
        # The context requirement, and the two cases it does not apply to: a
        # page on a tracked vendor's own site is about a vendor by definition,
        # and a name with a digit or a dot in it cannot be a dictionary word.
        host = _host(row["uri"])
        own_site = bool(host) and any(host == d or host.endswith("." + d)
                                      for d in domains)
        in_context = own_site or not contexts or \
            any(p.search(content) for p in contexts)
        kept = [(v, t) for v, t in hits if in_context or _distinctive(t)]
        for v, t in hits:
            if (v, t) not in kept:
                without_context += 1
                if len(rejected) < 25:
                    rejected.append({"uri": row["uri"], "title": row["title"],
                                     "source": row["news_source"],
                                     "vendor": v["vendor"], "term": t})
        hits = kept
        if not hits:
            continue
        matched += 1
        in_title = False
        for vendor, term in hits:
            per_vendor[vendor["vendor"]] = per_vendor.get(vendor["vendor"], 0) + 1
            in_title = in_title or _mentions(row["title"] or "", term)
            if len(samples) < 25:
                samples.append({"uri": row["uri"], "title": row["title"],
                                "source": row["news_source"],
                                "published": row["published"],
                                "vendor": vendor["vendor"], "term": term})
            if dry_run:
                continue
            cats = _categorize(row["title"] or "", row["summary"] or "")
            category = cats[0] if cats else "Media & Advertising"
            wrote = conn.execute(text("""
                INSERT INTO bw_article_categories
                    (article_uri, brand_id, category, classification_method,
                     confidence)
                SELECT :uri, :bid, :cat, :method, 1.0
                 WHERE NOT EXISTS (
                     SELECT 1 FROM bw_article_categories x
                      WHERE x.article_uri = :uri AND x.brand_id = :bid)
            """), {"uri": row["uri"], "bid": vendor["brand_id"],
                   "cat": category, "method": NAME_MATCH_METHOD}).rowcount
            if wrote:
                attributed += 1
                _link_entity(conn, row["uri"], vendor["brand_id"], term)
            else:
                already += 1
        if dry_run:
            continue
        origin = "collected" if (topic and row["topic"] == topic) else "corpus"
        # A name in the headline is the story's subject, the same weight the
        # phrase scan gives a phrase in the headline.
        score = TITLE_WEIGHT if in_title else BODY_WEIGHT
        corpus_added += conn.execute(text("""
            INSERT INTO bw_market_articles
                (market_id, article_uri, matched_terms, title_terms,
                 body_terms, score, method, origin)
            VALUES (:m, :uri, '{}', :tt, :bt, :score, :method, :origin)
            ON CONFLICT (market_id, article_uri) DO NOTHING
        """), {"m": market_id, "uri": row["uri"],
               "tt": 1 if in_title else 0, "bt": 0 if in_title else 1,
               "score": score, "method": NAME_MATCH_CORPUS_METHOD,
               "origin": origin}).rowcount

    return {
        "vendors": len(vendors),
        "scanned": len(rows),
        "matched": matched,
        "attributed": attributed,
        "already_linked": already,
        "without_context": without_context,
        "corpus_added": corpus_added,
        "truncated": len(rows) >= int(limit),
        "dry_run": dry_run,
        "by_vendor": dict(sorted(per_vendor.items(), key=lambda kv: -kv[1])),
        "samples": samples,
        # What the context rule turned away, so an operator can see whether
        # it is turning away the right things.
        "rejected": rejected,
    }


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

    # Same window, same limit, same dry-run: an article that names a vendor is
    # this market's coverage whether or not it used a market phrase.
    names = attribute_vendors(conn, market_id, topic_name=topic_name,
                              days=days, limit=limit, dry_run=dry_run)

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
        "vendor_names": names,
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
        SELECT COALESCE(NULLIF(SPLIT_PART(a.news_source, ':', 2), ''),
                        a.news_source, 'unknown') AS source, COUNT(*) AS n
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
    weekly = _mark_partial_weeks([dict(r) for r in by_week])

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
        "by_week": weekly,
        # Same floor as by_week just above: a shorter selection would draw a
        # 1-2 point chart, which reads as broken rather than as "not much
        # history yet". Before this, sentiment_trend ignored `days` entirely
        # and always drew a fixed 26 weeks, so it never moved when the Pulse
        # period selector changed while by_week and every other panel did.
        "sentiment_trend": sentiment_trend(conn, market_id,
                                           weeks=max(days, 90) // 7),
    }


def _mark_partial_weeks(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flag the week that has not finished, and say how much of it we have.

    The last bar is always short and always looks like a collapse. The week
    starting Monday 24 August read 41 against roughly 170 for a full week,
    which is what three and a half days looks like — not a drop in coverage.

    Two separate reasons the newest bar under-reads, and the chart has to admit
    both. The week is not over, and matching runs behind publication: 1,200
    articles were matched into one market on a single day, most of them
    published earlier, so a recent week keeps filling for days after it ends.
    That makes the most recent *complete* week provisional too.
    """
    if not rows:
        return rows
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone.utc).date()
    # Monday of the current week, matching DATE_TRUNC('week') in the query.
    this_monday = today - timedelta(days=today.weekday())
    for row in rows:
        try:
            monday = datetime.strptime(row["week"], "%Y-%m-%d").date()
        except (ValueError, TypeError, KeyError):
            continue
        if monday >= this_monday:
            row["partial"] = True
            row["days_covered"] = (today - monday).days + 1
            row["partial_reason"] = (
                f'{row["days_covered"]} of 7 days so far')
        elif monday >= this_monday - timedelta(days=7):
            # Finished, but too recent to have stopped filling.
            row["partial"] = True
            row["days_covered"] = 7
            row["partial_reason"] = (
                "still filling — we match articles for several days after "
                "they are published")
        else:
            row["partial"] = False
    return rows


def sentiment_trend(conn, market_id: int, *, weeks: int = 26) -> List[Dict[str, Any]]:
    """Weekly net-sentiment index for the market's matched corpus.

    Three series per week: all matched coverage, coverage attributed to a
    tracked vendor (via bw_article_categories), and everything else ("the
    market broadly"). Sentiment predicates mirror escalation_tiers._POS/_NEG
    so this agrees with what brand-level surfaces report for the same
    articles. A week under MIN_SCORED_FOR_SENTIMENT classified articles is
    None, not zero — there isn't enough signal to call a direction, and
    charting None as 0 would read as "neutral" when it means "no data".
    """
    from app.services.escalation_tiers import _NEG, _POS, MIN_SCORED_FOR_SENTIMENT

    since = _iso_days_ago(weeks * 7)
    rows = conn.execute(text(f"""
        WITH scoped AS (
            SELECT ma.article_uri,
                   COALESCE(a.publication_date, a.submission_date) AS pub,
                   a.sentiment,
                   EXISTS (
                       SELECT 1 FROM bw_article_categories bac
                       JOIN bw_market_brands mb ON mb.brand_id = bac.brand_id
                                                AND mb.market_id = ma.market_id
                       WHERE bac.article_uri = ma.article_uri
                   ) AS vendor_attributed
            FROM bw_market_articles ma
            JOIN articles a ON a.uri = ma.article_uri
            WHERE ma.market_id = :m
              AND COALESCE(a.publication_date, a.submission_date) >= :since
        )
        SELECT TO_CHAR(DATE_TRUNC('week', pub::timestamp), 'YYYY-MM-DD') AS week,
               COUNT(*) FILTER (WHERE COALESCE(sentiment, '') <> '')                  AS scored_all,
               COUNT(*) FILTER (WHERE {_POS})                                         AS pos_all,
               COUNT(*) FILTER (WHERE {_NEG})                                         AS neg_all,
               COUNT(*) FILTER (WHERE vendor_attributed
                                       AND COALESCE(sentiment, '') <> '')             AS scored_vendor,
               COUNT(*) FILTER (WHERE vendor_attributed AND {_POS})                   AS pos_vendor,
               COUNT(*) FILTER (WHERE vendor_attributed AND {_NEG})                   AS neg_vendor,
               COUNT(*) FILTER (WHERE NOT vendor_attributed
                                       AND COALESCE(sentiment, '') <> '')             AS scored_broad,
               COUNT(*) FILTER (WHERE NOT vendor_attributed AND {_POS})               AS pos_broad,
               COUNT(*) FILTER (WHERE NOT vendor_attributed AND {_NEG})               AS neg_broad
        FROM scoped
        GROUP BY 1 ORDER BY 1
    """), {"m": market_id, "since": since}).mappings().all()

    def _net(pos: int, neg: int, scored: int) -> Optional[int]:
        return (round((pos - neg) / scored * 100)
                if scored >= MIN_SCORED_FOR_SENTIMENT else None)

    return [{
        "week": r["week"],
        "scored_all": r["scored_all"],
        "net_all": _net(r["pos_all"], r["neg_all"], r["scored_all"]),
        "net_vendor": _net(r["pos_vendor"], r["neg_vendor"], r["scored_vendor"]),
        "net_broad": _net(r["pos_broad"], r["neg_broad"], r["scored_broad"]),
    } for r in rows]


# Social coverage repeats itself heavily: the same launch, the same Forbes
# piece, the same benchmark, posted by a dozen accounts within a day. Shown as
# a flat list that reads as twelve findings when it is one.
_CLUSTER_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "is", "are", "was", "were", "at", "by", "from", "this", "that",
    "it", "its", "as", "be", "we", "our", "you", "your", "new", "how", "why",
    "what", "more", "just", "now", "can", "will", "has", "have",
}


# Two posts are the same story when most of their meaningful words overlap.
# An exact fingerprint of the "longest words" was tried first and grouped by
# vendor name instead of by subject — every Exaforce post mentions Exaforce, so
# they all collapsed into one cluster while genuinely duplicated coverage of a
# SentinelOne announcement stayed apart.
CLUSTER_SIMILARITY = 0.55

# Below this a post has too few distinctive words for an overlap ratio to mean
# anything: two five-word posts sharing three words are not the same story.
MIN_CLUSTER_WORDS = 6


def _content_words(title: str, summary: str, vendor_words: set) -> set:
    """The words that carry a post's subject.

    Vendor names are removed. They are the most repeated words in the corpus
    and say only who is speaking, not what about — leaving them in makes every
    vendor its own cluster.
    """
    text_value = f"{title or ''} {summary or ''}".lower()
    text_value = re.sub(r"https?://\S+", " ", text_value)
    words = set(re.findall(r"[a-z][a-z0-9'\-]{3,}", text_value))
    return {w for w in words
            if w not in _CLUSTER_STOP and w not in vendor_words}


def cluster(rows: List[Dict[str, Any]], vendor_names: Optional[List[str]] = None
            ) -> List[Dict[str, Any]]:
    """Group coverage of the same story, newest first within each group.

    Returns the same rows with a ``cluster`` block on the first of each group,
    so a caller renders one card saying "and 6 more like this" rather than
    seven cards that read as seven findings.
    """
    vendor_words = set()
    for name in vendor_names or []:
        for word in re.findall(r"[a-z][a-z0-9'\-]{2,}", (name or "").lower()):
            vendor_words.add(word)

    prepared = []
    for row in rows:
        words = _content_words(row.get("title") or "", row.get("summary") or "",
                               vendor_words)
        prepared.append((row, words if len(words) >= MIN_CLUSTER_WORDS else None))

    used = [False] * len(prepared)
    out: List[Dict[str, Any]] = []
    for i, (row, words) in enumerate(prepared):
        if used[i]:
            continue
        used[i] = True
        head = dict(row)
        if words:
            members = []
            for j in range(i + 1, len(prepared)):
                if used[j]:
                    continue
                other, other_words = prepared[j]
                if not other_words:
                    continue
                overlap = len(words & other_words)
                union = len(words | other_words)
                if union and overlap / union >= CLUSTER_SIMILARITY:
                    used[j] = True
                    members.append(other)
            if members:
                head["cluster"] = {
                    "size": len(members) + 1,
                    "others": [{"uri": m["uri"], "title": m.get("title"),
                                "news_source": m.get("news_source"),
                                "published": m.get("published"),
                                "article_class": m.get("article_class"),
                                "author": (m.get("social_meta") or {}).get("author")}
                               for m in members],
                }
        out.append(head)
    return out


def articles(conn, market_id: int, *, limit: int = 50, offset: int = 0,
             days: Optional[int] = None, origin: Optional[str] = None,
             min_score: float = 0.0,
             classes: Optional[Sequence[str]] = None,
             require_signal_for_social: bool = True,
             vendor_id: Optional[int] = None) -> List[Dict[str, Any]]:
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
    if vendor_id is not None:
        where.append("""EXISTS (SELECT 1 FROM bw_article_categories bac
                                WHERE bac.article_uri = a.uri
                                  AND bac.brand_id = :vendor_id)""")
        params["vendor_id"] = vendor_id
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
               a.social_meta,
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
    # Which vendors each article is attributed to, so the reader can see whose
    # coverage a row is and filter by it. One query for the page rather than
    # one per row.
    uris = [r["uri"] for r in rows]
    vendors_by_uri: Dict[str, List[Dict[str, Any]]] = {}
    if uris:
        for uri, brand_id, name in conn.execute(text("""
            SELECT DISTINCT bac.article_uri, b.id, b.display_name
            FROM bw_article_categories bac
            JOIN bw_brands b ON b.id = bac.brand_id
            JOIN bw_market_brands mb ON mb.brand_id = b.id AND mb.market_id = :m
            WHERE bac.article_uri = ANY(:uris)
        """), {"m": market_id, "uris": uris}).fetchall():
            vendors_by_uri.setdefault(uri, []).append(
                {"brand_id": brand_id, "vendor": name})

    out: List[Dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        row["article_class"] = classify_article(
            row["uri"], row["news_source"], row.pop("bias_source", None),
            domains)
        row["vendors"] = vendors_by_uri.get(row["uri"], [])
        meta = row.get("social_meta")
        row["social_meta"] = meta if isinstance(meta, dict) else None
        if wanted and row["article_class"] not in wanted:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out
