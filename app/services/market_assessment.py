"""What the evidence says about a market: developments, who moved, findings.

The monitoring system answers "what did we collect". This module turns that
into "what changed, who changed, and how sure are we", so the report can lead
with conclusions and keep the tables as evidence behind them.

Four things live here, in the order the report uses them:

1. **Material developments** — one entry per real-world event, however many
   articles, posts and tweets discussed it. Built from the stored entity events,
   the matched corpus, job listings and headcount readings, and deduplicated
   deterministically (same vendor, same kind of event, close in time, and a
   shared name or subject). Every source record is kept underneath the event.
2. **Vendor observation states** — for each vendor, whether we saw a material
   change, watched and saw none, could not watch well enough to say, or were
   not watching at all. "No signal" is never allowed to mean "not observed".
3. **Findings** — three to six declarative statements generated from templates
   whose inputs are the counts above. Each template declares the coverage it
   needs, and a template whose coverage is not met produces nothing.
4. **Synthesis** — what the distribution of events says about the market, as
   short bounded paragraphs.

Nothing here renders HTML, and nothing here calls a model. The report renderer
(``market_report_html``) takes these structures as they are; it does not decide
whether something is material. ``market_analysis`` re-exports the entry points
so callers that expect them there find them.

Everything is deterministic and runs from stored rows in one pass, so the
report renders quickly and the same data always gives the same page.
"""

from __future__ import annotations

import logging
import os
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

#: Canonical development types, in the order the report ranks them. Earlier
#: is more material. The label is what a reader sees.
EVENT_TYPES: "OrderedDict[str, str]" = OrderedDict([
    ("acquisition", "Acquisition"),
    ("market_exit", "Market exit or shutdown"),
    ("market_entry", "Market entry"),
    ("funding", "Funding"),
    ("customer", "Customer evidence"),
    ("product_expansion", "Product expansion"),
    ("partnership", "Partnership"),
    ("product_launch", "Product launch"),
    ("executive_appointment", "Executive appointment"),
    ("headcount_change", "Headcount change"),
    ("significant_hiring", "Hiring"),
])

_TYPE_RANK = {t: i for i, t in enumerate(EVENT_TYPES)}

#: Types that merge with each other during deduplication. A vendor's own post
#: calls something a launch and a publisher calls the same thing an expansion;
#: they are one event.
_FAMILY = {
    "product_launch": "product", "product_expansion": "product",
    "acquisition": "ownership", "market_exit": "ownership",
    "market_entry": "ownership", "funding": "capital",
    "customer": "customer", "partnership": "partnership",
    "executive_appointment": "people", "significant_hiring": "hiring",
    "headcount_change": "headcount",
}

PRODUCT_TYPES = frozenset({"product_launch", "product_expansion"})
ADOPTION_TYPES = frozenset({"customer"})
CAPITAL_TYPES = frozenset({"funding", "acquisition"})

#: How a stored ``bw_entity_events.event_type`` maps onto the canonical set.
#: Types absent here are not material developments: a rebrand, a sentiment
#: shift, a coverage spike, a certification and an office move all stay in the
#: corpus and out of the report's lead.
_STORED_TYPE_MAP = {
    "acquisition": "acquisition", "merger": "acquisition",
    "funding_round": "funding", "investment": "funding", "ipo": "funding",
    "product_launch": "product_launch", "product_update": "product_expansion",
    "integration": "product_expansion",
    "partnership": "partnership", "reseller_agreement": "partnership",
    "customer_win": "customer",
    "leadership_change": "executive_appointment",
    "headcount_change": "headcount_change", "layoff": "headcount_change",
}

#: How a reviewed vendor post's ``review_kind`` maps onto the canonical set.
_REVIEW_KIND_MAP = {
    "launch": "product_launch", "funding": "funding", "customer": "customer",
    "partnership": "partnership", "acquisition": "acquisition",
    "hiring": "executive_appointment",
}


# ---------------------------------------------------------------------------
# Text classification — the keyword rules, kept out of the renderer
# ---------------------------------------------------------------------------

_PATTERNS: Sequence[Tuple[str, "re.Pattern[str]"]] = (
    ("market_exit", re.compile(
        r"\b(shuts?\s+down|shutting\s+down|wind(s|ing)?\s+down|ceases?\s+"
        r"operations|closes?\s+its\s+doors|files?\s+for\s+bankruptcy|"
        r"exits?\s+the\s+market)\b", re.I)),
    ("acquisition", re.compile(
        r"\bacqui(r(e|es|ed|ing)|sition)\b|\bbuys\b|\bto\s+buy\b|\bmerge[sd]?\b"
        r"|\bmerger\b", re.I)),
    ("funding", re.compile(
        r"\braises?\s+\$|\braised\s+\$|\bseries\s+[a-e]\b|\bfunding\s+round\b"
        r"|\bseed\s+round\b|\bcloses?\s+(a\s+)?\$[\d.,]+\s*(m|million|b|billion)"
        r"|\bsecures?\s+\$", re.I)),
    ("market_entry", re.compile(
        r"\b(enters?|entry\s+into|expands?\s+into|moves?\s+into)\s+(the\s+)?"
        r"[\w-]+(\s+[\w-]+)?\s+(market|category|space)\b", re.I)),
    ("customer", re.compile(
        r"\bselect(s|ed)\s+\w+(\s+\w+)?\s+(to|as|for)\b|\bdeploy(s|ed)\s+"
        r"(\w+\s+){0,3}(at|across|by|with)\b|\bnames\s+\w+\s+as\s+(a\s+)?"
        r"customer\b|\b(new\s+)?customer\s+(case\s+study|win|story)\b"
        r"|\bcase\s+study:|\bgoes\s+live\s+with\b|\bcontract\s+(with|from)\b"
        r"|\bsigns?\s+(\w+\s+){0,3}(as\s+a\s+)?customer\b|\bchose\s+\w+\s+"
        r"(to|as|for|over)\b", re.I)),
    ("partnership", re.compile(
        r"\bpartner(s|ed|ship|ing)?\b|\balliance\b|\bteams?\s+up\s+with\b"
        r"|\bjoins?\s+forces\b|\breseller\b", re.I)),
    ("product_launch", re.compile(
        r"\blaunch(es|ed|ing)?\b|\bunveils?\b|\bdebuts?\b|\bintroduc(es|ed|ing)\b"
        r"|\bgenerally\s+available\b|\bnow\s+available\b|\breleases?\b"
        r"|\bnew\s+(feature|capability|module|workflow|integration)s?\b"
        r"|\bnow\s+supports?\b|\badds?\b|\bexpands?\b|\bextends?\b"
        r"|\brolls?\s+out\b|\bships?\b|\bupgrades?\b",
        re.I)),
    ("executive_appointment", re.compile(
        r"\b(appoints?|appointed|names?|named|hires?|hired|joins?|joined|"
        r"welcomes?)\b.{0,80}\b(chief|ceo|cto|cfo|cro|coo|cmo|ciso|cpo|"
        r"vp|vice\s+president|head\s+of|director|president|general\s+manager|"
        r"founder)\b", re.I | re.S)),
)

#: Within the product family: words that say an existing product grew, as
#: opposed to a product appearing. Bounded on purpose — it decides a label
#: between two kinds of product news, nothing more.
_EXPANSION = re.compile(
    r"\bnow\s+supports?\b|\badds?\b|\badded\b|\bnew\s+(feature|capability|"
    r"module|workflows?|integrations?)\b|\bexpands?\b|\bextends?\b|\brolls?\s+"
    r"out\b|\bsupport\s+for\b|\bintroduc(es|ed|ing)\s+\S+\s+(workflows?|"
    r"response|automation|agents?|integration)\b", re.I)

#: Product news that moves from investigation toward acting on findings —
#: used only to word "why it matters" for a product expansion.
_RESPONSE = re.compile(
    r"\b(respon(se|d)|remediat\w*|containment|contain\b|take\s+action|"
    r"automated\s+actions?|playbooks?)\b", re.I)

#: A named senior role. A "welcome to the team" post about a junior hire is a
#: fact about the company, not a material development.
_SENIOR = re.compile(
    r"\b(chief\s+\w+\s+officer|c[etfrmis]o|ciso|cpo|vp\b|vice\s+president|"
    r"head\s+of|director|president|general\s+manager|founder|partner\b)",
    re.I)

#: Records that never become a development, whatever they match. Each line is
#: a class of post that turned up in the lead of an earlier report: people
#: looking for SOC work, course completions, freelance adverts, market-size
#: SEO reports, event promotion.
_NOISE = re.compile(
    r"\bfor\s+hire\b|\blooking\s+for\s+(work|opportunit|a\s+job|roles?|"
    r"positions?|an?\s+(internship|role))|\bopen\s+to\s+work\b|\bhire\s+me\b"
    r"|\bmy\s+resume\b|\bjob[- ]seek|\bseeking\s+(a\s+)?(role|position|job)"
    r"|\bi\s+just\s+completed\b|\bcompleted\s+(the\s+)?\S+\s+(room|course|"
    r"module|certification|training|lab)\b|\btryhackme\b|\bhackthebox\b"
    r"|\bexam\s+prep\b|\bfreelanc|\$\s?\d+\s?/\s?h(ou)?r?\b"
    r"|\bmarket\s+size\b|\bmarket\s+(research\s+)?report\b|\bcagr\b"
    r"|\bforecast\s+(to\s+)?20\d\d\b|\bindustry\s+analysis\s+report\b"
    r"|\bwebinar\b|\bregister\s+now\b|\bjoin\s+us\s+(at|for)\b|\bbooth\b"
    r"|\badd\s+this\s+session\b|\bsave\s+the\s+date\b|\bsee\s+you\s+at\b"
    r"|\brequesting\s+recommendations\b|\bday\s?\d+\b.{0,40}\bchallenge\b"
    r"|\b\d+\s?days?\s?challenge\b|\bbuilding\s+in\s+public\b", re.I)

#: Words a sentence does not end on. A title ending on one was cut short.
_DANGLING = frozenset("""
where and or the a an of to in on for with that which is are was were it's its
but as at by from into than then so if when while because we our you your their
they this these those how what who be been has have had can will would could
should not no also very more most such only same other another nor yet
""".split())

#: A headline the extractor could not find: somebody's "Post", a bare link,
#: or the boilerplate before one. Mirrors ``headlineOf`` in
#: ``MarketFindingsView.tsx`` so the page and the report agree.
_JUNK_HEADLINE = re.compile(r"(’s|'s) Post$|https?://|^Full announcement", re.I)

# Words that carry no subject. Generic English plus the vocabulary every
# announcement in a software market shares; a shared "platform" or "security"
# is not evidence that two records describe one event.
_COMMON = frozenset("""
the a an and or but of to in on for with is are was were at by from this that
it its as be we our you your new how why what more just now can will has have
had not with into about over under after before than then there their they
them here also very more most much many some such only same other another
been being being does did done make makes made get gets got take takes took
give gives gave use uses used using see sees seen say says said know knows
first last next back well still even ever every each both any all
introducing introduce introduces announce announces announced announcing
launch launches launched launching unveils unveil release releases released
product products platform platforms solution solutions service services
technology technologies capability capabilities feature features tool tools
company companies team teams customer customers partner partners partnership
security cyber cybersecurity soc automation automated autonomous agentic
agent agents analyst analysts alert alerts triage detection response threat
threats data cloud enterprise enterprises operations operation intelligence
today week month year years time work works working world market markets
industry leading leader leaders proud excited thrilled happy pleased welcome
learn read more click link full announcement post posts blog news story
support supports supported supporting help helps helping across between
through without within toward towards ai llm llms genai generative model
models alliance global enterprise
""".split())

#: Upper-case tokens that are generic in this domain rather than names.
_GENERIC_CAPS = frozenset({
    "AI", "SOC", "LLM", "MCP", "API", "SIEM", "SOAR", "MDR", "MSSP", "EDR",
    "XDR", "SASE", "CISO", "CEO", "CTO", "CFO", "CRO", "VP", "US", "USA",
    "UK", "EU", "IT", "GA", "SaaS", "ML", "RSA", "NIST", "CMMC", "SOC2",
    "AWS", "GCP", "MITRE", "ATT&CK", "GenAI", "OK", "NEW", "Q1", "Q2", "Q3",
    "Q4", "PR", "FAQ", "PDF", "CVE",
})

#: Merge window: two records this many days apart can still be one event.
MERGE_WINDOW_DAYS = 14
#: Days an attached report may precede the development it reports.
ATTACH_LEAD_DAYS = 2
#: Shared subject words needed to merge two records with no shared name,
#: and the share of both records' words they must make up.
MIN_SHARED_WORDS = 3
MIN_SHARED_RATIO = 0.25
#: A record with fewer subject words than this is "short" — a tweet, a
#: headline-only post — and merges on one shared name.
SHORT_RECORD_WORDS = 8

#: Open roles observed in the period before hiring is a development.
MIN_OPENINGS_FOR_HIRING = max(1, int(os.getenv(
    "MARKET_MIN_OPENINGS_FOR_HIRING", "5") or 5))
#: Headcount movement between two readings before it is a development.
MIN_HEADCOUNT_PCT = float(os.getenv("MARKET_MIN_HEADCOUNT_PCT", "10") or 10)
#: How many developments the main table shows before the rest fold away.
MAIN_TABLE_LIMIT = max(1, int(os.getenv("MARKET_MAIN_TABLE_LIMIT", "8") or 8))


def is_noise(text_value: str) -> bool:
    """A record the report should never lead with."""
    return bool(_NOISE.search(text_value or ""))


def _refine_product(kind: str, text_value: str) -> str:
    if kind == "product_launch" and _EXPANSION.search(text_value or ""):
        return "product_expansion"
    return kind


#: Kinds a body match is enough for. Ownership and capital events are worth
#: catching wherever they appear in a page; product, customer and partnership
#: words appear in the body of every marketing page ever written.
_BODY_KINDS = frozenset({"acquisition", "market_exit", "market_entry", "funding"})


def classify_text(text_value: str, *, title: Optional[str] = None
                  ) -> Optional[str]:
    """The kind of development a third-party record describes, or None.

    Keyword rules, tested in order of how much they change the market. A
    headline saying "acquires" and "launches" is an acquisition. Noise is
    rejected before any rule is tried, so a job-seeker post naming an
    acquisition still returns None.

    With ``title`` given, product, customer and partnership rules are tried
    against the title only. A vendor's "What is agentic security?" explainer
    mentions launching, deploying and partners in its body, and is none of
    those things.
    """
    if not text_value or is_noise(text_value):
        return None
    for kind, pattern in _PATTERNS:
        scope = text_value if (title is None or kind in _BODY_KINDS) else title
        if pattern.search(scope or ""):
            return _refine_product(kind, text_value)
    return None


def classify_record(record: Dict[str, Any]) -> Optional[str]:
    """The canonical development type of one corpus record, or None.

    A vendor's own post carries a reviewer's verdict and kind, and those are
    trusted: the review pass read the post. Everything else is matched on its
    words. Practitioner social and research never seed a development from
    here — they attach to one as evidence, or stay in the corpus.
    """
    text_value = f"{record.get('title') or ''} {record.get('summary') or ''}"
    if is_noise(text_value):
        return None
    kind = record.get("article_class")
    if kind == "social":
        if record.get("review_verdict") != "signal":
            return None
        mapped = _REVIEW_KIND_MAP.get((record.get("review_kind") or "").lower())
        if mapped == "executive_appointment" and not _SENIOR.search(text_value):
            return None
        if mapped is None:
            return None
        return _refine_product(mapped, text_value)
    if kind in ("discussion", "research"):
        return None
    # News and vendor-web pages: a development only when a tracked vendor is
    # named. A launch by a company we do not track is not one of the vendors'
    # moves, however well it matched the market's phrases.
    if not record.get("vendors"):
        return None
    return classify_text(text_value, title=record.get("title") or "")


def headline_of(record: Dict[str, Any]) -> str:
    """A headline a reader can use, from a record whose title may not be one.

    Strips the "Vendor:" prefix the extractor adds, and falls back to the
    body's first sentence when the title is somebody's "Post" or a bare link.
    """
    headline = (record.get("headline") or record.get("title") or "").strip()
    summary = (record.get("summary") or "").strip()
    for v in record.get("vendors") or []:
        name = (v.get("vendor") or "").strip()
        if not name:
            continue
        if headline.lower().startswith(f"{name.lower()}:"):
            headline = headline[len(name) + 1:].strip() or headline
        # A web page's title carries the site name after a bar.
        for sep in (" | ", " – ", " — ", " - "):
            if headline.lower().endswith(f"{sep}{name.lower()}"):
                headline = headline[:-(len(sep) + len(name))].strip() or headline
    # A title cut mid-sentence ("Our team prides itself on being
    # customer-centric, and it's where") is the opening of the body; the
    # body's first sentence is the headline.
    # A headline has no full stop; a post cut mid-sentence ends on a word
    # that cannot end one ("and it's where"), or is the opening of its own
    # body.
    last = headline.lower().split()[-1] if headline.split() else ""
    truncated = bool(headline) and not re.search(r"[.!?…\"”)]$", headline) and (
        last in _DANGLING
        or (len(headline) >= 60 and bool(summary)
            and summary.lower().startswith(headline[:30].lower())))
    if (_JUNK_HEADLINE.search(headline) or not headline or truncated) and summary:
        usable = [x for x in _sentences(summary)
                  if len(x) >= 12 and "http" not in x]
        # The first sentence that says something; a four-word opener is a
        # hook, not a headline.
        first = next((x for x in usable if len(x) >= 40), usable[0] if usable else "")
        if first:
            headline = _clip(first, 160)
    return headline or "Untitled"


def _sentences(text_value: str) -> List[str]:
    """Sentences, allowing for a closing quote after the full stop and not
    splitting on an initial ("J.B. Poindexter")."""
    text_value = re.sub(r"\s+", " ", text_value or "").strip()
    parts = re.split(r"(?<=[.!?])\s+|(?<=[.!?][\"”’)])\s+", text_value)
    out: List[str] = []
    for part in parts:
        if out and re.search(r"\b[A-Z]\.$", out[-1]):
            out[-1] = out[-1] + " " + part
        else:
            out.append(part)
    return [x for x in out if x]


def _clip(text_value: str, limit: int) -> str:
    text_value = (text_value or "").strip()
    if len(text_value) <= limit:
        return text_value
    cut = text_value[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return (cut or text_value[:limit]) + "…"


# ---------------------------------------------------------------------------
# Subject words — what two records must share to be one event
# ---------------------------------------------------------------------------

def _tokens(text_value: str) -> List[str]:
    """Words, without links, handles, hashtags, domains or possessives.

    "Cribl's" and "Cribl" are one name; "#CIOCommunity" and
    "shepherdgazette.bsky.social" are not subjects.
    """
    text_value = re.sub(r"https?://\S+|[@#]\S+|\b\S+\.\S+\b", " ",
                        text_value or "")
    out = []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9'’&\-]{2,}", text_value):
        tok = re.sub(r"['’]s$", "", tok)
        if len(tok) >= 3:
            out.append(tok)
    return out


def subject_words(text_value: str, stop: Set[str]) -> Set[str]:
    """Lower-case words that carry a record's subject."""
    out = set()
    for tok in _tokens(text_value):
        word = tok.lower().strip(".'-&")
        if len(word) < 4 or word in _COMMON or word in stop:
            continue
        out.add(word)
    return out


def _capitalised_words(text_value: str, stop: Set[str]) -> Set[str]:
    out = set()
    for tok in _tokens(text_value):
        word = tok.strip(".'-&")
        low = word.lower()
        if len(low) < 3 or low in _COMMON or low in stop:
            continue
        if word in _GENERIC_CAPS or word.upper() == word and len(word) <= 3:
            continue
        if word[0].isupper():
            out.add(low)
    return out


def _is_title_case(title: str) -> bool:
    words = [t for t in _tokens(title) if len(t) >= 4 and t.isalpha()]
    if len(words) < 3:
        return False
    return sum(1 for w in words if w[0].isupper()) / len(words) >= 0.6


def subject_names(title: str, body: str, stop: Set[str]) -> Set[str]:
    """Capitalised subject words — usually a counterparty or a product name.

    Only the title and the opening of the body are read. Bodies run long and
    name people, places and old products, and two posts by one vendor in a
    fortnight share those without being the same event.

    A Title-Case headline capitalises every word, so "Advances" and
    "Acquisition" in a press-release title would pass as names and match any
    long article using those words. From such a title a word counts only if
    the body, written in sentence case, capitalises it too.
    """
    names = _capitalised_words((body or "")[:160], stop)
    title_names = _capitalised_words(title or "", stop)
    if title_names and _is_title_case(title or "") and (body or "").strip():
        title_names &= _capitalised_words(body or "", stop)
    return names | title_names


def _title_of(record: Dict[str, Any]) -> str:
    # A corpus row carries ``title``; a candidate carries ``headline``.
    return record.get("title") or record.get("headline") or ""


def _lead_text(record: Dict[str, Any]) -> str:
    return f"{_title_of(record)} {(record.get('summary') or '')[:160]}"


def _full_text(record: Dict[str, Any]) -> str:
    return f"{_title_of(record)} {record.get('summary') or ''}"


# ---------------------------------------------------------------------------
# Candidates and deduplication
# ---------------------------------------------------------------------------

def _parse_day(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _within(a: Optional[date], b: Optional[date], days: int) -> bool:
    if a is None or b is None:
        return True
    return abs((a - b).days) <= days


def _vendor_ids(cand: Dict[str, Any]) -> Set[Any]:
    out = set()
    for v in cand.get("vendors") or []:
        ident = v.get("brand_id")
        out.add(ident if ident is not None else (v.get("vendor") or "").lower())
    return out


def same_development(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Whether two candidates describe one event.

    Same family of event, close in time, about a vendor in common (or one of
    them attributed to nobody), and either a shared name — a counterparty, a
    product — or enough shared subject words. A short record, which is what a
    tweet or a reposted headline is, merges on one shared name alone.
    """
    if _FAMILY.get(a["event_type"]) != _FAMILY.get(b["event_type"]):
        return False
    if not _within(a.get("day"), b.get("day"), MERGE_WINDOW_DAYS):
        return False
    # A report of an event cannot come out before the event. A record that
    # can only attach (practitioner social, a body-text mention in a news
    # piece) is a report; dated more than two days before the development it
    # is not a report of it, whatever words they share.
    if not b.get("seed") and a.get("day") and b.get("day") \
            and b["day"] < a["day"] - timedelta(days=ATTACH_LEAD_DAYS):
        return False
    va, vb = _vendor_ids(a), _vendor_ids(b)
    if va and vb and not (va & vb):
        return False
    # A name on one side counts when the other side has the same word in
    # lower case: a vendor writes "Intezer Workflows", a publisher writes
    # "adds automated response workflows".
    shared_names = ((a["names"] & b["names"]) | (a["names"] & b["words"])
                    | (b["names"] & a["words"]))
    shared_words = a["words"] & b["words"]
    union = len(a["words"] | b["words"]) or 1
    short = min(len(a["words"]), len(b["words"])) < SHORT_RECORD_WORDS
    if not (va and vb):
        # One side names no tracked vendor: a reposted headline, a tweet. It
        # joins on two shared names, or — if it is short — one name plus a
        # shared subject. A long article sharing one name with the event
        # mentions it in passing at most, and is not evidence of it.
        if len(shared_names) >= 2:
            return True
        return bool(shared_names) and len(shared_words) >= 2 and short
    if shared_names and (short or len(shared_words) >= 2 or len(shared_names) >= 2):
        return True
    # No shared name: most of both records' subject words have to overlap.
    # Three words in common between two long posts by one vendor is normal;
    # three in common out of ten is the same story.
    return (len(shared_words) >= MIN_SHARED_WORDS
            and len(shared_words) / union >= MIN_SHARED_RATIO)


def prepare_candidate(cand: Dict[str, Any], stop: Set[str]) -> Dict[str, Any]:
    """Add the derived fields deduplication reads."""
    vendor_words = set()
    for v in cand.get("vendors") or []:
        for w in re.findall(r"[a-z][a-z0-9'\-]{2,}", (v.get("vendor") or "").lower()):
            vendor_words.add(w)
    all_stop = stop | vendor_words
    cand["words"] = subject_words(_full_text(cand), all_stop)
    cand["names"] = subject_names(_title_of(cand), cand.get("summary") or "",
                                  all_stop)
    cand["day"] = _parse_day(cand.get("date"))
    cand.setdefault("evidence", [])
    cand.setdefault("seed", True)
    return cand


def _merge_into(dev: Dict[str, Any], cand: Dict[str, Any]) -> None:
    seen = {(e.get("uri") or e.get("key")) for e in dev["evidence"]}
    for e in cand.get("evidence") or []:
        ident = e.get("uri") or e.get("key")
        if ident in seen:
            continue
        seen.add(ident)
        dev["evidence"].append(e)
    known = _vendor_ids(dev)
    for v in cand.get("vendors") or []:
        ident = v.get("brand_id") if v.get("brand_id") is not None \
            else (v.get("vendor") or "").lower()
        if ident not in known:
            dev["vendors"].append(v)
            known.add(ident)
    dev["words"] |= cand["words"]
    dev["names"] |= cand["names"]
    # The earliest *seed* record dates the event; a repost days later does
    # not, and an attached mention cannot move it either way.
    if cand.get("seed") and cand.get("day") and (
            dev.get("day") is None or cand["day"] < dev["day"]):
        dev["day"], dev["date"] = cand["day"], cand.get("date")
    # An outside headline beats a vendor's own wording, and any headline
    # beats one built from a post with no first sentence.
    if cand.get("seed") and cand.get("headline_rank", 9) < dev.get("headline_rank", 9):
        dev["headline"], dev["summary"] = cand["headline"], cand.get("summary")
        dev["headline_rank"] = cand["headline_rank"]
    dev["merged_from"] = dev.get("merged_from", 0) + 1


def dedupe(candidates: Iterable[Dict[str, Any]], *,
           stop: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """One development per event, with every source record underneath it.

    Seeds first — stored events, then news, then the vendors' own records —
    so an outside report anchors the event where one exists. Records that
    cannot seed (practitioner social, research) are tried last and attach to
    a development or are dropped.
    """
    stop = set(stop or ())
    prepared = [prepare_candidate(dict(c), stop) for c in candidates]
    prepared.sort(key=lambda c: (0 if c.get("seed") else 1,
                                 c.get("seed_rank", 5),
                                 -(c["day"].toordinal() if c.get("day") else 0)))
    developments: List[Dict[str, Any]] = []
    for cand in prepared:
        match = next((d for d in developments if same_development(d, cand)), None)
        if match is not None:
            _merge_into(match, cand)
            continue
        if not cand.get("seed"):
            continue
        dev = dict(cand)
        dev["evidence"] = list(cand.get("evidence") or [])
        dev["vendors"] = list(cand.get("vendors") or [])
        dev["words"], dev["names"] = set(cand["words"]), set(cand["names"])
        developments.append(dev)
    return developments


# ---------------------------------------------------------------------------
# Provenance and importance
# ---------------------------------------------------------------------------

PROVENANCE_STATES = ("vendor_source_only", "independently_reported",
                     "multiple_independent_sources", "measured")

PROVENANCE_LABELS = {
    "vendor_source_only": "Vendor source only",
    "independently_reported": "Also reported independently",
    "multiple_independent_sources": "Reported by multiple independent sources",
    # A count read from a platform, not a statement by anyone. Used for
    # headcount readings, and nothing a vendor said.
    "measured": "Measured, not reported",
}


def provenance_of(evidence: Sequence[Dict[str, Any]]) -> str:
    """Whose word an event rests on, from the records underneath it.

    Counts distinct independent sources — a publisher domain, a social
    account — not records. Six tweets from one account are one source. The
    result says another source reported the same thing; it does not say
    anyone checked it.
    """
    if any(e.get("voice") == "measured" for e in evidence):
        if all(e.get("voice") == "measured" for e in evidence):
            return "measured"
    independent = {
        e.get("key") or e.get("uri")
        for e in evidence if e.get("voice") in ("independent", "primary")}
    if len(independent) >= 2:
        return "multiple_independent_sources"
    if len(independent) == 1:
        return "independently_reported"
    return "vendor_source_only"


def importance_of(event_type: str, provenance: str) -> str:
    """High, medium or low, from the kind of event and who reported it."""
    rank = _TYPE_RANK.get(event_type, 99)
    if rank <= _TYPE_RANK["funding"]:
        return "high"
    if event_type in ("customer", "product_expansion", "partnership"):
        return ("high" if provenance == "multiple_independent_sources"
                else "medium")
    if event_type in ("product_launch", "executive_appointment"):
        return ("medium" if provenance in ("independently_reported",
                                            "multiple_independent_sources")
                else "low")
    return "low"


def why_it_matters(dev: Dict[str, Any]) -> str:
    """The market consequence of the event, in one bounded sentence."""
    kind = dev["event_type"]
    only_vendor = dev.get("provenance") == "vendor_source_only"
    if kind == "acquisition":
        return ("Consolidation: an existing company has bought its way into "
                "the category rather than building.")
    if kind == "market_exit":
        return "One fewer independent vendor competes in this category."
    if kind == "market_entry":
        return "A company from outside the tracked set has started competing here."
    if kind == "funding":
        return "This provides additional capital for expansion."
    if kind == "customer":
        return ("Evidence beyond product availability: a named customer or "
                "deployment" + (", so far on the vendor's word only."
                                if only_vendor else ", reported outside the vendor."))
    if kind == "product_expansion":
        if _RESPONSE.search(_full_text(dev)):
            return "The product moves from investigation toward taking action."
        return "An existing product now covers more than it did."
    if kind == "product_launch":
        return "A new product is on offer; availability, not adoption."
    if kind == "partnership":
        return ("An agreement to work with another company; it shows intent, "
                "not sales.")
    if kind == "executive_appointment":
        return "An observed change in who leads part of the company."
    if kind == "significant_hiring":
        n = (dev.get("attributes") or {}).get("openings")
        return (f"{n} open roles: " if n else "") + "an observed scaling signal."
    if kind == "headcount_change":
        pct = (dev.get("attributes") or {}).get("pct")
        return ((f"A measured {pct:+.0f}% change in LinkedIn headcount "
                 "between two readings." if isinstance(pct, (int, float))
                 else "A measured change in LinkedIn headcount."))
    return "An observed change in one vendor's position."


def finish(dev: Dict[str, Any]) -> Dict[str, Any]:
    """The public shape of a development, from a deduplicated candidate."""
    evidence = list(dev.get("evidence") or [])
    provenance = provenance_of(evidence)
    independent = {e.get("key") or e.get("uri") for e in evidence
                   if e.get("voice") in ("independent", "primary")}
    source_types = sorted({e.get("source_type") or "unknown" for e in evidence})
    day = dev.get("day")
    out = {
        "event_id": dev.get("key"),
        "stored_event_id": dev.get("stored_event_id"),
        "event_type": dev["event_type"],
        "event_type_label": EVENT_TYPES.get(dev["event_type"], dev["event_type"]),
        "date": day.isoformat() if day else None,
        "date_established": bool(day) and bool(dev.get("date_established", True)),
        "vendors": [{"brand_id": v.get("brand_id"), "vendor": v.get("vendor")}
                    for v in dev.get("vendors") or []],
        "headline": dev.get("headline") or "Untitled",
        "summary": (dev.get("summary") or "").strip(),
        "evidence": [{k: e.get(k) for k in
                      ("uri", "title", "source", "published", "voice",
                       "social", "source_type", "key", "author")}
                     for e in evidence],
        "evidence_count": len(evidence) or int(dev.get("evidence_count") or 0),
        "source_count": len({e.get("key") or e.get("uri") for e in evidence}),
        "independent_source_count": len(independent),
        "source_types": source_types,
        "provenance": provenance,
        "provenance_label": PROVENANCE_LABELS[provenance],
        "confidence": dev.get("confidence"),
        "attributes": dev.get("attributes") or {},
        "merged_records": int(dev.get("merged_from") or 0),
    }
    out["importance"] = importance_of(out["event_type"], provenance)
    out["why_it_matters"] = why_it_matters({**dev, "provenance": provenance})
    return out


def rank_key(dev: Dict[str, Any]) -> Tuple:
    """Importance first; within a band, what somebody else reported before
    what only the vendor said; then the kind of event, then the sources."""
    imp = {"high": 0, "medium": 1, "low": 2}.get(dev.get("importance"), 3)
    independent = int(dev.get("independent_source_count") or 0)
    return (imp, 0 if independent else 1,
            _TYPE_RANK.get(dev["event_type"], 99),
            -independent, -int(dev.get("source_count") or 0),
            dev.get("date") or "", dev.get("headline") or "")


# ---------------------------------------------------------------------------
# Reading the candidates from the database
# ---------------------------------------------------------------------------

def _host(uri: str) -> str:
    m = re.match(r"https?://([^/]+)", uri or "")
    host = (m.group(1) if m else "").lower()
    return host[4:] if host.startswith("www.") else host


def _evidence_from_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """One corpus record as an evidence item with an independence key."""
    kind = row.get("article_class")
    meta = row.get("social_meta") or {}
    source = row.get("news_source") or ""
    if kind == "social":
        owner = (row.get("vendors") or [{}])[0].get("brand_id")
        return {"uri": row["uri"], "title": row.get("title"),
                "source": "linkedin", "published": row.get("published"),
                "voice": "owned", "social": True, "source_type": "vendor",
                "key": f"owned:linkedin:{owner or _host(row['uri'])}"}
    if kind == "vendor":
        return {"uri": row["uri"], "title": row.get("title"),
                "source": _host(row["uri"]), "published": row.get("published"),
                "voice": "owned", "social": False, "source_type": "vendor",
                "key": f"owned:web:{_host(row['uri'])}"}
    if kind == "discussion":
        platform = (meta.get("platform") or source.split(":")[-1] or "social")
        author = meta.get("author") or _host(row["uri"])
        return {"uri": row["uri"], "title": row.get("title"),
                "source": platform, "published": row.get("published"),
                "voice": "independent", "social": True, "source_type": "social",
                "author": meta.get("author"),
                "key": f"social:{platform}:{author}".lower()}
    if kind == "research":
        return {"uri": row["uri"], "title": row.get("title"),
                "source": source, "published": row.get("published"),
                "voice": "independent", "social": False,
                "source_type": "research", "key": f"research:{_host(row['uri'])}"}
    return {"uri": row["uri"], "title": row.get("title"),
            "source": _host(row["uri"]) or source, "published": row.get("published"),
            "voice": "independent", "social": False, "source_type": "news",
            "key": f"domain:{_host(row['uri']) or source.lower()}"}


def _stored_candidates(conn, market_id: int, days: int
                       ) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """Stored entity events as candidates, and the URIs they already hold."""
    from app.services import market_findings as mfind
    from app.services import market_lists as ml

    rows: List[Dict[str, Any]] = []
    page = 1
    while True:
        try:
            batch = mfind.findings(conn, market_id, days=days, page=page,
                                   page_size=ml.MAX_PAGE_SIZE)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("stored events unavailable: %s", exc)
            break
        rows.extend(batch.get("data") or [])
        if len(batch.get("data") or []) < ml.MAX_PAGE_SIZE:
            break
        page += 1

    out: List[Dict[str, Any]] = []
    held: Set[str] = set()
    for f in rows:
        attrs = f.get("attributes") or {}
        # A changed page on the vendor's own site: we know something changed
        # and not what. Not a development.
        if attrs.get("page_kind") is not None:
            continue
        raw = (f.get("finding_type") or "").lower()
        # Job-listing spikes are rebuilt from the listings themselves below,
        # as one development per vendor rather than one per job function.
        if raw == "hiring_spike":
            if attrs.get("postings") is not None:
                continue
            kind = "executive_appointment"
            if not _SENIOR.search(f"{f.get('headline') or ''} "
                                  f"{f.get('summary') or ''}"):
                continue
        else:
            kind = _STORED_TYPE_MAP.get(raw)
        if not kind:
            continue
        text_value = f"{f.get('headline') or ''} {f.get('summary') or ''}"
        if is_noise(text_value):
            continue
        kind = _refine_product(kind, text_value)
        evidence = []
        for s in f.get("supporting") or []:
            if s.get("uri"):
                held.add(s["uri"])
            voice = s.get("voice") or "independent"
            evidence.append({
                "uri": s.get("uri"), "title": s.get("title"),
                "source": s.get("source"), "published": None,
                "voice": voice, "social": bool(s.get("social")),
                "source_type": ("vendor" if voice == "owned"
                                else "social" if s.get("social") else "news"),
                "key": s.get("key") or s.get("uri")})
        stamp = f.get("occurred_at") or f.get("first_observed_at")
        out.append({
            "key": f"event:{f['finding_id']}",
            "stored_event_id": f["finding_id"],
            "event_type": kind,
            "date": _parse_day(stamp).isoformat() if _parse_day(stamp) else None,
            "date_established": f.get("occurred_at") is not None,
            "vendors": [{"brand_id": v.get("brand_id"), "vendor": v.get("vendor")}
                        for v in f.get("vendors") or []],
            "headline": headline_of({"title": f.get("headline"),
                                     "summary": f.get("summary"),
                                     "vendors": f.get("vendors")}),
            "summary": f.get("summary") or "",
            "evidence": evidence,
            "evidence_count": f.get("evidence_count"),
            "confidence": f.get("confidence"),
            "attributes": attrs,
            "seed": True,
            "seed_rank": 0,
            "headline_rank": 1 if evidence and any(
                e["voice"] != "owned" for e in evidence) else 2,
        })
    return out, held


def _corpus_candidates(conn, market_id: int, days: int, held: Set[str]
                       ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]],
                                  int]:
    """The matched corpus as candidates, plus the discussion left over.

    Returns (candidates, discussion_rows, total_records). Records already
    attached to a stored event ride along as evidence for it rather than
    seeding a second development.
    """
    from app.services import market_corpus as mcorp
    from app.services.market_corpus import _iso_days_ago

    rows = mcorp.articles(conn, market_id, limit=5000, days=days)
    by_class: Dict[str, int] = {}
    for row in rows:
        by_class[row.get("article_class") or "other"] = \
            by_class.get(row.get("article_class") or "other", 0) + 1
    # Everything matched in the window, including the vendor posts the
    # review pass judged noise — the honest size of what was distilled.
    total = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m
          AND COALESCE(a.publication_date, a.submission_date) >= :since
    """), {"m": market_id, "since": _iso_days_ago(days)}).scalar() or len(rows)
    cands: List[Dict[str, Any]] = []
    discussion: List[Dict[str, Any]] = []
    for row in rows:
        text_value = _full_text(row)
        noisy = is_noise(text_value)
        kind = classify_record(row)
        evidence = _evidence_from_record(row)
        klass = row.get("article_class")
        if row["uri"] in held:
            # Already evidence for a stored event. The event candidate carries
            # it; nothing to add.
            continue
        if kind:
            cands.append({
                "key": f"corpus:{row['uri']}",
                "event_type": kind,
                "date": (row.get("published") or "")[:10] or None,
                "vendors": list(row.get("vendors") or []),
                "headline": headline_of(row),
                "summary": row.get("summary") or "",
                "evidence": [evidence],
                "seed": True,
                "seed_rank": 1 if klass == "news" else 3 if klass == "vendor" else 2,
                "headline_rank": 0 if klass == "news" else 3,
            })
            continue
        if klass in ("discussion", "research", "news", "vendor") and not noisy:
            # Can attach to a development it discusses, on the same rules;
            # otherwise it is discussion, and shown as such further down. A
            # news roundup that mentions a launch in its body is evidence
            # for that launch, not a launch of its own.
            attach_kind = classify_text(text_value)
            if attach_kind:
                cands.append({
                    "key": f"corpus:{row['uri']}",
                    "event_type": attach_kind,
                    "date": (row.get("published") or "")[:10] or None,
                    "vendors": list(row.get("vendors") or []),
                    "headline": headline_of(row),
                    "summary": row.get("summary") or "",
                    "evidence": [evidence],
                    "seed": False,
                })
            elif klass in ("discussion", "research"):
                discussion.append(row)
    return cands, discussion, total, by_class


def _hiring_candidates(conn, market_id: int, days: int) -> List[Dict[str, Any]]:
    from app.services import market_analysis as man

    try:
        hiring = man.hiring(conn, market_id, days=days)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("hiring analysis unavailable: %s", exc)
        return []
    out = []
    for v in hiring.get("by_vendor") or []:
        n = int(v.get("openings") or 0)
        if n < MIN_OPENINGS_FOR_HIRING:
            continue
        try:
            postings = man.job_postings(conn, market_id, v.get("brand_id"))
        except Exception:                                          # noqa: BLE001
            postings = []
        evidence = []
        for p in postings[:12]:
            evidence.append({
                "uri": p.get("url"), "title": p.get("title"),
                "source": p.get("source") or "job board", "published": None,
                "voice": "owned", "social": False, "source_type": "jobs",
                "key": f"jobs:{v.get('brand_id')}"})
        by_function = v.get("by_function") or {}
        mix = ", ".join(f"{k} {c}" for k, c in sorted(
            by_function.items(), key=lambda kv: -kv[1])[:3])
        out.append({
            "key": f"jobs:{v.get('brand_id')}",
            "event_type": "significant_hiring",
            "date": None,
            "date_established": False,
            "vendors": [{"brand_id": v.get("brand_id"), "vendor": v.get("vendor")}],
            "headline": f"{n} open roles observed",
            "summary": (f"{n} distinct open roles observed on job boards during "
                        f"the period" + (f" ({mix})." if mix else ".")),
            "evidence": evidence,
            "evidence_count": n,
            "attributes": {"openings": n, "by_function": by_function},
            "seed": True, "seed_rank": 4, "headline_rank": 2,
        })
    return out


def _headcount_candidates(conn, market: Dict[str, Any], days: int
                          ) -> List[Dict[str, Any]]:
    from app.services import market_publish as mp

    try:
        head = mp.headcount_market(conn, market)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("headcount unavailable: %s", exc)
        return []
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for m in head.get("movers") or []:
        pct = m.get("pct")
        if not isinstance(pct, (int, float)) or abs(pct) < MIN_HEADCOUNT_PCT:
            continue
        latest_at = m.get("latest_at")
        try:
            when = datetime.fromisoformat(latest_at) if latest_at else None
        except ValueError:
            when = None
        if when and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when and when < since:
            continue
        prev, now_n = int(m.get("previous") or 0), int(m.get("latest") or 0)
        out.append({
            "key": f"headcount:{m.get('brand_id')}",
            "event_type": "headcount_change",
            "date": latest_at[:10] if latest_at else None,
            "vendors": [{"brand_id": m.get("brand_id"), "vendor": m.get("vendor")}],
            "headline": (f"LinkedIn headcount "
                         f"{'up' if pct > 0 else 'down'} {abs(pct):.0f}%"),
            "summary": (f"LinkedIn reported {prev} staff on "
                        f"{(m.get('previous_at') or '')[:10]} and {now_n} on "
                        f"{(latest_at or '')[:10]}."),
            "evidence": [{"uri": None, "title": "LinkedIn company profile readings",
                          "source": "linkedin", "published": latest_at,
                          "voice": "measured", "social": False,
                          "source_type": "linkedin_profile",
                          "key": f"measured:linkedin:{m.get('brand_id')}"}],
            "evidence_count": 2,
            "attributes": {"pct": pct, "previous": prev, "latest": now_n},
            "seed": True, "seed_rank": 4, "headline_rank": 2,
        })
    return out


def material_developments(conn, market_id: int, days: int = 30, *,
                          market: Optional[Dict[str, Any]] = None
                          ) -> Dict[str, Any]:
    """Every material development in the period, once each, with its sources.

    Returns ``developments`` ranked by importance, the number of collected
    records they were distilled from, and the practitioner discussion that was
    neither material nor attached to anything, for the corpus view.
    """
    from app.services import market_corpus as mcorp

    market = market or {"id": market_id}
    stored, held = _stored_candidates(conn, market_id, days)
    corpus, discussion, total_records, by_class = _corpus_candidates(
        conn, market_id, days, held)
    jobs = _hiring_candidates(conn, market_id, days)
    heads = _headcount_candidates(conn, market, days)

    # The market's own phrases are shared by everything in it, so they never
    # count as a subject two records have in common.
    stop: Set[str] = set()
    try:
        for term in mcorp.corpus_terms(conn, market_id):
            for w in re.findall(r"[a-z][a-z0-9'\-]{2,}", (term or "").lower()):
                stop.add(w)
    except Exception:                                              # noqa: BLE001
        pass

    merged = dedupe(stored + corpus + jobs + heads, stop=stop)
    developments = [finish(d) for d in merged]
    developments.sort(key=rank_key)
    for i, dev in enumerate(developments, 1):
        dev["rank"] = i

    # Attached discussion records are evidence now, so the discussion list
    # only holds what nothing claimed.
    attached = {e.get("uri") for d in developments for e in d["evidence"]}
    discussion = [r for r in discussion if r["uri"] not in attached]

    return {
        "days": days,
        "developments": developments,
        "total": len(developments),
        "records_considered": total_records + len(stored),
        "collected_records": total_records,
        "records_by_class": by_class,
        "discussion": discussion,
        "types": [{"event_type": t, "label": EVENT_TYPES[t],
                   "n": sum(1 for d in developments if d["event_type"] == t)}
                  for t in EVENT_TYPES
                  if any(d["event_type"] == t for d in developments)],
    }


# ---------------------------------------------------------------------------
# Vendor observation states
# ---------------------------------------------------------------------------

OBSERVATION_STATES = ("material_change", "monitored_no_material_change",
                      "incomplete_coverage", "paused", "not_yet_collected")

OBSERVATION_LABELS = {
    "material_change": "with material observed change",
    "monitored_no_material_change": "monitored, no material change observed",
    "incomplete_coverage": "with incomplete observation",
    "paused": "paused",
    "not_yet_collected": "not yet collected",
}


def required_observation_sources() -> List[str]:
    """The sources that must have worked before "nothing changed" is a claim.

    The vendor's own LinkedIn page and its website, by default: between them
    they carry every announcement a vendor makes about itself. Configurable,
    because a market collected from different sources has a different bar.
    """
    raw = os.getenv("MARKET_REQUIRED_OBSERVATION_SOURCES",
                    "linkedin_company_post,vendor_web")
    return [s.strip() for s in raw.split(",") if s.strip()]


def observation_state_for(vendor: Dict[str, Any],
                          policies: Dict[str, Dict[str, Any]], *,
                          required: Sequence[str], now: datetime, days: int,
                          has_change: bool) -> Tuple[str, List[str]]:
    """One vendor's state and the reasons, from its collection policies.

    Pure, so the rules can be tested without a database. ``policies`` is keyed
    by source and holds the ``bw_entity_source_policies`` row.
    """
    if not vendor.get("collection_enabled", True):
        return "paused", ["collection is switched off for this vendor"]
    if has_change:
        return "material_change", []
    if not policies or not any(p.get("last_attempt_at") or p.get("last_success_at")
                               for p in policies.values()):
        return "not_yet_collected", ["no source has been collected yet"]
    reasons: List[str] = []
    period_start = now - timedelta(days=days)
    for source in required:
        p = policies.get(source)
        if p is None:
            reasons.append(f"{source}: not configured")
            continue
        if not p.get("eligible", True):
            reasons.append(f"{source}: "
                           f"{p.get('ineligible_reason') or 'no identifier'}")
            continue
        if not p.get("enabled", False):
            reasons.append(f"{source}: disabled")
            continue
        if (p.get("consecutive_failures") or 0) > 0:
            reasons.append(f"{source}: the last check failed")
            continue
        last = p.get("last_success_at")
        if not last:
            reasons.append(f"{source}: never collected")
            continue
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        cadence = int(p.get("cadence_seconds") or 86400)
        allowed_age = max(period_start, now - timedelta(seconds=cadence * 2))
        if last < allowed_age:
            reasons.append(f"{source}: not checked during the period")
    if reasons:
        return "incomplete_coverage", reasons
    return "monitored_no_material_change", []


def vendor_observation(conn, market_id: int, days: int = 30, *,
                       developments: Optional[Sequence[Dict[str, Any]]] = None
                       ) -> Dict[str, Any]:
    """Every vendor's observation state, and the counts by state."""
    if developments is None:
        developments = material_developments(conn, market_id, days)["developments"]
    changed = {v.get("brand_id") for d in developments for v in d["vendors"]
               if v.get("brand_id") is not None}
    changed_names = {(v.get("vendor") or "").lower() for d in developments
                     for v in d["vendors"]}

    vendors = [dict(r) for r in conn.execute(text("""
        SELECT b.id AS brand_id, b.display_name AS vendor,
               mb.collection_enabled
          FROM bw_market_brands mb JOIN bw_brands b ON b.id = mb.brand_id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
         ORDER BY b.display_name
    """), {"m": market_id}).mappings().all()]
    required = required_observation_sources()
    policies: Dict[int, Dict[str, Dict[str, Any]]] = {}
    for row in conn.execute(text("""
        SELECT p.brand_id, p.source, p.enabled, p.eligible, p.ineligible_reason,
               p.cadence_seconds, p.last_attempt_at, p.last_success_at,
               p.consecutive_failures
          FROM bw_entity_source_policies p
          JOIN bw_market_brands mb ON mb.brand_id = p.brand_id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
    """), {"m": market_id}).mappings().all():
        policies.setdefault(int(row["brand_id"]), {})[row["source"]] = dict(row)

    now = datetime.now(timezone.utc)
    out_vendors = []
    counts = {s: 0 for s in OBSERVATION_STATES}
    for v in vendors:
        has_change = (v["brand_id"] in changed
                      or (v["vendor"] or "").lower() in changed_names)
        state, reasons = observation_state_for(
            v, policies.get(int(v["brand_id"]), {}), required=required,
            now=now, days=days, has_change=has_change)
        counts[state] += 1
        out_vendors.append({"brand_id": v["brand_id"], "vendor": v["vendor"],
                            "state": state, "reasons": reasons})
    return {
        "days": days,
        "required_sources": required,
        "states": [{"state": s, "label": OBSERVATION_LABELS[s], "n": counts[s]}
                   for s in OBSERVATION_STATES],
        "counts": counts,
        "vendors": out_vendors,
        "total": len(vendors),
    }


# ---------------------------------------------------------------------------
# Source coverage — eligible, configured, attempted, successful
# ---------------------------------------------------------------------------

def source_coverage(conn, market_id: int) -> List[Dict[str, Any]]:
    """Per source: how many vendors could be read, were set up, were tried,
    and were read successfully. Four different numbers; a denominator alone
    hides which of them is short."""
    from app.services import market_metrics as mmet

    registry_total = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_brands
         WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).scalar() or 0
    rows = [dict(r) for r in conn.execute(text("""
        SELECT p.source,
               COUNT(*) FILTER (WHERE p.eligible) AS eligible,
               COUNT(*) FILTER (WHERE p.enabled AND p.eligible) AS configured,
               COUNT(*) FILTER (WHERE p.enabled AND p.eligible
                                  AND p.last_attempt_at IS NOT NULL) AS attempted,
               COUNT(*) FILTER (WHERE p.enabled AND p.eligible
                                  AND p.last_success_at IS NOT NULL) AS successful
          FROM bw_entity_source_policies p
          JOIN bw_market_brands mb ON mb.brand_id = p.brand_id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
         GROUP BY p.source
    """), {"m": market_id}).mappings().all()]
    by_source = {r["source"]: r for r in rows}
    names = {row["key"]: f'{row["content"]} ({row["platform"]})'
             for row in mmet.SOURCE_LEGEND}
    out = []
    for src in mmet.tracked_sources():
        r = by_source.get(src, {})
        try:
            st = mmet.collection_state(conn, market_id, src)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("collection state %s failed: %s", src, exc)
            st = {}
        out.append({
            "source": src,
            "name": names.get(src, src),
            "registry_total": int(registry_total),
            "eligible": int(r.get("eligible") or 0),
            "configured": int(r.get("configured") or 0),
            "attempted": int(r.get("attempted") or 0),
            "successful": int(r.get("successful") or 0),
            "state": st.get("state"),
            "state_label": mmet.STATE_LABELS.get(st.get("state"), st.get("state")),
            "note": st.get("state_detail_public") or st.get("state_detail") or "",
        })
    return out


# ---------------------------------------------------------------------------
# Distribution and concentration
# ---------------------------------------------------------------------------

def _share(part: float, whole: float) -> Optional[float]:
    return round(part / whole, 3) if whole else None


def distribution(developments: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Counts by kind, by vendor, by provenance, and how concentrated."""
    by_type: Dict[str, int] = {}
    by_vendor: Dict[str, int] = {}
    by_prov: Dict[str, int] = {s: 0 for s in PROVENANCE_STATES}
    for d in developments:
        by_type[d["event_type"]] = by_type.get(d["event_type"], 0) + 1
        by_prov[d["provenance"]] = by_prov.get(d["provenance"], 0) + 1
        for v in d["vendors"]:
            name = v.get("vendor") or "?"
            by_vendor[name] = by_vendor.get(name, 0) + 1
    total = len(developments)
    vendors_ranked = sorted(by_vendor.items(), key=lambda kv: (-kv[1], kv[0]))
    top3 = sum(n for _, n in vendors_ranked[:3])
    product = sum(by_type.get(t, 0) for t in PRODUCT_TYPES)
    adoption = sum(by_type.get(t, 0) for t in ADOPTION_TYPES)
    return {
        "total": total,
        "by_type": [{"event_type": t, "label": EVENT_TYPES[t], "n": by_type[t]}
                    for t in EVENT_TYPES if by_type.get(t)],
        "by_vendor": [{"vendor": v, "n": n} for v, n in vendors_ranked],
        "vendors_with_change": len(by_vendor),
        "top_vendor_share": _share(vendors_ranked[0][1], total) if vendors_ranked else None,
        "top3_share": _share(top3, total),
        "product": product,
        "adoption": adoption,
        "partnership": by_type.get("partnership", 0),
        "capital": sum(by_type.get(t, 0) for t in CAPITAL_TYPES),
        "by_provenance": by_prov,
        "vendor_only_share": _share(by_prov.get("vendor_source_only", 0), total),
        "independent_share": _share(
            by_prov.get("independently_reported", 0)
            + by_prov.get("multiple_independent_sources", 0), total),
    }


# ---------------------------------------------------------------------------
# Findings — templates with declared coverage requirements
# ---------------------------------------------------------------------------

#: Share of eligible vendors a source must have reached before a finding may
#: compare counts across the market.
MIN_COVERAGE_SHARE = float(os.getenv("MARKET_FINDING_MIN_COVERAGE", "0.5") or 0.5)
#: Share of the registry read before coverage counts as complete and no
#: caveat is printed.
COMPLETE_COVERAGE_SHARE = 0.9
#: Top-three share of a measure above which it is called concentrated.
CONCENTRATED_TOP3_SHARE = 0.5
#: Developments needed before their distribution is worth a sentence.
MIN_DEVELOPMENTS_FOR_MIX = 5
#: Open roles and hiring vendors needed before concentration is a finding.
MIN_OPENINGS_FOR_CONCENTRATION = 10
MIN_HIRING_VENDORS = 2
#: Top vendor's share of openings that counts as concentrated.
HIRING_CONCENTRATION_SHARE = 0.4

MAX_FINDINGS = 6


def _coverage_share(collection: Optional[Dict[str, Any]]) -> Optional[float]:
    cov = (collection or {}).get("coverage") or {}
    eligible = cov.get("eligible") or 0
    if not eligible:
        return None
    return (cov.get("successful") or 0) / eligible


def _coverage_note(collection: Optional[Dict[str, Any]], what: str,
                   registry_total: int) -> str:
    cov = (collection or {}).get("coverage") or {}
    successful, eligible = cov.get("successful") or 0, cov.get("eligible") or 0
    if not eligible:
        return f"No vendor is set up for {what}."
    return (f"{what[:1].upper()}{what[1:]} collected for {successful} of {eligible} "
            f"vendors we can read it from, out of {registry_total} in the "
            "registry.")


def _partial_posts_note(inputs: Dict[str, Any]) -> str:
    """One sentence for the reader when a finding counts announcements from
    only part of the registry. Empty when every vendor's channel was read:
    complete coverage needs no caveat, and printing one under every finding
    teaches the reader to skip them."""
    cov = (inputs.get("post_collection") or {}).get("coverage") or {}
    eligible = int(cov.get("eligible") or 0)
    read = int(cov.get("successful") or 0)
    registry_total = int(inputs.get("registry_total") or 0)
    # 83 of 84 is the registry. A caveat at that level is noise.
    if not eligible or not registry_total \
            or read / registry_total >= COMPLETE_COVERAGE_SHARE:
        return ""
    return (f"This covers the {read} of {registry_total} vendors whose "
            "announcements could be read, not the whole registry.")


def _devs_of(devs: Sequence[Dict[str, Any]], *types: str) -> List[Dict[str, Any]]:
    return [d for d in devs if d["event_type"] in types]


def _name_list(devs: Sequence[Dict[str, Any]], limit: int = 4) -> str:
    names: List[str] = []
    for d in devs:
        for v in d["vendors"]:
            n = v.get("vendor")
            if n and n not in names:
                names.append(n)
    shown = names[:limit]
    extra = len(names) - len(shown)
    return ", ".join(shown) + (f" and {extra} more" if extra > 0 else "")


def _pct(share: Optional[float]) -> str:
    return f"{share * 100:.0f}%" if share is not None else "—"


def _first_sentence(dev: Dict[str, Any]) -> str:
    """What happened, in the record's own words: the summary's first
    sentence, or the headline when there is no summary."""
    sentences = _sentences(dev.get("summary") or "")
    first = sentences[0] if sentences else ""
    if len(first) < 20 or "http" in first:
        first = dev.get("headline") or ""
    return _clip(first, 320)


def _finding(ident: str, headline: str, body: str, *, evidence: List[str],
             coverage: str, developments: Sequence[Dict[str, Any]] = (),
             basis: str = "observed") -> Dict[str, Any]:
    return {
        "id": ident,
        "headline": headline,
        "body": body,
        "evidence": evidence,
        "coverage": coverage,
        "basis": basis,
        "developments": [d["event_id"] for d in developments],
    }


def candidate_findings(inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Three to six findings from the counts, or fewer if the data is thin.

    ``inputs`` carries: ``developments``, ``distribution``, ``observation``,
    ``hiring`` (the hiring analysis), ``registry_total``, ``post_collection``
    and ``jobs_collection`` (``market_metrics.collection_state`` blocks),
    ``days``. Each template checks its own requirement and returns nothing
    when it is not met; a finding never rests on a figure whose coverage
    was too thin to support it.
    """
    devs: List[Dict[str, Any]] = list(inputs.get("developments") or [])
    dist = inputs.get("distribution") or distribution(devs)
    obs = inputs.get("observation") or {}
    hiring = inputs.get("hiring") or {}
    registry_total = int(inputs.get("registry_total") or 0)
    days = int(inputs.get("days") or 30)
    post_cov = inputs.get("post_collection")
    out: List[Dict[str, Any]] = []

    # 1. Consolidation and exits: any acquisition is a finding on its own.
    ownership = _devs_of(devs, "acquisition", "market_exit", "market_entry")
    if ownership:
        acq = _devs_of(ownership, "acquisition")
        lines = [f'{d["headline"]} ({d["event_type_label"].lower()}, '
                 f'{d["date"] or "date not established"}, '
                 f'{d["provenance_label"].lower()})' for d in ownership]
        if acq:
            head = (f"Consolidation observed: {len(acq)} acquisition"
                    f"{'s' if len(acq) != 1 else ''} in the period.")
        else:
            head = (f"{len(ownership)} change{'s' if len(ownership) != 1 else ''}"
                    " in who competes in this category.")
        told = " ".join(_first_sentence(d) for d in ownership[:2])
        out.append(_finding(
            "consolidation", head,
            told + (" An acquisition brings an existing company's customers "
                    "and distribution into the category." if acq else ""),
            evidence=lines,
            coverage=_partial_posts_note(inputs),
            developments=ownership))

    # 2. Capital: funding events in the period, never their absence.
    funding = _devs_of(devs, "funding")
    if funding:
        out.append(_finding(
            "capital",
            f"New capital observed for {_name_list(funding)}.",
            " ".join(_first_sentence(d) for d in funding[:3])
            + " This provides additional capital for expansion.",
            evidence=[f'{d["headline"]} ({d["date"] or "date not established"}, '
                      f'{d["provenance_label"].lower()})' for d in funding],
            coverage=_partial_posts_note(inputs),
            developments=funding))

    # 3. Product against customer evidence. Comparing counts across the
    # market needs the vendors' own channels to have been read for most of
    # them; below that the comparison describes our collection, not the
    # market, and the observed-mix finding below is used instead.
    product = _devs_of(devs, *PRODUCT_TYPES)
    customers = _devs_of(devs, "customer")
    post_share = _coverage_share(post_cov)
    if (len(product) + len(customers) >= MIN_DEVELOPMENTS_FOR_MIX
            and post_share is not None and post_share >= MIN_COVERAGE_SHARE):
        indep = [d for d in customers
                 if d["provenance"] != "vendor_source_only"]
        if len(product) > 2 * len(customers):
            head = "Product activity still exceeds customer evidence."
        elif len(customers) >= len(product):
            head = "Customer evidence keeps pace with product announcements."
        else:
            head = "Product announcements and customer evidence are close."
        out.append(_finding(
            "product_vs_customer", head,
            f"Vendors made {len(product)} product launch or expansion "
            f"announcement{'s' if len(product) != 1 else ''} against "
            f"{len(customers)} customer or deployment announcement"
            f"{'s' if len(customers) != 1 else ''} in the period"
            + ((f", {len(indep)} of which "
                f"{'has' if len(indep) == 1 else 'have'} been reported by "
                "anyone other than the vendor." if indep else
                ", none of which has been reported by anyone other than "
                "the vendor.") if customers else ".")
            + " These count announcements, not sales.",
            evidence=[f"Product: {_name_list(product, 5)}"]
            + ([f"Customers: {_name_list(customers, 5)}"] if customers else []),
            coverage=_partial_posts_note(inputs),
            developments=product + customers))
    elif len(devs) >= MIN_DEVELOPMENTS_FOR_MIX and dist.get("by_type"):
        top = dist["by_type"][0] if dist["by_type"] else None
        lead = max(dist["by_type"], key=lambda t: t["n"]) if dist["by_type"] else top
        if lead:
            out.append(_finding(
                "dominant_kind",
                f"{lead['label']} is the most common kind of observed change "
                f"({lead['n']} of {dist['total']} developments).",
                "Counts of the deduplicated developments we observed, by "
                "kind: " + ", ".join(f"{t['label'].lower()} {t['n']}"
                                     for t in dist["by_type"]) + ".",
                evidence=[f"{t['label']}: {_name_list(_devs_of(devs, t['event_type']), 3)}"
                          for t in dist["by_type"][:3]],
                coverage=(f"Announcements could be read for only "
                          f"{_pct(post_share)} of vendors, so this describes "
                          "what was observed rather than the whole market."
                          if post_share is not None else
                          "The vendors' own announcements were not read, so "
                          "this describes outside coverage only."),
                developments=devs))

    # 4. Customer adoption on its own, when the comparison above was not made.
    if customers and not any(f["id"] == "product_vs_customer" for f in out):
        indep = [d for d in customers if d["provenance"] != "vendor_source_only"]
        out.append(_finding(
            "adoption",
            f"Customer evidence observed for {_name_list(customers)}.",
            f"{len(customers)} customer or deployment announcement"
            f"{'s' if len(customers) != 1 else ''}, "
            f"{len(indep)} of them reported by anyone other than the vendor.",
            evidence=[f'{d["headline"]} ({d["provenance_label"].lower()})'
                      for d in customers[:5]],
            coverage=_partial_posts_note(inputs),
            developments=customers))

    # 5. Hiring concentration. Job data exists for few vendors, so this is
    # an observed signal and says so; it is not a market-wide ranking.
    by_vendor = hiring.get("by_vendor") or []
    openings = int(hiring.get("openings") or 0)
    if (openings >= MIN_OPENINGS_FOR_CONCENTRATION
            and len(by_vendor) >= MIN_HIRING_VENDORS):
        top, second = by_vendor[0], by_vendor[1]
        share = top["openings"] / openings if openings else 0
        if share >= HIRING_CONCENTRATION_SHARE:
            hire_devs = _devs_of(devs, "significant_hiring")
            out.append(_finding(
                "hiring_concentration",
                "Observed hiring is concentrated in a small number of vendors.",
                f"Of the {openings} open roles observed, {top['vendor']} "
                f"accounts for {top['openings']} ({_pct(share)}), with "
                f"{second['vendor']} the next largest at {second['openings']}.",
                evidence=[f"{v['vendor']}: {v['openings']} open roles"
                          for v in by_vendor[:4]],
                coverage=(f"Job listings exist for only {len(by_vendor)} of "
                          f"{registry_total} vendors, so this is an observed "
                          "hiring signal rather than a market-wide ranking."),
                developments=hire_devs))

    # 6. Concentration of material change across the registry.
    if len(devs) >= MIN_DEVELOPMENTS_FOR_MIX and dist.get("vendors_with_change"):
        counts = obs.get("counts") or {}
        quiet = counts.get("monitored_no_material_change", 0)
        top3 = dist["by_vendor"][:3]
        top3_txt = ", ".join(f"{v['vendor']} {v['n']}" for v in top3)
        out.append(_finding(
            "change_concentration",
            f"{dist['vendors_with_change']} of {registry_total} vendors showed "
            "material observed change.",
            f"{len(devs)} developments in {days} days. The three most active "
            f"vendors account for {_pct(dist['top3_share'])} of them "
            f"({top3_txt})."
            + (f" {quiet} vendors were watched and showed no material change."
               if quiet else ""),
            evidence=[f"{v['vendor']}: {v['n']} development"
                      f"{'s' if v['n'] != 1 else ''}" for v in dist["by_vendor"][:5]],
            coverage="",
            developments=devs))

    # 7. Whose word it all rests on.
    if len(devs) >= MIN_DEVELOPMENTS_FOR_MIX:
        prov = dist.get("by_provenance") or {}
        vendor_only = prov.get("vendor_source_only", 0)
        indep = (prov.get("independently_reported", 0)
                 + prov.get("multiple_independent_sources", 0))
        share = dist.get("vendor_only_share") or 0
        head = ("Most observed developments rest on the vendor's own word."
                if share >= 0.6 else
                "Independent reporting covers a minority of developments."
                if share >= 0.4 else
                "Most developments were reported by somebody other than the vendor.")
        out.append(_finding(
            "corroboration", head,
            f"{vendor_only} of {len(devs)} developments have only the "
            f"vendor's own announcement behind them; {indep} "
            f"{'was' if indep == 1 else 'were'} also reported by at least one "
            "outside source.",
            evidence=[f"{PROVENANCE_LABELS[s]}: {prov.get(s, 0)}"
                      for s in PROVENANCE_STATES if prov.get(s)],
            coverage="",
            developments=devs))

    return out[:MAX_FINDINGS]


# ---------------------------------------------------------------------------
# Synthesis — what the distribution says about the market
# ---------------------------------------------------------------------------

def _founding_cutoff(now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    return now.year - 3


def market_synthesis(inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Short bounded paragraphs, each with its heading and coverage line.

    ``inputs``: ``formation`` (the formation analysis), ``distribution``,
    ``developments``, ``hiring``, ``share_of_voice``, ``funding_by_vendor``
    (list of {vendor, musd}), ``registry_total``, ``post_collection``.
    """
    out: List[Dict[str, Any]] = []
    registry_total = int(inputs.get("registry_total") or 0)

    # Market formation. Only when we know the founding year for most of the
    # registry; a share of a third of the list is a share of nothing.
    formation = inputs.get("formation") or {}
    cov = formation.get("coverage") or {}
    with_year = int(cov.get("measured") or 0)
    cutoff = _founding_cutoff(inputs.get("now"))
    recent = sum(int(r.get("vendors") or 0)
                 for r in formation.get("founded_by_year") or []
                 if r.get("year") and int(r["year"]) >= cutoff)
    if with_year and registry_total and with_year / registry_total >= MIN_COVERAGE_SHARE:
        share = recent / with_year
        if share >= 0.5:
            text_value = (
                f"The tracked cohort is young: {recent} of the {with_year} "
                f"vendors with a known founding year were founded in {cutoff} "
                "or later. The category therefore still contains a large "
                "number of companies at an early stage of formation.")
        elif share <= 0.25:
            text_value = (
                f"The tracked cohort is mostly established: only {recent} of "
                f"the {with_year} vendors with a known founding year were "
                f"founded in {cutoff} or later.")
        else:
            text_value = (
                f"The tracked cohort mixes new and established companies: "
                f"{recent} of the {with_year} vendors with a known founding "
                f"year were founded in {cutoff} or later.")
        out.append({"heading": "Market formation", "text": text_value,
                    "coverage": (f"Founding year known for {with_year} of "
                                 f"{registry_total} vendors.")})

    # Product against adoption evidence.
    dist = inputs.get("distribution") or {}
    total = int(dist.get("total") or 0)
    if total >= MIN_DEVELOPMENTS_FOR_MIX:
        product, adoption = dist.get("product", 0), dist.get("adoption", 0)
        partners = dist.get("partnership", 0)
        if product > 2 * max(adoption, 1):
            lead = ("Observed activity is weighted toward building and "
                    "positioning rather than deployment evidence.")
        elif adoption >= product:
            lead = ("Observed activity carries as much deployment evidence "
                    "as product news.")
        else:
            lead = ("Observed activity splits between product news and "
                    "deployment evidence.")
        out.append({
            "heading": "Product versus adoption evidence",
            "text": (f"{lead} Of {total} developments, {product} were product "
                     f"launches or expansions, {partners} partnerships and "
                     f"{adoption} customer or deployment announcements."),
            "coverage": _partial_posts_note(inputs)})

    # Concentration: each measure is a top-three share, and the paragraph
    # says "concentrated" only when at least one clears the bar. Citing 16%
    # under a heading that says concentrated is the wrong finding.
    measures: List[Tuple[str, float]] = []
    hiring = inputs.get("hiring") or {}
    by_vendor = hiring.get("by_vendor") or []
    openings = int(hiring.get("openings") or 0)
    if openings >= MIN_OPENINGS_FOR_CONCENTRATION and by_vendor:
        top3 = sum(int(v["openings"]) for v in by_vendor[:3])
        measures.append((f"the three vendors hiring most hold "
                         f"{_pct(top3 / openings)} of {openings} open roles "
                         f"({by_vendor[0]['vendor']} alone "
                         f"{_pct(by_vendor[0]['openings'] / openings)})",
                         top3 / openings))
    sov = inputs.get("share_of_voice") or {}
    own_total = int(sov.get("own_total") or 0)
    loud = sorted((v for v in sov.get("vendors") or [] if v.get("own_posts")),
                  key=lambda v: -int(v["own_posts"]))
    if own_total >= 20 and loud:
        top3 = sum(int(v["own_posts"]) for v in loud[:3])
        measures.append((f"the three most active accounts published "
                         f"{_pct(top3 / own_total)} of {own_total} vendor posts",
                         top3 / own_total))
    funding_rows = [r for r in (inputs.get("funding_by_vendor") or [])
                    if r.get("musd")]
    if len(funding_rows) >= 5:
        total_musd = sum(float(r["musd"]) for r in funding_rows)
        top3 = sum(float(r["musd"]) for r in sorted(
            funding_rows, key=lambda r: -float(r["musd"]))[:3])
        measures.append((f"the three best-funded vendors hold "
                         f"{_pct(top3 / total_musd)} of disclosed funding",
                         top3 / total_musd))
    if total >= MIN_DEVELOPMENTS_FOR_MIX and dist.get("top3_share") is not None:
        measures.append((f"three vendors account for "
                         f"{_pct(dist['top3_share'])} of {total} developments",
                         dist["top3_share"]))
    lines = [m for m, _ in measures]
    concentrated = [m for m, share in measures if share >= CONCENTRATED_TOP3_SHARE]
    if lines:
        if concentrated:
            lead = ("Observed activity is concentrated in "
                    + ("; ".join(concentrated) + ". "))
            rest = [m for m in lines if m not in concentrated]
            text_value = lead + (("Elsewhere it is spread: " + "; ".join(rest)
                                  + ".") if rest else "")
        else:
            text_value = ("Observed activity is spread rather than "
                          "concentrated: " + "; ".join(lines) + ".")
        denominators = []
        if openings >= MIN_OPENINGS_FOR_CONCENTRATION and by_vendor:
            denominators.append(f"job listings exist for {len(by_vendor)} of "
                                f"{registry_total} vendors")
        if len(funding_rows) >= 5:
            denominators.append(f"funding is disclosed for {len(funding_rows)} "
                                f"of {registry_total}")
        partial = _partial_posts_note(inputs)
        out.append({
            "heading": "Concentration",
            "text": text_value,
            "coverage": (("; ".join(denominators).capitalize() + ". "
                          if denominators else "") + partial).strip()})
    return out


# ---------------------------------------------------------------------------
# The whole assessment, for the report
# ---------------------------------------------------------------------------

def assess(conn, market: Dict[str, Any], *, days: int = 30,
           allowed_brand_ids: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    """Everything the report's lead needs, computed once.

    ``allowed_brand_ids`` restricts a shared view to the vendors it may name.
    Applied before findings are generated, so a restricted reader's findings
    are computed from what they may see rather than filtered after the fact.
    """
    from app.services import market_analysis as man
    from app.services import market_entitlements as ent
    from app.services import market_metrics as mmet

    market_id = market["id"]
    material = material_developments(conn, market_id, days, market=market)
    devs = material["developments"]
    if allowed_brand_ids is not None:
        allowed = {int(b) for b in allowed_brand_ids}
        devs = [d for d in devs if all(
            v.get("brand_id") is None or int(v["brand_id"]) in allowed
            for v in d["vendors"]) and d["vendors"]]
        material["developments"] = devs
        material["total"] = len(devs)

    observation = vendor_observation(conn, market_id, days, developments=devs)
    if allowed_brand_ids is not None:
        observation["vendors"] = ent.filter_rows(
            observation["vendors"], allowed_brand_ids)

    def _safe(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("assessment input %s failed: %s",
                           getattr(fn, "__name__", fn), exc)
            return None

    hiring = _safe(man.hiring, conn, market_id, days=days) or {}
    formation = _safe(man.formation, conn, market_id) or {}
    sov = _safe(man.share_of_voice, conn, market_id, days=days) or {}
    if allowed_brand_ids is not None:
        hiring = ent.filter_rows(hiring, allowed_brand_ids) or {}
        hiring["openings"] = sum(int(v.get("openings") or 0)
                                 for v in hiring.get("by_vendor") or [])
        sov = ent.filter_rows(sov, allowed_brand_ids) or {}
    post_collection = _safe(mmet.collection_state, conn, market_id,
                            "linkedin_company_post")
    jobs_collection = _safe(mmet.collection_state, conn, market_id,
                            "linkedin_jobs")
    registry_total = int(observation.get("total") or 0)
    funding_by_vendor = [dict(r) for r in conn.execute(text("""
        SELECT b.id AS brand_id, b.display_name AS vendor,
               (mb.baseline->'funding_baseline'->>'total_musd')::numeric AS musd
          FROM bw_market_brands mb JOIN bw_brands b ON b.id = mb.brand_id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
           AND (mb.baseline->'funding_baseline'->>'total_musd') IS NOT NULL
    """), {"m": market_id}).mappings().all()]
    for r in funding_by_vendor:
        r["musd"] = float(r["musd"]) if r["musd"] is not None else None
    if allowed_brand_ids is not None:
        funding_by_vendor = ent.filter_rows(funding_by_vendor, allowed_brand_ids)

    dist = distribution(devs)
    inputs = {
        "days": days,
        "developments": devs,
        "distribution": dist,
        "observation": observation,
        "hiring": hiring,
        "formation": formation,
        "share_of_voice": sov,
        "funding_by_vendor": funding_by_vendor,
        "registry_total": registry_total,
        "post_collection": post_collection,
        "jobs_collection": jobs_collection,
        "records_by_class": material.get("records_by_class") or {},
    }
    findings = candidate_findings(inputs)
    synthesis = market_synthesis(inputs)

    main = devs[:MAIN_TABLE_LIMIT]
    other = devs[MAIN_TABLE_LIMIT:]
    return {
        "days": days,
        "developments": devs,
        "main_developments": main,
        "other_developments": other,
        "collected_records": material["collected_records"],
        "discussion": material["discussion"],
        "distribution": dist,
        "observation": observation,
        "findings": findings,
        "synthesis": synthesis,
        "source_coverage": _safe(source_coverage, conn, market_id) or [],
        "inputs": {"registry_total": registry_total,
                   "post_collection": post_collection,
                   "jobs_collection": jobs_collection},
    }
