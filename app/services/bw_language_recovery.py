"""Non-English adverse-coverage recovery.

The embedding/DeBERTa relevance path is English-centric, so foreign-language
articles (the WeLib lawsuit coverage was Vietnamese, German and Portuguese)
score ~0.1 and silently drop below the 0.4 display threshold — invisible risk.

This pass sweeps recent low-scored articles whose text looks non-English and
re-judges topic relevance with an LLM directly (multilingual by nature; the
embedding path is skipped entirely). Attempted articles are stamped in
``llm_processing_metadata['lang_recovery']`` so they are never re-scanned.
Cost is bounded per run; the monitor loop calls this roughly hourly.
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

_EN_HINTS = re.compile(r"\b(the|and|of|to|in|for|with|on|is|are|that|from|this|has|have)\b", re.I)


def _looks_foreign(blob: str) -> bool:
    if not blob or len(blob) < 40:
        return False
    letters = [c for c in blob if c.isalpha()]
    if not letters:
        return False
    non_ascii = sum(1 for c in letters if ord(c) > 127) / len(letters)
    if non_ascii > 0.12:
        return True
    # Latin-script languages (pt/de/es/fr…) have few non-ASCII letters but no
    # English function words either.
    return len(blob) > 80 and not _EN_HINTS.search(blob)


async def _llm_topic_score(topic: str, title: str, summary: str) -> Optional[float]:
    from app.ai_models import LiteLLMModel, extract_content
    prompt = f"""You are a news-relevance scorer. The article below may be in ANY language — judge it in its own language, do not penalize for not being English.

Monitoring topic: "{topic}"

Article Title: {title}
Article Summary: {(summary or "")[:1200]}

How relevant is this article to the monitoring topic? If the topic names a company/brand, material events involving that company (lawsuits, filings, launches, scandals — including as plaintiff or named party) are HIGHLY relevant.

Respond with ONLY a number between 0.0 and 1.0."""
    try:
        model = LiteLLMModel.get_instance("gpt-5.4-mini")
        response = await model.agenerate_response(
            [{"role": "user", "content": prompt}], max_tokens=10, temperature=0.0)
        raw = extract_content(response).strip()
        m = re.search(r"(?:0?\.\d+|1\.0|[01])", raw)
        if not m:
            return None
        return max(0.0, min(1.0, float(m.group(0))))
    except Exception as e:
        logger.warning(f"lang_recovery LLM score failed: {e}")
        return None


async def recover_foreign_articles(db, limit: int = 20) -> dict:
    """Rescore up to `limit` foreign-looking low-relevance recent articles."""
    conn = db._temp_get_connection()
    summary = {"scanned": 0, "attempted": 0, "promoted": 0}
    try:
        rows = conn.execute(text("""
            SELECT uri, title, COALESCE(summary,''), topic
            FROM articles
            WHERE publication_date >= to_char(now() - interval '14 days','YYYY-MM-DD')
              AND (topic_alignment_score IS NULL OR topic_alignment_score < 0.4)
              AND (llm_processing_metadata->>'lang_recovery') IS NULL
              AND news_source NOT LIKE 'xpoz:%' AND news_source <> 'bluesky'
              -- Scope to Brand Watcher-relevant topics: an unscoped sweep over the
              -- whole firehose (>100k low-scored rows/30d) never converges.
              AND (topic LIKE 'Brand Monitoring %' OR topic ILIKE '%watch list%')
            ORDER BY publication_date DESC
            LIMIT 600
        """)).fetchall()
        summary["scanned"] = len(rows)
        candidates = [(u, t, sm, tp) for u, t, sm, tp in rows if _looks_foreign(f"{t or ''} {sm or ''}")]
        now_iso = datetime.now(timezone.utc).isoformat()
        for uri, title, art_summary, topic in candidates[:limit]:
            score = await _llm_topic_score(topic, title or "", art_summary)
            marker = {"at": now_iso, "score": score}
            if score is not None and score >= 0.4:
                conn.execute(text("""
                    UPDATE articles
                    SET topic_alignment_score = :s,
                        llm_processing_metadata = COALESCE(llm_processing_metadata, '{}'::jsonb)
                            || jsonb_build_object('lang_recovery', CAST(:m AS jsonb))
                    WHERE uri = :u
                """), {"s": score, "m": json.dumps(marker), "u": uri})
                summary["promoted"] += 1
                logger.info(f"lang_recovery promoted ({score:.2f}): {(title or '')[:80]}")
            else:
                # Stamp the attempt even on low/failed scores so we never re-scan.
                conn.execute(text("""
                    UPDATE articles
                    SET llm_processing_metadata = COALESCE(llm_processing_metadata, '{}'::jsonb)
                        || jsonb_build_object('lang_recovery', CAST(:m AS jsonb))
                    WHERE uri = :u
                """), {"m": json.dumps(marker), "u": uri})
            summary["attempted"] += 1
        conn.commit()
        if summary["attempted"]:
            logger.info(f"lang_recovery: {summary}")
        return summary
    except Exception as e:
        conn.rollback()
        logger.error(f"lang_recovery failed: {e}")
        return summary
    finally:
        conn.close()
