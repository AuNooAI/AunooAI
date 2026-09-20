"""Generic shadow check of extracted claims against their source text, with the
TypeSafe Jev model.

Any step that turns source text into a stored value (a summary, an explanation,
an event description, an extracted fact) can call ``schedule(site, item_key,
sources, claims, pipe_model)`` after it has produced the value. Each claim is
sent to Jev with the sources it was extracted from and the "double-checking
citations" questions: how do the sources relate to the claim (supports /
contradicts / says nothing), does the claim carry a checkable specific, and
which source supports it best. Rows land in ``extraction_check_shadow``.
Nothing on the extraction path reads them.

Sources are a list of {"label", "title", "text"}; long texts are chunked so a
claim is judged against the passage that mentions it, not a 32k-token wall.
The work runs on a daemon thread; a failed call is a row with ``jev_error``.

Env:
    TYPESAFE_SHADOW_EXTRACTION   "1" to enable (needs TYPESAFE_API_KEY)
    TYPESAFE_SHADOW_EXTRACTION_RATE  fraction of items sent (default 1.0)
"""
from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

USE_CASE = "services.extraction_check_shadow:check"
CHUNK_CHARS = 2500          # a passage a single claim is judged against
MIN_SOURCE_CHARS = 400      # below this the source is a stub and every claim reads as unsupported
MAX_SOURCES_PER_CALL = 8    # chunks per request; the 32k state budget holds far more


def enabled() -> bool:
    from app.services import typesafe_client
    return (os.getenv("TYPESAFE_SHADOW_EXTRACTION", "false").lower() in {"1", "true", "yes"}
            and typesafe_client.is_configured())


def sentences(text: str, min_len: int = 20) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if len(s.strip()) >= min_len]


def _chunks(sources: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Split every source into passages of CHUNK_CHARS, keeping the label."""
    out: List[Dict[str, str]] = []
    for s in sources:
        label = str(s.get("label") or "source")
        title = str(s.get("title") or "")
        text = str(s.get("text") or "")
        if not text and not title:
            continue
        pieces = [text[i:i + CHUNK_CHARS] for i in range(0, max(len(text), 1), CHUNK_CHARS)] or [""]
        for n, p in enumerate(pieces, 1):
            out.append({"ref": f"{label}" + (f" part {n}" if len(pieces) > 1 else ""), "title": title, "text": p})
    return out


def _pick_chunks(claim: str, chunks: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """The chunks most likely to contain the claim: token overlap, then order."""
    if len(chunks) <= MAX_SOURCES_PER_CALL:
        return chunks
    toks = {t for t in re.findall(r"[A-Za-z][A-Za-z\-]{3,}|\d[\d.,]*", claim.lower())}
    scored = sorted(chunks, key=lambda c: -len(toks & set(re.findall(r"[a-z][a-z\-]{3,}|\d[\d.,]*", (c["title"] + " " + c["text"]).lower()))))
    return scored[:MAX_SOURCES_PER_CALL]


def _questions(refs: List[str]) -> Dict[str, Dict[str, Any]]:
    q: Dict[str, Dict[str, Any]] = {
        "relation": {
            "type": "choice",
            "instructions": "How do the `sources` relate to `claim`? Judge only what the sources state; a claim that adds a date, figure, name or cause the sources do not contain is not supported.",
            "criteria": {
                "supports": "At least one source states the claim or directly implies it, including its specifics",
                "contradicts": "A source states the opposite, or gives a different date, figure, actor or outcome for the same thing",
                "says_nothing": "No source addresses what the claim asserts, or the claim adds a specific the sources do not contain",
            },
        },
        "has_specific": {
            "type": "noul",
            "instructions": "Does `claim` assert a checkable specific: a date, a figure, a named person or organisation doing something, or a concrete event?",
            "criteria": {"true": "The sentence could be wrong in a verifiable way",
                         "false": "Framing, interpretation or a recommendation with nothing to check"},
        },
    }
    for i, _ in enumerate(refs):
        q[f"src_{i}"] = {
            "type": "noul",
            "instructions": f"Does `sources[{i}]` on its own support `claim`, including the claim's specifics?",
            "criteria": {"true": "This passage states or directly implies the claim",
                         "false": "This passage does not address the claim, only part of it, or contradicts it"},
        }
    return q


def check_one(claim: str, chunks: List[Dict[str, str]]) -> Dict[str, Any]:
    from app.services import typesafe_client
    picked = _pick_chunks(claim, chunks)
    state = {"claim": claim, "sources": [{"ref": c["ref"], "title": c["title"], "text": c["text"]} for c in picked]}
    started = time.monotonic()
    out = typesafe_client.system_one(state, _questions([c["ref"] for c in picked]), use_case=USE_CASE)
    latency_ms = int((time.monotonic() - started) * 1000)
    base = {"source_label": ", ".join(c["ref"] for c in picked)[:500],
            "source_chars": sum(len(c["text"]) for c in picked), "jev_latency_ms": latency_ms}
    if not out:
        base["jev_error"] = "no response"
        return base
    try:
        a = out["answers"]; rel = a["relation"]; probs = rel.get("probabilities") or {}
        best_ref, best_p = None, None
        for i, c in enumerate(picked):
            p = float(a.get(f"src_{i}", {}).get("noul", 0.0))
            if best_p is None or p > best_p:
                best_ref, best_p = c["ref"], p
        base.update({
            "jev_relation": rel.get("choice"),
            "jev_p_supports": float(probs.get("supports", 0.0)),
            "jev_p_contradicts": float(probs.get("contradicts", 0.0)),
            "jev_p_says_nothing": float(probs.get("says_nothing", 0.0)),
            "jev_confidence": float(rel.get("confidence") or 0.0),
            "jev_has_specific": float(a["has_specific"]["noul"]),
            "jev_best_source": best_ref, "jev_best_source_p": best_p,
            "jev_model": out.get("model"), "jev_error": None,
        })
    except (KeyError, TypeError, ValueError) as e:
        base["jev_error"] = f"bad answers: {e}"
    return base


def _insert(rows: List[Dict[str, Any]]) -> int:
    from sqlalchemy import text
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    n = 0
    cols = ["site", "item_key", "field", "claim_no", "claim", "source_label", "source_chars", "pipe_model",
            "jev_relation", "jev_p_supports", "jev_p_contradicts", "jev_p_says_nothing", "jev_confidence",
            "jev_has_specific", "jev_best_source", "jev_best_source_p", "jev_model", "jev_latency_ms", "jev_error"]
    sql = text(f"INSERT INTO extraction_check_shadow ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})")
    try:
        for r in rows:
            conn.execute(sql, {c: r.get(c) for c in cols})
            n += 1
        conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[extraction shadow] insert failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()
    return n


def _run(site: str, item_key: str, sources: List[Dict[str, Any]], claims: List[Tuple[str, str]],
         pipe_model: Optional[str]) -> None:
    started = time.monotonic()
    chunks = _chunks(sources)
    if not chunks or not claims:
        return
    with ThreadPoolExecutor(max_workers=6) as ex:
        answers = list(ex.map(lambda c: check_one(c[1], chunks), claims))
    rows = []
    counters: Dict[str, int] = {}
    for (field, claim), ans in zip(claims, answers):
        counters[field] = counters.get(field, 0) + 1
        row = {"site": site, "item_key": (item_key or "")[:2000], "field": field, "claim_no": counters[field],
               "claim": claim[:2000], "pipe_model": (pipe_model or "")[:200] or None}
        row.update(ans)
        rows.append(row)
    n = _insert(rows)
    bad = [r for r in rows if r.get("jev_relation") in ("contradicts", "says_nothing") and (r.get("jev_has_specific") or 0) >= 0.5]
    logger.info(f"🪞 [extraction shadow] {site} {item_key[:60]!r}: {n} claims, "
                f"{len(bad)} checkable-and-unsupported, {sum(1 for r in rows if r.get('jev_error'))} errors, "
                f"{time.monotonic() - started:.1f}s")
    for r in bad[:3]:
        logger.info(f"🪞 [extraction shadow]   {r['jev_relation']} ({r['jev_confidence']:.2f}) {r['field']}: {r['claim'][:110]!r}")


def schedule(site: str, item_key: str, sources: Sequence[Dict[str, Any]],
             claims: Sequence[Tuple[str, str]], pipe_model: Optional[str] = None) -> bool:
    """``claims`` are (field, sentence) pairs. Returns True when scheduled. Never raises."""
    try:
        if not enabled() or not claims or not sources:
            return False
        rate = float(os.getenv("TYPESAFE_SHADOW_EXTRACTION_RATE", "1.0"))
        if rate < 1.0 and random.random() >= rate:
            return False
        t = threading.Thread(target=_run, name=f"extraction-shadow-{site}", daemon=True,
                             args=(site, item_key, [dict(s) for s in sources], [tuple(c) for c in claims], pipe_model))
        t.start()
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[extraction shadow] could not schedule: {e}")
        return False
