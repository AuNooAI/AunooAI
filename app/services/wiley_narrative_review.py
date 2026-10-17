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
# "2 October", "22 September 2026": the shared _DATE_WORDS pattern is
# month-first only, and the writers favour day-first (ninth review).
_DATE_DAY_FIRST = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?(?:,?\s+(\d{4}))?\b")


def _day_first_dates(sent: str) -> list:
    """(month, day, year|None) tuples for day-first dates in a sentence."""
    from app.services.daily_report_service import _MONTHS
    out = []
    for m in _DATE_DAY_FIRST.finditer(sent):
        mon = _MONTHS.get(m.group(2).lower().rstrip("."))
        if mon:
            out.append(((mon, int(m.group(1)), int(m.group(3)) if m.group(3) else None), m.start(), m.end()))
    return out


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
            # The short sentence the slide shows in place of a long body
            # (seventh review, 16 Oct 2026, F04): reviewed like the body.
            if isinstance(t, dict) and isinstance(t.get("display"), str) and t["display"].strip():
                segs.append({"target": f"{topic}.briefing.tensions[{i}].display", "topic": topic, "kind": "topic",
                             "assessment_id": aid, "path": f"topic_briefing.tensions[{i}].display", "text": t["display"],
                             "body": t.get("body") or "", "tension_idx": i})
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
    for i, dfw in enumerate(payload.get("executive_decision_framework") or []):
        if not isinstance(dfw, dict):
            continue
        for key in ("headline", "body"):
            if isinstance(dfw.get(key), str) and dfw[key].strip():
                segs.append({"target": f"decision_framework[{i}].{key}", "topic": None, "kind": "bundle",
                             "path": f"executive_decision_framework[{i}].{key}", "text": dfw[key]})
    # Per-scenario key signals and strategic imperatives are narrative too;
    # they print on the strategic-domain and scenario slides and had never
    # been reviewed (a market size called a "deal", 16 Oct 2026).
    for a, _r, _p in items:
        topic = a.get("topic") or "—"
        aid = a.get("id")
        for v in (a.get("scenario_verdicts") or []):
            syn = v.get("synthesis")
            if isinstance(syn, str):
                try:
                    syn = json.loads(syn)
                except Exception:
                    syn = None
            if not isinstance(syn, dict) or v.get("scenario_idx") is None:
                continue
            name = ((v.get("top_articles") or {}).get("deck_info") or {}).get("deck_scenario_name") or v.get("scenario_title") or "?"
            base = {"topic": topic, "kind": "verdict", "assessment_id": aid, "scenario_idx": v.get("scenario_idx"),
                    "scenario_name": name}
            for j, sig in enumerate(syn.get("key_signals") or []):
                if isinstance(sig, str) and sig.strip():
                    segs.append({**base, "target": f"{topic}.scenario[{name}].key_signals[{j}]",
                                 "path": f"key_signals[{j}]", "text": sig})
            imp = syn.get("strategic_imperative")
            if isinstance(imp, str) and imp.strip():
                segs.append({**base, "target": f"{topic}.scenario[{name}].imperative",
                             "path": "strategic_imperative", "text": imp})
    if isinstance(payload.get("strategic_overview"), str) and payload["strategic_overview"].strip():
        segs.append({"target": "strategic_overview", "topic": None, "kind": "bundle",
                     "path": "strategic_overview", "text": payload["strategic_overview"]})
    # The expert view (slide 4) was never reviewed; it said the administration
    # was "asserting veto authority" three weeks after the scheme was dropped
    # (sixth review, 16 Oct 2026, F02).
    if isinstance(payload.get("expert_commentary"), str) and payload["expert_commentary"].strip():
        segs.append({"target": "expert_commentary", "topic": None, "kind": "bundle",
                     "path": "expert_commentary", "text": payload["expert_commentary"]})
    letter = (payload.get("exec_summary") or {}).get("letter") if isinstance(payload.get("exec_summary"), dict) else None
    if isinstance(letter, str) and letter.strip():
        segs.append({"target": "exec_summary.letter", "topic": None, "kind": "bundle",
                     "path": "exec_summary.letter", "text": letter})
    return segs


# ── Ledger: what the narrative may claim ───────────────────────────────

def _historical_events(cadence: Optional[str], period_label: Optional[str]) -> Dict[str, list]:
    """Rows the window audit moved out of the deck (event_state
    'historical'), per topic; the narrative must not present them as this
    period's developments."""
    if not cadence or not period_label:
        return {}
    try:
        from app.database import get_database_instance
        rows = get_database_instance().facade.list_extracted_events(cadence=cadence, period_label=period_label,
                                                                     include_excluded=True) or []
    except Exception as e:
        logger.warning("narrative review: historical rows unavailable: %s", e)
        return {}
    out: Dict[str, list] = {}
    for r in rows:
        if str(r.get("event_state") or "") == "historical":
            out.setdefault(r.get("topic"), []).append(r)
    return out


def _ledger(items: list, events_by_topic: dict, historical_by_topic: Optional[dict] = None) -> Dict[str, dict]:
    from app.services.wiley_bundle_supervisor import _topic_data_payload
    out: Dict[str, dict] = {}
    for a, _r, _p in items:
        topic = a.get("topic") or "—"
        evs = events_by_topic.get(topic) or []
        data = _topic_data_payload(a, named_events=evs)
        # Each scenario lists the events judged to bear on it, the rows its
        # evidence slide shows. A synthesis that credits a scenario with any
        # other event is substituting evidence (fifth review, 16 Oct 2026, F04).
        scen = [{k: s.get(k) for k in ("name", "status", "read", "n_confirm", "n_counter",
                                        "original_consensus_pct", "article_share_delta_pct",
                                        "supports", "contradicts", "events")}
                for s in (data.get("scenarios") or [])]
        events = []
        for e in evs:
            mv, mu = e.get("magnitude_value"), e.get("magnitude_unit")
            events.append({
                "actor": e.get("actor"), "action": e.get("action"), "subject": e.get("subject"),
                "date": str(e.get("event_date") or "")[:10] or None,
                "magnitude": (f"{mv:g} {mu or ''}".strip() if isinstance(mv, (int, float)) else None),
                "state": e.get("event_state"),
                "date_basis": e.get("date_basis"),
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
        # Events only. Article titles were allowed for a while and let the
        # writers cite "supporting articles" the slides never show.
        out[topic] = {"scenarios": scen, "events": events,
                      "historical": [{"actor": h.get("actor"), "action": h.get("action"), "subject": h.get("subject"),
                                      "date": str(h.get("event_date") or "")[:10] or None, "edited_by": h.get("edited_by")}
                                     for h in (historical_by_topic or {}).get(topic, [])],
                      "tail_risks": [s.get("title") for s in eos if isinstance(s, dict) and s.get("title")]}
    return out


def _fmt_num(v) -> List[str]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return []
    # Every spelling a writer may use for the same value: -1.0 is quoted
    # as "1 point", "1.0 points" or "1.00"; 2.18 as "2.18" or "2.2".
    out = set()
    for v in (f, abs(f)):
        out.add(f"{v:g}")
        out.add(f"{v:.1f}")
        out.add(f"{v:.2f}")
        if v.is_integer():
            out.add(str(int(v)))
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
            for k in ("original_consensus_pct", "article_share_delta_pct", "n_confirm", "n_counter",
                      "supports", "contradicts"):
                nums.update(_fmt_num(s.get(k)))
        parts.extend(str(t) for t in (lt.get("tail_risks") or []))
    for v in extra_numbers:
        nums.update(_fmt_num(v))
    corpus = " ".join(parts)
    nums |= _numbers_in(corpus)
    return _dates_in(corpus), nums, corpus.lower()


# ── Deterministic preflight: dates, figures, and sweeping status claims ──

_SWEEP = re.compile(r"\b(all|every|each|none of the|no)\s+(five|four|six|three|two|\d+)?\s*(of the\s+)?scenarios?\b[^.]{0,80}?"
                    r"\b(too early|unconfirmed|holding|in doubt|leaning|contested|not bearing out|no (confirming|countering|supporting) events)",
                    re.I)
_STATUS_WORDS = {"too early": "Too early", "unconfirmed": "Unconfirmed", "holding": "Holding", "in doubt": "In doubt",
                 "leaning": "Leaning", "contested": "Contested", "not bearing out": "Not bearing out"}


def _sweep_findings(seg: dict, scen: list) -> List[dict]:
    """'All five scenarios remain too early' when two ledgers say Holding
    (16 Oct 2026 round-four review, F02). A sweep over a topic's scenarios
    must match every scenario's status; the judge let these through."""
    from app.services.daily_report_service import _sentences
    out = []
    statuses = [str(sc.get("status") or "") for sc in scen]
    if not statuses:
        return out
    for sent in _sentences(seg["text"]):
        m = _SWEEP.search(sent)
        if not m:
            continue
        word = m.group(4).lower()
        claimed = _STATUS_WORDS.get(word)
        if word.startswith("no "):
            claimed = "Too early"
        if not claimed:
            continue
        negated = m.group(1).lower().startswith("no")
        mismatch = [st for st in statuses if (st == claimed) if negated] if negated else [st for st in statuses if st != claimed]
        if mismatch:
            out.append({"target": seg["target"], "severity": "error", "check": "contradiction",
                        "finding": f"The sentence sweeps every scenario as '{claimed}' but the ledger statuses are {statuses}.",
                        "claim_text": sent, "source": "preflight",
                        "suggested_fix": "State the count that holds for each status, from the ledger."})
    return out


_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
              "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "a single": 1}
_STATUS_ALT = "too early|unconfirmed|holding|in doubt|leaning|contested|outlier confirming|not bearing out"
_COUNT = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
                    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|a single)\s+"
                    r"(?:of\s+(?:the\s+)?(?:\d+|\w+)\s+)?(?:scenarios?\s+|trends?\s+|forecasts?\s+)?"
                    r"(?:(?:are|is|remain|remains|remaining|now|still|currently|already|rated|read|reading|as|"
                    r"sit|sits|sitting|stand|stands|standing|that are|which are)\s+)*"
                    r"(" + _STATUS_ALT + r")\b", re.I)
_SILENCE = re.compile(r"\b(?:no|zero|without any|absent any)\s+(?:(named|confirming|countering|counter|judged|"
                      r"supporting|recorded|observed)\s+)?events?\b|\bleft no mark\b|\bevent silence\b|"
                      r"\bno activity\b|\bno (?:event )?record(?:ed)?\b|\bhas not registered\b|"
                      r"\bnot registered (?:a single|any) event", re.I)
_REMAINING = re.compile(r"\b(?:remaining|other|rest of the)\s+(?:\w+\s+)?scenarios\b", re.I)
_POINTS = re.compile(r"(\d+(?:\.\d+)?)[\s-]*(?:percentage[\s-]*)?points?\b", re.I)
_SHARE_PCT = re.compile(r"\barticle[\s-]share[^.;]{0,60}?(\d+(?:\.\d+)?)\s*(?:%|percent\b)(?!\s*(?:age\s+)?points?)", re.I)


def _status_counts(scen: list) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for sc in scen:
        st = str(sc.get("status") or "").strip().lower()
        if st:
            out[st] = out.get(st, 0) + 1
    return out


def _count_findings(seg: dict, scen: list, per_topic: Optional[List[list]] = None) -> List[dict]:
    """'Two holding, three too early' must be the ledger's tally. The
    fifth review (16 Oct 2026, F03) found six topic syntheses whose counts
    matched no evidence slide; the judge had let every one through.
    A bundle-level sentence may count one topic's scenarios, so it passes
    when the figure matches the bundle tally or any one topic's."""
    from app.services.daily_report_service import _sentences
    out = []
    counts = _status_counts(scen)
    if not counts:
        return out
    alt = [_status_counts(s) for s in (per_topic or [])]
    for sent in _sentences(seg["text"]):
        for m in _COUNT.finditer(sent):
            raw = m.group(1).lower()
            n = int(raw) if raw.isdigit() else _NUM_WORDS.get(raw)
            st = m.group(2).lower()
            if n is None or n > 60:
                continue
            if any(c.get(st, 0) == n for c in alt):
                continue
            if counts.get(st, 0) != n:
                tally = ", ".join(f"{v} {k}" for k, v in counts.items())
                out.append({"target": seg["target"], "severity": "error", "check": "contradiction",
                            "finding": f"The sentence counts {n} scenario(s) as '{st}'; the ledger has {counts.get(st, 0)} ({tally}).",
                            "claim_text": sent, "source": "preflight",
                            "suggested_fix": f"Use the ledger tally: {tally}."})
                break
    return out


_EVENT_COUNT = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
                          r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+(confirming|countering|counter)\s+"
                          r"(?:events?|developments?|signals?|records?)\b", re.I)


def _event_count_findings(seg: dict, scen: list) -> List[dict]:
    """"Drew 9 confirming events" for a scenario whose ledger lists eight:
    the count is the length of that scenario's events list, and it goes
    stale when a row leaves the ledger (ninth review, 16 Oct 2026). A
    sentence that names a scenario is held to that scenario's count; one
    that names none passes when any scenario of the ledger has the count."""
    from app.services.daily_report_service import _sentences
    out = []
    if not scen:
        return out
    for sent in _sentences(seg["text"]):
        low = sent.lower()
        named = [sc for sc in scen if _names_scenario(low, sc, strict=True)]
        for m in _EVENT_COUNT.finditer(sent):
            raw = m.group(1).lower()
            n = int(raw) if raw.isdigit() else _NUM_WORDS.get(raw)
            key = "n_confirm" if m.group(2).lower() == "confirming" else "n_counter"
            if n is None:
                continue
            pool = named or scen
            if any((sc.get(key) or 0) == n for sc in pool):
                continue
            have = ", ".join(f"{sc.get('name')}: {sc.get(key) or 0}" for sc in pool[:5])
            out.append({"target": seg["target"], "severity": "error", "check": "contradiction",
                        "finding": f"The sentence counts {n} {m.group(2).lower()} events; the ledger has {have}.",
                        "claim_text": sent, "source": "preflight",
                        "suggested_fix": "Use the scenario's count from the ledger."})
            break
    return out


def _silence_findings(seg: dict, scen: list) -> List[dict]:
    """'No events' about a scenario whose ledger lists them, a headline
    saying the topic has no events when three ledgers carry one each, or
    'the remaining scenarios left no mark' when only one is Too early
    (fifth review, F03, slides 74 and 87)."""
    from app.services.daily_report_service import _sentences
    out = []
    if not scen:
        return out
    with_events = [sc for sc in scen if (sc.get("n_confirm") or 0) + (sc.get("n_counter") or 0) > 0]
    without = [sc for sc in scen if sc not in with_events]
    is_headline = seg["target"].endswith(".headline")
    for sent in _sentences(seg["text"]):
        m = _SILENCE.search(sent)
        if not m:
            continue
        # "no countering events" is about one direction: wrong only when the
        # scenario has countering events; "no confirming events" likewise.
        qual = (m.group(1) or "").lower()
        if qual in ("countering", "counter"):
            def _has(sc): return (sc.get("n_counter") or 0) > 0
        elif qual in ("confirming", "supporting"):
            def _has(sc): return (sc.get("n_confirm") or 0) > 0
        else:
            def _has(sc): return sc in with_events
        low = sent.lower()
        named = [sc for sc in scen if len(str(sc.get("name") or "")) > 3 and str(sc.get("name")).lower() in low]
        bad = [sc for sc in named if _has(sc)]
        if qual and not named:
            continue
        why = None
        if bad:
            why = "; ".join(f"'{sc.get('name')}' has {sc.get('n_confirm')} confirming and {sc.get('n_counter')} countering events" for sc in bad)
        elif not named and is_headline and with_events:
            why = f"{len(with_events)} of {len(scen)} scenarios have judged events"
        elif not named and _REMAINING.search(sent) and len(without) < 2:
            why = f"only {len(without)} scenario is without events ({', '.join(sc.get('name') or '?' for sc in without) or 'none'})"
        if why:
            out.append({"target": seg["target"], "severity": "error", "check": "contradiction",
                        "finding": f"The sentence says there are no events, but {why}.",
                        "claim_text": sent, "source": "preflight",
                        "suggested_fix": "Name the scenarios that are Too early, and only those."})
    return out


def _points_findings(seg: dict, scen_all: list) -> List[dict]:
    """'N points' is the article-share delta and nothing else. A lede quoted
    a ten-event count as '10 points above its placebo baseline' while the
    delta was 2.18, and the figure check passed the 10 because the event
    count carried it (fifth review, F05)."""
    from app.services.daily_report_service import _sentences
    out = []
    deltas = set()
    for sc in scen_all:
        for v in _fmt_num(sc.get("article_share_delta_pct")):
            deltas.add(v)
    if not deltas:
        return out
    for sent in _sentences(seg["text"]):
        m = _SHARE_PCT.search(sent)
        if m:
            # "the article share increased 1.03 percent": the delta is in
            # points; the judge rated this a warning (16 Oct 2026, round 8).
            out.append({"target": seg["target"], "severity": "error", "check": "metric",
                        "finding": f"The article-share delta is quoted as '{m.group(1)} percent'; it is a difference in percentage points.",
                        "claim_text": sent, "source": "preflight",
                        "suggested_fix": f"Write '{m.group(1)} points above/below its placebo baseline'."})
            continue
        for m in _POINTS.finditer(sent):
            before = sent[max(0, m.start() - 12):m.start()].lower()
            if "basis" in before or "price" in before:
                continue
            n = m.group(1)
            if n in deltas or f"{float(n):g}" in deltas:
                continue
            shown = sorted({sc.get("article_share_delta_pct") for sc in scen_all if sc.get("article_share_delta_pct") is not None})
            out.append({"target": seg["target"], "severity": "error", "check": "metric",
                        "finding": f"The sentence quotes {n} points; no article-share delta in the ledger is {n} (deltas: {shown[:12]}).",
                        "claim_text": sent, "source": "preflight",
                        "suggested_fix": "Quote the scenario's article_share_delta_pct as 'N points above/below its placebo baseline', or drop the points figure. An event count is not points."})
            break
    return out


_SIGNAL_STOP = {"with", "from", "that", "this", "into", "over", "under", "after", "before", "their", "will",
                "have", "been", "more", "than", "when", "where", "which", "what", "about", "across", "through",
                "launch", "launches", "launched", "announce", "announces", "announced", "report", "reports",
                "reported", "new", "major", "first", "signal", "signals", "watch", "quantum", "research",
                "funding", "federal", "open", "science", "publishing", "model", "models", "data", "policy"}


def _signal_findings(seg: dict, scen: list, topic_events: list) -> List[dict]:
    """A key signal names an event from the scenario's ledger, or is marked
    'Watch:' as something to look for. An unnamed 'regional biosimilar
    manufacturing hub' presented as a signal is a claim with no event behind
    it (fifth review, F07)."""
    text = (seg.get("text") or "").strip()
    if text.lower().startswith("watch"):
        return []
    words = {w for w in _WORD.findall(text.lower()) if len(w) > 3 and w not in _SIGNAL_STOP}
    nums = set(re.findall(r"\d[\d.,]*", text))
    if not words:
        return []
    name = str(seg.get("scenario_name") or "").lower()
    own = next((sc for sc in scen if str(sc.get("name") or "").lower() == name), None)
    pools = [("scenario", (own or {}).get("events") or []), ("topic", topic_events or [])]
    for label, evs in pools:
        for e in evs:
            etext = " ".join(str(e.get(k) or "") for k in ("actor", "action", "subject", "magnitude")).lower()
            etoks = set(_WORD.findall(etext))
            if len(words & etoks) >= 2 or (nums and nums & set(re.findall(r"\d[\d.,]*", etext)) and words & etoks):
                return []
    return [{"target": seg["target"], "severity": "error", "check": "unsupported",
             "finding": "The key signal names no event in this scenario's ledger (or the topic's), and is not marked as a watch item.",
             "claim_text": text, "source": "preflight",
             "suggested_fix": "Name an event from this scenario's `events` (actor and what it did), or start the phrase with 'Watch:' so it reads as something to look for rather than something observed."}]


_SPEECH = re.compile(r"\b(report(?:ed|s|ing)?|disclos(?:ed|es|ure)|apologi[sz]ed|apology|announc(?:ed|es|ement)|"
                     r"warn(?:ed|s|ing)|confirm(?:ed|s)|publish(?:ed|es)|said|stated|according to|coverage|described|"
                     r"found|issued|wrote|revealed|admitted|backtracked|clarified)\b", re.I)
_SPEECH_ACT = re.compile(r"^\s*(apologi[sz]ed|disclosed|reported|announced|warned|confirmed|published|said|found|"
                         r"issued|stated|revealed|admitted|backtracked|clarified)\b", re.I)


def _date_basis_findings(seg: dict, events: list) -> List[dict]:
    """A date the ledger holds as an article date, or as the date of a
    statement (an apology, a disclosure), is written as the date the
    development happened: "agents accessed Medicare on 29 September" for an
    apology that day about a June hack; "NIH terminated grants on 28
    September" for a report of that date (sixth review, 16 Oct 2026, F01)."""
    from app.services.daily_report_service import _sentences, _dates_in, _date_matches
    by_date: Dict[tuple, list] = {}
    for e in events or []:
        d = str(e.get("date") or "")[:10]
        if len(d) == 10 and d[4] == "-":
            try:
                by_date.setdefault((int(d[5:7]), int(d[8:10]), int(d[:4])), []).append(e)
            except ValueError:
                continue
    from app.services.daily_report_service import _DATE_WORDS, _DATE_ISO, _MONTHS
    out = []
    for sent in _sentences(seg["text"]):
        # The speech verb must sit in the clause that carries the date, not
        # anywhere in the sentence: "agents accessed Medicare on 29 September
        # ..., prompting the company to apologise" passed on "apologise".
        located = []
        for m in _DATE_WORDS.finditer(sent):
            mon = _MONTHS.get(m.group(1).lower().rstrip("."))
            if mon:
                located.append(((mon, int(m.group(2)), int(m.group(3)) if m.group(3) else None), m.start(), m.end()))
        for m in _DATE_ISO.finditer(sent):
            located.append(((int(m.group(2)), int(m.group(3)), int(m.group(1))), m.start(), m.end()))
        located.extend(_day_first_dates(sent))
        for d, s0, s1 in located:
            # The clause that carries the date, from its last boundary (a
            # comma, a semicolon, "and", "while") to 25 characters after
            # the date: "the White House announced plans on 26 September …,
            # and NIH terminated grants on 28 September" must not pass on
            # the earlier clause's "announced" (eighth review, 16 Oct 2026).
            before = sent[:s0]
            cut = max(before.rfind(", "), before.rfind("; "), before.rfind(" and "), before.rfind(" while "),
                      before.rfind(": "))
            window = sent[max(0, cut + 1 if cut >= 0 else 0):min(len(sent), s1 + 25)]
            if _SPEECH.search(window):
                continue
            matches = [e for key, evs in by_date.items() if _date_matches(d, [key]) for e in evs]
            if not matches:
                continue
            # Several events can share a date; keep the ones the sentence is
            # about (actor or subject words in the sentence), or an unrelated
            # launch on the same day lets "agents accessed Medicare on 29
            # September" through (round nine, 16 Oct 2026).
            if len(matches) > 1:
                swords = set(_WORD.findall(sent.lower()))
                # The event the sentence is about: first by actor (initials
                # count), then by subject words. Subject words alone let
                # Newsom's "California Foundation for Science and Health
                # Research" stand in for NSF's withholding on the same day
                # (ninth review, 16 Oct 2026).
                # Actors are matched in the date's own clause: a sentence
                # that names NIH in its second clause must not let an NIH
                # event stand in for NSF's in the first (17 Oct 2026).
                clause = _clause_of(sent, s0)
                sent_toks = ({_norm_tok(w) for w in _WORD.findall(clause.lower())}
                             | {_norm_tok(w) for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", clause)})
                def _by_actor(e):
                    return bool(_actor_tokens(e) & sent_toks)
                def _by_subject(e):
                    s_ = {w for w in _WORD.findall(str(e.get("subject") or "").lower()) if len(w) > 3}
                    return len(s_ & swords) >= 2
                narrowed = [e for e in matches if _by_actor(e)] or [e for e in matches if _by_subject(e)]
                if narrowed:
                    matches = narrowed
            label = f"{d[1]} {['','January','February','March','April','May','June','July','August','September','October','November','December'][d[0]]}"
            if all(str(e.get("date_basis") or "") == "article" for e in matches):
                out.append({"target": seg["target"], "severity": "error", "check": "date",
                            "finding": f"{label} is the article date of every ledger event carrying it (reported, not occurred); the sentence dates the development itself.",
                            "claim_text": sent, "source": "preflight",
                            "suggested_fix": f"Write 'reported on {label}' or attach the date to the reporting, not to the development."})
                break
            if all(_SPEECH_ACT.search(str(e.get("action") or "")) for e in matches):
                acts = sorted({str(e.get("action")).split()[0].lower() for e in matches})
                out.append({"target": seg["target"], "severity": "error", "check": "date",
                            "finding": f"On {label} the ledger's event is a statement ({', '.join(acts)}), not the development it describes; the sentence dates the development.",
                            "claim_text": sent, "source": "preflight",
                            "suggested_fix": f"Date the statement: '<actor> {acts[0]} on {label} that …', and leave the underlying development undated unless the ledger dates it."})
                break
    return out


_TYPE_NOUN = (r"(agreements?|deals?|approvals?|submissions?|partnerships?|launches|releases?|acquisitions?|"
              r"contracts?|filings?|retractions?|terminations?|licen[cs]es?|licensing agreements?|investments?|"
              r"settlements?|lawsuits?)")
# Up to three words may sit between the number and the type noun ("nine
# generic/biosimilar submissions"); a second type may follow ("submissions
# and approvals"). Seventh review, 16 Oct 2026, F03.
_TYPE_COUNT = re.compile(r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
                         r"sixteen|seventeen|eighteen|nineteen|twenty)\s+(?:(?!scenarios?\b)[\w/&-]+\s+){0,3}?" + _TYPE_NOUN
                         + r"(?:\s*(?:,|and|or|/)\s*" + _TYPE_NOUN + r")?\b", re.I)
_TYPE_STEMS = {"agreement": ("agree", "partner", "deal", "contract", "sign", "mou", "alliance"),
               "deal": ("agree", "partner", "deal", "contract", "sign", "acqui"),
               "approval": ("approv", "clear", "authoris", "authoriz", "granted"),
               "submission": ("submit", "fil", "applic"), "filing": ("fil", "submit", "applic"),
               "partnership": ("partner", "agree", "alliance", "collaborat", "deal"),
               "launch": ("launch", "open", "unveil"), "release": ("releas", "publish", "open"),
               "acquisition": ("acqui", "bought", "purchas", "takeover"), "contract": ("contract", "award", "agree"),
               "retraction": ("retract",), "termination": ("terminat", "cancel", "withh"),
               "licen": ("licens",), "investment": ("invest", "equity", "stake", "convertible"),
               "settlement": ("settl",), "lawsuit": ("sued", "lawsuit", "litigat")}


def _type_count_findings(seg: dict, scen: list) -> List[dict]:
    """'Ten completed agreements' for a ledger of model releases, platform
    access and launches: the total is right and its meaning is wrong (sixth
    review, F04)."""
    from app.services.daily_report_service import _sentences
    out = []
    for sent in _sentences(seg["text"]):
        for m in _TYPE_COUNT.finditer(sent):
            raw = m.group(1).lower()
            n = int(raw) if raw.isdigit() else _NUM_WORDS.get(raw)
            word = m.group(2).lower()
            stem_key = next((k for k in _TYPE_STEMS if word.startswith(k[:5])), None)
            if not n or not stem_key:
                continue
            stems = tuple(_TYPE_STEMS[stem_key])
            word2 = (m.group(3) or "").lower()
            key2 = next((k for k in _TYPE_STEMS if word2 and word2.startswith(k[:5])), None)
            if key2:
                stems = stems + tuple(_TYPE_STEMS[key2])
                word = f"{word} and {word2}"
                stem_key = f"{stem_key} or {key2}"
            for sc in scen:
                evs = sc.get("events") or []
                if not evs or n not in ((sc.get("n_confirm") or 0), (sc.get("n_confirm") or 0) + (sc.get("n_counter") or 0)):
                    continue
                typed = [e for e in evs if any(s in (str(e.get("action") or "") + " " + str(e.get("subject") or "")).lower() for s in stems)]
                if len(typed) < len(evs):
                    acts = sorted({str(e.get("action") or "").lower() for e in evs})[:6]
                    out.append({"target": seg["target"], "severity": "error", "check": "state",
                                "finding": f"The sentence counts {n} {word}; the '{sc.get('name')}' ledger's {len(evs)} events are not all {stem_key}s (actions: {', '.join(acts)}).",
                                "claim_text": sent, "source": "preflight",
                                "suggested_fix": f"Say '{n} confirming events' and name the mix of types, or count only the {stem_key}s."})
                    break
            else:
                continue
            break
    return out


_PROGRESS = re.compile(r"\b(emerging|emerges|emerged|emergence|emergent|accelerat\w*|materialis\w*|materializ\w*|gaining|gains|taking hold|"
                       r"under ?way|is forming|are forming|routing around|substitut\w*|bearing out|confirm(?:ed|ing|s)|"
                       r"advancing|advances|strengthening|momentum|is building|are building|now fill|filling)\b", re.I)
_HEDGE = re.compile(r"\b(too early|no (?:[\w-]+ ){0,3}events?|not yet|watch|would|could|may|might|if|hypothes\w*|"
                    r"remains? to be seen|no evidence|absent|unconfirmed|has not|have not|despite having no|"
                    r"question to test|remains a question|whether)\b", re.I)
_NAME_GENERIC = {"models", "model", "systems", "system", "networks", "network", "research", "traditional",
                 "practical", "applications", "transition", "transformation", "markets", "market", "drives",
                 "emerges", "emerging", "persists", "mandates", "replace", "challenge", "unlocks", "disrupt",
                 "disrupting", "reshapes", "reaching", "limits", "fragmenting", "control", "authority",
                 "leadership", "innovation", "bodies", "clusters", "fill", "void", "governance"}


def _name_tokens(name: str) -> list:
    """The first two distinctive words of a scenario name, spelling
    normalised (decentralised = decentralized)."""
    toks = [_norm_tok(w) for w in re.findall(r"[A-Za-z][A-Za-z-]+", str(name or ""))]
    toks = [t for t in toks if len(t) >= 5 and t not in _NAME_GENERIC]
    return toks[:2]


def _norm_tok(w: str) -> str:
    w = w.lower().replace("’", "'")
    w = re.sub(r"'s$", "", w)
    w = w.replace("isation", "ization").replace("ised", "ized").replace("ise", "ize").replace("ising", "izing")
    return w


def _names_scenario(sent_low: str, sc: dict, strict: bool = False) -> bool:
    """``strict`` takes the full name or its first two or three words only;
    the two-token match ("biosimilar … partnership") read "Samsung expanded
    its partnership for six biosimilar candidates" as naming Biosimilar
    Partnership Models and held a nine-event count to it (16 Oct 2026)."""
    name = str(sc.get("name") or "").lower()
    if len(name) > 3 and name in sent_low:
        return True
    shorts = [" ".join(name.split()[:k]) for k in (3, 2)]
    if any(len(s) > 10 and s in sent_low for s in shorts):
        return True
    if strict:
        return False
    toks = _name_tokens(sc.get("name"))
    if len(toks) == 2:
        norm = " ".join(_norm_tok(w) for w in re.findall(r"[A-Za-z][A-Za-z'’-]+", sent_low))
        p1, p2 = norm.find(toks[0]), norm.find(toks[1])
        if p1 >= 0 and p2 >= 0 and abs(p1 - p2) <= 50:
            return True
    return False


def _progress_findings(seg: dict, scen: list) -> List[dict]:
    """An overview that says a scenario with no judged events is emerging,
    accelerating or routing around gatekeepers (sixth review, F03)."""
    from app.services.daily_report_service import _sentences
    out = []
    early = [sc for sc in scen if (sc.get("n_confirm") or 0) + (sc.get("n_counter") or 0) == 0 and len(str(sc.get("name") or "")) > 3]
    if not early:
        return out
    for sent in _sentences(seg["text"]):
        low = sent.lower()
        stripped = low
        for sc in scen:
            nm = str(sc.get("name") or "").lower()
            if len(nm) > 3:
                stripped = stripped.replace(nm, " ")
        if not _PROGRESS.search(stripped) or _HEDGE.search(sent):
            continue
        for sc in early:
            if _names_scenario(low, sc):
                out.append({"target": seg["target"], "severity": "error", "check": "contradiction",
                            "finding": f"The sentence describes '{sc.get('name')}' as developing; its ledger has no judged events (Too early).",
                            "claim_text": sent, "source": "preflight",
                            "suggested_fix": "Present it as a watch item or a hypothesis, not as something observed this cycle."})
                break
    return out


# ── Seventh review (16 Oct 2026): who did it, where, and what kind ─────

_TOK_STOP = {"the", "and", "for", "with", "its", "from", "that", "this", "into", "their", "through", "than",
             "model", "models", "agent", "agents", "system", "systems", "government", "website", "websites",
             "online", "data", "research", "report", "reported", "disclosed", "announced", "said", "about",
             "after", "over", "under", "while", "which", "where", "when", "have", "been", "were", "will",
             "also", "more", "most", "other", "such", "these", "those", "between", "across", "against",
             "including", "within", "quarter", "period", "event", "events", "company", "companies", "platform",
             "platforms", "service", "services", "national", "federal", "state", "public", "global", "new",
             "first", "united", "states", "university", "institute", "group", "based", "using", "used", "use",
             "would", "could", "should", "scenario", "scenarios", "topic", "activity", "development",
             "developments", "signals", "signal", "million", "billion", "fund", "funding", "funds", "funded",
             "percent", "total", "programme", "program", "initiative", "project", "projects"}
_GENERIC_ACTOR = {"administration", "government", "researchers", "university", "foundation", "agencies",
                  "agency", "office", "house", "white", "department", "national", "medicine", "group", "company",
                  "consortium", "publishers", "publisher", "unnamed", "coalition", "officials", "ministry",
                  "council", "institute", "committee", "authority", "court", "state", "federal", "trump"}


def _stem(w: str) -> str:
    w = _norm_tok(w)
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            w = w[: -len(suf)]
            break
    if len(w) > 3 and w[-1] == w[-2]:
        w = w[:-1]
    return w


def _content_tokens(text: str) -> set:
    return {_stem(w) for w in re.findall(r"[A-Za-z][A-Za-z'’-]+", str(text or ""))
            if len(w) >= 4 and w.lower() not in _TOK_STOP}


def _event_text(e: dict) -> str:
    return " ".join(str(e.get(k) or "") for k in ("actor", "action", "subject", "magnitude"))


def _actor_tokens(e: dict) -> set:
    """Words that name the actor: four letters or more, or an acronym of
    three ("NIH"), minus generic words."""
    actor = str(e.get("actor") or "")
    toks = {_norm_tok(w) for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", actor)
            if (len(w) >= 4 or (len(w) == 3 and w.isupper())) and w.lower() not in _GENERIC_ACTOR}
    # Initials of the capitalised words ("National Science Foundation" is
    # written NSF in the narrative).
    caps = [w for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", actor.split("(")[0]) if w[0].isupper()]
    if len(caps) >= 3:
        toks.add("".join(w[0].lower() for w in caps))
    return toks


def _proper_words(sent: str) -> set:
    """Capitalised words of a sentence (not the first word), normalised."""
    words = re.findall(r"[A-Za-z][A-Za-z'’&-]+", sent)
    # The first word is capitalised whatever it is; it counts only when it
    # is an actor name the caller filters for ("OpenAI models submitting…"
    # opens a clause with the actor).
    return {_norm_tok(w) for w in words if w[0].isupper()}


_CLAUSE_SPLIT = re.compile(r"[,;:]\s+|\s+(?:yet|while|but|whereas|and)\s+")


# A colon introduces a list and commas separate its items ("licensing
# agreements completed: Sanofi–Regeneron (…), AstraZeneca–Summit (…)");
# the deal-type check keeps the list in one clause.
_DEAL_SPLIT = re.compile(r";\s+|\s+(?:yet|while|but|whereas)\s+")


def _clause_of(sent: str, pos: int, splitter=None) -> str:
    """The clause of ``sent`` that contains character ``pos``."""
    start = 0
    for m in (splitter or _CLAUSE_SPLIT).finditer(sent):
        if m.start() > pos:
            return sent[start:m.start()]
        start = m.end()
    return sent[start:]


def _actor_findings(seg: dict, events: list) -> List[dict]:
    """A development credited to the wrong company: "OpenAI models submitting
    false tips to police" for Anthropic's Claude event (seventh review,
    16 Oct 2026, F01). A clause that shares three distinctive words with an
    event, one of them rare, and names another ledger actor but not the
    event's, is flagged. Clauses, not sentences: "Samsung expanded its Teva
    deal, while nine filings and approvals completed across … Afinitor"
    credits Samsung with nothing but its own deal."""
    from app.services.daily_report_service import _sentences
    out = []
    evs = [e for e in (events or []) if _actor_tokens(e)]
    if not evs:
        return out
    df: Dict[str, int] = {}
    ev_toks = []
    for e in evs:
        toks = _content_tokens(_event_text(e)) - _actor_tokens(e) - {_stem(w) for w in _actor_tokens(e)}
        ev_toks.append(toks)
        for t in toks:
            df[t] = df.get(t, 0) + 1
    # An actor word names an actor when few actors carry it ("Quantum" is
    # in Google Quantum AI, Zapata Quantum and IBM Quantum; it names none).
    actor_df: Dict[str, int] = {}
    for actor in {str(e.get("actor") or "") for e in evs}:
        for t in _actor_tokens({"actor": actor}):
            actor_df[t] = actor_df.get(t, 0) + 1
    all_actor_toks = {t for t, n in actor_df.items() if n <= 2}
    for sent in _sentences(seg["text"]):
        sent_words = {_norm_tok(w) for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", sent)}
        flagged = False
        for clause in _CLAUSE_SPLIT.split(sent):
            if flagged or not clause or not clause.strip():
                continue
            ctoks = _content_tokens(clause)
            named = _proper_words(clause) & all_actor_toks
            if not named:
                continue
            def _named_in_sentence(mine: set) -> bool:
                if mine & sent_words:
                    return True
                return any(len(m) >= 5 and (w.startswith(m[:5]) or m.startswith(w[:5]))
                           for m in mine for w in sent_words if len(w) >= 5)
            # Events whose actor the sentence names explain the clause's
            # words; a match on another event that uses the same words is
            # not a misattribution.
            explained = set()
            for e, toks in zip(evs, ev_toks):
                if _named_in_sentence(_actor_tokens(e)):
                    explained |= ctoks & toks
            for e, toks in zip(evs, ev_toks):
                shared = ctoks & toks
                if len(shared) < 3 or not any(df.get(t, 0) <= 2 for t in shared):
                    continue
                mine = _actor_tokens(e)
                if _named_in_sentence(mine) or shared <= explained:
                    continue
                etext_words = {_norm_tok(w) for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", _event_text(e))}
                others = named - mine - etext_words
                if not others:
                    continue
                out.append({"target": seg["target"], "severity": "error", "check": "identity",
                            "finding": (f"The sentence names {', '.join(sorted(others))} alongside '{' '.join(sorted(shared))}'; "
                                        f"the ledger event with those words is {e.get('actor')}'s ({str(e.get('action') or '')} "
                                        f"{str(e.get('subject') or '')[:90]})."),
                            "claim_text": sent, "source": "preflight",
                            "suggested_fix": f"Credit the development to {e.get('actor')} and keep the other actor's events separate."})
                flagged = True
                break
    return out


_SECURITY = re.compile(r"\b(breach\w*|hack\w*|intrusion\w*|security incidents?|security breach\w*|cyberattack\w*|"
                       r"infiltrat\w*|compromis\w*|attacks? on)\b", re.I)
_EDITORIAL = re.compile(r"\b(peer[- ]review(?:ed)?\s+(?:platform|system|process|infrastructure|credibility|integrity)s?|review platforms?|"
                        r"editorial (?:system|platform|workflow)s?|manuscript (?:system|platform)s?|"
                        r"journal (?:platform|system)s?|submission systems?)\b", re.I)
_ANALOGY = re.compile(r"\b(if|were|would|could|may|might|analog\w*|similar|equivalent|comparable|hypothes\w*|"
                      r"whether|worth watching|risk of|exposure)\b", re.I)


def _transfer_findings(seg: dict, events: list, scen: Optional[list] = None,
                       topics: Optional[list] = None) -> List[dict]:
    """A security incident moved to a kind of platform the ledger has no
    incident at: "security breaches at review platforms" when the agents
    were at government and other online systems (seventh review, F02).
    Hedged as a hypothesis or analogy before the security word, it passes."""
    from app.services.daily_report_service import _sentences
    out = []
    evtexts = [_event_text(e) for e in (events or [])]
    if any(_SECURITY.search(t) and _EDITORIAL.search(t) for t in evtexts):
        return out
    names = [str(sc.get("name") or "") for sc in (scen or []) if len(str(sc.get("name") or "")) > 3]
    names += [str(t) for t in (topics or []) if len(str(t or "")) > 3]
    for sent in _sentences(seg["text"]):
        probe = sent
        for nm in names:
            probe = re.sub(re.escape(nm), " ", probe, flags=re.I)
        ms = _SECURITY.search(probe)
        me = _EDITORIAL.search(probe)
        if not ms or not me:
            continue
        if _ANALOGY.search(probe[: ms.start()]):
            continue
        out.append({"target": seg["target"], "severity": "error", "check": "absent",
                    "finding": (f"The sentence places a security incident ('{ms.group(0)}') at '{me.group(0)}'; "
                                "no ledger event records an incident at a peer-review or editorial platform "
                                "(the agent incidents were at government and other online systems)."),
                    "claim_text": sent, "source": "preflight",
                    "suggested_fix": "Name the government/online incidents the ledger has, then put the risk to editorial systems as an analogy or hypothesis ('if … were to')."})
    return out


_CAUSAL = re.compile(r"\b((?:is|are|was|were)\s+(?:forcing|driving|prompting|compelling|pushing|triggering|fuell?ing|causing)|"
                     r"forc(?:e|es|ed|ing)\s+(?:the\s+)?(?:adoption|uptake|shift)|accelerat(?:ing|es|e)\s+(?:demand|adoption|uptake)"
                     r"\s+(?:for|of)|(?:leads?|leading|led)\s+to\s+(?:the\s+)?(?:adoption|formation|rise)|"
                     r"(?:as a result of|because of|in response to)\b)", re.I)


def _causal_findings(seg: dict) -> List[dict]:
    """"Operational failures are forcing the adoption of hybrid validation
    partnerships": the ledger has both developments, not that one drives
    the other (seventh review, F02). A causal link needs a hedge or an
    event that states it."""
    from app.services.daily_report_service import _sentences
    out = []
    for sent in _sentences(seg["text"]):
        m = _CAUSAL.search(sent)
        if not m or _HEDGE.search(sent):
            continue
        out.append({"target": seg["target"], "severity": "error", "check": "absent",
                    "finding": f"The sentence asserts a causal link ('{m.group(0)}'); the ledger records the developments, not that one caused the other.",
                    "claim_text": sent, "source": "preflight",
                    "suggested_fix": "Write the developments as appearing in parallel and pose the link as a question to test ('whether X is driving Y remains a question to test')."})
    return out


_DEAL_LABEL = re.compile(r"\b(licensing|licen[cs]es?|equity investments?|investments?|acquisitions?|mergers?|"
                         r"partnerships?|alliances?|collaborations?|approvals?|lawsuits?|litigation|settlements?)\b", re.I)
_DEAL_TYPES = {"licensing": ("licens",), "licence": ("licens",), "license": ("licens",),
               "investment": ("invest", "equity", "stake", "convertible"), "equity investment": ("invest", "equity", "stake", "convertible"),
               "acquisition": ("acqui", "bought", "purchas", "takeover"), "merger": ("merg",),
               "partnership": ("partner", "alliance", "collaborat", "joined", "agree", "deal"),
               "alliance": ("partner", "alliance", "collaborat", "joined", "agree", "deal"),
               "collaboration": ("partner", "alliance", "collaborat", "joined", "agree", "deal"),
               "approval": ("approv", "clear", "authori", "positive"), "lawsuit": ("sued", "lawsuit", "litigat", " suit"),
               "litigation": ("sued", "lawsuit", "litigat", " suit"), "settlement": ("settl",),
               "submission": ("submit", "filed", "applic", "certification"), "filing": ("submit", "filed", "applic", "certification")}


def _deal_key(word: str) -> Optional[str]:
    w = word.lower().rstrip("s")
    if w.endswith("ie"):
        w = w[:-2] + "y"
    for k in _DEAL_TYPES:
        if w == k or w.rstrip("s") == k or w.startswith(k[:6]):
            return k
    return None


def _event_deal_types(e: dict) -> set:
    text = " " + re.sub(r"unauthori[sz]\w*", " ", _event_text(e).lower())
    return {k for k, stems in _DEAL_TYPES.items() if any(s in text for s in stems)}


def _deal_type_findings(seg: dict, events: list, scen: list) -> List[dict]:
    """A named event listed under the wrong transaction type: AstraZeneca's
    equity investment in Summit under "licensing agreements" (seventh
    review, F03). The labels in the sentence must include the event's kind."""
    from app.services.daily_report_service import _sentences
    out = []
    names = [str(sc.get("name") or "").lower() for sc in (scen or []) if len(str(sc.get("name") or "")) > 3]
    for sent in _sentences(seg["text"]):
        low = sent.lower()
        for nm in names:
            low = low.replace(nm, " ")
        label_hits = [(m.start(), _deal_key(m.group(1))) for m in _DEAL_LABEL.finditer(low)]
        label_hits = [(p, k) for p, k in label_hits if k]
        if not label_hits:
            continue
        for e in events or []:
            mine = _actor_tokens(e)
            if not mine:
                continue
            # Where the sentence names the actor; the label must introduce
            # it (within 120 characters before, in the same clause) or
            # follow it closely (40 characters after).
            apos = [m.start() for m in re.finditer(r"[A-Za-z][A-Za-z'’&-]+", sent)
                    if _norm_tok(m.group(0)) in mine]
            if not apos:
                continue
            words = {_norm_tok(w) for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", sent)}
            subj = {_norm_tok(w) for w in re.findall(r"[A-Z][A-Za-z'’&-]{3,}", str(e.get("subject") or ""))} - mine
            if not (subj & words):
                continue
            labels = set()
            for p, k in label_hits:
                for a in apos:
                    if (p < a and a - p <= 120 and _clause_of(sent, p, _DEAL_SPLIT) == _clause_of(sent, a, _DEAL_SPLIT)) \
                            or (0 <= p - a <= 40):
                        labels.add(k)
            if not labels:
                continue
            label_stems = set().union(*[set(_DEAL_TYPES[k]) for k in labels])
            etypes = _event_deal_types(e)
            if not etypes:
                continue
            etext = " " + _event_text(e).lower()
            if any(s in etext for s in label_stems):
                continue
            out.append({"target": seg["target"], "severity": "error", "check": "state",
                        "finding": (f"The sentence files {e.get('actor')}'s event under '{', '.join(sorted(labels))}'; the ledger "
                                    f"event is '{str(e.get('action') or '')} {str(e.get('subject') or '')[:80]}' ({', '.join(sorted(etypes))})."),
                        "claim_text": sent, "source": "preflight",
                        "suggested_fix": f"Label it as the ledger does ({', '.join(sorted(etypes))}), or introduce the list with every type it contains."})
            break
    return out


_BASELINE = re.compile(r"\b(?:once|previously|formerly|traditionally|historically)\s+(?:reserved for|requir\w+|need\w+|"
                       r"limited to|confined to|the (?:domain|preserve) of|exclusive to|only possible on|handled by)\s+"
                       r"((?:(?!\b(?:and|which|that|counters?|but|while|yet|raises?|now|is|are)\b)[\w'’-]+\s+){0,3}"
                       r"(?!\b(?:and|which|that|counters?|but|while|yet|raises?|now|is|are)\b)[\w'’-]+)", re.I)


def _baseline_findings(seg: dict, events: list) -> List[dict]:
    """A comparison that swaps the event's baseline: "tasks once reserved for
    quantum hardware" for an algorithm the ledger compares with classical
    supercomputers (seventh review, F03)."""
    from app.services.daily_report_service import _sentences
    out = []
    evs = [(e, _content_tokens(_event_text(e))) for e in (events or [])]
    for sent in _sentences(seg["text"]):
        m = _BASELINE.search(sent)
        if not m:
            continue
        # The event is the one the clause around the comparison restates,
        # not the sentence's other event (a DoE roadmap and an Edinburgh
        # algorithm share one sentence on the quantum synthesis slide).
        clause = _clause_of(sent, m.start())
        stoks = _content_tokens(clause)
        if len(stoks) < 3:
            stoks = _content_tokens(sent)
        best = max(evs, key=lambda et: len(stoks & et[1]), default=None)
        if not best or len(stoks & best[1]) < 3:
            continue
        base_words = [w for w in re.findall(r"[A-Za-z]+", m.group(1)) if len(w) >= 5 and w.lower() not in _TOK_STOP]
        base_toks = [_stem(w) for w in base_words]
        if not base_toks:
            continue
        present = [t for t in base_toks if t in best[1]]
        # "world-class supercomputers" for "world's most powerful
        # supercomputers" keeps its head noun; "quantum hardware" for
        # "supercomputers" does not.
        if base_toks[-1] in best[1] and len(present) * 2 >= len(base_toks):
            continue
        out.append({"target": seg["target"], "severity": "error", "check": "state",
                    "finding": (f"The sentence sets the comparison baseline as '{m.group(1).strip()}'; the ledger event reads "
                                f"'{str(best[0].get('action') or '')} {str(best[0].get('subject') or '')[:100]}'."),
                    "claim_text": sent, "source": "preflight",
                    "suggested_fix": "Keep the event's own comparison baseline."})
    return out


# ── Eighth review (16 Oct 2026): rates, bridges and length ─────────────

_RATE = re.compile(r"\b(outpac\w+|faster than\b(?!\s+(?:anticipated|expected|forecast))|keep(?:s|ing)? pace|rate at which|far exceed\w*|smaller than the volume|"
                   r"can no longer absorb|cannot absorb|scale gap|exceed\w* (?:the )?(?:capacity|volume)|"
                   r"(?:is|are) accelerating\b|accelerating faster|at a faster rate|slower than\b|"
                   r"(?:is|are) (?:not )?scaling\b|past recovery)\b", re.I)
_RATE_OK = re.compile(r"\b(do(?:es)? not measure|not (?:a )?measure|cannot (?:establish|measure)|no measure|"
                      r"question to test|remains? (?:an? )?(?:open )?question|the question is whether)\b", re.I)


def _rate_findings(seg: dict) -> List[dict]:
    """"Incidents are outpacing the deployment of validation partnerships:
    ten events versus five" (eighth review, 16 Oct 2026, F2). The ledger
    has event counts and article-share deltas; neither is a rate, a volume
    or a capacity, so a sentence that compares speeds, volumes or capacity
    is flagged unless it says the counts do not measure that."""
    from app.services.daily_report_service import _sentences
    out = []
    for sent in _sentences(seg["text"]):
        m = _RATE.search(sent)
        if not m or _RATE_OK.search(sent):
            continue
        out.append({"target": seg["target"], "severity": "error", "check": "rate",
                    "finding": (f"The sentence compares rates, volumes or capacity ('{m.group(0)}'); the ledger has "
                                "scenario event counts and article-share deltas, neither of which measures a rate, "
                                "a volume of incidents or deployed capacity."),
                    "claim_text": sent, "source": "preflight",
                    "suggested_fix": "State the counts ('this quarter's evidence records ten confirming developments for X "
                                     "and five for Y'), say they show both patterns are present but do not measure whether "
                                     "one is keeping pace with the other, or drop the comparison. Never write 'the ledger' "
                                     "on a slide."})
    return out


_BRIDGE = re.compile(r"\b(prompt(?:s|ed|ing)|driv(?:es|en|ing)|suggest(?:s|ed|ing)?|pressure (?:on|from)|because of|"
                     r"as a result|lead(?:s|ing)? to|accelerat\w+ consolidation|margin pressure|forc(?:es|ed|ing)|"
                     r"spill\w*|caus(?:es|ed|ing)|in response to|responding to|is reshaping|are reshaping)\b", re.I)
_SEPARATE = re.compile(r"\b(separately|separate|distinct|does not connect|do not connect|no events? link\w*|"
                       r"in parallel|unrelated|different subjects)\b", re.I)
_BRIDGE_EXEMPT = re.compile(r"^\s*(If|Watch|Whether)\b")
_TOPIC_GENERIC = {"general", "monitoring", "transition", "uncertainty", "attacks", "expertise", "federal", "pullback",
                  "advantage", "science", "scientific", "publishers", "publishing", "research", "models", "systems",
                  "traditional", "practical", "applications", "networks", "platforms", "market", "business"}


def _topic_terms(ledger: Dict[str, dict]) -> Dict[str, set]:
    """Words that belong to one topic only: its name, its scenario names
    and its event actors (six letters or more, generic words dropped)."""
    raw: Dict[str, set] = {}
    for topic, lt in ledger.items():
        words = set()
        texts = [topic] + [str(sc.get("name") or "") for sc in (lt.get("scenarios") or [])]
        texts += [str(e.get("actor") or "") for e in (lt.get("events") or [])]
        for t in texts:
            for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", t):
                nw = _norm_tok(w)
                if len(nw) >= 6 and nw not in _TOPIC_GENERIC and nw not in _GENERIC_ACTOR:
                    words.add(nw)
        raw[topic] = words
    counts: Dict[str, int] = {}
    for ws in raw.values():
        for w in ws:
            counts[w] = counts.get(w, 0) + 1
    return {t: {w for w in ws if counts[w] == 1} for t, ws in raw.items()}


def _bridge_findings(seg: dict, ledger: Dict[str, dict]) -> List[dict]:
    """A causal link between two topics' developments: "the revenue shift
    from originator patents to biosimilar partnerships is prompting
    incumbents to re-evaluate their academic publishing portfolios" (eighth
    review, F1). Two topics' terms in one sentence with a causal connector,
    not marked as separate, is flagged; no event joins two topics."""
    from app.services.daily_report_service import _sentences
    out = []
    terms = _topic_terms(ledger)
    if len(terms) < 2:
        return out
    for sent in _sentences(seg["text"]):
        if _BRIDGE_EXEMPT.match(sent) or _SEPARATE.search(sent):
            continue
        m = _BRIDGE.search(sent)
        if not m:
            continue
        words = {_norm_tok(w) for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", sent)}
        hit = {t: sorted(words & ws)[:3] for t, ws in terms.items() if words & ws}
        if len(hit) < 2:
            continue
        out.append({"target": seg["target"], "severity": "error", "check": "bridge",
                    "finding": (f"The sentence joins developments of {', '.join(hit)} with a causal link ('{m.group(0)}'); "
                                "no event in the ledger connects them."),
                    "claim_text": sent, "source": "preflight",
                    "suggested_fix": "Keep each topic's developments in their own sentence and say they are separate; "
                                     "a link between them is a question to test, not a finding."})
    return out


_LENGTH_CAPS = {"cross_cutting_themes": (3, 380), "strategic_overview": (7, 1150), "executive_decision_framework": (5, 720)}


def _length_findings(seg: dict) -> List[dict]:
    """A theme body that runs to five long sentences is shrunk to tiny type
    and cut mid-sentence on the slide (eighth review, F4). The slide shows
    at most three complete sentences per theme."""
    from app.services.daily_report_service import _sentences
    path = seg.get("path") or ""
    key = next((k for k in _LENGTH_CAPS if path.startswith(k) and (path.endswith(".body") or path == k)), None)
    if not key:
        return []
    max_sent, max_chars = _LENGTH_CAPS[key]
    sents = [s for s in _sentences(seg["text"]) if s.strip()]
    n_chars = len(seg["text"].strip())
    if len(sents) <= max_sent and n_chars <= max_chars:
        return []
    return [{"target": seg["target"], "severity": "error", "check": "length",
             "finding": (f"The text runs to {len(sents)} sentences and {n_chars} characters; the slide shows at most "
                         f"{max_sent} complete sentences (about {max_chars} characters) and cannot cut mid-sentence."),
             "claim_text": seg["text"].strip(), "source": "preflight",
             "suggested_fix": f"Rewrite as at most {max_sent} complete sentences carrying the throughline and its two or "
                              "three named developments; the notes carry the evidence."}]


_CONTEXT = re.compile(r"\b(earlier|before the (?:window|forecast|quarter)|context|historical|historically|previously|"
                      r"last year|summer|spring|in (?:january|february|march|april|may|june|july|august) 20\d\d|"
                      r"pre-forecast|had (?:already )?(?:been|cut|cancelled|terminated))\b", re.I)


def _historical_findings(seg: dict, historical: list) -> List[dict]:
    """A development the window audit holds as historical context (its
    action predates the forecast) written as this period's: "NIH terminated
    Alzheimer's and kidney disease grants, reported on 28 September" after
    the NIH record was moved to summer context (ninth review, 16 Oct 2026).
    A sentence sharing three distinctive words with a historical row, and
    not marked as context, is flagged."""
    from app.services.daily_report_service import _sentences
    out = []
    hist = [(h, _content_tokens(_event_text(h))) for h in (historical or [])]
    if not hist:
        return out
    for sent in _sentences(seg["text"]):
        if _CONTEXT.search(sent):
            continue
        stoks = _content_tokens(sent)
        for h, toks in hist:
            shared = stoks & toks
            if len(shared) >= 3 and (_actor_tokens(h) & {_norm_tok(w) for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", sent)}
                                      or len(shared) >= 4):
                out.append({"target": seg["target"], "severity": "error", "check": "window",
                            "finding": (f"The sentence presents '{h.get('actor')} {h.get('action')} "
                                        f"{str(h.get('subject') or '')[:70]}' as this period's development; the window audit "
                                        f"holds it as historical context ({str(h.get('edited_by') or '')[:120]})."),
                            "claim_text": sent, "source": "preflight",
                            "suggested_fix": "Drop the development, or keep it only as context in so many words ('earlier terminations reported in September'), never as a dated action of the period or a confirming event."})
                break
    return out


# ── Tenth review (17 Oct 2026): geography ─────────────────────────────

_GEO_FRAME = re.compile(r"\b(Internationally|international(?:ly)?\b[^.]{0,40}\b(?:examples|developments|signals|evidence)|"
                        r"non-U\.?S\.?|outside the (?:U\.?S\.?|United States)|overseas|abroad|"
                        r"(?:in|across) (?:Europe|Asia|China|the EU|the UK))", re.I)
_GEO_CACHE: Dict[str, dict] = {}


async def geography_findings(segments: List[dict], ledger: Dict[str, dict]) -> List[dict]:
    """"Internationally, IonQ's Cambridge centre, CERN's OpenSearch
    deployment, Google's access provision to 200 European researchers, and
    WashU Medicine researchers' prize-winning tool reinforce the need to
    track non-U.S. research infrastructure" (tenth review, 17 Oct 2026):
    WashU Medicine is in St. Louis. A sentence framed as international is
    checked development by development: the events it names go to the
    geography judge, which says where each development takes place (an IonQ
    centre in Cambridge is outside the U.S. although IonQ is not), and a
    U.S. development in the list is an error."""
    from app.services.daily_report_service import _sentences
    from app.services.wiley_bundle_supervisor import _call_agent
    events_all = [e for lt in ledger.values() for e in (lt.get("events") or [])]
    hits = []  # (seg, sentence, [events named])
    for seg in segments:
        for sent in _sentences(seg["text"]):
            if not _GEO_FRAME.search(sent):
                continue
            words = {_norm_tok(w) for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", sent)}
            stems = {_stem(w) for w in re.findall(r"[A-Za-z][A-Za-z'’&-]+", sent)}
            named, seen = [], set()
            for e in events_all:
                toks = _actor_tokens(e)
                key = _event_text(e)
                # The actor's event the sentence names: its own words
                # ("Cambridge centre", "prize-winning tool") are in the
                # sentence too, or every IonQ event would count.
                own = _content_tokens(f"{e.get('action') or ''} {e.get('subject') or ''}") - {_stem(t) for t in toks}
                if toks and toks & words and own & stems and key not in seen:
                    seen.add(key)
                    named.append(e)
            if named:
                hits.append((seg, sent, named))
    if not hits:
        return []
    todo = {}
    for _seg, _sent, named in hits:
        for e in named:
            key = _event_text(e)
            if key not in _GEO_CACHE:
                todo[key] = e
    if todo:
        payload = {"developments": [{"id": i, "actor": e.get("actor"), "action": e.get("action"),
                                     "subject": e.get("subject")} for i, e in enumerate(todo.values())]}
        try:
            res = await _call_agent("wiley_geography_agent", payload)
        except Exception as e:
            logger.warning("geography judge failed: %s", e)
            res = {}
        keys = list(todo)
        for v in ((res or {}).get("developments") or []):
            try:
                _GEO_CACHE[keys[int(v.get("id"))]] = v
            except (TypeError, ValueError, IndexError):
                continue
    out = []
    for seg, sent, named in hits:
        us = []
        for e in named:
            v = _GEO_CACHE.get(_event_text(e)) or {}
            if str(v.get("location") or "").lower() == "us":
                us.append((e, v))
        if not us:
            continue
        what = "; ".join(f"{e.get('actor')} ({v.get('reason') or 'United States'})" for e, v in us)
        out.append({"target": seg["target"], "severity": "error", "check": "geography",
                    "finding": f"The sentence groups a U.S. development as international: {what}.",
                    "claim_text": sent, "source": "preflight",
                    "suggested_fix": "Drop the U.S. development from the international list; if it belongs in the "
                                     "letter, it goes in a U.S. sentence."})
    return out


def preflight(segments: List[dict], ledger: Dict[str, dict], extra_numbers: List = ()) -> List[dict]:
    from app.services.daily_report_service import (_dates_in, _numbers_in, _sentences,
                                                   _date_matches, _DATE_WORDS, _DATE_ISO)
    all_topics = list(ledger.values())
    facts_all = _facts(all_topics, extra_numbers)
    facts_by_topic = {t: _facts([lt], extra_numbers) for t, lt in ledger.items()}
    findings: List[dict] = []
    scen_all = [sc for lt in all_topics for sc in (lt.get("scenarios") or [])]
    events_all = [e for lt in all_topics for e in (lt.get("events") or [])]
    for seg in segments:
        if seg.get("kind") == "topic" and seg.get("topic") in ledger:
            scen = ledger[seg["topic"]].get("scenarios") or []
            evs = ledger[seg["topic"]].get("events") or []
            findings.extend(_sweep_findings(seg, scen))
            findings.extend(_count_findings(seg, scen))
            findings.extend(_event_count_findings(seg, scen))
            findings.extend(_silence_findings(seg, scen))
            findings.extend(_points_findings(seg, scen))
            findings.extend(_date_basis_findings(seg, evs))
            findings.extend(_type_count_findings(seg, scen))
            findings.extend(_progress_findings(seg, scen))
            findings.extend(_actor_findings(seg, evs))
            findings.extend(_transfer_findings(seg, evs, scen, topics=list(ledger)))
            findings.extend(_causal_findings(seg))
            findings.extend(_deal_type_findings(seg, evs, scen))
            findings.extend(_baseline_findings(seg, evs))
            findings.extend(_rate_findings(seg))
            findings.extend(_historical_findings(seg, ledger[seg["topic"]].get("historical") or []))
        elif seg.get("kind") == "verdict" and seg.get("topic") in ledger:
            scen = ledger[seg["topic"]].get("scenarios") or []
            findings.extend(_points_findings(seg, scen))
            findings.extend(_date_basis_findings(seg, ledger[seg["topic"]].get("events") or []))
            if "key_signals[" in seg.get("path", ""):
                findings.extend(_signal_findings(seg, scen, ledger[seg["topic"]].get("events") or []))
        else:
            findings.extend(_count_findings(seg, scen_all, per_topic=[lt.get("scenarios") or [] for lt in all_topics]))
            findings.extend(_event_count_findings(seg, scen_all))
            findings.extend(_points_findings(seg, scen_all))
            findings.extend(_date_basis_findings(seg, events_all))
            findings.extend(_type_count_findings(seg, scen_all))
            findings.extend(_progress_findings(seg, scen_all))
            findings.extend(_actor_findings(seg, events_all))
            findings.extend(_transfer_findings(seg, events_all, scen_all, topics=list(ledger)))
            findings.extend(_causal_findings(seg))
            findings.extend(_deal_type_findings(seg, events_all, scen_all))
            findings.extend(_baseline_findings(seg, events_all))
            findings.extend(_rate_findings(seg))
            findings.extend(_bridge_findings(seg, ledger))
            findings.extend(_length_findings(seg))
            findings.extend(_historical_findings(seg, [h for lt in all_topics for h in (lt.get("historical") or [])]))
        dates, nums, corpus = facts_by_topic.get(seg.get("topic")) if seg.get("kind") == "topic" else facts_all
        if seg.get("kind") == "topic" and seg.get("topic") not in facts_by_topic:
            dates, nums, corpus = facts_all
        for sent in _sentences(seg["text"]):
            for d in list(_dates_in(sent)) + [t for t, _a, _b in _day_first_dates(sent)]:
                if not _date_matches(d, dates):
                    label = f"{d[0]:02d}-{d[1]:02d}" + (f"-{d[2]}" if len(d) > 2 and d[2] else "")
                    findings.append({"target": seg["target"], "severity": "error", "check": "date",
                                     "finding": f"The date {label} appears in no event in the ledger.",
                                     "claim_text": sent, "source": "preflight",
                                     "suggested_fix": "Use the event's date from the ledger or drop the date."})
            stripped = _DATE_DAY_FIRST.sub(" ", _DATE_WORDS.sub(" ", _DATE_ISO.sub(" ", sent)))
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
        # The verdict is computed here, not taken from the judge: only a
        # claim the ledger contradicts (false) or lacks (absent) can block.
        # The judge has rated correct sentences "error" for wording.
        status = str(f.get("claim_status") or "").lower()
        if f["severity"] == "error" and status not in ("false", "absent", "audience"):
            f["severity"] = "warning"
            f["finding"] = (f.get("finding") or "") + f" [claim_status={status or 'unset'}; not blocking]"
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
               "segments": [({"target": s["target"], "topic": s.get("topic"), "text": s["text"], "body": s["body"]}
                             if s.get("body") else {"target": s["target"], "topic": s.get("topic"), "text": s["text"]})
                            for s in segments]}
    out = await _call_agent("wiley_narrative_judge_agent", payload)
    if not out:
        return [{"target": "*", "severity": "warning", "check": "review_failed", "source": "judge",
                 "finding": "The narrative judge did not answer; only the deterministic preflight ran.",
                 "claim_text": "", "suggested_fix": ""}]
    return _quote_gate((out or {}).get("findings") or [], segments)


# Dates and bare figures belong to the preflight. "metric" was in this set
# and demoted the judge's correct "10 points vs a delta of 2.18" to advisory
# because the figure check had matched the 10 to an event count (fifth
# review, 16 Oct 2026, F05); the points check above now owns that case.
_PREFLIGHT_OWNED = {"date", "figure", "date type", "actor", "causal", "transfer", "deal type", "baseline",
                    "rate", "bridge", "length", "window", "geography"}
_IMPERATIVE = re.compile(r"^(Monitor|Pilot|Establish|Launch|Build|Develop|Form|Engage|Stress-test|Prepare|Create|Define|"
                         r"Set|Track|Watch|Scope|Review|Negotiate|Invest|Fund|Audit|Map|Run|Use|Keep|Hold|Expand|Maintain|"
                         r"Secure|Design|Commission|Adopt|Require|Treat|Separate|Position|Price|Shift|Plan|Test|Assess|"
                         r"Brief|Convene|Draft|Identify|Introduce|Offer|Open|Pursue|Reserve|Retain|Start|Stop|Target|Tie|"
                         r"Train|Update|Allocate|Appoint|Assign|Benchmark|Budget|Clarify|Extend|Equip|Formalise|Formalize|"
                         r"Prioritise|Prioritize|Protect|Publish|Quantify|Rebalance|Recruit|Resist|Safeguard|Stage)\b")
_HYPOTHESIS = re.compile(r"^(If|Should|Were|Whether|Unless)\b|\bif\b.{0,160}\bthen\b|\b(would|could|may|might)\b", re.I)
# "Wiley should pilot …", "We should launch …": an action for the organisation,
# which the judge rated an audience error (eighth review, 16 Oct 2026).
_ORG_ACTION = re.compile(r"\b(?:we|wiley|the (?:company|organisation|organization))\s+(?:should|must|can|could|will|need|needs)\b", re.I)


def _status_matches(claim: str, scen_all: list) -> bool:
    """True when every scenario the sentence names is given its ledger
    status word; the judge called 'remains unconfirmed with one countering
    event' a contradiction of a ledger that said Unconfirmed, 0/1."""
    low = (claim or "").lower()
    named = [sc for sc in scen_all if len(str(sc.get("name") or "")) > 3 and str(sc.get("name")).lower() in low]
    if not named:
        return False
    for sc in named:
        st = str(sc.get("status") or "").lower()
        if not st or st not in low.replace(str(sc.get("name")).lower(), ""):
            return False
    return True
_SELF_CONTRADICTING = re.compile(
    r"\b(correctly|accurately|is accurate|is grounded|matches the ledger|as stated|"
    r"which matches|exactly as stated|is appropriate|which is appropriate|verb|singular|plural|grammatical)\b", re.I)



_WORD = re.compile(r"[a-z0-9]+")


def _paraphrases_event(claim: str, events: list) -> bool:
    """True when the claim sentence restates one ledger event: most of its
    content words appear in that event's text. A judge called "2,800
    viruses" unsupported because the event said "over 2,800 viruses"
    (16 Oct 2026); that is wording, not an absent development."""
    words = {w for w in _WORD.findall((claim or "").lower()) if len(w) > 3}
    if len(words) < 4:
        return False
    for e in events or []:
        text = " ".join(str(e.get(k) or "") for k in ("actor", "action", "subject", "magnitude", "date")).lower()
        etoks = set(_WORD.findall(text))
        if len(words & etoks) / len(words) >= 0.6:
            return True
    return False

def _merge(preflight_f: List[dict], judge_f: List[dict], events: Optional[list] = None,
           scen_all: Optional[list] = None) -> List[dict]:
    # Dates and figures belong to the deterministic preflight. A judge
    # "error" on a sentence the preflight passed is advisory (the judge
    # called "2.18 percentage points" wrong while saying it was right,
    # 16 Oct 2026). A finding that itself says the sentence is correct
    # cannot block either.
    pre_keys = {(f.get("target"), (f.get("claim_text") or "")[:80]) for f in preflight_f}
    adjusted = []
    for f in judge_f:
        f = dict(f)
        if f.get("severity") == "error":
            key = (f.get("target"), (f.get("claim_text") or "")[:80])
            # A points figure the deterministic points check accepted is
            # right; the judge read "0.83 points" against a ledger value of
            # 0.83 and called it wrong (16 Oct 2026, round 8).
            points_owned = (f.get("check") == "metric" and _POINTS.search(f.get("claim_text") or "")
                            and key not in pre_keys)
            claim = f.get("claim_text") or ""
            # A sentence that gives each named scenario its ledger status is
            # not a contradiction; an action written as an imperative with
            # no figure is not a claim; a sentence marked as a hypothesis
            # ("If … then", "could") is not asserting the outcome.
            # (Round nine, 16 Oct 2026: the judge rated all three as errors.)
            soft = ((f.get("check") == "contradiction" and _status_matches(claim, scen_all or []))
                    or (f.get("check") == "audience" and _ORG_ACTION.search(claim))
                    or (f.get("check") in ("unsupported", "absent") and _IMPERATIVE.match(claim.strip())
                        and not re.search(r"\d", claim))
                    or (f.get("check") in ("state", "unsupported", "absent", "hypothesis as fact")
                        and _HYPOTHESIS.search(claim.strip()) and not re.search(r"\d{4}", claim)))
            if soft or points_owned or (f.get("check") in _PREFLIGHT_OWNED and key not in pre_keys) \
                    or _SELF_CONTRADICTING.search(f.get("finding") or "") \
                    or (f.get("check") in ("unsupported", "absent")
                        and _paraphrases_event(f.get("claim_text") or "", events)):
                f["severity"] = "warning"
                f["finding"] = (f.get("finding") or "") + " [advisory: preflight passed this sentence]"
        adjusted.append(f)
    judge_f = adjusted
    seen = set()
    out = []
    for f in preflight_f + judge_f:
        key = (f.get("target"), (f.get("claim_text") or "")[:80], f.get("check"))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _write_verdict_field(db, assessment_id, scenario_idx, path: str, value: str) -> None:
    """Write one field of a scenario's synthesis (key_signals[j] or
    strategic_imperative) on forecast_scenario_verdicts."""
    from sqlalchemy import text as sa_text
    m = re.match(r"^(key_signals)\[(\d+)\]$", path)
    jpath = "{%s,%s}" % (m.group(1), m.group(2)) if m else "{%s}" % path
    db.facade._execute_with_rollback(sa_text(
        "UPDATE forecast_scenario_verdicts SET synthesis = jsonb_set("
        "CASE WHEN jsonb_typeof(synthesis)='string' THEN (synthesis #>> '{}')::jsonb ELSE synthesis END, "
        ":p, to_jsonb(CAST(:v AS text)), true) WHERE assessment_id=:a AND scenario_idx=:i"),
        {"p": jpath, "v": value, "a": assessment_id, "i": scenario_idx})


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
    prev_findings: List[dict] = []
    pending_revert = None
    rounds_run = 0
    for rnd in range(max_rounds + 1):
        items = await _load_items_for_period(cadence, period_label)
        synth = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or {}
        payload = synth.get("payload") or {}
        segments = _segments(items, payload)
        for s in segments:
            s["_period"] = period_label
        events_by_topic = _events_by_topic(cadence, period_label)
        ledger = _ledger(items, events_by_topic, _historical_events(cadence, period_label))
        # Tail-risk titles live in the EOS store, not on the assessment
        # summary; the letter names them and the gate needs them quoted.
        try:
            from app.services.wiley_delivery_service import _ensure_eos_for_bundle
            for t, sc in ((await _ensure_eos_for_bundle(items)) or {}).items():
                if t in ledger:
                    ledger[t]["tail_risks"] = [x.get("title") for x in (sc or []) if isinstance(x, dict) and x.get("title")]
        except Exception as e:
            logger.warning("narrative review: tail-risk titles unavailable: %s", e)
        n_scen = sum(len(v.get("scenarios") or []) for v in ledger.values())
        n_tail = sum(len(v.get("tail_risks") or []) for v in ledger.values())
        pre = preflight(segments, ledger, extra_numbers=[n_scen, n_tail, len(ledger)])
        try:
            pre += await geography_findings(segments, ledger)
        except Exception as e:
            logger.warning("narrative review: geography check failed: %s", e)
        jud = await judge(segments, ledger, organisation)
        findings = _merge(pre, jud, [e for lt in ledger.values() for e in (lt.get("events") or [])],
                          scen_all=[sc for lt in ledger.values() for sc in (lt.get("scenarios") or [])])
        # A repair that made a segment worse is undone: the previous text
        # comes back and its old findings stand (round 1 of the 16 Oct run
        # went from 13 errors to 24 before this guard).
        if pending_revert:
            before, errs_before = pending_revert
            pending_revert = None
            reverted = 0
            for t, seg in before.items():
                now_err = sum(1 for f in findings if f.get("target") == t and f.get("severity") == "error")
                if now_err > errs_before.get(t, 0):
                    try:
                        if seg["kind"] == "topic":
                            db.facade.patch_topic_summary_field(topic=seg["topic"], assessment_id=seg["assessment_id"],
                                                                path=seg["path"], value=seg["text"], edited_by="narrative-repair-revert", lock=False)
                        elif seg["kind"] == "verdict":
                            _write_verdict_field(db, seg["assessment_id"], seg["scenario_idx"], seg["path"], seg["text"])
                        else:
                            db.facade.patch_brief_field(cadence, period_label, path=seg["path"], value=seg["text"],
                                                        edited_by="narrative-repair-revert", lock=False)
                        reverted += 1
                        findings = [f for f in findings if f.get("target") != t] + [
                            f for f in prev_findings if f.get("target") == t]
                    except Exception as e:
                        logger.warning("narrative review: revert failed for %s: %s", t, e)
            if reverted:
                logger.info("narrative review: reverted %d segments the repair made worse", reverted)
        prev_findings = findings
        errors = [f for f in findings if f.get("severity") == "error"]
        history.append({"round": rnd, "errors": len(errors), "warnings": len(findings) - len(errors)})
        logger.info("narrative review round %d: %d errors, %d warnings", rnd, len(errors), len(findings) - len(errors))
        if not errors or not do_repair or rnd == max_rounds:
            break
        for s in segments:
            s["_cadence"] = cadence
        before = {s["target"]: s for s in segments}
        errs_before = {t: sum(1 for f in findings if f.get("target") == t and f.get("severity") == "error") for t in before}
        n = await _repair_with_cadence(db, cadence, period_label, segments, findings, ledger, organisation)
        rounds_run += 1
        if n == 0:
            break
        pending_revert = (before, errs_before)
        continue
    try:
        findings += await finish_displays(db, cadence, period_label, payload, ledger, organisation,
                                          extra_numbers=[n_scen, n_tail, len(ledger)])
    except Exception as e:
        logger.warning("narrative review: display sentences failed: %s", e)
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


async def finish_displays(db, cadence: str, period_label: str, payload: dict, ledger: Dict[str, dict],
                          organisation: dict, *, extra_numbers: List = (), passes: int = 3) -> List[dict]:
    """Write the display sentence of every long tension body, then check
    each one against the ledger (preflight) and against its own body (the
    judge, which sees the body and flags only what the display adds). A
    display with an error is rewritten with the finding as feedback; after
    ``passes`` it is dropped and the slide cuts the body at a clause
    boundary. Returns the dropped displays' findings as warnings."""
    from app.services.wiley_bundle_supervisor import _load_items_for_period, ensure_tension_displays
    problems: Dict[str, str] = {}
    advisory: List[dict] = []
    bad_segs: List[dict] = []
    for rnd in range(passes):
        items = await _load_items_for_period(cadence, period_label)
        n = await ensure_tension_displays(db, items, problems=problems)
        items = await _load_items_for_period(cadence, period_label)
        segs = [s for s in _segments(items, payload) if s["path"].endswith(".display")]
        if not segs:
            return advisory
        for s in segs:
            s["_period"] = period_label
        pre = preflight(segs, ledger, extra_numbers=extra_numbers)
        jud = await judge(segs, ledger, organisation)
        f = _merge(pre, jud, [e for lt in ledger.values() for e in (lt.get("events") or [])],
                   scen_all=[sc for lt in ledger.values() for sc in (lt.get("scenarios") or [])])
        errors = [x for x in f if x.get("severity") == "error"]
        bad_segs = [s for s in segs if any(x.get("target") == s["target"] for x in errors)]
        logger.info("narrative review: displays pass %d: %d written, %d with errors", rnd, n, len(bad_segs))
        if not bad_segs:
            return advisory
        problems = {}
        for s in bad_segs:
            msgs = [x.get("finding") or "" for x in errors if x.get("target") == s["target"]]
            problems[f"{s['topic']}|{s['tension_idx']}"] = " ".join(msgs)[:600]
        advisory = [dict(x, severity="warning", finding=(x.get("finding") or "") + " [display]") for x in errors]
    for s in bad_segs:
        db.facade.patch_topic_summary_field(topic=s["topic"], assessment_id=s["assessment_id"],
                                            path=s["path"], value="", edited_by="narrative-review", lock=False)
    logger.info("narrative review: %d display sentences dropped after %d passes", len(bad_segs), passes)
    return [dict(x, finding=x.get("finding", "") + " [dropped]") for x in advisory]


async def _shorten_segments(db, cadence, period_label, segments, findings) -> int:
    """Length findings go to the display agent: a shorter text of at most
    the cap, every name and figure from the original (display_ok), written
    back as the segment. The repair agent was asked twice and came back
    over the cap both times (eighth review, 16 Oct 2026)."""
    from app.services.wiley_bundle_supervisor import _call_agent, display_ok
    todo = {}
    for f in findings:
        if f.get("severity") != "error" or f.get("check") != "length":
            continue
        seg = next((s for s in segments if s["target"] == f.get("target")), None)
        if not seg:
            continue
        key = next((k for k in _LENGTH_CAPS if seg["path"].startswith(k)), None)
        if not key:
            continue
        max_sent, max_chars = _LENGTH_CAPS[key]
        todo[seg["target"]] = (seg, max_sent, max_chars)
    if not todo:
        return 0
    items = [{"id": t, "name": "", "body": seg["text"], "max_chars": max_chars - 20, "max_words": max(12, (max_chars - 20) // 7),
              "max_sentences": max_sent} for t, (seg, max_sent, max_chars) in todo.items()]
    n = 0
    for attempt in range(2):
        out = await _call_agent("wiley_display_agent", {"items": items})
        got = {x.get("id"): (x.get("display") or "").strip() for x in ((out or {}).get("items") or []) if isinstance(x, dict)}
        still = []
        for it in items:
            seg, max_sent, max_chars = todo[it["id"]]
            new = got.get(it["id"], "")
            if display_ok(new, seg["text"], cap=max_chars) and len(_length_findings(dict(seg, text=new))) == 0:
                try:
                    if seg["kind"] == "topic":
                        db.facade.patch_topic_summary_field(topic=seg["topic"], assessment_id=seg["assessment_id"],
                                                            path=seg["path"], value=new, edited_by="narrative-shorten", lock=False)
                    else:
                        db.facade.patch_brief_field(cadence, period_label, path=seg["path"], value=new,
                                                    edited_by="narrative-shorten", lock=False)
                    n += 1
                except Exception as e:
                    logger.warning("narrative shorten: write failed for %s: %s", seg["target"], e)
            else:
                still.append(dict(it, previous_attempt=new,
                                  problem=f"{len(new)} characters; at most {it['max_chars']} characters and "
                                          f"{it['max_sentences']} sentences, every name and figure from the body"))
        items = still
        if not items:
            break
    logger.info("narrative shorten: %d of %d over-length segments rewritten", n, len(todo))
    return n


async def _repair_with_cadence(db, cadence, period_label, segments, findings, ledger, organisation) -> int:
    from app.services.wiley_bundle_supervisor import _call_agent
    n_short = await _shorten_segments(db, cadence, period_label, segments, findings)
    shortened = {f.get("target") for f in findings if f.get("check") == "length" and f.get("severity") == "error"} if n_short else set()
    findings = [f for f in findings if not (f.get("target") in shortened and f.get("check") == "length")]
    flagged_targets = {f.get("target") for f in findings if f.get("severity") == "error"}
    flagged = [s for s in segments if s["target"] in flagged_targets]
    if not flagged:
        return n_short
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
        if seg["path"] == "exec_summary.letter":
            # The letter has its own gate (five sections, length, banned
            # severity words); a repair must not hand the bundle a letter
            # that gate will reject.
            from app.services.wiley_bundle_supervisor import _letter_defects, _quote_titles_with_banned_words
            titles = [sc.get("name") for lt in ledger.values() for sc in (lt.get("scenarios") or [])]
            titles += [t for lt in ledger.values() for t in (lt.get("tail_risks") or [])]
            new = _quote_titles_with_banned_words(new, titles)
            defects = _letter_defects(new)
            if defects:
                logger.info("narrative repair: letter repair rejected by the letter gate (%s)", "; ".join(defects))
                continue
        try:
            if seg["kind"] == "topic":
                db.facade.patch_topic_summary_field(topic=seg["topic"], assessment_id=seg["assessment_id"],
                                                    path=seg["path"], value=new, edited_by="narrative-repair", lock=False)
                if re.match(r"^topic_briefing\.tensions\[\d+\]\.body$", seg["path"]):
                    db.facade.patch_topic_summary_field(topic=seg["topic"], assessment_id=seg["assessment_id"],
                                                        path=seg["path"][:-4] + "display", value="",
                                                        edited_by="narrative-repair", lock=False)
            elif seg["kind"] == "verdict":
                _write_verdict_field(db, seg["assessment_id"], seg["scenario_idx"], seg["path"], new)
            else:
                db.facade.patch_brief_field(cadence, period_label, path=seg["path"], value=new,
                                            edited_by="narrative-repair", lock=False)
            n += 1
        except Exception as e:
            logger.warning("narrative repair: write failed for %s: %s", seg["target"], e)
    logger.info("narrative repair: rewrote %d of %d flagged segments", n, len(flagged))
    return n + n_short
