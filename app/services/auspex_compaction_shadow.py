"""Shadow context compaction for Auspex chats, with the TypeSafe Jev model.

Auspex keeps the last six turns of a conversation verbatim and, once the
history passes 50k estimated tokens, summarises everything older with an LLM.
The context garbage-collection pattern from the field does it the other way
round: score each old message for whether it is needed to answer the current
question and drop the rest, so whatever survives keeps its exact figures,
quotes, paths and citations instead of a lossy paraphrase.

This shadow asks Jev that question for every prior message of a turn, in one
request (one Noul per message, plus one per message for "carries specifics a
summary would lose"), and records the answers beside what the compactor did
with the message. Nothing on the chat path reads it; the history the model
receives is unchanged.

Env:
    TYPESAFE_SHADOW_COMPACTION       "1" to enable (needs TYPESAFE_API_KEY)
    TYPESAFE_SHADOW_COMPACTION_MIN   prior messages needed before the shadow runs (default 2)
    TYPESAFE_SHADOW_COMPACTION_MAX   most recent prior messages judged per turn (default 40)
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

USE_CASE = "services.auspex_compaction_shadow:judge"
MSG_CHARS = 700          # per message sent as state
KEPT_TURNS = 6           # mirrors conversation_compactor.DEFAULT_RECENT_TURNS_TO_KEEP


def enabled() -> bool:
    from app.services import typesafe_client
    return (os.getenv("TYPESAFE_SHADOW_COMPACTION", "false").lower() in {"1", "true", "yes"}
            and typesafe_client.is_configured())


def _questions(n: int) -> Dict[str, Dict[str, Any]]:
    q: Dict[str, Dict[str, Any]] = {}
    for i in range(n):
        q[f"needed_{i}"] = {
            "type": "noul",
            "instructions": f"Is `history[{i}]` needed to answer `question` well? It is needed if the answer refers to it, narrows it, builds on data or sources it introduced, or would be wrong or incomplete without it.",
            "criteria": {"true": "Dropping this message would change or weaken the answer",
                         "false": "The answer can be given just as well without it"},
        }
        q[f"specifics_{i}"] = {
            "type": "noul",
            "instructions": f"Does `history[{i}]` carry specifics that a summary would lose: figures, dates, names, quotes, URLs or citations?",
            "criteria": {"true": "It contains concrete values or references", "false": "It is framing, small talk or a general statement"},
        }
    return q


def _judge(question: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
    from app.services import typesafe_client
    state = {"question": (question or "")[:2000],
             "history": [{"role": m.get("role"), "text": str(m.get("content") or "")[:MSG_CHARS]} for m in history]}
    started = time.monotonic()
    out = typesafe_client.system_one(state, _questions(len(history)), use_case=USE_CASE, timeout_s=20.0)
    latency_ms = int((time.monotonic() - started) * 1000)
    if not out:
        return {"error": "no response", "latency_ms": latency_ms}
    try:
        a = out["answers"]
        return {"needed": [float(a[f"needed_{i}"]["noul"]) for i in range(len(history))],
                "specifics": [float(a[f"specifics_{i}"]["noul"]) for i in range(len(history))],
                "model": out.get("model"), "latency_ms": latency_ms, "error": None}
    except (KeyError, TypeError, ValueError) as e:
        return {"error": f"bad answers: {e}", "latency_ms": latency_ms}


def _insert(rows: List[Dict[str, Any]]) -> int:
    from sqlalchemy import text
    from app.database import get_database_instance
    cols = ["chat_id", "turn_key", "question", "history_messages", "history_tokens_est", "compaction_applied",
            "msg_index", "role", "chars", "pipe_fate", "jev_needed", "jev_carries_specifics", "jev_model",
            "jev_latency_ms", "jev_error"]
    sql = text(f"INSERT INTO auspex_compaction_shadow ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})")
    conn = get_database_instance()._temp_get_connection()
    n = 0
    try:
        for r in rows:
            conn.execute(sql, {c: r.get(c) for c in cols})
            n += 1
        conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[compaction shadow] insert failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()
    return n


def _run(chat_id: Optional[int], question: str, history: List[Dict[str, Any]], offset: int,
         total: int, tokens_est: Optional[int], compaction_applied: bool) -> None:
    ans = _judge(question, history)
    turn_key = uuid.uuid4().hex[:16]
    rows = []
    for i, m in enumerate(history):
        idx = offset + i
        kept = idx >= total - KEPT_TURNS * 2
        fate = "kept" if kept else ("summarised" if compaction_applied else "untouched")
        rows.append({"chat_id": chat_id, "turn_key": turn_key, "question": (question or "")[:2000],
                     "history_messages": total, "history_tokens_est": tokens_est, "compaction_applied": compaction_applied,
                     "msg_index": idx, "role": m.get("role"), "chars": len(str(m.get("content") or "")), "pipe_fate": fate,
                     "jev_needed": (ans["needed"][i] if not ans.get("error") else None),
                     "jev_carries_specifics": (ans["specifics"][i] if not ans.get("error") else None),
                     "jev_model": ans.get("model"), "jev_latency_ms": ans.get("latency_ms"), "jev_error": ans.get("error")})
    n = _insert(rows)
    if not ans.get("error"):
        keep = sum(1 for v in ans["needed"] if v >= 0.5)
        chars_keep = sum(r["chars"] for r, v in zip(rows, ans["needed"]) if v >= 0.5)
        chars_all = sum(r["chars"] for r in rows)
        logger.info(f"🪞 [compaction shadow] chat {chat_id}: {n} prior messages, Jev keeps {keep} "
                    f"({chars_keep}/{chars_all} chars), pipeline {'summarised older turns' if compaction_applied else 'kept all'}; "
                    f"{ans['latency_ms']} ms | {question[:50]!r}")


def schedule(chat_id: Optional[int], question: str, history: List[Dict[str, Any]],
             tokens_est: Optional[int] = None, compaction_applied: bool = False) -> bool:
    """Judge the prior messages of one turn on a daemon thread. Never raises."""
    try:
        if not enabled():
            return False
        prior = [m for m in (history or []) if m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()]
        if len(prior) < int(os.getenv("TYPESAFE_SHADOW_COMPACTION_MIN", "2")):
            return False
        max_n = int(os.getenv("TYPESAFE_SHADOW_COMPACTION_MAX", "40"))
        total = len(prior)
        window = prior[-max_n:]
        offset = total - len(window)
        snap = [{"role": m.get("role"), "content": str(m.get("content") or "")[:4000]} for m in window]
        t = threading.Thread(target=_run, name="auspex-compaction-shadow", daemon=True,
                             args=(chat_id, question, snap, offset, total, tokens_est, bool(compaction_applied)))
        t.start()
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[compaction shadow] could not schedule: {e}")
        return False
