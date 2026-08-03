"""Humanization pass for the Wiley report pipeline.

Wraps the ``humanize-mcp`` package (AunooAI's AI-tells detector + rewrite
prompt) and applies it to the LLM-generated prose in the bundle so the
deliverable doesn't read like AI slop. Threshold-gated: prose is only
rewritten when the detector finds more than ``HUMANIZE_TELL_THRESHOLD``
tells, and the rewrite is done with the tenant's existing model
(AIModelFactory) — no extra provider credentials.

Gated by ``WILEY_HUMANIZE`` (default on). Lock-aware callers must skip
locked fields before calling this.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Phrases that JUDGE the consensus/forecast as right or wrong — the framing
# the customer rejected. The exec-summary agent is told never to produce
# these, but LLMs slip, so we deterministically catch + rewrite them before
# the reviewer (and the customer) see the letter.
_VERDICT_RE = re.compile(
    r"\bconsensus\s+(?:was|is|were|on|proved|remained|appears|seems)\b"
    r"|\bconsensus\s+(?:was|is)\s+(?:high|low)\b"
    r"|\bconsensus\s+(?:has\s+)?(?:shifted|drifted|updated|moved)\b"
    r"|\b(?:was|were|is|proved|turned out)\s+(?:misplaced|vindicated|"
    r"correct|incorrect|right|wrong|accurate|inaccurate)\b"
    r"|\bexpectations?\s+(?:was|were|proved)\b"
    r"|\b(?:the\s+)?(?:crowd|forecast)\s+(?:was|were|proved)\s+"
    r"(?:right|wrong|correct|incorrect)\b",
    re.IGNORECASE,
)


def has_forecast_verdict(text: str) -> bool:
    return bool(text) and bool(_VERDICT_RE.search(text))


async def strip_forecast_verdicts(text: str) -> dict:
    """If the text judges the consensus/forecast as right/wrong (banned
    framing), rewrite it once to describe only what was expected and what the
    evidence shows. Returns {text, changed}. Never blocks — returns original
    on any failure."""
    out = {"text": text, "changed": False}
    if not text or not has_forecast_verdict(text):
        return out
    try:
        from app.ai_models import AIModelFactory
        sys = (
            "You edit a foresight brief. The text wrongly JUDGES forecasts/"
            "consensus as right, wrong, misplaced, correct, incorrect, high, "
            "or low, or describes consensus as shifting. Rewrite so it does "
            "NONE of that: state only what was expected at forecast time and "
            "what the named events since then show — never grade the "
            "expectation, never characterise 'consensus' beyond 'at forecast "
            "time, X was expected'. Preserve every fact, event, number, and "
            "the paragraph structure. Return ONLY the rewritten text."
        )
        model = AIModelFactory.get_model(_MODEL)
        rewritten = await model.agenerate_response(
            [{"role": "system", "content": sys},
             {"role": "user", "content": text}],
            temperature=0.2, max_tokens=4000,
        )
        rewritten = (rewritten or "").strip()
        if rewritten and not has_forecast_verdict(rewritten):
            out["text"] = rewritten
            out["changed"] = True
            logger.info("strip_forecast_verdicts: rewrote consensus-verdict prose")
        elif rewritten:
            # one more try kept the verdict — keep the rewrite anyway if it's
            # at least different, else original.
            out["text"] = rewritten
            out["changed"] = rewritten != text
            logger.warning("strip_forecast_verdicts: verdict phrasing may persist")
        return out
    except Exception as e:
        logger.warning("strip_forecast_verdicts failed: %s", e)
        return out


async def ground_check_exec_summary(text: str, named_events: list) -> dict:
    """Revise the exec-summary letter so every *specific* real-world event it
    cites is supported by the quarter's ``named_events``. Unsupported specifics
    (a named agency action, a dated policy event) are removed or softened to the
    general theme; supported claims and all other prose are kept verbatim.

    Returns ``{text, changed}``. Never blocks. Only runs when there ARE
    named_events to check against — otherwise we'd risk gutting a letter just
    because extraction produced no events that period.
    """
    out = {"text": text, "changed": False}
    events = named_events or []
    if not text or not text.strip() or not humanize_enabled() or not events:
        return out
    try:
        from app.ai_models import AIModelFactory
        lines = []
        for e in events[:60]:
            if not isinstance(e, dict):
                continue
            actor = (e.get("actor") or e.get("actor_normalized") or "").strip()
            action = (e.get("action") or "").strip()
            subject = (e.get("subject") or e.get("subject_normalized") or "").strip()
            date = (e.get("event_date") or "").strip()
            line = " ".join(p for p in [actor, action, subject] if p).strip()
            if date:
                line += f" ({date})"
            if line:
                lines.append("- " + line)
        grounded = "\n".join(lines)
        if not grounded:
            return out
        sys = (
            "You are a fact-grounding editor for a foresight brief. You are given "
            "GROUNDED EVENTS (the only verified real-world events for this period) "
            "and a LETTER. Some sentences may assert specific real-world events, "
            "agency/government actions, named policies, or dated developments that "
            "are NOT in GROUNDED EVENTS. For each such UNSUPPORTED specific claim, "
            "remove it or rephrase to the general theme without the unverifiable "
            "specifics. Keep every supported claim, and keep all other prose, "
            "paragraph structure, bold headers, and tone EXACTLY. Do not add new "
            "events. Return ONLY the revised letter."
        )
        usr = f"GROUNDED EVENTS:\n{grounded}\n\nLETTER:\n{text}"
        model = AIModelFactory.get_model(_MODEL)
        rewritten = await model.agenerate_response(
            [{"role": "system", "content": sys}, {"role": "user", "content": usr}],
            temperature=0.2, max_tokens=4000,
        )
        rewritten = (rewritten or "").strip()
        # Guard against the model gutting the letter — only accept a revision
        # that keeps at least half the original length.
        if rewritten and rewritten != text and len(rewritten) >= 0.5 * len(text):
            out["text"] = rewritten
            out["changed"] = True
            logger.info("ground_check_exec_summary: revised ungrounded event claim(s)")
        return out
    except Exception as e:
        logger.warning("ground_check_exec_summary failed: %s", e)
        return out


# A quantity worth checking: "14.5%", "1.4 million", "$300 billion", "one in
# forty". Deliberately no trailing \b — after "%" the next character is usually
# a space, and \b would never match there.
#
# ``lakh`` (100,000), ``L`` after a number, and ``crore`` (10,000,000) are here
# because Indian-English outlets are in the corpus and their units are the
# easiest to misread. A source headline reading "1.4L phantom citations" became
# "1.4 million" in a customer report — a tenfold overstatement that the report
# then contradicted itself on two paragraphs later.
_FIGURE_RE = re.compile(
    r"\$?\d[\d,]*(?:\.\d+)?\s*(?:%|percent|million|billion|trillion|lakh|crore)"
    # Headline abbreviations: "$14bn", "£162m", "3k". Without these a prose
    # claim of "$14 billion" looked unsourced against a source headline
    # writing "$14bn" — the exact false positive the first live lint run hit.
    r"|\$?\d[\d,]*(?:\.\d+)?\s*(?:bn|mn|tn|[mk])\b"
    r"|\$?\d[\d,]*(?:\.\d+)?L\b"
    # A comma-grouped bare number ("140,000"). Catches the same claim written
    # out in full instead of with a scale word. Years have no comma, so this
    # doesn't fire on every date.
    r"|\$?\d{1,3}(?:,\d{3})+\b"
    r"|\bone in (?:ten|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|\d+)\b",
    re.IGNORECASE,
)

# Multipliers used to compare a figure against the same quantity written in a
# different unit. A plain "%"-style unit has no multiplier and is compared as
# written, so "1.43%" still cannot satisfy "1.4 million".
_UNIT_SCALE = {
    "lakh": 100_000, "l": 100_000, "crore": 10_000_000,
    "million": 1_000_000, "billion": 1_000_000_000, "trillion": 1_000_000_000_000,
    "k": 1_000, "m": 1_000_000, "mn": 1_000_000,
    "bn": 1_000_000_000, "tn": 1_000_000_000_000,
}


def _figure_key(fig: str) -> str:
    """Normalised figure for exact comparison.

    Compares the number AND its unit, so "1.43%" cannot satisfy a claim of
    "1.4 million" and "300 grants" cannot satisfy "$300 billion". Substring
    matching on the digits alone is what let four invented statistics through
    on 2026-08-03.

    Scale units resolve to an absolute count, so "1.4 lakh" and "140,000" are
    the same key while "1.4 lakh" and "1.4 million" are not.
    """
    f = fig.lower().replace("$", "").replace(",", "").strip()
    f = re.sub(r"\s+", " ", f)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([a-z]+)", f)
    if m and m.group(2) in _UNIT_SCALE:
        return f"{float(m.group(1)) * _UNIT_SCALE[m.group(2)]:.0f}"
    return f.replace(" percent", "%").replace("percent", "%")


def _figure_ledger(sources: list) -> dict:
    """Map every figure found in ``sources`` to the sentence it came from."""
    ledger: dict = {}
    for src in sources or []:
        text = src if isinstance(src, str) else str(src)
        text = re.sub(r"\s+", " ", text)
        for m in _FIGURE_RE.finditer(text):
            key = _figure_key(m.group(0))
            if key in ledger:
                continue
            start = max(0, m.start() - 180)
            ledger[key] = text[start:m.end() + 140].strip()
    return ledger


async def ground_check_figures(text: str, sources: list, *,
                               check_subjects: bool = False) -> dict:
    """Revise the letter so every statistic it asserts is one the sources
    actually contain, used for the thing the source used it for.

    ``ground_check_exec_summary`` checks events — actor, action, subject, date.
    A statistic is not an event, so numbers were never checked at all. On
    2026-08-03 a Q3 executive summary asserted "a 14.5% drop in manuscript
    submissions — the single largest quarterly move in the portfolio". The
    number was real and came from a May assessment, where it meant federal R&D
    funding running "14.5% below baseline expectations". Three more figures in
    the same letter appeared in no source at all.

    Two passes: unsupported figures are identified deterministically (exact
    number + unit), then the model is told to delete those claims and to
    correct any figure whose subject disagrees with its source sentence.

    Returns ``{text, changed, unsupported}``. Never blocks.
    """
    out = {"text": text, "changed": False, "unsupported": []}
    if not text or not text.strip() or not humanize_enabled():
        return out
    ledger = _figure_ledger(sources)
    used = {_figure_key(m.group(0)): m.group(0) for m in _FIGURE_RE.finditer(text)}
    if not used:
        return out

    unsupported = [orig for key, orig in used.items() if key not in ledger]
    supported = {key: ledger[key] for key in used if key in ledger}
    out["unsupported"] = unsupported
    # ``check_subjects=False`` (the default) skips the model when nothing is
    # orphaned. For a stage that COPIES figures out of its own payload, the
    # "source sentence" is the output's own sentence and the comparison is
    # circular — it can only churn well-grounded prose.
    #
    # Set it True for a stage that DERIVES prose from different source text,
    # where drift is real and detectable: the cross-topic overview turned an
    # assessment's "14.5% drop below baseline expectations" into "a 14.5% drop
    # in manuscript submissions", and every stage downstream repeated it.
    if not unsupported and not check_subjects:
        return out

    try:
        from app.ai_models import AIModelFactory

        lines = [f'- {orig} — source says: "{supported[_figure_key(orig)]}"'
                 for orig in used.values() if _figure_key(orig) in supported]
        sys_prompt = (
            "You are a fact-grounding editor for a foresight brief. You are given "
            "a LETTER, a list of SOURCED FIGURES with the sentence each one came "
            "from, and a list of UNSOURCED FIGURES.\n"
            "1. Delete every claim built on an UNSOURCED FIGURE, or rewrite the "
            "sentence to make the same point without any number.\n"
            "2. For each SOURCED FIGURE, check the letter uses it for the SAME "
            "subject as its source sentence. If it does not, correct the letter "
            "to the source's subject. A figure about one thing must not be "
            "restated as being about another.\n"
            "3. Delete superlatives the sources do not support (\"the largest\", "
            "\"unprecedented\", \"the first\") unless the source says so.\n"
            "Keep every other sentence, the paragraph structure, the bold "
            "section headers and the tone EXACTLY. Never introduce a new number. "
            "Return ONLY the revised letter."
        )
        usr = (
            f"SOURCED FIGURES:\n" + ("\n".join(lines) or "(none)") +
            f"\n\nUNSOURCED FIGURES:\n" + ("\n".join("- " + u for u in unsupported) or "(none)") +
            f"\n\nLETTER:\n{text}"
        )
        model = AIModelFactory.get_model(_MODEL)
        rewritten = await model.agenerate_response(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": usr}],
            temperature=0.2, max_tokens=4000,
        )
        rewritten = (rewritten or "").strip()
        # Same guard as the event check: never accept a revision that gutted
        # the letter.
        if rewritten and rewritten != text and len(rewritten) >= 0.5 * len(text):
            out["text"] = rewritten
            out["changed"] = True
            still = [o for k, o in
                     {_figure_key(m.group(0)): m.group(0)
                      for m in _FIGURE_RE.finditer(rewritten)}.items()
                     if k not in ledger]
            logger.info("ground_check_figures: %d unsourced figure(s) in, %d out",
                        len(unsupported), len(still))
        elif unsupported:
            logger.warning("ground_check_figures: %d unsourced figure(s) left in place "
                           "(%s) — revision rejected", len(unsupported), ", ".join(unsupported))
        return out
    except Exception as e:
        logger.warning("ground_check_figures failed: %s", e)
        return out


# Words that start a sentence or head a section and would otherwise look like
# an organisation name. Not exhaustive — the check only reports names it
# cannot find in the sources, so a miss here costs a spurious log line, not a
# wrong edit.
_ORG_STOPWORDS = {
    "the", "this", "that", "these", "those", "a", "an", "and", "but", "for",
    "our", "your", "their", "we", "it", "in", "on", "at", "by", "as", "if",
    "when", "where", "while", "with", "without", "from", "to", "of", "no",
    "not", "both", "each", "every", "all", "some", "most", "more", "less",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "q1", "q2", "q3", "q4", "h1", "h2", "h3",
    # Technology acronyms the prose uses adjectivally — never org names.
    "ai", "llm", "llms", "genai", "ml",
}

# Countries / nationalities / regions. A sentence naming "China" or
# "Western institutions" is geography, not an organisation the source list
# must contain. Measured on the first live lint run: 10 of 18 org findings
# were words from this class.
_GEO_WORDS = {
    "china", "chinese", "india", "indian", "japan", "japanese", "korea",
    "korean", "germany", "german", "france", "french", "russia", "russian",
    "britain", "british", "america", "american", "americas", "europe",
    "european", "asia", "asian", "africa", "african", "australia",
    "australian", "canada", "canadian", "zealand", "netherlands", "dutch",
    "switzerland", "swiss", "brazil", "brazilian", "mexico", "mexican",
    "western", "eastern", "northern", "southern", "global", "international",
    "pacific", "atlantic", "nordic", "latin", "u.s", "us", "uk", "eu", "new",
}

# "AI-driven", "U.S.-origin" — an uppercase token hyphenated onto a
# lowercase tail is a compound adjective, not a name.
_HYPHEN_ADJ_RE = re.compile(r"[A-Z.]+-[a-z]")

# A run of capitalised words, joined only by "&" or "of". Nothing else
# bridges: "Springer Nature, Hindawi and Taylor & Francis" must yield three
# names. An earlier version let "and" join, produced "Hindawi and Taylor",
# matched that against "Taylor" in the sources, and passed the one name that
# was actually invented.
_ORG_RE = re.compile(
    r"\b[A-Z][A-Za-z.\-']*(?:\s+(?:&|of)\s+[A-Z][A-Za-z.\-']*"
    r"|\s+[A-Z][A-Za-z.\-']*)*\b"
)

# Single-word names are kept — "Hindawi" is exactly the case that matters —
# except where the word merely opens a sentence, which is why the sentence
# splitter below drops the first token of each sentence when it stands alone.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _org_candidates(text: str) -> dict:
    """Capitalised names in ``text``, keyed lowercase → as written.

    Keeps single-word names, which is the whole point: an invented
    organisation usually arrives as one word inside a list of real ones.
    """
    out: dict = {}
    for sentence in _SENTENCE_SPLIT_RE.split(text or ""):
        sentence = sentence.strip()
        if not sentence:
            continue
        for m in _ORG_RE.finditer(sentence):
            name = m.group(0).strip(" .")
            # "NIH's" / "IQM's" — the possessive broke the substring match
            # against sources that name the org without it.
            name = re.sub(r"[’']s\b", "", name)
            if _HYPHEN_ADJ_RE.search(name):
                continue
            words = name.split()
            if not words:
                continue
            skip = _ORG_STOPWORDS | _GEO_WORDS
            if all(w.lower().strip(".") in skip for w in words):
                continue
            # A single capitalised word that opens the sentence is far more
            # likely a sentence opener than a name.
            if len(words) == 1 and m.start() == 0:
                continue
            if len(words) == 1 and (len(name) < 4
                                    or name.lower().strip(".") in skip):
                continue
            if words[0].lower() in _ORG_STOPWORDS and len(words) > 1:
                words = words[1:]
            # Strip trailing acronym/stopword too: "Transparent AI
            # contribution statements" yields the candidate "Transparent AI",
            # which is an adjective + the AI acronym, not an organisation.
            while words and words[-1].lower().strip(".") in skip:
                words = words[:-1]
            name = " ".join(words)
            if not words or all(w.lower().strip(".") in skip for w in words):
                continue
            if len(words) == 1 and (m.start() == 0 or len(name) < 4
                                    or name.lower().strip(".") in skip):
                continue
            out.setdefault(name.lower(), name)
    return out


async def ground_check_entities(text: str, sources: list) -> dict:
    """Remove named organisations the sources never mention.

    The figure check compares numbers; a name is not a number, so an
    organisation the model supplied from its own knowledge passed straight
    through. On 2026-08-03 an executive summary named Hindawi among publishers
    facing mounting retractions. Hindawi appeared in no source behind the
    report, and it is this customer's own retired imprint — the single worst
    name to attribute to a third party in front of them.

    Deterministic detection, model-driven removal, same shape as
    :func:`ground_check_figures`. Returns ``{text, changed, unsupported}``.
    Never blocks.
    """
    out = {"text": text, "changed": False, "unsupported": []}
    if not text or not text.strip() or not humanize_enabled():
        return out
    haystack = " ".join(
        (s if isinstance(s, str) else str(s)) for s in (sources or [])
    ).lower()
    if not haystack:
        return out

    candidates = _org_candidates(text)
    # A name counts as sourced if the whole name appears, or if a distinctive
    # single word of it does — "Springer Nature" is sourced by "Springer".
    unsupported = []
    for key, name in candidates.items():
        if key in haystack:
            continue
        words = [w for w in re.split(r"[^A-Za-z]+", name)
                 if len(w) > 3 and w.lower() not in _ORG_STOPWORDS]
        if any(w.lower() in haystack for w in words):
            continue
        unsupported.append(name)
    out["unsupported"] = unsupported
    if not unsupported:
        return out

    try:
        from app.ai_models import AIModelFactory
        sys_prompt = (
            "You are a fact-grounding editor for a foresight brief. The LETTER "
            "names organisations that appear in NONE of the sources behind the "
            "report.\n"
            "For each UNSOURCED NAME: if it is a real organisation being "
            "asserted as an example, delete the name. Keep the sentence and its "
            "point, either by dropping the name from a list or by rewriting the "
            "claim without naming anyone. If removing it leaves a list of one, "
            "rewrite the sentence so it reads naturally.\n"
            "Do not add any replacement name. Do not touch any other sentence, "
            "the paragraph structure, the bold section headers or the tone. "
            "Return ONLY the revised letter."
        )
        usr = ("UNSOURCED NAMES:\n" + "\n".join("- " + u for u in unsupported)
               + f"\n\nLETTER:\n{text}")
        model = AIModelFactory.get_model(_MODEL)
        rewritten = (await model.agenerate_response(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": usr}],
            temperature=0.2, max_tokens=4000,
        ) or "").strip()
        if rewritten and rewritten != text and len(rewritten) >= 0.5 * len(text):
            out["text"] = rewritten
            out["changed"] = True
            still = [n for n in _org_candidates(rewritten)
                     if n in {u.lower() for u in unsupported}]
            logger.info("ground_check_entities: %d unsourced name(s) in, %d out",
                        len(unsupported), len(still))
        else:
            logger.warning("ground_check_entities: %d unsourced name(s) left in "
                           "place (%s) — revision rejected",
                           len(unsupported), ", ".join(unsupported))
        return out
    except Exception as e:
        logger.warning("ground_check_entities failed: %s", e)
        return out


# Above this many detected tells, rewrite. A few tells are normal in any
# prose; the rewrite is for genuinely slop-heavy passages.
_THRESHOLD = int(os.getenv("HUMANIZE_TELL_THRESHOLD", "3"))
_MODEL = os.getenv("HUMANIZE_MODEL", "gpt-5.4")


def humanize_enabled() -> bool:
    return os.getenv("WILEY_HUMANIZE", "true").strip().lower() not in {"0", "false", "no", "off"}


def count_tells(text: str) -> int:
    """Number of AI-tells the humanize-mcp detector finds (0 on any error)."""
    if not text or not text.strip():
        return 0
    try:
        from humanize_mcp.detection import detect_ai_tells
        return len(detect_ai_tells(text))
    except Exception as e:
        logger.warning("humanize: detector unavailable: %s", e)
        return 0


async def humanize_text(text: str, *, formality: str = "formal",
                        paragraph_style: str = "preserve",
                        tone: str = "neutral",
                        threshold: Optional[int] = None) -> dict:
    """Rewrite ``text`` to strip AI tells IF it's above threshold.

    ``threshold`` overrides ``HUMANIZE_TELL_THRESHOLD`` for this call. Customer
    -facing slide prose is short — two or three sentences — so the default of
    3 lets a passage through that would read as slop at that length.

    Returns ``{text, changed, tells_before, tells_after}``. On any failure
    returns the original text unchanged (never blocks report generation).
    """
    result = {"text": text, "changed": False, "tells_before": 0, "tells_after": 0}
    if not humanize_enabled() or not text or not text.strip():
        return result
    try:
        from humanize_mcp.detection import detect_ai_tells
        from humanize_mcp.prompts import SYSTEM_PROMPT, build_user_prompt
        from app.ai_models import AIModelFactory

        limit = _THRESHOLD if threshold is None else threshold
        before = detect_ai_tells(text)
        result["tells_before"] = len(before)
        if len(before) <= limit:
            return result  # clean enough; don't spend a model call

        user_prompt = build_user_prompt(
            text, tone=tone, formality=formality, paragraph_style=paragraph_style,
            length_mode="preserve",
        )
        model = AIModelFactory.get_model(_MODEL)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        rewritten = await model.agenerate_response(messages, temperature=0.4, max_tokens=4000)
        rewritten = (rewritten or "").strip()
        if not rewritten:
            return result

        result["text"] = rewritten
        result["changed"] = True
        result["tells_after"] = len(detect_ai_tells(rewritten))
        logger.info("humanize: %d → %d tells", result["tells_before"], result["tells_after"])
        return result
    except Exception as e:
        logger.warning("humanize: rewrite failed, leaving text as-is: %s", e)
        return result


async def humanize_bundle_payload(payload: dict, *, locked_keys: list = None) -> dict:
    """Humanize the prose fields of a bundle synthesis payload in place,
    skipping any dot-path in ``locked_keys``. Returns a summary
    ``{field: {tells_before, tells_after, changed}}`` for logging/audit.

    Fields humanized: exec_summary.letter, strategic_overview,
    expert_commentary, cross_cutting_themes[*].body,
    executive_decision_framework[*].body.
    """
    locked = set(locked_keys or [])
    summary: dict = {}
    if not humanize_enabled() or not isinstance(payload, dict):
        return summary

    async def _do(path, getter, setter):
        if path in locked:
            return
        cur = getter()
        if not isinstance(cur, str) or not cur.strip():
            return
        r = await humanize_text(cur)
        if r["changed"]:
            setter(r["text"])
        summary[path] = {"before": r["tells_before"], "after": r["tells_after"],
                         "changed": r["changed"]}

    es = payload.get("exec_summary")
    if isinstance(es, dict) and es.get("letter"):
        await _do("exec_summary.letter",
                  lambda: es.get("letter"),
                  lambda v: es.__setitem__("letter", v))

    if payload.get("strategic_overview"):
        await _do("strategic_overview",
                  lambda: payload.get("strategic_overview"),
                  lambda v: payload.__setitem__("strategic_overview", v))

    if payload.get("expert_commentary"):
        await _do("expert_commentary",
                  lambda: payload.get("expert_commentary"),
                  lambda v: payload.__setitem__("expert_commentary", v))

    for i, theme in enumerate(payload.get("cross_cutting_themes") or []):
        if isinstance(theme, dict) and theme.get("body"):
            await _do(f"cross_cutting_themes[{i}].body",
                      lambda t=theme: t.get("body"),
                      lambda v, t=theme: t.__setitem__("body", v))

    for i, item in enumerate(payload.get("executive_decision_framework") or []):
        if isinstance(item, dict) and item.get("body"):
            await _do(f"executive_decision_framework[{i}].body",
                      lambda it=item: it.get("body"),
                      lambda v, it=item: it.__setitem__("body", v))

    return summary
