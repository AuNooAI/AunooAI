"""Compare two versions of a web page by content blocks, not by raw lines.

The vendor-page monitor used to diff normalized lines. That reported a change
whenever a paragraph was re-wrapped, and it accepted whatever came back with
HTTP 200, including Cloudflare challenge pages and login walls, as the new
baseline. This module fixes both problems and is shared verbatim by the
monolith and the SaaS tree, so it must not import anything from ``app``.

Three jobs:

1. ``extract_blocks`` turns extracted page text into blocks. A block is a
   paragraph, a list item, a table row, or a heading. Lines that were only
   wrapped get joined back into one paragraph; list items and table rows stay
   separate so a duplicated price row is still visible as a duplicate.
2. ``compare_blocks`` compares two block lists as multisets. A block that moved
   is not a change. A block that now appears twice is an addition. A paragraph
   that was split or merged across line boundaries is reflow, not a change.
3. ``validate_content`` says whether a fetched page is safe to use as a new
   baseline. Challenge pages, login walls, empty extractions and sudden drops
   in size are reported so the caller keeps the prior baseline.

``NORMALIZER_VERSION`` must change whenever block extraction changes in a way
that alters hashes. Callers compare it against the version stored with a
baseline and reseed instead of reporting a vendor change.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Callable, Iterable, Optional

NORMALIZER_VERSION = "2026.10.01-1"

# Validation outcomes.
V_OK = "ok"
V_BLOCKED = "blocked"
V_EXTRACTION_FAILED = "extraction_failed"
V_SUSPICIOUS_DROP = "suspicious_drop"

# Block kinds.
K_TEXT = "text"
K_LIST = "list"
K_TABLE = "table"
K_HEADING = "heading"

# A page shorter than this that also carries a challenge or login marker is a
# wall, not content. Genuine concise pages above this length are accepted even
# if they mention logging in somewhere.
BLOCKED_MAX_CHARS = 400
# Below this there is nothing to compare; the extractor got nothing useful.
MIN_CONTENT_CHARS = 40
# A page that shrinks to under this fraction of its prior size is held back
# until the caller confirms the removal is real.
SUSPICIOUS_DROP_RATIO = 0.3
# A line at least this long with no sentence-ending punctuation was probably
# wrapped mid-sentence, so the next line is joined onto it.
WRAP_MIN_CHARS = 60

_BLOCK_MARKERS = (
    "verify you are human",
    "checking your browser",
    "checking if the site connection is secure",
    "just a moment",
    "attention required",
    "access denied",
    "enable javascript and cookies",
    "please enable cookies",
    "sign in",
    "log in to continue",
    "login to continue",
    "captcha",
    "ray id",
    "request blocked",
    "unusual traffic",
    "are you a robot",
)
_BLOCKED_STATUSES = {401, 403, 407, 429, 503}

_LIST_RE = re.compile(r"^\s*(?:[-*•▪◦]|\d{1,3}[.)])\s+\S")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+\S")
_TERMINAL_PUNCT = (".", "!", "?", ":", ";", ",")
_WS_RE = re.compile(r"\s+")


class Block(str):
    """A comparable unit of page content. Compares and hashes as its text, so
    ``"\\n".join(blocks)`` and ``Counter(blocks)`` work; ``kind`` rides along
    so the comparison knows which blocks may be reflowed."""

    kind: str

    def __new__(cls, text: str, kind: str = K_TEXT) -> "Block":
        obj = super().__new__(cls, text)
        obj.kind = kind
        return obj


def _collapse(line: str) -> str:
    return _WS_RE.sub(" ", line).strip()


def classify_line(line: str) -> str:
    """Which kind of block a single line starts. Table rows need two or more
    pipe or tab separators; list items start with a bullet or a number; a
    heading is a markdown heading."""
    stripped = line.strip()
    if not stripped:
        return K_TEXT
    if _HEADING_RE.match(stripped):
        return K_HEADING
    if _LIST_RE.match(stripped):
        return K_LIST
    if stripped.count("|") >= 2 or line.count("\t") >= 2:
        return K_TABLE
    return K_TEXT


def _looks_wrapped(prev: str) -> bool:
    """A long line without terminal punctuation was cut by a wrap, not by the
    author."""
    return len(prev) >= WRAP_MIN_CHARS and not prev.endswith(_TERMINAL_PUNCT)


def _continues(prev: str, cur: str) -> bool:
    """Should ``cur`` be joined onto paragraph line ``prev``?

    Yes when ``cur`` starts in lower case (nobody starts a heading or a price
    label that way) or when ``prev`` looks wrapped and ``cur`` reads like the
    rest of a sentence: long, or ending in punctuation. A short label such as
    "Pro $60" after a long line stays its own block, because a wrapped
    paragraph's last line almost always ends with a full stop.
    """
    if not prev or not cur:
        return False
    if cur[0].islower():
        return True
    if _looks_wrapped(prev):
        return len(cur) >= WRAP_MIN_CHARS or cur.endswith(_TERMINAL_PUNCT)
    return False


def extract_blocks(
    text: Optional[str],
    *,
    ignore_line: Optional[Callable[[str], bool]] = None,
) -> list[Block]:
    """Blocks of already-extracted page text.

    A paragraph ends at a blank line or at a line that is a list item, table
    row or heading. Inside a paragraph, wrapped lines are joined with one
    space and whitespace is collapsed. Nothing else is changed: numbers,
    currency symbols and units stay exactly as written. ``ignore_line`` lets
    the caller drop furniture (cookie banners, nav) before blocking.
    """
    blocks: list[Block] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            blocks.append(Block(" ".join(para), K_TEXT))
            para.clear()

    for raw in (text or "").splitlines():
        line = _collapse(raw)
        if not line:
            flush()
            continue
        if ignore_line is not None and ignore_line(line):
            continue
        kind = classify_line(raw)
        if kind != K_TEXT:
            flush()
            blocks.append(Block(line, kind))
            continue
        if para and _continues(para[-1], line):
            para[-1] = para[-1] + " " + line
        else:
            flush()
            para.append(line)
    flush()
    return blocks


def semantic_digest(blocks: Iterable[str]) -> str:
    """Hash of the block sequence. Stable across whitespace and line wrapping,
    changes when any block's text changes."""
    return hashlib.sha256("\n".join(blocks).encode("utf-8")).hexdigest()


def _kind(block: Any) -> str:
    return getattr(block, "kind", K_TEXT)


def _runs(items: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """Group (index, text) pairs into runs of consecutive indices."""
    runs: list[list[tuple[int, str]]] = []
    for idx, txt in items:
        if runs and runs[-1][-1][0] == idx - 1:
            runs[-1].append((idx, txt))
        else:
            runs.append([(idx, txt)])
    return runs


def _explain_reflow(
    removed: list[tuple[int, str]], added: list[tuple[int, str]],
) -> tuple[set[int], set[int]]:
    """Indices on each side that are explained by re-wrapping alone.

    Two exact checks, so a changed number can never be hidden:
    - a whole run of removed blocks joined with spaces equals a whole run of
      added blocks joined the same way (a paragraph re-wrapped), or
    - one block on one side equals a contiguous window of a run on the other
      side (lines merged into one, or one line split into several).
    """
    old_runs = _runs(removed)
    new_runs = _runs(added)
    old_done: set[int] = set()
    new_done: set[int] = set()

    def join(run: list[tuple[int, str]]) -> str:
        return " ".join(t for _, t in run)

    for orun in old_runs:
        for nrun in new_runs:
            if any(i in old_done for i, _ in orun) or any(i in new_done for i, _ in nrun):
                continue
            if join(orun) == join(nrun):
                old_done.update(i for i, _ in orun)
                new_done.update(i for i, _ in nrun)

    def match_windows(singles, runs, singles_done, runs_done):
        for idx, txt in singles:
            if idx in singles_done:
                continue
            for run in runs:
                hit = False
                n = len(run)
                for start in range(n):
                    for end in range(start + 2, n + 1):
                        window = run[start:end]
                        if any(i in runs_done for i, _ in window):
                            continue
                        if join(window) == txt:
                            runs_done.update(i for i, _ in window)
                            singles_done.add(idx)
                            hit = True
                            break
                    if hit:
                        break
                if hit:
                    break

    match_windows(added, old_runs, new_done, old_done)
    match_windows(removed, new_runs, old_done, new_done)
    return old_done, new_done


def compare_blocks(old_blocks: list, new_blocks: list) -> dict[str, Any]:
    """Multiset comparison of two block lists.

    ``added`` and ``removed`` are the blocks that differ after moves and
    reflow are taken out. A block present once before and twice now is one
    addition (Counter difference, not set difference). ``moved_count`` is how
    many shared blocks changed position. ``reflowed_count`` is how many blocks
    differed only by line wrapping and were discounted. ``material`` is true
    when anything remains added or removed.
    """
    old = [str(b) for b in old_blocks]
    new = [str(b) for b in new_blocks]
    old_counter = Counter(old)
    new_counter = Counter(new)

    # Shared blocks in each side's order, to count moves.
    common = old_counter & new_counter

    def shared_in_order(seq: list[str]) -> list[str]:
        left = Counter(common)
        out: list[str] = []
        for b in seq:
            if left[b] > 0:
                left[b] -= 1
                out.append(b)
        return out

    old_common = shared_in_order(old)
    new_common = shared_in_order(new)
    matcher = SequenceMatcher(a=old_common, b=new_common, autojunk=False)
    in_place = sum(size for _, _, size in matcher.get_matching_blocks())
    moved_count = len(old_common) - in_place

    removed_counter = old_counter - new_counter
    added_counter = new_counter - old_counter
    old_kinds = {str(b): _kind(b) for b in old_blocks}
    new_kinds = {str(b): _kind(b) for b in new_blocks}

    # Each unmatched block with its position in the original list.
    rem_left = Counter(removed_counter)
    removed_idx: list[tuple[int, str]] = []
    for i, b in enumerate(old):
        if rem_left[b] > 0:
            rem_left[b] -= 1
            removed_idx.append((i, b))
    add_left = Counter(added_counter)
    added_idx: list[tuple[int, str]] = []
    for i, b in enumerate(new):
        if add_left[b] > 0:
            add_left[b] -= 1
            added_idx.append((i, b))

    # Only paragraph text can be reflowed. List items and table rows keep
    # their boundaries, so a duplicated row is never explained away.
    old_text_only = [(i, b) for i, b in removed_idx if old_kinds.get(b) == K_TEXT]
    new_text_only = [(i, b) for i, b in added_idx if new_kinds.get(b) == K_TEXT]
    old_reflowed, new_reflowed = _explain_reflow(old_text_only, new_text_only)

    removed = [b for i, b in removed_idx if i not in old_reflowed]
    added = [b for i, b in added_idx if i not in new_reflowed]
    return {
        "added": added,
        "removed": removed,
        "added_count": len(added),
        "removed_count": len(removed),
        "moved_count": moved_count,
        "reflowed_count": len(old_reflowed) + len(new_reflowed),
        "material": bool(added or removed),
    }


def validate_content(
    text: Optional[str],
    prior_text: Optional[str] = None,
    status: int = 200,
) -> tuple[str, str]:
    """Is this page text fit to become the new baseline?

    Returns ``(outcome, reason)``. ``blocked`` for challenge and login pages
    (short text with a wall marker, or a blocking HTTP status),
    ``extraction_failed`` for empty or near-empty text, ``suspicious_drop``
    when the page lost more than 70 percent of its prior size, otherwise
    ``ok``. A concise page of 400 characters or more passes even when it
    mentions signing in, because real pages do.
    """
    body = (text or "").strip()
    length = len(body)
    if status in _BLOCKED_STATUSES:
        return V_BLOCKED, f"HTTP {status}"
    low = body.lower()
    if length < BLOCKED_MAX_CHARS:
        for marker in _BLOCK_MARKERS:
            if marker in low:
                return V_BLOCKED, f"challenge or login page ({marker!r})"
    if length < MIN_CONTENT_CHARS:
        return V_EXTRACTION_FAILED, f"extracted {length} chars"
    prior_len = len((prior_text or "").strip())
    if prior_len and length < SUSPICIOUS_DROP_RATIO * prior_len:
        return V_SUSPICIOUS_DROP, f"content fell from {prior_len} to {length} chars"
    return V_OK, ""
