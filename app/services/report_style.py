"""Shared clinical-register rules for customer-facing LLM prose.

Customers judge for themselves what counts as a crisis; the platform reports
what was published and how much of it there was. Append CLINICAL_STYLE to any
prompt that writes narrative a customer will read (timeline rollups and state
docs, signal/observer reports, digest leads). CLINICAL_STYLE_SHORT is the
same policy compressed for small prompts where token budget matters.

The prompt rule alone doesn't hold at 100%: tested against adversarial input
across the exec-summary, signal-report, and briefing-desk generators
(2026-08-24), a temperature-0.3 writer still reached for a banned word on
roughly 1 generation in 3-4 despite carrying CLINICAL_STYLE. Callers with a
retry loop already in place (e.g. a report that's rejected and regenerated on
structural defects) should also check ``has_severity_language`` and retry on
a hit, the same way they already retry on an empty or too-short draft.
"""

import re

_SEVERITY_WORDS = re.compile(
    r"\b(crisis|crises|severe|severely|aggressive|aggressively|alarming|"
    r"alarmingly|catastrophic|catastrophically|collapse|collapsing|"
    r"compromised)\b", re.IGNORECASE)


def find_severity_language(text: str) -> list:
    """Banned severity/threat words used in the writer's own voice, lowercased
    and deduplicated. A double-quoted span is exempt — the rule allows these
    words inside an attributed quote ('articles called it a "crisis"')."""
    unquoted = re.sub(r'"[^"]*"', "", text or "")
    return sorted({m.group(0).lower() for m in _SEVERITY_WORDS.finditer(unquoted)})


def has_severity_language(text: str) -> bool:
    return bool(find_severity_language(text))

CLINICAL_STYLE = (
    "\n\nTONE RULES (mandatory):\n"
    "- Attribute every criticism or praise to its source: \"articles alleged\", "
    "\"posts on social media said\", \"the lawsuit claims\". Never assert a "
    "verdict on the company in your own voice.\n"
    "- Quantify instead of characterize: counts, deltas, percentages "
    "(\"coverage rose from 14 to 114 articles\"). Do not write \"crisis\", "
    "\"severe\", \"aggressive\", \"alarming\", \"catastrophic\", \"spiked "
    "dramatically\", or similar severity language in your own voice; such "
    "words are allowed only inside attributed quotes (articles described the "
    "retractions as a \"crisis\").\n"
    "- Severity, significance, and threat labels in the input are "
    "machine-assigned sort keys, not judgments; report the underlying facts "
    "and counts, and do not translate the labels into alarm language. If a "
    "label appears without underlying facts, say a flag fired and details "
    "are unavailable — do not infer how serious it is from the label.\n"
    "- State open questions as questions, not warnings.\n"
    "- If the input contains a CUSTOMER-DEFINED STATUS line, state that status "
    "using its exact label and cite the numbers that triggered it. Never "
    "upgrade, downgrade, or invent a status that is not in the input."
)

CLINICAL_STYLE_SHORT = (
    " Attribute criticism to its source (\"articles alleged\", \"posts "
    "said\") rather than asserting it yourself, and quantify with counts "
    "instead of severity words like \"crisis\" or \"severe\" unless quoting "
    "a source. If the facts include a customer-defined status, state it "
    "using its exact label with the numbers that triggered it; never invent "
    "or change one."
)
