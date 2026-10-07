"""The brand path inside the real ingest pipeline, with every outside call
faked (tests/_cdq_ingest_fakes.py). Checks that one decision is made per
article and brand, that stored verdicts are left alone, that headline-only
coverage survives, and that the flag off leaves the old path untouched."""
import asyncio

import pytest

from app.services import automated_ingest_service as ais
from app.services import brand_ingest_hooks as bh
from app.services import brand_decision as bd
from app.services import brand_profile as bp
from tests._cdq_ingest_fakes import make_service, full_topic

TOPIC = "Brand Monitoring Colgate-Palmolive"
COLGATE = {"id": 5, "name": "colgate", "display_name": "Colgate-Palmolive", "brand_keywords": ["Colgate"],
           "product_keywords": [], "config": {"exclude_context": ["football"], "owned_domains": ["colgate.com"]},
           "enabled": True}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _art(uri, title, summary="", content=""):
    return {"uri": uri, "title": title, "summary": summary, "content": content,
            "news_source": "reuters.com", "publication_date": "2026-10-06", "topic": TOPIC, "analyzed": False}


class Recorder:
    def __init__(self):
        self.rejections, self.admitted, self.labels, self.article_only = [], [], [], []


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(ais._rejected, "enabled", lambda: False)
    monkeypatch.setattr(bd, "enabled", lambda: True)
    rec = Recorder()
    state = {"value": ("undecided", None, None)}

    async def stored_state(adb, uri, topic):
        return state["value"]

    async def save_rejection(adb, article, topic, d):
        rec.rejections.append((article["uri"], d))
        return "saved"

    async def save_admitted(adb, q, uri, topic, d):
        rec.admitted.append((uri, d, q))
        return "saved"

    async def save_label_with_status(adb, uri, topic, d, status):
        rec.labels.append((uri, d, status))
        return "saved"

    async def save_article_verdict_only(adb, article, topic, d):
        rec.article_only.append((article["uri"], d))
        return 1

    monkeypatch.setattr(bh._bstore, "stored_state", stored_state)
    monkeypatch.setattr(bh._bstore, "save_rejection", save_rejection)
    monkeypatch.setattr(bh._bstore, "save_admitted", save_admitted)
    monkeypatch.setattr(bh._bstore, "save_label_with_status", save_label_with_status)
    monkeypatch.setattr(bh._bstore, "save_article_verdict_only", save_article_verdict_only)
    monkeypatch.setattr(bh._bstore, "reuse_lookup_sync", lambda uri: (lambda key: None))

    judge_calls = []

    def set_judge(label=None, fail=False):
        def j(profile, article, mention, quality):
            judge_calls.append((article.get("uri"), quality))
            if fail:
                raise bd.JudgeUnavailable("timeout")
            return label, "because", "fake-1"
        j.route = "llm:fake"
        monkeypatch.setattr(bd, "configured_judges", lambda: (j,))

    svc = make_service({TOPIC: full_topic(TOPIC)}, score=0.9, threshold=0.45)
    monkeypatch.setattr(bh, "_resolution", lambda svc_, topic, group_id: bp.resolve([COLGATE], topic, group_id))
    bh._budget.update(window_start=0.0, used=0)

    # The harness replaces the scoring method with a fake; put the brand hook
    # in front of it, where transform_ingest puts it in the real method.
    _fake_score = svc._score_article_relevance_async

    async def scored(article, topic, keywords, threshold=None):
        ov = bh.relevance_override(svc, article, topic)
        if ov is not None:
            return ov
        return await _fake_score(article, topic, keywords)
    svc._score_article_relevance_async = scored

    async def quality(article):
        svc.quality_calls = getattr(svc, "quality_calls", []) + [article.get("uri")]
        return {"approved": True, "quality_score": 0.9}
    svc._quality_check_article_async = quality
    return svc, rec, state, set_judge, judge_calls


def test_flag_off_keeps_the_existing_path(env, monkeypatch):
    svc, rec, state, set_judge, calls = env
    monkeypatch.setattr(bd, "enabled", lambda: False)
    set_judge("subject")
    out = _run(svc.process_articles_batch([_art("u1", "Colgate cuts guidance", "Body")], TOPIC, ["Colgate"], route="manual"))
    assert out["saved"] == 1 and svc.score_calls == ["u1", "u1"] and calls == [] and rec.admitted == []  # old path scores twice


def test_earned_body_mention_one_judgment_no_numeric_rescore(env):
    svc, rec, state, set_judge, calls = env
    set_judge("notable")
    out = _run(svc.process_articles_batch(
        [_art("u2", "Consumer staples outlook", "Colgate cut its guidance, the CFO said.")], TOPIC, ["Colgate"], route="manual"))
    assert out["saved"] == 1 and len(calls) == 1 and svc.score_calls == []
    uri, d, q = rec.admitted[0]
    assert d.earned and d.brand_relation == "notable" and svc.analyze_calls == ["u2"]
    assert rec.labels == [("u2", d, "pending")]
    assert "UPDATE articles SET" in q[0]


def test_headline_only_coverage_skips_analysis_and_quality(env):
    svc, rec, state, set_judge, calls = env
    set_judge("passing")
    t = "Colgate-Palmolive seeks to divest some personal care brands"
    out = _run(svc.process_articles_batch([_art("u3", t, t)], TOPIC, ["Colgate"], route="manual"))
    assert out["saved"] == 1
    uri, d, q = rec.admitted[0]
    assert d.brand_relation == "notable" and d.provenance == "model+headline" and d.evidence["quality"] == "title_only"
    assert calls[0][1] == "title_only"
    assert svc.analyze_calls == [] and getattr(svc, "quality_calls", []) == []


def test_passing_body_mention_is_saved_as_rejection(env):
    svc, rec, state, set_judge, calls = env
    set_judge("passing")
    out = _run(svc.process_articles_batch(
        [_art("u4", "Retail roundup", "Shelves stocked with Colgate and other brands.")], TOPIC, ["Colgate"], route="manual"))
    assert out["saved"] == 0 and rec.admitted == [] and svc.analyze_calls == []
    assert rec.rejections[0][1].brand_relation == "passing"


def test_legacy_and_settled_rows_are_left_alone(env):
    svc, rec, state, set_judge, calls = env
    set_judge("subject")
    for s in (("legacy", None, "approved"), ("label_done", bd.Decision("decided", "subject", "independent"), "approved"),
              ("invalid", None, "approved")):
        state["value"] = s
        out = _run(svc.process_articles_batch([_art("u5", "Colgate results", "Body")], TOPIC, ["Colgate"], route="manual"))
        assert out["saved"] == 0
    assert calls == [] and rec.admitted == [] and rec.rejections == [] and svc.score_calls == []


def test_label_retry_reuses_the_label_without_judging(env):
    svc, rec, state, set_judge, calls = env
    set_judge("other")
    state["value"] = ("label_retry", bd.Decision("decided", "subject", "independent", "model", "x",
                                                 {"quality": "summary"}), "enrichment_failed")
    out = _run(svc.process_articles_batch([_art("u6", "Colgate results", "Body")], TOPIC, ["Colgate"], route="enrichment_retry"))
    assert out["saved"] == 1 and calls == [] and rec.admitted[0][1].brand_relation == "subject"


def test_unavailable_judgment_is_an_error_not_a_rejection(env):
    svc, rec, state, set_judge, calls = env
    set_judge(fail=True)
    out = _run(svc.process_articles_batch(
        [_art("u7", "Staples", "Colgate cut guidance.")], TOPIC, ["Colgate"], route="manual"))
    assert out["saved"] == 0 and out["errors"]
    d = rec.rejections[0][1]
    assert d.outcome == "unavailable" and d.ingest_status == "relevance_check_failed"


def test_no_mention_goes_to_topic_rules_and_lands_in_sector(env):
    svc, rec, state, set_judge, calls = env
    set_judge("subject")
    svc.score_article_relevance = lambda article, topic, keywords: {"relevance_score": 0.8}
    out = _run(svc.process_articles_batch(
        [_art("u8", "Toothpaste market grows 4%", "Industry sales rose.")], TOPIC, ["Colgate"], route="manual"))
    assert out["saved"] == 1 and calls == []
    d = rec.admitted[0][1]
    assert d.brand_relation == "sector" and d.admitted and not d.earned


def test_collision_rejected_by_rule_without_a_call(env):
    svc, rec, state, set_judge, calls = env
    set_judge("subject")
    _run(svc.process_articles_batch([_art("u9", "Colgate football wins on Hail Mary", "Football recap.")],
                                    TOPIC, ["Colgate"], route="manual"))
    assert calls == [] and rec.rejections[0][1].brand_relation == "other"


def test_theme_topics_are_untouched(env):
    svc, rec, state, set_judge, calls = env
    set_judge("subject")
    theme = "AI and Machine Learning"
    svc._research.topic_configs[theme] = full_topic(theme)
    a = _art("u10", "Colgate uses AI", "Body")
    a["topic"] = theme
    out = _run(svc.process_articles_batch([a], theme, ["AI"], route="manual"))
    assert out["saved"] == 1 and svc.score_calls == ["u10", "u10"] and calls == []


def test_judge_budget_leaves_the_rest_retryable(env, monkeypatch):
    svc, rec, state, set_judge, calls = env
    monkeypatch.setenv("BRAND_JUDGE_MAX_CALLS_PER_HOUR", "2")
    set_judge("notable")
    arts = [_art(f"b{i}", "Staples outlook", f"Colgate cut guidance, note {i}.") for i in range(5)]
    out = _run(svc.process_articles_batch(arts, TOPIC, ["Colgate"], route="manual"))
    assert len(calls) == 2 and out["saved"] == 2
    over = [d for _, d in rec.rejections if d.outcome == "unavailable"]
    assert len(over) == 3 and all("budget" in d.failure for d in over)


class _AnalyzeSvc:
    def __init__(self):
        self.seen = []

    async def _analyze_article_content_async(self, article, topic):
        self.seen.append(dict(article))
        if not (article.get("summary") or article.get("content")):
            return dict(article, analyzed=False)   # the site's "insufficient content" path
        return dict(article, analyzed=True, summary="from " + ("content" if article.get("content") else "summary"))


def test_admitted_item_without_summary_is_analysed_from_its_scraped_page():
    """6 Oct, sunstar: a Reuters Haleon story admitted as subject arrived with a
    scraped page but no summary, and failed analysis as insufficient content."""
    from app.services import brand_ingest_hooks as hooks
    svc = _AnalyzeSvc()
    d = bd.Decision("decided", "subject", "independent", evidence={"quality": "full"})
    art = {"uri": "r1", "title": "Haleon posts sales growth", "summary": "", "_scraped_content": "Haleon said on Thursday...",
           hooks.DECISION_KEY: d}
    out = _run(hooks.analyze_or_skip(svc, art, TOPIC))
    assert out["analyzed"] is True and out["summary"] == "from content"
    assert "content" not in out and out[hooks.DECISION_KEY] is d
    assert svc.seen[0]["content"].startswith("Haleon said")


def test_admitted_item_with_no_text_at_all_is_not_given_an_invented_summary():
    from app.services import brand_ingest_hooks as hooks
    svc = _AnalyzeSvc()
    d = bd.Decision("decided", "subject", "independent", evidence={"quality": "summary"})
    art = {"uri": "r2", "title": "Haleon posts sales growth", "summary": "", hooks.DECISION_KEY: d}
    out = _run(hooks.analyze_or_skip(svc, art, TOPIC))
    assert out["analyzed"] is True and not out.get("summary") and svc.seen == []


def test_non_brand_article_without_summary_keeps_the_site_behaviour():
    from app.services import brand_ingest_hooks as hooks
    svc = _AnalyzeSvc()
    out = _run(hooks.analyze_or_skip(svc, {"uri": "r3", "title": "x", "summary": "", "_scraped_content": "page"}, TOPIC))
    assert out["analyzed"] is False and "content" not in svc.seen[0]


def test_admitted_item_without_summary_uses_the_page_saved_this_run():
    from app.services import brand_ingest_hooks as hooks

    class _Db:
        async def get_raw_article_async(self, uri):
            return {"uri": uri, "raw_markdown": "Haleon reported organic growth of 5%..."}

    svc = _AnalyzeSvc(); svc.async_db = _Db()
    d = bd.Decision("decided", "subject", "independent", evidence={"quality": "full"})
    out = _run(hooks.analyze_or_skip(svc, {"uri": "r4", "title": "Haleon growth", "summary": "", hooks.DECISION_KEY: d}, TOPIC))
    assert out["summary"] == "from content" and svc.seen[0]["content"].startswith("Haleon reported")



def test_topic_scorer_works_with_old_and_new_threshold_signatures():
    """6 Oct, wbm: the older ingest service's get_relevance_threshold takes no
    topic; the hook called it with one and every no-mention candidate failed."""
    from app.services import brand_ingest_hooks as hooks

    class _Old:
        def score_article_relevance(self, article, topic, keywords):
            return {"relevance_score": 0.2}

        def get_relevance_threshold(self):
            return 0.5

    class _New(_Old):
        def get_relevance_threshold(self, topic=None):
            return 0.1

    assert hooks._topic_scorer(_Old(), TOPIC, [])({"uri": "x"}) is False
    assert hooks._topic_scorer(_New(), TOPIC, [])({"uri": "x"}) is True
    assert hooks._threshold(_Old(), TOPIC) == 0.5
