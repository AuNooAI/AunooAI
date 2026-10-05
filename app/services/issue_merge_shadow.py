"""Shadow same-event judgment for brand-risk issue merges, with the TypeSafe Jev model.

The issue builder decides whether a newly risk-flagged article belongs to an
existing issue by cosine similarity to the issue's centroid: attach above
0.99, ask a cheap LLM "same event?" between 0.85 and 0.99, open a new issue
below. TypeSafe's entity-alignment recipe replaces the threshold with one
three-level Score whose levels are the three things you can do with a pair
(leave apart, send to a curator, merge) and adds per-aspect Nouls so a
curator sees which aspect disagrees.

This shadow records that judgment for every pair the builder looks at,
next to what the builder did. It never changes the decision. It also has a
replay entry point so pairs from existing issues can be scored without
waiting for new risk-flagged articles.

Env:
    TYPESAFE_SHADOW_MERGE   "1" to enable (needs TYPESAFE_API_KEY)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

USE_CASE = "services.issue_merge_shadow:judge"
LEVELS = [
    "Different event: two separate developments, even if on the same broad topic or about the same company (two different lawsuits, two different scandals)",
    "Related, possibly the same: the same thread or a follow-up, but the pieces may describe distinct developments; a person should decide",
    "Same event: the same underlying development or a direct continuation of one ongoing story (including a recurring stream of the same signal about the same company)",
]


def enabled() -> bool:
    from app.services import typesafe_client
    return (os.getenv("TYPESAFE_SHADOW_MERGE", "false").lower() in {"1", "true", "yes"}
            and typesafe_client.is_configured())


def _questions() -> Dict[str, Dict[str, Any]]:
    return {
        "relation": {
            "type": "score",
            "instructions": "How does `article` relate to `issue`? The issue is an existing group of articles; `issue.examples` are titles already in it.",
            "criteria": LEVELS,
        },
        "same_action": {
            "type": "noul",
            "instructions": "Do `article` and `issue` describe the same concrete event or action (the same deal, ruling, retraction, review, incident), rather than two different ones?",
            "criteria": {"true": "One event, reported or continued", "false": "Different events, even if similar in kind"},
        },
        "same_actors": {
            "type": "noul",
            "instructions": "Are the same named people or organisations the ones acting in `article` and in `issue`?",
            "criteria": {"true": "The same named actors do the acting in both", "false": "Different actors, or the shared name is only the monitored brand mentioned in passing"},
        },
        "same_period": {
            "type": "noul",
            "instructions": "Do `article` and `issue` refer to the same time period, or is `article` a continuation of the issue's story rather than a separate later occurrence?",
            "criteria": {"true": "Same period or a direct continuation", "false": "A separate occurrence at another time"},
        },
    }


def _issue_examples(conn, issue_id: int, limit: int = 5) -> List[str]:
    from sqlalchemy import text
    try:
        rows = conn.execute(text("""
            SELECT a.title FROM bw_issue_articles ia JOIN articles a ON a.uri = ia.article_uri
            WHERE ia.issue_id = :i ORDER BY ia.added_at DESC LIMIT :n
        """), {"i": issue_id, "n": limit}).fetchall()
        return [str(r[0]) for r in rows if r and r[0]]
    except Exception:  # noqa: BLE001
        return []


def judge(article_title: str, article_summary: str, pub_date: str,
          issue_title: str, issue_examples: List[str], issue_last_seen: str = "") -> Dict[str, Any]:
    """One Jev request for one pair. Returns the jev_* fields; never raises."""
    from app.services import typesafe_client
    state = {
        "article": {"title": article_title or "", "summary": (article_summary or "")[:900],
                    "published": str(pub_date or "")[:10]},
        "issue": {"title": issue_title or "", "examples": issue_examples[:5],
                  "last_seen": str(issue_last_seen or "")[:10]},
    }
    started = time.monotonic()
    out = typesafe_client.system_one(state, _questions(), use_case=USE_CASE)
    latency_ms = int((time.monotonic() - started) * 1000)
    if not out:
        return {"jev_error": "no response", "jev_latency_ms": latency_ms}
    try:
        a = out["answers"]
        rel = a["relation"]; probs = rel.get("probabilities") or {}
        score = float(rel["score"])
        level = ["different", "related", "same"][max(0, min(2, int(round(score))))]
        return {
            "jev_score": max(0.0, min(1.0, score / 2.0)), "jev_level": level,
            "jev_p_different": float(probs.get("0", 0.0)), "jev_p_related": float(probs.get("1", 0.0)),
            "jev_p_same": float(probs.get("2", 0.0)), "jev_confidence": float(rel.get("confidence") or 0.0),
            "jev_same_action": float(a["same_action"]["noul"]), "jev_same_actors": float(a["same_actors"]["noul"]),
            "jev_same_period": float(a["same_period"]["noul"]),
            "jev_model": out.get("model"), "jev_latency_ms": latency_ms, "jev_error": None,
        }
    except (KeyError, TypeError, ValueError) as e:
        return {"jev_error": f"bad answers: {e}", "jev_latency_ms": latency_ms}


def insert(row: Dict[str, Any], conn=None) -> None:
    from sqlalchemy import text
    from app.database import get_database_instance
    own = conn is None
    if own:
        conn = get_database_instance()._temp_get_connection()
    base = {"brand_id": None, "article_uri": "", "article_title": None, "issue_id": None, "issue_title": None,
            "issue_members": None, "cosine_sim": None, "pipe_decision": "unknown", "jev_score": None,
            "jev_level": None, "jev_p_different": None, "jev_p_related": None, "jev_p_same": None,
            "jev_confidence": None, "jev_same_action": None, "jev_same_actors": None, "jev_same_period": None,
            "jev_model": None, "jev_latency_ms": None, "jev_error": None}
    base.update(row)
    try:
        conn.execute(text("""
            INSERT INTO issue_merge_shadow
                (brand_id, article_uri, article_title, issue_id, issue_title, issue_members, cosine_sim, pipe_decision,
                 jev_score, jev_level, jev_p_different, jev_p_related, jev_p_same, jev_confidence,
                 jev_same_action, jev_same_actors, jev_same_period, jev_model, jev_latency_ms, jev_error)
            VALUES
                (:brand_id, :article_uri, :article_title, :issue_id, :issue_title, :issue_members, :cosine_sim, :pipe_decision,
                 :jev_score, :jev_level, :jev_p_different, :jev_p_related, :jev_p_same, :jev_confidence,
                 :jev_same_action, :jev_same_actors, :jev_same_period, :jev_model, :jev_latency_ms, :jev_error)
        """), base)
        if own:
            conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[merge shadow] insert failed: {e}")
        if own:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if own:
            conn.close()


def _run(brand_id: int, uri: str, title: str, summary: str, pub_date: str,
         cand: Dict[str, Any], decision: str) -> None:
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        examples = _issue_examples(conn, int(cand["issue_id"]))
    finally:
        conn.close()
    ans = judge(title, summary, pub_date, cand.get("title") or "", examples)
    row = {"brand_id": brand_id, "article_uri": (uri or "")[:2000], "article_title": (title or "")[:500],
           "issue_id": cand.get("issue_id"), "issue_title": (cand.get("title") or "")[:500],
           "issue_members": len(examples), "cosine_sim": cand.get("sim"), "pipe_decision": decision}
    row.update(ans)
    insert(row)
    if not ans.get("jev_error"):
        logger.info(f"🪞 [merge shadow] brand {brand_id} sim={cand.get('sim'):.3f} pipeline={decision} "
                    f"jev={ans['jev_level']} ({ans['jev_confidence']:.2f}) | {title[:50]!r} vs {str(cand.get('title'))[:40]!r}")


def schedule(brand_id: int, uri: str, title: str, summary: str, pub_date: str,
             cand: Optional[Dict[str, Any]], decision: str) -> bool:
    """Record Jev's judgment for one (article, best candidate issue) pair on a
    daemon thread. Called after the builder has decided; never raises."""
    try:
        if not cand or not enabled():
            return False
        t = threading.Thread(target=_run, name="merge-shadow", daemon=True,
                             args=(int(brand_id), uri, title or "", summary or "", str(pub_date or ""),
                                   dict(cand), decision))
        t.start()
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[merge shadow] could not schedule: {e}")
        return False
