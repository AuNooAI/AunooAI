"""Shadow model-router judgment for Auspex chat turns, with the TypeSafe Jev model.

Every Auspex turn is routed by two regex classifiers (intent: casual / system /
research / general; depth: quick / standard / deep) and then sent to the same
model with the same retrieval budget regardless. The "model router" pattern
puts a cheap calibrated judgment in front of the expensive model instead: how
hard is this turn, does it need the article database at all, is it a follow-up
the conversation already answers. This shadow records that judgment for every
turn next to what the pipeline decided. Nothing on the chat path reads it and
the turn proceeds exactly as before.

Env:
    TYPESAFE_SHADOW_ROUTER   "1" to enable (needs TYPESAFE_API_KEY)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

USE_CASE = "services.auspex_route_shadow:judge"
DIFFICULTY_LEVELS = [
    "Routine: a lookup, a count, a recent-items list, a greeting or a question about the tool; a small model answers it well",
    "Analysis: a question needing several articles compared, summarised or explained; a capable mid-tier model",
    "Deep synthesis: multi-part, cross-topic or forecasting questions that need long-context reasoning; the flagship model earns its cost",
]


def enabled() -> bool:
    from app.services import typesafe_client
    return (os.getenv("TYPESAFE_SHADOW_ROUTER", "false").lower() in {"1", "true", "yes"}
            and typesafe_client.is_configured())


def _questions() -> Dict[str, Dict[str, Any]]:
    return {
        "intent": {
            "type": "choice",
            "instructions": "What kind of turn is `message`, given `conversation` and `topic`?",
            "criteria": {
                "casual": "A greeting, thanks, small talk, or a one-word acknowledgement",
                "system": "A question about the assistant itself, its features, what it can do or how to use it",
                "research": "A request to find, analyse, compare, summarise or forecast news coverage",
                "general": "Any other request, including questions answerable without the article database",
            },
        },
        "depth": {
            "type": "choice",
            "instructions": "How much of an answer does `message` call for?",
            "criteria": {
                "quick": "A short factual answer, a list, a number, a yes or no, a single headline",
                "standard": "A few paragraphs with sources",
                "deep": "A structured analysis: multi-part, comparative, trend or forecast, cross-topic",
            },
        },
        "needs_retrieval": {
            "type": "noul",
            "instructions": "Does answering `message` require searching the article database, rather than the conversation so far, general knowledge, or a description of the tool?",
            "criteria": {"true": "The answer depends on what the collected articles say", "false": "It can be answered without touching the article store"},
        },
        "followup": {
            "type": "noul",
            "instructions": "Is `message` a follow-up that can be answered from the articles and answers already in `conversation`, without a new search?",
            "criteria": {"true": "It refers to or narrows what was just discussed", "false": "It opens a new question or names things not yet discussed"},
        },
        "difficulty": {
            "type": "score",
            "instructions": "How hard is `message` for a language model to answer well, given `conversation` and `topic`?",
            "criteria": DIFFICULTY_LEVELS,
        },
    }


def _state(message: str, topic: Optional[str], history: List[Dict[str, Any]]) -> Dict[str, Any]:
    turns = []
    for m in history[-4:]:
        role = m.get("role"); content = str(m.get("content") or "")
        if role in ("user", "assistant") and content:
            turns.append({"role": role, "text": content[:600]})
    return {"topic": topic or "all topics", "conversation": turns, "message": (message or "")[:2000]}


def _judge(message: str, topic: Optional[str], history: List[Dict[str, Any]]) -> Dict[str, Any]:
    from app.services import typesafe_client
    started = time.monotonic()
    out = typesafe_client.system_one(_state(message, topic, history), _questions(), use_case=USE_CASE)
    latency_ms = int((time.monotonic() - started) * 1000)
    if not out:
        return {"jev_error": "no response", "jev_latency_ms": latency_ms}
    try:
        a = out["answers"]; it = a["intent"]; dp = a["depth"]; df = a["difficulty"]
        levels = max(1, len(DIFFICULTY_LEVELS) - 1)
        return {"jev_intent": it.get("choice"), "jev_intent_confidence": float(it.get("confidence") or 0.0),
                "jev_depth": dp.get("choice"), "jev_depth_confidence": float(dp.get("confidence") or 0.0),
                "jev_needs_retrieval": float(a["needs_retrieval"]["noul"]), "jev_followup": float(a["followup"]["noul"]),
                "jev_difficulty": max(0.0, min(1.0, float(df["score"]) / levels)),
                "jev_difficulty_confidence": float(df.get("confidence") or 0.0),
                "jev_model": out.get("model"), "jev_latency_ms": latency_ms, "jev_error": None}
    except (KeyError, TypeError, ValueError) as e:
        return {"jev_error": f"bad answers: {e}", "jev_latency_ms": latency_ms}


def _insert(row: Dict[str, Any]) -> None:
    from sqlalchemy import text
    from app.database import get_database_instance
    cols = ["chat_id", "topic", "message", "history_turns", "pipe_intent", "pipe_depth", "pipe_model", "pipe_limit",
            "jev_intent", "jev_intent_confidence", "jev_depth", "jev_depth_confidence", "jev_needs_retrieval",
            "jev_followup", "jev_difficulty", "jev_difficulty_confidence", "jev_model", "jev_latency_ms", "jev_error"]
    conn = get_database_instance()._temp_get_connection()
    try:
        conn.execute(text(f"INSERT INTO auspex_route_shadow ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"),
                     {c: row.get(c) for c in cols})
        conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[router shadow] insert failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def _run(chat_id: Optional[int], topic: Optional[str], message: str, history: List[Dict[str, Any]],
         pipe_intent: str, pipe_depth: str, pipe_model: str, pipe_limit: Optional[int]) -> None:
    ans = _judge(message, topic, history)
    row = {"chat_id": chat_id, "topic": topic, "message": (message or "")[:4000], "history_turns": len(history),
           "pipe_intent": pipe_intent, "pipe_depth": pipe_depth, "pipe_model": pipe_model, "pipe_limit": pipe_limit,
           "jev_intent": None, "jev_intent_confidence": None, "jev_depth": None, "jev_depth_confidence": None,
           "jev_needs_retrieval": None, "jev_followup": None, "jev_difficulty": None, "jev_difficulty_confidence": None,
           "jev_model": None, "jev_latency_ms": None, "jev_error": None}
    row.update(ans)
    _insert(row)
    if not ans.get("jev_error"):
        logger.info(f"🪞 [router shadow] chat {chat_id}: pipeline intent={pipe_intent} depth={pipe_depth} model={pipe_model} | "
                    f"jev intent={ans['jev_intent']} ({ans['jev_intent_confidence']:.2f}) depth={ans['jev_depth']} "
                    f"retrieval={ans['jev_needs_retrieval']:.2f} followup={ans['jev_followup']:.2f} "
                    f"difficulty={ans['jev_difficulty']:.2f} | {message[:60]!r}")


def schedule(chat_id: Optional[int], topic: Optional[str], message: str, history: List[Dict[str, Any]],
             pipe_intent: str, pipe_depth: str, pipe_model: str, pipe_limit: Optional[int] = None) -> bool:
    """Judge one chat turn on a daemon thread. Returns True when scheduled. Never raises."""
    try:
        if not enabled() or not (message or "").strip():
            return False
        snap = [{"role": m.get("role"), "content": str(m.get("content") or "")[:600]} for m in (history or [])[-6:]]
        t = threading.Thread(target=_run, name="auspex-router-shadow", daemon=True,
                             args=(chat_id, topic, message, snap, pipe_intent, pipe_depth, pipe_model, pipe_limit))
        t.start()
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[router shadow] could not schedule: {e}")
        return False
