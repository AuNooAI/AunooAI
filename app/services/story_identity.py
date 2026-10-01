"""Is this article a copy of one we already hold, and is it a press release?

Until October 2026 the only duplicate check at insert was an exact URL match,
and the only thing that kept an article out of the feeds was the topic
relevance score. So the same story reached a topic feed several times (a
tracking parameter on the URL, a second slug, a syndicated copy on another
outlet), and paid press-release wires counted as news because a market
report about batteries is about batteries. On bugfixing, 7% of readable
articles over 30 days repeated a title already in the same topic; on
wileytest 11%, and 6.7% came from a press-release wire.

Nothing here deletes or blocks a row. Ingest records three facts and the
readers in ``article_visibility`` act on them:

- ``url_key``: the URL reduced to what identifies the article, so a copy that
  differs only by tracking parameters is the same row.
- ``duplicate_of``: the URI of the first copy we saw of the same story in the
  same topic. The number of outlets carrying a story is information in its
  own right (AP stories reach 29 outlets), so copies are kept and counted.
- ``source_type``: ``news`` or ``press_release``.

Spec: docs/INGEST_DUPLICATES_AND_PRESS_RELEASES_SPEC.md
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional, Set

from functools import lru_cache

from app.services.daily_briefing_ranking import (
    MIN_TITLE_LENGTH_RATIO,
    MIN_TOKENS_FOR_SIMILARITY,
    TITLE_SIMILARITY_THRESHOLD,
    _title_tokens,
    normalize_title,
    normalize_uri,
)
try:
    from app.services.report_corpus import is_wire_host
except ImportError:
    # Sites whose report_corpus predates is_wire_host (wiley, wileytest as of
    # October 2026): the same check over their wire list, plus menafn, which
    # bugfixing's list carries, so every site labels the same way.
    from app.services.report_corpus import wire_sources as _wire_sources

    def is_wire_host(host: str) -> bool:
        h = (host or "").strip().lower()
        if h.startswith("www."):
            h = h[4:]
        if not h:
            return False
        for wire in set(_wire_sources()) | {"menafn.com"}:
            if h == wire or h.endswith("." + wire):
                return True
            if "." not in h and h.replace(" ", "") == wire.split(".")[0]:
                return True
        return False

#: Days either side of a new article's publication date searched for an
#: earlier copy of the same story. Syndicated copies land within a day or two;
#: a wider window starts merging a story with its own follow-ups.
SAME_STORY_WINDOW_DAYS = 3

#: Query parameters that never identify the article, on top of the campaign
#: tags ``normalize_uri`` already strips. Seeking Alpha appends
#: ``feed_item_type`` and Zacks ``cid``; both put one story into the PowerCo
#: topic twice on 1 October 2026.
_EXTRA_TRACKING = re.compile(
    r"(^|&)(feed_item_type|cid|ito|itm_[^=&]*|ocid|taid)=[^&]*",
    re.IGNORECASE,
)

PRESS_RELEASE = "press_release"
NEWS = "news"


def story_url_key(uri: Any) -> str:
    """The URL with everything that does not identify the article removed."""
    key = normalize_uri(uri)
    if "?" in key:
        path, _, query = key.partition("?")
        query = _EXTRA_TRACKING.sub("", query).lstrip("&")
        key = f"{path}?{query}" if query else path
    return key


def source_type(uri: Any, news_source: Any) -> str:
    """``press_release`` when the URL host or the source name is a paid wire."""
    host = normalize_uri(uri).split("/", 1)[0]
    if is_wire_host(host) or is_wire_host(str(news_source or "")):
        return PRESS_RELEASE
    return NEWS


@lru_cache(maxsize=200_000)
def _title_key(title: str):
    """Normalised title and its significant tokens, computed once per title.

    Each new article is compared with every earlier original in its topic's
    6-day window (about 1,850 on bugfixing's largest topic), so normalising
    on every comparison made labelling 99% regex work.
    """
    return normalize_title(title), _title_tokens(title)


#: Identical titles shorter than this (in significant tokens) are not linked:
#: "Editorial" on two different papers matched on equality alone.
MIN_TOKENS_FOR_EQUALITY = 3

#: Near (not equal) matches need the shorter title to have this many
#: significant tokens. The briefing composer uses 5; at 5, "Israel strikes
#: Hezbollah targets in Lebanon" linked to a different strike story, wording
#: that recurs every few days.
MIN_TOKENS_FOR_NEAR_MATCH = max(MIN_TOKENS_FOR_SIMILARITY, 6)

_DIGITS = re.compile(r"\d+")


#: Near matches on a shorter title than this need every token to match: one
#: differing word in a short title is often the point ("BEng 2027 entry
#: Electronic Engineering with AI" against "... Mechanical Engineering").
MIN_TOKENS_FOR_PARTIAL = 8


def same_story(title_a: Any, title_b: Any, press_release: bool = False,
               same_host: bool = False) -> bool:
    """Do two titles in the same topic describe the same story?

    The briefing composer's rule (``title_similarity``): equal after
    normalising, or the shorter title at least 85% contained in the longer
    one, never for titles under 5 significant tokens or less than half the
    other's length. Merging two different developments is the worse failure,
    so three more limits came from checking 50 links by eye on bugfixing:

    - Equal titles need at least 3 significant tokens ("Editorial").
    - Near matches need the same numbers ("AP Technology SummaryBrief at
      6:33 p.m." against "at 6:07 p.m." are different summaries).
    - Press releases link only on equal titles from different sites. Their
      wording is a formula,
      so "Radware Reports Second Quarter 2026 Financial Results" was 86%
      contained in PTC Therapeutics' release of the same name.
    """
    if not title_a or not title_b:
        return False
    na, ta = _title_key(str(title_a))
    nb, tb = _title_key(str(title_b))
    if not na or not nb:
        return False
    if press_release and same_host:
        # One wire publishing the same title twice is two releases: "Progress
        # on share buyback programme" is a weekly title many companies use.
        return False
    if na == nb:
        return len(ta) >= MIN_TOKENS_FOR_EQUALITY
    if press_release:
        return False
    if set(_DIGITS.findall(na)) != set(_DIGITS.findall(nb)):
        return False
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(shorter) < MIN_TOKENS_FOR_NEAR_MATCH:
        return False
    if len(shorter) / len(longer) < MIN_TITLE_LENGTH_RATIO:
        return False
    if len(shorter) < MIN_TOKENS_FOR_PARTIAL:
        return shorter <= longer
    return len(shorter & longer) / len(shorter) >= TITLE_SIMILARITY_THRESHOLD


def window_bounds(publication_date: Any) -> Optional[tuple]:
    """ISO strings bounding the same-story search, or None for no usable date."""
    if not publication_date:
        return None
    try:
        d = datetime.fromisoformat(str(publication_date).replace("Z", "+00:00")[:25])
    except ValueError:
        try:
            d = datetime.strptime(str(publication_date)[:10], "%Y-%m-%d")
        except ValueError:
            return None
    lo = (d - timedelta(days=SAME_STORY_WINDOW_DAYS)).date().isoformat()
    hi = (d + timedelta(days=SAME_STORY_WINDOW_DAYS + 1)).date().isoformat()
    return lo, hi


# --- Which topics show press releases ----------------------------------------

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.json")
_cache: dict = {"mtime": None, "topics": frozenset()}


def press_release_topics() -> Set[str]:
    """Topics whose feeds show press releases.

    A topic opts in with ``"include_press_releases": true`` in config.json.
    Without the key, Market Monitoring topics show them (a vendor's own
    releases are the point there) and every other topic does not, unless the
    site sets ``STORY_PR_DEFAULT=show``. Read from
    the file on change only, since every reader of ``articles`` asks.
    """
    try:
        mtime = os.path.getmtime(_CONFIG_PATH)
    except OSError:
        return set(_cache["topics"])
    if mtime != _cache["mtime"]:
        try:
            with open(_CONFIG_PATH) as f:
                topics = json.load(f).get("topics", [])
            # STORY_PR_DEFAULT=show keeps press releases in every topic that
            # has not said otherwise. Set on wiley and wileytest, where M&A
            # Updates and Patent Cliffs carry 11-19% wire releases that are
            # often the primary source for the deal or filing.
            show_all = os.getenv("STORY_PR_DEFAULT", "hide").strip().lower() == "show"
            names = set()
            for t in topics:
                name = (t.get("name") or "").strip()
                flag = t.get("include_press_releases")
                if flag is None:
                    flag = show_all or name.lower().startswith("market monitoring")
                if name and flag:
                    names.add(name)
            _cache.update(mtime=mtime, topics=frozenset(names))
        except (OSError, ValueError):
            pass
    return set(_cache["topics"])


# --- Labelling rows -----------------------------------------------------------
#
# A row is linked only to an earlier row that is already labelled
# (source_type set) and is itself an original. The sweep labels oldest first,
# so "already labelled" means "seen earlier", and the first copy we saw stays
# the original. Chains never form.

def _same_row_sql():
    from sqlalchemy import text
    return text("SELECT uri FROM articles WHERE topic = :topic AND url_key = :key "
                "AND uri <> :uri AND source_type IS NOT NULL "
                "ORDER BY duplicate_of NULLS FIRST LIMIT 1")


def _candidates_sql():
    from sqlalchemy import text
    return text("SELECT uri, title, source_type, news_source FROM articles WHERE topic = :topic "
                "AND publication_date >= :lo AND publication_date < :hi "
                "AND uri <> :uri AND source_type IS NOT NULL AND duplicate_of IS NULL "
                "ORDER BY COALESCE(submission_date, publication_date), uri")


#: Social platforms beyond the shared list in social_sources.py, which
#: other features rely on as it is (LinkedIn posts reach market topics).
_MORE_SOCIAL = ("linkedin", "twitter", "instagram", "tiktok", "facebook", "youtube", "threads")


def _host(uri: Any) -> str:
    return normalize_uri(uri).split("/", 1)[0]


def recheck_links(facade, limit: int = 5000, after_uri: str = "") -> dict:
    """Clear title-based links the current rule no longer makes.

    For tightening the rule without relabelling a whole site: every rule
    change so far only removes links, so a copy whose pair fails the current
    ``same_story`` becomes an original again. Links made by URL key stay.
    Pages through copies by URI; pass back ``last`` as ``after_uri``.
    """
    from sqlalchemy import text
    rows = facade._fetchall_with_rollback(text(
        "SELECT c.uri, c.title, c.source_type, o.uri, o.title, o.source_type "
        "FROM articles c JOIN articles o ON o.uri = c.duplicate_of "
        "WHERE c.uri > :after AND c.url_key IS DISTINCT FROM o.url_key "
        "ORDER BY c.uri LIMIT :limit"), {"after": after_uri, "limit": limit})
    stats = {"checked": 0, "cleared": 0, "last": None}
    clear = text("UPDATE articles SET duplicate_of = NULL WHERE uri = :uri")
    for cu, ct, cs, ou, ot, os_ in rows or []:
        stats["checked"] += 1
        stats["last"] = cu
        pr = PRESS_RELEASE in (cs, os_)
        if not same_story(ct, ot, press_release=pr, same_host=_host(cu) == _host(ou)):
            facade._execute_with_rollback(clear, {"uri": cu})
            stats["cleared"] += 1
    return stats


def _is_social(news_source: Any) -> bool:
    from app.services.social_sources import is_social_source
    s = str(news_source or "").lower()
    return is_social_source(s) or any(k in s for k in _MORE_SOCIAL)


def label_article(facade, uri: str, title: Any, news_source: Any, topic: Any,
                  publication_date: Any) -> dict:
    """The three labels for one article, from rows already labelled.

    ``same_row`` is the URI of a stored row whose URL differs only by
    tracking parameters, or None. The insert paths treat that as the article
    already existing; the sweep links it as a copy.
    """
    key = story_url_key(uri)
    labels = {"url_key": key, "source_type": source_type(uri, news_source),
              "duplicate_of": None, "same_row": None}
    if not topic:
        return labels
    row = facade._fetchone_with_rollback(
        _same_row_sql(), {"topic": topic, "key": key, "uri": uri})
    if row:
        labels["same_row"] = row[0]
        labels["duplicate_of"] = row[0]
        return labels
    # Social posts link on URL only. Two accounts posting the same news are
    # two voices, and the Voices views count authors.
    if _is_social(news_source):
        return labels
    bounds = window_bounds(publication_date)
    if not bounds or not normalize_title(title):
        return labels
    rows = facade._fetchall_with_rollback(
        _candidates_sql(), {"topic": topic, "lo": bounds[0], "hi": bounds[1], "uri": uri})
    mine_pr = labels["source_type"] == PRESS_RELEASE
    my_host = _host(uri)
    for r in rows or []:
        their_pr = len(r) > 2 and r[2] == PRESS_RELEASE
        if len(r) > 3 and _is_social(r[3]):
            continue
        if same_story(title, r[1], press_release=mine_pr or their_pr,
                      same_host=my_host == _host(r[0])):
            labels["duplicate_of"] = r[0]
            break
    return labels


def label_unlabelled(facade, limit: int = 2000, topic: Optional[str] = None,
                     dry_run: bool = False) -> dict:
    """Label rows with no source_type yet, oldest first.

    Catches every insert path that does not label at insert (there are a
    dozen raw INSERTs across routes, scripts and services), and is the
    backfill. Returns counts and, for a dry run, the links it would make.
    """
    from sqlalchemy import text
    params = {"limit": limit}
    topic_sql = ""
    if topic:
        topic_sql = "AND topic = :topic"
        params["topic"] = topic
    rows = facade._fetchall_with_rollback(text(
        "SELECT uri, title, news_source, topic, publication_date FROM articles "
        f"WHERE source_type IS NULL {topic_sql} "
        "ORDER BY COALESCE(submission_date, publication_date) NULLS LAST, uri LIMIT :limit"),
        params)
    stats = {"labelled": 0, "copies": 0, "press_releases": 0, "links": []}
    update = text("UPDATE articles SET url_key = :key, source_type = :st, "
                  "duplicate_of = :dup WHERE uri = :uri")
    for uri, title, news_source, row_topic, pub in rows or []:
        lab = label_article(facade, uri, title, news_source, row_topic, pub)
        stats["labelled"] += 1
        if lab["source_type"] == PRESS_RELEASE:
            stats["press_releases"] += 1
        if lab["duplicate_of"]:
            stats["copies"] += 1
            if dry_run:
                stats["links"].append((uri, title, lab["duplicate_of"]))
        if dry_run:
            # Nothing is written, so a later row in this batch cannot link to
            # an earlier one: a dry run undercounts copies. Use it to inspect.
            continue
        facade._execute_with_rollback(update, {
            "key": lab["url_key"], "st": lab["source_type"],
            "dup": lab["duplicate_of"], "uri": uri})
    return stats
