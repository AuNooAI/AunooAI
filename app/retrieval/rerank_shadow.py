"""Shadow rerank of Auspex retrievals with the TypeSafe Jev model, brand and
market topics only.

The shared cross-encoder (BAAI/bge-reranker-v2-m3) reorders vector candidates
for every Auspex path. On theme topics it works (AUC 0.885); on brand and
market topics it scores at chance (AUC 0.478), because "is this about SAGE
Publishing rather than sage the herb" is entity disambiguation, which a
semantic reranker cannot do. TypeSafe's re-ranking recipe scores each
query-candidate pair with one Noul whose criteria carry the definition of
relevant; that is what runs here.

After ``rerank()`` has produced its order, every candidate in the scored
pool is sent to Jev with the query, the topic's definition (entity plus
keywords for a brand, market definition plus vendor terms for a market) and
two questions: does this candidate answer the query, and is it about the
monitored entity or market at all. Rows land in ``rerank_shadow`` with the
cosine rank, the cross-encoder rank and score, and whether the candidate
made the top_k. The order the caller receives is never changed.

Env:
    TYPESAFE_SHADOW_RERANK   "1" to enable (needs TYPESAFE_API_KEY)
    TYPESAFE_SHADOW_RERANK_MAX  candidates per call (default 60)
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

USE_CASE = "retrieval.rerank_shadow:score"
_BRAND_RE = re.compile(r"^Brand Monitoring\s+(.+)$|^(.+?)\s-\sBrand Watch$", re.I)
_MARKET_RE = re.compile(r"^Market Monitoring\s+(.+)$", re.I)


def topic_kind(topic: Optional[str]) -> Optional[str]:
    if not topic:
        return None
    if _MARKET_RE.match(topic):
        return "market"
    if _BRAND_RE.match(topic):
        return "brand"
    return None


def enabled() -> bool:
    from app.services import typesafe_client
    return (os.getenv("TYPESAFE_SHADOW_RERANK", "false").lower() in {"1", "true", "yes"}
            and typesafe_client.is_configured())


def _entity_name(topic: str, kind: str) -> str:
    m = _MARKET_RE.match(topic) if kind == "market" else _BRAND_RE.match(topic)
    if not m:
        return topic
    return (m.group(1) or (m.group(2) if m.lastindex and m.lastindex >= 2 else None) or topic).strip()


def _keywords_for_topic(topic: str) -> List[str]:
    """The monitor's own search terms, so the definition names what the
    analyst means by the topic (the same lesson as the relevance judge)."""
    try:
        from sqlalchemy import text
        from app.database import get_database_instance
        conn = get_database_instance()._temp_get_connection()
        try:
            rows = conn.execute(text(
                "SELECT DISTINCT mk.keyword FROM monitored_keywords mk "
                "JOIN keyword_groups g ON g.id = mk.group_id WHERE g.topic = :t"
            ), {"t": topic}).fetchall()
        finally:
            conn.close()
        return [str(r[0]) for r in rows if r and r[0]][:25]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[rerank shadow] keyword lookup failed for {topic!r}: {e}")
        return []


def _definition(topic: str, kind: str, keywords: List[str]) -> Tuple[str, Dict[str, str]]:
    name = _entity_name(topic, kind)
    if kind == "market":
        return (
            f"The {name} market: its technology, products, vendors, buyers, adoption, pricing, funding, "
            f"acquisitions, partnerships, leadership, analyst coverage, and practitioner debate about how "
            f"this kind of product is built, bought, evaluated or trusted. A listed vendor does not have to be named.",
            {"true": f"The candidate is about the {name} market or a company, product or deal in it",
             "false": "General cybersecurity, AI or business news that only shares a word with a vendor name or search term"},
        )
    return (
        f'The organisation "{name}": its products and services, its named competitors, and the industry, '
        f"sector or policy it operates in, even when {name} is not named.",
        {"true": f"The candidate is about {name}, its products, its competitors or its sector",
         "false": f"A different person, place, product or organisation that shares the name, or an unrelated subject"},
    )


def _score_one(query: str, cand: Dict[str, Any], name: str, definition: str,
               entity_criteria: Dict[str, str], keywords: List[str]) -> Dict[str, Any]:
    from app.services import typesafe_client
    state = {
        "query": query,
        "monitored": {"name": name, "definition": definition, "search_terms": keywords},
        "candidate": {"title": cand.get("title") or "", "summary": (cand.get("summary") or "")[:1500],
                      "source": cand.get("news_source") or "", "published": str(cand.get("publication_date") or "")[:10]},
    }
    questions = {
        "answers_query": {
            "type": "noul",
            "instructions": "Would `candidate` help answer `query` for an analyst monitoring `monitored`? Judge the candidate's content, not its wording overlap with the query.",
            "criteria": {"true": "The candidate reports or analyses something the query is asking about, concerning the monitored entity or market",
                         "false": "The candidate is on a similar topic but does not address the query, or concerns something else that shares a name or keyword"},
        },
        "about_entity": {
            "type": "noul",
            "instructions": "Is `candidate` about `monitored` as `monitored.definition` describes it?",
            "criteria": entity_criteria,
        },
    }
    started = time.monotonic()
    out = typesafe_client.system_one(state, questions, use_case=USE_CASE)
    latency_ms = int((time.monotonic() - started) * 1000)
    if not out:
        return {"jev_error": "no response", "jev_latency_ms": latency_ms}
    try:
        a = out["answers"]
        return {"jev_answers_query": float(a["answers_query"]["noul"]),
                "jev_about_entity": float(a["about_entity"]["noul"]),
                "jev_model": out.get("model"), "jev_latency_ms": latency_ms, "jev_error": None}
    except (KeyError, TypeError, ValueError) as e:
        return {"jev_error": f"bad answers: {e}", "jev_latency_ms": latency_ms}


def _insert(rows: List[Dict[str, Any]]) -> int:
    from sqlalchemy import text
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    n = 0
    try:
        for r in rows:
            conn.execute(text("""
                INSERT INTO rerank_shadow
                    (call_id, caller, query, topic, topic_kind, top_k, pool_size, article_uri, title,
                     cosine_rank, cosine_score, ce_rank, ce_score, in_top_k,
                     jev_answers_query, jev_about_entity, jev_model, jev_latency_ms, jev_error)
                VALUES
                    (:call_id, :caller, :query, :topic, :topic_kind, :top_k, :pool_size, :article_uri, :title,
                     :cosine_rank, :cosine_score, :ce_rank, :ce_score, :in_top_k,
                     :jev_answers_query, :jev_about_entity, :jev_model, :jev_latency_ms, :jev_error)
            """), r)
            n += 1
        conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[rerank shadow] insert failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()
    return n


def _run(call_id: str, caller: str, query: str, topic: str, kind: str, top_k: int,
         pool: List[Dict[str, Any]], ce_rank: Dict[str, int], ce_score: Dict[str, float],
         top_uris: set) -> None:
    started = time.monotonic()
    keywords = _keywords_for_topic(topic)
    name = _entity_name(topic, kind)
    definition, entity_criteria = _definition(topic, kind, keywords)
    with ThreadPoolExecutor(max_workers=8) as ex:
        answers = list(ex.map(lambda c: _score_one(query, c, name, definition, entity_criteria, keywords), pool))
    rows = []
    for cos_rank, (c, ans) in enumerate(zip(pool, answers), start=1):
        uri = c.get("uri") or c.get("url") or ""
        row = {
            "call_id": call_id, "caller": caller, "query": query[:2000], "topic": topic, "topic_kind": kind,
            "top_k": top_k, "pool_size": len(pool), "article_uri": uri[:2000], "title": (c.get("title") or "")[:500],
            "cosine_rank": cos_rank,
            "cosine_score": (float(c["similarity_score"]) if c.get("similarity_score") is not None else None),
            "ce_rank": ce_rank.get(uri), "ce_score": ce_score.get(uri), "in_top_k": uri in top_uris,
            "jev_answers_query": None, "jev_about_entity": None, "jev_model": None, "jev_latency_ms": None, "jev_error": None,
        }
        row.update(ans)
        rows.append(row)
    n = _insert(rows)
    errs = sum(1 for a in answers if a.get("jev_error"))
    logger.info(f"🪞 [rerank shadow] {kind} '{topic}' q={query[:60]!r}: {n} candidates, "
                f"{errs} Jev errors, {time.monotonic() - started:.1f}s")


def decide_enabled() -> bool:
    from app.services import typesafe_client
    return (os.getenv("TYPESAFE_DECIDE_RERANK", "false").lower() in {"1", "true", "yes"}
            and typesafe_client.is_configured())


def decide(query: str, topic: Optional[str], ranked: List[Dict[str, Any]], top_k: int,
           caller: str = "") -> List[Dict[str, Any]]:
    """The decision step, behind TYPESAFE_DECIDE_RERANK. For brand and market
    topics, judge the ``top_k`` candidates the caller was about to return and
    drop those Jev says do not answer the query (``answers_query`` under
    TYPESAFE_DECIDE_RERANK_MIN, default 0.1), keeping at least
    TYPESAFE_DECIDE_RERANK_KEEP (default 5) in the original order. 0.1, not
    0.5: on the labelled rows the three true answers Jev had rejected sat at
    0.04, 0.15 and 0.45 while 42 of 44 non-answers sat under 0.1, so the low
    cut removes the noise and keeps two of the three; the reranker's order
    fills the rest. Nothing
    below ``top_k`` is promoted, because it has not been judged. Returns the
    list to hand back; on any failure, the unchanged ``ranked[:top_k]``.

    Justified by the blind labels of 19 Sept: 44 of 47 candidates Jev rejected
    from Auspex's used set were not answers to the query. The shadow keeps
    recording the whole pool beside this, so the decision is measured against
    the same rows: an ``in_top_k`` row with ``jev_answers_query`` under the
    threshold is one this step dropped.
    """
    head = list(ranked[:top_k])
    try:
        kind = topic_kind(topic)
        if not kind or not decide_enabled() or len(head) <= 1:
            return head
        thr = float(os.getenv("TYPESAFE_DECIDE_RERANK_MIN", "0.1"))
        keep_min = int(os.getenv("TYPESAFE_DECIDE_RERANK_KEEP", "5"))
        keywords = _keywords_for_topic(topic)
        name = _entity_name(topic, kind)
        definition, entity_criteria = _definition(topic, kind, keywords)
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=8) as ex:
            answers = list(ex.map(lambda c: _score_one(query, c, name, definition, entity_criteria, keywords), head))
        errs = sum(1 for a in answers if a.get("jev_error"))
        if errs:
            logger.warning(f"[rerank decide] {errs}/{len(head)} Jev errors; returning the unfiltered list")
            return head
        keep_idx = {i for i, a in enumerate(answers) if float(a["jev_answers_query"]) >= thr}
        # Fewer than keep_min pass: top up from the caller's own order, not
        # Jev's. Jev has said "none of these answers", so it has no ranking
        # to offer; the reranker's order is the best remaining signal. (An
        # offline check on the labelled rows showed Jev's order dropping the
        # one true answer among eight when it ranked the survivors itself.)
        for i in range(len(head)):
            if len(keep_idx) >= keep_min:
                break
            keep_idx.add(i)
        kept = [c for i, c in enumerate(head) if i in keep_idx]
        logger.info(f"🎯 [rerank decide] {kind} '{topic}' q={query[:60]!r}: kept {len(kept)} of {len(head)} "
                    f"(threshold {thr}, min {keep_min}) in {time.monotonic() - started:.1f}s via {caller or '-'}")
        return kept
    except Exception as e:  # noqa: BLE001 — the decision must never break retrieval
        logger.warning(f"[rerank decide] failed, returning the unfiltered list: {e}")
        return head


def schedule(query: str, topic: Optional[str], pool: List[Dict[str, Any]],
             ranked: List[Dict[str, Any]], top_k: int, caller: str = "") -> bool:
    """Start the shadow on a daemon thread when the topic is a brand or a
    market. ``pool`` is the cosine-ordered set that was scored; ``ranked``
    the cross-encoder order with ``rerank_score`` set. Never raises."""
    try:
        kind = topic_kind(topic)
        if not kind or not enabled() or not pool:
            return False
        max_n = int(os.getenv("TYPESAFE_SHADOW_RERANK_MAX", "60"))
        key = lambda c: c.get("uri") or c.get("url") or ""
        ce_rank = {key(c): i for i, c in enumerate(ranked, start=1)}
        ce_score = {key(c): float(c.get("rerank_score")) for c in ranked if c.get("rerank_score") is not None}
        # With no reranked order (a cosine-only path) the caller keeps the
        # first top_k of the pool, so that is what "in_top_k" means there.
        top_uris = {key(c) for c in (ranked or pool)[:top_k]}
        snapshot = [dict(c) for c in pool[:max_n]]
        t = threading.Thread(
            target=_run, name=f"rerank-shadow-{kind}", daemon=True,
            args=(str(uuid.uuid4()), caller, query, topic, kind, int(top_k), snapshot, ce_rank, ce_score, top_uris),
        )
        t.start()
        return True
    except Exception as e:  # noqa: BLE001 — the shadow must never break retrieval
        logger.warning(f"[rerank shadow] could not schedule: {e}")
        return False
