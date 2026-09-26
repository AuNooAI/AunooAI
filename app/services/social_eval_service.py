"""Lightweight relevance + sentiment evaluation for social posts (Reddit/Bluesky).

Social monitoring is high-volume, so each post gets a single cheap model call
(default a local/Bedrock model, not GPT) returning:
    {"relevance": 0.0-1.0, "sentiment": "positive"|"neutral"|"negative"}

"relevance" = is this post actually about the brand/topic (vs. an ambiguous
name match — e.g. "Wiley" the rapper vs Wiley the publisher). Results are stored
in the existing columns: topic_alignment_score / keyword_relevance_score (relevance)
and sentiment. This is intentionally lighter than the full hybrid DeBERTa +
embedding + LLM stack used for news.

The model is configurable via SOCIAL_EVAL_MODEL (default "gemma3:4b"). If the
model is unreachable (not provisioned), evaluation is skipped cleanly and the
posts simply remain unscored.
"""
import os
import re
import json
import asyncio
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_SOCIAL_EVAL_MODEL = "gemma3:4b"
_CALL_TIMEOUT_S = 90  # hard cap per model call; wedged provider sockets must not stall batches
# Canonical definition lives in social_sources; re-exported here because many
# consumers (routes, monitors) historically import it from this module.
from app.services.social_sources import SOCIAL_SOURCES, is_social_source  # noqa: F401
_MAX_CONCURRENT = 6  # cap parallel model calls

# Who wrote the post. A brand hears its audiences apart only if each post
# says who is speaking: a GP prescribing a programme is not a patient on it,
# and neither is the company's own account. Generic on purpose, so the same
# list serves a health provider (patient / clinician), a publisher
# (customer / academic / professional) and a security vendor (customer /
# professional). "unknown" is the honest default when the text gives no clue.
AUTHOR_ROLES = (
    "patient",       # uses or has been referred to a health service or treatment
    "caregiver",     # family member or carer speaking for a patient
    "clinician",     # doctor, GP, nurse, dietitian, pharmacist, therapist, other health professional
    "dental_professional",  # dentist, hygienist, dental clinic or dental student speaking as such
    "customer",      # end user or buyer of a non-health product/service, incl. prospective
    "academic",      # researcher, lecturer, scientist speaking as such
    "professional",  # works in the brand's industry but not for the brand (analyst, librarian, consultant, commissioner)
    "employee",      # works or worked for the brand
    "journalist",    # press, media outlet account, newsletter author
    "investor",      # shareholder, analyst covering the stock, VC
    "brand",         # the company itself, an affiliate or paid promotion
    "retailer",      # shop, pharmacy, online seller or distributor selling the brand's products
    "competitor",    # a rival company in the brand's market, its staff or its paid promotion
    "unknown",
)

_ROLE_GUIDE = (
    "Judge the role from what the post says and how the author speaks. If the BRAND CONTEXT "
    "describes a health, medical, care or treatment service, anyone using it, on it, referred "
    "to it, prescribed it, or logging their own progress with it is a patient, never a "
    "customer; customer is for non-health products and services only. Anyone who prescribes, "
    "refers, treats, or speaks as a doctor, GP, nurse, dietitian, pharmacist or therapist is a "
    "clinician, including when they say 'we' or 'us' about patients or about being asked to "
    "prescribe. A dentist, dental hygienist, orthodontist, dental clinic or dental student "
    "speaking as such is a dental_professional, not a clinician. A relative or carer describing "
    "someone else's care is a caregiver. An outlet or reporter is a journalist. A shop, "
    "pharmacy, online seller or distributor offering the brand's products for sale is a "
    "retailer; a recipe, review, comparison or affiliate account that links to the brand but "
    "does not sell its products is not: a review or comparison site is a journalist, and a "
    "recipe account that only names the brand as an ingredient or tag is unknown. Anyone "
    "describing the brand's product in their own routine, purchase, haul or use is a customer "
    "(or a patient, as above), even without saying 'I use'. Memes, jokes and commentary about the "
    "company that show no use of its products are unknown. A post marked #ad, #PR, gifted, "
    "sponsored or affiliate that promotes the product is paid promotion, so brand. A rival "
    "company's own account, its staff or its paid promotion is a competitor. Competitor needs "
    "the author to BE a rival company; an 'X vs Y' comparison, review or SEO article by anyone "
    "else is never a competitor (a journalist when it reports, otherwise unknown). Only the "
    "company's own account (including its regional and product "
    "accounts), its staff speaking for it, affiliates or paid promotion count as brand; a "
    "person's own progress log that names the brand is not the brand. When nothing in the "
    "text shows who is speaking, answer unknown rather than guessing. "
)

_SYSTEM_HEAD = (
    "You are a precise brand-monitoring classifier. For each social media post you are "
    "given a BRAND/TOPIC and the post text. Decide (1) how relevant the post is to that "
    "brand/topic on a 0.0-1.0 scale and (2) the sentiment toward the brand/topic.\n"
    "Relevance means the post is substantively ABOUT the brand/company — its business, "
    "products, people, actions, or someone's genuine experience or opinion of them. "
    "1.0 = clearly about the brand; 0.0 = unrelated or a coincidental name match "
    "(e.g. 'Wiley' the rapper vs Wiley the publisher).\n"
    "When a BRAND CONTEXT line describes the company, use it to disambiguate: a post "
    "about a DIFFERENT business, venue, person or product that merely shares the name "
    "(a hotel vs an oral-care maker, a stationery brand vs a health-products group) "
    "scores 0.0-0.1 regardless of how prominently the shared name appears.\n"
    "Advertisements and solicitation spam score 0.0-0.1 even when they name the brand or "
    "its products: contract-cheating / essay-mill / 'we take your online class or exam' "
    "services, homework or test-prep solicitations, piracy/download/coupon/referral blasts, "
    "and link-farm posts. An ad that merely lists brand products it services (e.g. "
    "'Pearson, Cengage, WileyPLUS, MyMathLab') is advertising the spammer, not discussing "
    "the brand — it is NOT relevant.\n"
    "If the post never mentions the brand at all — by name, obvious variant or abbreviation, "
    "product name containing the brand, @handle, #hashtag, or stock ticker — relevance must "
    "not exceed 0.3, no matter how close the subject matter is to the brand's industry "
    "(e.g. a complaint about ebooks or textbooks that names a different company or none).\n"
    "(3) Also name WHO is speaking. "
)
_SYSTEM_TAIL = (
    'Respond with ONLY a JSON object: {"relevance": <float 0-1>, "sentiment": '
    '"positive"|"neutral"|"negative", "author_role": <one of the roles>, '
    '"author_role_reason": <at most 12 words of evidence from the post>}. No prose.'
)


def author_roles() -> tuple:
    """The roles this site uses: AUTHOR_ROLES, or the set VOICES_PERSONAS names."""
    from app.services import voices_personas
    alt = voices_personas.active_set()
    return AUTHOR_ROLES if alt is None else alt.roles


def _role_prompt() -> str:
    """The role list and how to pick one, for this site's persona set."""
    from app.services import voices_personas
    alt = voices_personas.active_set()
    if alt is None:
        return "Pick author_role from this list only: " + ", ".join(AUTHOR_ROLES) + ". " + _ROLE_GUIDE
    return alt.role_prompt()


def _author_line(author: str) -> str:
    """The author's handle, for a site with its own persona set.

    On wileytest a journal's own account (@respcasereports) read as an academic
    without it: the handle is the evidence. Sites on the standard list keep the
    exact user message they had, so this is empty for them.
    """
    from app.services import voices_personas
    if voices_personas.active_set() is None or not (author or "").strip():
        return ""
    return f"\nAUTHOR: @{author.strip().lstrip('@')}"


def _system_prompt() -> str:
    return _SYSTEM_HEAD + _role_prompt() + _SYSTEM_TAIL


_SUPERVISOR_SYSTEM = (
    "You are a strict brand-monitoring reviewer. A first-pass classifier marked the "
    "social media post below as NEGATIVE toward the given BRAND/TOPIC. Verify that verdict "
    "by answering two questions:\n"
    "1. negative_toward_brand — is the negativity actually directed AT the brand/company or "
    "its products/services? Negative subject matter is NOT negativity toward the brand: a post "
    "sharing an article or paper about a grim topic that happens to be published by the brand, "
    "a complaint about a third party, or general industry criticism that does not target the "
    "brand all count as false. A complaint about the brand's own product misbehaving counts "
    "as true. Pay attention to WHO is criticized: if the brand is the one acting — suing "
    "someone, criticizing a third party, winning a dispute — the negativity is directed at "
    "the other party, not the brand, so answer false.\n"
    "2. spam_or_solicitation — is the post advertising, solicitation, a piracy/PDF/textbook "
    "request, or other spam, rather than a genuine opinion or experience?\n"
    'Respond with ONLY a JSON object: {"negative_toward_brand": true|false, '
    '"spam_or_solicitation": true|false}. No prose.'
)

# Supervisor pass on negative verdicts (second, stricter model call). On by
# default; SOCIAL_EVAL_SUPERVISOR=0 disables it.
def _supervisor_enabled() -> bool:
    return os.getenv("SOCIAL_EVAL_SUPERVISOR", "1").lower() not in ("0", "false", "no")


# Generic words that can lead a brand name without identifying it.
_ANCHOR_STOP = {"the", "and", "for", "brand", "monitoring", "group", "inc",
                "llc", "ltd", "corp", "company", "co", "john"}


def _brand_anchor_tokens(brand_topic: str) -> List[str]:
    """The distinctive leading token of the brand name, for the no-mention cap.

    "Brand Monitoring Pearsons Education" -> ["pearsons"]; "Wiley" -> ["wiley"].
    Returns [] when nothing distinctive can be derived (the cap then fails open).
    """
    name = re.sub(r"^brand monitoring\s+", "", (brand_topic or "").strip().lower())
    toks = [t for t in re.findall(r"[a-z0-9']+", name)
            if len(t) >= 3 and t not in _ANCHOR_STOP]
    return toks[:1]


_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_JA_COMPANY_SUFFIX = re.compile(r"(株式会社|ホールディングス)$")


def _brand_anchors(display_name: str, keywords: List[str]) -> List[str]:
    """Every name that counts as the post mentioning the brand.

    The cap used only the first word of the brand's title, so a post about
    Ora² or GUM never "mentioned" Sunstar and a Sensodyne post never mentioned
    Haleon: real posts were held at 0.3. Now the brand's keywords and product
    names count too, whole, and a Japanese company name counts without its
    株式会社 suffix (ライオン株式会社 -> ライオン).

    The first word of a keyword counts on its own only when it is written in
    capitals ("GUM toothbrush" -> GUM, matched in capitals only, so "gum
    disease" stays capped). Lower-case first words do not: "Science journals"
    would make every post about science count as naming Elsevier. A
    case-sensitive anchor carries a leading "=".
    """
    out: List[str] = list(_brand_anchor_tokens(display_name))
    for raw in keywords or []:
        raw = str(raw or "").strip().translate(_SUPERSCRIPT_DIGITS)
        kw = raw.lower()
        if not kw:
            continue
        out.append(kw)
        short = _JA_COMPANY_SUFFIX.sub("", kw)
        if short and short != kw:
            out.append(short)
        words = re.findall(r"[A-Za-z0-9']+", raw)
        if len(words) > 1 and words[0].lower() not in _ANCHOR_STOP:
            first = words[0]
            if len(first) >= 3 and first.isupper():
                out.append("=" + first)
    return list(dict.fromkeys(a for a in out if a))


def _mentions_brand(text_lower: str, anchors: List[str], text_raw: str = "") -> bool:
    """Word-start match so '#Wiley' / '@wileyglobal' / '$WLYY-adjacent' handles count.

    An anchor starting with "=" is matched case-sensitively, as a whole word,
    against ``text_raw`` (see ``_brand_anchors``).
    """
    for a in anchors:
        if a.startswith("="):
            if text_raw and re.search(r"(?<![A-Za-z0-9])" + re.escape(a[1:]) + r"(?![A-Za-z])",
                                      text_raw):
                return True
        elif re.search(r"(?<![a-z0-9])" + re.escape(a), text_lower):
            return True
    return False


def _parse_eval(content: str) -> Optional[Dict]:
    """Extract {relevance, sentiment} from a model response, tolerantly."""
    if not content:
        return None
    m = re.search(r"\{[\s\S]*\}", content)
    if not m:
        return None
    try:
        obj = json.loads(m.group())
    except json.JSONDecodeError:
        return None
    rel = obj.get("relevance")
    try:
        rel = max(0.0, min(1.0, float(rel)))
    except (TypeError, ValueError):
        return None
    sent = str(obj.get("sentiment", "")).strip().lower()
    if sent not in ("positive", "neutral", "negative"):
        sent = "neutral"
    out = {"relevance": rel, "sentiment": sent}
    out.update(_parse_role(obj))
    return out


def _parse_role(obj: Dict) -> Dict:
    """author_role + reason from a parsed model object; unknown when absent or off-list."""
    role = str(obj.get("author_role") or "").strip().lower().replace(" ", "_")
    if role not in author_roles():
        role = "unknown"
    reason = str(obj.get("author_role_reason") or "").strip()[:200]
    return {"author_role": role, "author_role_reason": reason or None}


def _role_system_prompt() -> str:
    return (
        "You are a brand-monitoring classifier. You are given a BRAND and a social media post "
        "about it. Say WHO wrote the post. " + _role_prompt() +
        'Respond with ONLY a JSON object: {"author_role": <one of the roles>, '
        '"author_role_reason": <at most 12 words of evidence from the post>}. No prose.'
    )


def _parse_verify(content: str) -> Optional[Dict]:
    """Extract the supervisor verdict from a model response, tolerantly."""
    if not content:
        return None
    m = re.search(r"\{[\s\S]*\}", content)
    if not m:
        return None
    try:
        obj = json.loads(m.group())
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or "negative_toward_brand" not in obj:
        return None
    return {"negative_toward_brand": bool(obj.get("negative_toward_brand")),
            "spam_or_solicitation": bool(obj.get("spam_or_solicitation"))}


class SocialEvalService:
    """Evaluate social posts for brand relevance + sentiment via a cheap model."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or os.getenv("SOCIAL_EVAL_MODEL", DEFAULT_SOCIAL_EVAL_MODEL)
        self._model = None
        self._unavailable = False

    def _get_model(self):
        if self._model is None and not self._unavailable:
            try:
                from app.ai_models import LiteLLMModel
                self._model = LiteLLMModel.get_instance(self.model_name)
                if not self._model:
                    self._unavailable = True
            except Exception as e:
                logger.warning(f"SocialEval model '{self.model_name}' unavailable: {e}")
                self._unavailable = True
        return self._model

    async def _eval_one(self, brand_topic: str, title: str, body: str,
                        author: str = "", brand_context: str = "",
                        anchors: Optional[List[str]] = None, source_tier: str = "",
                        topic_mode: bool = False) -> Optional[Dict]:
        model = self._get_model()
        if not model:
            return None
        text = f"{title}\n{body}".strip()[:1500]
        # Cheapest gate first (AI_DESIGN_PATTERNS 1.4). A post that never names
        # the brand is capped at 0.3 below, under every on-brand floor, whatever
        # the model says; so settle it here instead of paying for the call.
        # About half of collected posts are like this (Sunstar, 26 Sep 2026).
        gate_anchors = anchors if anchors is not None else _brand_anchor_tokens(brand_topic)
        gate_raw = f"{text}\n{author or ''}".translate(_SUPERSCRIPT_DIGITS)
        if gate_anchors and not _mentions_brand(gate_raw.lower(), gate_anchors, gate_raw):
            return {"relevance": 0.0, "sentiment": "neutral", "author_role": None,
                    "author_role_reason": None, "no_brand_mention": True}
        # brand_context = the bw_brands description. Without it the model cannot
        # tell same-name entities apart: a post by @Hotel_Sunstar IS about "a
        # Sunstar", and only "Sunstar = oral care company" makes it a miss.
        ctx = f"\nBRAND CONTEXT: {brand_context.strip()[:600]}" if brand_context else ""
        ctx += _author_line(author)
        # A watch on a subject is not a watch on a company. The extra guidance
        # rides in the user message rather than the system prompt so the brand
        # path sees byte-identical input to what it saw before.
        if source_tier and source_tier not in ("unknown", ""):
            ctx += f"\nSOURCE: {author or 'unknown'} — known to us as {source_tier.replace('_', ' ')}"
        if topic_mode:
            ctx += ("\nThis is a SUBJECT watch, not a company. Relevance means the post is "
                    "substantively about this subject — including a post that argues a position "
                    "within it. A post from a source known to us as state media, alternative "
                    "media or a party, pushing a line on this subject, is highly relevant even "
                    "when it names no organisation. Judge the subject, not a company name, and "
                    "score posts in any language on the same scale.")
        messages = [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": f"BRAND/TOPIC: {brand_topic}{ctx}\n\nPOST:\n{text}"},
        ]
        try:
            from fastapi.concurrency import run_in_threadpool
            # Hard deadline: a wedged provider socket (observed: Bedrock SSL read
            # blocking indefinitely) must not pin a worker slot forever — one hung
            # call would stall the whole batch AND the keyword-monitor loop.
            # On timeout the worker thread is abandoned (bounded leak), which is
            # the lesser evil.
            content = await asyncio.wait_for(
                run_in_threadpool(model.generate_response, messages), timeout=_CALL_TIMEOUT_S)
            r = _parse_eval(content)
        except asyncio.TimeoutError:
            logger.warning(f"SocialEval call timed out after {_CALL_TIMEOUT_S}s")
            return None
        except Exception as e:
            logger.debug(f"SocialEval call failed: {e}")
            return None
        # Deterministic backstop for the prompt's no-mention rule: a post that
        # never names the brand cannot be highly on-brand, however close the
        # subject matter (a French Sony ebook complaint scored 0.75 for Wiley).
        # 0.3 sits below the 0.4 relevance floor used by feeds and alert rules.
        if r and r["relevance"] > 0.3:
            # Brands keep the single title-derived anchor; a topic passes its own
            # keyword terms, which carry the language variants.
            anchors = anchors if anchors is not None else _brand_anchor_tokens(brand_topic)
            raw = f"{text}\n{author or ''}".translate(_SUPERSCRIPT_DIGITS)
            if anchors and not _mentions_brand(raw.lower(), anchors, raw):
                r["relevance"] = 0.3
        # Supervisor pass: negative on-brand verdicts drive the spike alerts and
        # adverse panels, so they get a second, stricter look before they count.
        # Spam/solicitation -> hidden (relevance 0.1); negativity that isn't aimed
        # at the brand (grim subject matter, third parties) -> neutral.
        if r and r["sentiment"] == "negative" and r["relevance"] >= 0.4 and _supervisor_enabled():
            v = await self._verify_negative(brand_topic, title, body)
            if v:
                if v["spam_or_solicitation"]:
                    r["relevance"] = min(r["relevance"], 0.1)
                elif not v["negative_toward_brand"]:
                    r["sentiment"] = "neutral"
        return r

    async def _verify_negative(self, brand_topic: str, title: str, body: str) -> Optional[Dict]:
        """Second-pass supervisor check on a first-pass negative verdict."""
        model = self._get_model()
        if not model:
            return None
        text = f"{title}\n{body}".strip()[:1500]
        messages = [
            {"role": "system", "content": _SUPERVISOR_SYSTEM},
            {"role": "user", "content": f"BRAND/TOPIC: {brand_topic}\n\nPOST:\n{text}"},
        ]
        try:
            from fastapi.concurrency import run_in_threadpool
            content = await asyncio.wait_for(
                run_in_threadpool(model.generate_response, messages), timeout=_CALL_TIMEOUT_S)
            return _parse_verify(content)
        except asyncio.TimeoutError:
            logger.warning(f"SocialEval supervisor call timed out after {_CALL_TIMEOUT_S}s")
            return None
        except Exception as e:
            logger.debug(f"SocialEval supervisor call failed: {e}")
            return None

    async def _role_one(self, brand_topic: str, title: str, body: str,
                        brand_context: str = "", author: str = "") -> Optional[Dict]:
        model = self._get_model()
        if not model:
            return None
        text = f"{title}\n{body}".strip()[:1500]
        ctx = f"\nBRAND CONTEXT: {brand_context.strip()[:600]}" if brand_context else ""
        ctx += _author_line(author)
        messages = [
            {"role": "system", "content": _role_system_prompt()},
            {"role": "user", "content": f"BRAND: {brand_topic}{ctx}\n\nPOST:\n{text}"},
        ]
        try:
            from fastapi.concurrency import run_in_threadpool
            content = await asyncio.wait_for(
                run_in_threadpool(model.generate_response, messages), timeout=_CALL_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.warning(f"SocialEval role call timed out after {_CALL_TIMEOUT_S}s")
            return None
        except Exception as e:
            logger.debug(f"SocialEval role call failed: {e}")
            return None
        m = re.search(r"\{[\s\S]*\}", content or "")
        if not m:
            return None
        try:
            return _parse_role(json.loads(m.group()))
        except json.JSONDecodeError:
            return None

    async def classify_roles(self, posts: List[Dict], brand_topic: str,
                             brand_context: str = "",
                             competitors: Optional[List[str]] = None) -> List[Dict]:
        """Author role only, for posts that were scored before roles existed.

        Same taxonomy as the combined call; returns [{uri, author_role,
        author_role_reason}] for the posts the model answered. A site with
        VOICES_ROLE_MODEL=jev gets the role from Jev instead (author_role_jev).
        """
        from app.services import author_role_jev
        if posts and author_role_jev.enabled():
            got = await asyncio.to_thread(author_role_jev.read_roles, brand_topic,
                                          brand_context, competitors or [], posts)
            return [{"uri": uri, **r} for uri, r in got.items()]
        if not posts or not self._get_model():
            return []
        sem = asyncio.Semaphore(_MAX_CONCURRENT)
        results: List[Dict] = []

        async def _run(p):
            async with sem:
                r = await self._role_one(brand_topic, p.get("title") or "",
                                         p.get("summary") or p.get("content") or "",
                                         brand_context=brand_context,
                                         author=p.get("author") or "")
                if r:
                    results.append({"uri": p.get("uri") or p.get("url"), **r})

        await asyncio.gather(*[_run(p) for p in posts], return_exceptions=True)
        return results

    async def evaluate_posts(self, posts: List[Dict], brand_topic: str,
                             brand_context: str = "", anchors: Optional[List[str]] = None,
                             tiers: Optional[Dict[str, str]] = None,
                             topic_mode: bool = False) -> List[Dict]:
        """Evaluate a batch of post dicts (need 'uri','title','summary'/'content').

        Returns list of {uri, relevance, sentiment} for posts the model scored.
        Bounded concurrency; returns [] if the model is unavailable.
        """
        if not posts or not self._get_model():
            return []
        sem = asyncio.Semaphore(_MAX_CONCURRENT)
        results: List[Dict] = []

        async def _run(p):
            async with sem:
                title = p.get("title") or ""
                body = p.get("summary") or p.get("content") or ""
                author = p.get("author") or (p.get("social_meta") or {}).get("author") or ""
                # A Bluesky handle and a Telegram channel are both addressed the
                # way a domain is, so one lookup serves both.
                tier = ""
                if tiers:
                    handle = (author or "").strip().lstrip("@").lower()
                    tier = tiers.get(handle) or tiers.get(f"t.me/{handle}") or ""
                r = await self._eval_one(brand_topic, title, body, author=author,
                                         brand_context=brand_context, anchors=anchors,
                                         source_tier=tier, topic_mode=topic_mode)
                if r:
                    results.append({"uri": p.get("uri") or p.get("url"), **r})

        await asyncio.gather(*[_run(p) for p in posts], return_exceptions=True)
        return results

    async def evaluate_and_store(self, db, brand_topic: str, days_back: int = 7,
                                 limit: int = 500) -> Dict:
        """Find unevaluated social posts for a brand topic, score them, persist scores.

        Stores relevance -> topic_alignment_score + keyword_relevance_score,
        sentiment -> sentiment, and marks ingest_status='social_evaluated',
        analyzed=true. Idempotent: skips posts already social_evaluated.

        Candidates are selected by COLLECTION recency (submission_date), not the
        post's own publication_date — social posts (esp. subreddit feeds) are often
        older than the poll window even when freshly collected. The idempotent
        'social_evaluated' marker + limit bound the work.
        """
        from sqlalchemy import text
        if not self._get_model():
            return {"evaluated": 0, "skipped_model_unavailable": True}
        src_clause = " OR ".join([f"LOWER(news_source) LIKE :s{i}" for i in range(len(SOCIAL_SOURCES))])
        params = {"t": brand_topic, "lim": limit}
        for i, s in enumerate(SOCIAL_SOURCES):
            params[f"s{i}"] = f"%{s}%"
        rows = db.facade._execute_with_rollback(text(f"""
            SELECT uri, title, summary, COALESCE(social_meta->>'author','') FROM articles
            WHERE topic = :t
              AND ({src_clause})
              AND (ingest_status IS NULL OR ingest_status <> 'social_evaluated')
            ORDER BY submission_date DESC NULLS LAST
            LIMIT :lim
        """), params).fetchall()
        posts = [{"uri": r[0], "title": r[1], "summary": r[2], "author": r[3]} for r in rows]
        if not posts:
            return {"evaluated": 0, "candidates": 0}
        # Entity-collision handling: posts matching the brand's exclude terms
        # (config.news_keyword_excludes — hotels, newspapers, stationery makers
        # sharing the name) are scored 0 deterministically, no model call. The
        # brand description rides along on the model calls so the LLM can tell
        # look-alike entities apart on its own.
        ctx = _brand_context_for_topic(db, brand_topic)
        # No brand behind this topic: it is a subject watch, so give the model
        # the topic's description and its own keyword terms as anchors.
        profile = {"description": "", "anchors": [], "tiers": {}}
        topic_mode = not ctx["description"] and not ctx["excludes"]
        if topic_mode:
            profile = _topic_profile(db, brand_topic)
        excluded_zeroed = 0
        if ctx["excludes"]:
            keep = []
            for p in posts:
                blob = f"{p['title'] or ''} {p['summary'] or ''} {p['author'] or ''}".lower()
                if any(x in blob for x in ctx["excludes"]):
                    db.facade._execute_with_rollback(text("""
                        UPDATE articles SET topic_alignment_score = 0, keyword_relevance_score = 0,
                            sentiment = 'Neutral', ingest_status = 'social_evaluated', analyzed = true
                        WHERE uri = :uri
                    """), {"uri": p["uri"]})
                    excluded_zeroed += 1
                else:
                    keep.append(p)
            posts = keep
        scored = await self.evaluate_posts(
            posts, brand_topic,
            brand_context=ctx["description"] or profile["description"],
            anchors=(profile["anchors"] or None) if topic_mode else (ctx.get("anchors") or None),
            tiers=profile["tiers"] or None,
            topic_mode=topic_mode and bool(profile["description"] or profile["anchors"]))
        # The model call keeps relevance and sentiment; on a site that has
        # switched it on, Jev names the author's role (author_role_jev).
        from app.services import author_role_jev
        if author_role_jev.enabled() and not topic_mode and scored:
            brand = brand_topic.replace("Brand Monitoring ", "", 1)
            by_uri = {p["uri"]: p for p in posts}
            jev = await asyncio.to_thread(
                author_role_jev.read_roles, brand, ctx["description"],
                author_role_jev.rival_names(db, brand),
                [by_uri[s["uri"]] for s in scored
                 if s["uri"] in by_uri and not s.get("no_brand_mention")])
            for s in scored:
                s.update(jev.get(s["uri"]) or {})
        for s in scored:
            db.facade._execute_with_rollback(text("""
                UPDATE articles SET topic_alignment_score = :rel, keyword_relevance_score = :rel,
                    sentiment = :sent, ingest_status = 'social_evaluated', analyzed = true,
                    author_role = :role, author_role_reason = :role_why
                WHERE uri = :uri
            """), {"rel": s["relevance"], "sent": s["sentiment"].capitalize(), "uri": s["uri"],
                   "role": s.get("author_role"), "role_why": s.get("author_role_reason")})
        db.facade.connection.commit()
        logger.info(f"SocialEval: scored {len(scored)}/{len(posts)} {brand_topic!r} posts via {self.model_name}"
                    + (f" ({excluded_zeroed} zeroed by exclude terms)" if excluded_zeroed else ""))
        return {"evaluated": len(scored), "candidates": len(posts),
                "excluded": excluded_zeroed, "model": self.model_name}


async def evaluate_mentions_for_group(db, group_id: Optional[int] = None,
                                      brand_id: Optional[int] = None,
                                      limit: int = 200) -> Dict:
    """Score pending mentions one company at a time, not one post at a time.

    ``evaluate_and_store`` above scores a post against a topic and writes the
    answer onto the article row. That is right when a post concerns exactly one
    company and wrong the moment it names two: the second company inherits
    whatever was decided about the first, and a post reused in two monitoring
    topics carries one score for both.

    This scores each ``(post, company)`` pair on its own and writes the result
    to that pair's mention. The article columns are only touched when the post
    maps to exactly one entity — where they cannot be ambiguous — and only
    while dual-write is on, so the legacy readers keep working during rollout.

    Nothing is scored implicitly. A mention stays ``pending`` until this runs,
    because an unevaluated mention counted as neutral is an opinion the system
    invented.
    """
    from sqlalchemy import text

    from app.services import entity_content, entity_flags

    service = get_social_eval_service()
    if not service._get_model():
        return {"evaluated": 0, "skipped_model_unavailable": True}

    where = ["m.status = 'pending'", "m.evaluated_at IS NULL",
             "m.channel IN ('public_social', 'community')"]
    params: Dict = {"lim": limit}
    if brand_id is not None:
        where.append("m.brand_id = :brand_id")
        params["brand_id"] = brand_id
    if group_id is not None:
        where.append("EXISTS (SELECT 1 FROM keyword_article_matches kam "
                     "WHERE kam.article_uri = m.article_uri "
                     "AND kam.group_id = :group_id)")
        params["group_id"] = group_id

    rows = db.facade._execute_with_rollback(text(f"""
        SELECT m.id, m.brand_id, m.article_uri, b.display_name,
               a.title, a.summary,
               (SELECT count(*) FROM bw_entity_mentions o
                 WHERE o.article_uri = m.article_uri) AS entities_on_article,
               COALESCE(b.description, '') AS brand_context
          FROM bw_entity_mentions m
          JOIN bw_brands b ON b.id = m.brand_id
          JOIN articles a ON a.uri = m.article_uri
         WHERE {' AND '.join(where)}
         ORDER BY m.created_at
         LIMIT :lim
    """), params).fetchall()
    if not rows:
        return {"evaluated": 0, "candidates": 0}

    conn = db.facade.connection
    evaluated = 0
    excluded = 0
    excludes_by_brand: Dict[int, List[str]] = {}
    anchors_by_brand: Dict[int, Optional[List[str]]] = {}
    from app.services import author_role_jev
    rivals_by_brand: Dict[str, List[str]] = {}
    for (mention_id, mention_brand, uri, display_name, title, summary,
         entities_on_article, brand_context) in rows:
        # Entity collisions (config.news_keyword_excludes: "Oviva Therapeutics",
        # a US biotech, next to Oviva the weight-management provider) are
        # settled before any model call, the same way evaluate_and_store does
        # on the topic path. This path skipped it, so a look-alike scored 0.9.
        if mention_brand not in excludes_by_brand:
            _ctx = _brand_context_for_topic(db, f"Brand Monitoring {display_name}")
            excludes_by_brand[mention_brand] = _ctx["excludes"]
            anchors_by_brand[mention_brand] = _ctx.get("anchors") or None
        blob = f"{title or ''} {summary or ''}".lower()
        author = db.facade._execute_with_rollback(text(
            "SELECT COALESCE(social_meta->>'author', '') FROM articles WHERE uri = :u"),
            {"u": uri}).scalar() or ""
        if any(x in blob or x in author.lower() for x in excludes_by_brand[mention_brand]):
            entity_content.score_mention(
                conn, mention_id, relevance=0.0, sentiment=None,
                stance='not_applicable', method='exclude_term', model=None,
                version=entity_content.MATCHER_VERSION, status='accepted')
            excluded += 1
            continue
        # One post, one company, one verdict — the brand name is the subject
        # of the question rather than the topic the post was collected under.
        # The brand description rides along so the model can tell a patient
        # from a customer and a look-alike company from the real one.
        scored = await service.evaluate_posts(
            [{"uri": uri, "title": title, "summary": summary, "author": ""}],
            display_name, brand_context=brand_context,
            anchors=anchors_by_brand.get(mention_brand))
        if not scored:
            continue
        verdict = scored[0]
        if author_role_jev.enabled() and not verdict.get("no_brand_mention"):
            if display_name not in rivals_by_brand:
                rivals_by_brand[display_name] = author_role_jev.rival_names(db, display_name)
            jev = await asyncio.to_thread(
                author_role_jev.read_role, display_name, brand_context,
                rivals_by_brand[display_name],
                {"title": title, "summary": summary, "author": author})
            verdict.update(jev or {})
        sentiment = (verdict.get("sentiment") or "").lower()
        entity_content.score_mention(
            conn, mention_id, relevance=verdict.get("relevance"),
            sentiment=sentiment.capitalize() or None,
            stance=_STANCE_BY_SENTIMENT.get(sentiment),
            method='llm', model=service.model_name,
            version=entity_content.MATCHER_VERSION,
            status='accepted')
        evaluated += 1

        # Who wrote the post does not depend on which company is asked about,
        # so the role goes on the article row for every mention.
        if verdict.get("author_role"):
            db.facade._execute_with_rollback(text("""
                UPDATE articles SET author_role = :role, author_role_reason = :why
                 WHERE uri = :uri
            """), {"role": verdict["author_role"],
                   "why": verdict.get("author_role_reason"), "uri": uri})

        # Only unambiguous posts may write the shared article columns.
        if entity_flags.dual_write() and int(entities_on_article) == 1:
            db.facade._execute_with_rollback(text("""
                UPDATE articles
                   SET topic_alignment_score = :rel,
                       keyword_relevance_score = :rel,
                       sentiment = :sent, ingest_status = 'social_evaluated',
                       analyzed = true
                 WHERE uri = :uri
            """), {"rel": verdict.get("relevance"),
                   "sent": sentiment.capitalize(), "uri": uri})

    conn.commit()
    logger.info("SocialEval: scored %d/%d pending mentions via %s (%d zeroed by exclude terms)",
                evaluated, len(rows), service.model_name, excluded)
    return {"evaluated": evaluated, "candidates": len(rows),
            "excluded": excluded, "model": service.model_name}


# A company being the actor in a story is not the same as the story being
# negative about it, so stance is derived conservatively and left unset where
# the sentiment does not carry one.
_STANCE_BY_SENTIMENT = {
    "positive": "supportive",
    "negative": "critical",
    "neutral": "neutral",
    "mixed": "mixed",
}


def _topic_profile(db, topic: str) -> Dict:
    """Description, anchor terms and source tiers for a plain keyword topic.

    The brand path (``_brand_context_for_topic``) answers for
    "Brand Monitoring <name>" topics and is untouched. Everything else used to
    get nothing at all: no description, so the model judged a post against the
    bare topic title, and a single anchor word derived from that title, so the
    no-mention cap fired on any post not containing it. For
    "Swiss Federal Elections 2027 Disinfo Monitoring" the anchor was "swiss",
    which does not match "Switzerland" (swiss/switz) and matches no German,
    French or Italian post at all — 88 posts sat at the 0.30 ceiling, several
    of them squarely on topic (2026-09-17).

    Anchors now come from the topic's own monitored keywords, which already
    carry the language variants, and tiers come from sd_sources when a watch
    module has populated it.
    """
    from sqlalchemy import text
    out: Dict[str, Any] = {"description": "", "anchors": [], "tiers": {}}
    if not topic:
        return out
    try:
        from app.config.settings import get_config_path
        cfg_path = get_config_path()
    except Exception:
        cfg_path = None
    try:
        import json as _json
        from pathlib import Path
        path = Path(cfg_path) if cfg_path else Path(__file__).resolve().parents[1] / "config" / "config.json"
        cfg = _json.loads(path.read_text())
        for t in cfg.get("topics", []):
            if (t.get("name") or "").strip().lower() == topic.strip().lower():
                out["description"] = (t.get("description") or "").strip()
                break
    except Exception as e:  # noqa: BLE001 - context is an enhancement, never a blocker
        logger.debug(f"SocialEval topic description lookup failed for {topic!r}: {e}")

    try:
        rows = db.facade._fetchall_with_rollback(text(
            "SELECT k.keyword FROM monitored_keywords k "
            "JOIN keyword_groups g ON g.id = k.group_id WHERE g.topic = :t"),
            {"t": topic}, operation_name="social eval topic anchors")
        seen: List[str] = []
        for (kw,) in rows or []:
            bare = re.sub(r"^(company|tech|person|location):", "", (kw or "").strip(), flags=re.I)
            for tok in re.findall(r"[\w'-]{4,}", bare.lower(), flags=re.UNICODE):
                if tok not in _ANCHOR_STOP and tok not in seen:
                    seen.append(tok)
        for tok in re.findall(r"[\w'-]{4,}", (topic or "").lower(), flags=re.UNICODE):
            if tok not in _ANCHOR_STOP and tok not in seen:
                seen.append(tok)
        out["anchors"] = seen[:60]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"SocialEval topic anchors lookup failed for {topic!r}: {e}")

    try:
        if db.facade._fetchone_with_rollback(text("SELECT to_regclass('sd_sources')"), {},
                                             operation_name="social eval tier probe")[0]:
            rows = db.facade._fetchall_with_rollback(text(
                "SELECT domain, tier FROM sd_sources"), {},
                operation_name="social eval tiers")
            out["tiers"] = {(d or "").lower(): t for d, t in (rows or []) if d and t}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"SocialEval tier lookup failed: {e}")
    return out


def _brand_context_for_topic(db, brand_topic: str) -> Dict:
    """Description + entity-collision exclude terms for the brand behind a topic.

    Topic 'Brand Monitoring <display_name>' -> the bw_brands row. The exclude
    terms are config.news_keyword_excludes — despite the name it is the brand's
    entity-collision list (other companies/venues sharing the name), which is
    exactly as wrong on social as it is on news, so both channels apply it.
    Plain keyword topics (no matching brand) get empty context and evaluate as
    before.
    """
    from sqlalchemy import text
    name = re.sub(r"^brand monitoring\s+", "", (brand_topic or "").strip(), flags=re.I)
    if not name or name == (brand_topic or "").strip():
        return {"description": "", "excludes": []}
    try:
        row = db.facade._fetchone_with_rollback(text(
            "SELECT description, config, brand_keywords, product_keywords "
            "FROM bw_brands WHERE LOWER(display_name) = LOWER(:n)"),
            {"n": name}, operation_name="social eval brand context")
        if not row:
            return {"description": "", "excludes": []}
        cfg = row[1] if isinstance(row[1], dict) else (json.loads(row[1]) if row[1] else {})
        excludes = [str(x).strip().lower() for x in (cfg.get("news_keyword_excludes") or [])
                    if str(x).strip()]
        kws: List[str] = []
        for col in (row[2], row[3]):
            vals = col if isinstance(col, list) else (json.loads(col) if col else [])
            kws.extend(str(v) for v in vals or [])
        return {"description": (row[0] or "").strip(), "excludes": excludes,
                "anchors": _brand_anchors(name, kws)}
    except Exception as e:  # noqa: BLE001 - context is an enhancement, never a blocker
        logger.debug(f"SocialEval brand-context lookup failed for {brand_topic!r}: {e}")
        return {"description": "", "excludes": []}


def apply_exclude_terms(conn, brand_id: int, display_name: str,
                        excludes: List[str]) -> Dict[str, int]:
    """Zero already-scored posts that match the brand's exclude terms.

    The terms are checked when a post is first evaluated, so a term added
    later did nothing for what was already in the tables: Noom's Voices kept
    showing Thai fan posts about an actor nicknamed "Noom" that the model had
    scored 0.7 to 1.0. Saving the list now re-applies it to the brand's stored
    mentions and topic rows, the same way the evaluators would have. Matching
    is the same lowercase substring test over title, summary and author.
    """
    terms = [str(x).strip().lower() for x in (excludes or []) if str(x).strip()]
    if not terms:
        return {"mentions": 0, "articles": 0}
    from sqlalchemy import text
    from app.services import entity_content
    out = {"mentions": 0, "articles": 0}
    topic = f"Brand Monitoring {display_name}"

    def _hit(title, summary, author) -> bool:
        blob = f"{title or ''} {summary or ''} {author or ''}".lower()
        return any(t in blob for t in terms)

    try:
        rows = conn.execute(text("""
            SELECT m.id, a.uri, a.title, a.summary, a.social_meta->>'author'
              FROM bw_entity_mentions m JOIN articles a ON a.uri = m.article_uri
             WHERE m.brand_id = :b AND COALESCE(m.relevance, 0) > 0
        """), {"b": brand_id}).fetchall()
        for mid, uri, title, summary, author in rows:
            if _hit(title, summary, author):
                entity_content.score_mention(
                    conn, int(mid), relevance=0.0, sentiment=None,
                    stance='not_applicable', method='exclude_term', model=None,
                    version=entity_content.MATCHER_VERSION, status='accepted')
                out["mentions"] += 1
    except Exception as e:  # noqa: BLE001 — no mention table on the topic-only trees
        logger.debug("apply_exclude_terms: mention pass skipped: %s", e)
    rows = conn.execute(text("""
        SELECT uri, title, summary, social_meta->>'author'
          FROM articles
         WHERE topic = :t AND COALESCE(topic_alignment_score, 0) > 0
    """), {"t": topic}).fetchall()
    for uri, title, summary, author in rows:
        if _hit(title, summary, author):
            conn.execute(text("""
                UPDATE articles SET topic_alignment_score = 0, keyword_relevance_score = 0,
                       sentiment = 'Neutral'
                 WHERE uri = :u
            """), {"u": uri})
            out["articles"] += 1
    return out


_singleton: Optional[SocialEvalService] = None


def get_social_eval_service() -> SocialEvalService:
    global _singleton
    if _singleton is None:
        _singleton = SocialEvalService()
    return _singleton


async def sweep_unevaluated_social(db, limit_per_topic: int = 200,
                                   max_topics: int = 12, days_back: int = 14) -> Dict:
    """Retry evaluation for social posts whose scoring failed earlier.

    evaluate_and_store only marks posts it successfully scored, so model
    timeouts/outages leave posts as candidates — but they were only retried
    when their group's COLLECTION cycle happened to run again. This sweep is
    collection-independent: find topics with unevaluated recent social posts
    and re-run the evaluator for each, honoring the group's model choice.
    """
    from sqlalchemy import text
    src_clause = " OR ".join(f"LOWER(news_source) LIKE :s{i}" for i in range(len(SOCIAL_SOURCES)))
    params = {"mt": max_topics, "cutoff": ""}
    for i, s in enumerate(SOCIAL_SOURCES):
        params[f"s{i}"] = f"%{s}%"
    from datetime import datetime, timedelta, timezone
    params["cutoff"] = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        rows = db.facade._execute_with_rollback(text(f"""
            SELECT topic, COUNT(*) FROM articles
            WHERE ({src_clause})
              AND (ingest_status IS NULL OR ingest_status <> 'social_evaluated')
              AND COALESCE(topic, '') <> ''
              AND submission_date >= :cutoff
            GROUP BY topic ORDER BY COUNT(*) DESC LIMIT :mt
        """), params).fetchall()
    except Exception as e:  # noqa: BLE001 - sweep is best-effort
        logger.warning(f"SocialEval sweep candidate scan failed: {e}")
        return {"swept": 0, "error": str(e)}
    total = {"swept": 0, "topics": 0}
    for topic, backlog in rows:
        try:
            grp = db.facade._execute_with_rollback(text(
                "SELECT default_llm_model FROM keyword_groups WHERE topic = :t"
                " AND COALESCE(default_llm_model,'') <> '' LIMIT 1"), {"t": topic}).fetchone()
            svc = SocialEvalService(grp[0]) if grp else get_social_eval_service()
            res = await svc.evaluate_and_store(db, topic, limit=min(limit_per_topic, int(backlog)))
            if res.get("skipped_model_unavailable"):
                logger.info("SocialEval sweep: model unavailable, aborting this round")
                break
            total["swept"] += res.get("evaluated", 0)
            total["topics"] += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"SocialEval sweep failed for {topic!r}: {e}")
    if total["swept"]:
        logger.info(f"SocialEval sweep: re-scored {total['swept']} posts across {total['topics']} topic(s)")
    return total
