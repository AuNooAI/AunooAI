"""WP3a: scrape after the relevance gate (docs/pipelines/08_INGEST_FIX_SPEC.md).

process_articles_batch is run with the per-article step stubbed, so what is
checked is which articles get a page before the gate: collector content and
cached pages need no scrape, a snippet too thin to judge is scraped first,
brand topics keep the old pre-gate scrape, and everything else waits until
it has passed the gate.
"""
import asyncio
import logging

import pytest

from app.services import automated_ingest_service as ais

LONG = "A sentence long enough for the relevance gate to judge the article on its merits. " * 2


class FakeAsyncDb:
    def __init__(self, cached):
        self.cached = cached

    async def get_raw_article_async(self, uri):
        return {"raw_markdown": self.cached[uri]} if uri in self.cached else None


def _svc(monkeypatch, cached=None):
    svc = object.__new__(ais.AutomatedIngestService)
    svc.logger = logging.getLogger("test")
    svc.async_db = FakeAsyncDb(cached or {})
    svc._last_extraction_outcomes = {}
    svc.scraped_batches = []
    seen = {}

    async def scrape_batch(uris, topic=None):
        svc.scraped_batches.append(list(uris))
        svc._last_extraction_outcomes = {u: ais.EXTRACTION_OK for u in uris}
        return {u: "PAGE " + "x" * 400 for u in uris}

    async def single(article, topic, keywords, **kw):
        seen[article["uri"]] = article.get("_scraped_content")
        if not article.get("_scraped_content") and article.get("passes"):
            article["_scraped_after_gate"] = True
            return {"status": "success", "uri": article["uri"]}
        return {"status": "filtered", "uri": article["uri"], "reason": "relevance_threshold"}

    monkeypatch.setattr(svc, "scrape_articles_batch", scrape_batch, raising=False)
    monkeypatch.setattr(svc, "_process_single_article_async", single, raising=False)
    monkeypatch.setattr(svc, "_configuration_block_reasons", lambda topics: {}, raising=False)
    monkeypatch.setattr(ais._rejected, "enabled", lambda: False)
    return svc, seen


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_gate_evidence_threshold(monkeypatch):
    assert ais.gate_evidence_insufficient({"title": "t", "summary": "Read more"})
    assert ais.gate_evidence_insufficient({"title": "t"})
    assert not ais.gate_evidence_insufficient({"title": "t", "summary": LONG})
    assert not ais.gate_evidence_insufficient({"title": "t", "content": LONG})
    monkeypatch.setenv("INGEST_MIN_GATE_TEXT_CHARS", "500")
    assert ais.gate_evidence_insufficient({"title": "t", "summary": LONG})


def test_only_thin_snippets_are_scraped_before_the_gate(monkeypatch):
    svc, seen = _svc(monkeypatch, cached={"u-cached": "CACHED " + "y" * 300})
    articles = [
        {"uri": "u-content", "title": "t", "content": "C" * 300},
        {"uri": "u-cached", "title": "t", "summary": "short"},
        {"uri": "u-thin", "title": "t", "summary": "Read more"},
        {"uri": "u-empty", "title": "t"},
        {"uri": "u-pass", "title": "t", "summary": LONG, "passes": True},
        {"uri": "u-reject", "title": "t", "summary": LONG},
    ]
    res = run(svc.process_articles_batch(articles, topic="AI", keywords=["ai"]))
    assert svc.scraped_batches == [["u-thin", "u-empty"]]
    assert seen["u-content"] == "C" * 300 and seen["u-cached"].startswith("CACHED")
    assert seen["u-thin"].startswith("PAGE") and seen["u-empty"].startswith("PAGE")
    assert seen["u-pass"] is None and seen["u-reject"] is None
    assert res["scrape"] == {"pre_gate": 2, "cache_hits": 1, "post_gate": 1}
    assert articles[2]["_prescrape_reason"] == "insufficient_gate_text"


def test_brand_topics_keep_the_pre_gate_scrape(monkeypatch):
    svc, seen = _svc(monkeypatch)
    articles = [{"uri": "b1", "title": "t", "summary": LONG}, {"uri": "b2", "title": "t", "summary": LONG}]
    res = run(svc.process_articles_batch(articles, topic="Brand Monitoring Acme", keywords=["acme"]))
    assert svc.scraped_batches == [["b1", "b2"]]
    assert articles[0]["_prescrape_reason"] == "brand_decision_reads_page"
    assert res["scrape"]["pre_gate"] == 2
