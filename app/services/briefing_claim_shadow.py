"""Shadow citation check of a desk-briefing draft with the TypeSafe Jev model.

TypeSafe's "double-checking citations" recipe: for each claim and the source
it rests on, one Choice question decides whether the source supports the
claim, contradicts it, or says nothing about it, and the answer's confidence
says whether a person should look. Here the claims are the sentences of the
draft the reviewer sees (summary, each theme, each priority action) and the
sources are the same source items the reviewer and the repair writer are
held to.

Which sources a sentence is checked against:
  * a theme sentence: the theme's ``supporting_items`` refs ("Article 2"),
    falling back to all sources when the theme lists none;
  * a summary or action sentence: all source items.
One request per sentence carries the Choice plus a Noul per cited source
("does this one support it?"), so the row also records the best-supporting
source. A Noul "does this sentence carry a checkable specific?" rides along
so sentences with nothing to verify can be separated in the analysis.

Rows land in ``briefing_claim_shadow`` next to whether the preflight or the
LLM judge flagged the same sentence. The work runs on a daemon thread after
the first review; it never delays or alters the finalize stream.

Env:
    TYPESAFE_SHADOW_CITATIONS   "1" to enable (needs TYPESAFE_API_KEY)
    TYPESAFE_SHADOW_CITATIONS_MAX_SOURCES  per request (default 8)
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

USE_CASE = "services.briefing_claim_shadow:check"
_REF_RE = re.compile(r"(Article|Incident)\s+(\d+)", re.I)


def enabled() -> bool:
    from app.services import typesafe_client
    return (os.getenv("TYPESAFE_SHADOW_CITATIONS", "false").lower() in {"1", "true", "yes"}
            and typesafe_client.is_configured())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _sources(articles: List[Dict], incidents: List[Dict]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for i, a in enumerate(articles, 1):
        out[f"Article {i}"] = {
            "ref": f"Article {i}", "title": a.get("title") or "",
            "source": a.get("source") or a.get("news_source") or "",
            "published": str(a.get("publication_date") or "")[:10],
            "text": (a.get("summary") or "")[:900],
        }
    for i, inc in enumerate(incidents, 1):
        out[f"Incident {i}"] = {
            "ref": f"Incident {i}", "title": inc.get("name") or inc.get("title") or "",
            "source": "incident", "published": "",
            "text": ((inc.get("summary") or inc.get("description") or "")[:700]
                     + " " + " ".join(str(x) for x in (inc.get("entities") or [])[:12])),
        }
    return out


def _segments(synthesis_result: Dict) -> List[Tuple[str, str, List[str]]]:
    """(target, text, cited refs) for every prose field the reviewer sees."""
    segs: List[Tuple[str, str, List[str]]] = [("summary", synthesis_result.get("briefing_summary") or "", [])]
    for t in synthesis_result.get("themes") or []:
        if isinstance(t, dict):
            refs = []
            for r in (t.get("supporting_items") or []):
                m = _REF_RE.search(str(r))
                if m:
                    refs.append(f"{m.group(1).title()} {int(m.group(2))}")
            segs.append((f"theme:{t.get('theme_name') or ''}",
                         " ".join(str(t.get(k) or "") for k in ("description", "strategic_implication")), refs))
    for i, a in enumerate(synthesis_result.get("priority_actions") or [], 1):
        if isinstance(a, dict):
            segs.append((f"action:{i}", " ".join(str(a.get(k) or "") for k in ("action", "rationale")), []))
    return segs


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if len(s.strip()) >= 20]


def _questions(refs: List[str]) -> Dict[str, Dict[str, Any]]:
    q: Dict[str, Dict[str, Any]] = {
        "relation": {
            "type": "choice",
            "instructions": "How do the `sources` relate to `claim`? Judge only what the sources state; a claim that goes beyond them is not supported.",
            "criteria": {
                "supports": "At least one source states the claim or directly implies it is true, including its specifics (dates, figures, names, who did what)",
                "contradicts": "A source states the opposite of the claim, or gives a different date, figure, actor or outcome for the same thing",
                "says_nothing": "No source addresses what the claim asserts, or the claim adds a specific the sources do not contain",
            },
        },
        "has_specific": {
            "type": "noul",
            "instructions": "Does `claim` assert a checkable specific: a date, a figure, a named person or organisation doing something, or a concrete event?",
            "criteria": {"true": "The sentence could be wrong in a verifiable way",
                         "false": "The sentence is framing, interpretation or a recommendation with nothing to check"},
        },
    }
    for i, ref in enumerate(refs):
        q[f"src_{i}"] = {
            "type": "noul",
            "instructions": f"Does `sources[{i}]` (its title and text) on its own support `claim`, including the claim's specifics?",
            "criteria": {"true": "This source states or directly implies the claim",
                         "false": "This source does not address the claim, or only part of it, or contradicts it"},
        }
    return q


def _check_one(sentence: str, refs: List[str], sources: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    from app.services import typesafe_client
    picked = [sources[r] for r in refs if r in sources]
    state = {"claim": sentence, "sources": [{"ref": s["ref"], "title": s["title"], "source": s["source"],
                                              "published": s["published"], "text": s["text"]} for s in picked]}
    started = time.monotonic()
    out = typesafe_client.system_one(state, _questions([s["ref"] for s in picked]), use_case=USE_CASE)
    latency_ms = int((time.monotonic() - started) * 1000)
    if not out:
        return {"jev_error": "no response", "jev_latency_ms": latency_ms}
    try:
        a = out["answers"]
        rel = a["relation"]
        probs = rel.get("probabilities") or {}
        best_ref, best_p = None, None
        for i, s in enumerate(picked):
            p = float(a.get(f"src_{i}", {}).get("noul", 0.0))
            if best_p is None or p > best_p:
                best_ref, best_p = s["ref"], p
        return {
            "jev_relation": rel.get("choice"),
            "jev_p_supports": float(probs.get("supports", 0.0)),
            "jev_p_contradicts": float(probs.get("contradicts", 0.0)),
            "jev_p_says_nothing": float(probs.get("says_nothing", 0.0)),
            "jev_confidence": float(rel.get("confidence") or 0.0),
            "jev_best_source": best_ref, "jev_best_source_p": best_p,
            "jev_has_specific": float(a["has_specific"]["noul"]),
            "jev_model": out.get("model"), "jev_latency_ms": latency_ms, "jev_error": None,
        }
    except (KeyError, TypeError, ValueError) as e:
        return {"jev_error": f"bad answers: {e}", "jev_latency_ms": latency_ms}


def _judge_lookup(findings: List[Dict]) -> List[Tuple[str, Dict]]:
    return [(_norm(f.get("claim_text") or ""), f) for f in (findings or []) if f.get("claim_text")]


def _match_finding(sentence: str, lookup: List[Tuple[str, Dict]]) -> Optional[Dict]:
    s = _norm(sentence)
    best = None
    for claim, f in lookup:
        if not claim:
            continue
        if claim in s or s in claim:
            sev = {"error": 3, "warning": 2, "info": 1}.get(str(f.get("severity")), 0)
            if best is None or sev > best[0]:
                best = (sev, f)
    return best[1] if best else None


def _insert(rows: List[Dict[str, Any]]) -> int:
    from sqlalchemy import text
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    n = 0
    try:
        for r in rows:
            conn.execute(text("""
                INSERT INTO briefing_claim_shadow
                    (briefing_id, briefing_name, review_round, target, sentence_no, sentence, source_refs, scope,
                     jev_relation, jev_p_supports, jev_p_contradicts, jev_p_says_nothing, jev_confidence,
                     jev_best_source, jev_best_source_p, jev_has_specific, jev_model, jev_latency_ms, jev_error,
                     judge_flagged, judge_severity, judge_check, judge_finding, review_status)
                VALUES
                    (:briefing_id, :briefing_name, :review_round, :target, :sentence_no, :sentence, :source_refs, :scope,
                     :jev_relation, :jev_p_supports, :jev_p_contradicts, :jev_p_says_nothing, :jev_confidence,
                     :jev_best_source, :jev_best_source_p, :jev_has_specific, :jev_model, :jev_latency_ms, :jev_error,
                     :judge_flagged, :judge_severity, :judge_check, :judge_finding, :review_status)
            """), r)
            n += 1
        conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[citation shadow] insert failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()
    return n


def _run(briefing_id: Optional[int], briefing_name: str, review_round: int, synthesis_result: Dict,
         articles: List[Dict], incidents: List[Dict], findings: List[Dict], review_status: str) -> None:
    max_sources = int(os.getenv("TYPESAFE_SHADOW_CITATIONS_MAX_SOURCES", "20"))
    sources = _sources(articles, incidents)
    # Incidents first: a briefing has a handful of them and the summary and
    # actions lean on them heavily. The first live run (briefing 15) capped
    # "all" at 8 refs, which cut every incident and turned two JADEPUFFER
    # sentences into "says nothing" with the evidence sitting in Incident 2.
    all_refs = [r for r in sources if r.startswith("Incident")] + [r for r in sources if r.startswith("Article")]
    lookup = _judge_lookup(findings)
    jobs: List[Tuple[str, int, str, List[str], str]] = []
    for target, text_, cited in _segments(synthesis_result):
        refs = [r for r in cited if r in sources]
        scope = "cited" if refs else "all"
        refs = (refs or all_refs)[:max_sources]
        for n, sent in enumerate(_sentences(text_), 1):
            jobs.append((target, n, sent, refs, scope))
    if not jobs:
        logger.info(f"🪞 [citation shadow] '{briefing_name}': no sentences to check")
        return
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as ex:
        answers = list(ex.map(lambda j: _check_one(j[2], j[3], sources), jobs))
    rows = []
    for (target, n, sent, refs, scope), ans in zip(jobs, answers):
        f = _match_finding(sent, lookup)
        row = {
            "briefing_id": briefing_id, "briefing_name": (briefing_name or "")[:300], "review_round": review_round,
            "target": target[:300], "sentence_no": n, "sentence": sent[:2000],
            "source_refs": ", ".join(refs)[:500], "scope": scope,
            "jev_relation": None, "jev_p_supports": None, "jev_p_contradicts": None, "jev_p_says_nothing": None,
            "jev_confidence": None, "jev_best_source": None, "jev_best_source_p": None, "jev_has_specific": None,
            "jev_model": None, "jev_latency_ms": None, "jev_error": None,
            "judge_flagged": f is not None,
            "judge_severity": (f or {}).get("severity"),
            "judge_check": ((f or {}).get("check") or ((f or {}).get("source"))) if f else None,
            "judge_finding": ((f or {}).get("finding") or "")[:1000] if f else None,
            "review_status": review_status,
        }
        row.update(ans)
        rows.append(row)
    n = _insert(rows)
    errs = sum(1 for a in answers if a.get("jev_error"))
    unsupported = sum(1 for a in answers if a.get("jev_relation") in ("contradicts", "says_nothing"))
    logger.info(f"🪞 [citation shadow] '{briefing_name}' round {review_round}: {n} sentences recorded, "
                f"{unsupported} not supported per Jev, {errs} errors, {time.monotonic() - started:.1f}s")


def schedule(briefing_id: Optional[int], briefing_name: str, review_round: int, synthesis_result: Dict,
             articles: List[Dict], incidents: List[Dict], review: Dict) -> bool:
    """Start the check on a daemon thread. Returns True when scheduled."""
    if not enabled() or not synthesis_result:
        return False
    try:
        import copy
        t = threading.Thread(
            target=_run, name=f"citation-shadow-{briefing_id or briefing_name}", daemon=True,
            args=(briefing_id, briefing_name, int(review_round), copy.deepcopy(synthesis_result),
                  [dict(a) for a in articles], [dict(i) for i in incidents],
                  copy.deepcopy((review or {}).get("findings") or []), str((review or {}).get("status") or "")),
        )
        t.start()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[citation shadow] could not schedule: {e}")
        return False
