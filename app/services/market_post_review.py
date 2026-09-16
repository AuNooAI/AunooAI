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

import json
import logging
import os
from datetime import datetime, timezone
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

# Body text sent per post. A LinkedIn post's point is in its first lines; the
# rest is hashtags.
SUMMARY_CHARS = 600

PROMPT = """You are screening posts published by vendors in the {market} market.

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

A hire is signal only when the post says someone has joined or been appointed.
A customer is signal only when the customer is named or the deal is described.
A launch is signal only when the post announces that a specific, named product
or capability is now available, shipped or released, and kind "launch" is only
for that. A post that argues a point, explains what the product does in general,
comments on a threat, breach or vulnerability, marks an anniversary, or points
to a webinar, podcast, interview, playbook or newsletter is not a launch: its
kind is "opinion" (or "research" for a finding, "event" for the webinar).
Naming the product is not enough — the post has to say something new has shipped
or is now available. When in doubt between "launch" and "opinion", choose
"opinion".

For kind "customer" only, also give a "customer" object (the kind stays
"customer"; the values below are not kinds):
- "name": the organisation named as the customer, exactly as written, or null
  when no organisation is named. A description is not a name: "a Fortune 500
  retailer", "one of our customers", "three banks" and "multiple federal
  agencies" are all null. A person's name is not an organisation. The vendor
  itself, and a partner or reseller delivering the deal, are not the customer.
- "speaker": "customer" when a named person from the customer is quoted or
  presented speaking about it; otherwise "vendor".
- "stage": "in_use" when the customer is running it; "evaluation" when they are
  evaluating, piloting or trialling it; "case_study" when the post presents a
  published case study or customer story; "existing" when it is a business
  review or visit with a customer already using it; otherwise "unclear".

Judge only what the text actually says. A post that gestures at a big claim
without stating anything specific is noise, however important it sounds. Being
written by a vendor does not by itself make a post noise, and a post being
enthusiastic does not make it signal. When a post is on the line between
signal and commentary or between commentary and noise, choose the lower one.

Reply with a JSON array, one object per post, in the same order, no prose:
[{{"n": 1, "verdict": "signal", "kind": "launch", "reason": "<12 words or fewer>"}},
 {{"n": 2, "verdict": "signal", "kind": "customer", "reason": "<12 words or fewer>",
   "customer": {{"name": "Virgin Money", "speaker": "customer", "stage": "in_use"}}}}]

Posts:
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

    where = ["a.bias_source = 'vendor:linkedin'", own_voice_sql("a")]
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
        body = (post.get("summary") or "").strip().replace("\n", " ")
        lines.append(f"{i}. [{post.get('vendor')}] {post.get('title') or ''}\n"
                     f"   {body[:SUMMARY_CHARS]}")
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
        max_tokens=min(4096, 220 * len(posts) + 400),
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
            "followed": bool(post.get("followed")),
        })
    return out


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
                 review_model, reviewed_at)
            VALUES (:m, :uri, :method, :origin,
                    :verdict, :kind, :reason, CAST(:customer AS JSONB),
                    :model, NOW())
            ON CONFLICT (market_id, article_uri) DO UPDATE SET
                review_verdict  = EXCLUDED.review_verdict,
                review_kind     = EXCLUDED.review_kind,
                review_reason   = EXCLUDED.review_reason,
                review_customer = EXCLUDED.review_customer,
                review_model    = EXCLUDED.review_model,
                reviewed_at     = NOW()
        """), {"m": market_id, "uri": v["uri"], "verdict": v["verdict"],
               "kind": v["kind"], "reason": v["reason"], "model": model,
               "method": method, "origin": origin,
               "customer": json.dumps(customer) if customer else None})
        written += 1
    return written


CUSTOMER_PROMPT = """Each post below was published by a vendor in the {market} market and
announces a customer. For each one, say what it tells a reader about that
customer.

- "name": the organisation named as the customer, exactly as written, or null
  when no organisation is named. A description is not a name: "a Fortune 500
  retailer", "one of our customers", "three banks" and "multiple federal
  agencies" are all null. A person's name is not an organisation. The vendor
  itself, and a partner or reseller delivering the deal, are not the customer.
- "speaker": "customer" when a named person from the customer is quoted or
  presented speaking about it; otherwise "vendor".
- "stage": "in_use" when the customer is running it; "evaluation" when they are
  evaluating, piloting or trialling it; "case_study" when the post presents a
  published case study or customer story; "existing" when it is a business
  review or visit with a customer already using it; otherwise "unclear".

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
