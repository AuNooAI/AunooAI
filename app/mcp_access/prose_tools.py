"""MCP tool that checks a draft for AI-writing tells.

``check_ai_tells`` runs the heuristic detector from ``humanize_mcp`` (regex
only, no model call) over text the assistant has written and returns every
flagged span with the detector that fired and a concrete fix. The point is
that asking a model to "write less like an AI" rarely works, while handing
it a named list of offending spans does: the model edits those spans and
checks again. The recipes in ``recipes.py`` tell the assistant to call this
before it returns a briefing.

Deterministic and cheap: milliseconds on a 60k-character draft. Never raises
on detector trouble; a missing package is returned as an ``error`` field so
the assistant can carry on without the check.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Awaitable, Callable

from .errors import ToolError
from .tools import ToolSpec

MAX_TEXT_CHARS = 60_000
MAX_TELLS_RETURNED = 200

# Tells per 1,000 words. The deep-research humanizer's practical floor is
# about two per thousand after a rewrite pass; a fresh draft from a frontier
# model lands anywhere from three to ten.
_CLEAN_PER_1000 = 1.0
_ACCEPTABLE_PER_1000 = 3.0


def _verdict(count: int, words: int) -> tuple[str, float]:
    density = round(count * 1000.0 / words, 2) if words else 0.0
    if count == 0:
        return "clean", density
    if density <= _CLEAN_PER_1000:
        return "clean", density
    if density <= _ACCEPTABLE_PER_1000:
        return "acceptable", density
    return "rewrite", density


def _detect(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from humanize_mcp.detection import compute_readability, detect_ai_tells
    return detect_ai_tells(text), compute_readability(text)


async def check_ai_tells(ctx=None, text: str | None = None) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ToolError("text is required: the draft to check")
    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS]
    try:
        tells, readability = _detect(text)
    except ImportError:
        return {"error": "the AI-tells detector is not installed on this site"}

    by_type = Counter(t.get("tell_type") or "unknown" for t in tells)
    words = int(readability.get("word_count") or 0)
    verdict, density = _verdict(len(tells), words)

    spans = [
        {
            "type": t.get("tell_type"),
            "label": t.get("label"),
            "text": t.get("text"),
            "start": t.get("start"),
            "end": t.get("end"),
            "fix": t.get("suggestion"),
        }
        for t in sorted(tells, key=lambda t: (t.get("start") or 0, t.get("end") or 0))
    ]
    out: dict[str, Any] = {
        "verdict": verdict,
        "tell_count": len(tells),
        "tells_per_1000_words": density,
        "by_type": dict(by_type.most_common()),
        "tells": spans[:MAX_TELLS_RETURNED],
        "readability": readability,
        "next_step": (
            "No action needed."
            if verdict == "clean"
            else "Edit each flagged span using its fix, then call check_ai_tells again on the revised draft. "
                 "Do not restyle the whole text; only the spans listed need to change."
        ),
    }
    if len(spans) > MAX_TELLS_RETURNED:
        out["tells_omitted"] = len(spans) - MAX_TELLS_RETURNED
    if truncated:
        out["truncated_to_chars"] = MAX_TEXT_CHARS
    return out


SPECS: dict[str, ToolSpec] = {
    "check_ai_tells": ToolSpec(
        name="check_ai_tells",
        description=(
            "Check a draft you have written for AI-writing tells before you return it. A regex detector (no "
            "model call) flags every span that reads as machine prose: inflated vocabulary such as 'landscape' "
            "or 'underscore', rule-of-three lists, 'not X but Y' parallelism, vague openers, tailing "
            "significance clauses, summary flourishes, weasel phrases, em-dash and bold overuse. Each flagged "
            "span comes with the fix to apply. Returns a verdict (clean, acceptable, rewrite), the count per "
            "detector, the spans with offsets, and readability figures. Call it on any briefing, report or "
            "summary longer than a paragraph, edit only the flagged spans, and call it again."
        ),
        properties={
            "text": {"type": "string", "description": "The draft to check, up to 60,000 characters."},
        },
        required=("text",),
        timeout=15.0,
    ),
}

HANDLERS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "check_ai_tells": check_ai_tells,
}
