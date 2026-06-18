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
                        tone: str = "neutral") -> dict:
    """Rewrite ``text`` to strip AI tells IF it's above threshold.

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

        before = detect_ai_tells(text)
        result["tells_before"] = len(before)
        if len(before) <= _THRESHOLD:
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
