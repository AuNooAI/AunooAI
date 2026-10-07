"""The fixed output block of the article analysis prompts.

docs/pipelines/08_INGEST_FIX_SPEC.md, WP3b and WP6c. There are two analysis
prompts, one per mode:

- ``content_analysis`` (manual research, bulk research, the model bias arena):
  every field, including Political Bias and Factuality.
- ``content_analysis_auto`` (automated ingest): the same minus Political Bias,
  Factuality and their explanations, which ingest never stored. Stored outlet
  factuality comes from Media Bias/Fact Check instead.

Each prompt is free text up to the line ``REQUIRED OUTPUT FORMAT:`` and a
fixed block after it, built here. The parser in article_analyzer reads the
labels this block asks for, so the block is not editable: PromptManager
refuses to save, restore or import a version of these prompts whose block
differs from ``output_block(prompt_type)``. Changing the block is a schema
change: edit the field lists here, bump ``SCHEMA_VERSION`` and run
``scripts/migrate_analysis_prompt_schema.py`` on each site.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

SCHEMA_VERSION = "2026-10-07.1"

SEPARATOR = "REQUIRED OUTPUT FORMAT:"

MANUAL = "content_analysis"
AUTO = "content_analysis_auto"
SCHEMA_PROMPT_TYPES = (MANUAL, AUTO)

#: Fields the manual prompt asks for, in order.
MANUAL_FIELDS: List[str] = [
    "Title", "Summary", "Category",
    "Future Signal", "Future Signal Explanation",
    "Sentiment", "Sentiment Explanation",
    "Time to Impact", "Time to Impact Explanation",
    "Driver Type", "Driver Type Explanation",
    "Political Bias", "Political Bias Explanation",
    "Factuality", "Factuality Explanation",
    "Tags",
]

#: Fields auto-ingest never stored, so its prompt does not ask for them.
AUTO_OMITTED = ("Political Bias", "Political Bias Explanation", "Factuality", "Factuality Explanation")
AUTO_FIELDS: List[str] = [f for f in MANUAL_FIELDS if f not in AUTO_OMITTED]

_PLACEHOLDERS: Dict[str, str] = {
    "Title": "<title>",
    "Summary": "<summary>",
    "Category": "<one of the categories listed above>",
    "Future Signal": "<one of the future signals listed above>",
    "Sentiment": "<one of the sentiment values listed above>",
    "Time to Impact": "<one of the time to impact values listed above>",
    "Driver Type": "<one of the driver types listed above>",
    "Political Bias": "<one of the political bias values listed above>",
    "Factuality": "<one of the factuality values listed above>",
    "Tags": "first tag, second tag, third tag",
}

_RULES = (
    "Reply with exactly the lines below, in this order, one field per line.\n"
    "Copy each label character-for-character, followed by a colon and a space.\n"
    "Do not number the lines. Do not add markdown - no asterisks, hashes, or bold.\n"
    "Do not rename, merge, reorder, add, or omit any line.\n"
    "Write every value in English, whatever language the article is written in."
)


def fields_for(prompt_type: str) -> List[str]:
    return AUTO_FIELDS if prompt_type == AUTO else MANUAL_FIELDS


def output_block(prompt_type: str) -> str:
    """The fixed block, starting with the separator line."""
    lines = [f"{f}: {_PLACEHOLDERS.get(f, '<one or two sentences>')}" for f in fields_for(prompt_type)]
    return SEPARATOR + "\n" + _RULES + "\n\n" + "\n".join(lines)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("—", "-").replace("–", "-")).strip()


def split(user_prompt: str) -> "tuple[str, Optional[str]]":
    """``(instructions, block)``; block is None when the separator is absent."""
    if SEPARATOR not in (user_prompt or ""):
        return user_prompt or "", None
    head, tail = user_prompt.split(SEPARATOR, 1)
    return head.rstrip(), SEPARATOR + tail


def schema_problem(prompt_type: str, user_prompt: str) -> Optional[str]:
    """Why this user prompt breaks the fixed block, or None when it is
    intact. Whitespace and dash style are ignored; anything else in the
    block, including a block that keeps the heading but changes a field,
    is a problem."""
    if prompt_type not in SCHEMA_PROMPT_TYPES:
        return None
    if (user_prompt or "").count(SEPARATOR) != 1:
        return (f"the prompt must contain the line '{SEPARATOR}' exactly once, "
                f"followed by the fixed output block")
    _instructions, block = split(user_prompt)
    if _norm(block) != _norm(output_block(prompt_type)):
        return ("the fixed output block after "
                f"'{SEPARATOR}' was changed; only the instructions above it can be edited")
    return None


def with_canonical_block(prompt_type: str, user_prompt: str) -> str:
    """The prompt's instructions followed by the current fixed block. For
    schema migrations only. Recognises the older ``OUTPUT FORMAT`` heading
    the live prompts used before this module existed."""
    instructions, block = split(user_prompt)
    if block is None:
        m = re.search(r"\n\s*OUTPUT FORMAT\s*\n", instructions)
        if m:
            instructions = instructions[:m.start()].rstrip()
    return instructions.rstrip() + "\n\n" + output_block(prompt_type)


def auto_instructions(manual_instructions: str) -> str:
    """The manual instructions without the Political Bias and Factuality
    sections, for seeding the auto prompt."""
    text = re.sub(r"\n\s*Political Bias\n.*?(?=\n\s*\n)", "", manual_instructions, flags=re.S)
    text = re.sub(r"\n\s*Factuality\n.*?(?=\n\s*\n)", "", text, flags=re.S)
    return re.sub(r"\n{3,}", "\n\n", text)
