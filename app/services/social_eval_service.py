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

_SYSTEM = (
    "You are a precise brand-monitoring classifier. For each social media post you are "
    "given a BRAND/TOPIC and the post text. Decide (1) how relevant the post is to that "
    "brand/topic on a 0.0-1.0 scale and (2) the sentiment toward the brand/topic.\n"
    "Relevance means the post is substantively ABOUT the brand/company — its business, "
    "products, people, actions, or someone's genuine experience or opinion of them. "
    "1.0 = clearly about the brand; 0.0 = unrelated or a coincidental name match "
    "(e.g. 'Wiley' the rapper vs Wiley the publisher).\n"
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
    'Respond with ONLY a JSON object: {"relevance": <float 0-1>, "sentiment": '
    '"positive"|"neutral"|"negative"}. No prose.'
)


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


def _mentions_brand(text_lower: str, anchors: List[str]) -> bool:
    """Word-start match so '#Wiley' / '@wileyglobal' / '$WLYY-adjacent' handles count."""
    return any(re.search(r"(?<![a-z0-9])" + re.escape(a), text_lower) for a in anchors)


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
    return {"relevance": rel, "sentiment": sent}


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
                        author: str = "") -> Optional[Dict]:
        model = self._get_model()
        if not model:
            return None
        text = f"{title}\n{body}".strip()[:1500]
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"BRAND/TOPIC: {brand_topic}\n\nPOST:\n{text}"},
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
            anchors = _brand_anchor_tokens(brand_topic)
            hay = f"{text}\n{author or ''}".lower()
            if anchors and not _mentions_brand(hay, anchors):
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

    async def evaluate_posts(self, posts: List[Dict], brand_topic: str) -> List[Dict]:
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
                r = await self._eval_one(brand_topic, title, body, author=author)
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
        scored = await self.evaluate_posts(posts, brand_topic)
        for s in scored:
            db.facade._execute_with_rollback(text("""
                UPDATE articles SET topic_alignment_score = :rel, keyword_relevance_score = :rel,
                    sentiment = :sent, ingest_status = 'social_evaluated', analyzed = true
                WHERE uri = :uri
            """), {"rel": s["relevance"], "sent": s["sentiment"].capitalize(), "uri": s["uri"]})
        db.facade.connection.commit()
        logger.info(f"SocialEval: scored {len(scored)}/{len(posts)} {brand_topic!r} posts via {self.model_name}")
        return {"evaluated": len(scored), "candidates": len(posts), "model": self.model_name}


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
                 WHERE o.article_uri = m.article_uri) AS entities_on_article
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
    for (mention_id, mention_brand, uri, display_name, title, summary,
         entities_on_article) in rows:
        # One post, one company, one verdict — the brand name is the subject
        # of the question rather than the topic the post was collected under.
        scored = await service.evaluate_posts(
            [{"uri": uri, "title": title, "summary": summary, "author": ""}],
            display_name)
        if not scored:
            continue
        verdict = scored[0]
        sentiment = (verdict.get("sentiment") or "").lower()
        entity_content.score_mention(
            conn, mention_id, relevance=verdict.get("relevance"),
            sentiment=sentiment.capitalize() or None,
            stance=_STANCE_BY_SENTIMENT.get(sentiment),
            method='llm', model=service.model_name,
            version=entity_content.MATCHER_VERSION,
            status='accepted')
        evaluated += 1

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
    logger.info("SocialEval: scored %d/%d pending mentions via %s",
                evaluated, len(rows), service.model_name)
    return {"evaluated": evaluated, "candidates": len(rows),
            "model": service.model_name}


# A company being the actor in a story is not the same as the story being
# negative about it, so stance is derived conservatively and left unset where
# the sentiment does not carry one.
_STANCE_BY_SENTIMENT = {
    "positive": "supportive",
    "negative": "critical",
    "neutral": "neutral",
    "mixed": "mixed",
}


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
