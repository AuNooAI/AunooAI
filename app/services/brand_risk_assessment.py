"""Brand Risk v2 — issue builder and assessment reader.

docs/BRAND_RISK_BENCHMARK_SPEC.md. Two halves:

- build_issues_for_brand(): groups risk-flagged articles (bw_article_risks) into
  issues — one underlying event, assessed once. Merge order: analyst override,
  shared syndication story group, embedding similarity to the issue centroid
  (>= 0.85 auto-merge, 0.70-0.85 cheap-LLM confirmation), else a new issue.
  Analyst overrides (bw_issue_overrides) always win and survive rebuilds.

- get_assessment(): active issues as of a date (severity-scaled expiry:
  high 28d / medium 14d / low 7d without new coverage), an attention readout
  (coverage vs the brand's own weekly average, direct articles queries — NOT
  bw_daily_stats, which stores cumulative snapshots), peer sector-wide flags,
  and the customer's escalation tier. No 0-100 score exists anywhere here.

Everything the customer sees is deterministic given stored verdicts; LLM use is
confined to the merge-confirmation call.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

ISSUE_EXPIRY_DAYS = {"high": 28, "medium": 14, "low": 7}
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}

# Measured on wbm (2026-08-14): distinct events score up to 0.982 on the 768-d
# encoder — same-topic and same-story are inseparable by similarity alone, so
# embedding NOMINATES candidates and the LLM confirmation decides. Auto-merge
# only for near-duplicates; syndicated copies are caught by story groups anyway.
AUTO_MERGE_SIM = 0.99      # cosine similarity: attach without asking (near-dupes only)
CONFIRM_SIM = 0.85         # 0.85-0.99: ask the cheap LLM; below: new issue
CANDIDATE_WINDOW_DAYS = 45  # only issues with coverage this recent are merge candidates
CONFIRM_MODEL = "gpt-5.4-mini"

# Recurring same-source signal streams (not discrete events): all of a brand's
# risk-flagged articles from such a source form ONE continuing issue,
# deterministically — the LLM same-event question is ill-posed for review pairs
# and answers it inconsistently, fragmenting the stream into singletons.
STREAM_SOURCES = {"glassdoor"}

PEER_MIN_ARTICLES = 20     # scored distinct articles in-window to make a peer eligible
PEER_MIN_PEERS = 2         # eligible peers needed before sector-wide is customer-facing

ATTENTION_MIN_HISTORY_DAYS = 56   # ~8 weeks of history before a multiple is claimed
ATTENTION_SPIKE_MULTIPLE = 2.0
ATTENTION_SPIKE_MIN_COUNT = 3

_SCORED = "COALESCE(a.sentiment, '') <> ''"
_REL = "COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4"


def _day(date_str: str) -> str:
    return (date_str or "")[:10]


def _shift(date_str: str, days: int) -> str:
    return (datetime.strptime(_day(date_str), "%Y-%m-%d")
            + timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Issue builder
# ---------------------------------------------------------------------------

def _issue_members_findings(conn, issue_id: int):
    return conn.execute(text("""
        SELECT r.risk_type, r.severity, r.confidence, r.justification
        FROM bw_issue_articles ia
        JOIN bw_article_risks r
          ON r.article_uri = ia.article_uri AND r.brand_id = ia.brand_id
        WHERE ia.issue_id = :iid
    """), {"iid": issue_id}).fetchall()


def _refresh_issue(conn, issue_id: int) -> None:
    """Recompute severity, primary/secondary types, justification, and the
    seen-range from the issue's current members."""
    findings = _issue_members_findings(conn, issue_id)
    if not findings:
        return
    top = max(findings, key=lambda f: (SEVERITY_ORDER.get(f[1], 0), f[2] or 0.0))
    types = sorted({f[0] for f in findings} - {top[0]})
    rng = conn.execute(text("""
        SELECT MIN(a.publication_date), MAX(a.publication_date)
        FROM bw_issue_articles ia JOIN articles a ON a.uri = ia.article_uri
        WHERE ia.issue_id = :iid
    """), {"iid": issue_id}).fetchone()
    conn.execute(text("""
        UPDATE bw_issues SET severity = :sev, primary_type = :pt,
               secondary_types = :st, justification = COALESCE(:j, justification),
               first_seen = COALESCE(:fs, first_seen),
               last_seen = COALESCE(:ls, last_seen), updated_at = NOW()
        WHERE id = :iid
    """), {"iid": issue_id, "sev": top[1], "pt": top[0],
           "st": json.dumps(types), "j": top[3],
           "fs": _day(rng[0] or ""), "ls": _day(rng[1] or "")})


def _attach(conn, issue_id: int, brand_id: int, uri: str,
            similarity: Optional[float], method: str) -> None:
    conn.execute(text("""
        INSERT INTO bw_issue_articles (issue_id, article_uri, brand_id, similarity, merge_method)
        VALUES (:iid, :u, :b, :sim, :m)
        ON CONFLICT (brand_id, article_uri) DO NOTHING
    """), {"iid": issue_id, "u": uri, "b": brand_id, "sim": similarity, "m": method})
    _refresh_issue(conn, issue_id)


def _new_issue(conn, brand_id: int, uri: str, title: str, pub_date: str) -> int:
    iid = conn.execute(text("""
        INSERT INTO bw_issues (brand_id, title, primary_type, secondary_types,
                               severity, first_seen, last_seen)
        VALUES (:b, :t, 'unclassified', '[]', 'low', :d, :d) RETURNING id
    """), {"b": brand_id, "t": (title or "Untitled issue")[:300],
           "d": _day(pub_date)}).fetchone()[0]
    _attach(conn, iid, brand_id, uri, None, "seed")
    return iid


def _stream_candidate(conn, brand_id: int, source: str, pub_date: str) -> Optional[int]:
    """The brand's open issue made up entirely of articles from the same stream
    source (e.g. Glassdoor reviews), if one exists in the candidate window."""
    cutoff = _shift(pub_date, -CANDIDATE_WINDOW_DAYS)
    row = conn.execute(text("""
        SELECT ia.issue_id
        FROM bw_issue_articles ia
        JOIN bw_issues i ON i.id = ia.issue_id
        JOIN articles a ON a.uri = ia.article_uri
        WHERE ia.brand_id = :bid AND i.last_seen >= :cutoff
        GROUP BY ia.issue_id
        HAVING bool_and(LOWER(COALESCE(a.news_source, '')) = :src)
        ORDER BY MAX(a.publication_date) DESC LIMIT 1
    """), {"bid": brand_id, "cutoff": cutoff, "src": source}).fetchone()
    return row[0] if row else None


def _story_group_candidate(conn, brand_id: int, uri: str) -> Optional[int]:
    row = conn.execute(text("""
        SELECT ia.issue_id FROM bw_article_stories s1
        JOIN bw_article_stories s2
          ON s2.story_group_id = s1.story_group_id AND s2.brand_id = s1.brand_id
        JOIN bw_issue_articles ia
          ON ia.article_uri = s2.article_uri AND ia.brand_id = :bid
        WHERE s1.article_uri = :uri AND s1.brand_id = :bid
        LIMIT 1
    """), {"uri": uri, "bid": brand_id}).fetchone()
    return row[0] if row else None


def _best_embedding_candidate(conn, brand_id: int, uri: str,
                              pub_date: str) -> Optional[Dict[str, Any]]:
    """Highest cosine similarity between the article and the centroid of any
    recent issue. Returns {issue_id, title, sim} or None."""
    cutoff = _shift(pub_date, -CANDIDATE_WINDOW_DAYS)
    row = conn.execute(text("""
        WITH cent AS (
            SELECT ia.issue_id, AVG(m.embedding) AS emb
            FROM bw_issue_articles ia
            JOIN bw_issues i ON i.id = ia.issue_id
            JOIN articles m ON m.uri = ia.article_uri
            WHERE ia.brand_id = :bid AND i.last_seen >= :cutoff
              AND m.embedding IS NOT NULL
            GROUP BY ia.issue_id
        )
        SELECT c.issue_id, i.title,
               1 - (c.emb <=> (SELECT embedding FROM articles WHERE uri = :uri)) AS sim
        FROM cent c JOIN bw_issues i ON i.id = c.issue_id
        WHERE (SELECT embedding FROM articles WHERE uri = :uri) IS NOT NULL
        ORDER BY sim DESC LIMIT 1
    """), {"bid": brand_id, "uri": uri, "cutoff": cutoff}).fetchone()
    if not row or row[2] is None:
        return None
    return {"issue_id": row[0], "title": row[1], "sim": float(row[2])}


async def _llm_confirm_merge(article_title: str, article_summary: str,
                             issue_title: str) -> bool:
    """Borderline-similarity merges get a one-line same-event check. On any
    failure the answer is no — a wrong split is cheaper to correct than a
    wrong merge."""
    from app.ai_models import LiteLLMModel, extract_content
    prompt = (f'Are these two items about the SAME underlying event, or direct '
              f'continuations of one ongoing story?\n'
              f'A: {article_title} — {(article_summary or "")[:400]}\n'
              f'B: {issue_title}\n'
              f'Rules:\n'
              f'- Two different events on the same broad topic (e.g. two separate '
              f'publishing-integrity scandals, two different lawsuits) are NOT the same.\n'
              f'- A recurring stream of the same signal about the same company (e.g. '
              f'employee reviews on the same themes) IS one continuing story.\n'
              f'Answer with ONLY JSON: {{"same_event": true|false, "why": "one sentence"}}')
    try:
        model = LiteLLMModel.get_instance(CONFIRM_MODEL)
        resp = await model.agenerate_response(
            [{"role": "user", "content": prompt}], max_tokens=100, temperature=0.0)
        raw = extract_content(resp).strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        return bool(m and json.loads(m.group(0)).get("same_event") is True)
    except Exception as e:
        logger.debug(f"merge confirmation failed: {e}")
        return False


async def build_issues_for_brand(conn, brand_id: int) -> Dict[str, int]:
    """Assign every not-yet-assigned risk-flagged article to an issue.
    Incremental and idempotent; analyst overrides always win. The caller owns
    the transaction."""
    stats = {"attached": 0, "created": 0, "skipped": 0}
    rows = conn.execute(text("""
        SELECT a.uri, a.title, LEFT(COALESCE(a.summary, ''), 600), a.publication_date,
               COALESCE(a.news_source, '')
        FROM articles a
        WHERE EXISTS (SELECT 1 FROM bw_article_risks r
                      WHERE r.article_uri = a.uri AND r.brand_id = :bid)
          AND NOT EXISTS (SELECT 1 FROM bw_issue_articles ia
                          WHERE ia.article_uri = a.uri AND ia.brand_id = :bid)
        ORDER BY a.publication_date
    """), {"bid": brand_id}).fetchall()
    for uri, title, summary, pub_date, news_source in rows:
        override = conn.execute(text("""
            SELECT action, target_issue_id FROM bw_issue_overrides
            WHERE brand_id = :bid AND article_uri = :uri
        """), {"bid": brand_id, "uri": uri}).fetchone()
        if override:
            action, target = override
            if action == "detach":
                stats["skipped"] += 1
            elif action == "attach" and target:
                _attach(conn, target, brand_id, uri, None, "override")
                stats["attached"] += 1
            continue
        src = news_source.strip().lower()
        if src in STREAM_SOURCES:
            iid = _stream_candidate(conn, brand_id, src, pub_date)
            if iid:
                _attach(conn, iid, brand_id, uri, None, "stream")
                stats["attached"] += 1
                continue
            _new_issue(conn, brand_id, uri, title, pub_date)
            stats["created"] += 1
            continue
        iid = _story_group_candidate(conn, brand_id, uri)
        if iid:
            _attach(conn, iid, brand_id, uri, None, "story_group")
            stats["attached"] += 1
            continue
        cand = _best_embedding_candidate(conn, brand_id, uri, pub_date)
        if cand and cand["sim"] >= AUTO_MERGE_SIM:
            _attach(conn, cand["issue_id"], brand_id, uri, cand["sim"], "embedding")
            stats["attached"] += 1
        elif cand and cand["sim"] >= CONFIRM_SIM and \
                await _llm_confirm_merge(title or "", summary or "", cand["title"]):
            _attach(conn, cand["issue_id"], brand_id, uri, cand["sim"], "llm_confirm")
            stats["attached"] += 1
        else:
            _new_issue(conn, brand_id, uri, title, pub_date)
            stats["created"] += 1
    return stats


# ---------------------------------------------------------------------------
# Assessment reader (no LLM)
# ---------------------------------------------------------------------------

def active_issues_as_of(conn, brand_id: int, end: str) -> List[Dict[str, Any]]:
    """Issues active as of `end`: first coverage on or before `end`, last
    coverage within the severity-scaled expiry window before `end`. Evaluated
    against the date asked for — never against today — so historical reports
    and calibration runs reproduce."""
    end_d = _day(end)
    rows = conn.execute(text("""
        SELECT id, title, primary_type, secondary_types, severity,
               justification, first_seen, last_seen
        FROM bw_issues WHERE brand_id = :bid AND first_seen <= :end
        ORDER BY last_seen DESC
    """), {"bid": brand_id, "end": end_d + "~"}).fetchall()
    out = []
    for iid, title, ptype, stypes, sev, just, fs, ls in rows:
        cutoff = _shift(end_d, -ISSUE_EXPIRY_DAYS.get(sev, 14))
        if _day(ls) < cutoff:
            continue
        detail = conn.execute(text("""
            SELECT COUNT(DISTINCT ia.article_uri),
                   COUNT(DISTINCT a.news_source),
                   COUNT(DISTINCT ia.article_uri) FILTER (WHERE a.publication_date >= :recent),
                   COUNT(DISTINCT a.news_source) FILTER (WHERE a.publication_date < :recent)
            FROM bw_issue_articles ia JOIN articles a ON a.uri = ia.article_uri
            WHERE ia.issue_id = :iid AND a.publication_date <= :end
        """), {"iid": iid, "recent": _shift(end_d, -7), "end": end_d + "~"}).fetchone()
        n_articles, n_sources, recent_articles, sources_before = detail
        # spreading = the last 7 days brought coverage from a source the issue
        # had not seen before; persisting = same sources still writing.
        if recent_articles and n_sources > (sources_before or 0):
            momentum = "spreading"
        elif recent_articles:
            momentum = "persisting"
        else:
            momentum = "fading"
        if isinstance(stypes, str):
            try:
                stypes = json.loads(stypes)
            except Exception:
                stypes = []
        out.append({"id": iid, "title": title, "primary_type": ptype,
                    "secondary_types": stypes or [], "severity": sev,
                    "justification": just, "first_seen": _day(fs),
                    "last_seen": _day(ls), "articles": n_articles or 0,
                    "sources": n_sources or 0, "momentum": momentum})
    out.sort(key=lambda i: i["last_seen"], reverse=True)
    out.sort(key=lambda i: SEVERITY_ORDER.get(i["severity"], 0), reverse=True)
    return out


def _attention(conn, brand_id: int, end: str) -> Dict[str, Any]:
    """Coverage in the 7 days ending at `end` vs the brand's own weekly average
    over prior history (direct articles queries; min ~8 weeks of history)."""
    end_d = _day(end)
    week_ago = _shift(end_d, -7)
    hist = conn.execute(text(f"""
        SELECT MIN(a.publication_date)
        FROM bw_article_categories bac JOIN articles a ON a.uri = bac.article_uri
        WHERE bac.brand_id = :bid AND {_REL}
    """), {"bid": brand_id}).fetchone()
    hist_start = _day(hist[0] or "")
    if not hist_start or (datetime.strptime(week_ago, "%Y-%m-%d")
                          - datetime.strptime(hist_start, "%Y-%m-%d")).days < ATTENTION_MIN_HISTORY_DAYS:
        return {"available": False,
                "reason": f"needs {ATTENTION_MIN_HISTORY_DAYS} days of prior coverage history"}
    hist_weeks = max(1.0, (datetime.strptime(week_ago, "%Y-%m-%d")
                           - datetime.strptime(hist_start, "%Y-%m-%d")).days / 7.0)
    rows = conn.execute(text(f"""
        SELECT bac.category,
               COUNT(DISTINCT a.uri) FILTER (
                   WHERE a.publication_date >= :wk AND a.publication_date <= :end) AS recent,
               COUNT(DISTINCT a.uri) FILTER (WHERE a.publication_date < :wk) AS hist
        FROM bw_article_categories bac JOIN articles a ON a.uri = bac.article_uri
        WHERE bac.brand_id = :bid AND {_REL}
        GROUP BY bac.category
    """), {"bid": brand_id, "wk": week_ago, "end": end_d + "~"}).fetchall()
    spikes, total_recent, total_hist = [], 0, 0
    for cat, recent, hist_n in rows:
        total_recent += recent or 0
        total_hist += hist_n or 0
        weekly_avg = (hist_n or 0) / hist_weeks
        if weekly_avg > 0 and recent >= ATTENTION_SPIKE_MIN_COUNT \
                and recent >= ATTENTION_SPIKE_MULTIPLE * weekly_avg:
            spikes.append({"category": cat, "recent": recent,
                           "weekly_avg": round(weekly_avg, 1),
                           "multiple": round(recent / weekly_avg, 1)})
    overall_avg = total_hist / hist_weeks
    spikes.sort(key=lambda s: -s["multiple"])
    return {"available": True, "window_days": 7,
            "overall_recent": total_recent,
            "overall_weekly_avg": round(overall_avg, 1),
            "overall_multiple": (round(total_recent / overall_avg, 1)
                                 if overall_avg > 0 else None),
            "category_spikes": spikes}


def _eligible_peers(conn, brand_id: int, start: str, end: str) -> List[Dict[str, Any]]:
    rows = conn.execute(text(f"""
        SELECT b.id, COALESCE(b.display_name, b.name), COUNT(DISTINCT a.uri) AS n
        FROM bw_brands b
        JOIN bw_article_categories bac ON bac.brand_id = b.id
        JOIN articles a ON a.uri = bac.article_uri
        WHERE b.id <> :bid AND {_REL} AND {_SCORED}
          AND a.publication_date >= :start AND a.publication_date <= :end
        GROUP BY b.id, COALESCE(b.display_name, b.name)
        HAVING COUNT(DISTINCT a.uri) >= :minn
    """), {"bid": brand_id, "start": _day(start), "end": _day(end) + "~",
           "minn": PEER_MIN_ARTICLES}).fetchall()
    return [{"id": r[0], "name": r[1], "articles": r[2]} for r in rows]


def _peer_matches_for_issue(conn, issue_id: int, peer_ids: List[int],
                            start: str, end: str) -> List[int]:
    """Peers with at least one in-window article >= AUTO_MERGE_SIM similar to
    the issue centroid — the same matcher the issue builder uses."""
    if not peer_ids:
        return []
    rows = conn.execute(text(f"""
        WITH cent AS (
            SELECT AVG(m.embedding) AS emb FROM bw_issue_articles ia
            JOIN articles m ON m.uri = ia.article_uri
            WHERE ia.issue_id = :iid AND m.embedding IS NOT NULL
        )
        SELECT DISTINCT bac.brand_id
        FROM bw_article_categories bac
        JOIN articles a ON a.uri = bac.article_uri, cent
        WHERE bac.brand_id = ANY(:peers) AND {_REL}
          AND a.publication_date >= :start AND a.publication_date <= :end
          AND a.embedding IS NOT NULL AND cent.emb IS NOT NULL
          AND 1 - (a.embedding <=> cent.emb) >= :sim
    """), {"iid": issue_id, "peers": peer_ids, "start": _day(start),
           "end": _day(end) + "~", "sim": AUTO_MERGE_SIM}).fetchall()
    return [r[0] for r in rows]


def get_assessment(conn, brand_id: int, start: str, end: str) -> Dict[str, Any]:
    """The full v2 assessment: active issues as of `end`, attention readout,
    peer context, escalation tier. Deterministic — no LLM calls, no score."""
    issues = active_issues_as_of(conn, brand_id, end)
    peers = _eligible_peers(conn, brand_id, start, end)
    peer_facing = len(peers) >= PEER_MIN_PEERS
    peer_by_id = {p["id"]: p["name"] for p in peers}
    for issue in issues:
        matched = _peer_matches_for_issue(conn, issue["id"], list(peer_by_id),
                                          start, end)
        issue["sector_wide"] = sorted(peer_by_id[m] for m in matched)
        issue["sector_wide_display"] = peer_facing and bool(matched)
    risk_level = max((i["severity"] for i in issues),
                     key=lambda s: SEVERITY_ORDER.get(s, 0), default=None)
    tier = None
    try:
        from app.services.escalation_tiers import evaluate_brand_tier
        tier = evaluate_brand_tier(conn, brand_id)
    except Exception:
        logger.exception("tier evaluation failed for brand %s", brand_id)
    return {"brand_id": brand_id, "start": _day(start), "end": _day(end),
            "risk_level": risk_level, "active_issues": issues,
            "attention": _attention(conn, brand_id, end),
            "eligible_peers": peers if peer_facing else [],
            "escalation_tier": tier}
