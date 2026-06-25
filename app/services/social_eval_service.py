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
SOCIAL_SOURCES = ("reddit", "bluesky", "bsky")  # news_source substrings that mark social posts
_MAX_CONCURRENT = 6  # cap parallel model calls

_SYSTEM = (
    "You are a precise brand-monitoring classifier. For each social media post you are "
    "given a BRAND/TOPIC and the post text. Decide (1) how relevant the post is to that "
    "brand/topic on a 0.0-1.0 scale — 1.0 = clearly about it, 0.0 = unrelated or a "
    "coincidental name match — and (2) the sentiment toward the brand/topic. "
    'Respond with ONLY a JSON object: {"relevance": <float 0-1>, "sentiment": '
    '"positive"|"neutral"|"negative"}. No prose.'
)


def is_social_source(news_source: Optional[str]) -> bool:
    s = (news_source or "").lower()
    return any(k in s for k in SOCIAL_SOURCES)


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

    async def _eval_one(self, brand_topic: str, title: str, body: str) -> Optional[Dict]:
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
            content = await run_in_threadpool(model.generate_response, messages)
            return _parse_eval(content)
        except Exception as e:
            logger.debug(f"SocialEval call failed: {e}")
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
                r = await self._eval_one(brand_topic, title, body)
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
            SELECT uri, title, summary FROM articles
            WHERE topic = :t
              AND ({src_clause})
              AND (ingest_status IS NULL OR ingest_status <> 'social_evaluated')
            ORDER BY submission_date DESC NULLS LAST
            LIMIT :lim
        """), params).fetchall()
        posts = [{"uri": r[0], "title": r[1], "summary": r[2]} for r in rows]
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


_singleton: Optional[SocialEvalService] = None


def get_social_eval_service() -> SocialEvalService:
    global _singleton
    if _singleton is None:
        _singleton = SocialEvalService()
    return _singleton
