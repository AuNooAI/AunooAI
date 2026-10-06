"""The brand path's entry points into the ingest pipeline.

automated_ingest_service differs from site to site (thirteen versions on
2026-10-06), so the brand path is kept here and the service calls it from five
one-line hooks that scripts/brand_rollout/transform_ingest.py inserts at
anchors present in every version:

  pre_decide           top of _process_single_article_async: settle decided
                       rows, decide undecided ones once, mark admitted ones
  relevance_override   top of _score_article_relevance_async: an admitted
                       article is not scored again (no second judgment)
  analyze_or_skip      the analysis call: a headline-only item is not given a
                       generated summary
  quality_or_skip      the quality check: a headline-only item has no body to check
  save_enriched        the final save: article and scoped match rows together

Everything is off unless BRAND_RELATION_DECISIONS is set; with it off each
hook returns at once and the pipeline is unchanged.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from app.services import brand_decision as _bdec
from app.services import brand_decision_store as _bstore
from app.services import brand_profile as _bprof

logger = logging.getLogger(__name__)

DECISION_KEY = "_brand_decision"
_budget = {"window_start": 0.0, "used": 0}
_BUDGET_WINDOW_S = 3600.0


def _reserve_judge_call() -> bool:
    """Rolling one-hour cap on brand judge calls (BRAND_JUDGE_MAX_CALLS_PER_HOUR,
    default 600). Reserved before deciding, so concurrent articles cannot pass it."""
    cap = int(os.getenv("BRAND_JUDGE_MAX_CALLS_PER_HOUR", "600") or 600)
    now = time.monotonic()
    if now - _budget["window_start"] > _BUDGET_WINDOW_S:
        _budget.update(window_start=now, used=0)
    if _budget["used"] >= cap:
        return False
    _budget["used"] += 1
    return True


def _settle_budget(model_calls: int) -> None:
    _budget["used"] = max(0, _budget["used"] + model_calls - 1)


def _resolution(svc, topic: str, group_id: Optional[int]):
    conn = svc.db._temp_get_connection()
    try:
        return _bprof.resolve_for_topic(conn, topic, group_id)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _threshold(svc, topic: str) -> float:
    """The site's relevance threshold. Older ingest versions (wbm, wileytest,
    wiley on 6 Oct) take no topic argument; calling them with one raised, and
    every candidate without a brand mention ended "unavailable"."""
    import inspect
    fn = svc.get_relevance_threshold
    try:
        takes_topic = len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        takes_topic = True
    return float(fn(topic) if takes_topic else fn())


def _topic_scorer(svc, topic: str, keywords: List[str]):
    """The site's existing topic rules for an article that does not name the
    brand: relevant (True), not (False) or unavailable (None)."""
    def score(article: Dict[str, Any]) -> Optional[bool]:
        try:
            res = svc.score_article_relevance(article, topic, keywords)
        except Exception as e:  # noqa: BLE001 - includes RelevanceUnavailableError
            logger.debug("brand topic scorer failed: %s", e)
            return None
        val = (res or {}).get("relevance_score")
        if val is None:
            return None
        try:
            return float(val) >= _threshold(svc, topic)
        except Exception as e:  # noqa: BLE001
            logger.warning("brand topic scorer: no relevance threshold for %r: %s", topic, e)
            return None
    return score


async def pre_decide(svc, article: Dict[str, Any], topic: str, keywords: List[str],
                     ledger_ctx: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """None: not the brand path (flag off, not a brand topic, no profile, no
    match row). {"action": "return", "result": ...}: settled here. {"action":
    "continue"}: admitted, marked on the article for the rest of the pipeline."""
    if not _bdec.enabled() or not topic or not _bprof.brand_name_for_topic(topic):
        return None
    uri = article.get("uri") or ""
    adb = svc.async_db
    try:
        state, stored, art_status = await _bstore.stored_state(adb, uri, topic)
    except Exception as e:  # noqa: BLE001 - e.g. br_001 not applied
        logger.warning("Brand path unavailable for %s (%s); existing path used", uri[:80], type(e).__name__)
        return None
    if state == "no_row":
        return None
    loop = asyncio.get_event_loop()
    group_id = (ledger_ctx or {}).get("group_id")
    resolution = await loop.run_in_executor(None, _resolution, svc, topic, group_id)
    if resolution.profile is None and not resolution.error:
        return None
    settled = {"action": "return", "result": {"status": "filtered", "uri": uri, "reason": "already_decided"}}
    if state in ("label_done", "legacy"):
        return settled
    if state == "invalid":
        logger.warning("Invalid stored brand label for %s under %r; left for repair", uri[:80], topic)
        return settled
    if state == "label_retry":
        # The keyword route leaves analysis retries to the enrichment sweep
        # where the site has one (ledger_ctx exists only on those sites).
        if ledger_ctx is not None and art_status == "enrichment_failed":
            return settled
        if stored.admitted:
            article[DECISION_KEY] = stored
            return {"action": "continue"}
        await _bstore.save_article_verdict_only(adb, article, topic, stored)
        return settled

    view = dict(article)
    if article.get("_scraped_content") and not view.get("content"):
        view["raw"] = article["_scraped_content"]
    judges = _bdec.configured_judges()
    reserved = _reserve_judge_call()
    if not reserved:
        def over_budget(*_a):
            raise _bdec.JudgeUnavailable("hourly brand judge budget reached")
        over_budget.route = "budget"
        judges = (over_budget,)
    scorer = _topic_scorer(svc, topic, keywords)
    d = await loop.run_in_executor(None, lambda: _bdec.decide(
        resolution, view, judges=judges, topic_scorer=scorer,
        reuse=_bstore.reuse_lookup_sync(uri), collection_query=article.get("_collection_query")))
    if reserved:
        _settle_budget(d.model_calls if d is not None else 0)
    if d is None:
        return None
    logger.info(
        "Brand decision %r %s: policy=%s/%s outcome=%s relation=%s source=%s provenance=%s route=%s "
        "calls=%s admitted=%s earned=%s%s", topic, uri[:80], _bprof.POLICY_VERSION, _bdec.RUBRIC_VERSION,
        d.outcome, d.brand_relation, d.source_relation, d.provenance, d.route, d.model_calls,
        d.admitted, d.earned, f" failure={d.failure[:160]}" if d.failure else "")
    if d.outcome == "decided" and d.admitted:
        # The label is stored now with status 'pending', so a later failure in
        # analysis or quality keeps it and nothing is judged twice.
        try:
            saved = await _bstore.save_label_with_status(adb, uri, topic, d, "pending")
        except _bstore.SaveFailed as e:
            logger.error("Brand label not saved for %s: %s", uri[:80], e)
            return {"action": "return", "result": {"status": "error", "uri": uri, "error": f"brand label save failed: {e}"}}
        if saved == "concurrent":
            return settled
        article[DECISION_KEY] = d
        return {"action": "continue"}
    saved = await _bstore.save_rejection(adb, article, topic, d)
    if saved == "concurrent":
        return settled
    if d.outcome == "unavailable":
        result = {"status": "error", "uri": uri, "reason": "relevance_check_failed",
                  "error": f"brand judgment unavailable: {d.failure}"}
    elif d.outcome == "deferred":
        result = {"status": "filtered", "uri": uri, "reason": "deferred", "detail": d.reason}
    else:
        result = {"status": "filtered", "uri": uri, "reason": "brand_relation",
                  "brand_relation": d.brand_relation, "relevance_score": d.grade}
    return {"action": "return", "result": result}


def relevance_override(svc, article: Dict[str, Any], topic: str) -> Optional[Dict[str, Any]]:
    """For an admitted article: the stored decision as a relevance result, so
    neither the quick check nor the post-analysis rescore judges it again.
    The comparison score is at least the site's threshold, so a label decides
    inclusion; the stored score is the label's grade."""
    d = article.get(DECISION_KEY)
    if d is None:
        return None
    try:
        thr = _threshold(svc, topic)
    except Exception:  # noqa: BLE001
        thr = 0.0
    grade = d.grade if d.grade is not None else 0.0
    return {
        "relevance_score": max(grade, thr, 1.0 if d.admitted else 0.0),
        "topic_alignment_score": grade,
        "keyword_relevance_score": grade,
        "confidence_score": 1.0,
        "overall_match_explanation": d.explanation()[:1000],
    }


def title_only(article: Dict[str, Any]) -> bool:
    d = article.get(DECISION_KEY)
    return bool(d is not None and d.evidence.get("quality") == "title_only" and not article.get("_scraped_content"))


def _no_summary_text(article: Dict[str, Any]) -> bool:
    return not (article.get("summary") or article.get("content"))


async def analyze_or_skip(svc, article: Dict[str, Any], topic: str):
    """The analysis step, except for a headline-only brand item: its summary
    would be generated from the headline, which is invented body text.

    The analysis reads only 'summary' or 'content'. An admitted brand item
    that arrived without a summary but with a scraped page (Reuters, 6 Oct)
    is analysed from that page; with no text at all it is treated as
    headline-only, instead of failing as "insufficient content"."""
    if title_only(article):
        article["analyzed"] = True
        return article
    if article.get(DECISION_KEY) is not None and _no_summary_text(article):
        page = (article.get("_scraped_content") or "").strip()
        if not page:
            # Scraped during this run but kept in a local variable of the
            # pipeline; the pipeline saved it to raw_articles just before.
            try:
                raw = await svc.async_db.get_raw_article_async(article.get("uri") or "")
                page = ((raw or {}).get("raw_markdown") or "").strip()
            except Exception:  # noqa: BLE001 - older async_db without the reader
                page = ""
        if not page:
            article["analyzed"] = True
            return article
        view = dict(article)
        view["content"] = page[:20000]
        out = await svc._analyze_article_content_async(view, topic)
        if isinstance(out, dict):
            out.pop("content", None)
            out[DECISION_KEY] = article[DECISION_KEY]
            return out
        return out
    return await svc._analyze_article_content_async(article, topic)


async def quality_or_skip(svc, article: Dict[str, Any]) -> Dict[str, Any]:
    if title_only(article):
        return {"approved": True, "quality_score": None,
                "quality_issues": "headline only: body text not available"}
    return await svc._quality_check_article_async(article)


async def save_enriched(svc, article: Dict[str, Any], topic: str) -> bool:
    """The final save. For an admitted brand item the article UPDATE and its
    match rows commit together and a save touching no row fails."""
    d = article.get(DECISION_KEY)
    if d is None:
        return await svc.async_db.update_article_with_enrichment(article)
    from app.services.async_db import build_enrichment_update
    article["topic"] = article.get("topic") or topic
    clean = {k: v for k, v in article.items() if k != DECISION_KEY}
    try:
        await _bstore.save_admitted(svc.async_db, build_enrichment_update(clean),
                                    article.get("uri") or "", topic, d)
        return True
    except _bstore.SaveFailed as e:
        logger.error("Brand save failed for %s: %s", (article.get("uri") or "")[:80], e)
        return False
