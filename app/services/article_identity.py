"""Which stored article a collected item is, and what to keep from a repeat.

Until October 2026 the insert path asked one question: is this exact URL
already a row? A tracking variant of a known URL became a second row, a
social post seen under two URLs became two rows, and a second provider's
fuller copy of a known story was thrown away. This module answers three
questions for the insert path (``DatabaseQueryFacade.create_article``):

- ``resolve_identity``: which row is this, by record type. A social post is
  its platform and post id, a scholarly record its DOI, ordinary news its
  canonical URL. A URL never identifies a social post, because a profile
  URL stands for many posts.
- ``record_observation``: remember that this provider showed us this row,
  under this URL. Every URL variant goes into ``article_url_aliases`` with
  the registry version that reduced it, so a later registry change is
  visible on the rows written before it.
- ``merge_fields``: what a repeat may change on the stored row. A non-empty
  value is never replaced by an empty one, a full text beats an excerpt, a
  known date fills a missing one but never overwrites a different one.

Every database call here is best effort: a failure is logged and the caller
carries on with the plain insert or update it would have done anyway.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 4, 8 and 30.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.collectors.url_identity import (
    ID_CANONICAL_URL,
    ID_SOCIAL,
    RT_NEWS,
    RT_SCHOLARLY,
    RT_SOCIAL,
    choose_identity,
    normalize_url,
    observation_identity,
    registry_version,
)

logger = logging.getLogger(__name__)

#: Values ``content_kind`` may take (work package 8).
KIND_FULL_TEXT = "full_text"
KIND_ABSTRACT = "abstract"
KIND_EXCERPT = "excerpt"
KIND_SOCIAL = "social_post"
KIND_UNKNOWN = "unknown"

#: How a stored row was found. Written to the log and to ``last_create_outcome``.
MATCH_URI = "uri"
MATCH_OBSERVATION = "observation"
MATCH_SOCIAL_META = "social_meta"
MATCH_ALIAS = "alias"
MATCH_CANONICAL = "canonical_url"
MATCH_URL_KEY = "url_key"

#: Column values the merge must never produce: set once at insert, or owned
#: by the analysis step.
PROTECTED_COLUMNS = frozenset({
    "uri", "first_seen_at", "submission_date", "topic", "analyzed",
    "category", "future_signal", "future_signal_explanation", "sentiment",
    "sentiment_explanation", "time_to_impact", "time_to_impact_explanation",
    "tags", "driver_type", "driver_type_explanation", "bias",
    "factual_reporting", "mbfc_credibility_rating", "bias_source",
    "bias_country", "press_freedom", "media_type", "popularity",
    "topic_alignment_score", "keyword_relevance_score", "confidence_score",
    "overall_match_explanation", "extracted_article_topics",
    "extracted_article_keywords", "quality_score", "quality_issues",
    "url_key", "duplicate_of", "source_type",
})

#: Markers a provider leaves at the end of a cut-off body. NewsAPI writes
#: ``[+1234 chars]``; scrapers leave an ellipsis.
_TRUNCATION_MARKERS = ("[+", "…", "...")


@dataclass
class Resolution:
    """The answer to "which row is this".

    ``uri`` is the stored row's key when ``existing`` is true, otherwise
    None. ``method`` is the identity method from ``url_identity`` (how the
    record is identified), ``matched_by`` is which lookup found the row.
    """
    uri: Optional[str]
    method: str
    canonical_url: str
    existing: bool
    record_type: str = RT_NEWS
    identity_key: str = ""
    matched_by: Optional[str] = None


# ---------------------------------------------------------------------------
# Reading the article dict
# ---------------------------------------------------------------------------

def _raw(article: Dict[str, Any]) -> Dict[str, Any]:
    raw = article.get("raw_data")
    return raw if isinstance(raw, dict) else {}


def _social(article: Dict[str, Any]) -> Dict[str, Any]:
    meta = article.get("social_meta")
    return meta if isinstance(meta, dict) else {}


def record_type_of(article: Dict[str, Any]) -> str:
    """Social when the collector attached ``social_meta`` or a platform,
    scholarly when it carries an arXiv id or DOI, otherwise news."""
    raw = _raw(article)
    if _social(article) or raw.get("platform"):
        return RT_SOCIAL
    if raw.get("arxiv_id") or raw.get("doi") or article.get("doi"):
        return RT_SCHOLARLY
    return RT_NEWS


def provider_of(article: Dict[str, Any]) -> str:
    """The collector's own name for itself, falling back to the source."""
    raw = _raw(article)
    p = raw.get("provider") or raw.get("source_name") or article.get("provider")
    if not p:
        src = str(article.get("source") or "")
        p = src.split(":", 1)[0] if src.startswith("xpoz:") else src
    return (str(p).strip().lower() or "unknown")[:40]


def _platform_and_post_id(article: Dict[str, Any]):
    meta = _social(article)
    raw = _raw(article)
    platform = meta.get("platform") or raw.get("platform")
    post_id = meta.get("external_id") or raw.get("external_id") or raw.get("uri")
    return (str(platform).lower() if platform else None,
            str(post_id) if post_id else None)


def _external_id(article: Dict[str, Any]) -> Optional[str]:
    """The provider's own id for the record, whichever key the collector used."""
    raw = _raw(article)
    meta = _social(article)
    if meta.get("external_id"):
        return str(meta["external_id"])
    for key in ("external_id", "arxiv_id", "doi", "uri", "id"):
        if raw.get(key):
            return str(raw[key])
    return None


def content_kind_of(article: Dict[str, Any]) -> str:
    """The article dict's own label, or a guess from the record type."""
    kind = article.get("content_kind")
    if kind in (KIND_FULL_TEXT, KIND_ABSTRACT, KIND_EXCERPT, KIND_SOCIAL, KIND_UNKNOWN):
        return kind
    rt = record_type_of(article)
    if rt == RT_SOCIAL:
        return KIND_SOCIAL
    if rt == RT_SCHOLARLY:
        return KIND_ABSTRACT
    return KIND_EXCERPT


def _body(article: Dict[str, Any]) -> str:
    """The longest text the collector gave us for the body."""
    best = ""
    for key in ("content", "summary", "description"):
        v = article.get(key)
        if isinstance(v, str) and len(v.strip()) > len(best):
            best = v.strip()
    raw_content = _raw(article).get("content")
    if isinstance(raw_content, str) and len(raw_content.strip()) > len(best):
        best = raw_content.strip()
    return best


def _looks_truncated(text: Optional[str]) -> bool:
    t = (text or "").rstrip()
    return any(t.endswith(m) or (m == "[+" and "[+" in t[-20:]) for m in _TRUNCATION_MARKERS)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def _text_sql(sql: str):
    from sqlalchemy import text
    return text(sql)


def _fetchone(facade, sql: str, params: Dict[str, Any]):
    try:
        return facade._fetchone_with_rollback(_text_sql(sql), params)
    except Exception as exc:  # noqa: BLE001 - lookups are best effort
        logger.warning("article identity lookup failed (%s): %s", sql[:60], exc)
        return None


def observation_key_for(article: Dict[str, Any], provider: Optional[str] = None) -> Optional[str]:
    """The unique key one provider's copy of a record gets in
    ``article_observations``. Method and key together, so a provider id and
    a canonical URL can never collide."""
    ident = observation_identity(
        provider=provider or provider_of(article),
        external_id=_external_id(article),
        url=article.get("url") or article.get("uri"),
    )
    return f"{ident.method}:{ident.key}" if ident else None


def resolve_identity(facade, article: Dict[str, Any]) -> Resolution:
    """Which stored row this collected item is, or that there is none.

    Lookup order for news: the exact ``articles.uri``, an alias row for the
    URL, ``articles.canonical_url``, then ``articles.url_key`` (the older
    story key). A same-topic row wins when the key matches several, so a
    story that two topics collect keeps the row the topic already shows.

    Social posts skip every URL lookup. They are found by the exact uri, by
    an earlier observation of the same platform post id, or by the
    ``social_meta`` the collector stored on the row.
    """
    url = str(article.get("url") or article.get("uri") or "").strip()
    rt = record_type_of(article)
    raw = _raw(article)
    platform, post_id = _platform_and_post_id(article)
    provider = provider_of(article)
    norm = normalize_url(url)
    canonical = norm.canonical if norm.valid else url
    try:
        identity = choose_identity(
            record_type=rt, provider=provider, external_id=_external_id(article), url=url,
            platform=platform, post_id=post_id, doi=raw.get("doi") or article.get("doi"),
            title=article.get("title"), content=_body(article),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("choose_identity failed for %s: %s", url, exc)
        identity = None
    method = identity.method if identity else ID_CANONICAL_URL
    key = identity.key if identity else canonical
    topic = article.get("topic")

    def found(uri: str, how: str) -> Resolution:
        return Resolution(uri=uri, method=method, canonical_url=canonical, existing=True,
                          record_type=rt, identity_key=key, matched_by=how)

    if url:
        row = _fetchone(facade, "SELECT uri FROM articles WHERE uri = :uri", {"uri": url})
        if row:
            return found(row[0], MATCH_URI)

    obs_key = observation_key_for(article, provider)
    if obs_key:
        row = _fetchone(facade, "SELECT article_uri FROM article_observations "
                                "WHERE observation_key = :k LIMIT 1", {"k": obs_key})
        if row:
            return found(row[0], MATCH_OBSERVATION)

    if rt == RT_SOCIAL:
        if platform and post_id:
            row = _fetchone(
                facade,
                "SELECT uri FROM articles WHERE social_meta->>'platform' = :p "
                "AND social_meta->>'external_id' = :e LIMIT 1",
                {"p": platform, "e": post_id})
            if row:
                return found(row[0], MATCH_SOCIAL_META)
        # No URL lookups: a profile URL stands for many posts.
        return Resolution(uri=None, method=method, canonical_url=canonical, existing=False,
                          record_type=rt, identity_key=key)

    if norm.valid:
        row = _fetchone(facade, "SELECT article_uri FROM article_url_aliases "
                                "WHERE url IN (:u, :c) LIMIT 1", {"u": url, "c": canonical})
        if row:
            return found(row[0], MATCH_ALIAS)
        row = _fetchone(
            facade,
            "SELECT uri FROM articles WHERE canonical_url = :c "
            "ORDER BY (topic = :topic) DESC, COALESCE(submission_date, '') LIMIT 1",
            {"c": canonical, "topic": topic or ""})
        if row:
            return found(row[0], MATCH_CANONICAL)

    if url:
        from app.services.story_identity import story_url_key
        row = _fetchone(
            facade,
            "SELECT uri FROM articles WHERE url_key = :k "
            "ORDER BY (topic = :topic) DESC, duplicate_of NULLS FIRST, "
            "COALESCE(submission_date, '') LIMIT 1",
            {"k": story_url_key(url), "topic": topic or ""})
        if row:
            return found(row[0], MATCH_URL_KEY)

    return Resolution(uri=None, method=method, canonical_url=canonical, existing=False,
                      record_type=rt, identity_key=key)


# ---------------------------------------------------------------------------
# Observations and aliases
# ---------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def record_observation(facade, uri: str, article: Dict[str, Any], provider: Optional[str] = None,
                       *, resolution: Optional[Resolution] = None,
                       payload: Optional[Dict[str, Any]] = None) -> bool:
    """Write the observation and the URL alias for one sighting of ``uri``.

    Replays are no-ops: the observation key and the alias URL are unique and
    the inserts say ``ON CONFLICT DO NOTHING``. Also fills
    ``articles.canonical_url``, ``identity_method`` and ``record_type`` on a
    row that has none yet and moves ``last_seen_at``. Returns False when any
    write failed; nothing is raised.
    """
    ok = True
    provider = (provider or provider_of(article))[:40]
    url = str(article.get("url") or article.get("uri") or "").strip()
    res = resolution
    if res is None:
        norm = normalize_url(url)
        res = Resolution(uri=uri, method=ID_CANONICAL_URL, canonical_url=norm.canonical if norm.valid else url,
                         existing=True, record_type=record_type_of(article))
    body = _body(article)
    kind = content_kind_of(article)
    truncated = bool(article.get("truncated")) or (kind == KIND_EXCERPT and _looks_truncated(body))
    extra = dict(payload or {})
    authors = article.get("authors")
    if isinstance(authors, list) and authors:
        extra.setdefault("authors", [str(a) for a in authors if a])
    if article.get("published_date"):
        extra.setdefault("published_date", str(article.get("published_date")))
    obs_key = observation_key_for(article, provider)
    if obs_key:
        try:
            facade._execute_with_rollback(_text_sql(
                "INSERT INTO article_observations (article_uri, provider, external_id, observation_key, "
                "url, content_kind, truncated, extraction_method, published_at_raw, payload) "
                "VALUES (:uri, :provider, :ext, :key, :url, :kind, :trunc, :method, :raw, CAST(:payload AS jsonb)) "
                "ON CONFLICT (observation_key) DO NOTHING"),
                {"uri": uri, "provider": provider, "ext": _external_id(article), "key": obs_key,
                 "url": url or None, "kind": kind, "trunc": truncated,
                 "method": (article.get("extraction_method") or None),
                 "raw": (str(article.get("published_at_raw") or article.get("published_date") or "")[:200] or None),
                 "payload": json.dumps({k: _json_safe(v) for k, v in extra.items()})})
        except Exception as exc:  # noqa: BLE001
            ok = False
            logger.warning("observation not recorded for %s: %s", uri, exc)
    if url and normalize_url(url).valid:
        try:
            facade._execute_with_rollback(_text_sql(
                "INSERT INTO article_url_aliases (article_uri, url, canonical_url, registry_version) "
                "VALUES (:uri, :url, :canonical, :version) ON CONFLICT (url) DO NOTHING"),
                {"uri": uri, "url": url, "canonical": res.canonical_url, "version": registry_version()[:32]})
        except Exception as exc:  # noqa: BLE001
            ok = False
            logger.warning("alias not recorded for %s: %s", uri, exc)
    try:
        facade._execute_with_rollback(_text_sql(
            "UPDATE articles SET canonical_url = COALESCE(canonical_url, :canonical), "
            "identity_method = COALESCE(identity_method, :method), "
            "record_type = COALESCE(record_type, :rt), last_seen_at = NOW() WHERE uri = :uri"),
            {"canonical": res.canonical_url or None, "method": res.method[:24], "rt": res.record_type[:16],
             "uri": uri})
    except Exception as exc:  # noqa: BLE001
        ok = False
        logger.warning("identity columns not set for %s: %s", uri, exc)
    return ok


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _date_text(value: Any) -> str:
    """Two dates compare equal when they name the same instant or the same
    day, whatever the string shape. ``2026-09-29`` equals
    ``2026-09-29T00:00:00+00:00``; it does not equal ``2026-09-29T08:00``."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.isoformat()
    s = str(value).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return s
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    d = d.astimezone(timezone.utc)
    if d.hour == 0 and d.minute == 0 and d.second == 0:
        return d.date().isoformat()
    return d.isoformat()


def merge_fields(existing_row: Dict[str, Any], incoming: Dict[str, Any],
                 *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Column updates a repeat sighting may apply to the stored row.

    Rules (work package 8):

    - A non-empty stored value is never replaced by an empty one.
    - The body (``summary``) is replaced by a longer one only when the
      incoming copy is ``full_text`` and the stored one is not, or when the
      stored one is an excerpt the provider cut off.
    - A known publication date fills a missing one. A different known date
      is left alone; the caller records the incoming one in the observation
      payload, which ``record_observation`` does.
    - Authors are unioned under ``authors`` only when the row has such a
      column (the monolith's ``articles`` does not; the union then lives in
      the observation payload).
    - ``last_seen_at`` moves to now. ``first_seen_at``, ``submission_date``
      and every analysis column are never touched.
    """
    updates: Dict[str, Any] = {}
    row = existing_row or {}

    def fill(column: str, value: Any):
        if _nonempty(value) and not _nonempty(row.get(column)):
            updates[column] = value

    title = incoming.get("title")
    fill("title", title)
    fill("news_source", incoming.get("source") or incoming.get("news_source"))
    fill("original_title", incoming.get("original_title"))
    fill("original_summary", incoming.get("original_summary"))

    incoming_body = _body(incoming)
    stored_body = str(row.get("summary") or "")
    incoming_kind = content_kind_of(incoming)
    stored_kind = row.get("content_kind") or KIND_UNKNOWN
    if _nonempty(incoming_body):
        if not _nonempty(stored_body):
            updates["summary"] = incoming_body
            updates["content_kind"] = incoming_kind
        elif len(incoming_body) > len(stored_body):
            stored_truncated = (stored_kind in (KIND_EXCERPT, KIND_UNKNOWN)
                                and (bool(row.get("truncated")) or _looks_truncated(stored_body)))
            if (incoming_kind == KIND_FULL_TEXT and stored_kind != KIND_FULL_TEXT) or stored_truncated:
                updates["summary"] = incoming_body
                updates["content_kind"] = incoming_kind

    incoming_date = incoming.get("published_date") or incoming.get("publication_date")
    stored_date = row.get("publication_date")
    if _nonempty(incoming_date) and not _nonempty(stored_date):
        updates["publication_date"] = incoming_date
        for col in ("published_at_raw", "publication_date_precision", "date_provenance"):
            if _nonempty(incoming.get(col)):
                updates[col] = incoming[col]
    elif _nonempty(incoming_date) and _nonempty(stored_date):
        if _date_text(incoming_date) != _date_text(stored_date):
            # Conflicting known dates: keep the stored one. The observation
            # row carries the incoming one as published_at_raw.
            updates.setdefault("_date_conflict", {"stored": stored_date, "incoming": incoming_date})

    if "authors" in row:
        have = [a for a in (row.get("authors") or []) if a] if isinstance(row.get("authors"), list) else []
        new = [str(a) for a in (incoming.get("authors") or []) if a] if isinstance(incoming.get("authors"), list) else []
        if new:
            union = list(dict.fromkeys(have + new))
            if union != have:
                updates["authors"] = union

    meta = incoming.get("social_meta")
    if isinstance(meta, dict) and meta and not _nonempty(row.get("social_meta")):
        updates["social_meta"] = meta

    updates["last_seen_at"] = now or datetime.now(timezone.utc)
    for col in list(updates):
        if col in PROTECTED_COLUMNS:
            del updates[col]
    return updates


def column_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
    """The part of a ``merge_fields`` result that is a column write: the
    private keys (``_date_conflict``) are for the observation payload."""
    return {k: v for k, v in updates.items() if not k.startswith("_")}


def authors_union(existing: Optional[List[str]], incoming: Optional[List[str]]) -> List[str]:
    have = [str(a) for a in (existing or []) if a]
    new = [str(a) for a in (incoming or []) if a]
    return list(dict.fromkeys(have + new))
