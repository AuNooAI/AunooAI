"""Reading vendor posts once and deciding whether they carry anything.

A market monitor cannot use vendor LinkedIn posts wholesale and cannot throw
them away either. There are 562 of them against 122 news articles, so used
wholesale they bury everything; and most are conference-booth notices. But
vendors announce launches, raises, customer wins and senior hires on LinkedIn
first and often nowhere else, so discarding the channel loses real events.

No keyword rule separates the two. These two posts are the same shape:

    Dropzone AI is a 2025 IA40 winner, two years in a row.
    If you're at the Gartner Summit today, come meet the team at booth 4141.

So each post is read once by a model and given a verdict, and the verdict is
stored on its ``bw_market_articles`` row. Reviewed once, not per query — the
judgement does not change and re-asking would be paying twice for the same
answer.

Three verdicts:

    signal     — a fact about the company or the market. A launch, a raise, a
                 customer, a partnership, an award, a hire, a finding.
    commentary — substantive analysis of the market with no new fact in it.
                 Worth reading, not worth reporting as a change.
    noise      — conference presence, generic recruiting, content-free hype.
"""

import asyncio
import html
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

VERDICTS = ("signal", "commentary", "noise")

CUSTOMER_SPEAKERS = ("customer", "vendor")
CUSTOMER_STAGES = ("in_use", "evaluation", "case_study", "existing", "unclear")


def _customer_of(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The customer object from one verdict, normalised, or None.

    Only for kind "customer". A missing or malformed object is None rather
    than a guess, so the report falls back to its own reading of the text.
    """
    if (str(item.get("kind") or "")).strip().lower() != "customer":
        return None
    raw = item.get("customer")
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    name = (str(name).strip()[:120] or None) if name not in (None, "", "null") else None
    speaker = str(raw.get("speaker") or "vendor").strip().lower()
    stage = str(raw.get("stage") or "unclear").strip().lower()
    if speaker not in CUSTOMER_SPEAKERS:
        speaker = "vendor"
    # Nobody unnamed can be quoted: "the customer's own words" needs a
    # customer. A model that marks an anonymous account as the customer
    # speaking is contradicting itself, and the vendor is the one talking.
    if name is None:
        speaker = "vendor"
    return {
        "name": name,
        "speaker": speaker,
        "stage": stage if stage in CUSTOMER_STAGES else "unclear",
    }

# Posts per model call. Small enough that one bad post cannot cost a whole
# batch, large enough that the instructions are not re-sent per post. Reasoning
# models silently truncate long batched JSON, so this stays well short of any
# output ceiling.
DEFAULT_BATCH = 20

# Body text sent per post. A LinkedIn post's point is in its first lines, but
# the review now writes a summary too, and at 600 characters Intezer's list of
# four launches was cut after two and the model supplied the rest.
SUMMARY_CHARS = 1200
# A blog article states its news further down, after an opening paragraph
# that sets the scene.
BLOG_SUMMARY_CHARS = 1500

PROMPT = """You are screening posts and blog articles published by vendors in the {market} market.

For each post decide what it is:

- "signal": states a fact about the company or the market. A product launch or
  capability, a funding round, a named customer or design win, a partnership,
  an acquisition, an award, a senior hire, headcount or office news, a research
  finding, a published benchmark.
- "commentary": substantive analysis or argument about the market with no new
  fact about the company in it. Worth reading for context.
- "noise": conference or booth presence, "come see us", generic recruiting,
  reposts with no added content, congratulations, motivational content, or
  hype with nothing specific behind it.

Also give a kind: launch, funding, customer, partnership, acquisition, award,
hiring, research, opinion, event, other.

A post whose author is shown as @handle is by a person we follow — an analyst
or practitioner, not a vendor. For them a substantive argument or observation
about the market is "commentary" and worth keeping; a reply with no substance,
a joke, or a post about something else entirely is "noise".

These are noise, not signal, however senior the people in them:
- a speaking slot, panel appearance, webinar, podcast or conference visit
- an office visit by an official, a customer or an investor
- an employee spotlight, team profile or "meet the team" post
- an executive being quoted in someone else's article
- a company anniversary, culture post or award shortlisting

If you give kind "event" or "opinion", the verdict cannot be "signal".

Being accepted into another company's programme (a partner programme, an
accelerator, a verification or early-access scheme, a marketplace listing) is
kind "award", not "partnership". A partnership is two named companies agreeing
to work together.

A hire is signal only when the post says someone has joined or been appointed.
A customer is signal only when the customer is named or the deal is described.
A launch is signal only when the post announces that a specific, named product
or capability is now available, shipped or released, and kind "launch" is only
for that. A post that argues a point, explains what the product does in general,
comments on a threat, breach or vulnerability, marks an anniversary, or points
to a webinar, podcast, interview, playbook or newsletter is not a launch: its
kind is "opinion" (or "research" for a finding, "event" for the webinar).
Naming the product is not enough — the post has to say something new has shipped
or is now available. Financial results, a dividend, a book, and a certification,
course or training programme are not launches: their kind is "other". When in doubt between "launch" and "opinion", choose
"opinion".

For kind "customer" only, also give a "customer" object (the kind stays
"customer"; the values below are not kinds):
- "name": the organisation named as the customer, exactly as written, or null
  when no organisation is named. A description is not a name: "a Fortune 500
  retailer", "one of our customers", "three banks" and "multiple federal
  agencies" are all null. A pronoun is not a name: "they", "the team", "this
  company" are null. A person's name is not an organisation. The vendor itself,
  its own products and platforms, a partner or reseller delivering the deal,
  and a company that co-wrote or published the case study, are not the
  customer.
- "speaker": "customer" when a named person from the customer is quoted or
  presented speaking about it; otherwise "vendor".
- "stage": "in_use" when the customer is running it; "evaluation" when they are
  evaluating, piloting or trialling it; "case_study" only when the post says a
  case study or customer story has been published (it names or links to it); a
  story told in the post itself is not a published case study; "existing" when
  it is a business review or visit with a customer already using it; otherwise
  "unclear".

Judge only what the text actually says. A post that gestures at a big claim
without stating anything specific is noise, however important it sounds. Being
written by a vendor does not by itself make a post noise, and a post being
enthusiastic does not make it signal. When a post is on the line between
signal and commentary or between commentary and noise, choose the lower one.

For every "signal", also write the item as a reader of a market news page
should see it. Use only what the post states. Write in the third person, in
our words, not the vendor's: no "we", "our", "us", "excited", "proud",
"thrilled", no hashtags, no emoji, no claim the post does not make.
- "headline": one line of at most 14 words, "<Company> <did what> <with whom or
  what>", naming the product, customer, partner, investor or amount the post
  names. "Legion Security joins OpenAI's Daybreak Blue programme for approved
  defenders", not "We're proud to share that we have been accepted".
- "summary": one sentence of at most 30 words adding what the headline leaves
  out and the post states about the same development: a figure, a date, who is
  involved, what it does. Never a different fact from elsewhere in the post
  (an acquisition's summary is about the acquisition, not an analyst report the
  post also mentions). When the post lists items, name them as the post does.
  null when the post says nothing more about the development.
For "commentary" and "noise", headline and summary are null.

Reply with a JSON array, one object per post, in the same order, no prose:
[{{"n": 1, "verdict": "signal", "kind": "launch", "reason": "<12 words or fewer>",
   "headline": "Torq launches Auto Triage, which keeps context across alerts",
   "summary": "The agent carries what it learned from earlier alerts into new investigations."}},
 {{"n": 2, "verdict": "signal", "kind": "customer", "reason": "<12 words or fewer>",
   "headline": "Virgin Money runs Legion Security in its SOC",
   "summary": null,
   "customer": {{"name": "Virgin Money", "speaker": "customer", "stage": "in_use"}}}},
 {{"n": 3, "verdict": "noise", "kind": "event", "reason": "<12 words or fewer>",
   "headline": null, "summary": null}}]

Posts:
{posts}"""


# ---------------------------------------------------------------------------
# Earned coverage — the same question asked of somebody else's reporting
# ---------------------------------------------------------------------------
#
# The vendor review above reads posts we already know the author of: the row
# carries ``bias_source = 'vendor:linkedin'``, so the subject is settled before
# the model is asked anything. Trade press is not like that. An article lands
# in the corpus because it matched a market phrase — "security operations",
# "AI SOC" — and those say nothing about which company it concerns. Of 249
# earned-press articles in the AI-SOC corpus, 30 had a company attached.
#
# So this pass asks two questions where the vendor pass asks one: *who is this
# about*, and *what happened*. The first is the one that kept the ``coverage``
# extractor switched off, because no deterministic rule separates an article
# about a company from an article that mentions it in a list.
#
# A cheap term scan narrows the batch before the model sees it, so we are not
# paying to read articles that name no vendor at all. The scan proposes; it
# never decides.

#: Candidate vendors shown per article. Enough for a roundup that names
#: several, small enough that the prompt stays cheap.
EARNED_MAX_CANDIDATES = 8

EARNED_PROMPT = """Below are news articles from the trade press, each followed by the
companies in the {market} market whose name appears in it.

For each article decide two things.

First, which company the article is *about* — the one whose news it reports.
Give its name exactly as listed under that article, or null. These are null:

- a roundup, listicle or "top N vendors" piece that names several companies
  and reports news about none of them
- an article about something else that cites the company as an example, quotes
  its staff as commentators, or lists it among competitors
- a market-size, forecast or industry-trend piece
- an article about a different company that merely mentions this one

Name a company only when something happened to *that* company and the article
reports it. When two companies share the news — an acquisition, a partnership —
name the one the headline leads with.

Second, what kind of development it reports: launch, funding, customer,
partnership, acquisition, award, hiring, research, opinion, event, other.

Then a verdict:
- "signal": the article reports a specific development at the named company.
- "commentary": substantive analysis of the market, or of the company, with no
  new development in it.
- "noise": a passing mention, a jobs roundup, a press-release rewrite with
  nothing specific in it, or an article about something else entirely.

If "company" is null the verdict cannot be "signal". If you give kind "event"
or "opinion" the verdict cannot be "signal".

"reason" is a short phrase naming what happened, and it must name the thing:
"$33M Series A led by Accel", "acquires Wirespeed", "launches Torq Auto Triage".
Not "funding announced" — the name is what makes it checkable.

Reply with a JSON array, one object per article, in the same order, no prose:
[{{"n": 1, "company": "Torq", "kind": "funding", "verdict": "signal",
  "reason": "$33M Series A led by Accel"}},
 {{"n": 2, "company": null, "kind": "other", "verdict": "noise",
  "reason": "vendor roundup, no news"}}]

Articles:
{posts}"""


def _model() -> str:
    """The model to review with.

    Screening is a cheap, high-volume, low-stakes judgement, so it follows the
    same setting the article analysis step uses rather than reaching for a
    bigger one.
    """
    return (os.getenv("MARKET_POST_REVIEW_MODEL")
            or os.getenv("KEYWORD_MONITOR_DEFAULT_MODEL")
            or "bedrock-kimi-k2-5")


def candidates(conn, market_id: int, *, limit: int = 200,
                days: Optional[int] = None,
                redo: bool = False,
                kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Vendor posts for this market's vendors that have not been read yet.

    Selected from ``bw_article_categories`` rather than from the article's
    topic, because a post's topic is its own vendor's Brand Watch lane and
    those are not scoped to a market.

    ``kinds`` narrows a ``redo`` to posts already given one of those kinds,
    for re-reading one kind after its prompt gained a field.
    """
    # A reshare is not the vendor's claim, so classifying it as the vendor's
    # signal or noise is a category error — and it spends a model call to make
    # one.
    from app.services.market_corpus import own_voice_sql

    # The vendor's LinkedIn posts and its own website's articles. Until 25 Sep
    # 2026 only the first: 3 of about 330 blog posts had ever been read, so an
    # announcement made on a vendor's blog never became a development.
    where = ["(a.bias_source = 'vendor:linkedin' OR a.bias_source LIKE 'owned:%')",
             own_voice_sql("a")]
    params: Dict[str, Any] = {"m": market_id, "lim": int(limit)}
    if not redo:
        where.append("(ma.review_verdict IS NULL OR ma.article_uri IS NULL)")
    if kinds:
        where.append("LOWER(ma.review_kind) = ANY(:kinds)")
        params["kinds"] = [k.lower() for k in kinds]
    if days:
        from datetime import timedelta

        where.append("COALESCE(a.publication_date, a.submission_date) >= :since")
        params["since"] = (datetime.now(timezone.utc)
                           - timedelta(days=int(days))).strftime("%Y-%m-%dT%H:%M:%S")

    rows = conn.execute(text(f"""
        SELECT DISTINCT ON (a.uri)
               a.uri, a.title, a.summary, b.display_name AS vendor,
               a.bias_source,
               COALESCE(a.publication_date, a.submission_date) AS published
        FROM articles a
        JOIN bw_article_categories bac ON bac.article_uri = a.uri
        JOIN bw_market_brands mb ON mb.brand_id = bac.brand_id
                                 AND mb.market_id = :m
        JOIN bw_brands b ON b.id = bac.brand_id
        LEFT JOIN bw_market_articles ma ON ma.article_uri = a.uri
                                        AND ma.market_id = :m
        WHERE {' AND '.join(where)}
        ORDER BY a.uri,
                 COALESCE(a.publication_date, a.submission_date) DESC
        LIMIT :lim
    """), params).mappings().all()
    out = [dict(r) for r in rows]
    if not redo and not kinds:
        out += followed_candidates(conn, market_id, limit=max(0, limit - len(out)), days=days)
    return out


def followed_candidates(conn, market_id: int, *, limit: int = 200,
                        days: Optional[int] = None) -> List[Dict[str, Any]]:
    """Posts by followed accounts that matched no market phrase and wait for
    the judge (``market_follow`` lands them under the market's topic with
    ``social_meta.pending_review``). Shown to the model as ``@handle``."""
    if limit <= 0:
        return []
    topic = conn.execute(text(
        "SELECT config->'collection'->>'topic_name' FROM bw_markets WHERE id = :m"),
        {"m": market_id}).scalar()
    if not topic:
        return []
    where = ["a.topic = :topic", "a.social_meta->>'pending_review' = 'true'",
             "a.social_meta->>'followed' = 'true'",
             "NOT EXISTS (SELECT 1 FROM bw_market_articles ma"
             "             WHERE ma.article_uri = a.uri AND ma.market_id = :m)"]
    params: Dict[str, Any] = {"m": market_id, "topic": topic, "lim": int(limit)}
    if days:
        from datetime import timedelta

        where.append("COALESCE(a.publication_date, a.submission_date) >= :since")
        params["since"] = (datetime.now(timezone.utc)
                           - timedelta(days=int(days))).strftime("%Y-%m-%dT%H:%M:%S")
    rows = conn.execute(text(f"""
        SELECT a.uri, a.title, a.summary,
               '@' || (a.social_meta->>'author') AS vendor,
               COALESCE(a.publication_date, a.submission_date) AS published
        FROM articles a
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(a.publication_date, a.submission_date) DESC
        LIMIT :lim
    """), params).mappings().all()
    return [{**dict(r), "followed": True} for r in rows]


def _render(posts: List[Dict[str, Any]]) -> str:
    lines = []
    for i, post in enumerate(posts, 1):
        # Feed summaries arrive HTML-escaped ("&#8211;").
        body = html.unescape(post.get("summary") or "").strip().replace("\n", " ")
        blog = (post.get("bias_source") or "").startswith("owned:")
        source = f"{post.get('vendor')}, blog" if blog else post.get("vendor")
        lines.append(f"{i}. [{source}] {post.get('title') or ''}\n"
                     f"   {body[:BLOG_SUMMARY_CHARS if blog else SUMMARY_CHARS]}")
    return "\n".join(lines)


async def _judge(market_name: str, posts: List[Dict[str, Any]],
                 model: str) -> List[Dict[str, Any]]:
    """One model call over one batch. Returns verdicts aligned to ``posts``."""
    import litellm

    from app.ai_models import extract_json_response, resolve_litellm_call_params

    prompt = PROMPT.format(market=market_name, posts=_render(posts))
    response = await litellm.acompletion(
        **resolve_litellm_call_params(model),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=min(8192, 320 * len(posts) + 400),
        # The same post must get the same reading. Sampled, a borderline post
        # (Intezer's Q2 milestone listing four launches) was signal on one
        # read and commentary on the next.
        temperature=0,
    )
    raw = (response.choices[0].message.content or "").strip()
    parsed = extract_json_response(raw)
    if isinstance(parsed, dict):
        parsed = parsed.get("results") or parsed.get("posts") or []
    if not isinstance(parsed, list):
        raise ValueError(f"model returned {type(parsed).__name__}, not a list")

    # Match on the index the model echoes back, not on position. A model that
    # drops one post from a batch would otherwise shift every verdict after it
    # onto the wrong article, which is silent and unrecoverable.
    by_index: Dict[int, Dict[str, Any]] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= len(posts):
            by_index[n] = item

    out = []
    for i, post in enumerate(posts, 1):
        item = by_index.get(i)
        if not item:
            continue
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in VERDICTS:
            continue
        kind = (str(item.get("kind") or "other").strip().lower())[:24]
        # The prompt says an event or an opinion cannot be signal. Models
        # agree and then do it anyway, so the rule is enforced here as well —
        # a contradiction between the two fields is resolved against the
        # stronger claim.
        if kind in ("event", "opinion") and verdict == "signal":
            verdict = "commentary" if kind == "opinion" else "noise"
        out.append({
            "uri": post["uri"],
            "verdict": verdict,
            "kind": kind,
            "reason": (str(item.get("reason") or "").strip())[:400],
            "customer": _customer_of({**item, "kind": kind}),
            "headline": _written(item.get("headline"), 200) if verdict == "signal" else None,
            "summary": _written(item.get("summary"), 400) if verdict == "signal" else None,
            "followed": bool(post.get("followed")),
            "source_text": f"{post.get('title') or ''}\n{post.get('summary') or ''}",
            "vendor": post.get("vendor"),
        })
    return out


# ---------------------------------------------------------------------------
# Generate, validate, correct
# ---------------------------------------------------------------------------
#
# The review makes five judgements per post: whether it is news, what kind,
# who the customer is, and a headline and summary. Until 26 Sep 2026 only the
# last two were checked, so a wrong kind or a wrong customer went straight to
# the page ("Help Net Security is named as a customer" of Tuskira, for a
# threat newsletter). Now all five are checked by Jev (TypeSafe's decision
# model: a different model, it cannot generate, about $0.04 per million
# input tokens). A post Jev disagrees with goes to a second, stronger model
# with the post, the draft and each objection. Jev checks the correction. What
# is still unconfirmed is held back: an unconfirmed kind is not published, an
# unconfirmed customer name is dropped, an unconfirmed headline or summary is
# not shown.

#: Characters of the post shown to the checker.
CHECK_SOURCE_CHARS = 4000
#: Least probability of "supports" for a headline or summary to be used.
#: 0.5 let a half-supported headline lead the page (0.64, Help Net Security).
CHECK_MIN_SUPPORT = 0.7
#: A kind the drafter chose, that Jev gives less than this, is an objection.
KIND_MIN_SUPPORT = 0.25
#: Below this, Jev does not read the post as news, or the name as a customer.
NEWS_MIN = 0.4
CUSTOMER_MIN = 0.5
#: The headline's actor and the summary's subject, as Jev reads them.
ROLE_MIN = 0.5
#: The featured item and the highlights need more than a pass: both the
#: headline and the kind at this probability or better.
PROMINENT_MIN = 0.85
_CHECK_CONCURRENCY = 4

#: Kinds that become a development on the page. A wrong one of these is what
#: matters; confusing two kinds that are never shown is harmless.
EVENT_KINDS = ("launch", "funding", "customer", "partnership", "acquisition",
               "hiring")

_CHECK_CRITERIA = {
    "supports": "The post states it or directly implies it, including every "
                "name, figure, date and outcome it gives",
    "contradicts": "The post states something different: another company, "
                   "product, figure, date or outcome",
    "says_nothing": "The post does not state it, or it adds a name, figure, "
                    "claim or outcome the post does not contain",
}

#: What each kind is, written for a reader that takes definitions literally.
KIND_CRITERIA = {
    "launch": "A specific named product, feature or capability of the company "
              "is now available, shipped or released. Not a preview of something "
              "coming, not a look back, not a listing on a marketplace.",
    "funding": "The company raised investment: a round, led by or from investors.",
    "customer": "A named organisation buys, deploys or uses the company's "
                "product, awards it a contract (a government contract or "
                "award is a customer), or the post presents a case study about "
                "a customer. "
                "A publication or newsletter writing about the company, a "
                "partner, a co-author and an investor are not customers.",
    "partnership": "Two named companies agree to work together, integrate or "
                   "resell. Joining a programme, ecosystem, protocol, coalition "
                   "or marketplace alongside many others is not a partnership.",
    "acquisition": "The company buys another company or is bought.",
    "award": "Recognition: an award, ranking, analyst mention, certification, "
             "programme or ecosystem membership, or marketplace listing. Not "
             "a contract or funded award from a government or customer.",
    "hiring": "A named person has joined the company or been appointed to a role.",
    "research": "The company publishes a study, survey, benchmark or threat research.",
    "other": "Anything else: a newsletter, event, webinar, opinion, recap, "
             "financial results, promotion, or plans for the future.",
}


def _check_questions(item: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    q: Dict[str, Dict[str, Any]] = {
        "is_news": {
            "type": "noul",
            "instructions": ("Does `post` announce a specific new development at "
                             "the company that has happened: a launch, a deal, a "
                             "customer, a hire, a funding round, published research?"),
            "criteria": {
                "true": "It announces something specific the company has done or "
                        "that has happened to it, including a named customer's "
                        "deployment of its product or the results they got",
                "false": "It is commentary, a newsletter, event or webinar "
                         "promotion, a preview of something coming, a recap, or "
                         "coverage of another company"},
        },
        "kind": {
            "type": "choice",
            "instructions": "Which kind of development does `post` announce?",
            "criteria": KIND_CRITERIA,
        },
    }
    for field in ("headline", "summary"):
        if item.get(field):
            q[field] = {
                "type": "choice",
                "instructions": (f"How does `post` relate to `{field}`? Judge only "
                                 f"what the post states. A `{field}` that names the "
                                 "wrong company as the actor, turns an unnamed "
                                 "customer into a named one, or adds a detail the "
                                 "post lacks is not supported."),
                "criteria": _CHECK_CRITERIA}
    if item.get("headline"):
        # Who did it, not only whether the words are in the post: "SEP2
        # publishes case study on Spectrum Security deployment" passed the
        # support question at 0.92 for Spectrum's own post.
        q["actor"] = {
            "type": "noul",
            "instructions": ("`post` was published by `publisher`. Does `headline` "
                             "name the right company as the one that did what it "
                             "describes?"),
            "criteria": {
                "true": "The company the headline says acted is the one that did "
                        "it according to the post",
                "false": "The headline makes another company the actor: the "
                         "customer, a partner, a co-author or a publication"},
        }
    if item.get("headline") and item.get("summary"):
        # A true fact from elsewhere in the post is still the wrong summary:
        # Coalition's acquisition of Wirespeed was summarised with a Forrester
        # report the post also mentioned.
        q["summary_on_event"] = {
            "type": "noul",
            "instructions": "Is `summary` about the same development as `headline`?",
            "criteria": {
                "true": "It adds detail about the development the headline reports",
                "false": "It reports a different fact, event or topic from the post"},
        }
    if (item.get("customer") or {}).get("name"):
        q["customer"] = {
            "type": "noul",
            "instructions": ("`post` was published by `publisher`. According to "
                             "`post`, is `customer_name` an organisation that buys, "
                             "deploys or uses `publisher`'s product? A company that "
                             "co-wrote, published or partnered on something with "
                             "`publisher` is not its customer."),
            "criteria": {
                "true": "The post says it buys, runs, deploys, uses or is "
                        "evaluating the product, or is the subject of its "
                        "customer case study",
                "false": "It is a publisher, press outlet, partner, co-author, "
                         "investor, the company itself or its own product, or "
                         "the post does not say it uses the product"},
        }
    return q


def check_one(source_text: str, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Jev's reading of one reviewed post's five judgements, or None when Jev
    is not configured or did not answer."""
    from app.services import typesafe_client

    if not typesafe_client.is_configured():
        return None
    state: Dict[str, Any] = {"post": (source_text or "")[:CHECK_SOURCE_CHARS],
                             "publisher": item.get("vendor") or "the company"}
    for field in ("headline", "summary"):
        if item.get(field):
            state[field] = item[field]
    name = (item.get("customer") or {}).get("name")
    if name:
        state["customer_name"] = name
    out = typesafe_client.system_one(
        state, _check_questions(item),
        use_case="services.market_post_review:validate")
    if not out:
        return None
    answers = out.get("answers") or {}
    check: Dict[str, Any] = {"model": out.get("model")}
    for field in ("headline", "summary"):
        if field in answers:
            a = answers[field] or {}
            probs = a.get("probabilities") or {}
            check[field] = {"verdict": a.get("choice"),
                            "p_supports": round(float(probs.get("supports", 0.0)), 3),
                            "confidence": round(float(a.get("confidence") or 0.0), 3)}
    k = answers.get("kind") or {}
    probs = k.get("probabilities") or {}
    check["kind"] = {"choice": k.get("choice"),
                     "p_drafted": round(float(probs.get(item.get("kind"), 0.0)), 3),
                     "confidence": round(float(k.get("confidence") or 0.0), 3)}
    if "is_news" in answers:
        check["is_news"] = round(float((answers["is_news"] or {}).get("noul", 0.0)), 3)
    if "customer" in answers:
        check["customer"] = round(float((answers["customer"] or {}).get("noul", 0.0)), 3)
    for key in ("actor", "summary_on_event"):
        if key in answers:
            check[key] = round(float((answers[key] or {}).get("noul", 0.0)), 3)
    # Figures and names, checked by characters rather than by a model.
    from app.services.review_exact_checks import exact_objections
    exact = exact_objections(item.get("headline"), item.get("summary"),
                             source_text or "", [item.get("vendor") or ""])
    if exact:
        check["exact"] = exact
    return check


def passes(check: Optional[Dict[str, Any]], field: str) -> bool:
    """Whether the stored check lets ``field`` be shown. No check, no text:
    an unchecked headline is exactly what this exists to stop."""
    reading = (check or {}).get(field) or {}
    if any(x.startswith(f"the {field} ") for x in (check or {}).get("exact") or []):
        return False
    if field == "headline" and float((check or {}).get("actor", 1.0)) < ROLE_MIN:
        return False
    if field == "summary" and float((check or {}).get("summary_on_event", 1.0)) < ROLE_MIN:
        return False
    return (reading.get("verdict") == "supports"
            and float(reading.get("p_supports") or 0.0) >= CHECK_MIN_SUPPORT)


def objections(item: Dict[str, Any], check: Optional[Dict[str, Any]]) -> List[str]:
    """What Jev disputes in one signal, in words the corrector can act on."""
    if not check or item.get("verdict") != "signal":
        return []
    out: List[str] = []
    kind = item.get("kind")
    k = check.get("kind") or {}
    if kind in EVENT_KINDS and k.get("choice") != kind \
            and float(k.get("p_drafted") or 0.0) < KIND_MIN_SUPPORT:
        out.append(f'kind "{kind}" is not supported; the checker reads it as '
                   f'"{k.get("choice")}"')
    if kind in EVENT_KINDS and float(check.get("is_news", 1.0)) < NEWS_MIN:
        out.append("the checker does not read the post as announcing a specific "
                   "new development")
    if "customer" in check and float(check["customer"]) < CUSTOMER_MIN:
        out.append(f'"{(item.get("customer") or {}).get("name")}" is not shown by '
                   "the post to buy or use the product")
    if item.get("headline") and float(check.get("actor", 1.0)) < ROLE_MIN:
        out.append("the headline makes the wrong company the actor; the post was "
                   f"published by {item.get('vendor') or 'the vendor'}")
    if item.get("summary") and float(check.get("summary_on_event", 1.0)) < ROLE_MIN:
        out.append("the summary is about a different fact from the headline's "
                   "development")
    out.extend(check.get("exact") or [])
    for field in ("headline", "summary"):
        reading = check.get(field) or {}
        if item.get(field) and not (reading.get("verdict") == "supports" and
                                    float(reading.get("p_supports") or 0.0) >= CHECK_MIN_SUPPORT):
            out.append(f"the {field} is not supported by the post "
                       f"({reading.get('verdict') or 'no answer'})")
    return out


async def _validate(verdicts: List[Dict[str, Any]]) -> None:
    """Attach Jev's check to every signal, in place."""
    todo = [v for v in verdicts if v.get("verdict") == "signal"]
    gate = asyncio.Semaphore(_CHECK_CONCURRENCY)

    async def one(v: Dict[str, Any]) -> None:
        async with gate:
            try:
                v["check"] = await asyncio.to_thread(
                    check_one, v.get("source_text") or "", v)
            except Exception as exc:  # noqa: BLE001 — never fail the review over the check
                logger.warning("validation failed for %s: %s", v.get("uri"), exc)

    await asyncio.gather(*(one(v) for v in todo))


CORRECT_PROMPT = """You are correcting a first reading of vendor posts in the {market} market.
Another model read each post below and a checker disputed parts of its reading.
For each post, read the post itself and return a corrected reading. Keep what the
post supports and fix what the checker disputes, unless the post shows the first
reading was right. If the post does not announce a specific new development at
the company (it is commentary, a newsletter, event promotion, a preview, a recap,
or coverage of someone else), set "verdict" to "commentary" or "noise".

Kinds: launch, funding, customer, partnership, acquisition, award, hiring,
research, other.
{kinds}

For "customer": "name" is the organisation that buys or uses the product, exactly
as written, or null. A publisher, newsletter, partner, co-author, investor or the
vendor's own product is not the customer. "stage": in_use, evaluation,
case_study, existing or unclear.

"headline": at most 14 words, "<Company> <did what> <with whom or what>", third
person, only what the post states, no "we", no hype. "summary": one sentence of
at most 30 words about the same development, only facts the post states, or null.
For commentary and noise, headline, summary and customer are null.

Reply with a JSON array, one object per post, in the same order, no prose:
[{{"n": 1, "verdict": "signal", "kind": "launch", "headline": "...", "summary": "...",
  "customer": null, "reason": "<12 words or fewer>"}}]

Posts:
{posts}"""


def _corrector_model() -> str:
    """A stronger model than the drafter, so the correction is a second
    opinion and not the same reading again."""
    return os.getenv("MARKET_REVIEW_CORRECTOR_MODEL") or "claude-sonnet-4-5"


async def _correct(market_name: str, flagged: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """One call over the flagged posts. Returns corrected items by URI."""
    import litellm

    from app.ai_models import extract_json_response, resolve_litellm_call_params

    blocks = []
    for i, v in enumerate(flagged, 1):
        draft = {k: v.get(k) for k in ("verdict", "kind", "headline", "summary", "customer")}
        blocks.append(
            f"{i}. PUBLISHED BY: {v.get('vendor') or 'unknown'}\n"
            f"   POST: {(v.get('source_text') or '')[:CHECK_SOURCE_CHARS]}\n"
            f"   FIRST READING: {json.dumps(draft, ensure_ascii=False)}\n"
            f"   CHECKER DISPUTES: {'; '.join(v.get('objections') or []) or 'nothing; confirm or correct'}")
    kinds = "\n".join(f"- {k}: {d}" for k, d in KIND_CRITERIA.items())
    prompt = CORRECT_PROMPT.format(market=market_name, kinds=kinds,
                                   posts="\n\n".join(blocks))
    response = await litellm.acompletion(
        **resolve_litellm_call_params(_corrector_model()),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=min(8192, 350 * len(flagged) + 400),
        temperature=0,
    )
    parsed = extract_json_response((response.choices[0].message.content or "").strip())
    if isinstance(parsed, dict):
        parsed = parsed.get("results") or parsed.get("posts") or []
    out: Dict[str, Dict[str, Any]] = {}
    for item in parsed if isinstance(parsed, list) else []:
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 1 <= n <= len(flagged):
            out[flagged[n - 1]["uri"]] = item
    return out


def _apply_correction(v: Dict[str, Any], item: Dict[str, Any]) -> None:
    verdict = str(item.get("verdict") or v["verdict"]).strip().lower()
    if verdict not in VERDICTS:
        verdict = v["verdict"]
    kind = str(item.get("kind") or v["kind"]).strip().lower()[:24]
    before = {k: v.get(k) for k in ("verdict", "kind", "headline", "summary", "customer")}
    v["verdict"], v["kind"] = verdict, kind
    signal = verdict == "signal"
    v["headline"] = _written(item.get("headline"), 200) if signal else None
    v["summary"] = _written(item.get("summary"), 400) if signal else None
    v["customer"] = _customer_of({**item, "kind": kind}) if signal else None
    if item.get("reason"):
        v["reason"] = str(item["reason"]).strip()[:400]
    after = {k: v.get(k) for k in ("verdict", "kind", "headline", "summary", "customer")}
    # A second read that confirms is not a correction.
    if after != before:
        v["first_draft"] = before


def _hold_what_is_unconfirmed(v: Dict[str, Any]) -> None:
    """After correction: publish only what the checker confirms."""
    check = v.get("check")
    remaining = objections(v, check)
    if not check or not remaining:
        return
    k = check.get("kind") or {}
    kind_disputed = (v.get("kind") in EVENT_KINDS and k.get("choice") != v.get("kind")
                     and float(k.get("p_drafted") or 0.0) < KIND_MIN_SUPPORT)
    not_news = v.get("kind") in EVENT_KINDS and float(check.get("is_news", 1.0)) < NEWS_MIN
    if kind_disputed or not_news:
        # Not published. Recorded, so the held items can be read and counted.
        check["held"] = "; ".join(remaining)
        v["verdict"] = "commentary"
        v["headline"] = v["summary"] = v["customer"] = None
        return
    if "customer" in check and float(check["customer"]) < CUSTOMER_MIN and v.get("customer"):
        v["customer"] = {**v["customer"], "name": None, "speaker": "vendor"}
        check["customer_dropped"] = True


async def validate_and_correct(market_name: str, verdicts: List[Dict[str, Any]]) -> Dict[str, int]:
    """Validate every signal with Jev, correct what it disputes with a second
    model, validate again, and hold back what is still unconfirmed. In place."""
    await _validate(verdicts)
    flagged = []
    for v in verdicts:
        v["objections"] = objections(v, v.get("check"))
        # Every item that can reach the page gets a second reading, disputed
        # or not: the featured item on 26 Sep was a newsletter every check
        # had passed.
        if v["objections"] or (v.get("verdict") == "signal"
                               and v.get("kind") in EVENT_KINDS):
            flagged.append(v)
    corrected = 0
    if flagged:
        try:
            fixes = await _correct(market_name, flagged)
        except Exception as exc:  # noqa: BLE001 — the uncorrected reading is still held below
            logger.warning("correction failed for %d posts: %s", len(flagged), exc)
            fixes = {}
        for v in flagged:
            if v["uri"] in fixes:
                _apply_correction(v, fixes[v["uri"]])
                corrected += int(bool(v.get("first_draft")))
        await _validate([v for v in flagged if v["uri"] in fixes])
    held = 0
    for v in verdicts:
        if v.get("first_draft") and v.get("check") is not None:
            v["check"]["corrected"] = True
            v["check"]["first_draft"] = v["first_draft"]
            v["check"]["objections"] = v.get("objections")
        if v.get("check") is not None and v.get("verdict") == "signal":
            v["check"]["second_read"] = bool(v.get("first_draft")) or bool(
                v.get("kind") in EVENT_KINDS)
        before = v["verdict"]
        _hold_what_is_unconfirmed(v)
        held += int(before == "signal" and v["verdict"] != "signal")
    return {"flagged": len(flagged), "corrected": corrected, "held": held}


# Kept for callers that only want the writing checked.
async def check_writing(verdicts: List[Dict[str, Any]]) -> None:
    await _validate(verdicts)


def _written(value: Any, limit: int) -> Optional[str]:
    """A headline or summary the model wrote, or None for anything empty."""
    text_value = re.sub(r"\s+", " ", str(value or "")).strip().strip('"')
    if not text_value or text_value.lower() in ("null", "none", "n/a"):
        return None
    return text_value[:limit]


def store(conn, market_id: int, verdicts: List[Dict[str, Any]],
          model: str) -> int:
    """Write verdicts, creating the row when a post matched no phrase.

    ``score`` is left NULL rather than set to 0 for a post that arrived through
    review: it was never phrase-scored, and a zero would read as "scored, and
    scored nothing".
    """
    written = 0
    for v in verdicts:
        customer = v.get("customer")
        if v.get("followed"):
            # A followed account's post: the judge decides whether it joins
            # the market at all. Noise stays off the market, marked so it is
            # not read again; signal or commentary attaches it.
            conn.execute(text("""
                UPDATE articles
                   SET social_meta = COALESCE(social_meta, '{}'::jsonb) - 'pending_review'
                                     || jsonb_build_object('follow_verdict', CAST(:verdict AS TEXT))
                 WHERE uri = :uri
            """), {"uri": v["uri"], "verdict": v["verdict"]})
            if v["verdict"] == "noise":
                written += 1
                continue
            method, origin = "watchlist", "follow"
        else:
            method, origin = "post_review", "corpus"
        conn.execute(text("""
            INSERT INTO bw_market_articles
                (market_id, article_uri, method, origin,
                 review_verdict, review_kind, review_reason, review_customer,
                 review_headline, review_summary, review_check,
                 review_model, reviewed_at)
            VALUES (:m, :uri, :method, :origin,
                    :verdict, :kind, :reason, CAST(:customer AS JSONB),
                    :headline, :summary, CAST(:check AS JSONB),
                    :model, NOW())
            ON CONFLICT (market_id, article_uri) DO UPDATE SET
                review_verdict  = EXCLUDED.review_verdict,
                review_kind     = EXCLUDED.review_kind,
                review_reason   = EXCLUDED.review_reason,
                review_customer = EXCLUDED.review_customer,
                review_headline = EXCLUDED.review_headline,
                review_summary  = EXCLUDED.review_summary,
                review_check    = EXCLUDED.review_check,
                review_model    = EXCLUDED.review_model,
                reviewed_at     = NOW()
        """), {"m": market_id, "uri": v["uri"], "verdict": v["verdict"],
               "kind": v["kind"], "reason": v["reason"], "model": model,
               "method": method, "origin": origin,
               "customer": json.dumps(customer) if customer else None,
               "headline": v.get("headline"), "summary": v.get("summary"),
               "check": json.dumps(v["check"]) if v.get("check") else None})
        written += 1
    return written


CUSTOMER_PROMPT = """Each post below was published by a vendor in the {market} market and
announces a customer. For each one, say what it tells a reader about that
customer.

- "name": the organisation named as the customer, exactly as written, or null
  when no organisation is named. A description is not a name: "a Fortune 500
  retailer", "one of our customers", "three banks" and "multiple federal
  agencies" are all null. A pronoun is not a name: "they", "the team", "this
  company" are null. A person's name is not an organisation. The vendor itself,
  its own products and platforms, a partner or reseller delivering the deal,
  and a company that co-wrote or published the case study, are not the
  customer.
- "speaker": "customer" when a named person from the customer is quoted or
  presented speaking about it; otherwise "vendor".
- "stage": "in_use" when the customer is running it; "evaluation" when they are
  evaluating, piloting or trialling it; "case_study" only when the post says a
  case study or customer story has been published (it names or links to it); a
  story told in the post itself is not a published case study; "existing" when
  it is a business review or visit with a customer already using it; otherwise
  "unclear".

Judge only what the text actually says. Reply with a JSON array, one object per
post, in the same order, no prose:
[{{"n": 1, "name": "Virgin Money", "speaker": "customer", "stage": "in_use"}},
 {{"n": 2, "name": null, "speaker": "vendor", "stage": "case_study"}}]

Posts:
{posts}"""


def customer_candidates(conn, market_id: int, *, limit: int = 200,
                        redo: bool = False) -> List[Dict[str, Any]]:
    """Posts already judged "customer" that have no customer reading yet."""
    where = ["ma.market_id = :m", "ma.review_kind = 'customer'"]
    if not redo:
        where.append("ma.review_customer IS NULL")
    rows = conn.execute(text(f"""
        SELECT DISTINCT ON (a.uri)
               a.uri, a.title, a.summary, b.display_name AS vendor
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        JOIN bw_article_categories bac ON bac.article_uri = a.uri
        JOIN bw_market_brands mb ON mb.brand_id = bac.brand_id
                                 AND mb.market_id = ma.market_id
        JOIN bw_brands b ON b.id = bac.brand_id
        WHERE {' AND '.join(where)}
        ORDER BY a.uri
        LIMIT :lim
    """), {"m": market_id, "lim": int(limit)}).mappings().all()
    return [dict(r) for r in rows]


async def _read_customers(market_name: str, posts: List[Dict[str, Any]],
                          model: str) -> Dict[str, Dict[str, Any]]:
    """One model call over one batch of customer posts. uri -> reading."""
    import litellm

    from app.ai_models import extract_json_response, resolve_litellm_call_params

    prompt = CUSTOMER_PROMPT.format(market=market_name, posts=_render(posts))
    response = await litellm.acompletion(
        **resolve_litellm_call_params(model),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=min(4096, 120 * len(posts) + 300),
    )
    parsed = extract_json_response((response.choices[0].message.content or "").strip())
    if isinstance(parsed, dict):
        parsed = parsed.get("results") or parsed.get("posts") or []
    if not isinstance(parsed, list):
        raise ValueError(f"model returned {type(parsed).__name__}, not a list")
    out: Dict[str, Dict[str, Any]] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        if not 1 <= n <= len(posts):
            continue
        reading = _customer_of({"kind": "customer", "customer": item})
        if reading:
            out[posts[n - 1]["uri"]] = reading
    return out


async def read_customers(conn, market_id: int, market_name: str, *,
                         limit: int = 200, batch: int = DEFAULT_BATCH,
                         redo: bool = False) -> Dict[str, Any]:
    """Fill in the customer reading for posts judged "customer" without one.

    Separate from ``review`` on purpose. Re-running the review prompt over
    posts it has already judged re-rolls the verdict — a redo over 29 customer
    posts moved 11 of them to noise or another kind — and the verdict is meant
    to be given once. This pass takes the verdict as given and asks only the
    three customer questions.
    """
    model = _model()
    posts = customer_candidates(conn, market_id, limit=limit, redo=redo)
    result: Dict[str, Any] = {"model": model, "candidates": len(posts),
                              "read": 0, "batches": 0, "failed_batches": 0}
    for start in range(0, len(posts), batch):
        chunk = posts[start:start + batch]
        result["batches"] += 1
        try:
            readings = await _read_customers(market_name, chunk, model)
        except Exception as exc:  # noqa: BLE001
            result["failed_batches"] += 1
            logger.warning("customer reading batch failed (%d posts): %s",
                           len(chunk), exc)
            continue
        for uri, reading in readings.items():
            conn.execute(text("""
                UPDATE bw_market_articles
                   SET review_customer = CAST(:customer AS JSONB)
                 WHERE market_id = :m AND article_uri = :uri
            """), {"m": market_id, "uri": uri, "customer": json.dumps(reading)})
            result["read"] += 1
        conn.commit()
    return result


async def review(conn, market_id: int, market_name: str, *,
                 limit: int = 200, batch: int = DEFAULT_BATCH,
                 days: Optional[int] = None, redo: bool = False,
                 kinds: Optional[List[str]] = None,
                 dry_run: bool = False) -> Dict[str, Any]:
    """Read unreviewed vendor posts and record what each one is."""
    model = _model()
    posts = candidates(conn, market_id, limit=limit, days=days, redo=redo,
                       kinds=kinds)
    result: Dict[str, Any] = {
        "model": model, "candidates": len(posts), "reviewed": 0,
        "batches": 0, "failed_batches": 0, "dry_run": dry_run,
        "counts": {v: 0 for v in VERDICTS}, "samples": [],
    }
    if not posts or dry_run:
        result["samples"] = [
            {"vendor": p["vendor"], "title": p["title"]} for p in posts[:10]]
        return result

    for start in range(0, len(posts), batch):
        chunk = posts[start:start + batch]
        result["batches"] += 1
        try:
            verdicts = await _judge(market_name, chunk, model)
        except Exception as exc:  # noqa: BLE001 — one bad batch is not a failed run
            result["failed_batches"] += 1
            logger.warning("post review batch failed (%d posts): %s",
                           len(chunk), exc)
            continue
        loop_stats = await validate_and_correct(market_name, verdicts)
        for key, n in loop_stats.items():
            result.setdefault("validation", {}).setdefault(key, 0)
            result["validation"][key] += n
        by_uri = {p["uri"]: p for p in chunk}
        for v in verdicts:
            result["counts"][v["verdict"]] += 1
            if v["verdict"] == "signal" and len(result["samples"]) < 15:
                post = by_uri.get(v["uri"], {})
                result["samples"].append({
                    "vendor": post.get("vendor"), "title": post.get("title"),
                    "kind": v["kind"], "reason": v["reason"],
                })
        result["reviewed"] += store(conn, market_id, verdicts, model)
        conn.commit()

    # Customer posts judged before the reading existed, or whose reading the
    # model left out, get it here without their verdict being re-asked.
    try:
        result["customers"] = await read_customers(conn, market_id, market_name,
                                                   limit=limit, batch=batch)
    except Exception as exc:  # noqa: BLE001
        logger.warning("customer reading pass failed: %s", exc)
    return result


# ---------------------------------------------------------------------------
# Earned coverage — candidates, judgement, storage
# ---------------------------------------------------------------------------

#: Registry terms shorter than this are not scanned for on their own. "Arc",
#: "Hunt" and "Radiant" are company names and also ordinary words, and the
#: registry already marks those ``qualification_required``; this is a floor
#: under the ones it has not marked.
EARNED_MIN_TERM = 4


def _earned_press_sql(alias: str = "a") -> str:
    """Trade press: not a social post, not the company's own publishing.

    ``social_sources.earned_news_sql`` is the house predicate and would be the
    obvious thing to call, but it also requires ``analyzed = true``. That gate
    exists for Brand Watcher's metric queries, where an unenriched row would
    skew a count. Nothing here reads an enrichment field — the model is given
    the title and summary, which every row has — and the gate would discard 93
    of 249 earned articles in the AI-SOC corpus. Dropping a third of the
    scarcest input to satisfy a gate written for a different purpose would
    defeat the feature, so the two source tests are used without it.
    """
    from app.services.social_sources import owned_src_sql, social_src_sql

    return (f"NOT {social_src_sql(alias + '.news_source')}"
            f" AND NOT {owned_src_sql(alias + '.bias_source')}")


def earned_candidates(conn, market_id: int, *, limit: int = 100,
                      days: Optional[int] = None,
                      redo: bool = False) -> List[Dict[str, Any]]:
    """Trade-press articles naming at least one of the market's vendors.

    The term scan is a prefilter, not an attribution. It answers "is it worth
    paying a model to read this", and the model decides who the article is
    actually about. A term that appears only in the body still qualifies the
    article for reading, because a funding story often names the company once
    in the lede and the scan cannot tell the lede from the tail.

    Terms come from ``bw_entity_query_terms``, which the registry already
    maintains, so a vendor whose display name differs from how the press
    writes it is found through its aliases.
    """
    where = ["ma.market_id = :m", _earned_press_sql("a")]
    params: Dict[str, Any] = {"m": market_id, "lim": int(limit),
                              "minlen": EARNED_MIN_TERM}
    if not redo:
        where.append("ma.review_verdict IS NULL")
    if days:
        from datetime import timedelta

        where.append("COALESCE(a.publication_date, a.submission_date) >= :since")
        params["since"] = (datetime.now(timezone.utc)
                           - timedelta(days=int(days))).strftime("%Y-%m-%dT%H:%M:%S")

    rows = conn.execute(text(f"""
        SELECT a.uri, a.title, a.summary, a.news_source, a.url,
               COALESCE(a.publication_date, a.submission_date) AS published,
               ARRAY(
                   SELECT DISTINCT b.display_name
                     FROM bw_entity_query_terms t
                     JOIN bw_brands b ON b.id = t.brand_id
                     JOIN bw_market_brands mb ON mb.brand_id = t.brand_id
                                             AND mb.market_id = ma.market_id
                    WHERE t.enabled
                      AND mb.role <> 'excluded'
                      AND LENGTH(t.normalized_term) >= :minlen
                      AND (a.title ILIKE '%' || t.term || '%'
                           OR a.summary ILIKE '%' || t.term || '%')
                    LIMIT {EARNED_MAX_CANDIDATES}
               ) AS vendors
          FROM bw_market_articles ma
          JOIN articles a ON a.uri = ma.article_uri
         WHERE {' AND '.join(where)}
           -- Naming a vendor is a condition of selection, not a filter applied
           -- afterwards. Left to Python, ``limit`` would bound the *scan*: a
           -- limit of 10 returned the ten newest earned articles and then kept
           -- the one that named a vendor. The caller is budgeting model calls,
           -- so the limit has to count articles that will actually be read.
           AND EXISTS (
               SELECT 1
                 FROM bw_entity_query_terms t
                 JOIN bw_market_brands mb ON mb.brand_id = t.brand_id
                                          AND mb.market_id = ma.market_id
                WHERE t.enabled
                  AND mb.role <> 'excluded'
                  AND LENGTH(t.normalized_term) >= :minlen
                  AND (a.title ILIKE '%' || t.term || '%'
                       OR a.summary ILIKE '%' || t.term || '%'))
         ORDER BY COALESCE(a.publication_date, a.submission_date) DESC
         LIMIT :lim
    """), params).mappings().all()

    return [dict(r) for r in rows if r["vendors"]]


def _render_earned(posts: List[Dict[str, Any]]) -> str:
    lines = []
    for i, post in enumerate(posts, 1):
        body = (post.get("summary") or "").strip().replace("\n", " ")
        named = ", ".join(post.get("vendors") or [])
        lines.append(f"{i}. {post.get('title') or ''}\n"
                     f"   {body[:SUMMARY_CHARS]}\n"
                     f"   companies named: {named}")
    return "\n".join(lines)


async def _judge_earned(market_name: str, posts: List[Dict[str, Any]],
                        model: str) -> List[Dict[str, Any]]:
    """One model call over one batch of trade-press articles."""
    import litellm

    from app.ai_models import extract_json_response, resolve_litellm_call_params

    prompt = EARNED_PROMPT.format(market=market_name,
                                  posts=_render_earned(posts))
    response = await litellm.acompletion(
        **resolve_litellm_call_params(model),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=min(4096, 220 * len(posts) + 400),
    )
    raw = (response.choices[0].message.content or "").strip()
    parsed = extract_json_response(raw)
    if isinstance(parsed, dict):
        parsed = parsed.get("results") or parsed.get("articles") or []
    if not isinstance(parsed, list):
        raise ValueError(f"model returned {type(parsed).__name__}, not a list")

    by_index: Dict[int, Dict[str, Any]] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= len(posts):
            by_index[n] = item

    out = []
    for i, post in enumerate(posts, 1):
        item = by_index.get(i)
        if not item:
            continue
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in VERDICTS:
            continue
        kind = (str(item.get("kind") or "other").strip().lower())[:24]
        company = (str(item.get("company") or "").strip() or None)

        # The prompt states both rules; models agree and then do it anyway, so
        # each is enforced here too. An article about nobody cannot be signal,
        # whatever the model called it.
        if company is None and verdict == "signal":
            verdict = "commentary" if kind not in ("event", "other") else "noise"
        if kind in ("event", "opinion") and verdict == "signal":
            verdict = "commentary" if kind == "opinion" else "noise"

        # The model must pick from the list it was shown. A name it invented,
        # or one belonging to a company we did not offer, is dropped rather
        # than matched loosely — attributing an event to the wrong vendor is
        # worse than attributing it to none.
        offered = {v.lower(): v for v in (post.get("vendors") or [])}
        matched = offered.get((company or "").lower())
        if company and not matched:
            company, verdict = None, ("noise" if verdict == "signal" else verdict)

        out.append({
            "uri": post["uri"],
            "verdict": verdict,
            "kind": kind,
            "reason": (str(item.get("reason") or "").strip())[:400],
            "vendor": matched,
        })
    return out


def store_earned(conn, market_id: int, verdicts: List[Dict[str, Any]],
                 model: str) -> int:
    """Write the verdict, and link the article to the company it is about.

    The link is what the ``coverage`` extractor reads. It is written on the
    ``earned_news`` channel, which is what makes the evidence independent when
    the extractor keys it: a publisher's domain is one voice, and it is not
    the vendor's.
    """
    from app.services import entity_content

    written = 0
    for v in verdicts:
        conn.execute(text("""
            UPDATE bw_market_articles
               SET review_verdict = :verdict,
                   review_kind    = :kind,
                   review_reason  = :reason,
                   review_model   = :model,
                   reviewed_at    = NOW()
             WHERE market_id = :m AND article_uri = :uri
        """), {"m": market_id, "uri": v["uri"], "verdict": v["verdict"],
               "kind": v["kind"], "reason": v["reason"], "model": model})

        if v.get("vendor"):
            brand_id = conn.execute(text("""
                SELECT b.id FROM bw_brands b
                 JOIN bw_market_brands mb ON mb.brand_id = b.id
                                         AND mb.market_id = :m
                WHERE b.display_name = :name
                LIMIT 1
            """), {"m": market_id, "name": v["vendor"]}).scalar()
            if brand_id:
                entity_content.link_content(
                    conn, brand_id=int(brand_id), article_uri=v["uri"],
                    relationship="about", channel="earned_news",
                    attribution_method="classifier",
                    metadata={"model": model, "kind": v["kind"]})
        written += 1
    return written


async def review_earned(conn, market_id: int, market_name: str, *,
                        limit: int = 100, batch: int = DEFAULT_BATCH,
                        days: Optional[int] = None, redo: bool = False,
                        dry_run: bool = False) -> Dict[str, Any]:
    """Read unreviewed trade-press articles and record who and what."""
    model = _model()
    posts = earned_candidates(conn, market_id, limit=limit, days=days,
                              redo=redo)
    result: Dict[str, Any] = {
        "model": model, "candidates": len(posts), "reviewed": 0,
        "batches": 0, "failed_batches": 0, "dry_run": dry_run,
        "attributed": 0, "counts": {v: 0 for v in VERDICTS}, "samples": [],
    }
    if not posts or dry_run:
        result["samples"] = [{"title": p["title"], "vendors": p["vendors"]}
                             for p in posts[:10]]
        return result

    for start in range(0, len(posts), batch):
        chunk = posts[start:start + batch]
        result["batches"] += 1
        try:
            verdicts = await _judge_earned(market_name, chunk, model)
        except Exception as exc:  # noqa: BLE001 — one bad batch is not a failed run
            result["failed_batches"] += 1
            logger.warning("earned review batch failed (%d articles): %s",
                           len(chunk), exc)
            continue
        by_uri = {p["uri"]: p for p in chunk}
        for v in verdicts:
            result["counts"][v["verdict"]] += 1
            if v.get("vendor"):
                result["attributed"] += 1
            if v["verdict"] == "signal" and len(result["samples"]) < 15:
                result["samples"].append({
                    "vendor": v.get("vendor"),
                    "title": by_uri.get(v["uri"], {}).get("title"),
                    "kind": v["kind"], "reason": v["reason"],
                })
        result["reviewed"] += store_earned(conn, market_id, verdicts, model)
        conn.commit()
    return result


# ---------------------------------------------------------------------------
# Practitioner posts: is it about this market, and does it say anything?
# ---------------------------------------------------------------------------
#
# The Social panel was filtered by phrases alone, so a political joke reply
# ("@PnL63962200 Hamas in response: We have AI SOC") matched "AI SOC" and was
# shown. Each practitioner post is now read once by Jev, and the verdict is
# stored under review_check.social. The page shows a post only when both
# answers pass. An unchecked post (Jev unreachable, or not read yet) is
# shown on the phrase filters, and read on the next pass.

#: Least probability for a practitioner post to be shown.
SOCIAL_MIN = 0.5
#: At or above this, a practitioner post is a company advertising itself
#: (@splunk on its own launch, @lumutech on its patent).
SELF_PROMO_MAX = 0.6


def _social_questions(market_name: str, terms: List[str]) -> Dict[str, Dict[str, Any]]:
    about = f"{market_name}" + (f" ({', '.join(terms[:8])})" if terms else "")
    return {
        "on_topic": {
            "type": "noul",
            "instructions": f"Is `post` about {about}?",
            "criteria": {
                "true": "It discusses this market, its products, its vendors, or how "
                        "the people who buy or use them judge them",
                "false": "It is about something else and only uses the words in "
                         "passing, as a joke, or about another field"},
        },
        "self_promotion": {
            "type": "noul",
            "instructions": ("Is `post` a company promoting its own product, event, "
                             "patent or achievement?"),
            "criteria": {
                "true": "The author is the company, or speaks for it, and the post "
                        "advertises what that company does or has won",
                "false": "Someone else's view, news about another company, or an "
                         "independent practitioner's own experience"},
        },
        "substance": {
            "type": "noul",
            "instructions": ("Does `post` say something a practitioner in this market "
                             "would find informative: a view with a reason, an "
                             "experience, news, or analysis?"),
            "criteria": {
                "true": "It makes a point, reports something, or shares experience",
                "false": "It is a joke, a bare reply or reaction, a promotion, a job "
                         "or training post, or chatter with no point"},
        },
    }


def check_social_one(text_value: str, market_name: str,
                     terms: List[str]) -> Optional[Dict[str, Any]]:
    from app.services import typesafe_client

    if not typesafe_client.is_configured() or not (text_value or "").strip():
        return None
    out = typesafe_client.system_one(
        {"post": text_value[:CHECK_SOURCE_CHARS]},
        _social_questions(market_name, terms),
        use_case="services.market_post_review:check_social")
    if not out:
        return None
    a = out.get("answers") or {}
    return {"on_topic": round(float((a.get("on_topic") or {}).get("noul", 0.0)), 3),
            "substance": round(float((a.get("substance") or {}).get("noul", 0.0)), 3),
            "self_promotion": round(float((a.get("self_promotion") or {}).get("noul", 0.0)), 3),
            "model": out.get("model")}


def social_passes(row: Dict[str, Any]) -> bool:
    """Whether a practitioner post may be shown: hidden only when Jev read it
    and turned it away. An unchecked post falls back to the phrase filters,
    because "unchecked" includes "Jev could not be reached" — the TypeSafe
    credits ran out on 26 Sep 2026, and hiding unchecked posts would have
    emptied the panel."""
    check = (row.get("review_check") or {}).get("social")
    if not isinstance(check, dict):
        return True
    return (float(check.get("on_topic") or 0.0) >= SOCIAL_MIN
            and float(check.get("substance") or 0.0) >= SOCIAL_MIN
            and float(check.get("self_promotion") or 0.0) < SELF_PROMO_MAX)


def check_social_posts(market_id: int, *, days: int = 31, limit: int = 600,
                       redo: bool = False) -> Dict[str, int]:
    """Check every unchecked practitioner post in the window. Synchronous and
    on its own connection, so a caller can run it in a worker thread."""
    import concurrent.futures

    from app.database import get_database_instance
    from app.services.market_collect import market_terms

    conn = get_database_instance()._temp_get_connection()
    try:
        name = conn.execute(text("SELECT name FROM bw_markets WHERE id = :m"),
                            {"m": market_id}).scalar() or ""
        terms = market_terms(conn, market_id)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        rows = conn.execute(text("""
            SELECT ma.article_uri, a.title, a.summary
              FROM bw_market_articles ma
              JOIN articles a ON a.uri = ma.article_uri
             WHERE ma.market_id = :m
               AND a.social_meta IS NOT NULL
               AND a.social_meta->>'author' IS NOT NULL
               AND COALESCE(a.bias_source, '') <> 'vendor:linkedin'
               AND COALESCE(a.publication_date, a.submission_date) >= :since
               AND (:redo OR ma.review_check IS NULL OR NOT (ma.review_check ? 'social'))
             ORDER BY COALESCE(a.publication_date, a.submission_date) DESC
             LIMIT :lim
        """), {"m": market_id, "since": since, "lim": int(limit),
               "redo": bool(redo)}).fetchall()
        conn.rollback()

        def one(r):
            body = f"{r[1] or ''}\n{r[2] or ''}".strip()
            return r[0], check_social_one(body, name, terms)

        with concurrent.futures.ThreadPoolExecutor(max_workers=_CHECK_CONCURRENCY) as pool:
            results = list(pool.map(one, rows))
        stored = shown = 0
        for uri, check in results:
            if not check:
                continue
            conn.execute(text("""
                UPDATE bw_market_articles
                   SET review_check = COALESCE(review_check, '{}'::jsonb)
                                      || jsonb_build_object('social', CAST(:c AS JSONB))
                 WHERE market_id = :m AND article_uri = :u
            """), {"c": json.dumps(check), "m": market_id, "u": uri})
            stored += 1
            shown += int(social_passes({"review_check": {"social": check}}))
        conn.commit()
        return {"candidates": len(rows), "checked": stored, "shown": shown}
    finally:
        conn.close()
