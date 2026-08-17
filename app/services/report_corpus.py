"""Hygiene pass over the article corpus that goes into a customer report.

The corpus for a Wiley Horizons topic is selected by
``topic_alignment_score > 0.7``. That score is coarse — on the
"Attacks on Expertise & Peer Review" topic, 43 articles sit at exactly
1.00 and 246 at exactly 0.80, and plenty of the 1.00s are ordinary AI
business news. Retuning the scorer is a separate job; this module deals
with the two failures the score cannot catch at all:

* **The same story counted several times.** Syndicated wire copy lands
  under several URIs with near-identical titles, so one white paper
  showed up as ``[37] [38] [39] [40] [46]`` in a single report and
  padded the apparent evidence base fivefold.
* **Publishers we should not cite to this customer.** A research-
  integrity report that cites a known health-misinformation site
  undermines itself no matter how the citation is used.

Both filters run at prompt-build time, so the numbered list the model
sees, the list persisted to ``future_horizon_articles``, and the
references section of every export are the same list in the same order.
"""
from __future__ import annotations

import logging as _logging
import os as _os
import re as _re

_log = _logging.getLogger(__name__)


# Publishers excluded from customer-facing report corpora. This is NOT a
# collection filter — the articles stay collected and searchable; they
# just don't become numbered evidence in a document that goes to a
# customer. Override with a comma-separated REPORT_SOURCE_BLOCKLIST.
_DEFAULT_BLOCKED_SOURCES = (
    "naturalnews.com",
    "newstarget.com",
    "healthranger.com",
    "brighteon.com",
    "beforeitsnews.com",
)


def blocked_sources() -> set:
    raw = _os.getenv("REPORT_SOURCE_BLOCKLIST")
    if raw is None:
        return set(_DEFAULT_BLOCKED_SOURCES)
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def _host(value: str) -> str:
    """Bare hostname from a URI or a news_source string, no ``www.``."""
    v = (value or "").strip().lower()
    if not v:
        return ""
    if "://" in v:
        v = v.split("://", 1)[1]
    v = v.split("/", 1)[0].split("?", 1)[0]
    return v[4:] if v.startswith("www.") else v


def _is_blocked(row: dict, blocked: set) -> bool:
    if not blocked:
        return False
    for field in ("news_source", "source", "uri", "url"):
        h = _host(str(row.get(field) or ""))
        if not h:
            continue
        if h in blocked or any(h.endswith("." + b) for b in blocked):
            return True
    return False


_PUNCT_RE = _re.compile(r"[^a-z0-9 ]+")
_WS_RE = _re.compile(r"\s+")

# Prefixes wire syndication bolts onto an otherwise identical headline.
_LEAD_NOISE_RE = _re.compile(
    r"^(?:retracted|retraction(?: note)?|\[retracted\]|correction|update|exclusive|"
    r"breaking|opinion|analysis|commentary)\s*[:\-–—]?\s*"
)


def _title_key(title: str) -> str:
    """Normalised headline used for duplicate detection.

    Lowercased, punctuation stripped, syndication prefixes removed, then
    cut to the first 12 words. Full-string equality misses the common
    case where one outlet appends its own name or a subtitle.
    """
    t = (title or "").strip().lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    t = _LEAD_NOISE_RE.sub("", t)
    return " ".join(t.split()[:12])


def filter_report_corpus(rows: list, *, topic: str = "") -> list:
    """Drop blocked publishers and near-duplicate headlines, in order.

    Order is preserved, and the first occurrence of a duplicate wins, so
    the caller's ranking (alignment desc, then date desc) is untouched.
    Rows are plain dicts as SELECTed; unknown keys are ignored.
    """
    if not rows:
        return []
    blocked = blocked_sources()
    seen: set = set()
    out: list = []
    n_blocked = 0
    n_dupe = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _is_blocked(row, blocked):
            n_blocked += 1
            continue
        key = _title_key(row.get("title") or "")
        if key and key in seen:
            n_dupe += 1
            continue
        if key:
            seen.add(key)
        out.append(row)
    if n_blocked or n_dupe:
        _log.info(
            "report corpus%s: dropped %d blocked-publisher and %d duplicate "
            "articles, %d remain",
            f" [{topic}]" if topic else "", n_blocked, n_dupe, len(out),
        )
    return out


# ── On-topic screen ───────────────────────────────────────────────────
# ``topic_alignment_score`` does not discriminate at the top of its range.
# On "Attacks on Expertise & Peer Review", 43 articles sit at exactly 1.00
# and among them are "Taktile raises $110M to put AI in charge of bank
# decisions" and "Standard Chartered Cutting 8,000 Jobs as AI Focus
# Accelerates". Raising the 0.7 threshold cannot help, because the
# off-topic articles rank at the top. So the corpus gets one cheap
# yes/no pass before it becomes numbered evidence.
#
# nova-lite per the 2026-07-16 cost directive: bulk classification, ~13x
# cheaper than Haiku 4.5. One call per 25 articles, so a 90-article topic
# costs four small calls.

_SCREEN_MODEL = _os.getenv("REPORT_CORPUS_SCREEN_MODEL", "nova-lite")
_SCREEN_BATCH = 25
# Refuse to act on a screen that rejected most of the corpus — that reads
# as a broken prompt or a wrong topic label, not 60 off-topic articles.
_SCREEN_MIN_KEEP_RATIO = 0.35


def screen_enabled() -> bool:
    return _os.getenv("REPORT_CORPUS_SCREEN", "true").strip().lower() \
        not in {"0", "false", "no", "off"}


def _screen_prompt(topic: str, batch: list, offset: int) -> str:
    lines = []
    for i, row in enumerate(batch, start=offset + 1):
        title = (row.get("title") or "")[:180]
        src = (row.get("news_source") or "")[:40]
        summary = (row.get("summary") or "").strip().replace("\n", " ")[:200]
        line = f"{i}. {title} — {src}"
        if summary:
            line += f"\n   {summary}"
        lines.append(line)
    listing = "\n".join(lines)
    # Measured on the live corpus 2026-08-03: a title-only, narrowly-worded
    # version of this prompt dropped 63 of 87 including clearly on-topic
    # material (Springer Nature retraction news, anti-science policy
    # stories under a topic named "Attacks on Expertise"). Hence the broad-
    # reading instruction and the doubt→Y bias: this screen exists to cut
    # obvious junk, and a kept borderline article is a much smaller error
    # than a dropped relevant one.
    return (
        f'Topic: "{topic}"\n\n'
        "For each article below, answer whether it belongs in an evidence set "
        "for this topic.\n\n"
        "Read the topic name broadly: every distinct concept in it counts. "
        "A topic named \"Attacks on Expertise & Peer Review\" covers attacks "
        "on scientific expertise, anti-science policy, misinformation, AND "
        "peer-review, retraction and research-integrity stories.\n\n"
        "Answer N only when the article is clearly about something else and "
        "merely shares a broad field with the topic — an ordinary product "
        "launch, funding round, earnings report, jobs story or how-to guide "
        "is not evidence for a research or policy topic just because it "
        "mentions AI or science. If in doubt, answer Y.\n\n"
        "Answer with one line per article, in order, formatted exactly as "
        "`<number>:Y` or `<number>:N`. No other text.\n\n"
        f"{listing}"
    )


_VERDICT_RE = _re.compile(r"^\s*(\d{1,4})\s*[:.\)-]\s*([YN])", _re.MULTILINE | _re.IGNORECASE)


async def screen_corpus_relevance(rows: list, topic: str,
                                  model: str = None) -> list:
    """Drop articles a cheap model judges off-topic. Fails open.

    Returns the surviving rows in their original order. Any error, an
    unparseable reply, or a suspiciously harsh verdict leaves the corpus
    untouched — a thin report beats no report, and this must never be the
    reason a bundle fails to build.
    """
    if not rows or not screen_enabled():
        return rows
    model = model or _SCREEN_MODEL
    verdicts: dict = {}
    try:
        import asyncio
        import litellm
        from app.ai_models import resolve_litellm_call_params

        async def _one(offset: int, batch: list) -> None:
            resp = await asyncio.to_thread(
                litellm.completion,
                **resolve_litellm_call_params(model),
                messages=[{"role": "user",
                           "content": _screen_prompt(topic, batch, offset)}],
                max_tokens=1200, temperature=0, caching=False,
            )
            text = resp.choices[0].message.content or ""
            for m in _VERDICT_RE.finditer(text):
                verdicts[int(m.group(1))] = m.group(2).upper() == "Y"

        batches = [(i, rows[i:i + _SCREEN_BATCH])
                   for i in range(0, len(rows), _SCREEN_BATCH)]
        await asyncio.gather(*(_one(off, b) for off, b in batches))
    except Exception as e:
        _log.warning("report corpus [%s]: relevance screen failed, keeping all "
                     "%d articles: %s", topic, len(rows), e)
        return rows

    if not verdicts:
        _log.warning("report corpus [%s]: relevance screen returned nothing "
                     "parseable, keeping all %d articles", topic, len(rows))
        return rows

    # Unscored articles are kept — a truncated reply must not silently
    # delete the tail of the corpus.
    kept = [row for i, row in enumerate(rows, 1) if verdicts.get(i, True)]
    ratio = len(kept) / len(rows)
    if ratio < _SCREEN_MIN_KEEP_RATIO:
        _log.warning("report corpus [%s]: screen rejected %d of %d articles "
                     "(%.0f%% kept) — below the %.0f%% floor, ignoring the "
                     "screen. Check the topic label.",
                     topic, len(rows) - len(kept), len(rows), ratio * 100,
                     _SCREEN_MIN_KEEP_RATIO * 100)
        return rows
    if len(kept) < len(rows):
        _log.info("report corpus [%s]: relevance screen dropped %d of %d "
                  "off-topic articles, %d remain",
                  topic, len(rows) - len(kept), len(rows), len(kept))
    return kept
