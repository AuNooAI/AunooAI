"""scripts/brand_rollout/transform_ingest.py on a minimal ingest source."""
import importlib.util
import os

spec = importlib.util.spec_from_file_location(
    "ti", os.path.join(os.path.dirname(__file__), "..", "scripts", "brand_rollout", "transform_ingest.py"))
ti = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ti)

SRC = '''import asyncio
import logging

class S:
    async def _process_single_article_async(self, article, topic, keywords):
        try:
            self.logger.debug(f"🔄 Processing article: {article_title}")
            if not (article.get('summary') or article.get('content')) or not article.get('title'):
                return 1
            enriched_article = await asyncio.wait_for(
                self._analyze_article_content_async(enriched_article, topic),
                timeout=60)
            quality_result = await self._quality_check_article_async(enriched_article)
            success = await self.async_db.update_article_with_enrichment(enriched_article)
        except Exception:
            pass

    async def _score_article_relevance_async(self, article_data, topic, keywords):
        """Async version of relevance scoring"""
        return None
'''


def test_applies_every_edit_and_compiles():
    out, report, ok = ti.transform(SRC)
    assert ok
    statuses = dict(report)
    assert all(statuses[n] == "applied" for n in ("import", "pre_decide", "relevance_override",
                                                  "analyze_or_skip", "quality_or_skip", "save_enriched", "no_text_guard"))
    assert statuses["ledger_guard"].startswith("not in this version")
    compile(out, "x.py", "exec")
    assert "_bhooks.pre_decide(self, article, topic, keywords" in out
    assert out.count(ti.MARK) >= 6


def test_second_run_changes_nothing():
    once, _, _ = ti.transform(SRC)
    twice, report, ok = ti.transform(once)
    assert ok and twice == once and all(s == "present" for _, s in report)


def test_missing_required_anchor_writes_nothing():
    bad = SRC.replace('"""Async version of relevance scoring"""', '"""something else"""')
    out, report, ok = ti.transform(bad)
    assert not ok and dict(report)["relevance_override"].startswith("REQUIRED")
