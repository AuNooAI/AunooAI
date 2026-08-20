"""Timeline mementos — daily event extraction (monolith port of saas /timeline).

A "memento" is one row in ``timeline_events``: a concrete, dated development
for a scope (Brand Watcher brand or keyword-group topic), extracted from that
day's articles. Sources per day:

- SQL detectors (no LLM): volume_spike, sentiment_shift, source_shift
- Brand extras (no LLM): story_emergence (bw_article_stories cluster reaching
  2+ sources), risk_finding (new high-severity bw_article_risks), alert
  (bw_alert_events echo — already identity-deduped upstream)
- One LLM pass (gpt-5.4-mini) over the day's top articles extracting up to 4
  concrete developments, primed with the scope's recent memento titles so a
  continuing story REUSES its title and bumps occurrence_count instead of
  minting a near-duplicate every day.

Dedup: content_hash excludes the event date for story-type events (recurring
story = one memento, occurrence bumped); analytic detectors hash WITH the date
(a different day's shift is a different fact). Weekly/monthly rollups in
``timeline_rollup`` absorb dailies via superseded_by_id / is_stale.

Sync + raw-connection style (db._temp_get_connection()), matching the other
Brand Watcher services; the scheduler calls it via asyncio.to_thread.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services.report_style import CLINICAL_STYLE_SHORT

logger = logging.getLogger(__name__)

MAX_DAILY_EVENTS_PER_SCOPE = 12
LLM_MAX_ARTICLES = 12
LLM_MODEL = "gpt-5.4-mini"
KNOWN_TITLE_LOOKBACK_DAYS = 14

_NEG_SQL = ("(a.sentiment ILIKE '%negativ%' OR a.sentiment ILIKE '%concern%' OR a.sentiment ILIKE '%pessimis%'"
            " OR a.sentiment ILIKE '%critical%' OR a.sentiment ILIKE '%alarm%')")
_POS_SQL = "(a.sentiment ILIKE '%positiv%' OR a.sentiment ILIKE '%optimis%')"

_SIG_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------

def get_timeline_scopes(conn) -> List[Dict[str, Any]]:
    """All timeline scopes: enabled brands + active non-brand-lane topics.

    Market-registry vendors are excluded. Daily extraction is one LLM call per
    scope per day, so an 82-vendor market would add 82 calls a day to say what
    the market's own topic timeline already says. The market is the scope; the
    vendors are what it is measured against.
    """
    has_markets = conn.execute(text(
        "SELECT to_regclass('public.bw_market_brands')")).scalar()
    market_filter = ("""
        AND NOT EXISTS (SELECT 1 FROM bw_market_brands mb
                        WHERE mb.brand_id = bw_brands.id)
    """ if has_markets else "")

    scopes: List[Dict[str, Any]] = []
    for bid, bname in conn.execute(text(
            "SELECT id, display_name FROM bw_brands WHERE enabled = true "
            f"{market_filter} ORDER BY id")).fetchall():
        scopes.append({"scope_type": "brand", "scope_id": str(bid), "label": bname})
    for topic, in conn.execute(text("""
            SELECT DISTINCT topic FROM keyword_groups
            WHERE is_active = true AND topic NOT ILIKE 'Brand Monitoring %'
            ORDER BY topic""")).fetchall():
        scopes.append({"scope_type": "topic", "scope_id": topic, "label": topic})
    return scopes


def scope_label(conn, scope_type: str, scope_id: str) -> str:
    if scope_type == "brand":
        row = conn.execute(text("SELECT display_name FROM bw_brands WHERE id = :b"),
                           {"b": int(scope_id)}).fetchone()
        return row[0] if row else f"Brand {scope_id}"
    return scope_id


# ---------------------------------------------------------------------------
# Day articles per scope
# ---------------------------------------------------------------------------

def _day_bounds(target: date) -> Dict[str, str]:
    return {"d0": target.isoformat(), "d1": (target + timedelta(days=1)).isoformat()}


_ARTICLE_COLS = ("a.uri, a.title, LEFT(COALESCE(NULLIF(a.summary,''), a.title, ''), 300), "
                 "a.news_source, a.sentiment, COALESCE(a.topic_alignment_score, 0)")


def _market_corpus_available(conn) -> bool:
    """Whether this deployment has the market monitor's corpus table.

    Guarded rather than assumed: timeline generation runs on tenants that have
    never had a market monitor, and a missing table there would break every
    topic timeline, not just a market's.
    """
    try:
        return bool(conn.execute(
            text("SELECT to_regclass('bw_market_articles')")).scalar())
    except Exception:  # noqa: BLE001
        return False


def _fetch_day_articles(conn, scope_type: str, scope_id: str, target: date) -> List[Dict[str, Any]]:
    """Articles ingested on the target day for the scope, most relevant first."""
    p = _day_bounds(target)
    if scope_type == "brand":
        bid = int(scope_id)
        lane = conn.execute(text("SELECT display_name FROM bw_brands WHERE id = :b"),
                            {"b": bid}).fetchone()
        lane_topic = f"Brand Monitoring {lane[0]}" if lane else "__none__"
        rows = conn.execute(text(f"""
            SELECT DISTINCT ON (a.uri) {_ARTICLE_COLS}
            FROM articles a
            LEFT JOIN bw_article_categories bac
                   ON bac.article_uri = a.uri AND bac.brand_id = :bid
            WHERE a.submission_date >= :d0 AND a.submission_date < :d1
              AND (bac.article_uri IS NOT NULL OR a.topic = :lane)
              AND COALESCE(bac.relevance_score, a.topic_alignment_score, 0) >= 0.4
              AND NOT EXISTS (SELECT 1 FROM bw_finding_reviews fpr
                              WHERE fpr.article_uri = a.uri AND fpr.status = 'false_positive')
            ORDER BY a.uri
        """), {**p, "bid": bid, "lane": lane_topic}).fetchall()
    else:
        # A market monitor's topic has a second source of articles: the ones
        # matched out of the corpus by the market's own phrases, which were
        # collected under some other topic and so fail `a.topic = :t`. On the
        # SOC Automation market that is 282 of 606 articles, and without this
        # clause none of them reach the timeline, the brief or an observer.
        #
        # They are gated on the market's own match score, not on
        # `topic_alignment_score` — that column measures an article against the
        # topic it was collected for, which is a different question and here
        # would be the wrong one.
        #
        # Vendor LinkedIn posts are in only when the review pass judged them
        # to state a fact. Unfiltered they are 562 posts against 122 news
        # articles and arrive in bursts, so a daily timeline built on them is
        # a record of vendor marketing. Filtered, they are where launches,
        # partnerships and raises show up first.
        market_clause = ""
        if _market_corpus_available(conn):
            market_clause = """
              OR EXISTS (
                  SELECT 1 FROM bw_market_articles ma
                  JOIN bw_markets m ON m.id = ma.market_id
                  WHERE ma.article_uri = a.uri
                    AND (ma.score >= 12 OR ma.review_verdict = 'signal')
                    AND (COALESCE(a.bias_source, '') <> 'vendor:linkedin'
                         OR ma.review_verdict = 'signal')
                    AND COALESCE(
                        m.config->'collection'->>'topic_name',
                        'Market Monitoring ' || m.name) = :t
              )"""
        rows = conn.execute(text(f"""
            SELECT {_ARTICLE_COLS}
            FROM articles a
            WHERE a.submission_date >= :d0 AND a.submission_date < :d1
              AND ((a.topic = :t AND COALESCE(a.topic_alignment_score, 0) >= 0.4)
                   {market_clause})
        """), {**p, "t": scope_id}).fetchall()
    arts = [{"uri": r[0], "title": r[1] or "", "summary": r[2] or "", "source": r[3] or "",
             "sentiment": r[4] or "", "score": float(r[5] or 0)} for r in rows]
    arts.sort(key=lambda a: -a["score"])
    return arts


# ---------------------------------------------------------------------------
# Dedup hash + upsert
# ---------------------------------------------------------------------------

def _norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").lower().strip())


def _content_hash(event_type: str, title: str, scope_type: str, scope_id: str,
                  event_date: Optional[date] = None) -> str:
    """Dedup hash. Pass event_date ONLY for analytic events whose recurrence on
    another day is a genuinely new fact; story events hash undated so the same
    story bumps occurrence instead of duplicating."""
    raw = f"{event_type}|{_norm_title(title)}|{scope_type}|{scope_id}"
    if event_date is not None:
        raw += f"|{event_date.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()


def upsert_event(conn, scope_type: str, scope_id: str, evt: Dict[str, Any],
                 target: date, dated_hash: bool) -> str:
    """Insert a memento; on hash conflict bump occurrence/last_seen (once per day).

    Returns 'created' | 'bumped' | 'dup'.
    """
    chash = evt.get("content_hash") or _content_hash(
        evt["event_type"], evt["title"], scope_type, scope_id,
        target if dated_hash else None)
    row = conn.execute(text("""
        INSERT INTO timeline_events
            (scope_type, scope_id, event_type, event_subtype, title, description,
             significance, event_data, entities, article_uris, article_count,
             content_hash, event_date, last_seen_date, granularity)
        VALUES (:st, :sid, :et, :sub, :title, :descr, :sig, :edata, :ents, :uris,
                :n, :h, :d, :d, :gran)
        ON CONFLICT ON CONSTRAINT uq_timeline_event_hash DO UPDATE
        SET last_seen_date = EXCLUDED.event_date,
            occurrence_count = timeline_events.occurrence_count + 1,
            description = COALESCE(NULLIF(EXCLUDED.description, ''), timeline_events.description),
            article_count = timeline_events.article_count + EXCLUDED.article_count,
            is_stale = false
        WHERE timeline_events.last_seen_date < EXCLUDED.event_date
        RETURNING occurrence_count
    """), {
        "st": scope_type, "sid": scope_id, "et": evt["event_type"],
        "sub": evt.get("event_subtype"), "title": evt["title"][:500],
        "descr": evt.get("description") or "",
        "sig": evt.get("significance", "medium"),
        "edata": json.dumps(evt.get("event_data") or {}),
        "ents": json.dumps(evt.get("entities") or []),
        "uris": json.dumps((evt.get("article_uris") or [])[:50]),
        "n": evt.get("article_count", 1), "h": chash, "d": target,
        "gran": evt.get("granularity", "daily"),
    }).fetchone()
    if row is None:
        return "dup"
    return "created" if row[0] == 1 else "bumped"


# ---------------------------------------------------------------------------
# SQL detectors (no LLM)
# ---------------------------------------------------------------------------

def _detect_volume_spike(conn, scope_type, scope_id, target, day_count) -> Optional[Dict]:
    p = {"d0": (target - timedelta(days=7)).isoformat(), "d1": target.isoformat()}
    if scope_type == "brand":
        prior = conn.execute(text("""
            SELECT COUNT(DISTINCT a.uri) FROM articles a
            JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :bid
            WHERE a.submission_date >= :d0 AND a.submission_date < :d1
        """), {**p, "bid": int(scope_id)}).fetchone()[0] or 0
    else:
        prior = conn.execute(text("""
            SELECT COUNT(*) FROM articles a
            WHERE a.topic = :t AND a.submission_date >= :d0 AND a.submission_date < :d1
              AND COALESCE(a.topic_alignment_score, 0) >= 0.4
        """), {**p, "t": scope_id}).fetchone()[0] or 0
    avg = prior / 7.0
    if day_count < 5 or avg <= 0 or day_count < avg * 2:
        return None
    return {
        "event_type": "volume_spike",
        "title": f"Coverage spike: {day_count} articles (7-day avg {avg:.1f})",
        "description": f"{day_count} on-scope articles arrived today against a 7-day daily average of {avg:.1f}.",
        "significance": "high" if day_count >= avg * 3 else "medium",
        "event_data": {"today": day_count, "avg_7d": round(avg, 2)},
    }


def _detect_sentiment_shift(conn, scope_type, scope_id, target, day_articles) -> Optional[Dict]:
    def _neg_share(arts):
        scored = [a for a in arts if a["sentiment"]]
        if len(scored) < 5:
            return None, 0
        neg = sum(1 for a in scored if re.search(r"negativ|concern|pessimis|critical|alarm",
                                                 a["sentiment"], re.I))
        return neg / len(scored), len(scored)

    today_share, today_n = _neg_share(day_articles)
    if today_share is None:
        return None
    p = {"d0": (target - timedelta(days=7)).isoformat(), "d1": target.isoformat()}
    if scope_type == "brand":
        row = conn.execute(text(f"""
            SELECT COUNT(*) FILTER (WHERE {_NEG_SQL}) AS neg,
                   COUNT(*) FILTER (WHERE COALESCE(a.sentiment,'') <> '') AS scored
            FROM articles a
            JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :bid
            WHERE a.submission_date >= :d0 AND a.submission_date < :d1
        """), {**p, "bid": int(scope_id)}).fetchone()
    else:
        row = conn.execute(text(f"""
            SELECT COUNT(*) FILTER (WHERE {_NEG_SQL}) AS neg,
                   COUNT(*) FILTER (WHERE COALESCE(a.sentiment,'') <> '') AS scored
            FROM articles a
            WHERE a.topic = :t AND a.submission_date >= :d0 AND a.submission_date < :d1
              AND COALESCE(a.topic_alignment_score, 0) >= 0.4
        """), {**p, "t": scope_id}).fetchone()
    neg, scored = row[0] or 0, row[1] or 0
    if scored < 10:
        return None
    prior_share = neg / scored
    delta = today_share - prior_share
    if abs(delta) < 0.25:
        return None
    direction = "negative" if delta > 0 else "positive"
    return {
        "event_type": "sentiment_shift",
        "title": f"Sentiment shift {direction} ({prior_share:.0%} → {today_share:.0%} negative share)",
        "description": (f"Negative share of scored coverage moved from {prior_share:.0%} (7-day) "
                        f"to {today_share:.0%} today across {today_n} scored articles."),
        "significance": "high" if abs(delta) >= 0.4 else "medium",
        "event_data": {"prior_neg_share": round(prior_share, 3),
                       "today_neg_share": round(today_share, 3),
                       "delta": round(delta, 3), "sample": today_n},
    }


def _detect_source_shift(conn, scope_type, scope_id, target, day_articles) -> Optional[Dict]:
    today_sources = {a["source"] for a in day_articles if a["source"]}
    if not today_sources:
        return None
    p = {"d0": (target - timedelta(days=30)).isoformat(), "d1": target.isoformat()}
    if scope_type == "brand":
        rows = conn.execute(text("""
            SELECT DISTINCT a.news_source FROM articles a
            JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :bid
            WHERE a.submission_date >= :d0 AND a.submission_date < :d1
        """), {**p, "bid": int(scope_id)}).fetchall()
    else:
        rows = conn.execute(text("""
            SELECT DISTINCT a.news_source FROM articles a
            WHERE a.topic = :t AND a.submission_date >= :d0 AND a.submission_date < :d1
        """), {**p, "t": scope_id}).fetchall()
    prior = {r[0] for r in rows if r[0]}
    new_sources = sorted(today_sources - prior)
    if len(new_sources) < 2:
        return None
    return {
        "event_type": "source_shift",
        "title": f"New sources covering scope: {', '.join(new_sources[:3])}",
        "description": (f"{len(new_sources)} source(s) not seen in the prior 30 days began "
                        f"covering this today: {', '.join(new_sources[:8])}."),
        "significance": "medium",
        "event_data": {"new_sources": new_sources[:20], "prior_source_count": len(prior)},
        "article_uris": [a["uri"] for a in day_articles if a["source"] in new_sources][:10],
    }


# ---------------------------------------------------------------------------
# Brand-only structured sources
# ---------------------------------------------------------------------------

def _brand_story_events(conn, brand_id: int, target: date) -> List[Dict]:
    """Story clusters that reached 2+ members with at least one member today."""
    p = _day_bounds(target)
    rows = conn.execute(text("""
        SELECT s.story_group_id, COUNT(*) AS n,
               MAX(ca.title) AS canon_title,
               array_agg(s.article_uri) AS uris
        FROM bw_article_stories s
        JOIN articles a ON a.uri = s.article_uri
        LEFT JOIN articles ca ON ca.uri = s.story_group_id
        WHERE s.brand_id = :bid
        GROUP BY s.story_group_id
        HAVING COUNT(*) >= 2
           AND MAX(a.submission_date) >= :d0 AND MAX(a.submission_date) < :d1
    """), {"bid": brand_id, **p}).fetchall()
    events = []
    for gid, n, canon_title, uris in rows:
        title = (canon_title or "Syndicated story")[:200]
        events.append({
            "event_type": "story_emergence",
            "title": f"{title} (×{n} sources)",
            "description": f"The same story is now carried by {n} distinct sources.",
            "significance": "high" if n >= 4 else "medium",
            "event_data": {"story_group_id": gid, "source_count": n},
            "article_uris": list(uris or [])[:20],
            "article_count": n,
            # keyed on the cluster, not the title/date: growth bumps occurrence
            "content_hash": _content_hash("story_emergence", gid, "brand", str(brand_id)),
        })
    return events


def _brand_risk_events(conn, brand_id: int, target: date) -> List[Dict]:
    rows = conn.execute(text("""
        SELECT r.risk_type, COUNT(*), MAX(a.title), array_agg(DISTINCT r.article_uri)
        FROM bw_article_risks r JOIN articles a ON a.uri = r.article_uri
        WHERE r.brand_id = :bid AND r.severity = 'high'
          AND r.detected_at >= CAST(:d0 AS date) AND r.detected_at < CAST(:d1 AS date)
        GROUP BY r.risk_type
    """), {"bid": brand_id, **_day_bounds(target)}).fetchall()
    events = []
    for risk_type, n, sample, uris in rows:
        events.append({
            "event_type": "risk_finding",
            "title": f"High-severity {risk_type.replace('_', '/')} finding ({n})",
            "description": f"{n} article(s) flagged {risk_type} at high severity. e.g. \"{(sample or '')[:120]}\"",
            "significance": "critical",
            "event_data": {"risk_type": risk_type, "count": n},
            "article_uris": list(uris or [])[:20],
            "article_count": n,
            "content_hash": _content_hash(
                "risk_finding", f"{risk_type}|{'|'.join(sorted(uris or []))}", "brand", str(brand_id)),
        })
    return events


def _brand_alert_events(conn, brand_id: int, target: date) -> List[Dict]:
    """Echo bw_alert_events as mementos — they are already identity-deduped."""
    rows = conn.execute(text("""
        SELECT rule, severity, title, dedup_key, payload
        FROM bw_alert_events
        WHERE brand_id = :bid AND rule <> 'digest'
          AND created_at >= CAST(:d0 AS date) AND created_at < CAST(:d1 AS date)
    """), {"bid": brand_id, **_day_bounds(target)}).fetchall()
    events = []
    for rule, severity, title, dedup_key, payload in rows:
        p = payload if isinstance(payload, dict) else json.loads(payload or "{}")
        events.append({
            "event_type": "alert",
            "event_subtype": rule,
            "title": title[:300],
            "description": "",
            "significance": "critical" if severity == "high" else "medium",
            "event_data": {"rule": rule, "severity": severity},
            "article_uris": (p.get("alert_uris") or [])[:10],
            "content_hash": _content_hash("alert", dedup_key, "brand", str(brand_id)),
        })
    return events


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

def _parse_json_lenient(raw: str):
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    try:
        obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
        return obj
    except json.JSONDecodeError:
        return None


def _known_recent_titles(conn, scope_type: str, scope_id: str, target: date) -> List[str]:
    rows = conn.execute(text("""
        SELECT title FROM timeline_events
        WHERE scope_type = :st AND scope_id = :sid
          AND event_subtype = 'llm_extracted'
          AND event_date >= :cutoff
        ORDER BY last_seen_date DESC NULLS LAST, event_date DESC
        LIMIT 40
    """), {"st": scope_type, "sid": scope_id,
           "cutoff": target - timedelta(days=KNOWN_TITLE_LOOKBACK_DAYS)}).fetchall()
    return [r[0] for r in rows]


def _llm_extract_events(scope_name: str, day_articles: List[Dict],
                        known_titles: List[str]) -> List[Dict]:
    if len(day_articles) < 3:
        return []
    arts = day_articles[:LLM_MAX_ARTICLES]
    art_block = "\n".join(
        f"[{i}] {a['title']}" + (f" — {a['summary'][:200]}" if a["summary"] else "")
        for i, a in enumerate(arts))
    known_block = ("\n".join(f"- {t}" for t in known_titles[:40])) or "(none yet)"
    prompt = (
        f"You maintain a running timeline of concrete developments for \"{scope_name}\".\n\n"
        f"Today's articles:\n{art_block}\n\n"
        f"KNOWN EVENTS already on the timeline (last {KNOWN_TITLE_LOOKBACK_DAYS} days):\n{known_block}\n\n"
        "Extract up to 4 concrete developments from today's articles. Rules:\n"
        "- A development is something that HAPPENED (a decision, launch, filing, "
        "report, dispute, appointment, result) — not a theme or vibe.\n"
        "- If a development continues a KNOWN EVENT, reuse that event's title "
        "VERBATIM as its title, and include it ONLY if today adds something "
        "material; otherwise leave it out entirely.\n"
        "- Titles: factual, specific, max 100 chars, no editorializing.\n"
        "- description: 1-2 plain sentences stating what happened, grounded "
        "only in the articles." + CLINICAL_STYLE_SHORT + "\n\n"
        "Output a pure JSON array (no markdown) of objects with fields: "
        "\"title\", \"description\", \"significance\" (low|medium|high|critical), "
        "\"entities\" (list of named orgs/people), \"article_indexes\" (list of "
        "integers referencing the articles above). Output [] if nothing concrete "
        "happened today."
    )
    try:
        from app.ai_models import LiteLLMModel
        model = LiteLLMModel.get_instance(LLM_MODEL)
        raw = model.generate_response([{"role": "user", "content": prompt}], temperature=0.2)
        parsed = _parse_json_lenient(raw)
        if not isinstance(parsed, list):
            return []
        events = []
        for item in parsed[:4]:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            idxs = [i for i in (item.get("article_indexes") or [])
                    if isinstance(i, int) and 0 <= i < len(arts)]
            events.append({
                "event_type": "new_development",
                "event_subtype": "llm_extracted",
                "title": str(item["title"])[:200],
                "description": str(item.get("description") or "")[:800],
                "significance": item.get("significance") if item.get("significance")
                                in _SIG_ORDER else "medium",
                "entities": [str(e)[:80] for e in (item.get("entities") or [])[:10]],
                "article_uris": [arts[i]["uri"] for i in idxs][:10],
                "article_count": max(len(idxs), 1),
            })
        return events
    except Exception as e:  # noqa: BLE001
        logger.warning(f"timeline LLM extraction failed for {scope_name}: {e}")
        return []


# ---------------------------------------------------------------------------
# Run tracking + main entrypoint
# ---------------------------------------------------------------------------

def _record_run(conn, scope_type, scope_id, run_type, run_date, status,
                processed=0, created=0, deduped=0, duration=0.0, error=None):
    conn.execute(text("""
        INSERT INTO timeline_runs (scope_type, scope_id, run_type, run_date, status,
                                   articles_processed, events_created, events_deduplicated,
                                   duration_seconds, error_message)
        VALUES (:st, :sid, :rt, :rd, :status, :p, :c, :dd, :dur, :err)
        ON CONFLICT ON CONSTRAINT uq_timeline_run DO UPDATE
        SET status = EXCLUDED.status,
            articles_processed = EXCLUDED.articles_processed,
            events_created = EXCLUDED.events_created,
            events_deduplicated = EXCLUDED.events_deduplicated,
            duration_seconds = EXCLUDED.duration_seconds,
            error_message = EXCLUDED.error_message
    """), {"st": scope_type, "sid": scope_id, "rt": run_type, "rd": run_date,
           "status": status, "p": processed, "c": created, "dd": deduped,
           "dur": round(duration, 2), "err": error})
    conn.commit()


def run_already_completed(conn, scope_type, scope_id, run_type, run_date) -> bool:
    return conn.execute(text("""
        SELECT 1 FROM timeline_runs
        WHERE scope_type = :st AND scope_id = :sid AND run_type = :rt
          AND run_date = :rd AND status = 'completed'
    """), {"st": scope_type, "sid": scope_id, "rt": run_type, "rd": run_date}).fetchone() is not None


def extract_daily_events(conn, scope_type: str, scope_id: str, target: date,
                         use_llm: bool = True) -> Dict[str, int]:
    """Extract one day's mementos for a scope. Idempotent per (scope, day)."""
    t0 = time.monotonic()
    if run_already_completed(conn, scope_type, scope_id, "daily_extraction", target):
        return {"articles_processed": 0, "events_created": 0, "events_deduplicated": 0}

    label = scope_label(conn, scope_type, scope_id)
    day_articles = _fetch_day_articles(conn, scope_type, scope_id, target)

    dated: List[Dict] = []      # analytic events — hash includes the date
    undated: List[Dict] = []    # story events — hash excludes the date

    if day_articles:
        for det in (_detect_volume_spike(conn, scope_type, scope_id, target, len(day_articles)),
                    _detect_sentiment_shift(conn, scope_type, scope_id, target, day_articles),
                    _detect_source_shift(conn, scope_type, scope_id, target, day_articles)):
            if det:
                dated.append(det)

    if scope_type == "brand":
        bid = int(scope_id)
        undated.extend(_brand_story_events(conn, bid, target))
        undated.extend(_brand_risk_events(conn, bid, target))
        undated.extend(_brand_alert_events(conn, bid, target))

    if use_llm and day_articles:
        known = _known_recent_titles(conn, scope_type, scope_id, target)
        undated.extend(_llm_extract_events(label, day_articles, known))

    candidates = sorted(dated, key=lambda e: _SIG_ORDER.get(e.get("significance", "medium"), 2)) + \
        sorted(undated, key=lambda e: _SIG_ORDER.get(e.get("significance", "medium"), 2))
    candidates = candidates[:MAX_DAILY_EVENTS_PER_SCOPE]

    created = deduped = 0
    try:
        for evt in candidates:
            outcome = upsert_event(conn, scope_type, scope_id, evt, target,
                                   dated_hash=evt in dated)
            if outcome == "created":
                created += 1
            else:
                deduped += 1
        conn.commit()
        _record_run(conn, scope_type, scope_id, "daily_extraction", target, "completed",
                    len(day_articles), created, deduped, time.monotonic() - t0)
    except Exception as e:
        conn.rollback()
        _record_run(conn, scope_type, scope_id, "daily_extraction", target, "failed",
                    len(day_articles), created, deduped, time.monotonic() - t0, str(e)[:500])
        raise
    if created or deduped:
        logger.info("Timeline: %s/%s %s — %d articles, %d created, %d deduped/bumped",
                    scope_type, label, target, len(day_articles), created, deduped)
    return {"articles_processed": len(day_articles),
            "events_created": created, "events_deduplicated": deduped}
