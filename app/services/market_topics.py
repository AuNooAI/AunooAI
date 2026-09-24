"""What a market's coverage is about right now, and what is rising.

The front page shows two short lists. "Being discussed" is the subjects with
the most articles in the last 7 days. "Emerging" is the subjects whose
coverage is concentrated in those 7 days against the last 30, so a subject
that was quiet all month and busy this week rises to the top even when its
total is small.

Both come from one daily run: the market's matched corpus for the last 30
days, as a numbered list of headlines, goes to a cheap model once, and the
model groups them into subjects — an event, a company action, a product, a
report or a question that several headlines are about — and names each.
The counts are arithmetic over the members it returns; the model cannot
add an article, only choose which listed headlines belong together, and a
member number it invents is dropped.

Why a model and not k-means over the stored embedding (the first version,
6 Sep 2026): the embedding was trained for relevance, and on this corpus
it groups by surface form — one Reddit thread style, one X account's
replies, Unicode-bold LinkedIn posts, Turkish — not by subject. Centring,
title-only vectors and a cohesion gate were all tried the same day and
each made the lists worse for a reader. Headlines to a model found the
7AI round, Fal.Con and the Cribl acquisition first time.

Each run is self-contained. The emerging signal is the date distribution
inside one run, so nothing matches subjects across runs and nothing
should: a subject's id is only stable inside the row it is stored in.
"""

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

WINDOW_DAYS = 30        # the corpus window that is grouped
RECENT_DAYS = 7         # "this week" for both panels
CORPUS_LIMIT = 600      # newest N matched articles in the window
MIN_ARTICLES = 24       # fewer than this and nothing is stored; the panel hides
MIN_CLUSTER = 3         # a subject needs this many headlines
MIN_RECENT = 3          # and this many this week to be listed
MIN_RISE = 1.3          # Emerging: at least 1.3x the corpus's own share of recent articles
RISE_PRIOR = 2.0        # pseudo-counts so a 3-of-3 subject does not read as 5x
PANEL_SIZE = 5
MAX_SUBJECTS = 20       # what the model is asked for, at most
SAMPLE_TITLES = 5       # newest members kept as a sample in the stored row
GROUPING_MAX_TOKENS = 12000
# One call's idea of "a subject" drifts: the same 600 headlines gave 6, 8,
# 12, 14 and 18 subjects on 6 Sep. Two samples, keeping the one with more
# subjects that qualify for the lists, steadies the day-to-day count for
# the price of one extra cheap call.
GROUPING_SAMPLES = 2
HEADLINE_CHARS = 160

# Kimi K2.5 on Bedrock: the same cheap model the briefing and themes use.
DEFAULT_MODEL = os.getenv("MARKET_TOPICS_MODEL", "bedrock-kimi-k2-5")


class GroupingFailed(RuntimeError):
    """The model did not return usable subjects after two attempts."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


_HANDLE_PREFIX = re.compile(r"^@[\w.-]+:\s*")
_VENDOR_PREFIX = re.compile(r"^[A-Z][\w .&,'’-]{1,40}:\s+(?=\S)")


def clean_headline(title: Optional[str]) -> str:
    """The headline without the "@handle: " or "Vendor: " prefix the
    collectors add, on one line, cut to HEADLINE_CHARS."""
    t = " ".join((title or "").split())
    t = _HANDLE_PREFIX.sub("", t)
    t = _VENDOR_PREFIX.sub("", t)
    return t.strip()[:HEADLINE_CHARS]


# ---------------------------------------------------------------------------
# Gathering (sync, no model call)
# ---------------------------------------------------------------------------

def compute(conn, market: Dict[str, Any]) -> Dict[str, Any]:
    """The numbered headline list the model will group, plus the corpus
    facts the ranking needs. ``items`` is dropped before storing."""
    from app.services import market_corpus as mcorp

    market_id = int(market["id"])
    rows = mcorp.articles(conn, market_id, limit=CORPUS_LIMIT, days=WINDOW_DAYS,
                          require_signal_for_social=True)
    base = {"market_id": market_id, "market": market.get("name"),
            "computed_at": _now().isoformat(), "window_days": WINDOW_DAYS,
            "recent_days": RECENT_DAYS, "model": None,
            "being_discussed": [], "emerging": [], "clusters": [], "items": []}
    # Noise never names a subject: six $MASK penny-stock posts about an "Edge
    # AI SoC" chip were the second most-discussed subject on 23 September.
    from app.services.market_assessment import record_is_noise
    items = [r for r in rows
             if clean_headline(r.get("title")) and not record_is_noise(r)]
    if len(items) < MIN_ARTICLES:
        return {**base, "n": len(items), "k": 0,
                "reason": f"only {len(items)} matched articles with a headline; "
                          f"need {MIN_ARTICLES}"}
    recent_since = mcorp._iso_days_ago(RECENT_DAYS)
    corpus_recent = sum(1 for r in items if (r.get("published") or "") >= recent_since)
    # The corpus's own recent share is the baseline, not 7/30. Matching lags
    # publication by days, so the newest week always under-reads; a baseline
    # measured the same way cancels that out.
    return {**base, "n": len(items), "k": 0, "recent_since": recent_since,
            "corpus_recent": corpus_recent,
            "corpus_recent_share": round(corpus_recent / len(items), 4),
            "items": items}


# ---------------------------------------------------------------------------
# Grouping and naming: one model call
# ---------------------------------------------------------------------------

def _grouping_prompt(result: Dict[str, Any], market_name: str) -> str:
    lines = []
    for i, r in enumerate(result["items"], 1):
        kind = r.get("article_class") or "news"
        lines.append(f"{i}. [{(r.get('published') or '')[:10]}] [{kind}] "
                     f"{clean_headline(r.get('title'))}")
    return (f"Below are {len(lines)} headlines from {market_name} coverage in the last "
            f"{result['window_days']} days, one per line: number, date, kind, headline.\n"
            "Group them into subjects. A subject is one specific thing several headlines "
            "are about: an event (a conference, a funding round, an acquisition), a "
            "company's action, a product or launch, a published report or guide, or one "
            "question people are arguing about.\n"
            "Rules:\n"
            f"- A subject needs at least {MIN_CLUSTER} headlines. Aim for 10 to {MAX_SUBJECTS} "
            "subjects: a month of coverage of this size nearly always holds that many. Once "
            "three headlines share a specific thing (a launch, a report, a partnership, an "
            "award, an acquisition, a funding round, a conference), that is a subject; do "
            "not stop at the biggest few.\n"
            "- A headline belongs to at most one subject.\n"
            "- Leave out headlines that are not about a specific subject: general "
            "commentary, job adverts, stock tickers, welcome-to-the-team posts, and "
            "anything off the market's topic. Do not force them into a subject.\n"
            "- Do not make a subject out of one author's output unless the headlines "
            "are about the same specific thing.\n"
            "- A theme is not a subject. \"Discussions on alert fatigue\" or \"Commentary "
            "on agentic SOCs\" groups opinions, not a thing that happened; leave those "
            "headlines out.\n"
            f"- Every subject is about {market_name}, so a name that restates the market "
            "tells the reader nothing. Name the specific event, company, product, report "
            "or question, in 3-8 words. No two names alike.\n"
            "- One plain sentence per subject saying what is being reported, from the "
            "headlines only. Do not invent a company, product or event.\n"
            "Reply with JSON only, in this shape and nothing else:\n"
            '{"subjects": [{"name": "...", "summary": "...", "members": [12, 40, 41]}]}\n\n'
            + "\n".join(lines))


def _parse_subjects(raw: str, n_items: int) -> List[Dict[str, Any]]:
    from app.ai_models import extract_json_response

    parsed = extract_json_response(raw)
    if isinstance(parsed, dict):
        parsed = parsed.get("subjects") or parsed.get("groups") or parsed.get("topics")
    if not isinstance(parsed, list):
        raise ValueError("model returned no subjects list")
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:60]
        members: List[int] = []
        for m in item.get("members") or []:
            try:
                idx = int(m)
            except (TypeError, ValueError):
                continue
            # A number the model invented, or one already used, is dropped:
            # the first subject to claim a headline keeps it.
            if 1 <= idx <= n_items and idx not in seen:
                seen.add(idx)
                members.append(idx)
        if name and len(members) >= MIN_CLUSTER:
            out.append({"name": name,
                        "summary": str(item.get("summary") or "").strip()[:200] or None,
                        "members": members})
    return out


def _build_clusters(result: Dict[str, Any], subjects: List[Dict[str, Any]]) -> None:
    items = result["items"]
    recent_since = result["recent_since"]
    share = float(result.get("corpus_recent_share") or 0)
    clusters: List[Dict[str, Any]] = []
    for s in subjects:
        members = [items[i - 1] for i in s["members"]]
        members.sort(key=lambda r: r.get("published") or "", reverse=True)
        n_total = len(members)
        n_recent = sum(1 for m in members if (m.get("published") or "") >= recent_since)
        rise = (((n_recent + RISE_PRIOR * share) / (n_total + RISE_PRIOR)) / share
                if share > 0 else 0.0)
        vendor_counts: Counter = Counter()
        vendor_ids: Dict[str, Any] = {}
        for m in members:
            for v in m.get("vendors") or []:
                vendor_counts[v["vendor"]] += 1
                vendor_ids.setdefault(v["vendor"], v.get("brand_id"))
        source_counts: Counter = Counter(
            m.get("news_source") for m in members if m.get("news_source"))
        clusters.append({
            "id": 0, "name": s["name"], "summary": s.get("summary"),
            "n_total": n_total, "n_recent": n_recent, "n_prior": n_total - n_recent,
            "recent_share": round(n_recent / n_total, 4), "rise": round(rise, 3),
            "top_vendors": [{"brand_id": vendor_ids.get(v), "vendor": v, "n": n}
                            for v, n in vendor_counts.most_common(5)],
            "top_sources": [{"source": src, "n": n} for src, n in source_counts.most_common(3)],
            "sample": [{"uri": m["uri"], "title": m.get("title"),
                        "source": m.get("news_source"), "published": m.get("published")}
                       for m in members[:SAMPLE_TITLES]],
            "uris": [m["uri"] for m in members],
        })
    clusters.sort(key=lambda c: (-c["n_recent"], -c["n_total"]))
    for i, c in enumerate(clusters):
        c["id"] = i
    result["clusters"] = clusters
    result["k"] = len(clusters)
    result["assigned"] = sum(c["n_total"] for c in clusters)


async def group(result: Dict[str, Any], market_name: str,
                model: Optional[str] = None) -> Dict[str, Any]:
    """One model call that groups the headlines into named subjects and
    fills ``result["clusters"]``. Raises GroupingFailed after two attempts.

    Deliberately not vector_routes._generate_report_with_retry: that helper
    rejects a reply containing severity words, and a security market's
    subjects are full of them ("critical", "breach", "severe").
    """
    import litellm

    from app.ai_models import resolve_litellm_call_params

    items = result.get("items") or []
    if not items:
        return result
    model = model or DEFAULT_MODEL
    messages = [
        {"role": "system",
         "content": "You group news headlines into specific subjects and name them from "
                    "the headlines alone, never inventing a company, product or event "
                    "they do not support. Reply with JSON only."},
        {"role": "user", "content": _grouping_prompt(result, market_name)},
    ]
    last_error: Optional[Exception] = None
    best: Optional[List[Dict[str, Any]]] = None
    best_key = (-1, -1)
    samples = 0
    # GROUPING_SAMPLES good replies, with one spare attempt for a bad one.
    for attempt in range(1, GROUPING_SAMPLES + 2):
        if samples >= GROUPING_SAMPLES:
            break
        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(model), messages=messages,
                max_tokens=GROUPING_MAX_TOKENS)
            raw = (response.choices[0].message.content or "").strip()
            if not raw:
                raise ValueError("empty reply")
            subjects = _parse_subjects(raw, len(items))
            if not subjects:
                raise ValueError("no subjects with enough members in reply")
        except Exception as exc:  # empty Bedrock reply, truncated JSON, transport
            last_error = exc
            logger.warning("market topics: grouping attempt %d failed: %s", attempt, exc)
            continue
        samples += 1
        trial = dict(result)
        _build_clusters(trial, subjects)
        listable = sum(1 for c in trial["clusters"] if c["n_recent"] >= MIN_RECENT)
        key = (listable, trial["assigned"])
        logger.info("market topics: sample %d: %d subjects, %d listable, %d assigned",
                    attempt, len(subjects), listable, trial["assigned"])
        if key > best_key:
            best, best_key = subjects, key
    if best is None:
        raise GroupingFailed(str(last_error))
    result["model"] = model
    _build_clusters(result, best)
    return result


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank(result: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the two lists. Pure: reads the clusters, writes two id lists."""
    eligible = [c for c in result.get("clusters") or []
                if c.get("name") and int(c.get("n_recent") or 0) >= MIN_RECENT]
    discussed = sorted(eligible, key=lambda c: (-c["n_recent"], -c["n_total"]))[:PANEL_SIZE]
    taken = {c["id"] for c in discussed}
    rising = sorted((c for c in eligible if float(c.get("rise") or 0) >= MIN_RISE),
                    key=lambda c: -float(c["rise"]))
    # A subject already in Being discussed is not repeated here; its rise
    # shows on that row instead. Emerging can be empty, and the card then
    # shows one list.
    emerging = [c for c in rising if c["id"] not in taken][:PANEL_SIZE]
    result["being_discussed"] = [c["id"] for c in discussed]
    result["emerging"] = [c["id"] for c in emerging]
    return result


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def store(conn, result: Dict[str, Any]) -> int:
    payload = {k: v for k, v in result.items() if k != "items"}
    row_id = conn.execute(text("""
        INSERT INTO bw_market_topics (market_id, computed_at, window_days, recent_days,
                                      n_articles, k, model, result)
        VALUES (:m, :at, :w, :r, :n, :k, :model, CAST(:res AS JSONB))
        RETURNING id
    """), {"m": result["market_id"], "at": result["computed_at"],
           "w": result["window_days"], "r": result["recent_days"],
           "n": result.get("n") or 0, "k": result.get("k") or 0,
           "model": result.get("model"), "res": json.dumps(payload)}).scalar()
    conn.commit()
    return int(row_id)


def latest(conn, market_id: int) -> Optional[Dict[str, Any]]:
    """The newest stored run, or None."""
    row = conn.execute(text("""
        SELECT id, computed_at, result FROM bw_market_topics
         WHERE market_id = :m ORDER BY computed_at DESC LIMIT 1
    """), {"m": market_id}).mappings().first()
    if not row:
        return None
    result = dict(row["result"] or {})
    result["id"] = row["id"]
    result["computed_at"] = (row["computed_at"].isoformat()
                             if hasattr(row["computed_at"], "isoformat")
                             else str(row["computed_at"]))
    return result


def topic_by_id(result: Optional[Dict[str, Any]], topic_id: int) -> Optional[Dict[str, Any]]:
    for c in (result or {}).get("clusters") or []:
        if int(c.get("id", -1)) == int(topic_id):
            return c
    return None


def listed(result: Optional[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """The two panels as cluster dicts, in display order."""
    if not result:
        return {"being_discussed": [], "emerging": []}
    by_id = {c["id"]: c for c in result.get("clusters") or []}
    return {key: [by_id[i] for i in result.get(key) or [] if i in by_id]
            for key in ("being_discussed", "emerging")}
