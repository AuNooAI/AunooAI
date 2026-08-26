"""The records behind every number, in one consistent shape.

Every aggregate on the Market Monitor page used to be a dead end. "62 vendors
with no signal" was the most useful figure on the overview and there was no way
to see which 62. A count you cannot open is a claim you cannot check, and the
whole point of the metric contract is that a reader can check.

Three rules hold across every list here.

**The drill-down uses the aggregate's filters.** Not similar filters — the same
ones, passed through. A list that quietly applies a different window or a
different relevance floor gives a total that disagrees with the card that opened
it, and then neither number can be trusted.

**Pagination happens in the database.** ``limit``/``offset`` over a set the
caller already fetched is not pagination; it hides the tail and reports a total
that is really a page size. Every list here returns its true total from a
separate ``COUNT``, and every sort has a unique tie-break so page two cannot
repeat a row from page one.

**A cap is disclosed.** Where a query is bounded, the bound is in the response,
because a silently truncated list reads as a complete one.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.services import market_metrics as mmet
from app.services.market_corpus import own_voice_sql

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 50

_OWN_VOICE = own_voice_sql("a")


def envelope(rows: List[Dict[str, Any]], *, total: int, page: int,
             page_size: int, sort: str, filters: Dict[str, Any],
             metric: Optional[Dict[str, Any]] = None,
             notes: Optional[List[str]] = None) -> Dict[str, Any]:
    """The response shape every list shares.

    One shape rather than each endpoint inventing its own, so a UI table
    component can render any of them and a reader comparing two lists is
    comparing like with like.
    """
    return {
        "data": rows,
        "meta": {
            "metric": metric,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": max(1, -(-total // page_size)) if page_size else 1,
                "sort": sort,
                "has_more": page * page_size < total,
            },
            # Echoed back so the caller can prove the list it is looking at is
            # the one it asked for. A drill-down whose filters silently differ
            # from the aggregate's is the failure this guards.
            "applied_filters": {k: v for k, v in filters.items()
                               if v is not None and v != ""},
            "notes": notes or [],
        },
    }


def _page(page: int, page_size: int) -> Tuple[int, int]:
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    return size, max(0, (max(1, page) - 1) * size)


def _since(days: Optional[int]) -> Optional[str]:
    """The window bound, in the aggregate's own format.

    ``articles.publication_date`` and ``submission_date`` are TEXT, so this
    comparison is a string comparison, and the exact spelling of the bound
    decides the result. ``datetime.isoformat()`` emits microseconds and a
    ``+00:00`` offset; the aggregates use ``_iso_days_ago``, which emits
    neither. Feeding the two into the same TEXT comparison gave a drill-down
    total of 532 against a card that said 533 — one post either side of a
    boundary that differed only in punctuation.

    So this delegates rather than reimplementing. A drill-down whose window is
    computed independently of its aggregate will disagree with it eventually,
    and the disagreement will look like a counting bug rather than a formatting
    one.
    """
    if not days:
        return None
    from app.services.market_corpus import _iso_days_ago
    return _iso_days_ago(days)


# ---------------------------------------------------------------------------
# Vendor posts (spec 4.3)
# ---------------------------------------------------------------------------

# What the review verdict is called on screen, per spec 4.13. The stored values
# stay as they are: `signal`, `commentary` and `noise` are what the classifier
# wrote and rewriting history on a rename would destroy the only record of what
# it actually decided. Both travel — the raw value and the label — and a post
# nothing has classified is Unreviewed rather than being folded into Promotion.
CLASSIFICATION_LABELS: Dict[str, str] = {
    "signal": "Announcement / factual update",
    "commentary": "Commentary / opinion",
    "noise": "Promotion / low-substance",
}
UNREVIEWED_LABEL = "Unreviewed"

OWNERSHIP_VALUES = ("owned", "reshared", "earned")

_POST_SORTS = {
    "published_at:desc": "published_at DESC NULLS LAST, uri",
    "published_at:asc": "published_at ASC NULLS LAST, uri",
    "engagement:desc": "engagement DESC NULLS LAST, uri",
    "vendor:asc": "vendor ASC, published_at DESC NULLS LAST, uri",
}


def posts(conn, market_id: int, *, days: Optional[int] = None,
          vendor_id: Optional[int] = None, platform: Optional[str] = None,
          ownership: Optional[str] = None,
          classification: Optional[str] = None,
          page: int = 1, page_size: int = DEFAULT_PAGE_SIZE,
          sort: str = "published_at:desc") -> Dict[str, Any]:
    """Vendor posts, one row per post per vendor it is attributed to.

    ``ownership`` is the distinction the market's post counts turn on. A vendor
    resharing somebody else's post is neither the vendor speaking nor anybody
    covering the vendor, so it is its own value here rather than being folded
    into either — the same rule the counts use, from the same SQL fragment.
    """
    size, offset = _page(page, page_size)
    order = _POST_SORTS.get(sort, _POST_SORTS["published_at:desc"])
    sort = sort if sort in _POST_SORTS else "published_at:desc"

    where = ["mb.market_id = :m", "mb.role <> 'excluded'",
             "COALESCE(a.bias_source,'') = 'vendor:linkedin'"]
    params: Dict[str, Any] = {"m": market_id, "lim": size, "off": offset}

    since = _since(days)
    if since:
        where.append("COALESCE(a.publication_date, a.submission_date) >= :since")
        params["since"] = since
    if vendor_id is not None:
        where.append("bac.brand_id = :vid")
        params["vid"] = vendor_id
    if platform:
        where.append("lower(COALESCE(a.social_meta->>'platform','linkedin'))"
                     " = lower(:plat)")
        params["plat"] = platform
    if ownership == "owned":
        where.append(_OWN_VOICE)
    elif ownership == "reshared":
        where.append(f"NOT {_OWN_VOICE}")
    elif ownership == "earned":
        # Earned items are not vendor:linkedin at all, so this drops the
        # owned-source condition rather than adding to it.
        where = [w for w in where
                 if w != "COALESCE(a.bias_source,'') = 'vendor:linkedin'"]
        where.append("COALESCE(a.bias_source,'') <> 'vendor:linkedin'")
    if classification:
        if classification == "unreviewed":
            where.append("r.review_verdict IS NULL")
        else:
            where.append("r.review_verdict = :cls")
            params["cls"] = classification

    joined = f"""
        FROM bw_article_categories bac
        JOIN articles a ON a.uri = bac.article_uri
        JOIN bw_brands b ON b.id = bac.brand_id
        JOIN bw_market_brands mb ON mb.brand_id = b.id
        LEFT JOIN bw_market_articles r ON r.article_uri = a.uri
                                      AND r.market_id = mb.market_id
        WHERE {' AND '.join(where)}
    """

    # DISTINCT on (brand, uri) because bw_article_categories holds one row per
    # category, so a post filed under three categories is three rows. Counting
    # them made 562 reviewed posts read as 783.
    total = conn.execute(text(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT bac.brand_id, a.uri {joined}) t"
    ), {k: v for k, v in params.items() if k not in ("lim", "off")}).scalar() or 0

    rows = [dict(r) for r in conn.execute(text(f"""
        SELECT DISTINCT
               bac.brand_id, b.display_name AS vendor,
               a.uri, a.title, a.url,
               COALESCE(a.publication_date, a.submission_date) AS published_at,
               a.submission_date AS observed_at,
               LEFT(COALESCE(a.summary, ''), 600) AS excerpt,
               a.social_meta->>'author' AS account,
               COALESCE(a.social_meta->>'platform', 'linkedin') AS platform,
               COALESCE((a.social_meta->>'reactions')::numeric, 0) AS engagement,
               COALESCE(a.social_meta->>'is_repost','false') = 'true' AS is_reshare,
               r.review_verdict AS classification_raw,
               r.review_reason AS why_relevant,
               r.review_kind AS classification_kind,
               r.matched_terms AS matched_terms,
               r.score AS relevance_score,
               ({_OWN_VOICE}) AS is_owned
        {joined}
        ORDER BY {order}
        LIMIT :lim OFFSET :off
    """), params).mappings().all()]

    for row in rows:
        raw = row.get("classification_raw")
        row["classification"] = CLASSIFICATION_LABELS.get(raw, UNREVIEWED_LABEL)
        row["engagement"] = float(row["engagement"] or 0)
        # Three values, not two. "Not owned" covers both a reshare and somebody
        # else's article, which are different things.
        row["ownership"] = ("owned" if row["is_owned"]
                            else "reshared" if row["is_reshare"]
                            else "earned")
        leg = mmet.legend_for("linkedin_company_post")
        row["provider"] = leg["provider"]

    collection = mmet.collection_state(conn, market_id, "linkedin_company_post")
    metric = mmet.metric(
        "vendor_post_records",
        label="Vendor posts",
        definition=("Individual posts attributed to a monitored vendor, with "
                    "the review verdict on each. One row per post per vendor "
                    "it mentions."),
        numerator="posts", denominator="matched vendor posts",
        window={"days": days}, collection=collection, value=total,
        limitations=[
            "A post naming two vendors appears once for each.",
            "Posts collected before reshare state was recorded read as owned.",
        ])

    return envelope(rows, total=int(total), page=max(1, page), page_size=size,
                    sort=sort, metric=metric,
                    filters={"days": days, "vendor_id": vendor_id,
                             "platform": platform, "ownership": ownership,
                             "classification": classification})


# ---------------------------------------------------------------------------
# Observed job listings (spec 4.8)
# ---------------------------------------------------------------------------

JOB_STATUSES = ("currently_observed", "newly_observed", "no_longer_observed",
                "first_observation")


# Every source that produces a job listing. Two of them now: the billed
# LinkedIn dataset, and the company's own hiring system, which is free.
JOB_SOURCES = ("linkedin_jobs", "ats_jobs")


def drop_cross_source_duplicates(rows: List[Dict[str, Any]]
                                 ) -> List[Dict[str, Any]]:
    """One role published on two boards is one role.

    A company that posts a job to LinkedIn *and* to its own hiring system
    produces two listings for one job, and adding the sources together counted
    both: of 188 listings, 39 were the same role twice — 28 of 7ai's 29 LinkedIn
    titles were also on its Ashby board, and all six of Crogl's.

    The company's own board wins. It is the primary publication, it carries a
    real posting date where the LinkedIn dataset carries none, and it is what a
    reader checking the claim will open.

    Matched on normalised title within one vendor, which is safe in this
    direction only: if a company has two distinct roles sharing a title, its own
    board has both of them, so dropping the LinkedIn copy loses nothing.

    Shared with ``market_analysis.hiring`` so the count on a card and the count
    in its drill-down cannot drift apart — they did, by exactly these 39.
    """
    own_board: Dict[Any, set] = {}
    for row in rows:
        if row.get("source") == "ats_jobs":
            own_board.setdefault(row.get("brand_id"), set()).add(
                _normalize_title(row.get("title")))
    if not own_board:
        return list(rows)

    kept = []
    for row in rows:
        title_key = _normalize_title(row.get("title"))
        if (row.get("source") != "ats_jobs" and title_key
                and title_key in own_board.get(row.get("brand_id"), set())):
            continue
        kept.append(row)
    return kept


def _normalize_title(title: Optional[str]) -> str:
    """A job title reduced to what two boards would agree on.

    Case, punctuation and runs of whitespace only. Deliberately not fuzzy: two
    genuinely different roles often differ by one word ("Senior Security
    Engineer" against "Security Engineer"), so a similarity threshold would
    merge them and undercount a company's hiring.
    """
    cleaned = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _job_run_history(conn, market_id: int
                     ) -> Tuple[Dict[Tuple[int, str], List[int]],
                                Dict[int, Optional[set]]]:
    """Per vendor and source, the successful jobs runs that covered it.

    Keyed on **(vendor, source)**, not vendor alone. A listing only ever appears
    in runs of the source that found it, so comparing an Ashby listing against
    the latest LinkedIn run would find it absent and report it gone — every ATS
    listing would read as closed on the next LinkedIn sweep, and vice versa.

    A run covers a vendor when it named that vendor (``brand_id``) or when the
    vendor was in its requested set. Market-wide sweeps are the normal case, so
    reading only ``brand_id`` would find almost no history.

    Only successful, uncapped runs count. The spec is explicit that a failed,
    partial or truncated run may not mark a listing as gone, and this is where
    that is enforced: such runs are not in the history at all, so nothing is
    ever compared against them.
    """
    rows = conn.execute(text("""
        SELECT r.id, r.brand_id, r.source, r.requested_brand_ids,
               r.metrics->'seen_item_ids' AS seen_item_ids
          FROM bw_collection_runs r
         WHERE r.market_id = :m AND r.source = ANY(:sources)
           AND r.status = 'succeeded'
           -- A batch that came back at the provider's limit may be missing
           -- listings it never saw, so it cannot be evidence of absence.
           AND COALESCE((r.metrics->>'truncated')::boolean, false) = false
         ORDER BY r.started_at DESC
    """), {"m": market_id, "sources": list(JOB_SOURCES)}).mappings().all()

    history: Dict[Tuple[int, str], List[int]] = {}
    seen_by_run: Dict[int, Optional[set]] = {}
    for row in rows:
        covered = set()
        if row["brand_id"]:
            covered.add(int(row["brand_id"]))
        for bid in (row["requested_brand_ids"] or []):
            covered.add(int(bid))
        for bid in covered:
            history.setdefault((bid, row["source"]), []).append(int(row["id"]))
        # What the run reported seeing, where it recorded that. None means the
        # run predates the recording, and the caller falls back to the
        # snapshot's own run id.
        items = row["seen_item_ids"]
        seen_by_run[int(row["id"])] = (
            {str(i) for i in items} if isinstance(items, list) else None)
    return history, seen_by_run


def jobs(conn, market_id: int, *, brand_id: Optional[int] = None,
         status: Optional[str] = None, source: Optional[str] = None,
         page: int = 1, page_size: int = DEFAULT_PAGE_SIZE,
         sort: str = "vendor:asc",
         include_all: bool = False) -> Dict[str, Any]:
    """Job listings we can currently see, and what changed since last time.

    Deliberately not called hiring. First observation is not an opening date and
    disappearance is not a confirmed closure — a listing can vanish because it
    was filled, withdrawn, reworded, or because the provider's page did not
    include it that day. The statuses say only what we observed.
    """
    size, offset = _page(page, page_size)
    history, seen_by_run = _job_run_history(conn, market_id)

    where = ["s.snapshot_type = 'job_posting'", "mb.market_id = :m",
             "mb.role <> 'excluded'", "s.source = ANY(:sources)"]
    params: Dict[str, Any] = {"m": market_id, "sources": list(JOB_SOURCES)}
    if brand_id is not None:
        where.append("s.brand_id = :b")
        params["b"] = brand_id
    # `source` is deliberately *not* filtered here — see the dedup below.

    # One row per listing, carrying every run that saw it, so the status rules
    # below are a set comparison rather than another query per row.
    rows = [dict(r) for r in conn.execute(text(f"""
        SELECT s.provider_item_id, s.brand_id, s.source,
               b.display_name AS vendor,
               MAX(s.data->>'title') AS title,
               MAX(s.data->>'location') AS location,
               MAX(s.data->>'seniority') AS seniority,
               -- ATS listings carry the board's own department in `function`
               -- and a normalised guess in `function_hint`; LinkedIn ones only
               -- have the former. Preferring the raw value keeps the company's
               -- own wording where it exists.
               COALESCE(MAX(s.data->>'function'),
                        MAX(s.data->>'function_hint')) AS function,
               MAX(s.data->>'employment_type') AS employment_type,
               MAX(s.data->>'url') AS url,
               MAX(s.data->>'observed_source') AS observed_source,
               MIN(s.observed_at) AS first_seen,
               MAX(s.observed_at) AS last_seen,
               -- A real publication date where the board gives one. LinkedIn
               -- never did reliably; Greenhouse and Ashby both do.
               MAX(s.published_at) AS posted_at,
               ARRAY_AGG(DISTINCT s.collection_run_id) AS seen_in_runs
          FROM bw_vendor_snapshots s
          JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
          JOIN bw_brands b ON b.id = s.brand_id
         WHERE {' AND '.join(where)}
         GROUP BY s.provider_item_id, s.brand_id, s.source, b.display_name
    """), params).mappings().all()]

    from app.services.market_analysis import _group_function

    out: List[Dict[str, Any]] = []
    for row in rows:
        # Keyed on the source that produced the listing, so an Ashby listing is
        # only ever compared against Ashby runs. Comparing across sources would
        # report every ATS listing as gone on the next LinkedIn sweep.
        runs = history.get((int(row["brand_id"]), row["source"]), [])
        latest = runs[0] if runs else None
        previous = runs[1] if len(runs) > 1 else None
        stored_in = {r for r in (row["seen_in_runs"] or []) if r is not None}

        def _was_seen(run_id: Optional[int]) -> Optional[bool]:
            """Was this listing present in that run? True, False, or unknown.

            Three values, not two, and the third one matters. A run that
            recorded what it saw gives a definitive answer. A run that did not
            — every run from before that recording existed — can only confirm
            presence, never absence: an unchanged listing writes no new
            snapshot, so the stored row still points at the first run that saw
            it and says nothing about later ones.

            Treating that silence as absence marked all 99 listings "newly
            observed" on the first run after the change, which is a claim about
            a change that did not happen.
            """
            if run_id is None:
                return None
            reported = seen_by_run.get(run_id)
            if reported is not None:
                return row["provider_item_id"] in reported
            return True if run_id in stored_in else None

        seen_latest = _was_seen(latest)
        seen_previous = _was_seen(previous)

        if latest is None:
            # No successful covering run at all, so nothing can be said about
            # this listing's current state.
            state = "first_observation"
        elif seen_latest:
            # Present now. "Newly" needs the previous run to have *definitely*
            # not had it — unknown is not absent, or the first run after any
            # change to how presence is recorded reports the whole board as new.
            state = ("newly_observed" if seen_previous is False
                     else "currently_observed")
        elif seen_latest is False and seen_previous is False:
            # Definitely absent from the two most recent successful, uncapped
            # runs. Both have to be definite: one unknown is not a disappearance.
            state = "no_longer_observed"
        else:
            # Not confirmed present and not confirmed gone.
            state = "first_observation"

        row["status"] = state
        row["function_group"] = _group_function(row.get("function"))
        row["runs_covering_vendor"] = len(runs)
        row.pop("seen_in_runs", None)
        out.append(row)

    # Deduplicated across sources before any filter is applied, so filtering to
    # one source cannot change what counts as a duplicate. Applied after, the
    # per-source totals summed to 188 against an unfiltered 149.
    before = len(out)
    out = drop_cross_source_duplicates(out)
    duplicates = before - len(out)

    if source:
        out = [r for r in out if r["source"] == source]
    if status:
        out = [r for r in out if r["status"] == status]

    reverse = sort.endswith(":desc")
    key = sort.split(":")[0]
    if key == "first_seen":
        out.sort(key=lambda r: (r["first_seen"], r["vendor"]), reverse=reverse)
    elif key == "last_seen":
        out.sort(key=lambda r: (r["last_seen"], r["vendor"]), reverse=reverse)
    else:
        out.sort(key=lambda r: (r["vendor"], r["title"] or ""))
        sort = "vendor:asc"

    total = len(out)
    states = [mmet.collection_state(conn, market_id, src)
              for src in JOB_SOURCES]
    single_run = sum(1 for r in out if r["runs_covering_vendor"] < 2)
    by_source: Dict[str, int] = {}
    for row in out:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1

    notes = []
    if duplicates:
        notes.append(
            f"{duplicates} LinkedIn listing(s) were excluded as the same role "
            "already published on the company's own board, which is the "
            "primary source and carries a posting date.")
    if single_run:
        notes.append(
            f"{single_run} listing(s) belong to a vendor with only one "
            "successful jobs run on file for that source, so no change can be "
            "reported for them yet.")
    # Which source found what. Two sources with very different coverage read as
    # one number otherwise, and the LinkedIn half is the thin one.
    if len(by_source) > 1:
        notes.append("By source: " + ", ".join(
            f"{n} from {k.replace('_', ' ')}"
            for k, n in sorted(by_source.items(), key=lambda kv: -kv[1])))

    metric = mmet.metric(
        "observed_job_listings",
        label="Observed active job listings",
        definition=("Listings seen at a monitored vendor in the most recent "
                    "successful, uncapped collection, from LinkedIn and from "
                    "the company's own hiring system. First observation is not "
                    "an opening date and disappearance is not a confirmed "
                    "closure."),
        numerator="job listings", denominator="monitored vendors",
        collections=states, value=total,
        limitations=[
            # Kept, and rewritten. LinkedIn alone was the largest gap in this
            # metric: Dropzone AI listed nothing there and had eleven roles on
            # its own board. Reading the board directly closes most of it, and
            # what remains is companies that publish nothing machine-readable.
            "Most companies here do not hire through LinkedIn, so listings now "
            "come from each company's own hiring system where we can find one. "
            "A company whose careers page publishes no structured listings is "
            "still uncovered, and a zero for it means we found nothing to read "
            "rather than that it is not hiring.",
            "Indeed cannot attribute a listing to a company, so it is not a "
            "substitute source.",
            "A listing can disappear because it was filled, withdrawn or "
            "reworded, and we cannot tell which.",
            "Only successful, uncapped runs are compared, and only against the "
            "same source, so neither a failed run nor the other source ever "
            "marks a listing as gone.",
        ])

    result = envelope(out[offset:offset + size], total=total,
                      page=max(1, page), page_size=size, sort=sort,
                      metric=metric, notes=notes,
                      filters={"brand_id": brand_id, "status": status,
                               "source": source})
    if include_all:
        # The whole matching set, for the route's pre-existing `postings` key.
        # That key used to hold every listing, and quietly cutting it to one
        # page would truncate the hiring panel to 50 of 91 with nothing on
        # screen to say so. The rows are already built above, so this costs
        # nothing beyond the reference.
        result["_all"] = out
    return result


# ---------------------------------------------------------------------------
# Coverage items (spec 4.4)
# ---------------------------------------------------------------------------

def coverage_items(conn, market_id: int, *, days: Optional[int] = None,
                   week: Optional[str] = None, source: Optional[str] = None,
                   vendor_id: Optional[int] = None,
                   page: int = 1, page_size: int = DEFAULT_PAGE_SIZE,
                   sort: str = "published_at:desc") -> Dict[str, Any]:
    """The records behind one bar of the weekly content chart.

    ``week`` takes an ISO date for the Monday of the week, which is what the
    chart's own x-axis carries, so clicking a bar can pass its label straight
    through instead of recomputing a range and risking a different one.
    """
    size, offset = _page(page, page_size)
    order = ("published_at ASC NULLS LAST, uri" if sort.endswith(":asc")
             else "published_at DESC NULLS LAST, uri")
    sort = "published_at:asc" if sort.endswith(":asc") else "published_at:desc"

    where = ["mb.market_id = :m", "mb.role <> 'excluded'"]
    params: Dict[str, Any] = {"m": market_id, "lim": size, "off": offset}
    since = _since(days)
    if since:
        where.append("COALESCE(a.publication_date, a.submission_date) >= :since")
        params["since"] = since
    if week:
        where.append(
            "DATE_TRUNC('week', COALESCE(a.publication_date, "
            "a.submission_date)::timestamp) = DATE_TRUNC('week', :week::timestamp)")
        params["week"] = week
    if vendor_id is not None:
        where.append("bac.brand_id = :vid")
        params["vid"] = vendor_id
    if source:
        # The stored discriminator, so "vendor LinkedIn" and "news" separate
        # the way the chart's own legend does.
        if source == "vendor_linkedin":
            where.append("COALESCE(a.bias_source,'') = 'vendor:linkedin'")
        elif source == "news":
            where.append("COALESCE(a.bias_source,'') <> 'vendor:linkedin'")
            where.append("COALESCE(a.social_meta->>'platform','') = ''")
        else:
            where.append("lower(COALESCE(a.social_meta->>'platform','')) "
                         "= lower(:src)")
            params["src"] = source

    joined = f"""
        FROM bw_article_categories bac
        JOIN articles a ON a.uri = bac.article_uri
        JOIN bw_brands b ON b.id = bac.brand_id
        JOIN bw_market_brands mb ON mb.brand_id = b.id
        WHERE {' AND '.join(where)}
    """
    total = conn.execute(text(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT a.uri {joined}) t"),
        {k: v for k, v in params.items()
         if k not in ("lim", "off")}).scalar() or 0

    rows = [dict(r) for r in conn.execute(text(f"""
        SELECT DISTINCT a.uri, a.title, a.url,
               COALESCE(a.publication_date, a.submission_date) AS published_at,
               a.bias_source,
               COALESCE(a.social_meta->>'platform',
                        CASE WHEN COALESCE(a.bias_source,'') = 'vendor:linkedin'
                             THEN 'linkedin' ELSE 'news' END) AS platform,
               CASE WHEN COALESCE(a.bias_source,'') = 'vendor:linkedin'
                    THEN 'vendor-owned' ELSE 'third-party (earned)' END
                   AS ownership,
               LEFT(COALESCE(a.summary, ''), 400) AS excerpt
        {joined}
        ORDER BY {order}
        LIMIT :lim OFFSET :off
    """), params).mappings().all()]

    news = mmet.collection_state(conn, market_id, "linkedin_company_post")
    metric = mmet.metric(
        "content_observed",
        label="Content observed",
        definition=("Items matching this market that we observed in the period. "
                    "A floor for what was published, not a measure of it."),
        numerator="distinct matched items", denominator="items we collected",
        window={"days": days}, collection=news, value=total,
        limitations=["We observe configured sources only, so this is coverage "
                     "we collected rather than everything published."])

    return envelope(rows, total=int(total), page=max(1, page), page_size=size,
                    sort=sort, metric=metric,
                    filters={"days": days, "week": week, "source": source,
                             "vendor_id": vendor_id})


# ---------------------------------------------------------------------------
# One voice's posts (spec 4.14)
# ---------------------------------------------------------------------------

def voice_posts(conn, market_id: int, author: str, *,
                days: Optional[int] = None, page: int = 1,
                page_size: int = DEFAULT_PAGE_SIZE) -> Dict[str, Any]:
    """Every relevant post by one account, with the vendors each one names.

    Reads the market corpus (``bw_market_articles``), which is the population
    ``top_voices`` counts. An earlier version joined ``bw_article_categories``
    instead — per-vendor attribution — and returned nothing for accounts the
    voices list ranked, because a practitioner post can be about the market
    without naming a vendor we track. Vendor attribution is a LEFT JOIN here for
    exactly that reason: it labels a post, it does not decide whether the post
    counts.
    """
    size, offset = _page(page, page_size)
    where = ["ma.market_id = :m",
             "a.social_meta->>'author' = :author",
             "COALESCE(a.bias_source,'') <> 'vendor:linkedin'"]
    params: Dict[str, Any] = {"m": market_id, "author": author,
                              "lim": size, "off": offset}
    since = _since(days)
    if since:
        where.append("COALESCE(a.publication_date, a.submission_date) >= :since")
        params["since"] = since

    joined = f"""
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE {' AND '.join(where)}
    """
    total = conn.execute(text(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT a.uri {joined}) t"),
        {k: v for k, v in params.items()
         if k not in ("lim", "off")}).scalar() or 0

    rows = [dict(r) for r in conn.execute(text(f"""
        SELECT a.uri, a.title, a.url,
               COALESCE(a.publication_date, a.submission_date) AS published_at,
               COALESCE(a.social_meta->>'platform',
                        SPLIT_PART(a.news_source, ':', 2),
                        a.news_source) AS platform,
               COALESCE((a.social_meta->>'likes')::numeric, 0)
                 + COALESCE((a.social_meta->>'comments')::numeric, 0)
                 + COALESCE((a.social_meta->>'reposts')::numeric,
                            (a.social_meta->>'shares')::numeric, 0)
                   AS engagement,
               LEFT(COALESCE(a.summary, ''), 600) AS excerpt,
               ma.matched_terms AS matched_terms,
               ma.score AS relevance_score,
               ma.review_reason AS why_relevant,
               -- Which tracked vendors this post names, if any. A post can be
               -- about the market and name none of them.
               COALESCE((
                   SELECT ARRAY_AGG(DISTINCT b.display_name
                                    ORDER BY b.display_name)
                     FROM bw_article_categories bac
                     JOIN bw_brands b ON b.id = bac.brand_id
                     JOIN bw_market_brands mb ON mb.brand_id = b.id
                          AND mb.market_id = :m AND mb.role <> 'excluded'
                    WHERE bac.article_uri = a.uri
               ), ARRAY[]::text[]) AS vendors_mentioned
        {joined}
        ORDER BY COALESCE(a.publication_date, a.submission_date) DESC NULLS LAST,
                 a.uri
        LIMIT :lim OFFSET :off
    """), params).mappings().all()]
    for row in rows:
        row["engagement"] = float(row["engagement"] or 0)

    threshold = _consistent_min()
    metric = mmet.metric(
        "voice_posts",
        label="Posts by this account",
        definition=("Posts by one third-party account that matched this market. "
                    f"An account with fewer than {threshold} relevant posts is "
                    "a breakout post rather than a consistent voice."),
        numerator="matched posts by this account",
        window={"days": days}, value=total,
        collection=mmet.collection_state(conn, market_id, "linkedin_company_post"),
        limitations=[
            "Engagement is as observed when we collected the post, not a final "
            "figure — a post keeps accruing after we read it.",
            "A post can match this market without naming a vendor we track.",
        ])

    return envelope(rows, total=int(total), page=max(1, page), page_size=size,
                    sort="published_at:desc", metric=metric,
                    filters={"author": author, "days": days})


def _consistent_min() -> int:
    from app.services.market_analysis import consistent_voice_min_posts
    return consistent_voice_min_posts()


# ---------------------------------------------------------------------------
# Funding (spec 4.5, 4.7)
# ---------------------------------------------------------------------------

# Crunchbase's raw stage values, grouped and ordered per spec 4.5. Debt and
# grants are kept out of the equity ladder rather than being sorted next to a
# Series C, because presenting a loan as a growth stage misreads the company.
STAGE_GROUPS: List[Tuple[str, Tuple[str, ...]]] = [
    ("Pre-seed", ("pre_seed",)),
    ("Seed", ("seed",)),
    ("Early venture", ("series_a", "series_b")),
    ("Later venture", ("series_c", "series_d", "series_e", "series_f",
                       "series_g", "series_h")),
    ("Growth / private equity", ("private_equity", "corporate_round")),
    ("Debt", ("debt_financing",)),
    ("Grant / non-equity", ("grant", "non_equity_assistance")),
    ("Secondary", ("secondary_market",)),
    ("Public / exit", ("ipo", "post_ipo_equity", "post_ipo_debt",
                       "post_ipo_secondary")),
    ("Other / undisclosed", ("equity_crowdfunding", "funding_round",
                             "series_unknown", "initial_coin_offering", "ico",
                             "undisclosed", "convertible_note")),
]

STAGE_ORDER = [name for name, _ in STAGE_GROUPS]
_STAGE_OF_RAW = {raw: name for name, raws in STAGE_GROUPS for raw in raws}

# Not equity, and the legend has to say so.
NON_EQUITY_GROUPS = frozenset({"Debt", "Grant / non-equity"})


def stage_group(raw: Optional[str]) -> str:
    """Which group a raw Crunchbase stage belongs to.

    Anything unrecognised goes to Other / undisclosed and keeps its raw value in
    the drill-down, rather than being dropped or guessed into a neighbouring
    group.
    """
    if not raw:
        return "Other / undisclosed"
    return _STAGE_OF_RAW.get(str(raw).strip().lower(), "Other / undisclosed")


def funding_vendors(conn, market_id: int, *, stage: Optional[str] = None,
                    disclosure: Optional[str] = None, page: int = 1,
                    page_size: int = DEFAULT_PAGE_SIZE,
                    sort: str = "disclosed:desc") -> Dict[str, Any]:
    """Per vendor funding, each field labelled with where it came from.

    The two figures come from different places and used to be presented as one
    Crunchbase record: the disclosed total is the imported workbook's, while the
    stage, investors and scores are the Crunchbase snapshot's. A reader who
    attributes the total to Crunchbase is being misled by the layout.
    """
    size, offset = _page(page, page_size)

    rows = [dict(r) for r in conn.execute(text("""
        WITH latest AS (
            SELECT DISTINCT ON (s.brand_id) s.brand_id, s.data, s.observed_at
              FROM bw_vendor_snapshots s
              JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                   AND mb.market_id = :m AND mb.role <> 'excluded'
             WHERE s.snapshot_type = 'funding'
             ORDER BY s.brand_id, s.observed_at DESC
        )
        SELECT b.id AS brand_id, b.display_name AS vendor,
               mb.baseline->'metrics'->>'total_funding_musd' AS disclosed_raw,
               mb.baseline->'metrics'->>'funding_status' AS funding_status,
               l.data->>'last_funding_type' AS stage_raw,
               l.data->>'num_funding_rounds' AS rounds,
               l.data->>'growth_score' AS growth_score,
               l.data->>'heat_score' AS heat_score,
               l.data->>'cb_rank' AS cb_rank,
               l.data->'investors' AS investors,
               l.data->'lead_investors' AS lead_investors,
               l.data->>'url' AS crunchbase_url,
               l.observed_at AS crunchbase_read_at
          FROM bw_market_brands mb
          JOIN bw_brands b ON b.id = mb.brand_id
          LEFT JOIN latest l ON l.brand_id = b.id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
         ORDER BY b.display_name
    """), {"m": market_id}).mappings().all()]

    out = []
    for row in rows:
        raw = row.pop("disclosed_raw", None)
        try:
            disclosed = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            disclosed = None
        status = (row.get("funding_status") or "").strip().lower()
        # Three states, not two. "Undisclosed" is a company that chose not to
        # say; "unavailable" is us not having looked or not having found it.
        # Rendering both as 0 put bootstrapped companies and unread ones in the
        # same bucket at the bottom of the chart.
        if disclosed is not None:
            state = "disclosed"
        elif status in ("undisclosed", "bootstrapped", "self-funded"):
            state = "undisclosed"
        else:
            state = "unavailable"

        row["disclosed_total_musd"] = disclosed
        row["disclosure"] = state
        row["stage_group"] = stage_group(row.get("stage_raw"))
        row["is_equity_stage"] = row["stage_group"] not in NON_EQUITY_GROUPS
        # Field-level provenance, because the two halves of this row have
        # different origins and different dates.
        row["sources"] = {
            "disclosed_total_musd": "imported workbook baseline",
            "stage": "Crunchbase (via Bright Data)",
            "investors": "Crunchbase (via Bright Data)",
            "growth_score": "Crunchbase (via Bright Data)",
            "heat_score": "Crunchbase (via Bright Data)",
        }
        for key in ("rounds", "growth_score", "heat_score", "cb_rank"):
            try:
                row[key] = float(row[key]) if row[key] not in (None, "") else None
            except (TypeError, ValueError):
                row[key] = None
        out.append(row)

    if stage:
        out = [r for r in out if r["stage_group"] == stage]
    if disclosure:
        out = [r for r in out if r["disclosure"] == disclosure]

    if sort.startswith("disclosed"):
        out.sort(key=lambda r: (r["disclosed_total_musd"] is None,
                                -(r["disclosed_total_musd"] or 0), r["vendor"]))
        sort = "disclosed:desc"
    else:
        out.sort(key=lambda r: r["vendor"])
        sort = "vendor:asc"

    collection = mmet.collection_state(conn, market_id, "crunchbase_company")
    metric = mmet.metric(
        "vendor_funding",
        label="Vendor funding",
        definition=("Disclosed cumulative funding per vendor with its stage and "
                    "investors. The total comes from the imported workbook; the "
                    "stage, investors and scores come from Crunchbase."),
        numerator="vendors", denominator="vendors in the market",
        collection=collection, value=len(out),
        limitations=[
            "Cumulative total, not a single round. There is no round-level "
            "amount or date, so no 'largest raise' figure can be given.",
            "Undisclosed means the company did not say. Unavailable means we "
            "have not read it. Neither is zero.",
            "Currency conversion is not applied, so totals are only comparable "
            "where the source currency matches.",
        ])

    return envelope(out[offset:offset + size], total=len(out),
                    page=max(1, page), page_size=size, sort=sort,
                    metric=metric,
                    filters={"stage": stage, "disclosure": disclosure})


def _normalize_investor(name: str) -> str:
    """Case, spacing and trailing punctuation only.

    Deliberately not fuzzy. Merging "Accel" with "Accel-KKR" because they look
    alike would invent a portfolio overlap that does not exist, and this figure
    exists to show overlap. Real name variants belong in a reviewed alias table,
    not in a similarity threshold.
    """
    cleaned = re.sub(r"\s+", " ", (name or "").strip())
    cleaned = re.sub(r"[.,]+$", "", cleaned)
    return cleaned.casefold()


def investors(conn, market_id: int, *, min_vendors: int = 2,
              page: int = 1, page_size: int = DEFAULT_PAGE_SIZE
              ) -> Dict[str, Any]:
    """Investors appearing in more than one monitored vendor's record.

    This measures observed portfolio overlap and nothing else. It does not
    establish how much was invested, current ownership, who led a round, or
    whether the investor did well — none of which is in the data.
    """
    size, offset = _page(page, page_size)
    raw = conn.execute(text("""
        WITH latest AS (
            SELECT DISTINCT ON (s.brand_id) s.brand_id, s.data
              FROM bw_vendor_snapshots s
              JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                   AND mb.market_id = :m AND mb.role <> 'excluded'
             WHERE s.snapshot_type = 'funding'
             ORDER BY s.brand_id, s.observed_at DESC
        )
        SELECT l.brand_id, b.display_name AS vendor, inv AS investor,
               l.data->>'url' AS crunchbase_url
          FROM latest l
          JOIN bw_brands b ON b.id = l.brand_id,
               JSONB_ARRAY_ELEMENTS_TEXT(
                   CASE WHEN JSONB_TYPEOF(l.data->'investors') = 'array'
                        THEN l.data->'investors' ELSE '[]'::jsonb END) AS inv
    """), {"m": market_id}).mappings().all()

    grouped: Dict[str, Dict[str, Any]] = {}
    for row in raw:
        key = _normalize_investor(row["investor"])
        if not key:
            continue
        entry = grouped.setdefault(key, {
            "investor": row["investor"].strip(),
            "normalized": key, "forms": set(), "vendors": [],
        })
        entry["forms"].add(row["investor"].strip())
        if not any(v["brand_id"] == row["brand_id"] for v in entry["vendors"]):
            entry["vendors"].append({
                "brand_id": row["brand_id"], "vendor": row["vendor"],
                "evidence_url": row["crunchbase_url"],
            })

    out = []
    for entry in grouped.values():
        if len(entry["vendors"]) < min_vendors:
            continue
        entry["forms"] = sorted(entry["forms"])
        entry["vendor_count"] = len(entry["vendors"])
        entry["vendors"].sort(key=lambda v: v["vendor"])
        # Only worth surfacing when the same investor was written two ways;
        # otherwise it is noise on every row.
        if len(entry["forms"]) < 2:
            entry.pop("forms")
        out.append(entry)
    out.sort(key=lambda e: (-e["vendor_count"], e["investor"].casefold()))

    collection = mmet.collection_state(conn, market_id, "crunchbase_company")
    cov = collection["coverage"]
    limitations = [
        "Portfolio overlap only. It does not show amount invested, current "
        "ownership, who led a round, or investment performance.",
        "Names are matched on case, spacing and trailing punctuation. Genuine "
        "variants of one name are not merged automatically, because a "
        "similarity guess would invent an overlap.",
    ]
    if cov.get("eligible") and cov["successful"] < cov["eligible"]:
        # The honest caveat, and the reason this figure is currently near-empty.
        limitations.insert(0, (
            f"Only {cov['successful']} of {cov['eligible']} vendors with a "
            "Crunchbase page have been read, so an investor can appear to back "
            "one vendor when it backs several."))

    metric = mmet.metric(
        "shared_investors",
        label="Investors backing more than one vendor",
        definition=("A normalized investor name appearing in the latest "
                    "Crunchbase investor records for two or more monitored "
                    "vendors."),
        numerator="investors", denominator="vendors read from Crunchbase",
        collection=collection, value=len(out), limitations=limitations)

    return envelope(out[offset:offset + size], total=len(out),
                    page=max(1, page), page_size=size,
                    sort="vendor_count:desc", metric=metric,
                    filters={"min_vendors": min_vendors})


def investor_vendors(conn, market_id: int, investor: str) -> Dict[str, Any]:
    """Every monitored vendor whose record names one investor."""
    listing = investors(conn, market_id, min_vendors=1, page=1,
                        page_size=MAX_PAGE_SIZE)
    target = _normalize_investor(investor)
    match = next((e for e in listing["data"]
                  if e["normalized"] == target), None)
    if match is None:
        return envelope([], total=0, page=1, page_size=DEFAULT_PAGE_SIZE,
                        sort="vendor:asc",
                        filters={"investor": investor},
                        metric=listing["meta"]["metric"])
    return envelope(match["vendors"], total=len(match["vendors"]), page=1,
                    page_size=MAX_PAGE_SIZE, sort="vendor:asc",
                    metric=listing["meta"]["metric"],
                    filters={"investor": match["investor"]},
                    notes=([f"Also written as: {', '.join(match['forms'])}"]
                           if match.get("forms") else []))


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def csv_of(rows: List[Dict[str, Any]]) -> str:
    """A CSV of whatever the list returned.

    Uses the same rows the JSON did, so an export cannot disagree with the
    screen. Nested values are JSON-encoded rather than flattened, because
    flattening a list of investors into a cell silently loses the ones past the
    first.
    """
    import csv
    import io
    import json

    if not rows:
        return ""
    columns = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
            for k, v in row.items() if k in columns})
    return buf.getvalue()
