"""Shadow referee for observer-agent matches, with the TypeSafe Jev model.

An observer agent is a plain-English signal ("flag anything suggesting a
competitor is about to acquire a rival") evaluated by an LLM over batches of
articles. The matcher returns, per flagged article, a confidence, a threat
level and a summary; code validates the URI against the candidate set and
saves an alert. Nothing checks whether the flag was warranted, whether the
articles it did not flag should have been, or whether the summary says more
than the article does.

This shadow judges every article in the batch, flagged or not, against the
same signal: a Noul "does this article match the signal", a three-level
threat Score, and, for flagged articles, a Choice on whether the matcher's
summary is supported by the article. Rows land beside the matcher's verdict.
Nothing on the alert path reads them; the alerts are saved exactly as before.

Env:
    TYPESAFE_SHADOW_REFEREE       "1" to enable (needs TYPESAFE_API_KEY)
    TYPESAFE_SHADOW_REFEREE_MAX   articles judged per batch (default 60)
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

USE_CASE = "services.signal_referee_shadow:judge"
THREAT_LEVELS = [
    "Low: routine or background; no action needed beyond noting it",
    "Medium: worth an analyst's attention this week",
    "High: material to the organisation and time-sensitive",
]


def enabled() -> bool:
    from app.services import typesafe_client
    return (os.getenv("TYPESAFE_SHADOW_REFEREE", "false").lower() in {"1", "true", "yes"}
            and typesafe_client.is_configured())


def _field(a: Any, key: str, default: str = "") -> str:
    try:
        v = a.get(key) if hasattr(a, "get") else None
    except Exception:  # noqa: BLE001
        v = None
    if v is None and hasattr(a, "get"):
        md = a.get("metadata") if hasattr(a, "get") else None
        if isinstance(md, dict):
            v = md.get(key)
    return str(v) if v else default


def _questions(flagged: bool) -> Dict[str, Dict[str, Any]]:
    q: Dict[str, Dict[str, Any]] = {
        "matches": {
            "type": "noul",
            "instructions": "Does `article` match `signal.instruction`, read literally as an analyst wrote it? The article must itself report or show what the signal asks for, not merely be on a related topic.",
            "criteria": {"true": "An analyst who wrote this signal would want this article flagged",
                         "false": "The article does not show what the signal asks for, or only touches its topic"},
        },
        "threat": {
            "type": "score",
            "instructions": "If `article` matches `signal.instruction`, how serious is it for the organisation the signal was written for?",
            "criteria": THREAT_LEVELS,
        },
    }
    if flagged:
        q["summary_relation"] = {
            "type": "choice",
            "instructions": "How does `article` relate to `matcher_summary`, the sentence an automated matcher wrote about it? Judge only what the article states.",
            "criteria": {"supports": "The article states or directly implies everything the summary claims",
                         "contradicts": "The article states something different for the same thing",
                         "says_nothing": "The summary adds claims, actors, dates or figures the article does not contain"},
        }
    return q


def _judge(instruction: Dict[str, Any], article: Any, match: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    from app.services import typesafe_client
    flagged = match is not None
    state = {
        "signal": {"name": str(instruction.get("name") or ""), "instruction": str(instruction.get("instruction") or "")[:2000]},
        "article": {"title": _field(article, "title"), "source": _field(article, "news_source") or _field(article, "source"),
                    "published": _field(article, "publication_date")[:10], "text": (_field(article, "summary") or _field(article, "content"))[:2500]},
    }
    if flagged:
        state["matcher_summary"] = str(match.get("summary") or "")[:1000]
    started = time.monotonic()
    out = typesafe_client.system_one(state, _questions(flagged), use_case=USE_CASE)
    latency_ms = int((time.monotonic() - started) * 1000)
    if not out:
        return {"jev_error": "no response", "jev_latency_ms": latency_ms}
    try:
        a = out["answers"]; th = a["threat"]
        score = float(th["score"]); levels = max(1, len(THREAT_LEVELS) - 1)
        res = {"jev_matches": float(a["matches"]["noul"]), "jev_threat": max(0.0, min(1.0, score / levels)),
               "jev_threat_level": ["low", "medium", "high"][max(0, min(2, int(round(score))))],
               "jev_threat_confidence": float(th.get("confidence") or 0.0),
               "jev_summary_relation": None, "jev_summary_confidence": None,
               "jev_model": out.get("model"), "jev_latency_ms": latency_ms, "jev_error": None}
        if flagged and "summary_relation" in a:
            res["jev_summary_relation"] = a["summary_relation"].get("choice")
            res["jev_summary_confidence"] = float(a["summary_relation"].get("confidence") or 0.0)
        return res
    except (KeyError, TypeError, ValueError) as e:
        return {"jev_error": f"bad answers: {e}", "jev_latency_ms": latency_ms}


def decide_enabled() -> bool:
    from app.services import typesafe_client
    return (os.getenv("TYPESAFE_DECIDE_REFEREE", "false").lower() in {"1", "true", "yes"}
            and typesafe_client.is_configured())


def hold(instruction: Dict[str, Any], article: Any, match: Dict[str, Any]) -> bool:
    """The decision step, behind TYPESAFE_DECIDE_REFEREE: True when the alert
    should be saved as held (kept out of the email, listed for review) because
    Jev scores the cited article under TYPESAFE_DECIDE_REFEREE_MIN (default
    0.15) on "does this article match the instruction". Synchronous, one call.
    0.15 rather than 0.3 because on the eight labelled rows the lowest true
    match sat at 0.19 and the confident non-matches at 0.05 to 0.12.
    Any error means not held, so a Jev outage changes nothing.

    Justified by the blind labels of 19 Sept: of seven matcher flags Jev
    rejected, five were promos, awards and trend pieces. The shadow keeps
    recording every batch beside this, so a held alert is a row with
    matcher_flagged and jev_matches under the threshold.
    """
    try:
        if not decide_enabled() or not article:
            return False
        thr = float(os.getenv("TYPESAFE_DECIDE_REFEREE_MIN", "0.15"))
        ans = _judge(instruction, article, match)
        if ans.get("jev_error") or ans.get("jev_matches") is None:
            return False
        held = float(ans["jev_matches"]) < thr
        if held:
            logger.info(f"🎯 [referee hold] '{instruction.get('name')}': {_field(article, 'title')[:80]!r} "
                        f"held at jev_matches={ans['jev_matches']:.2f} < {thr}")
        return held
    except Exception as e:  # noqa: BLE001 — never block an alert on the referee
        logger.warning(f"[referee hold] failed, alert goes out: {e}")
        return False


def _insert(rows: List[Dict[str, Any]]) -> int:
    from sqlalchemy import text
    from app.database import get_database_instance
    cols = ["instruction_id", "instruction_name", "run_kind", "batch_key", "article_uri", "title",
            "matcher_flagged", "matcher_confidence", "matcher_threat", "matcher_summary",
            "jev_matches", "jev_threat", "jev_threat_level", "jev_threat_confidence",
            "jev_summary_relation", "jev_summary_confidence", "jev_model", "jev_latency_ms", "jev_error"]
    sql = text(f"INSERT INTO signal_referee_shadow ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})")
    conn = get_database_instance()._temp_get_connection()
    n = 0
    try:
        for r in rows:
            conn.execute(sql, {c: r.get(c) for c in cols})
            n += 1
        conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[referee shadow] insert failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()
    return n


def _run(instruction: Dict[str, Any], articles: List[Any], matches: Dict[str, Dict[str, Any]], run_kind: str) -> None:
    started = time.monotonic()
    batch_key = uuid.uuid4().hex[:16]
    with ThreadPoolExecutor(max_workers=8) as ex:
        answers = list(ex.map(lambda a: _judge(instruction, a, matches.get(_field(a, "uri"))), articles))
    rows = []
    for a, ans in zip(articles, answers):
        uri = _field(a, "uri"); m = matches.get(uri)
        row = {"instruction_id": instruction.get("id"), "instruction_name": str(instruction.get("name") or "")[:300],
               "run_kind": run_kind, "batch_key": batch_key, "article_uri": uri[:2000], "title": _field(a, "title")[:500],
               "matcher_flagged": m is not None,
               "matcher_confidence": (float(m.get("confidence")) if m and m.get("confidence") is not None else None),
               "matcher_threat": (str(m.get("threat_level")) if m else None),
               "matcher_summary": (str(m.get("summary") or "")[:1000] if m else None),
               "jev_matches": None, "jev_threat": None, "jev_threat_level": None, "jev_threat_confidence": None,
               "jev_summary_relation": None, "jev_summary_confidence": None, "jev_model": None,
               "jev_latency_ms": None, "jev_error": None}
        try:
            if row["matcher_confidence"] is not None:
                row["matcher_confidence"] = float(row["matcher_confidence"])
        except (TypeError, ValueError):
            row["matcher_confidence"] = None
        row.update(ans)
        rows.append(row)
    n = _insert(rows)
    ok = [r for r in rows if not r.get("jev_error")]
    flagged = [r for r in ok if r["matcher_flagged"]]
    missed = [r for r in ok if not r["matcher_flagged"] and (r["jev_matches"] or 0) >= 0.7]
    unwarranted = [r for r in flagged if (r["jev_matches"] or 0) < 0.3]
    unsupported = [r for r in flagged if r.get("jev_summary_relation") in ("contradicts", "says_nothing")]
    logger.info(f"🪞 [referee shadow] {run_kind} '{instruction.get('name')}': {n} articles, matcher flagged {len(flagged)}; "
                f"Jev: {len(unwarranted)} flagged-but-unwarranted, {len(missed)} unflagged-but-matching (≥0.7), "
                f"{len(unsupported)} summaries not supported; {time.monotonic() - started:.1f}s")


def schedule(instruction: Dict[str, Any], articles: List[Any], matches: Any, run_kind: str) -> bool:
    """Judge one matcher batch on a daemon thread. ``matches`` is the raw list the
    matcher returned; only entries with ``signal_detected`` count as flags.
    Returns True when scheduled. Never raises."""
    try:
        if not enabled() or not articles:
            return False
        from app.routes.vector_routes import _normalize_uri  # same normaliser as the candidate-set gate
        by_norm = {_normalize_uri(_field(a, "uri")): _field(a, "uri") for a in articles if _field(a, "uri")}
        flagged: Dict[str, Dict[str, Any]] = {}
        for m in (matches or []):
            if isinstance(m, dict) and m.get("signal_detected"):
                uri = by_norm.get(_normalize_uri(str(m.get("article_uri") or "")))
                if uri:
                    flagged[uri] = m
        max_n = int(os.getenv("TYPESAFE_SHADOW_REFEREE_MAX", "60"))
        snap = []
        for a in articles[:max_n]:
            snap.append({k: _field(a, k) for k in ("uri", "title", "summary", "content", "news_source", "source", "publication_date")})
        inst = {"id": instruction.get("id"), "name": instruction.get("name"), "instruction": instruction.get("instruction")}
        t = threading.Thread(target=_run, name="signal-referee-shadow", daemon=True,
                             args=(inst, snap, flagged, run_kind))
        t.start()
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[referee shadow] could not schedule: {e}")
        return False
