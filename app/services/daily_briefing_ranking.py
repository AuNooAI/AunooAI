"""Deterministic relevance-first ranking for the Briefing Desk compose flow.

Everything here is pure: no database, no LLM, no clock unless you pass one in.
That is deliberate — the compose pipeline's selection quality is the thing that
kept going wrong, and it can only be pinned down by tests if the scoring,
deduplication and shortlist rules are separable from the I/O around them.

What it replaces: the old flow sorted every candidate by publication date, so
the newest row won regardless of whether it was on topic. A Bluesky post about
a city council election, scored 0.00 against "Brand Monitoring Pearsons
Education", was the top candidate the curator saw. Here, topic alignment
carries half the composite score and recency carries a tenth of it.

The three stages a candidate passes through:

  1. ``score_article`` turns a row into a composite score plus the component
     breakdown that explains it.
  2. ``dedupe_candidates`` collapses the same story arriving under several
     URLs, titles or outlets into one candidate that remembers every topic it
     matched.
  3. ``build_shortlist`` fills the curator's slots by rotating through the
     requested topics, so a high-volume topic cannot take every slot, and
     defers rather than discards candidates that break the per-source cap.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# Tunables — named on purpose, so a change is a reviewable diff and not a
# number buried in a sort key.
# --------------------------------------------------------------------------

#: Component weights for the composite score. They sum to 1.0.
#:
#: NOTE on ``quality``: on every tenant inspected so far ``articles.quality_score``
#: is a constant 0.8 wherever it is set at all, so its weight currently acts as a
#: flat bonus for "the analyzer filled this in" rather than a quality signal.
#: It is kept at the spec's weight rather than silently zeroed; drop it to 0.0
#: and give the 0.10 to alignment if that stays true.
WEIGHTS: Dict[str, float] = {
    "alignment": 0.50,
    "keyword": 0.15,
    "quality": 0.10,
    "confidence": 0.10,
    "credibility": 0.05,
    "recency": 0.10,
}

#: Days for the recency component to halve. Recency is a freshness nudge and a
#: tie-breaker, never the primary sort key.
RECENCY_HALF_LIFE_DAYS = 3.0

#: Bounded adjustment applied after the base score for an explicit reader
#: preference on the article's source. Small enough that it reorders near-equals
#: and nothing else.
USER_PREFERENCE_BOOST = 0.05

#: Standalone articles from one source in the final briefing, before the
#: material-gap override below applies.
MAX_PER_SOURCE = 3

#: A candidate over the per-source cap may still be taken when every remaining
#: under-cap alternative is worse by more than this much composite score. Set
#: from the observed spread: on-topic candidates cluster within ~0.05 of each
#: other, so 0.15 only fires when the alternative is genuinely weaker.
SOURCE_CAP_OVERRIDE_GAP = 0.15

#: Token containment above which two titles are treated as the same story.
#: Deliberately high — merging two distinct developments is a worse failure
#: than showing both.
TITLE_SIMILARITY_THRESHOLD = 0.85

#: Titles shorter than this (in significant tokens) are never merged by
#: similarity, only by exact normalized equality. Short titles share generic
#: words too easily.
MIN_TOKENS_FOR_SIMILARITY = 5

#: Two titles are only compared when the shorter has at least this share of the
#: longer's token count. Without it a short generic headline fully contained in
#: a long unrelated one would merge on containment alone.
MIN_TITLE_LENGTH_RATIO = 0.5

#: Credibility strings mapped to a 0..1 contribution. Anything unrecognised
#: contributes zero — unknown credibility is not a reason to reject.
CREDIBILITY_SCORES: Dict[str, float] = {
    "very high": 1.0,
    "high": 1.0,
    "high credibility": 1.0,
    "mostly factual": 0.75,
    "medium": 0.5,
    "medium credibility": 0.5,
    "mixed": 0.5,
    "low": 0.2,
    "low credibility": 0.2,
    "very low": 0.0,
}

#: Query parameters stripped before comparing URLs. Syndication feeds bolt
#: these on, so two copies of one story differ only by campaign tracking.
_TRACKING_PARAMS = re.compile(
    r"(^|&)(utm_[^=&]*|partner|fbclid|gclid|mc_cid|mc_eid|ref|ref_src|source|"
    r"campaign|cmpid|smid|guccounter)=[^&]*",
    re.IGNORECASE,
)

#: Dropped before comparing titles — outlet suffixes and the "(source, date)"
#: tail the newsfeed appends to some rows.
_TITLE_NOISE = re.compile(r"\s*[\(\[][^\)\]]*\d{4}-\d{2}-\d{2}[^\)\]]*[\)\]]\s*$")

_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the "
    "to was were will with new says say said after over into amid".split()
)


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

def clamp01(value: float) -> float:
    """Pin a float into 0..1. Guards against a score stored out of range."""
    if value != value:  # NaN
        return 0.0
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def normalize_score(value: Any) -> Optional[float]:
    """A stored score as a 0..1 float, or None when there is nothing usable.

    Accepts the 0..100 form as well, because a couple of enrichment paths in
    this codebase write percentages. Returns None rather than a neutral value:
    a missing signal must contribute zero, not a made-up average.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    if f > 1.0:
        f = f / 100.0
    return clamp01(f)


def parse_publication_time(value: Any) -> Optional[datetime]:
    """Parse ``publication_date`` (stored as TEXT) into an aware UTC datetime.

    Handles the ISO shapes present in the table — with offset, with 'Z', naive,
    and bare ``YYYY-MM-DD`` — and returns None for anything else. A row that
    cannot be parsed gets no freshness credit rather than crashing the sort.
    """
    if isinstance(value, datetime):
        dt = value
    else:
        if not value:
            return None
        s = str(value).strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
            if not m:
                return None
            try:
                dt = datetime.fromisoformat(m.group(1))
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def recency_score(
    published: Optional[datetime],
    now: datetime,
    half_life_days: float = RECENCY_HALF_LIFE_DAYS,
) -> float:
    """Exponential freshness decay: 1.0 at publication, 0.5 one half-life later.

    An unparseable or missing date scores 0.0 — no artificial advantage. A date
    in the future is treated as "just now" rather than scoring above 1.0.
    """
    if published is None:
        return 0.0
    age_days = (now - published).total_seconds() / 86400.0
    if age_days <= 0:
        return 1.0
    if half_life_days <= 0:
        return 0.0
    return clamp01(math.pow(0.5, age_days / half_life_days))


def credibility_score(row: Dict[str, Any]) -> Optional[float]:
    """Best available source-credibility contribution, or None when unrated.

    Both ``mbfc_credibility_rating`` and ``factual_reporting`` are consulted and
    the better of the two is used, since a given outlet often carries only one.
    """
    best: Optional[float] = None
    for field in ("mbfc_credibility_rating", "factual_reporting"):
        raw = row.get(field)
        if not raw:
            continue
        mapped = CREDIBILITY_SCORES.get(str(raw).strip().lower())
        if mapped is None:
            continue
        best = mapped if best is None else max(best, mapped)
    return best


def normalize_uri(value: Any) -> str:
    """A URL reduced to what identifies the story: scheme, host and path.

    Drops the scheme, a leading ``www.``, tracking parameters, the fragment and
    a trailing slash, so the same article syndicated with campaign tags
    collapses to one key.
    """
    if not value:
        return ""
    s = str(value).strip()
    s = s.split("#", 1)[0]
    s = re.sub(r"^https?://", "", s, flags=re.IGNORECASE)
    if "?" in s:
        path, _, query = s.partition("?")
        query = _TRACKING_PARAMS.sub("", query).lstrip("&")
        s = f"{path}?{query}" if query else path
    s = re.sub(r"^www\.", "", s, flags=re.IGNORECASE)
    return s.rstrip("/").lower()


def normalize_title(value: Any) -> str:
    """A title reduced for equality comparison: no punctuation, no case, no
    trailing "(outlet, 2026-08-18)" tail, single-spaced."""
    if not value:
        return ""
    s = _TITLE_NOISE.sub("", str(value))
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _title_tokens(title: str) -> frozenset:
    return frozenset(t for t in normalize_title(title).split() if t not in _STOPWORDS)


def title_similarity(a: Any, b: Any) -> float:
    """How much of the shorter title's meaning the longer one contains, 0..1.

    Containment rather than Jaccard, because a syndicated rewrite keeps the
    substance and changes the framing: "Concentric AI unveils new feature for
    sensitive data discovery" and "Concentric AI's new feature expands
    sensitive data discovery" share seven of eight significant tokens but score
    only 0.70 on Jaccard, under any threshold safe enough to use.

    Returns 0.0 when either title is too short to judge, or when one is more
    than twice the length of the other — both are cases where a high score
    would say more about generic words than about the story.
    """
    ta, tb = _title_tokens(a), _title_tokens(b)
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(shorter) < MIN_TOKENS_FOR_SIMILARITY:
        return 0.0
    if len(shorter) / len(longer) < MIN_TITLE_LENGTH_RATIO:
        return 0.0
    return len(shorter & longer) / len(shorter)


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def score_article(
    row: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    weights: Optional[Dict[str, float]] = None,
    half_life_days: float = RECENCY_HALF_LIFE_DAYS,
) -> Dict[str, Any]:
    """Composite relevance score for one candidate row, with its breakdown.

    Returns ``{"composite": float, "components": {...}, "published": datetime|None}``.
    Every component is 0..1; a component with no underlying signal is 0.0, so a
    row missing optional enrichment simply forgoes that share of the score.
    """
    w = weights or WEIGHTS
    now = now or datetime.now(timezone.utc)
    published = parse_publication_time(row.get("publication_date"))

    components = {
        "alignment": normalize_score(row.get("topic_alignment_score")) or 0.0,
        "keyword": normalize_score(row.get("keyword_relevance_score")) or 0.0,
        "quality": normalize_score(row.get("quality_score")) or 0.0,
        "confidence": normalize_score(row.get("confidence_score")) or 0.0,
        "credibility": credibility_score(row) or 0.0,
        "recency": recency_score(published, now, half_life_days),
    }
    composite = sum(w.get(k, 0.0) * v for k, v in components.items())

    preference = str(row.get("user_preference") or "").strip().lower()
    if preference == "more":
        composite += USER_PREFERENCE_BOOST
    elif preference == "less":
        composite -= USER_PREFERENCE_BOOST
    components["preference"] = (
        USER_PREFERENCE_BOOST if preference == "more"
        else -USER_PREFERENCE_BOOST if preference == "less" else 0.0
    )

    return {
        "composite": clamp01(composite),
        "components": components,
        "published": published,
    }


def annotate_candidates(
    rows: Iterable[Dict[str, Any]],
    *,
    topic: Optional[str] = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Attach scores and bookkeeping fields to raw candidate rows.

    The added keys are underscore-prefixed so they never collide with a column
    name and are easy to strip before anything is stored.
    """
    now = now or datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        scored = score_article(row, now=now)
        row["_score"] = scored["composite"]
        row["_components"] = scored["components"]
        row["_published"] = scored["published"]
        row["_norm_uri"] = normalize_uri(row.get("canonical_url") or row.get("uri"))
        row["_norm_title"] = normalize_title(row.get("title"))
        if topic:
            row["_topic"] = topic
            row["_topics"] = [topic]
            row["_topic_scores"] = {topic: row["_score"]}
        else:
            row.setdefault("_topics", [])
            row.setdefault("_topic_scores", {})
        out.append(row)
    return out


def sort_key(row: Dict[str, Any]) -> Tuple[float, float, float, str]:
    """Stable ordering: composite desc, alignment desc, published desc, uri asc.

    The final URI term makes the order total, so two runs over identical data
    produce identical briefings.
    """
    published = row.get("_published")
    ts = published.timestamp() if published else float("-inf")
    alignment = normalize_score(row.get("topic_alignment_score")) or 0.0
    return (-float(row.get("_score") or 0.0), -alignment, -ts, str(row.get("uri") or ""))


def rank(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Candidates in deterministic relevance order."""
    return sorted(rows, key=sort_key)


# --------------------------------------------------------------------------
# Story deduplication
# --------------------------------------------------------------------------

def _merge_into(keeper: Dict[str, Any], other: Dict[str, Any]) -> None:
    """Fold ``other``'s topic membership into ``keeper`` and record the drop."""
    for t in other.get("_topics") or []:
        if t not in keeper.setdefault("_topics", []):
            keeper["_topics"].append(t)
    for t, s in (other.get("_topic_scores") or {}).items():
        best = keeper.setdefault("_topic_scores", {})
        if s > best.get(t, -1.0):
            best[t] = s
    keeper.setdefault("_merged_uris", [])
    other_uri = other.get("uri")
    if other_uri and other_uri != keeper.get("uri"):
        keeper["_merged_uris"].append(other_uri)


def _prefer(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(keeper, dropped) for a duplicate pair.

    Composite score decides. When the two are effectively tied the better-rated
    source wins, so a syndicated copy on a wire aggregator yields to the outlet
    that carries a credibility rating.
    """
    sa, sb = float(a.get("_score") or 0.0), float(b.get("_score") or 0.0)
    if abs(sa - sb) < 1e-6:
        ca = credibility_score(a) or 0.0
        cb = credibility_score(b) or 0.0
        if cb > ca:
            return b, a
        if ca > cb:
            return a, b
        return (a, b) if sort_key(a) <= sort_key(b) else (b, a)
    return (a, b) if sa > sb else (b, a)


def dedupe_candidates(rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Collapse duplicate stories. Returns (kept, dropped_count).

    Three passes, cheapest first: normalized URL, then normalized title, then a
    conservative token-overlap check for syndicated copies that were retitled.
    The highest-ranked member of each group survives and inherits every topic
    the group matched.
    """
    kept: List[Dict[str, Any]] = []
    by_uri: Dict[str, Dict[str, Any]] = {}
    by_title: Dict[str, Dict[str, Any]] = {}
    dropped = 0

    for row in rank(rows):
        uri_key = row.get("_norm_uri") or ""
        if uri_key and uri_key in by_uri:
            keeper, loser = _prefer(by_uri[uri_key], row)
            _merge_into(keeper, loser)
            if keeper is not by_uri[uri_key]:
                _replace(kept, by_uri[uri_key], keeper, by_uri, by_title)
            dropped += 1
            continue

        title_key = row.get("_norm_title") or ""
        if title_key and title_key in by_title:
            keeper, loser = _prefer(by_title[title_key], row)
            _merge_into(keeper, loser)
            if keeper is not by_title[title_key]:
                _replace(kept, by_title[title_key], keeper, by_uri, by_title)
            dropped += 1
            continue

        match = None
        for existing in kept:
            if title_similarity(row.get("title"), existing.get("title")) >= TITLE_SIMILARITY_THRESHOLD:
                match = existing
                break
        if match is not None:
            keeper, loser = _prefer(match, row)
            _merge_into(keeper, loser)
            if keeper is not match:
                _replace(kept, match, keeper, by_uri, by_title)
            dropped += 1
            continue

        kept.append(row)
        if uri_key:
            by_uri[uri_key] = row
        if title_key:
            by_title[title_key] = row

    return rank(kept), dropped


def _replace(kept, old, new, by_uri, by_title) -> None:
    """Swap a group's representative in place, keeping the lookup maps honest."""
    for i, r in enumerate(kept):
        if r is old:
            kept[i] = new
            break
    else:
        kept.append(new)
    for key in (old.get("_norm_uri"), new.get("_norm_uri")):
        if key:
            by_uri[key] = new
    for key in (old.get("_norm_title"), new.get("_norm_title")):
        if key:
            by_title[key] = new


# --------------------------------------------------------------------------
# Shortlist construction
# --------------------------------------------------------------------------

def _source_of(row: Dict[str, Any]) -> str:
    return str(row.get("news_source") or "").strip().lower()


def build_shortlist(
    ranked_by_topic: Dict[str, List[Dict[str, Any]]],
    *,
    limit: int,
    topic_order: Optional[Sequence[str]] = None,
    max_per_source: int = MAX_PER_SOURCE,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Fill ``limit`` shortlist slots fairly across topics. Returns (shortlist, stats).

    Round-robin through the requested topics so every topic with eligible
    material is represented before any topic gets a second helping — the old
    global sort let one busy topic take every slot. A candidate that would
    breach the per-source cap is *deferred*, not dropped, and a later pass
    spends any unfilled capacity on the deferred candidates in rank order.
    """
    topics = list(topic_order or ranked_by_topic.keys())
    cursors = {t: 0 for t in topics}
    chosen: List[Dict[str, Any]] = []
    chosen_ids: set = set()
    per_source: Dict[str, int] = {}
    deferred: List[Dict[str, Any]] = []
    stats = {"per_topic": {t: 0 for t in topics}, "deferred_for_source": 0, "second_pass": 0}

    def identity(row: Dict[str, Any]) -> str:
        return row.get("_norm_uri") or str(row.get("uri") or id(row))

    def take(row: Dict[str, Any], topic: Optional[str]) -> None:
        chosen.append(row)
        chosen_ids.add(identity(row))
        per_source[_source_of(row)] = per_source.get(_source_of(row), 0) + 1
        if topic:
            stats["per_topic"][topic] = stats["per_topic"].get(topic, 0) + 1

    # Pass 1 — one candidate per topic per round, respecting the source cap.
    progress = True
    while len(chosen) < limit and progress:
        progress = False
        for topic in topics:
            if len(chosen) >= limit:
                break
            rows = ranked_by_topic.get(topic) or []
            while cursors[topic] < len(rows):
                row = rows[cursors[topic]]
                cursors[topic] += 1
                if identity(row) in chosen_ids:
                    continue
                if per_source.get(_source_of(row), 0) >= max_per_source:
                    deferred.append(row)
                    stats["deferred_for_source"] += 1
                    continue
                take(row, topic)
                progress = True
                break

    # Pass 2 — spend leftover capacity on the deferred high scorers, cap lifted
    # because the alternative is shipping a shorter, weaker shortlist.
    if len(chosen) < limit and deferred:
        for row in rank(deferred):
            if len(chosen) >= limit:
                break
            if identity(row) in chosen_ids:
                continue
            take(row, (row.get("_topics") or [None])[0])
            stats["second_pass"] += 1

    stats["selected"] = len(chosen)
    return chosen, stats


def backfill(
    selected: Sequence[Dict[str, Any]],
    pool: Sequence[Dict[str, Any]],
    *,
    target: int,
    topics: Optional[Sequence[str]] = None,
    max_per_source: int = MAX_PER_SOURCE,
    override_gap: float = SOURCE_CAP_OVERRIDE_GAP,
) -> List[Dict[str, Any]]:
    """Best remaining candidates to bring ``selected`` up to ``target``.

    When ``topics`` is given and there is room for one article per topic, a
    coverage pass runs first: each requested topic with an eligible candidate
    and no representative yet contributes its best one. Otherwise a briefing
    built from eight topics could end up covering three of them.

    Source diversity is then enforced, with one documented escape: when the best
    under-cap candidate is worse than the best over-cap one by more than
    ``override_gap``, the cap yields. Diversity is there to stop one outlet
    dominating a briefing, not to justify swapping a strong story for a weak one.
    """
    chosen_ids = {r.get("_norm_uri") or str(r.get("uri")) for r in selected}
    per_source: Dict[str, int] = {}
    covered: set = set()
    for r in selected:
        per_source[_source_of(r)] = per_source.get(_source_of(r), 0) + 1
        covered.update(r.get("_topics") or [])

    remaining = [r for r in rank(pool)
                 if (r.get("_norm_uri") or str(r.get("uri"))) not in chosen_ids]
    added: List[Dict[str, Any]] = []

    if topics and len(topics) <= target:
        for topic in topics:
            if topic in covered or len(selected) + len(added) >= target:
                continue
            best = next((r for r in remaining if topic in (r.get("_topics") or [])), None)
            if best is None:
                continue
            remaining.remove(best)
            added.append(best)
            per_source[_source_of(best)] = per_source.get(_source_of(best), 0) + 1
            covered.update(best.get("_topics") or [])

    while len(selected) + len(added) < target and remaining:
        under = next((r for r in remaining if per_source.get(_source_of(r), 0) < max_per_source), None)
        over = remaining[0] if remaining[0] is not under else None
        pick = under
        if under is None:
            pick = remaining[0]
        elif over is not None and float(over.get("_score") or 0.0) - float(under.get("_score") or 0.0) > override_gap:
            pick = over
        remaining.remove(pick)
        added.append(pick)
        per_source[_source_of(pick)] = per_source.get(_source_of(pick), 0) + 1

    return added
