"""Shared clinical-register rules for customer-facing LLM prose.

Customers judge for themselves what counts as a crisis; the platform reports
what was published and how much of it there was. Append CLINICAL_STYLE to any
prompt that writes narrative a customer will read (timeline rollups and state
docs, signal/observer reports, digest leads). CLINICAL_STYLE_SHORT is the
same policy compressed for small prompts where token budget matters.
"""

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
    "- State open questions as questions, not warnings."
)

CLINICAL_STYLE_SHORT = (
    " Attribute criticism to its source (\"articles alleged\", \"posts "
    "said\") rather than asserting it yourself, and quantify with counts "
    "instead of severity words like \"crisis\" or \"severe\" unless quoting "
    "a source."
)
