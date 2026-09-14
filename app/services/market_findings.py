"""What changed in a market, as findings rather than a feed of records.

The Findings page answered "what did the system ingest". It listed collected
posts and articles, newest first, which is an activity feed — it cannot say what
changed, because a post is evidence and evidence is not a conclusion.

A finding is a deduplicated market change with its evidence attached.
``bw_entity_events`` already held most of that model: an occurrence date with
its own precision, a first-observed date, corroboration counted on distinct
sources, evidence rows and affected vendors. This module reads those as findings
— grouping them into the specification's six themes, deriving materiality,
mapping evidence state onto the four statuses a reader sees, and ordering by
visible rules rather than an opaque relevance score.

Two things it deliberately does not do.

**It does not invent an event date.** ``occurred_at`` is null where nothing
established one, and the page says "date not established" rather than showing
the collection time in a slot labelled as when it happened.

**It separates what a vendor can state about itself from what it merely claims.**
A company announcing its own product, its own hire or its own rebrand is the
authoritative source for that fact; there is nobody else to confirm it, and
demanding a second source treats the primary record as a weakness. A company
announcing that a named customer chose it, or that a round closed, is an
interested party talking about somebody else who has not spoken yet. The first
is a confirmed finding on the vendor's own word. The second stays a watch item
until the other side, or a publisher, says the same thing.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.services import market_metrics as mmet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Themes (spec 4.15)
# ---------------------------------------------------------------------------
#
# Six groups, in the order the page shows them. The extractors' own event types
# are the input; a type nobody has mapped lands in "Attention and narrative"
# rather than vanishing, and the raw type travels with every finding so a reader
# can see what it actually was.
THEMES: List[Tuple[str, Tuple[str, ...]]] = [
    ("Funding and ownership", ("funding_round", "acquisition", "ipo",
                               "investment", "merger")),
    ("Product and launches", ("product_launch", "product_update",
                              "certification", "integration")),
    ("Customers and partnerships", ("partnership", "customer_win",
                                    "reseller_agreement")),
    ("Hiring and headcount", ("hiring_spike", "headcount_change", "layoff",
                              "office_opening")),
    ("Leadership and strategy", ("leadership_change", "strategy_shift",
                                 "brand_identity_change", "rebrand")),
    ("Attention and narrative", ("coverage_spike", "sentiment_shift")),
]

THEME_ORDER = [name for name, _ in THEMES]
_THEME_OF = {t: name for name, types in THEMES for t in types}
FALLBACK_THEME = "Attention and narrative"


def theme_of(event_type: Optional[str]) -> str:
    return _THEME_OF.get((event_type or "").strip().lower(), FALLBACK_THEME)


# ---------------------------------------------------------------------------
# Evidence state (spec 4.15 status)
# ---------------------------------------------------------------------------
#
# The reader sees four states. The database holds two related fields — the
# event's lifecycle status and how well corroborated it is — and the mapping
# between them is the interesting part:
#
#   dismissed     the event was rejected on review, or folded into another
#   confirmed     a primary document, including the vendor's own announcement
#                 of a fact about itself
#   corroborated  two or more independent sources
#   watch         a claim about somebody else, so far only from the claimant
#
# The line between the last two is who the statement is about, not who made it.
STATUSES = ("confirmed", "corroborated", "watch", "dismissed")

# Facts a company is the authoritative source for. Nobody else can confirm that
# Exaforce shipped a feature or hired a CRO, because Exaforce doing it *is* the
# event — so "no independent source" on one of these describes the world, not a
# gap in our evidence. Everything outside this set involves a second party (an
# investor, a customer, an acquirer, a partner) who has not spoken, and there
# the vendor is an interested witness rather than the record.
#
# Layoffs sit outside deliberately. A company is authoritative that it cut
# staff, but the scale is the part that matters and the part it frames.
SELF_REPORTABLE = frozenset({
    "product_launch", "product_update", "certification", "integration",
    "leadership_change", "office_opening", "rebrand", "brand_identity_change",
    "hiring_spike", "headcount_change", "strategy_shift",
})

# Which evidence relationships count toward supporting a finding. The same set
# entity_events.recompute_corroboration uses, named once here because I wrote
# the narrower version ('supports' only) in two places and both silently
# reported zero sources against a corroboration field that said otherwise.
SUPPORTING = ("supports", "originates")

_STATUS_RANK = {s: i for i, s in enumerate(STATUSES)}


def status_of(event_status: str, corroboration: str, *,
              event_type: Optional[str] = None,
              vendor_voiced: bool = False) -> str:
    if event_status in ("rejected", "superseded"):
        return "dismissed"
    if corroboration == "primary_document":
        return "confirmed"
    if corroboration == "corroborated":
        return "corroborated"
    # The vendor's own channel, on a fact the vendor owns. Calling that a watch
    # item asks a company to corroborate its own product launch.
    if vendor_voiced and (event_type or "").strip().lower() in SELF_REPORTABLE:
        return "confirmed"
    return "watch"


# ---------------------------------------------------------------------------
# Materiality
# ---------------------------------------------------------------------------
#
# Ordering the page by materiality means having one, and the spec is explicit
# that it must not be an unexplained score. So these are rules, the reason is
# returned alongside the value, and both are shown.
#
# The shape of the judgement: money and ownership change the market; a
# partnership or a named customer changes a vendor's position; a job advert is
# the weakest signal we collect, because every growing company always has some.
_HIGH_TYPES = frozenset({"funding_round", "acquisition", "ipo", "merger",
                         "leadership_change"})
_MEDIUM_TYPES = frozenset({"partnership", "customer_win", "product_launch",
                           "strategy_shift", "layoff"})


def materiality_of(event_type: str, *, corroboration: str,
                   vendor_count: int,
                   attributes: Optional[Dict[str, Any]] = None
                   ) -> Tuple[str, str]:
    """How much this matters, and why in one clause."""
    event_type = (event_type or "").strip().lower()
    attrs = attributes or {}

    # A changed page on the vendor's own site, before anything else is
    # considered. The web-diff extractor files these as product_launch, so
    # "Andesite: news page changed" — twelve words different on a news index —
    # was ranking as a medium-materiality product launch in the executive
    # summary. We know something changed and not what, and usually not when.
    if attrs.get("page_kind") is not None:
        words = attrs.get("changed_word_count")
        return "low", (f"only a page on the vendor's own site changed"
                       + (f", by {words} words" if isinstance(words, int)
                          else ""))

    if event_type in _HIGH_TYPES:
        return "high", "money or ownership changed hands"

    if event_type in _MEDIUM_TYPES:
        # A change touching several monitored companies at once is a market
        # movement rather than one company's news.
        if vendor_count > 1:
            return "high", (f"affects {vendor_count} monitored vendors at once")
        if corroboration in ("corroborated", "primary_document"):
            return "high", "independently corroborated"
        return "medium", "a change in one vendor's position"

    if event_type in ("hiring_spike", "headcount_change", "office_opening"):
        # Deliberately low. Every growing company is always hiring, so a job
        # advert on its own is the weakest thing we collect.
        return "low", "hiring is a weak signal on its own"

    return "low", "no rule ranks this type higher"


# ---------------------------------------------------------------------------
# Reading findings
# ---------------------------------------------------------------------------

SORTS = ("recommended", "newest_event", "recently_observed",
         "highest_confidence", "vendor")


def _sort_key(sort: str):
    """The deterministic tiers behind each order.

    "Recommended" is the specification's five tiers, in its order: new or
    materially updated first, then materiality, then evidence state, then the
    event date falling back to when we first saw it, then the id. The id tie-break
    is what makes it total — without it two findings with identical everything
    else swap places between requests and the page appears to shuffle itself.

    The evidence tier counts outside sources before it looks at the status
    label. Once a vendor's own product announcement became "confirmed" — which
    it should be, since nobody else can confirm it — ranking on the label alone
    floated every routine launch post above a named US Air Force contract,
    because the contract is a claim about somebody else and stays a watch item.
    Outside interest is what the tier was for.
    """
    materiality_rank = {"high": 0, "medium": 1, "low": 2}

    if sort == "newest_event":
        return lambda f: (f["occurred_at"] is None,
                          _neg_stamp(f["occurred_at"] or f["first_observed_at"]),
                          f["finding_id"])
    if sort == "recently_observed":
        return lambda f: (_neg_stamp(f["first_observed_at"]), f["finding_id"])
    if sort == "highest_confidence":
        return lambda f: (-(f["confidence"] or 0),
                          _STATUS_RANK.get(f["status"], 9), f["finding_id"])
    if sort == "vendor":
        return lambda f: ((f["vendors"][0]["vendor"].lower()
                           if f["vendors"] else "~"), f["finding_id"])
    return lambda f: (
        0 if f["is_new_in_period"] else 1,
        materiality_rank.get(f["materiality"], 3),
        -(f.get("non_vendor_source_count") or 0),
        # No tier on the status label itself. It no longer ranks how well
        # supported a finding is — "confirmed" now covers a vendor's own
        # product post — so within one materiality band the date decides, and
        # the byline tells the reader where each item came from.
        _neg_stamp(f["occurred_at"] or f["first_observed_at"]),
        f["finding_id"],
    )


def _neg_stamp(value) -> float:
    """Newest first, as a sortable number, with nulls last."""
    if value is None:
        return float("inf")
    try:
        return -value.timestamp()
    except AttributeError:
        return float("inf")


def findings(conn, market_id: int, *, days: Optional[int] = 30,
             theme: Optional[str] = None, vendor_id: Optional[int] = None,
             status: Optional[str] = None,
             materiality: Optional[str] = None,
             sort: str = "recommended",
             include_dismissed: bool = False,
             page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    """The market's findings, ordered by visible rules."""
    from app.services import market_lists as ml

    sort = sort if sort in SORTS else "recommended"
    size = max(1, min(page_size, ml.MAX_PAGE_SIZE))
    offset = (max(1, page) - 1) * size

    where = ["mb.market_id = :m", "mb.role <> 'excluded'"]
    params: Dict[str, Any] = {"m": market_id}
    if not include_dismissed:
        # Tombstoned and rejected events are not findings. They are kept so a
        # folded duplicate cannot be recreated, not so they can be read.
        where.append("e.status NOT IN ('rejected', 'superseded')")
    if days:
        # On the event date where there is one, falling back to when we first
        # saw it. Filtering only on occurred_at would drop every finding whose
        # date was never established, which is the opposite of the intent.
        where.append("COALESCE(e.occurred_at, e.first_observed_at) >= "
                     "NOW() - (:days || ' days')::INTERVAL")
        params["days"] = str(days)
    if vendor_id is not None:
        where.append("ee.brand_id = :vid")
        params["vid"] = vendor_id

    rows = [dict(r) for r in conn.execute(text(f"""
        SELECT DISTINCT
               e.id, e.event_type, e.event_subtype, e.title, e.description,
               e.occurred_at, e.date_precision, e.first_observed_at,
               e.last_observed_at, e.confidence, e.corroboration, e.status,
               e.attributes, e.materiality AS stored_materiality,
               e.review_state, e.why_it_matters, e.limitations
          FROM bw_entity_events e
          JOIN bw_entity_event_entities ee ON ee.event_id = e.id
          JOIN bw_market_brands mb ON mb.brand_id = ee.brand_id
         WHERE {' AND '.join(where)}
    """), params).mappings().all()]

    if not rows:
        return _empty(conn, market_id, days, sort,
                      {"theme": theme, "vendor_id": vendor_id,
                       "status": status, "materiality": materiality})

    ids = [r["id"] for r in rows]
    vendors = _vendors_for(conn, ids)
    evidence = _evidence_summary(conn, ids)

    out: List[Dict[str, Any]] = []
    for row in rows:
        ev = evidence.get(row["id"], {})
        vend = vendors.get(row["id"], [])
        # Every supporting source is one of the vendor's own channels. Whether
        # that is the record or only a claim depends on what the event is about,
        # which is why the type goes in too.
        vendor_voiced = bool(ev.get("sources")) and not ev.get(
            "independent_sources")
        state = status_of(row["status"], row["corroboration"],
                          event_type=row["event_type"],
                          vendor_voiced=vendor_voiced)
        # Stored materiality wins where somebody set it; otherwise derived, and
        # the reason travels either way so the page never shows a bare label.
        derived, why_material = materiality_of(
            row["event_type"], corroboration=row["corroboration"],
            vendor_count=len(vend), attributes=row["attributes"])
        material = row["stored_materiality"] or derived

        out.append({
            "finding_id": row["id"],
            "headline": row["title"],
            "summary": row["description"],
            "why_it_matters": row["why_it_matters"],
            "materiality": material,
            "materiality_reason": (why_material if not row["stored_materiality"]
                                   else "set on review"),
            "finding_type": row["event_type"],
            "finding_subtype": row["event_subtype"],
            "theme": theme_of(row["event_type"]),
            "status": state,
            "corroboration": row["corroboration"],
            "confidence": row["confidence"],
            "review_state": row["review_state"],
            "vendors": vend,
            # Null where nothing established one. The page says "date not
            # established"; it never shows first_observed_at in this slot.
            "occurred_at": row["occurred_at"],
            "date_precision": row["date_precision"],
            "first_observed_at": row["first_observed_at"],
            "last_updated_at": row["last_observed_at"],
            "independent_source_count": ev.get("sources", 0),
            "non_vendor_source_count": ev.get("independent_sources", 0),
            # Together these let a page say "announced by Exaforce" where the
            # vendor is the record, and "not confirmed by the other side" where
            # it is only the claimant, without re-deriving the rule.
            "vendor_voiced": vendor_voiced,
            "supporting": ev.get("supporting") or [],
            "self_reportable": (row["event_type"] or "").strip().lower()
            in SELF_REPORTABLE,
            "evidence_count": ev.get("items", 0),
            "source_platforms": ev.get("platforms", []),
            "strongest_evidence": ev.get("strongest"),
            "has_contradiction": ev.get("contradicted", False),
            "limitations": list(row["limitations"] or []),
            "attributes": row["attributes"] or {},
        })

    # "New in selected period", not "new since your last visit": there is no
    # per-viewer read timestamp, and claiming the reader personally has not seen
    # something we cannot know is a lie the ordering does not need.
    for finding in out:
        stamp = finding["occurred_at"] or finding["first_observed_at"]
        finding["is_new_in_period"] = bool(
            days and stamp and _within_days(stamp, days))

    if theme:
        out = [f for f in out if f["theme"] == theme]
    if status:
        out = [f for f in out if f["status"] == status]
    if materiality:
        out = [f for f in out if f["materiality"] == materiality]

    out.sort(key=_sort_key(sort))

    # The executive section: the few things that deserve attention now.
    # Dismissed never appears, and a low-materiality watch item does not either
    # — it is the most common kind of record here and would crowd out the rest.
    executive = [f for f in out
                 if f["status"] != "dismissed"
                 and not (f["status"] == "watch"
                          and f["materiality"] == "low")][:5]

    by_theme = {name: [f for f in out if f["theme"] == name]
                for name in THEME_ORDER}
    watch_items = [f for f in out if f["status"] == "watch"]

    return {
        "data": out[offset:offset + size],
        "executive": executive,
        "by_theme": {k: v for k, v in by_theme.items() if v},
        "watch_items": watch_items[:20],
        "meta": _meta(conn, market_id, days, sort, len(out), page, size,
                      {"theme": theme, "vendor_id": vendor_id,
                       "status": status, "materiality": materiality},
                      findings_rows=out),
    }


def _within_days(stamp, days: int) -> bool:
    from datetime import datetime, timedelta, timezone
    try:
        return stamp >= datetime.now(timezone.utc) - timedelta(days=days)
    except TypeError:
        return False


def _vendors_for(conn, event_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    out: Dict[int, List[Dict[str, Any]]] = {}
    for row in conn.execute(text("""
        SELECT ee.event_id, ee.brand_id, b.display_name AS vendor,
               ee.relation
          FROM bw_entity_event_entities ee
          JOIN bw_brands b ON b.id = ee.brand_id
         WHERE ee.event_id = ANY(:ids)
         ORDER BY b.display_name
    """), {"ids": event_ids}).mappings():
        out.setdefault(int(row["event_id"]), []).append({
            "brand_id": row["brand_id"], "vendor": row["vendor"],
            # subject or mentioned: a partnership names two, and
            # only one of them is the vendor whose post it was.
            "relation": row["relation"],
        })
    return out


def _evidence_summary(conn, event_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Per finding: how many items, how many *independent* sources, and the best one.

    The two counts differ and both matter. Three records from one publisher are
    three items and one source, and it is the source count that decides whether
    anything is corroborated — which is why the folded Booz Allen duplicate kept
    two evidence rows and stayed a vendor claim.
    """
    out: Dict[int, Dict[str, Any]] = {}
    for row in conn.execute(text("""
        SELECT ev.event_id,
               COUNT(*) AS items,
               -- ('supports', 'originates'), which is the set
               -- entity_events.recompute_corroboration counts. Filtering on
               -- 'supports' alone excluded the originating record — 201 of 216
               -- evidence rows — so every finding reported zero sources while
               -- its corroboration field said otherwise. Two counts of the same
               -- thing must use the same rule.
               COUNT(DISTINCT ev.independence_key) FILTER (
                   WHERE ev.relationship = ANY(:supporting)
               ) AS sources,
               COUNT(DISTINCT ev.independence_key) FILTER (
                   WHERE ev.relationship = ANY(:supporting)
                     AND ev.independence_key NOT LIKE 'owned:%'
               ) AS independent_sources,
               COUNT(*) FILTER (WHERE ev.relationship = 'contradicts') AS against,
               ARRAY_AGG(DISTINCT SPLIT_PART(ev.independence_key, ':', 1))
                   AS key_kinds,
               (ARRAY_AGG(ev.excerpt ORDER BY LENGTH(COALESCE(ev.excerpt, ''))
                          DESC))[1] AS strongest_excerpt,
               (ARRAY_AGG(ev.article_uri ORDER BY
                          LENGTH(COALESCE(ev.excerpt, '')) DESC))[1] AS strongest_uri,
               -- Every supporting record, not only the strongest. A page that
               -- offers one link out of five holds four the reader cannot see.
               -- One row per source key, so three items from one publisher
               -- appear once rather than three times.
               JSONB_AGG(DISTINCT JSONB_BUILD_OBJECT(
                   'uri', ev.article_uri,
                   'key', ev.independence_key,
                   'title', a.title,
                   'source', COALESCE(NULLIF(SPLIT_PART(a.news_source, ':', 2), ''),
                                      a.news_source),
                   'social', (a.social_meta IS NOT NULL)
               )) FILTER (WHERE ev.relationship = ANY(:supporting)
                            AND ev.article_uri IS NOT NULL) AS supporting_rows
          FROM bw_entity_event_evidence ev
          LEFT JOIN articles a ON a.uri = ev.article_uri
         WHERE ev.event_id = ANY(:ids)
         GROUP BY ev.event_id
    """), {"ids": event_ids,
           "supporting": list(SUPPORTING)}).mappings():
        out[int(row["event_id"])] = {
            "items": int(row["items"] or 0),
            "sources": int(row["sources"] or 0),
            # Sources that are not the vendor itself. This is the number that
            # decides whether anything is corroborated, and it is usually zero.
            "independent_sources": int(row["independent_sources"] or 0),
            "contradicted": bool(row["against"]),
            # 'owned' and 'domain' rather than a platform name: the key records
            # whose voice it is, which is the useful distinction here.
            "platforms": sorted({k for k in (row["key_kinds"] or []) if k}),
            "strongest": ({"excerpt": row["strongest_excerpt"],
                           "uri": row["strongest_uri"]}
                          if row["strongest_excerpt"] or row["strongest_uri"]
                          else None),
            "supporting": _dedupe_supporting(row["supporting_rows"]),
        }
    return out


def _dedupe_supporting(rows) -> List[Dict[str, Any]]:
    """One entry per source key, labelled by whose voice it is.

    ``JSONB_AGG(DISTINCT ...)`` deduplicates whole objects, so two records from
    the same publisher with different titles both survive it. The key is what
    decides independence everywhere else, so it decides here too.
    """
    seen: Dict[str, Dict[str, Any]] = {}
    for row in (rows or []):
        key = row.get("key") or row.get("uri") or ""
        if key in seen:
            continue
        owned = str(key).startswith("owned:")
        primary = str(key).startswith(("official:", "filing:", "sec:"))
        seen[key] = {
            "uri": row.get("uri"),
            "title": (row.get("title") or "").strip(),
            "source": (row.get("source") or "").strip(),
            "social": bool(row.get("social")),
            "voice": "primary" if primary else "owned" if owned else "independent",
        }
    # Independent sources first, then primary documents, then the vendor's own
    # channels — the order a reader would want to click in.
    rank = {"independent": 0, "primary": 1, "owned": 2}
    return sorted(seen.values(), key=lambda r: (rank.get(r["voice"], 3),
                                                r["source"], r["title"]))


def evidence(conn, market_id: int, finding_id: int) -> Dict[str, Any]:
    """Every record behind one finding, deduplicated by source."""
    # The row, not a truthiness test on the type: an event with a null or empty
    # event_type exists, and reading its type as "missing" would 404 it.
    found = conn.execute(text("""
        SELECT e.event_type FROM bw_entity_events e
          JOIN bw_entity_event_entities ee ON ee.event_id = e.id
          JOIN bw_market_brands mb ON mb.brand_id = ee.brand_id
         WHERE e.id = :f AND mb.market_id = :m LIMIT 1
    """), {"f": finding_id, "m": market_id}).first()
    if found is None:
        raise ValueError(f"finding {finding_id} is not in market {market_id}")
    self_reportable = (found[0] or "").strip().lower() in SELF_REPORTABLE

    rows = [dict(r) for r in conn.execute(text("""
        SELECT ev.id, ev.evidence_type, ev.relationship, ev.independence_key,
               ev.excerpt, ev.article_uri, ev.snapshot_id, ev.created_at,
               a.title, a.url, a.news_source,
               COALESCE(a.publication_date, a.submission_date) AS published_at
          FROM bw_entity_event_evidence ev
          LEFT JOIN articles a ON a.uri = ev.article_uri
         WHERE ev.event_id = :f
         ORDER BY ev.relationship, ev.created_at
    """), {"f": finding_id}).mappings().all()]

    for row in rows:
        key = row["independence_key"] or ""
        # Said plainly, because "owned:vendor:X" is not a sentence.
        row["voice"] = ("the vendor's own channel" if key.startswith("owned:")
                        else "a primary document" if key.startswith(
                            ("official:", "filing:", "sec:"))
                        else "an independent publisher")

    sources = sorted({r["independence_key"] for r in rows
                      if r["relationship"] in SUPPORTING})
    return {
        "finding_id": finding_id,
        "data": rows,
        "meta": {
            "evidence_count": len(rows),
            "independent_source_count": len(sources),
            "sources": sources,
            "notes": (
                [] if not (sources and all(s.startswith("owned:")
                                           for s in sources))
                # The vendor is the source, and for its own product or its own
                # hire that is the record rather than a shortfall.
                else ["Announced by the vendor on its own channels, which is "
                      "the primary record for something a company does itself."]
                if self_reportable
                else ["Every record here comes from the vendor's own channels. "
                      "This is what the vendor said; the other party named in "
                      "it has not said the same thing."]),
        },
    }


# ---------------------------------------------------------------------------
# States (spec 4.15 empty and degraded)
# ---------------------------------------------------------------------------

def _synthesis_state(conn, market_id: int, finding_count: int,
                     days: Optional[int]) -> Dict[str, Any]:
    """Why the page is empty, when it is.

    Four different reasons, and they are not interchangeable. "No findings" when
    the evidence has not been read yet is the same error as a zero from a
    collector that never ran.
    """
    evidence_items = conn.execute(text("""
        SELECT COUNT(DISTINCT bac.article_uri)
          FROM bw_article_categories bac
          JOIN bw_market_brands mb ON mb.brand_id = bac.brand_id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
    """), {"m": market_id}).scalar() or 0

    examined = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_articles
         WHERE market_id = :m AND review_verdict IS NOT NULL
    """), {"m": market_id}).scalar() or 0

    post_state = mmet.collection_state(conn, market_id,
                                       "linkedin_company_post")
    if post_state["state"] in mmet.UNMEASURED:
        return {"state": "collection_incomplete",
                "detail": (f"Collection is {post_state['state_detail'] or ''}. "
                           "Findings cannot be complete until it succeeds."),
                "evidence_items": evidence_items}
    if finding_count:
        return {"state": "ready", "detail": None,
                "evidence_items": evidence_items}
    if evidence_items and not examined:
        # The distinction MM-23 is about: evidence in hand, nothing read yet.
        return {"state": "synthesis_pending",
                "detail": (f"{evidence_items} evidence items collected and not "
                           "yet examined. This is not the same as no findings."),
                "evidence_items": evidence_items}
    return {"state": "no_findings",
            "detail": ("Collection succeeded and nothing in the period met the "
                       "bar for a finding."),
            "evidence_items": evidence_items}


def _meta(conn, market_id: int, days: Optional[int], sort: str, total: int,
          page: int, size: int, filters: Dict[str, Any],
          findings_rows: Optional[List[Dict[str, Any]]] = None
          ) -> Dict[str, Any]:
    state = _synthesis_state(conn, market_id, total, days)
    rows = findings_rows or []
    corroborated = sum(1 for f in rows if f["status"] in
                       ("corroborated", "confirmed"))
    notes: List[str] = []
    if rows and not corroborated:
        # Nothing here has a second source. For a company's own product or hire
        # that is normal; for a claim about a customer or an investor it means
        # the other side has not spoken.
        notes.append(
            "Nobody outside the vendors has reported any of this. Where a "
            "vendor is describing its own product or its own hire, its word is "
            "the record. Where it names a customer, a partner or an investor, "
            "treat it as one side of the story until someone else says the "
            "same thing.")
    return {
        "metric": mmet.metric(
            "market_findings",
            label="Findings",
            definition=("Deduplicated market changes with their evidence "
                        "attached. A finding is not an activity record: several "
                        "reports of one event are one finding."),
            numerator="findings", denominator="evidence items examined",
            window={"days": days},
            collection=mmet.collection_state(conn, market_id,
                                             "linkedin_company_post"),
            value=total,
            limitations=[
                "Findings are evidence-backed market changes, not a complete "
                "activity feed.",
                "An event date is shown only where one was established. Where "
                "it was not, the first-observed date is shown as such.",
                "Materiality is rule-based and the rule is shown beside it. It "
                "is not a measure of business impact.",
            ]),
        "pagination": {"page": max(1, page), "page_size": size,
                       "total": total,
                       "pages": max(1, -(-total // size)) if size else 1,
                       "sort": sort,
                       "has_more": max(1, page) * size < total},
        "applied_filters": {k: v for k, v in
                            dict(filters, days=days).items()
                            if v is not None and v != ""},
        "synthesis": state,
        "counts": {
            "total": total,
            "corroborated": corroborated,
            "watch": sum(1 for f in rows if f["status"] == "watch"),
            "by_theme": {name: sum(1 for f in rows if f["theme"] == name)
                         for name in THEME_ORDER},
        },
        "themes": THEME_ORDER,
        "sorts": list(SORTS),
        "notes": notes,
    }


def _empty(conn, market_id: int, days: Optional[int], sort: str,
           filters: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "data": [], "executive": [], "by_theme": {}, "watch_items": [],
        "meta": _meta(conn, market_id, days, sort, 0, 1, 50, filters),
    }
