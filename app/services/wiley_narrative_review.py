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

def _ledger(items: list, events_by_topic: dict) -> Dict[str, dict]:
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
        for d, s0, s1 in located:
            window = sent[max(0, s0 - 90):min(len(sent), s1 + 25)]
            if _SPEECH.search(window):
                continue
            matches = [e for key, evs in by_date.items() if _date_matches(d, [key]) for e in evs]
            if not matches:
                continue
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


_TYPE_COUNT = re.compile(r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
                         r"sixteen|seventeen|eighteen|nineteen|twenty)\s+(?:(?:confirming|completed|signed|new|formal|"
                         r"separate|distinct|successful)\s+)*(agreements?|deals?|approvals?|submissions?|partnerships?|"
                         r"launches|releases?|acquisitions?|contracts?|filings?|retractions?|terminations?)\b", re.I)
_TYPE_STEMS = {"agreement": ("agree", "partner", "deal", "contract", "sign", "mou", "alliance"),
               "deal": ("agree", "partner", "deal", "contract", "sign", "acqui"),
               "approval": ("approv", "clear", "authoris", "authoriz", "granted"),
               "submission": ("submit", "fil", "applic"), "filing": ("fil", "submit", "applic"),
               "partnership": ("partner", "agree", "alliance", "collaborat", "deal"),
               "launch": ("launch", "open", "unveil"), "release": ("releas", "publish", "open"),
               "acquisition": ("acqui", "bought", "purchas", "takeover"), "contract": ("contract", "award", "agree"),
               "retraction": ("retract",), "termination": ("terminat", "cancel", "withh")}


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
            stems = _TYPE_STEMS[stem_key]
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


_PROGRESS = re.compile(r"\b(emerging|emerges|emerged|accelerat\w*|materialis\w*|materializ\w*|gaining|gains|taking hold|"
                       r"under ?way|is forming|are forming|routing around|substitut\w*|bearing out|confirm(?:ed|ing|s)|"
                       r"advancing|advances|strengthening|momentum|is building|are building|now fill|filling)\b", re.I)
_HEDGE = re.compile(r"\b(too early|no (?:\w+ )?events?|not yet|watch|would|could|may|might|if|hypothes\w*|"
                    r"remains? to be seen|no evidence|absent|unconfirmed|has not|have not|despite having no)\b", re.I)


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
        if not _PROGRESS.search(sent) or _HEDGE.search(sent):
            continue
        for sc in early:
            name = str(sc.get("name")).lower()
            shorts = [" ".join(name.split()[:k]) for k in (3, 2)]
            if name in low or any(len(s) > 10 and s in low for s in shorts):
                out.append({"target": seg["target"], "severity": "error", "check": "contradiction",
                            "finding": f"The sentence describes '{sc.get('name')}' as developing; its ledger has no judged events (Too early).",
                            "claim_text": sent, "source": "preflight",
                            "suggested_fix": "Present it as a watch item or a hypothesis, not as something observed this cycle."})
                break
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
            findings.extend(_silence_findings(seg, scen))
            findings.extend(_points_findings(seg, scen))
            findings.extend(_date_basis_findings(seg, evs))
            findings.extend(_type_count_findings(seg, scen))
            findings.extend(_progress_findings(seg, scen))
        elif seg.get("kind") == "verdict" and seg.get("topic") in ledger:
            scen = ledger[seg["topic"]].get("scenarios") or []
            findings.extend(_points_findings(seg, scen))
            findings.extend(_date_basis_findings(seg, ledger[seg["topic"]].get("events") or []))
            if "key_signals[" in seg.get("path", ""):
                findings.extend(_signal_findings(seg, scen, ledger[seg["topic"]].get("events") or []))
        else:
            findings.extend(_count_findings(seg, scen_all, per_topic=[lt.get("scenarios") or [] for lt in all_topics]))
            findings.extend(_points_findings(seg, scen_all))
            findings.extend(_date_basis_findings(seg, events_all))
            findings.extend(_type_count_findings(seg, scen_all))
            findings.extend(_progress_findings(seg, scen_all))
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
               "segments": [{"target": s["target"], "topic": s.get("topic"), "text": s["text"]} for s in segments]}
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
_PREFLIGHT_OWNED = {"date", "figure"}
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

def _merge(preflight_f: List[dict], judge_f: List[dict], events: Optional[list] = None) -> List[dict]:
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
            if points_owned or (f.get("check") in _PREFLIGHT_OWNED and key not in pre_keys) \
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
        ledger = _ledger(items, events_by_topic)
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
        jud = await judge(segments, ledger, organisation)
        findings = _merge(pre, jud, [e for lt in ledger.values() for e in (lt.get("events") or [])])
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
            elif seg["kind"] == "verdict":
                _write_verdict_field(db, seg["assessment_id"], seg["scenario_idx"], seg["path"], new)
            else:
                db.facade.patch_brief_field(cadence, period_label, path=seg["path"], value=new,
                                            edited_by="narrative-repair", lock=False)
            n += 1
        except Exception as e:
            logger.warning("narrative repair: write failed for %s: %s", seg["target"], e)
    logger.info("narrative repair: rewrote %d of %d flagged segments", n, len(flagged))
    return n
