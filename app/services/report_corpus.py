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
    # Same character as the rest of this list and a different domain from
    # naturalnews.com, which is why it slipped through. It put two articles
    # into a rebuilt United States deck for an oral-health customer.
    "naturalhealth365.com",
)


# Aggregators and syndication portals. They are real domains in real countries,
# so the publisher-country filter has no reason to drop them, but a row from
# one is somebody else's story re-hosted: it credits the aggregator instead of
# the newsroom, and it double-counts a story we often already hold from the
# original. A market topic asking "what is the French press saying" is not
# answered by a Google News entry. Override with REPORT_AGGREGATOR_BLOCKLIST;
# set it empty to turn the whole rule off.
_DEFAULT_AGGREGATOR_SOURCES = (
    "news.google.com",
    "headtopics.com",
    "newsbreak.com",
    "msn.com",
    "flipboard.com",
    "smartnews.com",
    "inkl.com",
    "apple.news",
    "ground.news",
    "dailyhunt.in",
    "bundle.app",
    "lomazoma.com",
    "yahoo.com",
    "yahoo.co.jp",
    "smt.docomo.ne.jp",
)


# Press-release distribution services. A wire item is a company talking about
# itself, carried verbatim: it is not a newsroom's judgement about the world,
# and counting it as evidence lets anyone with a budget put a claim into a
# customer's deck. Distinct from the aggregator list because the problem is
# authorship, not re-hosting, and distinct from the blocklist because nobody is
# alleging bad faith. Override with REPORT_WIRE_BLOCKLIST; empty turns it off.
#
# Grounded in what Sunstar actually collected: prtimes.jp (168 articles),
# globenewswire.com (145), openpr.com (100), prnewswire.com (33),
# businesswire.com (10), presseportal.de (5), prweb.com (3).
#
# NOT on this list, deliberately: europapress.es and its health vertical
# infosalus.com match "press" by name but are Spain's second news agency, and
# newsroom.heart.org is the American Heart Association publishing its own
# research — a primary source, not a paid distribution channel.
_DEFAULT_WIRE_SOURCES = (
    "prnewswire.com",
    "prnewswire.co.uk",
    "businesswire.com",
    "globenewswire.com",
    "einpresswire.com",
    "accesswire.com",
    "prweb.com",
    "prtimes.jp",
    "openpr.com",
    "presseportal.de",
    "presseportal.ch",
    "ots.at",
    "24-7pressrelease.com",
    "newsdirect.com",
    "abnewswire.com",
    "marketersmedia.com",
)


def blocked_sources() -> set:
    raw = _os.getenv("REPORT_SOURCE_BLOCKLIST")
    if raw is None:
        return set(_DEFAULT_BLOCKED_SOURCES)
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def aggregator_sources() -> set:
    raw = _os.getenv("REPORT_AGGREGATOR_BLOCKLIST")
    if raw is None:
        return set(_DEFAULT_AGGREGATOR_SOURCES)
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def wire_sources() -> set:
    raw = _os.getenv("REPORT_WIRE_BLOCKLIST")
    if raw is None:
        return set(_DEFAULT_WIRE_SOURCES)
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


# Tenants that predate per-group collection countries have no
# ``keyword_groups.country`` column at all. Asking anyway makes the facade log
# an ERROR for every topic of every report, on tenants where the answer can
# only ever be "no country". Establish once whether the column exists.
_HAVE_GROUP_COUNTRY: "bool | None" = None


def _group_country_column_exists(db) -> bool:
    global _HAVE_GROUP_COUNTRY
    if _HAVE_GROUP_COUNTRY is None:
        try:
            # information_schema always exists, so this asks the question
            # without provoking the error we are trying to avoid.
            from sqlalchemy import text as _sa_text
            row = db.facade._execute_with_rollback(_sa_text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'keyword_groups' AND column_name = 'country' "
                "LIMIT 1"
            )).fetchone()
            _HAVE_GROUP_COUNTRY = row is not None
        except Exception as e:
            _log.debug("report corpus: could not inspect keyword_groups: %s", e)
            _HAVE_GROUP_COUNTRY = False
        if not _HAVE_GROUP_COUNTRY:
            _log.info("report corpus: no keyword_groups.country on this tenant; "
                      "country filtering is off, the other rules still apply")
    return _HAVE_GROUP_COUNTRY


def market_country_for_topic(topic: str):
    """The ISO2 country a topic is supposed to be about, or None.

    A market topic is one whose collection group declares a country —
    "Oral Health & Whole-Body Health - France" carries ``fr``. Ordinary topics
    declare nothing and are never country-filtered.
    """
    if not topic:
        return None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text as _sa_text
        db = get_database_instance()
        if not _group_country_column_exists(db):
            return None
        row = db.facade._execute_with_rollback(_sa_text(
            "SELECT country FROM keyword_groups "
            "WHERE topic = :t AND country IS NOT NULL AND country <> '' LIMIT 1"
        ), {"t": topic}).fetchone()
    except Exception as e:
        _log.debug("report corpus: country lookup failed for %s: %s", topic, e)
        return None
    if row is None:
        return None
    val = (dict(row._mapping).get("country") or "").strip().lower()
    return val or None


def filter_report_corpus(rows: list, *, topic: str = "") -> list:
    """Drop blocked publishers and near-duplicate headlines, in order.

    Order is preserved, and the first occurrence of a duplicate wins, so
    the caller's ranking (alignment desc, then date desc) is untouched.
    Rows are plain dicts as SELECTed; unknown keys are ignored.
    """
    if not rows:
        return []
    blocked = blocked_sources()

    # A market topic must only cite its own country's press. Until Sep 2026 it
    # could not: no collector honours a country filter, so "France" meant
    # French-LANGUAGE press and a BBC Afrique story counted as French evidence.
    # Publisher country is now resolved per domain and stamped on the article,
    # so the corpus can simply require it.
    want_country = market_country_for_topic(topic)
    have_column = any(isinstance(r, dict) and "source_country" in r for r in rows)
    if want_country and not have_column:
        # The caller's SELECT does not fetch the column. Filtering on a key that
        # is absent would discard the entire corpus, so decline and say so.
        _log.warning("report corpus: topic %r wants country %s but rows carry no "
                     "source_country; not country-filtering", topic, want_country)
        want_country = None

    aggregators = aggregator_sources()
    wires = wire_sources()

    seen: set = set()
    out: list = []
    n_blocked = 0
    n_dupe = 0
    n_country = 0
    n_agg = 0
    n_wire = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if want_country and (row.get("source_country") or "").lower() != want_country:
            n_country += 1
            continue
        if _is_blocked(row, blocked):
            n_blocked += 1
            continue
        if _is_blocked(row, aggregators):
            n_agg += 1
            continue
        if _is_blocked(row, wires):
            n_wire += 1
            continue
        key = _title_key(row.get("title") or "")
        if key and key in seen:
            n_dupe += 1
            continue
        if key:
            seen.add(key)
        out.append(row)
    if n_wire:
        _log.info("report corpus: dropped %d press-release wire row(s) for topic %r",
                  n_wire, topic)
    if n_agg:
        _log.info("report corpus: dropped %d aggregator row(s) for topic %r", n_agg, topic)
    if n_country:
        _log.info("report corpus: dropped %d article(s) not published in %s for topic %r",
                  n_country, want_country, topic)
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
