"""Exact checks on what the review writes: every figure and every name in a
headline or summary must be in the post.

Jev reads a headline against its post and answers whether the post supports
it. It reads figures and dates as text, and it passed "Conifers AI finds 47%
of detections need attention" against a post that said 40%, and "Mate joins
Okta's XAA Ecosystem" against a post that never names Okta. These checks do
not read meaning at all. They look for the characters, so they cannot be
talked round, and they cost nothing.

A failure is an objection like any of Jev's: the corrector sees it and fixes
the text, and what cannot be fixed is not shown.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Optional, Set

_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6,
         "b": 1e9, "bn": 1e9, "billion": 1e9}

# A number with its scale word: "$30M", "30 million", "6K+", "40%", "1,000".
_NUMBER = re.compile(
    r"(?<![\w.])\$?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(k|thousand|mn|m|million|bn|b|billion)?(?![a-z])", re.I)

# Capitalised words and all-caps tokens that are not names: sentence
# openers, market vocabulary, months, days.
_NOT_NAMES = frozenset("""
a an the and or of for to in on at by with from as its it this that
ai soc siem soar edr xdr mdr ndr iam api apis llm llms mcp ciso cto ceo cfo
coo cmo cro vp svp evp gm hr it ot ics saas paas us uk eu uae gcc mena apac
q1 q2 q3 q4 h1 h2 fy new launches launch adds joins hires appoints names
partners acquires raises wins publishes releases introduces unveils expands
january february march april may june july august september october
november december jan feb mar apr jun jul aug sep sept oct nov dec
monday tuesday wednesday thursday friday saturday sunday
security cyber cybersecurity platform agent agents agentic unnamed
""".split())


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def _values(text: str) -> Set[float]:
    """Every number in ``text`` as a value, with and without its scale word,
    so "$30M" in a headline matches "$30 million" or "30,000,000" in a post."""
    out: Set[float] = set()
    for m in _NUMBER.finditer(_plain(text)):
        try:
            base = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.add(base)
        scale = (m.group(2) or "").lower()
        if scale in _MULT:
            out.add(base * _MULT[scale])
    return out


def unsupported_figures(written: str, source: str) -> List[str]:
    """Numbers in ``written`` that ``source`` does not contain."""
    have = _values(source)
    missing: List[str] = []
    for m in _NUMBER.finditer(_plain(written)):
        try:
            base = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        scale = (m.group(2) or "").lower()
        candidates = {base, base * _MULT.get(scale, 1.0)}
        if not any(abs(c - h) <= max(1e-9, 0.005 * abs(h)) for c in candidates for h in have):
            missing.append(m.group(0).strip())
    return missing


def _name_tokens(text: str) -> List[str]:
    """Words that look like names: capitalised, three letters or more, not
    market vocabulary.

    Skipped: the first word of each sentence (capitalised whatever it is:
    "Enables", "Former"); all-caps tokens of four letters or fewer, which are
    acronyms the post may spell out ("MTTR"); and the part of a hyphenated
    word after the hyphen ("CrowdStrike-led" is checked as "CrowdStrike").
    """
    out = []
    for sentence in re.split(r"(?<=[.!?:;])\s+", _plain(text)):
        words = re.findall(r"[A-Za-z][A-Za-z0-9&.'’\-]*[A-Za-z0-9]|[A-Z]{2,}", sentence)
        for i, w in enumerate(words):
            for j, part in enumerate(w.split("-")):
                core = part.strip(".'’")
                low = core.lower()
                if len(core) < 3 or low in _NOT_NAMES:
                    continue
                if not core[0].isupper():
                    continue
                if i == 0 and j == 0 and not core.isupper() and core[1:].islower():
                    continue
                if core.isupper() and len(core) <= 4:
                    continue
                out.append(core)
    return out


def unsupported_names(written: str, source: str,
                      also_known: Optional[Iterable[str]] = None) -> List[str]:
    """Name-like words in ``written`` that appear nowhere in ``source``.

    ``also_known`` are names the post need not spell out: the vendor's own
    name and its aliases, which the byline carries.
    """
    hay = _plain(source).lower()
    hay_squashed = re.sub(r"[^a-z0-9]", "", hay)
    known = {k.lower() for k in (also_known or []) if k}
    known_parts = {p for k in known for p in re.split(r"[^a-z0-9]+", k) if p}
    missing: List[str] = []
    for tok in _name_tokens(written):
        low = tok.lower()
        if low in known or low in known_parts:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(low)}(?![a-z0-9])", hay):
            continue
        # "AquilaI" in the headline, "Aquila I" in the post.
        if re.sub(r"[^a-z0-9]", "", low) in hay_squashed:
            continue
        # A possessive or plural: "Okta's", "Agents".
        stem = re.sub(r"(['’]s|s)$", "", low)
        if stem != low and re.search(rf"(?<![a-z0-9]){re.escape(stem)}", hay):
            continue
        missing.append(tok)
    return missing


def exact_objections(headline: Optional[str], summary: Optional[str],
                     source: str, vendor_names: Iterable[str] = ()) -> List[str]:
    """Objections in the words the corrector reads."""
    out: List[str] = []
    for field, text_value in (("headline", headline), ("summary", summary)):
        if not text_value:
            continue
        figures = unsupported_figures(text_value, source)
        if figures:
            out.append(f"the {field} gives {', '.join(figures)}, which the post "
                       "does not state")
        names = unsupported_names(text_value, source, vendor_names)
        if names:
            out.append(f"the {field} names {', '.join(names)}, which the post "
                       "does not mention")
    return out
