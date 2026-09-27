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

import html
import json
import logging
import os
import re
import unicodedata
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
    # Last, so it ranks lowest. `importance_of` reads position, and a
    # published study is a real development that should never lead a report
    # over an acquisition or a funding round.
    ("research", "Research finding"),
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
#: Readings, not actions: counted apart from the developments.
SIGNAL_TYPES = frozenset({"significant_hiring", "headcount_change"})
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
    "research_finding": "research",
    "leadership_change": "executive_appointment",
    "headcount_change": "headcount_change", "layoff": "headcount_change",
}

#: How a reviewed vendor post's ``review_kind`` maps onto the canonical set.
_REVIEW_KIND_MAP = {
    "launch": "product_launch", "funding": "funding", "customer": "customer",
    "partnership": "partnership", "acquisition": "acquisition",
    "hiring": "executive_appointment",
    "research": "research",
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
        r"(to|as|for|over)\b"
        # A government award is a customer: "a $30M STRATFI award … to equip
        # the U.S. Space Force".
        r"|\bawarded\s+(an?\s+)?(\S+\s+){0,3}contract\b|\bstratfi\b|\bsbir\b",
        re.I)),
    # "Partner" alone is not a partnership: "How Prophet AI Protects
    # High-Exposure Partner Environments" is a blog post about customers'
    # partners.
    ("partnership", re.compile(
        r"\bpartner(s|ed|ing)?\s+with\b|\bpartnership\b|\bpartnering\b"
        r"|\b(technology|strategic|channel|integration|mssp|launch|design|"
        r"premier|preferred)\s+partner\b|\bnow\s+an?\s+(\w+\s+){0,3}partner\b"
        r"|\bjoins?\s+(the\s+)?(\S+\s+){0,4}(program|programme|ecosystem)\b"
        r"|\bnow\s+part\s+of\b|\balliance\b|\bteams?\s+up\s+with\b"
        r"|\bjoins?\s+forces\b|\breseller\b", re.I)),
    ("product_launch", re.compile(
        r"\blaunch(es|ed|ing)?\b|\bunveils?\b|\bdebuts?\b|\bintroduc(es|ed|ing)\b"
        r"|\bgenerally\s+available\b|\bnow\s+available\b|\breleases?\b"
        r"|\bnew\s+(feature|capability|module|workflow|integration)s?\b"
        r"|\bnow\s+supports?\b|\badds?\b|\bexpand(s|ed|ing)?\b|\bextends?\b"
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
    r"module|workflows?|integrations?)\b|\bexpand(s|ed|ing)?\b|\bextends?\b|\brolls?\s+"
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
    r"head\s+of|director|president|general\s+manager|founder|"
    # "Partner" as a title, not the word: "customer and partner experiences"
    # made a field-marketing hire an executive appointment.
    r"(managing|general|founding|operating)\s+partner\b|"
    # "Founding Channel Leader" (Mate), "to lead SOC team" (AiStrike).
    r"founding\s+(\w+\s+){0,2}(leader|lead|head)\b|\blead\s+of\b|"
    # "to lead SOC team", not "to lead the charge on customer experiences".
    r"\bto\s+lead\s+(the\s+|our\s+|its\s+)?(\w+\s+){0,2}(team|teams|function|"
    r"department|division|organi[sz]ation|operations|sales|engineering|marketing|"
    r"product|research|go-to-market|gtm|business|region|emea|americas|apac)\b|"
    r"\b\w+\s+leader\b)",
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
    r"|\b\d+\s?days?\s?challenge\b|\bbuilding\s+in\s+public\b"
    # Promotion aimed at consumers, which reaches this market only by
    # matching a vendor's name or one of its words in passing. A Bluesky
    # post offering a "Fun-Pass" under the code "7AI-N5AI" led the public
    # site's Social panel on 16 September 2026.
    r"|\blink\s+in\s+bio\b|\buse\s+(this\s+)?code\b|\bpromo\s+code\b"
    r"|\bdiscount\s+code\b|\bfollow\s+(for|4)\s+follow\b|\bdm\s+me\b"
    r"|\bgiveaway\b|\bairdrop\b|\bonlyfans\b|\bcreator\s+drops?\b"
    r"|\bfree\s*&\s*unlimited\b"
    # Somebody asking which job to take. Adjacent to the job-seeking lines
    # above and just as far from what this market tracks; two of these led
    # the Social panel the same day. Deliberately the shapes of a question
    # about one's own career — "any advice" alone also matches a
    # practitioner asking how to evaluate AI SOC tools, which is the kind of
    # post the panel exists for.
    r"|\brecently\s+graduated\b|\bcareer\s+advice\b|\bjob\s+offers?\b"
    r"|\bwhich\s+offer\b|\bshould\s+i\s+(take|accept|choose)\b"
    r"|\bbreak\s+into\s+(cyber|security)\b|\bresume\s+review\b"
    # A feed robot restating a vendor's headlines. Seven of these in ninety
    # days, all from one account, none of them anybody saying anything.
    r"|\bthe\s+latest\s+update\s+for\b"
    # Share-price chatter. A vendor's stock moving is not the vendor doing
    # something, and the market's own funding and acquisition news reaches
    # the report through the development path, not through this one.
    r"|\bstocks?\s+to\s+(buy|watch)\b|\bcyber\s?security\s+stocks\b"
    r"|\bprice\s+targets?\b|\bmarket\s+recap\b|\bearnings\s+call\b"
    # A sales approach. "What practitioners are saying" does not mean a
    # partner's campaign copy asking the reader to get in touch; the same
    # Microsoft Copilot line ran from three accounts in ninety days.
    r"|\bmessage\s+us\b|\bcontact\s+us\s+(today|to|for)\b"
    r"|\bbook\s+a\s+(demo|call)\b|\brequest\s+a\s+demo\b"
    r"|\bget\s+in\s+touch\s+to\b|\btalk\s+to\s+(us|our\s+team)\b"
    # Penny-stock promotion and chip news. "SoC" is a system-on-chip there:
    # six $MASK posts about an "Edge AI SoC" were the second most-discussed
    # subject on 23 September 2026.
    r"|\bpre-?market\s+news\b|\$[a-z]{2,5}\s*<\s*\$\d"
    r"|\bsoc\b.{0,40}\b(pre-?silicon|silicon|chipsets?|semiconductors?|"
    r"tape-?out|npu|emulation|fpgas?|rtl)\b|\b(pre-?silicon|silicon|chipsets?|"
    r"semiconductors?|tape-?out|npu|emulation|fpgas?|rtl|chips?)\b.{0,40}\bsoc\b"
    # A paid listing release: "SOC Automation Tool List 2026 includes …".
    r"|\b(tool|vendor|company|companies|solution)s?\s+list\s+20\d\d\s+includes\b"
    # A junior hire announced by an employer, and a learner's lab write-up.
    r"|\bjoins\s+our\s+team\s+as\s+(an?\s+)?(\w+\s+){0,3}(analyst|intern|associate)\b"
    r"|\bi\s+worked\s+through\b|\bletsdefend\b|\bhome\s?lab\b|\bcyberdefenders\b",
    re.I)

#: Headlines that are not a market event whatever kind the review gave them:
#: a search-engine listicle, a vendor stopping one attack for one customer, a
#: leaderboard, a training course. Read against the headline only, because
#: the words turn up in the body of real launches ("stopped threats").
_NOT_EVENT = re.compile(
    r"\b(top|best)\s+\d+\b|\b\d+\s+best\b|\balternatives\s+(to\b|in\s+20\d\d)"
    r"|\b(shut\s+down|blocked|stopped|contained|neutrali[sz]ed)\s+(\w+\s+){0,3}"
    r"(malicious|attacks?|executions?|intrusions?|ransomware|hackers?)\b"
    # "We helped another Coalition policyholder avoid a cyber attack!"
    r"|\bhelp(ed|s|ing)?\s+(\S+\s+){0,4}(avoid|prevent|stop|block|survive|thwart)\b"
    r"|\bleaderboard\b"
    # A download or follower count is a milestone, not a launch: "Virtus
    # passes 6K+ downloads" was filed as Imperum's product launch.
    r"|\b\d[\d,.]*\s?[km]?\+?\s+(downloads|stars|installs|followers|views)\b"
    r"|\bcertifi(ed|cation)\s+(\S+\s+){0,5}(program|programme|course)\b"
    # A credential and an open-letter signature are not events. The review
    # prompt says so, and still read UiPath's "Professional Certification"
    # as a launch and Cotool's signature on OpenAI's letter as a partnership.
    r"|\bcertification\b|\bcredential\b|\bopen\s+letter\b"
    # A marketplace listing is a place to buy, not a product or a partner.
    # The review files it as an award, and still sent Anvilogic's listing
    # as a partnership and Daylight's as a launch.
    r"|\b(listed|lists|listing|available|launch(es|ed)?|now\s+on|becomes?|"
    r"awardable)\b[^.]{0,60}\bmarketplaces?\b"
    # "Awardable" is cleared to bid, not a contract won (BlueDome on
    # Tradewinds).
    r"|\bawardable\b"
    # A preview is not a launch: "D3 Security to unveil Morpheus 2 on
    # September 16" duplicated the launch it announced.
    r"|\b(to|will)\s+(unveil|launch|debut|announce|showcase)\b"
    r"|\bset\s+to\s+(launch|unveil|debut)\b|\bcoming\s+soon\b|\bsneak\s+peek\b"
    # An advisor is not an executive appointment.
    r"|\badvis(or|ory\s+board)\b"
    r"|\bcall\s+(for|to)\s+collective\s+action\b",
    re.I)

#: Subreddits that are about getting a job rather than doing one. A post in
#: r/SecurityCareerAdvice is a career question however it is worded, and the
#: wording is what the text rules above have to work from — "20yo in
#: cybersecurity, which path could lead to a location-independent career?"
#: hits none of them. Named subreddits only: r/FreeITCourses reposts real
#: vendor news and r/learnwithcodelivly carries practitioners writing up
#: their own work, so neither is on this list.
_CAREER_SUBREDDITS = frozenset({
    "securitycareeradvice", "itcareerquestions", "cscareerquestions",
    "jobs", "forhire", "hiring", "jobhuntify", "uaejobseekers",
    "freshertechjobsindia", "resumeinminutes",
})

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
#: A newsletter's lead-in before the news: "In this issue, topics include
#: how…", "In our tenth edition, Andesite shares its new partnership…".
_NEWSLETTER_LEAD = re.compile(
    r"^in (?:this|our|the latest)(?: \w+)? (?:issue|edition),\s*"
    r"(?:topics include\s*(?:how\s+)?)?", re.I)

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
#: A product named in both headlines can be one launch across this many days.
PRODUCT_NAME_WINDOW_DAYS = 30
#: Days an attached report may precede the development it reports.
ATTACH_LEAD_DAYS = 2
#: Shared subject words needed to merge two records with no shared name,
#: and the share of both records' words they must make up.
MIN_SHARED_WORDS = 3
MIN_SHARED_RATIO = 0.25
#: A vendor's follow-up post about one release, within this many days, merges
#: on this many shared subject words whatever their share. Huntbase opened its
#: Hub on 22 Sep 2026 and posted "Two days later there are 162" on the 24th:
#: twelve words in common, but long posts, so under the ratio.
FOLLOW_UP_DAYS = 3
FOLLOW_UP_SHARED_WORDS = 10
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


#: A stock ticker as a social post writes one. Two *different* tickers in a
#: post makes it share-price commentary; one is how a stock-tracking account
#: tags a vendor's own announcement, which is a development like any other.
#: Counted as a set, so the same ticker in a title and again in the body does
#: not read as two.
_TICKER = re.compile(r"\$[A-Z]{1,5}\b")


def is_noise(text_value: str) -> bool:
    """A record the report should never lead with."""
    if _NOISE.search(text_value or ""):
        return True
    return len(set(_TICKER.findall(text_value or ""))) >= 2


def record_is_noise(record: Dict[str, Any]) -> bool:
    """Whether one corpus record is noise, reading its words and where it
    came from. :func:`is_noise` sees only the words, and a Reddit post's
    subreddit says more about it than any phrase in it does."""
    meta = record.get("social_meta")
    sub = ((meta or {}).get("subreddit") or "").strip().lower()
    if sub in _CAREER_SUBREDDITS:
        return True
    return is_noise(f"{record.get('title') or ''} {record.get('summary') or ''}")


#: A government contract or award, which reads like money raised and is a
#: customer: Method Security's "$30M STRATFI award" from the U.S. Space Force
#: was written up as "raised a $30M strategic round".
_CONTRACT = re.compile(
    r"\b(stratfi|sbir|tacfi|contract)\b"
    r"|\baward(ed|s)?\b.{0,60}\b(force|army|navy|department|agency|"
    r"government|dod|ministry)\b", re.I | re.S)
_RAISE = re.compile(r"\b(rais(es|ed|ing)|series\s+[a-e]|seed\s+round|"
                    r"investment\s+round|investors?|led\s+by)\b", re.I)


#: A post that looks back on something done earlier. Its date is when it was
#: posted: Sevii's module launched at Fal.Con and was dated 22 Sep from the
#: "Looking back at an outstanding CrowdStrike Fal.Con" recap.
_LOOKS_BACK = re.compile(
    r"^\W*(\w+(\s+\w+)?:\s*)?(looking\s+back|a\s+look\s+back|recap|"
    r"that'?s\s+a\s+wrap|that['’]s\s+a\s+wrap|what\s+a\s+week|last\s+week\b|"
    r"thank\s+you\s+to\s+everyone)", re.I)


#: A usage count: "passed 6K+ downloads", "10,000 stars on GitHub".
_USAGE_COUNT = re.compile(
    r"\b\d[\d,.]*\s?[km]?\+?\s+(downloads|stars|installs|users|followers|"
    r"views|pulls|forks)\b", re.I)

#: The opening of a post that announces something new.
_ANNOUNCES = re.compile(
    r"^\W*(\w+(\s+\w+)?:\s*)?(\W*)(introducing|announcing|meet\b|today\b|"
    r"(we['’]?re|we\s+are)\s+(excited|thrilled|proud|launching|releasing|"
    r"introducing|announcing)|(just|now)\s+(launched|released|available)|new\b)",
    re.I)


def milestone_post(kind: Optional[str], text_value: str) -> bool:
    """A launch reading of a post that reports a usage count and does not
    open by announcing anything: a milestone about an earlier launch.

    Read on the post, not the headline. On 27 Sep 2026 Sonnet 5, as the
    corrector, rewrote Imperum's "thank you for 6K+ downloads" post as
    "Imperum releases Imperum-CybersecurityLLM v1.0 on Hugging Face"; the
    count moved to the summary and the headline rule no longer saw it. The
    model was released on 24 Aug, in its own post.
    """
    if kind not in ("product_launch", "product_expansion"):
        return False
    text_value = text_value or ""
    return bool(_USAGE_COUNT.search(text_value)) \
        and not _ANNOUNCES.search(text_value.split(":", 1)[-1] if
                                  re.match(r"^[^:]{2,60}:\s", text_value) else text_value)


#: A post in a recurring series: a newsletter or weekly brief mentions the
#: company's earlier news, and the review read Tuskira's "Threat Brief: Week
#: of September 21" as a launch (and once as Help Net Security becoming a
#: customer). Read on the post's own title, not the rewrite.
_SERIES = re.compile(
    r"\b(threat\s+brief|newsletter|digest|round-?up|in\s+this\s+issue|"
    r"week\s+of\s+\w+\s+\d{1,2}|weekly\s+(brief|update|recap)|"
    r"(monthly|quarterly)\s+(update|recap|brief))\b", re.I)


def _refine_funding(kind: Optional[str], text_value: str) -> Optional[str]:
    if kind == "funding" and _CONTRACT.search(text_value or "") \
            and not _RAISE.search(text_value or ""):
        return "customer"
    return kind


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
    kind = record.get("article_class")
    # A vendor's own post or blog page the review has read: its reading
    # decides, and the noise rules judge only the headline the page will
    # show. Run over the whole post they turned real news away for a word in
    # passing: a partnership post that mentions the booth (Merlin Cyber and
    # Torq), a senior hire that ends "talk to us" (Vigilbase), a launch whose
    # opening line is "We block hackers" (Wirespeed Login Security).
    if kind == "social" or (kind == "vendor" and record.get("review_verdict")):
        # A post by a company that is no longer one of this market's vendors
        # (panaya dropped its peer tier on 22 Sep 2026) still carries a
        # review, and was still filed: Avo Automation's posts stayed on a
        # six-vendor page.
        if not record.get("vendors"):
            return None
        if record.get("review_verdict") != "signal":
            return None
        shown = checked_writing(record)[0] or headline_of(record)
        if is_noise(shown) or _NOT_EVENT.search(shown) \
                or _SERIES.search(headline_of(record)):
            return None
        mapped = _REVIEW_KIND_MAP.get((record.get("review_kind") or "").lower())
        # A contract reads as an award to both models: Method's $30M STRATFI
        # award from the U.S. Space Force was filed as recognition and hidden.
        if mapped is None and _CONTRACT.search(shown) and not _RAISE.search(shown):
            mapped = "customer"
        # Senior by the headline's own title: "President and Founder" of
        # somebody else's firm, further down the post, made an advisor an
        # executive appointment.
        if mapped == "executive_appointment" and not _SENIOR.search(shown):
            return None
        if mapped is None:
            return None
        refined = _refine_funding(_refine_product(mapped, text_value),
                                  f"{shown} {text_value}")
        if milestone_post(refined, text_value):
            return None
        return refined
    if record_is_noise(record) or _NOT_EVENT.search(headline_of(record)):
        return None
    if kind in ("discussion", "research"):
        return None
    # News and vendor-web pages: a development only when a tracked vendor is
    # named. A launch by a company we do not track is not one of the vendors'
    # moves, however well it matched the market's phrases.
    if not record.get("vendors"):
        return None
    return classify_text(text_value, title=record.get("title") or "")


#: What may follow a vendor's name in its page's name: "Crogl, Inc.".
_COMPANY_SUFFIXES = frozenset({
    "inc", "ltd", "llc", "corp", "co", "gmbh", "plc", "ag", "sa", "bv",
    "ai", "security", "labs", "technologies", "technology", "cyber", "io",
    "hq", "official"})


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
    # The short name a vendor posts under: "Mate: Mate is joining…" under
    # Mate Security, which then read "Mate Security: Mate: Mate is joining".
    for alias in sorted(_vendor_aliases(record), key=len, reverse=True):
        if headline.lower().startswith(f"{alias}:"):
            headline = headline[len(alias) + 1:].strip() or headline
            break
    # The company page's own name, which can run longer than the name we
    # track it under: "Crogl, Inc.: Your SOC depends on…" for Crogl. The
    # prefix is the page's name when it starts with the vendor's name and
    # ends at the first colon.
    page = re.match(r"^([^:\n]{1,40}):\s+", headline)
    if page:
        label = page.group(1).lower()
        for alias in _vendor_aliases(record):
            if not label.startswith(alias):
                continue
            # Only a company suffix or decoration may follow the name, or
            # "Mate Announce Gamebooks: the Control Flow…" loses its subject.
            rest = re.findall(r"[a-z]+", label[len(alias):])
            if all(w in _COMPANY_SUFFIXES for w in rest):
                headline = headline[page.end():].strip() or headline
                break
    for v in record.get("vendors") or []:
        name = (v.get("vendor") or "").strip()
        if not name:
            continue
        # A web page's title carries the site name after a bar.
        for sep in (" | ", " – ", " — ", " - "):
            if headline.lower().endswith(f"{sep}{name.lower()}"):
                headline = headline[:-(len(sep) + len(name))].strip() or headline
    lead = _NEWSLETTER_LEAD.match(headline)
    if lead and headline[lead.end():]:
        rest = headline[lead.end():]
        headline = rest[0].upper() + rest[1:]
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
    # A question is not news, and a three-word opener is a hook. "Simbian: The
    # best AI for your SOC?" and "Anvilogic: SAP kept Splunk." were both on the
    # page while the sentence carrying the news sat two lines down.
    #
    # Only when the headline is the body's own opening, which is what makes it
    # a post fragment rather than a title. A generated label such as "29 open
    # roles" is short and is not the start of anything, and replacing it with
    # its own explanatory sentence made the hiring section worse.
    hook = bool(headline) and bool(summary) and (
        headline.rstrip().endswith("?") or len(headline) < 30
    ) and summary.lower().startswith(headline.strip().lower()[:20])
    if (_JUNK_HEADLINE.search(headline) or not headline or truncated or hook) and summary:
        usable = [x for x in _sentences(summary)
                  if len(x) >= 12 and "http" not in x
                  and not (hook and x.strip().lower() == headline.strip().lower())]
        # The first sentence that says something; a four-word opener is a
        # hook, not a headline.
        first = next((x for x in usable if len(x) >= 40), usable[0] if usable else "")
        if first:
            headline = _clip(first, 160)
    return plain_letters(headline) or "Untitled"


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
        # A name takes its suffix after an apostrophe in Turkish and
        # elsewhere: "PARS’ı" and "SOCNova’nın" are PARS and SOCNova.
        if tok[:1].isupper():
            tok = re.split(r"['’]", tok)[0]
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
    letters = [t for t in _tokens(text_value) if t.isalpha()]
    shouting = bool(letters) and sum(t.isupper() for t in letters) * 2 > len(letters)
    for tok in _tokens(text_value):
        word = tok.strip(".'-&")
        low = word.lower()
        if len(low) < 3 or low in _COMMON or low in stop:
            continue
        # A three-letter acronym is a name (DXC, IBM) unless the post is
        # shouting, where every word is upper case.
        if word in _GENERIC_CAPS or (word.upper() == word and (
                len(word) <= 2 or (len(word) == 3 and shouting))):
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
    """The UTC day of a timestamp.

    The database session runs in Europe/Berlin, so a stored event time comes
    back as local time, and ``.date()`` on it moved every post made after
    22:00 UTC to the next day: Wirespeed's acquisition post of 17 Sep 22:02
    UTC showed as 18 Sep. The source's own date is UTC, and so is this.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    # A text timestamp with an offset ("2026-09-19 00:02:00+02:00") also has
    # to be read as an instant, not by its first ten characters.
    if len(raw) > 10:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc)
            return parsed.date()
        except ValueError:
            pass
    try:
        return date.fromisoformat(raw[:10])
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
    va, vb = _vendor_ids(a), _vendor_ids(b)
    if not _within(a.get("day"), b.get("day"), MERGE_WINDOW_DAYS):
        # One named customer's story with one vendor, told again weeks later,
        # is one item: Spectrum posted the SEP2 case study on 3 Sep and
        # re-shared the interview on 25 Sep.
        if (a["event_type"] == b["event_type"] == "customer" and (va & vb)
                and _within(a.get("day"), b.get("day"), PRODUCT_NAME_WINDOW_DAYS)
                and _customer_name(a) and _customer_name(a) == _customer_name(b)):
            return True
        # A product named in both headlines is one launch for longer than
        # the usual window: D3 announced Morpheus 2 on 28 August and posted
        # about "new improvements with Morpheus 2" on 17 September, and the
        # page listed two launches.
        return bool(
            _FAMILY.get(a["event_type"]) == "product" and (va & vb)
            and _within(a.get("day"), b.get("day"), PRODUCT_NAME_WINDOW_DAYS)
            and b.get("seed") and _product_in_both_titles(a, b, strict=True))
    # A report of an event cannot come out before the event. A record that
    # can only attach (practitioner social, a body-text mention in a news
    # piece) is a report; dated more than two days before the development it
    # is not a report of it, whatever words they share.
    if not b.get("seed") and a.get("day") and b.get("day") \
            and b["day"] < a["day"] - timedelta(days=ATTACH_LEAD_DAYS):
        return False
    if va and vb and not (va & vb):
        return False
    if _different_products(a, b):
        return False
    if _different_partners(a, b):
        return False
    shared_words = a["words"] & b["words"]
    if va & vb and b.get("seed") \
            and _within(a.get("day"), b.get("day"), FOLLOW_UP_DAYS) \
            and len(shared_words) >= FOLLOW_UP_SHARED_WORDS:
        return True
    # A vendor's own post and a launch days away are one event only when both headlines
    # name the same product. Shared words and names from the bodies are not
    # enough: a vendor describes every release in the same vocabulary. Mars
    # Security's Playbooks post (16 Sep 2026) joined its detection engine
    # launch (8 Sep) on "Real" from "Real-Time", and Intezer's revenue post
    # joined its Amplify Hub launch two weeks earlier.
    if (_FAMILY.get(a["event_type"]) == "product" and va & vb
            and (_vendor_only(a) or _vendor_only(b))
            and not _within(a.get("day"), b.get("day"), 1)
            and not _product_in_both_titles(a, b)):
        return False
    # One vendor's blog and LinkedIn post about one release, a day apart,
    # share the release's name in both headlines even when that name is an
    # acronym ("MCP support") that never counts as a subject elsewhere.
    if va & vb and _within(a.get("day"), b.get("day"), 1) \
            and a.get("title_keys", set()) & b.get("title_keys", set()):
        return True
    # A record that can only attach is evidence for the development, so it
    # has to be about the same thing: it names the development's vendor in
    # its headline or opening. Without this a string of tweets about the
    # Zscaler and Proofpoint launches (Sep 2026) attached to a Simbian post
    # on shared words and made it "reported by multiple independent sources".
    # A deal is the exception: a report of it may name only the other party
    # ("Cribl advances with AI SOC acquisition" for Cribl buying Radiant). A
    # partner such as CrowdStrike or Anthropic is not enough, because every
    # other post in the market names them.
    if not b.get("seed") and va and not _names_vendor_of(b, a):
        if a["event_type"] not in _DEAL_TYPES:
            return False
        headline_names = a["names"] & {t.lower() for t in _tokens(_title_of(a))}
        if not headline_names & (b["names"] | b["words"]):
            return False
    # A name on one side counts when the other side has the same word in
    # lower case: a vendor writes "Intezer Workflows", a publisher writes
    # "adds automated response workflows".
    shared_names = ((a["names"] & b["names"]) | (a["names"] & b["words"])
                    | (b["names"] & a["words"]))
    union = len(a["words"] | b["words"]) or 1
    short = min(len(a["words"]), len(b["words"])) < SHORT_RECORD_WORDS
    if va and vb and shared_names:
        # The same product in both headlines is the same event, however
        # long the publisher's summary runs: "introduce Intezer Workflows"
        # and "adds automated response workflows to AI SOC" were two rows
        # because the second had nine subject words and only one in common.
        if _product_in_both_titles(a, b):
            return True
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


def _next_name(title: str, name: str) -> Optional[str]:
    """The capitalised word right after ``name`` in ``title``, if any:
    "Sentinel" in "Introducing Virtus Sentinel"."""
    toks = _tokens(title)
    for i, tok in enumerate(toks[:-1]):
        if tok.lower() == name and toks[i + 1][:1].isupper():
            nxt = toks[i + 1].lower()
            return None if nxt in _COMMON else nxt
    return None


def _titles_name_pairs(a: Dict[str, Any], b: Dict[str, Any], strict: bool = False):
    """For each name both headlines carry, the word after it in each.
    ``strict`` counts only a word both records capitalise: "Program" in one
    headline and "program" in another are not one product."""
    shared = a["names"] & b["names"]
    if not strict:
        shared |= (a["names"] & b["words"]) | (b["names"] & a["words"])
    ta, tb = _title_of(a), _title_of(b)
    in_both = shared & {t.lower() for t in _tokens(ta)} & {t.lower() for t in _tokens(tb)}
    return [(name, _next_name(ta, name), _next_name(tb, name)) for name in in_both]


def _different_products(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Whether the headlines name two products of one family: "Virtus
    Sentinel" and "Virtus Cerebrum", which Imperum launched ten days apart
    and the page showed as one launch."""
    pairs = _titles_name_pairs(a, b)
    return bool(pairs) and all(na and nb and na != nb for _, na, nb in pairs)


def _customer_name(record: Dict[str, Any]) -> Optional[str]:
    """The customer the review named for a customer item, lowercased."""
    reading = (record.get("attributes") or {}).get("customer") or {}
    name = reading.get("name") if isinstance(reading, dict) else None
    return name.strip().lower() if isinstance(name, str) and name.strip() else None


def _vendor_only(record: Dict[str, Any]) -> bool:
    """Whether every source under the record is the vendor's own channel."""
    evidence = record.get("evidence") or []
    return bool(evidence) and all(e.get("voice") == "owned" for e in evidence)


def _headline_names(record: Dict[str, Any]) -> Set[str]:
    return record["names"] & {t.lower() for t in _tokens(_title_of(record))}


def _different_partners(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Whether two partnership records name different partners.

    Each headline names someone the other record never mentions, in its names
    or its words. AquilaI announced partnerships with Virus Rescuers and with
    Ampcus Cyber at one event two days apart; sharing "Aquila" and "GISEC"
    merged them into one item with one partner's headline and the other's
    date.
    """
    if a["event_type"] != "partnership" or b["event_type"] != "partnership":
        return False
    only_a = _headline_names(a) - b["names"] - b["words"]
    only_b = _headline_names(b) - a["names"] - a["words"]
    return bool(only_a) and bool(only_b)


def _product_in_both_titles(a: Dict[str, Any], b: Dict[str, Any],
                            strict: bool = False) -> bool:
    """Whether both headlines carry the same name, followed by the same
    word or by none, so it is the same product."""
    return any(not (na and nb and na != nb)
               for _, na, nb in _titles_name_pairs(a, b, strict))


#: Events whose report may name only the counterparty: the buyer, the investor.
_DEAL_TYPES = frozenset({"acquisition", "market_exit", "funding"})

#: Kinds of news a vendor's own channel also writes about when it happens to
#: somebody else.
THIRD_PARTY_KINDS = frozenset({"acquisition", "market_exit", "funding",
                               "partnership", "customer"})

_FIRST_PERSON = re.compile(r"\b(we|we're|we’re|we've|we’ve|our|us)\b", re.I)


def review_confidence(check: Optional[Dict[str, Any]]) -> Optional[float]:
    """How sure the checks are of a reviewed post: the lower of Jev's support
    for the headline and for the kind, or None when it was never checked.
    The featured item and the highlights need PROMINENT_MIN."""
    if not isinstance(check, dict) or "kind" not in check:
        return None
    head = float((check.get("headline") or {}).get("p_supports") or 0.0)
    kind = float((check.get("kind") or {}).get("p_drafted") or 0.0)
    return round(min(head, kind), 3)


def prominent_ok(dev: Dict[str, Any]) -> bool:
    """Whether a development may be the featured item or quoted in a
    highlight. An outside report, which the review does not write, may."""
    from app.services.market_post_review import PROMINENT_MIN

    conf = dev.get("review_confidence")
    return conf is None or conf >= PROMINENT_MIN


def checked_writing(record: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """The review's own headline and one-line summary for a post, each only
    when Jev found the post supports it (``market_post_review.passes``).

    The rules below this pick a sentence out of the vendor's own post, and a
    vendor's post is written to hook, not to report: "When Your Insider Risk
    Program Is Put to the Test". The review writes the item in our words and a
    second model checks it against the post.
    """
    from app.services.market_post_review import passes

    check = record.get("review_check")
    headline = record.get("review_headline")
    summary = record.get("review_summary")
    return (headline if headline and passes(check, "headline") else None,
            summary if summary and passes(check, "summary") else None)


def speaks_for_vendor(title: str, record: Dict[str, Any]) -> bool:
    """Whether a vendor's own headline is about the vendor: it names the
    vendor, or it speaks as the company ("we", "our")."""
    return bool(_FIRST_PERSON.search(title or "")) or _names_vendor_of(
        {"title": title or ""}, record)

#: How much of an attached record's body may name the vendor: the opening,
#: where a report says who it is about.
ATTACH_NAME_CHARS = 400


def _names_vendor_of(record: Dict[str, Any], dev: Dict[str, Any]) -> bool:
    """Whether ``record``'s headline or opening names one of ``dev``'s
    vendors, by full name or by the short name a vendor goes by."""
    hay = f"{_title_of(record)} {(record.get('summary') or '')[:ATTACH_NAME_CHARS]}"
    hay = unicodedata.normalize("NFKC", hay).lower()
    return any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", hay)
               for alias in _vendor_aliases(dev))


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
    # What a headline names, for records a day apart: its names, plus the
    # acronyms subject_names leaves out ("MCP").
    cand["title_keys"] = {
        t.lower() for t in _tokens(_title_of(cand))
        if t.lower() not in all_stop and t.lower() not in _COMMON
        and (t.lower() in cand["names"] or (t.isupper() and t.isalpha()))}
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
    # Only a record that could have seeded the development widens what it
    # matches. An attached report joining on the development's words and
    # then lending its own to the next match is how one Simbian post grew to
    # fifteen sources about other companies' launches.
    if cand.get("seed"):
        dev["words"] |= cand["words"]
        dev["names"] |= cand["names"]
    # The earliest *seed* record dates the event; a repost days later does
    # not, and an attached mention cannot move it either way.
    if cand.get("seed") and cand.get("day") and (
            dev.get("day") is None or cand["day"] < dev["day"]):
        dev["day"], dev["date"] = cand["day"], cand.get("date")
    # An outside headline beats a vendor's own wording, and any headline
    # beats one built from a post with no first sentence.
    # An English headline beats a foreign one, whatever the rank: SOCNova
    # posted PARS in Turkish and in English, and the page showed the Turkish.
    from app.utils.title_translation import looks_english
    dev_en = looks_english(dev.get("headline") or "")
    cand_en = looks_english(cand.get("headline") or "")
    if dev_en != cand_en:
        better = cand_en
    else:
        better = cand.get("headline_rank", 9) < dev.get("headline_rank", 9)
    if cand.get("seed") and better:
        dev["headline"], dev["summary"] = cand["headline"], cand.get("summary")
        dev["headline_rank"] = cand["headline_rank"]
        dev["dek"] = cand.get("dek") or dev.get("dek")
    elif not dev.get("dek") and cand.get("dek"):
        dev["dek"] = cand["dek"]
    # A reading the review pass made carries to the development it joins;
    # two readings combine (latest stage, named if any, quoted if any).
    cand_customer = (cand.get("attributes") or {}).get("customer")
    if cand_customer:
        dev["attributes"] = {**(dev.get("attributes") or {}),
                             "customer": combine_customer_readings(
                                 (dev.get("attributes") or {}).get("customer"),
                                 cand_customer)}
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
    "vendor_source_only": "Vendor sources only",
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


# ---------------------------------------------------------------------------
# Reading a customer-evidence item
# ---------------------------------------------------------------------------
#
# Whether the customer is named, who is speaking, and what stage the account
# describes. Who else reported it is the wrong test for a customer win: the
# realistic corroboration is the customer saying it, and that almost never
# reaches the press. So the sentence under a customer row is read off the item
# rather than off the provenance.

# An organisation name: capitalised words, allowing "of", "and", "&", "the"
# inside ("University of Montana", "J.B. Poindexter & Co").
_ORG = (r"(?P<org>[A-Z][\w&.'\u2019-]*(?:\s+(?:of|and|&|the|de|for)\s+)?"
        r"(?:\s*[A-Z][\w&.'\u2019-]*(?:\s+(?:of|and|&|de)\s+)?){0,5})")
_ROLE = (r"(?:CISO|CIO|CTO|CSO|CEO|CFO|VP|Vice\s+President|Head|Director|"
         r"Manager|Engineer|Lead|Analyst|Officer|Architect)")
_PERSON = r"[A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][\w'-]+"
# (pattern, a person from the customer is attached to the name)
_CUSTOMER_NAME_PATTERNS = [
    # "John Barrow, CISO at J.B. Poindexter & Co"; "Department Manager ... at X"
    (re.compile(_ROLE + r"[^.,;\n]{0,40}?\s+(?:at|of|from)\s+" + _ORG), True),
    # "Michael Shannon from Guardant Health"; "Erik Wille at Cabinetworks Group"
    (re.compile(_PERSON + r"\s+(?:from|at)\s+" + _ORG), True),
    # "what METCLOUD (Ian Vickers) had to say"
    (re.compile(r"\bwhat\s+" + _ORG + r"\s*(?:\([^)]*\))?\s+had\s+to\s+say"), True),
    # "The Air Force selected Crogl"; "Spencer Fane LLP receives"
    (re.compile(r"(?:^|[.!?]\s+|,\s+)(?:[Tt]he\s+)?" + _ORG
                + r"\s+(?:selected|chose|picked|adopted|deployed|uses|relies\s+on|"
                r"receives|receive|has\s+chosen|went\s+live|signed)\b"), False),
    # "For the University of Montana, ..."; "the team at MediaMarktSaturn".
    # Not "with Nadia Mejri, our Customer Success Director": a capitalised
    # run followed by a comma and a job title is a person.
    (re.compile(r"\b(?:[Ff]or|at|with|from|inside|within)\s+(?:the\s+)?" + _ORG
                + r"(?!\s*,\s+(?:our|their|its|the|a|an)?\s*(?:[A-Z]\w*\s+){0,3}"
                + _ROLE + r"\b)(?!\s*,\s+(?:our|my)\b)"
                + r"(?=\s*[,.:;(]|\s+(?:had|has|have|is|was|uses|used|relies|"
                r"chose|selected|during|receives|to)\b)"), False),
]
# Words that a capitalised run can be made of without naming anyone.
_NOT_AN_ORG = {
    "ai", "soc", "siem", "mdr", "xdr", "edr", "it", "the", "a", "an", "and",
    "of", "our", "your", "we", "us", "read", "watch", "see", "hear", "new",
    "customer", "customers", "case", "study", "ciso", "cio", "cto", "ceo",
    "linkedin", "black", "hat", "usa", "rsa", "rsac", "q1", "q2", "q3", "q4",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday", "sunday", "fortune",
    "enterprise", "security", "operations", "center", "centre", "challenge",
    "business", "review", "this", "that", "here", "why", "how", "what", "when",
}
_UNNAMED = re.compile(
    r"\b(?:one|a|an|another)\s+(?:of\s+our\s+)?(?:new\s+|large\s+|major\s+|"
    r"leading\s+|global\s+|regional\s+)?(?:customer|client|enterprise|"
    r"organi[sz]ation|company|bank|retailer|firm|institution|university|"
    r"hospital|agency|manufacturer|insurer)s?\b|\bFortune\s*\d+", re.I)
_EVALUATION = re.compile(
    r"\b(?:evaluat\w*|pilot\w*|proof[- ]of[- ]concept|POC|trial\w*|testing|"
    r"bake-?off)\b", re.I)
_CASE_STUDY = re.compile(
    r"\bcase\s+stud(?:y|ies)|customer\s+stor(?:y|ies)|success\s+stor(?:y|ies)"
    r"|read\s+the\s+(?:full\s+)?story\b", re.I)
_IN_USE = re.compile(
    r"\b(?:selected|chose|deployed|deploys|goes\s+live|went\s+live|relies\s+on|"
    r"rely\s+on|uses|using|since\s+adding|handles|runs\s+on|in\s+production|"
    r"scaling|dispositioning|anchor|adopted|rolled\s+out|protects|working\s+with"
    r"|primary\s+SIEM)\b", re.I)
_EXISTING = re.compile(r"\bbusiness\s+review|\bcustomer\s+visit|\bQBR\b", re.I)
_CUSTOMER_SPEAKS = re.compile(
    r"\bhear\s+directly\s+from|\bhad\s+to\s+say|\bin\s+(?:his|her|their)\s+"
    r"(?:own\s+)?words|\bdescribes\b|\btold\s+us|\bshares?\s+how\s+(?:his|her|their)"
    r"|\bspeaks?\s+about|\btalks?\s+about", re.I)


def _vendor_aliases(dev: Dict[str, Any]) -> set:
    out = set()
    for v in dev.get("vendors") or []:
        name = (v.get("vendor") or "").strip()
        if not name:
            continue
        out.add(name.lower())
        head = re.split(r"[\s(,]", name)[0].lower()
        if len(head) > 3:
            out.add(head)
    return out


_ABBREVIATION = re.compile(r"(?:[A-Z]\.)+|(?:Inc|Ltd|Co|Corp|LLC|Pty|GmbH|Bros)\.")


def _clean_org(raw: str, aliases: set) -> Optional[str]:
    # The name pattern lets a word carry a period ("J.B.", "Co."), so it can
    # run through the end of a sentence: "Cabinetworks Group. When". Stop at
    # the first word that ends a sentence rather than abbreviates.
    words = []
    for w in re.sub(r"\s+", " ", raw).strip().split(" "):
        if w.endswith(".") and not _ABBREVIATION.fullmatch(w):
            words.append(w[:-1])
            break
        words.append(w)
    org = " ".join(words).strip(" ,.;:()'\u2019")
    org = re.sub(r"\s+(?:of|and|&|the|de|for)$", "", org)
    if not org:
        return None
    words = org.split()
    if len(words) > 6:
        return None
    low = org.lower()
    if low in aliases or any(a and a in low.split() for a in aliases):
        return None
    if all(w.lower().strip("&.'") in _NOT_AN_ORG for w in words):
        return None
    return org


_STAGE_TEXT = {
    "in_use": "described in use",
    "evaluation": "evaluating it rather than running it",
    "case_study": "a published case study",
    "existing": "an existing customer",
    "unclear": "described as a customer",
}


def _coauthor_not_customer(name: Optional[str], text_value: str) -> bool:
    """Whether ``name`` appears in the post only as the case study's co-author
    or publisher. Kai's "We worked with Anthropic on a case study covering what
    Kai does inside a real enterprise environment" named Anthropic as the
    customer, and the review kept doing so after being told not to."""
    if not name or not text_value:
        return False
    n = re.escape(name.strip())
    return bool(re.search(
        rf"\b(worked|partnered|teamed\s+up)\s+with\s+{n}\s+on\s+(a|the|this)\s+"
        rf"(joint\s+)?case\s+study\b|\b{n}\s+(published|publishes|wrote|co-?wrote)\s+"
        rf"(a|the|this)\s+case\s+study\b|\bcase\s+study\s+(by|from|with)\s+{n}\b",
        text_value, re.I))


def reading_from_review(stored: Dict[str, Any],
                        as_of: Optional[str] = None,
                        text_value: Optional[str] = None) -> Dict[str, Any]:
    """The reading the post review stored, in the shape the report uses.

    The review pass read the whole post once with a model and recorded the
    customer's name (or that there is none), who speaks and the stage. That is
    the durable source; the rules below are the fallback for posts reviewed
    before the field existed. ``as_of`` is the post's date, kept so that when
    two posts about one customer merge, the later one's stage wins.
    """
    name = (stored.get("name") or "").strip() or None
    if _coauthor_not_customer(name, text_value or ""):
        name = None
    speaker = (stored.get("speaker") or "vendor") if name else "vendor"
    stage = stored.get("stage") or "unclear"
    return {
        "named": bool(name), "name": name,
        "voice": ("in the customer's own words" if speaker == "customer"
                  else "in the vendor's words"),
        "stage": _STAGE_TEXT.get(stage, _STAGE_TEXT["unclear"]),
        "as_of": (as_of or "")[:10] or None,
        "source": "review",
    }


def combine_customer_readings(a: Optional[Dict[str, Any]],
                              b: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """One reading for a development built from more than one post.

    The rule: the most recent post decides the stage, because a customer
    described as evaluating in June and in use in August is in use. The
    customer is named if any post names them. It is in the customer's own
    words if any post quotes them. Taking whichever post happened to come
    first was one model's call on one post; this is every post read together.
    """
    if not a:
        return b
    if not b:
        return a
    later, earlier = (b, a) if (b.get("as_of") or "") >= (a.get("as_of") or "") else (a, b)
    named = [r for r in (later, earlier) if r.get("named")]
    voices = {r.get("voice") for r in (a, b)}
    return {
        "named": bool(named),
        "name": named[0].get("name") if named else None,
        "voice": ("in the customer's own words"
                  if "in the customer's own words" in voices
                  else later.get("voice") or earlier.get("voice")),
        "stage": later.get("stage") or earlier.get("stage"),
        "as_of": later.get("as_of") or earlier.get("as_of"),
        "source": ("review" if a.get("source") == "review"
                   and b.get("source") == "review" else
                   (later.get("source") or earlier.get("source"))),
    }


def customer_reading(dev: Dict[str, Any]) -> Dict[str, Any]:
    """Named or unnamed, who speaks, and what stage, for one item.

    From the review pass where it read the post; from the rules below where
    it did not.
    """
    stored = (dev.get("attributes") or {}).get("customer")
    if isinstance(stored, dict) and stored.get("source") == "review":
        return stored
    return _customer_reading_by_rules(dev)


def _customer_reading_by_rules(dev: Dict[str, Any]) -> Dict[str, Any]:
    text_value = _full_text(dev)
    aliases = _vendor_aliases(dev)
    name = None
    person_attached = False
    for pat, attached in _CUSTOMER_NAME_PATTERNS:
        for m in pat.finditer(text_value):
            org = _clean_org(m.group("org"), aliases)
            if org:
                name, person_attached = org, attached
                break
        if name:
            break
    if _EVALUATION.search(text_value):
        stage = "evaluating it rather than running it"
    elif _CASE_STUDY.search(text_value):
        stage = "a published case study"
    elif _EXISTING.search(text_value):
        stage = "an existing customer"
    elif _IN_USE.search(text_value):
        stage = "described in use"
    else:
        stage = "described as a customer"
    if name and (person_attached or _CUSTOMER_SPEAKS.search(text_value)):
        voice = "in the customer's own words"
    else:
        voice = "in the vendor's words"
    return {"named": bool(name), "name": name, "voice": voice, "stage": stage,
            "unnamed_marker": bool(_UNNAMED.search(text_value)),
            "source": "rules"}


def _customer_named(dev: Dict[str, Any]) -> bool:
    reading = (dev.get("attributes") or {}).get("customer")
    if reading is None:
        reading = customer_reading(dev)
    return bool(reading.get("named"))


def _customer_listable(dev: Dict[str, Any]) -> bool:
    """Whether a customer item can be named in a highlight: the customer is
    named, or the vendor published a case study about it. "SEP2 runs 24/7 MDR
    across 70+ customers" is neither, and read as a customer announcement in
    the highlight's list."""
    if _customer_named(dev):
        return True
    reading = (dev.get("attributes") or {}).get("customer") or customer_reading(dev)
    return reading.get("stage") == _STAGE_TEXT["case_study"]


def customer_sentence(dev: Dict[str, Any]) -> str:
    """One plain sentence about the customer, only when it adds to the
    headline. The old template joined three fragments into "Live Oak Bank is
    named as a customer; it describes the product in use, in the vendor's
    words", which read as if the bank described the product, under a headline
    that already said the bank uses it."""
    r = customer_reading(dev)
    stage = r.get("stage")
    if r["named"]:
        name = r["name"]
        if r.get("voice") == "in the customer's own words":
            return f"Someone from {name} is quoted in the post."
        if stage == _STAGE_TEXT["evaluation"]:
            return f"{name} is evaluating the product, not yet running it."
        if stage == _STAGE_TEXT["case_study"]:
            return f"The vendor has published a case study about {name}."
        return ""
    if stage == _STAGE_TEXT["evaluation"]:
        return "The vendor does not name the customer, which is still evaluating the product."
    if stage == _STAGE_TEXT["case_study"]:
        return "The vendor has published a case study but does not name the customer."
    return "The vendor does not name the customer."


def _dev_vendor_name(dev: Dict[str, Any]) -> str:
    for v in dev.get("vendors") or []:
        if isinstance(v, dict):
            name = v.get("vendor") or v.get("name") or v.get("display_name")
            if name:
                return str(name)
    return "The vendor"


# "Why it matters" says only what the source itself says about the event:
# the product, the amount, the partner, the buyer. A sentence that would be
# the same for every event of a type is a glossary entry, not a reason, and
# it lives once in the Method section instead. When the source says nothing
# more than the headline, the cell is empty.
_LAUNCH_WORDS = re.compile(
    r"\b(introduc\w*|launch\w*|announc\w*|releas\w*|unveil\w*|now available|"
    r"general(?:ly)? availab\w*|debut\w*|roll\w* out|adds?|extends?|expands?|"
    r"now (?:covers|supports|includes))\b", re.I)
_PARTNER_WORDS = re.compile(
    r"\b(partner\w*|integrat\w*|alliance|teams? up|collaborat\w*|joins forces)\b", re.I)
_APPOINT_WORDS = re.compile(
    r"\b(joins|joined|appointed|appoints|named|hired|hires|welcomes|promoted)\b", re.I)
_MONEY = re.compile(r"([$€£])\s?(\d+(?:[.,]\d+)?)\s?(m|mm|million|b|bn|billion)\b", re.I)
_ROUND = re.compile(r"\b(pre[- ]seed|seed|series\s+[a-h]|strategic)\b", re.I)
_ACQUIRED_BY = re.compile(
    r"\b(?:acquired by|acquisition by|bought by|to be acquired by|sold to)\s+"
    r"([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})")
#: A vendor announcing its own sale: "Coalition, Inc. acquired us".
_ACQUIRED_US = re.compile(
    r"\b([A-Z][\w&.'-]*(?:,?\s+[A-Z][\w&.'-]*){0,3})\s+(?:has\s+)?acquired\s+"
    r"(?:us|our company)\b")
_ACQUIRES = re.compile(
    r"\b([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})\s+"
    r"(?:acquires|has acquired|to acquire|buys|completes (?:the |its )?acquisition of)\b")
_PAGE_CHANGED = re.compile(r"\bpage changed\b", re.I)


def _join_abbreviations(parts: Iterable[str]) -> List[str]:
    """Rejoin pieces a split cut after an abbreviation, not a sentence end.

    Splitting "Coalition, Inc. acquired us..." after "Inc." dropped the buyer,
    and the consolidation highlight read "acquired us for our ability to stop
    cyber threats" on Wirespeed's row, as if Wirespeed were the buyer. The
    extractor fixed the same cut in f416743b; this is its list.
    """
    from app.services.entity_event_extractors.owned_post import _ABBREV_END

    joined: List[str] = []
    for part in parts:
        part = (part or "").strip()
        if not part:
            continue
        if joined and _ABBREV_END.search(joined[-1]):
            joined[-1] = joined[-1] + " " + part
        else:
            joined.append(part)
    return joined


def _sentences(text_value: str) -> List[str]:
    out = []
    for raw in _join_abbreviations(re.split(r"(?<=[.!?])\s+|\n+", text_value or "")):
        sent = re.sub(r"^[^A-Za-z0-9$€£\"'(]+", "", raw)
        if len(sent) < 12 or sent.lower().startswith("http"):
            continue
        out.append(sent)
    return out


def _clip(sent: str, limit: int = 150) -> str:
    sent = sent.strip()
    if len(sent) <= limit:
        return sent if sent.endswith((".", "!", "?")) else sent + "."
    cut = sent[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def _detail_sentence(dev: Dict[str, Any], pattern) -> str:
    """The first sentence of the body that matches and is not the headline.
    The headline is already the row's "material change"; repeating it as the
    reason would say the same thing twice."""
    headline = re.sub(r"\s+", " ", _title_of(dev) or "").strip().lower().rstrip(".!?")
    for sent in _sentences(dev.get("summary") or ""):
        plain = re.sub(r"\s+", " ", sent).lower().rstrip(".!?")
        if not headline or (plain not in headline and headline not in plain):
            if pattern.search(sent):
                return _clip(sent)
    return ""


def _money(text_value: str) -> str:
    m = _MONEY.search(text_value or "")
    if not m:
        return ""
    sym, num, unit = m.group(1), m.group(2).replace(",", "."), m.group(3).lower()
    return f"{sym}{num}{'B' if unit.startswith('b') else 'M'}"


_HEADLINE_BUYER = re.compile(r"^([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,2})\b(?=.*\bacqui)", re.I)


def _acquirer(text_value: str, vendor: str, headline: str = "") -> str:
    m = _ACQUIRED_BY.search(text_value or "") or _ACQUIRED_US.search(text_value or "")
    if m:
        return m.group(1).strip()
    for m in _ACQUIRES.finditer(text_value or ""):
        name = m.group(1).strip()
        if name.lower() != (vendor or "").lower():
            return name
    # "Cribl Advances ... with New AI SOC Acquisition": the buyer leads a
    # headline about an acquisition when the vendor does not.
    m = _HEADLINE_BUYER.match(headline or "")
    if m and m.group(1).lower() != (vendor or "").lower() and "acqui" in (headline or "").lower():
        return m.group(1).split(" ")[0]
    return ""


def why_it_matters(dev: Dict[str, Any]) -> str:
    """What the source says about the event, in one bounded sentence — or
    nothing, when it says no more than the headline."""
    kind = dev["event_type"]
    text_value = _full_text(dev)
    if kind == "customer":
        return customer_sentence(dev)
    if kind in ("product_launch", "product_expansion"):
        if _PAGE_CHANGED.search(text_value):
            return ""
        return _detail_sentence(dev, _LAUNCH_WORDS)
    if kind == "funding":
        amount, rnd = _money(text_value), _ROUND.search(text_value)
        label = rnd.group(1).lower().replace("  ", " ") if rnd else ""
        # "$16.5M in total funding" is the running total, not this round.
        m = _MONEY.search(text_value or "")
        after = text_value[m.end():m.end() + 40].lower() if m else ""
        # "This brings our total funding raised to $29M": the total, said
        # before the figure (StrikeReady, Sep 2026, shown as "a $29M round").
        before = text_value[max(0, m.start() - 40):m.start()].lower() if m else ""
        if amount and (re.search(r"in total|total funding|total raised|to date|so far", after)
                       or re.search(r"\btotal\b|\bto date\b|\bbrings?\b", before)):
            return f"{amount} raised in total, the vendor says."
        if amount and label:
            return f"A {amount} {label} round."
        if amount:
            return f"A {amount} round."
        if label:
            return f"A {label} round; the amount is not stated."
        return ""
    if kind == "acquisition":
        buyer = _acquirer(text_value, _dev_vendor_name(dev), _title_of(dev))
        return f"Bought by {buyer}." if buyer else ""
    if kind == "partnership":
        # The headline names the partner; the body's next sentence usually
        # says what the partnership is for, which is the part worth adding.
        return (_detail_sentence(dev, _PARTNER_WORDS)
                or _detail_sentence(dev, re.compile(r"\b(?:will|to|for|so that|enabl\w*|us\w*)\b", re.I)))
    if kind == "executive_appointment":
        return _detail_sentence(dev, _APPOINT_WORDS)
    if kind in ("market_exit", "market_entry"):
        return ""
    if kind == "significant_hiring":
        n = (dev.get("attributes") or {}).get("openings")
        return f"{n} open roles." if n else "Open roles above the floor."
    if kind == "headcount_change":
        pct = (dev.get("attributes") or {}).get("pct")
        return ((f"LinkedIn headcount changed {pct:+.0f}% between the two dates "
                 "we collected it." if isinstance(pct, (int, float))
                 else "LinkedIn headcount changed between the two dates we collected it."))
    return "A change at one vendor."


# A summary is our excerpt of the source record, so choosing which of its
# sentences to keep is editing, not misquoting. These are the sentence shapes
# a marketing writer (human or model) uses as a drumroll: they carry no fact,
# and a card has no room for them. The 7ai/DXC case-study summary opened
# "What does agentic security look like at global scale? Ask DXC Technology."
# and pivoted on "The real story is what came next." (5 Sep 2026).
_DRUMROLL = re.compile(
    r"the (real|best|bigger|full) (story|part|news|picture)|"
    r"what (came|happened) next|here'?s the (thing|kicker)|"
    r"but that'?s not all|it gets (better|worse)|plot twist|"
    r"and (here'?s|that'?s) why", re.IGNORECASE)


def _sentence_is_slop(sent: str) -> bool:
    sent = sent.strip()
    if not sent:
        return True
    if sent.endswith("?"):          # a question in an excerpt is a hook
        return True
    if len(sent.split()) <= 4:      # "Ask DXC Technology." — a fragment
        return True
    if _DRUMROLL.search(sent):
        return True
    try:
        from humanize_mcp.detection import detect_ai_tells
        return bool(detect_ai_tells(sent))
    except ImportError:
        return False


def plain_summary(text: str) -> str:
    """The excerpt's sentences with the marketing drumroll left out."""
    if not text:
        return text
    sentences = _join_abbreviations(re.split(r"(?<=[.!?])\s+", text.strip()))
    kept = [s for s in sentences if not _sentence_is_slop(s)]
    return " ".join(kept)


#: Event type -> the extractor's marker kind for the sentence that states it.
_MARKER_KIND = {
    "product_launch": "launch", "product_expansion": "launch",
    "partnership": "partnership", "customer": "customer", "funding": "funding",
    "acquisition": "acquisition", "executive_appointment": "hiring",
}


_MONTHS_DAYS = frozenset("""
january february march april may june july august september october november
december monday tuesday wednesday thursday friday saturday sunday
""".split())
#: A headline pointing at something it does not name: "That's the gap we
#: built Exaforce to close."
_DEICTIC = re.compile(r"^(?:that['’]?s|that is|this is|here['’]?s|here is)\b", re.I)


def _mixed_case_names(sentence: str) -> Set[str]:
    """Capitalised words after the first that are not months, days or
    acronyms: the product and company names in a sentence."""
    toks = _tokens(sentence)[1:]
    return {t.lower() for t in toks
            if t[:1].isupper() and not t.isupper()
            and t.lower() not in _COMMON and t.lower() not in _MONTHS_DAYS}


def _names_any(sentence: str, aliases: Set[str]) -> bool:
    low = sentence.lower()
    return any(re.search(rf"(?<!\w){re.escape(a)}(?!\w)", low) for a in aliases)


def _is_hook(headline: str, aliases: Set[str]) -> bool:
    """Whether a vendor's headline is the post's opening hook rather than
    its news: it points at something unnamed, or it names neither the vendor
    nor any product and is short or names nothing at all."""
    h = (headline or "").strip()
    if not h:
        return False
    if _DEICTIC.search(h):
        return True
    if _names_any(h, aliases):
        return False
    # A long sentence is usually a description of the thing even when it
    # names nothing ("This week we unified Detection and Response into a
    # single Agents workspace…"); two names is a product ("Introducing
    # Virtus Sentinel").
    return len(h) < 60 and len(_mixed_case_names(h)) < 2


def announcing_headline(headline: str, summary: str, event_type: str,
                        vendors: Sequence[Dict[str, Any]] = (),
                        reason: Optional[str] = None) -> str:
    """The sentence that states the news, when the headline is the post's
    hook. "A coverage map tells you a rule exists." and "Most security
    platforms add a tab." were launch headlines; the product was named two
    sentences down. The first of the next few sentences that names the
    vendor or a product wins, one carrying the event's own verb first. A
    headline that is not a hook is kept."""
    from app.services.entity_event_extractors.owned_post import (
        _DEFERRING_OPENERS, _KIND_MARKERS)
    aliases = _vendor_aliases({"vendors": list(vendors or [])})
    if not summary or not _is_hook(headline, aliases):
        return headline
    markers = _KIND_MARKERS.get(_MARKER_KIND.get(event_type, ""), ())
    hook = (headline or "").strip().lower().rstrip(".!?")
    usable = []
    for sent in _sentences(plain_letters(summary))[:6]:
        sent = re.sub(r"^\W+", "", sent).strip()
        low = sent.lower()
        # A customer's quote is evidence, not a headline.
        if (len(sent) < 15 or "http" in low or low.rstrip(".!?") == hook
                or low.startswith(_DEFERRING_OPENERS)
                or sent[:1] in "\"“'‘" or re.search(r"\bsays?\b", low)
                or sent.upper() == sent):
            continue
        if _names_any(sent, aliases) or _mixed_case_names(sent):
            usable.append(sent)
    best = next((x for x in usable if any(m in x.lower() for m in markers)),
                usable[0] if usable else "")
    if best:
        return _clip(best, 160)
    # No sentence names the vendor or a product. The review pass's one-line
    # reading says what the post announced, in our words, and is a better
    # headline than a hook: "Vector autonomous red team agent shipped", not
    # "Someone relaxes a WAF rule during an incident."
    # Only for a launch whose headline names nothing. One that names a
    # product ("Announcing Nightwatch for detections.ai Enterprise.") says
    # more than the reading does, and for a customer story or a research post
    # the reading is a label ("Named customer with results"), not a headline.
    nameless = (event_type in PRODUCT_TYPES
                and not _names_any(headline or "", aliases)
                and not _mixed_case_names(headline or ""))
    reason = (reason or "").strip().rstrip(".")
    if nameless and reason and len(reason) >= 15:
        return reason[:1].upper() + reason[1:]
    return headline


def plain_letters(value: str) -> str:
    """Posts dressed in mathematical-bold letters (𝐁𝐅𝐒𝐈) as plain letters.
    Trademark signs go first, because NFKC would spell ™ out as "TM"."""
    value = re.sub(r"[™®©℠]", "", value or "")
    # Strikethrough and underline done with combining marks ("W̶e̶e̶k̶s̶"):
    # the marks go, the letters stay.
    value = re.sub(r"[\u0332\u0333\u0335-\u0338]", "", value)
    return unicodedata.normalize("NFKC", value)


def _named_headline(headline: str, vendors: Sequence[Dict[str, Any]]) -> str:
    """The headline with its vendor named, when it doesn't name one already.

    A development's headline is usually the source record's own sentence, and
    a vendor writing about its customer names the customer, not itself — the
    7ai case study about DXC read as a DXC announcement (5 Sep 2026). The
    byline names the vendor too, but small and after the fact.
    """
    names = [n for n in ((v.get("vendor") or "").strip()
                         for v in vendors or []) if n]
    if not names or not headline:
        return headline
    for name in names + sorted(_vendor_aliases({"vendors": vendors})):
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", headline, re.IGNORECASE):
            return headline
    # "AquilaI" for a headline that spells it "Aquila I".
    squashed = re.sub(r"[^a-z0-9]", "", headline.lower())
    if any(re.sub(r"[^a-z0-9]", "", n.lower()) in squashed for n in names):
        return headline
    # The short name the vendor posts under, too short to be an alias
    # everywhere: "Kai hires Thomas N." under Kai Security read "Kai
    # Security: Kai hires…".
    first = re.split(r"[\s(,]", names[0])[0]
    if first and re.match(rf"{re.escape(first)}\b", headline):
        return headline
    return f"{names[0]}: {headline}"


def _vendor_spelling(value: Optional[str], vendors: Sequence[Dict[str, Any]]) -> Optional[str]:
    """A vendor's name as the registry spells it, wherever the text spells it
    otherwise: the review wrote "AiSOC" and "Vigilbase" for AISOC and
    VigilBase, and the page showed both spellings side by side."""
    if not value:
        return value
    for v in vendors or []:
        name = re.sub(r"\s*\([^)]*\)\s*$", "", (v.get("vendor") or "")).strip()
        if len(name) < 3:
            continue
        value = re.sub(rf"(?<![\w.]){re.escape(name)}(?![\w])", name, value, flags=re.I)
    return value


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
        # "Strike48 (A Devo company)" is a note to the operator.
        "vendors": [{"brand_id": v.get("brand_id"),
                     "vendor": re.sub(r"\s*\([^)]*\)\s*$", "", v.get("vendor") or "")}
                    for v in dev.get("vendors") or []],
        "headline": _named_headline(_vendor_spelling(
            plain_letters(dev.get("headline") or "Untitled"), dev.get("vendors") or []),
            dev.get("vendors") or []),
        "summary": plain_summary(plain_letters((dev.get("summary") or "").strip())),
        # One checked sentence in our words, when the review wrote one.
        "dek": _vendor_spelling(dev.get("dek"), dev.get("vendors") or []),
        "review_confidence": dev.get("review_confidence"),
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
    if out["event_type"] == "customer":
        out["attributes"] = {**out["attributes"], "customer": customer_reading(dev)}
    out["why_it_matters"] = why_it_matters({**dev, "provenance": provenance})
    return out


def rank_key(dev: Dict[str, Any]) -> Tuple:
    """Importance first; within a band, what somebody else reported before
    what only the vendor said; then the kind of event, then the sources."""
    imp = {"high": 0, "medium": 1, "low": 2}.get(dev.get("importance"), 3)
    independent = int(dev.get("independent_source_count") or 0)
    # Newest first within a band: an equally ranked development from
    # yesterday beats one from three weeks ago. Until 2 September 2026 the
    # date tie-break sorted the ISO string ascending, so the OLDEST won and
    # the front page led its sections with weeks-old items. A development
    # with no date sorts after any dated one.
    day = _parse_day(dev.get("date"))
    return (imp, 0 if independent else 1,
            _TYPE_RANK.get(dev["event_type"], 99),
            -independent, -int(dev.get("source_count") or 0),
            -(day.toordinal() if day else 0),
            dev.get("headline") or "")


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
    host = _host(row["uri"]) or source.lower()
    from app.services.report_corpus import is_wire_host

    if is_wire_host(host) or is_wire_host(source):
        # A release on a wire is the company's own announcement.
        return {"uri": row["uri"], "title": row.get("title"),
                "source": host, "published": row.get("published"),
                "voice": "owned", "social": False, "source_type": "vendor",
                "key": f"owned:wire:{host}"}
    return {"uri": row["uri"], "title": row.get("title"),
            "source": _host(row["uri"]) or source, "published": row.get("published"),
            "voice": "independent", "social": False, "source_type": "news",
            "key": f"domain:{host}"}


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

    # What the review pass read off each customer post, by post. A stored
    # event holds its posts as evidence and the corpus path skips those, so
    # the reading has to be picked up here or it is lost.
    readings = {r[0]: (r[1], r[2]) for r in conn.execute(text("""
        SELECT ma.article_uri, ma.review_customer,
               COALESCE(a.publication_date, a.submission_date)
          FROM bw_market_articles ma
          LEFT JOIN articles a ON a.uri = ma.article_uri
         WHERE ma.market_id = :m AND ma.review_customer IS NOT NULL
    """), {"m": market_id}).fetchall()}
    # And its one-line reading of each post, the headline of last resort,
    # with the checked headline and summary it wrote.
    reasons: Dict[str, str] = {}
    writing: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    # The current reading of every reviewed post. A stored event keeps the
    # type its post was given when it was made; when a later review reads the
    # post differently, the event follows the post.
    readings_now: Dict[str, Tuple[str, str]] = {}
    confidence: Dict[str, float] = {}
    for r in conn.execute(text("""
        SELECT article_uri, review_verdict, review_kind, review_reason,
               review_headline, review_summary, review_check
          FROM bw_market_articles
         WHERE market_id = :m AND review_verdict IS NOT NULL
    """), {"m": market_id}).mappings():
        readings_now[r["article_uri"]] = (r["review_verdict"],
                                          (r["review_kind"] or "").lower())
        if r["review_verdict"] != "signal":
            continue
        if r["review_reason"]:
            reasons[r["article_uri"]] = r["review_reason"]
        checked = checked_writing(dict(r))
        if checked[0]:
            writing[r["article_uri"]] = checked
        conf = review_confidence(r["review_check"])
        if conf is not None:
            confidence[r["article_uri"]] = conf

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
        kind = _refine_funding(_refine_product(kind, text_value), text_value)
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
        if kind == "customer":
            combined = None
            for e in evidence:
                stored, when = readings.get(e.get("uri")) or (None, None)
                if isinstance(stored, dict):
                    combined = combine_customer_readings(
                        combined, reading_from_review(stored, as_of=str(when or ""),
                                                      text_value=text_value))
            if combined:
                attrs = {**attrs, "customer": combined}
        stamp = f.get("occurred_at") or f.get("first_observed_at")
        # A vendor's own announcement, read again: Legion's acceptance into
        # an OpenAI programme was stored as a partnership, and on a second
        # reading is an award, which is not a development at all.
        if attrs.get("announced_by") == "vendor":
            current = [readings_now[e["uri"]] for e in evidence
                       if e.get("voice") == "owned" and e.get("uri") in readings_now]
            if current:
                signals = [k for v, k in current if v == "signal"]
                if not signals:
                    continue
                reread = _REVIEW_KIND_MAP.get(signals[0])
                # A contract re-read as an award is still a customer (Method).
                # Read on the headline, as classify_record does, not the whole
                # post: Anvilogic's Snowflake Marketplace listing became a
                # customer story because the post says "Committed Capacity
                # contract" in passing.
                # The stored headline is only the fallback: it is often the
                # post's opening line, and here that line was the one that
                # said "contract".
                said = " ".join(h for h in (
                    (writing.get(e["uri"]) or (None, None))[0]
                    for e in evidence if e.get("voice") == "owned") if h) \
                    or (f.get("headline") or "")
                if reread is None and _CONTRACT.search(said) \
                        and not _RAISE.search(said):
                    reread = "customer"
                if reread is None:
                    continue
                if _FAMILY.get(reread) != _FAMILY.get(kind):
                    kind = _refine_funding(_refine_product(reread, text_value),
                                           text_value)
        written, dek = next((writing[e["uri"]] for e in evidence
                             if e.get("uri") in writing), (None, None))
        original = announcing_headline(
            headline_of({"title": f.get("headline"),
                         "summary": f.get("summary"),
                         "vendors": f.get("vendors")}),
            f.get("summary") or "", kind, f.get("vendors") or [],
            reason=next((reasons[e["uri"]] for e in evidence
                         if e.get("uri") in reasons), None))
        headline = written or original
        # A hire is an executive appointment by the title in the headline,
        # not by a word anywhere in the post ("here to lead the charge on
        # unforgettable customer and partner experiences").
        if kind == "executive_appointment" and not _SENIOR.search(headline):
            continue
        # The noise rules judge the headline the page will show, and the
        # whole post only when the review wrote none: a word in passing
        # ("booth", "talk to us") turned real news away. The shown headline
        # can also be a sentence the stored title was not: "…has passed 6K+
        # downloads" came from Imperum's post body.
        if is_noise(headline if written else text_value) \
                or _NOT_EVENT.search(headline) \
                or milestone_post(kind, text_value) \
                or any(_SERIES.search(e.get("title") or "") for e in evidence
                       if e.get("voice") == "owned"):
            continue
        out.append({
            "key": f"event:{f['finding_id']}",
            "stored_event_id": f["finding_id"],
            "event_type": kind,
            "date": _parse_day(stamp).isoformat() if _parse_day(stamp) else None,
            # The stored title is the announcing sentence, so the post's own
            # opening line is read from its evidence ("Sevii: Looking back at
            # an outstanding CrowdStrike Fal.Con").
            "date_established": (f.get("occurred_at") is not None
                                 and not any(_LOOKS_BACK.search(x or "") for x in
                                             [f.get("headline")] + [
                                                 e.get("title") for e in evidence
                                                 if e.get("voice") == "owned"])),
            "vendors": [{"brand_id": v.get("brand_id"), "vendor": v.get("vendor")}
                        for v in f.get("vendors") or []],
            "headline": headline,
            "review_confidence": min((confidence[e["uri"]] for e in evidence
                                      if e.get("uri") in confidence), default=None),
            # Deduplication reads the post's own title, not the rewrite: two
            # headlines written for one listing need not share the words
            # that match them.
            "title": original,
            "dek": dek,
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
    wider: List[Dict[str, Any]] = []
    wider_unchecked: List[Dict[str, Any]] = []
    for row in rows:
        text_value = _full_text(row)
        noisy = record_is_noise(row)
        kind = classify_record(row)
        evidence = _evidence_from_record(row)
        klass = row.get("article_class")
        if klass in ("news", "discussion") and not row.get("vendors") and not noisy:
            wide = _wider_candidate(row, evidence)
            if wide and wide.get("unchecked"):
                wider_unchecked.append(wide)
            elif wide:
                wider.append(wide)
        if row["uri"] in held:
            # Already evidence for a stored event. The event candidate carries
            # it; nothing to add.
            continue
        # A press release names its partners in the body; "CrowdStrike
        # Expands Project QuiltWorks" listed Artemis and became an Artemis
        # product expansion. News seeds only for a vendor its headline names;
        # otherwise it is a report that can attach to that vendor's own item.
        if kind and klass == "news" and row.get("vendors") and not _names_vendor_of(
                {"title": row.get("title") or ""}, row):
            kind = None
        # A vendor's blog writes about other companies' deals too: D3's post
        # "Cribl Just Acquired Radiant Security's AI SOC Technology" is D3's
        # commentary, not D3's acquisition.
        if kind in THIRD_PARTY_KINDS and klass == "vendor" \
                and not speaks_for_vendor(checked_writing(row)[0]
                                          or row.get("title") or "", row):
            kind = None
        headline = None
        written, dek = (None, None) if klass == "news" else checked_writing(row)
        # A vendor blog post about a customer it does not name is a story, not
        # news: Nebulock's "When Your Insider Risk Program Is Put to the Test".
        if kind == "customer" and klass == "vendor" \
                and not (row.get("review_customer") or {}).get("name"):
            kind = None
        ruled = None
        if kind:
            ruled = (headline_of(row) if klass == "news" else
                     announcing_headline(headline_of(row),
                                         row.get("summary") or "", kind,
                                         row.get("vendors") or [],
                                         reason=row.get("review_reason")))
            headline = written or ruled
            # The shown headline can be a body sentence the title was not.
            if _NOT_EVENT.search(headline) or milestone_post(
                    kind, f"{row.get('title') or ''} {row.get('summary') or ''}"):
                kind = None
        if kind:
            attrs: Dict[str, Any] = {}
            if kind == "customer" and isinstance(row.get("review_customer"), dict):
                attrs["customer"] = reading_from_review(
                    row["review_customer"], as_of=str(row.get("published") or ""),
                    text_value=text_value)
            cands.append({
                "key": f"corpus:{row['uri']}",
                "event_type": kind,
                "date": (row.get("published") or "")[:10] or None,
                "vendors": list(row.get("vendors") or []),
                "headline": headline,
                "review_confidence": (review_confidence(row.get("review_check"))
                                      if klass != "news" else None),
                "title": ruled,
                # A post looking back ("Looking back at Fal.Con…") is dated
                # by when it was posted, not when the thing happened.
                "date_established": not _LOOKS_BACK.search(headline_of(row)),
                "dek": dek,
                "summary": row.get("summary") or "",
                "evidence": [evidence],
                "attributes": attrs,
                "seed": True,
                "seed_rank": 1 if klass == "news" else 3 if klass == "vendor" else 2,
                # A checked headline in our words beats the vendor's own
                # sentence, and an outside publisher's headline beats both.
                "headline_rank": 0 if klass == "news" else 2 if written else 3,
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
    return cands, discussion, total, by_class, wider, wider_unchecked


#: What a company outside the vendor list can do that belongs on the page.
WIDER_TYPES = frozenset({"acquisition", "market_exit", "funding",
                         "product_launch", "product_expansion", "partnership"})
#: The company a news headline leads with, before the verb saying what it did.
#: Names joined by "and" or "&" are allowed ("Cisco & NVIDIA bring…"); the
#: first one is the company the item is filed under.
_LEAD_COMPANY = re.compile(
    r"^([A-Z][\w.'’-]*(?:\s+(?:[A-Z][\w.'’-]*|AI|&|and)){0,3}?)\s+(?i:launches|"
    r"announces|unveils|introduces|debuts|releases|adds|added|expands|expanded|"
    r"is\s+expanding|acquires|to\s+acquire|buys|has\s+acquired|completes|raises|"
    r"secures|partners|teams\s+up|rolls\s+out|brings|bring|taps|bets|"
    r"has\s+launched|launched)\b")

#: What a shared headline carries before the company: a poster's handle, an
#: emoji, "Exciting news:".
_LEAD_IN = re.compile(
    r"^(?:@[\w.-]+:\s*)?[^\w(]*(?:(?:exciting|big|breaking|great|huge)\s+news|"
    r"icymi|breaking|news|update|announcement|just\s+announced)\s*[:!\-–—]\s*",
    re.I)


def _lead_title(title: str) -> str:
    """The headline as the lead-company match should read it.

    "🔐 Cisco &amp; NVIDIA bring Splunk AI…" failed on the emoji and the
    escaped ampersand, and "Exciting news: Cisco announces intent to acquire
    WideField Security" on its lead-in, so Splunk's week at .conf reached the
    page only as a subject under "Being discussed".
    """
    value = html.unescape(title or "").strip()
    value = re.sub(r"^@[\w.-]+:\s*", "", value)
    # Leading hashtags: "#Cybersecurity KDDI Expands…" made the company
    # "Cybersecurity KDDI".
    value = re.sub(r"^(?:\s*#\w+)+\s+", "", value)
    value = _LEAD_IN.sub("", value)
    return re.sub(r"^[^\w(]+", "", value).strip()


def _merge_by_company(devs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One item per company and kind of event within the merge window. The
    usual rules need a shared name besides the company's, and two headlines
    about Zscaler's Agentic SOC five days apart shared none."""
    out: List[Dict[str, Any]] = []
    for dev in sorted(devs, key=lambda d: d.get("day") or date.min):
        match = next((o for o in out
                      if _vendor_ids(o) == _vendor_ids(dev)
                      and _FAMILY.get(o["event_type"]) == _FAMILY.get(dev["event_type"])
                      and _within(o.get("day"), dev.get("day"), MERGE_WINDOW_DAYS)), None)
        if match is None:
            out.append(dev)
        else:
            _merge_into(match, {**dev, "seed": True})
    return out


def _wider_candidate(row: Dict[str, Any], evidence: Dict[str, Any]
                     ) -> Optional[Dict[str, Any]]:
    """A news report of a deal or launch by a company we do not track, as a
    candidate attributed to the company its headline leads with.

    Zscaler's Agentic SOC, Proofpoint's agent built with OpenAI and Quorum
    Cyber buying Ontinue were all collected in September 2026 and all
    dropped, because only the tracked vendors' moves reached the page.
    """
    title = row.get("title") or ""
    if _NOT_EVENT.search(title):
        return None
    lead_title = _lead_title(title)
    kind = classify_text(_full_text(row), title=lead_title)
    lead = _LEAD_COMPANY.match(lead_title)
    if kind not in WIDER_TYPES or not lead:
        return None
    company = re.split(r"\s+(?:and|&)\s+", lead.group(1).strip())[0]
    company = re.sub(r"['’]s$", "", company)
    # The company's own site, which has no registry entry for a company we do
    # not track: atos.net made "Atos partners with GCH" read as reported
    # independently.
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    site = (_host(row["uri"]) or "").split(".")[0].replace("-", "")
    if len(slug) >= 3 and site and (site == slug or site.startswith(slug)):
        evidence = {**evidence, "voice": "owned", "source_type": "vendor",
                    "key": f"owned:web:{_host(row['uri'])}"}
    # The strip shows only what its review wrote and Jev passed
    # (market_wider_review). An item not read yet waits for the review, and
    # one that failed is not shown: the post's own text is no headline.
    reading = (row.get("review_check") or {}).get("wider") \
        if isinstance(row.get("review_check"), dict) else None
    if not reading:
        return {"unchecked": True, "uri": row["uri"], "title": row.get("title"),
                "summary": row.get("summary"), "company": company, "kind": kind}
    if not reading.get("passed") or not reading.get("headline"):
        return None
    return {
        "key": f"wider:{row['uri']}",
        "event_type": kind,
        "date": (row.get("published") or "")[:10] or None,
        "vendors": [{"brand_id": None, "vendor": company}],
        # A shared headline arrives with the poster's links, handles and
        # hashtags: "… Autonomous Threat Era • @QuorumCyber @OntinueMXDR •
        # #DRJ https://t.co/…".
        "headline": reading["headline"],
        "summary": reading.get("summary") or "",
        "evidence": [evidence],
        "seed": True, "seed_rank": 1,
        # A publisher's headline over a post that shares one.
        "headline_rank": 0 if row.get("article_class") == "news" else 1,
    }


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
            "headline": f"{n} open roles",
            "summary": (f"{n} distinct open roles on job boards during "
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
            "evidence": [{"uri": None, "title": "LinkedIn company profile, two dates",
                          "source": "linkedin", "published": latest_at,
                          "voice": "measured", "social": False,
                          "source_type": "linkedin_profile",
                          "key": f"measured:linkedin:{m.get('brand_id')}"}],
            "evidence_count": 2,
            "attributes": {"pct": pct, "previous": prev, "latest": now_n},
            "seed": True, "seed_rank": 4, "headline_rank": 2,
        })
    return out


def includes_research(market: Dict[str, Any]) -> bool:
    """Whether this market counts a published study as a development.

    Off unless the market asks for it, via ``config.developments
    .include_research``. Off is the conservative default because switching it
    on changes the shape of a report rather than adding to its edges, and the
    two markets we have measured want opposite answers.

    On a health market the evidence *is* the news: "Weight Watchers Releases
    GLP-1 Results Report Demonstrating 61% Greater Weight Loss" was the most
    consequential thing that vendor did that month, and it also produced
    Oviva's first corroborated event, because an outside publication reported
    the same study.

    On AI-in-the-SOC it is mostly content marketing. Counting research there
    added 35 developments to a 93-development month — more than product
    launches — and pushed the share of developments with an outside source
    down from 0.118 to 0.086, because a vendor's own benchmark is vendor-only
    by construction. The report got longer and its corroboration looked worse
    while nothing about the market had changed.

    The event itself is recorded either way. This decides whether the market's
    report counts it, not whether we know about it.
    """
    cfg = market.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except ValueError:
            cfg = {}
    return bool((cfg.get("developments") or {}).get("include_research"))


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
    # A caller that passed only an id still gets the market's own answer;
    # defaulting it to "off" here would make the flag depend on which entry
    # point asked.
    if "config" not in market:
        market = dict(market, config=conn.execute(text(
            "SELECT config FROM bw_markets WHERE id = :m"),
            {"m": market_id}).scalar())
    stored, held = _stored_candidates(conn, market_id, days)
    corpus, discussion, total_records, by_class, wider, wider_unchecked = _corpus_candidates(
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
    # Dropped after distilling, not before: a research record can still be the
    # evidence that corroborates somebody else's development, and excluding it
    # from the candidate pool would throw that away too.
    if not includes_research(market):
        developments = [d for d in developments
                        if d["event_type"] != "research"]
    developments.sort(key=rank_key)
    for i, dev in enumerate(developments, 1):
        dev["rank"] = i

    # Attached discussion records are evidence now, so the discussion list
    # only holds what nothing claimed.
    attached = {e.get("uri") for d in developments for e in d["evidence"]}
    # The wider market: other companies' deals and launches, one item per
    # event, newest first, none that is already evidence for a vendor's own.
    # A social post alone is one account's word; it takes a news report or
    # a second account for a company we do not track.
    wider_devs = [d for d in (finish(d) for d in _merge_by_company(dedupe(
        [w for w in wider if w["evidence"][0]["uri"] not in attached], stop=stop)))
        if "news" in d["source_types"] or d["source_count"] >= 2]
    # Most reported first: the front page shows five, and Zscaler's launch,
    # reported by ten sources, sat sixth behind single-source items.
    wider_devs.sort(key=lambda d: (d["source_count"], str(d.get("date") or "")),
                    reverse=True)
    discussion = [r for r in discussion if r["uri"] not in attached]

    return {
        "days": days,
        "developments": developments,
        "total": len(developments),
        "records_considered": total_records + len(stored),
        "collected_records": total_records,
        "records_by_class": by_class,
        "discussion": discussion,
        "wider": wider_devs,
        # Strip candidates its review has not read yet (market_wider_review).
        "wider_unchecked": wider_unchecked,
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
    "material_change": "with a development",
    "monitored_no_material_change": "watched, no development",
    "incomplete_coverage": "partly collected",
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
    events = [d for d in developments if not is_signal(d)]
    changed = {v.get("brand_id") for d in events for v in d["vendors"]
               if v.get("brand_id") is not None}
    changed_names = {(v.get("vendor") or "").lower() for d in events
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


def is_signal(dev: Dict[str, Any]) -> bool:
    """A hiring or headcount reading: counted on its own, not as something
    a vendor did."""
    return dev.get("event_type") in SIGNAL_TYPES


def top_vendors(by_vendor: Sequence[Dict[str, Any]], n: int = 3) -> List[Dict[str, Any]]:
    """The ``n`` most active vendors, and every vendor tied with the last of
    them: Mate Security had as many developments as the third-placed vendor
    and was left out of "the three most active" (Sep 2026)."""
    rows = list(by_vendor)
    if len(rows) <= n:
        return rows
    floor = rows[n - 1]["n"]
    return [r for r in rows if r["n"] >= floor]


def distribution(developments: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Counts by kind, by vendor, by provenance, and how concentrated.

    Hiring and headcount readings are counted by kind and as ``signals``, and
    left out of everything else: "101 developments" held 18 of them, and the
    sections listing developments never showed those 18."""
    by_type: Dict[str, int] = {}
    by_vendor: Dict[str, int] = {}
    by_prov: Dict[str, int] = {s: 0 for s in PROVENANCE_STATES}
    for d in developments:
        by_type[d["event_type"]] = by_type.get(d["event_type"], 0) + 1
    events = [d for d in developments if not is_signal(d)]
    for d in events:
        by_prov[d["provenance"]] = by_prov.get(d["provenance"], 0) + 1
        for v in d["vendors"]:
            name = v.get("vendor") or "?"
            by_vendor[name] = by_vendor.get(name, 0) + 1
    total = len(events)
    vendors_ranked = sorted(by_vendor.items(), key=lambda kv: (-kv[1], kv[0]))
    # The share of developments that involve any of the most active vendors,
    # not the sum of their counts: a development naming two of them is one.
    leaders = {r["vendor"] for r in top_vendors(
        [{"vendor": v, "n": n} for v, n in vendors_ranked])}
    top3 = sum(1 for d in events
               if any((v.get("vendor") or "?") in leaders for v in d["vendors"]))
    product = sum(by_type.get(t, 0) for t in PRODUCT_TYPES)
    adoption = sum(by_type.get(t, 0) for t in ADOPTION_TYPES)
    return {
        "total": total,
        "signals": len(developments) - total,
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
#: Share of developments carrying a source other than the vendor, below which
#: a finding may not characterise the market's behaviour.
#:
#: Two findings here count vendor announcements and then say something about
#: the market: which kind of announcement dominates, and whose word the
#: developments rest on. Both are only about the market if we read enough
#: besides the vendors for the balance to mean anything, and on this host we
#: do not. The event extractors read vendor LinkedIn, vendor sites and
#: LinkedIn jobs; the ``coverage`` extractor that would read trade press is
#: registered and switched off. Matching corpus records onto events at report
#: time recovers some outside sourcing, but only 12 of 101 developments in the
#: last 30 days, and 19 of the 31 independent evidence items behind those are
#: social posts rather than reporting.
#:
#: So "for most developments the only source is the vendor" was measuring how
#: little we read and reporting it as a fact about the market, every period,
#: with no other answer available to it. Same for the product-against-customer
#: comparison: vendors post launches more than customer wins, so counting only
#: vendor posts guarantees that result.
#:
#: ``MIN_COVERAGE_SHARE`` does not catch this. It asks whether we reached
#: enough vendors, which we do; it never asks whether we reached anyone but
#: vendors. This is that second question. Set at a third because below that
#: the vendor-only share is carried by what we did not read, not by how the
#: market behaves.
MIN_INDEPENDENT_SHARE = float(
    os.getenv("MARKET_FINDING_MIN_INDEPENDENT", "0.35") or 0.35)
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


def _vendor_lines(rows: List[Dict[str, Any]], key: str, unit: str,
                  limit: int = 4, singular: Optional[str] = None) -> List[str]:
    """One evidence line per vendor, with withheld vendors collapsed into one.

    A masked row (see ``market_entitlements.mask_rows``) carries the same
    placeholder name as every other masked row, so printing them one per line
    would read as the same vendor four times.
    """
    def _unit(n: int) -> str:
        return singular if (singular and int(n) == 1) else unit

    shown = rows[:limit]
    lines = [f"{r['vendor']}: {r[key]} {_unit(r[key])}"
             for r in shown if not r.get("withheld")]
    hidden = [r for r in shown if r.get("withheld")]
    if hidden:
        total = sum(int(r.get(key) or 0) for r in hidden)
        lines.append(f"{len(hidden)} vendor{'s' if len(hidden) != 1 else ''} "
                     f"not shown in this view: {total} {_unit(total)}")
    return lines


def _alone(row: Dict[str, Any], share: float) -> str:
    """'7ai alone 21%', or its masked form."""
    if row.get("withheld"):
        return f"the largest, not shown in this view, {_pct(share)}"
    return f"{row['vendor']} alone {_pct(share)}"


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


_LED_BY = re.compile(r"\bled by ([^.;\n]{3,90})", re.I)


def _evidence_line(dev: Dict[str, Any]) -> str:
    """One source line under a highlight: the headline, whose word it rests
    on, and the day, the way the rest of the page writes them. It read
    "(acquisition, 2026-09-17, vendor sources only)", repeating the kind the
    highlight had just named."""
    day = _parse_day(dev.get("date"))
    when = f"{day.day} {day.strftime('%b %Y')}" if day else "date unknown"
    return f'{dev["headline"]} ({dev["provenance_label"]}, {when})'


def _day_month(iso: Optional[str]) -> str:
    day = _parse_day(iso)
    return f"{day.day} {day.strftime('%B')}" if day else ""


def _deal_sentence(dev: Dict[str, Any]) -> str:
    """A deal in our words: who bought whom, who raised what, and when.

    The vendor's own first sentence read "Coalition, Inc. acquired us for our
    ability to stop cyber threats in milliseconds" in the report's voice, and
    a fixed line about the buyer taking on customers followed it whatever
    the deal was (Sep 2026). The vendor's sentence stays in the evidence line.
    """
    vendor = _dev_vendor_name(dev)
    when = _day_month(dev.get("date"))
    on = f" on {when}" if when else ""
    text_value = _full_text(dev)
    if dev["event_type"] == "acquisition":
        buyer = _acquirer(text_value, vendor, _title_of(dev))
        if buyer:
            return f"{buyer} acquired {vendor}{on}."
        return f"{vendor} was acquired{on}; the source does not name the buyer."
    if dev["event_type"] == "funding":
        wim = (dev.get("why_it_matters") or "").strip().rstrip(".")
        total = ""
        if wim.startswith("A "):
            said = f"{vendor} raised a {wim[2:]}"
        else:
            said = f"{vendor} raised a new round"
            if "in total" in wim:
                total = (f" {vendor} says it has raised "
                         f"{wim.split(' raised in total')[0]} in total.")
        # The headline first, on its own: joined to the post, a headline with
        # no full stop ran the match on into the vendor's text ("led by Wa'ed
        # Ventures StrikeReady is excited to share our new investment round
        # led by the venture").
        led = (_LED_BY.search(_title_of(dev))
               or _LED_BY.search(dev.get("summary") or ""))
        if led:
            said += f" led by {led.group(1).strip()}"
        return f"{said}{on}.{total}"
    return _first_sentence(dev)


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
    # Every development, for counting only. In a shared view ``devs`` holds
    # just the ones whose vendors may be named; the market's figures must not
    # shrink with the reader's entitlement.
    counted = inputs.get("counted_developments") or devs
    obs = inputs.get("observation") or {}
    hiring = inputs.get("hiring") or {}
    registry_total = int(inputs.get("registry_total") or 0)
    days = int(inputs.get("days") or 30)
    post_cov = inputs.get("post_collection")
    out: List[Dict[str, Any]] = []

    # 1. Consolidation and exits: any acquisition is a finding on its own.
    # Only items the checks are sure of are named in a highlight; every
    # development still counts.
    quoted = [d for d in devs if prominent_ok(d)]
    ownership = _devs_of(quoted, "acquisition", "market_exit", "market_entry")
    if ownership:
        acq = _devs_of(ownership, "acquisition")
        lines = [_evidence_line(d) for d in ownership]
        if acq:
            head = (f"{len(acq)} acquisition"
                    f"{'s' if len(acq) != 1 else ''} among the vendors we track.")
        else:
            head = (f"{len(ownership)} change{'s' if len(ownership) != 1 else ''}"
                    " in who is in the market.")
        told = " ".join(_deal_sentence(d) for d in ownership[:2])
        out.append(_finding(
            "consolidation", head, told,
            evidence=lines,
            coverage=_partial_posts_note(inputs),
            developments=ownership))

    # 2. Capital: funding events in the period, never their absence.
    funding = _devs_of(quoted, "funding")
    if funding:
        out.append(_finding(
            "capital",
            f"New funding for {_name_list(funding)}.",
            " ".join(_deal_sentence(d) for d in funding[:3]),
            evidence=[_evidence_line(d) for d in funding],
            coverage=_partial_posts_note(inputs),
            developments=funding))

    # 3. Product against customer evidence. Comparing counts across the
    # market needs the vendors' own channels to have been read for most of
    # them; below that the comparison describes our collection, not the
    # market, and the observed-mix finding below is used instead.
    # Counted over every development, named from the ones this reader may
    # see: a shared view that counted only its ten vendors said customer
    # evidence "keeps pace" where the market's figures say product activity
    # exceeds it.
    product = _devs_of(devs, *PRODUCT_TYPES)
    customers = _devs_of(devs, "customer")
    # Counted in full, but only a named customer or a case study is listed.
    listed_customers = [d for d in customers
                        if _customer_listable(d) and prominent_ok(d)]
    product_all = _devs_of(counted, *PRODUCT_TYPES)
    customers_all = _devs_of(counted, "customer")
    post_share = _coverage_share(post_cov)
    # Both branches below characterise the market from the mix of developments,
    # so both need the mix to have come from somewhere other than the vendors.
    # Reading only vendor channels guarantees product announcements outnumber
    # customer ones, because that is what vendors post; saying so back is
    # circular. See MIN_INDEPENDENT_SHARE.
    independent_enough = (dist.get("independent_share") or 0) >= MIN_INDEPENDENT_SHARE
    if not independent_enough:
        pass
    elif (len(product_all) + len(customers_all) >= MIN_DEVELOPMENTS_FOR_MIX
            and post_share is not None and post_share >= MIN_COVERAGE_SHARE):
        named = [d for d in customers_all if _customer_named(d)]
        if len(product_all) > 2 * len(customers_all):
            head = "Vendors announce products far more often than customers."
        elif len(customers_all) >= len(product_all):
            head = "Customer announcements keep pace with product announcements."
        else:
            head = "Product and customer announcements are about level."
        out.append(_finding(
            "product_vs_customer", head,
            f"Vendors made {len(product_all)} product launch or expansion "
            f"announcement{'s' if len(product_all) != 1 else ''} against "
            f"{len(customers_all)} customer or deployment announcement"
            f"{'s' if len(customers_all) != 1 else ''} in the period"
            + ((f", {len(named)} of which name"
                f"{'s' if len(named) == 1 else ''} the customer." if named else
                ", none of which names the customer.") if customers_all else ".")
            + " These count announcements, not sales.",
            evidence=[f"Product: {_name_list(product, 5)}"]
            + ([f"Customers: {_name_list(listed_customers, 5)}"]
               if listed_customers else []),
            coverage=_partial_posts_note(inputs),
            developments=product + customers))
    elif len(devs) >= MIN_DEVELOPMENTS_FOR_MIX and dist.get("by_type"):
        top = dist["by_type"][0] if dist["by_type"] else None
        lead = max(dist["by_type"], key=lambda t: t["n"]) if dist["by_type"] else top
        if lead:
            out.append(_finding(
                "dominant_kind",
                f"{lead['label']} is the most common kind of development "
                f"({lead['n']} of {dist['total']}).",
                "Developments by kind, each counted once: " + ", ".join(f"{t['label'].lower()} {t['n']}"
                                     for t in dist["by_type"]) + ".",
                evidence=[f"{t['label']}: {_name_list(_devs_of(devs, t['event_type']), 3)}"
                          for t in dist["by_type"][:3]],
                coverage=(f"We could read announcements for only "
                          f"{_pct(post_share)} of vendors, so this describes "
                          "what we saw, not the whole market."
                          if post_share is not None else
                          "We did not read the vendors' own announcements, so "
                          "this covers outside reporting only."),
                developments=devs))

    # 4. Customer adoption on its own, when the comparison above was not made.
    if listed_customers and not any(f["id"] == "product_vs_customer" for f in out):
        named = [d for d in customers if _customer_named(d)]
        out.append(_finding(
            "adoption",
            f"Customer announcements from {_name_list(listed_customers)}.",
            f"{len(customers)} customer or deployment announcement"
            f"{'s' if len(customers) != 1 else ''}, "
            f"{len(named)} of them naming the customer.",
            evidence=[_evidence_line(d)
                      for d in listed_customers[:5]],
            coverage=_partial_posts_note(inputs),
            developments=listed_customers))

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
                "A few vendors account for most open roles.",
                f"Of the {openings} open roles, {top['vendor']} "
                f"accounts for {top['openings']} ({_pct(share)}), with "
                f"{second['vendor']} the next largest at {second['openings']}.",
                evidence=_vendor_lines(by_vendor, "openings", "open roles"),
                coverage=(f"Only {len(by_vendor)} of {registry_total} vendors have job "
                          "listings we can read, so this is not a market-wide ranking."),
                developments=hire_devs))

    # 6. Concentration of material change across the registry.
    if len(devs) >= MIN_DEVELOPMENTS_FOR_MIX and dist.get("vendors_with_change"):
        counts = obs.get("counts") or {}
        quiet = counts.get("monitored_no_material_change", 0)
        # Every vendor in the registry is in one sentence or another, so the
        # figures add up to the total: 55 with a development and 38 without
        # left four unexplained (Sep 2026).
        unread = (counts.get("incomplete_coverage", 0) + counts.get("paused", 0)
                  + counts.get("not_yet_collected", 0))
        top3 = top_vendors(dist["by_vendor"])
        top3_txt = ", ".join(f"{v['vendor']} {v['n']}" for v in top3[:5])
        if len(top3) > 5:
            top3_txt += f", and {len(top3) - 5} more"
        signals = dist.get("signals") or 0
        out.append(_finding(
            "change_concentration",
            f"{dist['vendors_with_change']} of {registry_total} vendors had a "
            "development.",
            f"{dist['total']} developments in {days} days"
            + (f", plus {signals} hiring or headcount signals" if signals else "")
            # Ties at the cut-off made "the 19 most active vendors".
            + (f". The {len(top3)} most active vendors account for "
               if len(top3) <= 5 else
               f". The {len(top3)} vendors with {top3[-1]['n']} or more "
               "developments account for ")
            + f"{_pct(dist['top3_share'])} of them ({top3_txt})."
            + (f" {quiet} vendors were watched and had none." if quiet else "")
            + (f" {unread} are not fully collected yet." if unread else ""),
            evidence=_vendor_lines(dist["by_vendor"], "n", "developments",
                                   singular="development", limit=5),
            coverage="",
            developments=devs))

    # 7. Whose word it all rests on — only once somebody other than the
    # vendors has been read. With vendor-only collection this counted our own
    # inputs and reported them as a property of the market, every period, with
    # no other answer available to it. See MIN_INDEPENDENT_SHARE.
    if len(devs) >= MIN_DEVELOPMENTS_FOR_MIX and independent_enough:
        prov = dist.get("by_provenance") or {}
        vendor_only = prov.get("vendor_source_only", 0)
        indep = (prov.get("independently_reported", 0)
                 + prov.get("multiple_independent_sources", 0))
        share = dist.get("vendor_only_share") or 0
        head = ("For most developments the only source is the vendor."
                if share >= 0.6 else
                "Outside sources reported fewer than half of the developments."
                if share >= 0.4 else
                "Most developments were reported by somebody other than the vendor.")
        out.append(_finding(
            "corroboration", head,
            f"{vendor_only} of {dist['total']} developments have only the "
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
                f"Most of the market is new: {recent} of the {with_year} "
                f"vendors with a known founding year were founded in {cutoff} "
                "or later.")
        elif share <= 0.25:
            text_value = (
                f"Most of the market is established: only {recent} of "
                f"the {with_year} vendors with a known founding year were "
                f"founded in {cutoff} or later.")
        else:
            text_value = (
                f"The market mixes new and established companies: "
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
            lead = "Product news outweighs customer announcements."
        elif adoption >= product:
            lead = "Customer announcements keep up with product news."
        else:
            lead = "Activity splits between product news and customer announcements."
        out.append({
            "heading": "Products versus customers",
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
                         f"({_alone(by_vendor[0], by_vendor[0]['openings'] / openings)})",
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
            lead = ("Activity is concentrated in "
                    + ("; ".join(concentrated) + ". "))
            rest = [m for m in lines if m not in concentrated]
            text_value = lead + (("Elsewhere it is spread: " + "; ".join(rest)
                                  + ".") if rest else "")
        else:
            text_value = ("Activity is spread rather than "
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
    Developments are filtered to those vendors before findings are generated,
    because a development is a headline and a headline names its subject. The
    market-wide aggregates (hiring, share of voice, funding) are kept whole and
    only masked, so the shared view states the same finding as the full one
    with the withheld vendors unnamed.
    """
    from app.services import market_analysis as man
    from app.services import market_entitlements as ent
    from app.services import market_metrics as mmet

    market_id = market["id"]
    material = material_developments(conn, market_id, days, market=market)
    devs = material["developments"]
    every_dev = devs
    if allowed_brand_ids is not None:
        allowed = {int(b) for b in allowed_brand_ids}

        def _in(v: Dict[str, Any]) -> bool:
            return v.get("brand_id") is None or int(v["brand_id"]) in allowed

        kept = []
        for d in devs:
            if not d["vendors"]:
                continue
            if all(_in(v) for v in d["vendors"]):
                kept.append(d)
                continue
            # Hiring and headcount stay, masked, not dropped (user decision,
            # 2 Sep 2026): the public hiring list showed 3 of 10 qualifying
            # recruiters while its header counted the whole market's 157
            # roles. The counts keep their place in the list; the name — and
            # the evidence, whose job-board links identify the vendor — are
            # withheld. Ranking fields (source_count etc.) were computed
            # before this point, so emptying the evidence cannot re-rank.
            if d.get("event_type") in ("significant_hiring", "headcount_change"):
                kept.append({**d, "withheld": True, "evidence": [],
                             "vendors": [v if _in(v) else
                                         {**v, "vendor": ent.WITHHELD_LABEL,
                                          "withheld": True}
                                         for v in d["vendors"]]})
                continue
            # Everything else is editorial and open (operator policy, 9 Sep
            # 2026): a restricted reader sees every vendor's news, posts and
            # developments by name — the movers card sat on 2 Sep while the
            # market moved. Only KPIs and metrics stay with the authorized
            # set (the hiring/headcount masking above, the distribution rows
            # below, share-of-voice and the benchmark report).
            kept.append(d)
        devs = kept
        material["developments"] = devs
        material["total"] = len(devs)

    # The counts are the market's, whichever vendors this reader may see:
    # "8 of 84 vendors showed change" counted the shown vendors against the
    # whole registry. The per-vendor rows are then filtered for display.
    observation = vendor_observation(conn, market_id, days,
                                     developments=every_dev)
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
    # Masked, not filtered. Dropping the withheld vendors' rows changed the
    # totals: the shared view of ten vendors reported 7ai at 58% of 55 roles
    # and "5 of 84 vendors", where the whole market is 21% of 149 roles across
    # 20 vendors. The counts stay whole; only the names are withheld.
    if allowed_brand_ids is not None:
        hiring = ent.mask_rows(hiring, allowed_brand_ids) or {}
        sov = ent.mask_rows(sov, allowed_brand_ids) or {}
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
        funding_by_vendor = ent.mask_rows(funding_by_vendor, allowed_brand_ids)

    dist = distribution(every_dev)
    if allowed_brand_ids is not None:
        shown = set(ent.vendor_names(conn, market_id, allowed_brand_ids).values())
        for row in dist["by_vendor"]:
            if row["vendor"] not in shown:
                row["vendor"] = ent.WITHHELD_LABEL
                row["withheld"] = True
    inputs = {
        "days": days,
        "developments": devs,
        "counted_developments": every_dev,
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
        "wider": material.get("wider") or [],
        "distribution": dist,
        "observation": observation,
        "findings": findings,
        "synthesis": synthesis,
        "source_coverage": _safe(source_coverage, conn, market_id) or [],
        "inputs": {"registry_total": registry_total,
                   "post_collection": post_collection,
                   "jobs_collection": jobs_collection},
    }
