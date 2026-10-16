"""Reviewer gate and bounded repair for the Wiley bundle narrative.

The 16 Oct 2026 review found the narrative (ledes, tensions,
recommendations, next steps, themes, overview, letter) describing a state
the refreshed evidence no longer supported: a trend called "dominant" whose
ledger said Stable, a review of options described as a completed
separation, a 0.85-point net rate written as an "85-point jump". No stage
read the text against the ledger it was written from.

This module is the pattern in docs/AI_DESIGN_PATTERNS.md 6.9 applied to the
bundle: a deterministic preflight on dates and figures, a judge a tier above
the writers whose findings must quote the sentence they are about, and a
repair step that may change only the quoted sentences, at most twice.
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_ROUNDS = 2
_YEAR = re.compile(r"^(19|20)\d\d$")


# ── Segments: every narrative field, with the path to write it back ────

def _segments(items: list, payload: dict) -> List[dict]:
    segs: List[dict] = []
    for a, _r, _p in items:
        topic = a.get("topic") or "—"
        aid = a.get("id")
        summ = a.get("summary") or {}
        tb = summ.get("topic_briefing") or {}
        for key in ("lede", "headline", "intelligence_view"):
            if isinstance(tb.get(key), str) and tb[key].strip():
                segs.append({"target": f"{topic}.briefing.{key}", "topic": topic, "kind": "topic",
                             "assessment_id": aid, "path": f"topic_briefing.{key}", "text": tb[key]})
        for i, t in enumerate(tb.get("tensions") or []):
            if isinstance(t, dict) and isinstance(t.get("body"), str) and t["body"].strip():
                segs.append({"target": f"{topic}.briefing.tensions[{i}]", "topic": topic, "kind": "topic",
                             "assessment_id": aid, "path": f"topic_briefing.tensions[{i}].body", "text": t["body"]})
        for i, r in enumerate(summ.get("strategic_recommendations") or []):
            if not isinstance(r, dict):
                continue
            for key in ("headline", "rationale"):
                if isinstance(r.get(key), str) and r[key].strip():
                    segs.append({"target": f"{topic}.recommendations[{i}].{key}", "topic": topic, "kind": "topic",
                                 "assessment_id": aid, "path": f"strategic_recommendations[{i}].{key}", "text": r[key]})
        for i, st in enumerate(summ.get("next_steps") or []):
            if isinstance(st, dict) and isinstance(st.get("action"), str) and st["action"].strip():
                segs.append({"target": f"{topic}.next_steps[{i}]", "topic": topic, "kind": "topic",
                             "assessment_id": aid, "path": f"next_steps[{i}].action", "text": st["action"]})
    for i, th in enumerate(payload.get("cross_cutting_themes") or []):
        if not isinstance(th, dict):
            continue
        for key in ("lead", "body"):
            if isinstance(th.get(key), str) and th[key].strip():
                segs.append({"target": f"cross_topic.cross_cutting_themes[{i}].{key}", "topic": None,
                             "kind": "bundle", "path": f"cross_cutting_themes[{i}].{key}", "text": th[key]})
    if isinstance(payload.get("strategic_overview"), str) and payload["strategic_overview"].strip():
        segs.append({"target": "strategic_overview", "topic": None, "kind": "bundle",
                     "path": "strategic_overview", "text": payload["strategic_overview"]})
    letter = (payload.get("exec_summary") or {}).get("letter") if isinstance(payload.get("exec_summary"), dict) else None
    if isinstance(letter, str) and letter.strip():
        segs.append({"target": "exec_summary.letter", "topic": None, "kind": "bundle",
                     "path": "exec_summary.letter", "text": letter})
    return segs


# ── Ledger: what the narrative may claim ───────────────────────────────

def _ledger(items: list, events_by_topic: dict) -> Dict[str, dict]:
    from app.services.wiley_bundle_supervisor import _topic_data_payload
    out: Dict[str, dict] = {}
    for a, _r, _p in items:
        topic = a.get("topic") or "—"
        evs = events_by_topic.get(topic) or []
        data = _topic_data_payload(a, named_events=evs)
        scen = [{k: s.get(k) for k in ("name", "status", "original_consensus_pct",
                                        "confirmation_delta_pct", "supports", "contradicts")}
                for s in (data.get("scenarios") or [])]
        events = []
        for e in evs:
            mv, mu = e.get("magnitude_value"), e.get("magnitude_unit")
            events.append({
                "actor": e.get("actor"), "action": e.get("action"), "subject": e.get("subject"),
                "date": str(e.get("event_date") or "")[:10] or None,
                "magnitude": (f"{mv:g} {mu or ''}".strip() if isinstance(mv, (int, float)) else None),
                "state": e.get("event_state"),
            })
        eos = (a.get("summary") or {}).get("extreme_outlier_scenarios") or (a.get("summary") or {}).get("eos") or []
        # The writers also see each scenario's top supporting and contradicting
        # articles, and cite them for context ("NASA powering up Roman's
        # camera"); those titles are sources too, or the judge flags every
        # article-grounded clause as unsupported.
        arts: List[str] = []
        for sc in (data.get("scenarios") or []):
            for key in ("top_supports", "top_contras"):
                for art in (sc.get(key) or []):
                    t = art.get("title") or art.get("headline") if isinstance(art, dict) else str(art)
                    if t and t not in arts:
                        arts.append(str(t))
        out[topic] = {"scenarios": scen, "events": events, "articles": arts[:60],
                      "tail_risks": [s.get("title") for s in eos if isinstance(s, dict) and s.get("title")]}
    return out


def _fmt_num(v) -> List[str]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return []
    out = {f"{f:g}"}
    if f.is_integer():
        out.add(str(int(f)))
    out.add(f"{abs(f):g}")
    return list(out)


def _facts(ledger_topics: List[dict], extra_numbers: List = ()) -> Tuple[set, set, str]:
    from app.services.daily_report_service import _dates_in, _numbers_in
    parts: List[str] = []
    nums: set = set()
    for lt in ledger_topics:
        for e in lt.get("events") or []:
            parts.append(" ".join(str(e.get(k) or "") for k in ("date", "actor", "action", "subject", "magnitude")))
        for s in lt.get("scenarios") or []:
            parts.append(str(s.get("name") or ""))
            for k in ("original_consensus_pct", "confirmation_delta_pct", "supports", "contradicts"):
                nums.update(_fmt_num(s.get(k)))
        parts.extend(str(t) for t in (lt.get("tail_risks") or []))
        parts.extend(str(t) for t in (lt.get("articles") or []))
    for v in extra_numbers:
        nums.update(_fmt_num(v))
    corpus = " ".join(parts)
    nums |= _numbers_in(corpus)
    return _dates_in(corpus), nums, corpus.lower()


# ── Deterministic preflight: dates and figures ────────────────────────

def preflight(segments: List[dict], ledger: Dict[str, dict], extra_numbers: List = ()) -> List[dict]:
    from app.services.daily_report_service import (_dates_in, _numbers_in, _sentences,
                                                   _date_matches, _DATE_WORDS, _DATE_ISO)
    all_topics = list(ledger.values())
    facts_all = _facts(all_topics, extra_numbers)
    facts_by_topic = {t: _facts([lt], extra_numbers) for t, lt in ledger.items()}
    findings: List[dict] = []
    for seg in segments:
        dates, nums, corpus = facts_by_topic.get(seg.get("topic")) if seg.get("kind") == "topic" else facts_all
        if seg.get("kind") == "topic" and seg.get("topic") not in facts_by_topic:
            dates, nums, corpus = facts_all
        for sent in _sentences(seg["text"]):
            for d in _dates_in(sent):
                if not _date_matches(d, dates):
                    label = f"{d[0]:02d}-{d[1]:02d}" + (f"-{d[2]}" if len(d) > 2 and d[2] else "")
                    findings.append({"target": seg["target"], "severity": "error", "check": "date",
                                     "finding": f"The date {label} appears in no event in the ledger.",
                                     "claim_text": sent, "source": "preflight",
                                     "suggested_fix": "Use the event's date from the ledger or drop the date."})
            stripped = _DATE_WORDS.sub(" ", _DATE_ISO.sub(" ", sent))
            for n in _numbers_in(stripped):
                if n in nums or _YEAR.match(n) or n.lower() in corpus:
                    continue
                findings.append({"target": seg["target"], "severity": "error", "check": "figure",
                                 "finding": f"The figure {n} appears in no event or scenario number in the ledger.",
                                 "claim_text": sent, "source": "preflight",
                                 "suggested_fix": "Quote a figure the ledger carries, with its qualifier, or drop it."})
    return findings


# ── Judge, quote-gated ─────────────────────────────────────────────────

def _quote_gate(findings: List[dict], segments: List[dict]) -> List[dict]:
    from app.services.daily_report_service import _norm_quote
    by_target = {s["target"]: _norm_quote(s["text"]) for s in segments}
    whole = " ".join(by_target.values())
    out = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        f = dict(f)
        f.setdefault("source", "judge")
        sev = (f.get("severity") or "warning").lower()
        f["severity"] = "error" if sev == "error" else "warning"
        q = _norm_quote(f.get("claim_text") or "")
        if not q:
            if f["severity"] == "error":
                f["severity"] = "warning"
                f["finding"] = (f.get("finding") or "") + " [no verbatim quote; not blocking]"
            out.append(f)
            continue
        t = f.get("target")
        if (t in by_target and (q in by_target[t] or (len(q) > 40 and q[:40] in by_target[t]))) \
                or q in whole or (len(q) > 40 and q[:40] in whole):
            if t not in by_target:
                f["target"] = next((k for k, v in by_target.items() if q in v or q[:40] in v), t)
            out.append(f)
        else:
            logger.info("narrative review: dropped judge finding whose quote is not in the text: %.120s", f.get("finding"))
    return out


async def judge(segments: List[dict], ledger: Dict[str, dict], organisation: dict) -> List[dict]:
    from app.services.wiley_bundle_supervisor import _call_agent
    payload = {"organisation": organisation or {}, "ledger": ledger,
               "segments": [{"target": s["target"], "topic": s.get("topic"), "text": s["text"]} for s in segments]}
    out = await _call_agent("wiley_narrative_judge_agent", payload)
    if not out:
        return [{"target": "*", "severity": "warning", "check": "review_failed", "source": "judge",
                 "finding": "The narrative judge did not answer; only the deterministic preflight ran.",
                 "claim_text": "", "suggested_fix": ""}]
    return _quote_gate((out or {}).get("findings") or [], segments)


def _merge(preflight_f: List[dict], judge_f: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for f in preflight_f + judge_f:
        key = (f.get("target"), (f.get("claim_text") or "")[:80], f.get("check"))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


# ── Orchestration ──────────────────────────────────────────────────────

async def review_and_repair(cadence: str, period_label: str, *, max_rounds: int = MAX_ROUNDS,
                            do_repair: bool = True) -> dict:
    """Preflight + judge; repair the quoted sentences and re-review, at most
    ``max_rounds`` times. The verdict is computed from counts in code."""
    from app.database import get_database_instance
    from app.services.wiley_bundle_supervisor import _load_items_for_period, _organisation_context
    from app.services.wiley_delivery_service import _events_by_topic

    db = get_database_instance()
    organisation = _organisation_context()
    history = []
    findings: List[dict] = []
    rounds_run = 0
    for rnd in range(max_rounds + 1):
        items = await _load_items_for_period(cadence, period_label)
        synth = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or {}
        payload = synth.get("payload") or {}
        segments = _segments(items, payload)
        for s in segments:
            s["_period"] = period_label
        events_by_topic = _events_by_topic(cadence, period_label)
        ledger = _ledger(items, events_by_topic)
        n_scen = sum(len(v.get("scenarios") or []) for v in ledger.values())
        n_tail = sum(len(v.get("tail_risks") or []) for v in ledger.values())
        pre = preflight(segments, ledger, extra_numbers=[n_scen, n_tail, len(ledger)])
        jud = await judge(segments, ledger, organisation)
        findings = _merge(pre, jud)
        errors = [f for f in findings if f.get("severity") == "error"]
        history.append({"round": rnd, "errors": len(errors), "warnings": len(findings) - len(errors)})
        logger.info("narrative review round %d: %d errors, %d warnings", rnd, len(errors), len(findings) - len(errors))
        if not errors or not do_repair or rnd == max_rounds:
            break
        for s in segments:
            s["_cadence"] = cadence
        n = await _repair_with_cadence(db, cadence, period_label, segments, findings, ledger, organisation)
        rounds_run += 1
        if n == 0:
            break
    errors = [f for f in findings if f.get("severity") == "error"]
    result = {"verdict": "blocked" if errors else "clear", "rounds": rounds_run,
              "errors": len(errors), "warnings": len(findings) - len(errors),
              "history": history, "findings": findings[:80],
              "at": datetime.now(timezone.utc).isoformat()}
    try:
        db.facade.patch_brief_field(cadence, period_label, path="narrative_review", value=result,
                                    edited_by="narrative-review", lock=False)
    except Exception as e:
        logger.warning("narrative review: could not persist result: %s", e)
    return result


async def _repair_with_cadence(db, cadence, period_label, segments, findings, ledger, organisation) -> int:
    from app.services.wiley_bundle_supervisor import _call_agent
    flagged_targets = {f.get("target") for f in findings if f.get("severity") == "error"}
    flagged = [s for s in segments if s["target"] in flagged_targets]
    if not flagged:
        return 0
    payload = {"organisation": organisation or {}, "ledger": ledger,
               "segments": [{"target": s["target"], "text": s["text"]} for s in flagged],
               "findings": [{k: f.get(k) for k in ("target", "finding", "claim_text", "suggested_fix", "check")}
                            for f in findings if f.get("target") in flagged_targets and f.get("severity") == "error"]}
    out = await _call_agent("wiley_repair_agent", payload)
    repaired = {s.get("target"): s.get("text") for s in ((out or {}).get("segments") or []) if isinstance(s, dict)}
    n = 0
    for seg in flagged:
        new = repaired.get(seg["target"])
        if not isinstance(new, str) or not new.strip() or new.strip() == seg["text"].strip():
            continue
        if len(new) > 1.5 * len(seg["text"]) + 200:
            logger.info("narrative repair: %s grew too much; skipped", seg["target"])
            continue
        try:
            if seg["kind"] == "topic":
                db.facade.patch_topic_summary_field(topic=seg["topic"], assessment_id=seg["assessment_id"],
                                                    path=seg["path"], value=new, edited_by="narrative-repair", lock=False)
            else:
                db.facade.patch_brief_field(cadence, period_label, path=seg["path"], value=new,
                                            edited_by="narrative-repair", lock=False)
            n += 1
        except Exception as e:
            logger.warning("narrative repair: write failed for %s: %s", seg["target"], e)
    logger.info("narrative repair: rewrote %d of %d flagged segments", n, len(flagged))
    return n
