"""Work package 27: Firecrawl batch rejection isolates the rejecting URL,
redirect wrappers are resolved first, and the per-URL fallback runs for
what the batch did not deliver."""
import asyncio

import pytest

from app.services import automated_ingest_service as ais
from app.services.automated_ingest_service import (
    EXTRACTION_OK, EXTRACTION_REJECTED, EXTRACTION_NO_CONTENT, EXTRACTION_FALLBACK,
)
from tests._cdq_ingest_fakes import make_service, full_topic, article


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


GOOGLE = "https://news.google.com/rss/articles/CBMiabc123?oc=5"


def _wire_firecrawl(svc, *, no_content=()):
    """A fake provider that rejects any batch holding a Google News link and
    a resolver that records its calls and fails to resolve."""
    svc.submitted = []
    svc.resolved = []

    async def _submit(firecrawl_app, urls):
        svc.submitted.append(list(urls))
        if any("news.google.com" in u for u in urls):
            raise Exception("Bad Request: No valid URLs provided")
        return {u: (None if u in no_content else f"# body of {u}") for u in urls}

    async def _resolve(url):
        svc.resolved.append(url)
        return url  # resolution failed: send as is

    svc._firecrawl_submit = _submit
    svc._resolve_redirect_wrapper = _resolve


def test_one_google_news_url_in_ten_yields_nine_ok_and_one_rejected():
    svc = make_service({"T": full_topic()})
    _wire_firecrawl(svc)
    uris = [f"https://site{i}.example/a" for i in range(9)] + [GOOGLE]

    out = _run(svc._firecrawl_batch_scrape(object(), uris))

    assert set(out) == set(uris)                                   # every input URL is a key
    assert sum(1 for u in uris if out[u]) == 9
    assert out[GOOGLE] is None
    outcomes = svc._last_extraction_outcomes
    assert sum(1 for v in outcomes.values() if v == EXTRACTION_OK) == 9
    assert outcomes[GOOGLE] == EXTRACTION_REJECTED
    assert svc.resolved == [GOOGLE]                                 # resolver ran before the provider
    assert len(svc.submitted) >= 2                                  # the batch was split, not dropped


def test_rejected_batch_is_never_a_bare_empty_mapping():
    svc = make_service({"T": full_topic()})
    _wire_firecrawl(svc)
    out = _run(svc._firecrawl_batch_scrape(object(), [GOOGLE]))
    assert out == {GOOGLE: None}
    assert svc._last_extraction_outcomes == {GOOGLE: EXTRACTION_REJECTED}


def test_google_url_wrapper_resolves_without_network():
    svc = make_service({"T": full_topic()})
    target = _run(svc._resolve_redirect_wrapper("https://www.google.com/url?url=https%3A%2F%2Fpub.example%2Fstory&x=1"))
    assert target == "https://pub.example/story"


def test_scrape_batch_falls_back_only_for_undelivered_non_rejected_urls():
    svc = make_service({"T": full_topic()}, firecrawl_app=object())
    empty = "https://site7.example/empty"
    _wire_firecrawl(svc, no_content={empty})
    fallback_calls = []

    async def _fallback(uris):
        fallback_calls.append(list(uris))
        return {u: f"fallback {u}" for u in uris}

    svc._fallback_individual_scraping = _fallback
    # restore the real batch method the fixture stubbed out
    svc.scrape_articles_batch = ais.AutomatedIngestService.scrape_articles_batch.__get__(svc)
    uris = ["https://site1.example/a", empty, GOOGLE]

    out = _run(svc.scrape_articles_batch(uris, topic="T"))

    assert fallback_calls == [[empty]]                              # not the rejected one, not the ok one
    assert out["https://site1.example/a"].startswith("# body")
    assert out[empty].startswith("fallback")
    assert out[GOOGLE] is None
    oc = svc._last_extraction_outcomes
    assert oc["https://site1.example/a"] == EXTRACTION_OK
    assert oc[empty] == EXTRACTION_FALLBACK
    assert oc[GOOGLE] == EXTRACTION_REJECTED
    assert svc.async_db.raw_saved == ["https://site1.example/a", empty]


def test_batch_writes_extraction_status_and_content_kind_into_articles(monkeypatch):
    monkeypatch.setattr(ais._rejected, "enabled", lambda: False)
    svc = make_service({"T": full_topic()}, score=0.9)
    a_ok = article("https://site1.example/a", summary="")      # needs scraping
    a_rej = article(GOOGLE, summary="")

    async def _scrape(uris, topic=None):
        svc._last_extraction_outcomes = {a_ok["uri"]: EXTRACTION_OK, GOOGLE: EXTRACTION_REJECTED}
        return {a_ok["uri"]: "full body", GOOGLE: None}

    svc.scrape_articles_batch = _scrape

    async def _single(art, topic, keywords, **kw):
        return {"status": "filtered", "uri": art["uri"], "reason": "relevance_threshold"}

    svc._process_single_article_async = _single
    out = _run(svc.process_articles_batch([a_ok, a_rej], "T", ["k"], route="manual"))

    assert a_ok["extraction_status"] == EXTRACTION_OK and a_ok["content_kind"] == "full_text"
    assert a_rej["extraction_status"] == EXTRACTION_REJECTED and "content_kind" not in a_rej
    assert out["extraction"] == {EXTRACTION_OK: 1, EXTRACTION_REJECTED: 1}
