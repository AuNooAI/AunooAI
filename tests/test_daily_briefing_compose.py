"""Briefing Desk compose: configuration, curation validation, fallback, backfill.

The pipeline's failures were not in the ranking arithmetic but in the wiring
around it — a floor the request advertised and the service never applied, a
window the caller asked for and the gather ignored, two endpoints that passed
different arguments, and a fallback that shipped whatever was newest when the
curator said nothing usable. These tests hold that wiring in place.

The database and the LLM are faked, so the whole file runs without PostgreSQL.
"""

import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from app.services import daily_briefing_compose_service as svc

NOW = datetime.now(timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")


def article(uri, *, align=0.85, days_ago=0.5, source=None, title=None, **extra):
    row = {
        "uri": uri,
        "title": title or f"Story about {uri}",
        "summary": f"Summary of {uri}",
        "publication_date": _iso(days_ago),
        "news_source": source or f"{uri}.com",
        "topic_alignment_score": align,
        "keyword_relevance_score": 0.6,
        "quality_score": 0.8,
        "confidence_score": 0.95,
        "factual_reporting": "high",
        "mbfc_credibility_rating": "high credibility",
        "overall_match_explanation": "matches the topic",
        "user_preference": None,
    }
    row.update(extra)
    return row


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class FakeFacade:
    """Applies the eligibility rules the real query applies, so a test can show
    a filter is honoured end to end rather than only in SQL."""

    def __init__(self, by_topic: Dict[str, List[Dict[str, Any]]]):
        self.corpus = by_topic
        self.calls: List[Dict[str, Any]] = []
        self.staged_articles: List[Dict[str, Any]] = []
        self.staged_incidents: List[Dict[str, Any]] = []
        self.staged_emerging: List[Dict[str, Any]] = []
        self.deleted: List[int] = []
        self.create_should_fail = False

    def get_briefing_candidate_articles(self, topic, *, days_back, min_alignment,
                                        limit, exclude_social=True):
        from app.services.social_sources import is_social_source
        self.calls.append({"topic": topic, "days_back": days_back,
                           "min_alignment": min_alignment, "limit": limit,
                           "exclude_social": exclude_social})
        cutoff = NOW - timedelta(days=days_back)
        out = []
        for row in self.corpus.get(topic, []):
            if exclude_social and is_social_source(row.get("news_source")):
                continue
            score = row.get("topic_alignment_score")
            if score is None or score < min_alignment:
                continue
            published = svc.datetime.fromisoformat(row["publication_date"]).replace(tzinfo=timezone.utc)
            if published < cutoff:
                continue
            out.append(dict(row))
        out.sort(key=lambda r: (-r["topic_alignment_score"], r["publication_date"]), reverse=False)
        return out[:limit]

    def get_desk_briefings_for_user(self, username):
        return []

    def create_desk_briefing(self, *, name, username, description, topic):
        if self.create_should_fail:
            raise RuntimeError("boom")
        return 4242

    def delete_desk_briefing(self, briefing_id, username):
        self.deleted.append(briefing_id)
        return True

    def add_article_to_desk_briefing(self, briefing_id, username, payload):
        self.staged_articles.append(payload)
        return True

    def add_incident_to_desk_briefing(self, briefing_id, username, payload):
        self.staged_incidents.append(payload)
        return True

    def add_emerging_topic_to_desk_briefing(self, briefing_id, username, payload):
        self.staged_emerging.append(payload)
        return True


class FakeDB:
    def __init__(self, facade):
        self.facade = facade

    def _temp_get_connection(self):  # pragma: no cover - patched out in tests
        raise AssertionError("compose should not open a raw connection in tests")


class FakeEmergingTopic:
    def __init__(self, label, confidence):
        self.label = label
        self.confidence = confidence

    def to_dict(self):
        return {"topic_label": self.label, "confidence_score": self.confidence,
                "why_emerging": "because", "topic_filter": "t"}


def install_stubs(monkeypatch, *, emerging=None, incidents=None, curate=None,
                  emerging_calls=None):
    """Neutralise everything around the article path: profile, history, few-shot,
    pinned model, emerging-topic detection, incident detection and the curator."""
    monkeypatch.setattr(svc, "_get_default_org_profile", lambda db: None)
    monkeypatch.setattr(svc, "_get_pinned_briefing_model", lambda db: None)
    monkeypatch.setattr(svc, "_fewshot_examples", lambda db, k=5: {"articles": [], "incidents": [], "emerging": []})
    monkeypatch.setattr(svc, "_recently_shared_items",
                        lambda db, days: {"article_uris": set(), "incidents": set(), "emerging": set()})

    async def fake_detect(topics, days_back, model, profile_id=None):
        return list(incidents or [])
    monkeypatch.setattr(svc, "_detect_incidents", fake_detect)

    class FakeService:
        def __init__(self, config=None, ai_model_getter=None):
            pass

        async def run_detection(self, topic_filter=None, days_back=7):
            return None

        def get_emerging_topics(self, topic_filter=None, days_back=7,
                                min_confidence=0.0, limit=20):
            if emerging_calls is not None:
                emerging_calls.append({"topic": topic_filter, "min_confidence": min_confidence,
                                       "days_back": days_back})
            return [t for t in (emerging or []) if t.confidence >= min_confidence]

    import app.services.emerging_topics as et
    monkeypatch.setattr(et, "EmergingTopicsService", FakeService)
    monkeypatch.setattr(et, "EmergingTopicsConfig", lambda **kw: None)

    async def fake_curate(payload, fewshot, model, profile_ctx=""):
        return curate(payload) if callable(curate) else curate
    monkeypatch.setattr(svc, "_curate", fake_curate)


def compose(db, topics, **kwargs):
    """Drain the streaming pipeline; return (events, final complete/error event)."""
    async def run():
        events = []
        async for e in svc.compose_daily_briefing_stream(db, "tester", topics, **kwargs):
            events.append(e)
        return events
    events = asyncio.get_event_loop().run_until_complete(run())
    final = next((e for e in reversed(events) if e["stage"] in ("complete", "error")), None)
    return events, final


@pytest.fixture
def loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# --------------------------------------------------------------------------
# Configuration reaches the service
# --------------------------------------------------------------------------

class TestConfiguration:
    def test_the_service_accepts_every_field_the_request_model_declares(self):
        """The non-streaming endpoint passed min_alignment and min_confidence to
        a generator that did not accept them, so every call to it was a 500."""
        from app.routes.daily_reports_routes import AutoComposeRequest, _compose_kwargs

        kwargs = _compose_kwargs(AutoComposeRequest())
        inspect.signature(svc.compose_daily_briefing_stream).bind(None, "u", ["t"], **kwargs)

    def test_both_endpoints_build_the_same_configuration(self):
        import app.routes.daily_reports_routes as routes

        source = inspect.getsource(routes)
        assert source.count("_compose_kwargs(request)") == 2

    def test_the_request_defaults_carry_a_real_alignment_floor(self):
        from app.routes.daily_reports_routes import AutoComposeRequest

        req = AutoComposeRequest()
        assert req.min_alignment > 0.0
        assert req.min_confidence > 0.0

    def test_the_configured_floor_and_window_reach_the_query(self, loop, monkeypatch):
        facade = FakeFacade({"T": [article("a")]})
        install_stubs(monkeypatch, curate=None)
        compose(FakeDB(facade), ["T"], min_alignment=0.55, days_back=9, run_detection=False)
        assert facade.calls[0]["min_alignment"] == 0.55
        assert facade.calls[0]["days_back"] == 9
        assert facade.calls[0]["exclude_social"] is True

    def test_no_caller_disables_the_alignment_floor(self):
        """`min_alignment=-1.0` was hard-coded in the gather, which made the
        advertised floor a no-op."""
        assert "-1.0" not in inspect.getsource(svc._gather_candidate_articles)

    def test_a_seven_day_request_reaches_a_strong_four_day_old_article(self, loop, monkeypatch):
        facade = FakeFacade({"T": [article("old", align=0.9, days_ago=4)]})
        install_stubs(monkeypatch, curate=None)
        compose(FakeDB(facade), ["T"], days_back=7, run_detection=False)
        assert [a["uri"] for a in facade.staged_articles] == ["old"]

    def test_a_three_day_request_excludes_that_same_article(self, loop, monkeypatch):
        facade = FakeFacade({"T": [article("old", align=0.9, days_ago=4)]})
        install_stubs(monkeypatch, curate=None)
        compose(FakeDB(facade), ["T"], days_back=3, run_detection=False)
        assert facade.staged_articles == []

    def test_a_candidate_exactly_on_the_floor_is_kept(self, loop, monkeypatch):
        facade = FakeFacade({"T": [article("edge", align=0.4)]})
        install_stubs(monkeypatch, curate=None)
        compose(FakeDB(facade), ["T"], min_alignment=0.4, run_detection=False)
        assert [a["uri"] for a in facade.staged_articles] == ["edge"]

    def test_min_confidence_excludes_lower_confidence_emerging_topics(self, loop, monkeypatch):
        calls: List[Dict[str, Any]] = []
        facade = FakeFacade({"T": [article("a")]})
        install_stubs(
            monkeypatch, curate=None, emerging_calls=calls,
            emerging=[FakeEmergingTopic("strong", 0.9), FakeEmergingTopic("weak", 0.3)],
        )
        compose(FakeDB(facade), ["T"], min_confidence=0.6, run_detection=False)
        assert calls[0]["min_confidence"] == 0.6
        assert [t["name"] for t in facade.staged_emerging] == ["strong"]


# --------------------------------------------------------------------------
# What the curator is shown
# --------------------------------------------------------------------------

class TestCuratorPayload:
    def test_the_curator_receives_the_ranking_signals(self, loop, monkeypatch):
        seen = {}

        def capture(payload):
            seen["articles"] = payload["candidate_articles"]
            return {"articles": [{"id": "a0", "reason": "ok"}], "incidents": [], "emerging_topics": []}

        facade = FakeFacade({"T": [article("a")]})
        install_stubs(monkeypatch, curate=capture)
        compose(FakeDB(facade), ["T"], run_detection=False)

        candidate = seen["articles"][0]
        for field in ("id", "title", "source", "date", "topics", "prerank_score",
                      "topic_alignment", "keyword_relevance", "quality",
                      "analysis_confidence", "credibility", "summary"):
            assert field in candidate, f"curator payload is missing {field}"

    def test_social_posts_never_reach_the_curator(self, loop, monkeypatch):
        """The reported symptom: a Bluesky post in a daily news briefing."""
        seen = {}

        def capture(payload):
            seen["articles"] = payload["candidate_articles"]
            return {"articles": [], "incidents": [], "emerging_topics": []}

        facade = FakeFacade({"T": [
            article("post", align=0.0, days_ago=0.001, source="bluesky",
                    title="Post by @sjpete.bsky.social"),
            article("news", align=0.84, days_ago=1),
        ]})
        install_stubs(monkeypatch, curate=capture)
        compose(FakeDB(facade), ["T"], run_detection=False)
        assert [c["title"] for c in seen["articles"]] == ["Story about news"]

    def test_every_topic_with_material_gets_shortlist_exposure(self, loop, monkeypatch):
        seen = {}

        def capture(payload):
            seen["articles"] = payload["candidate_articles"]
            return {"articles": [], "incidents": [], "emerging_topics": []}

        facade = FakeFacade({
            "Busy": [article(f"busy{i}", align=0.9, days_ago=0.01) for i in range(60)],
            "Quiet": [article("quiet", align=0.75, days_ago=2)],
            "Sparse": [article("sparse", align=0.7, days_ago=2)],
        })
        install_stubs(monkeypatch, curate=capture)
        compose(FakeDB(facade), ["Busy", "Quiet", "Sparse"], run_detection=False)

        shown = {t for c in seen["articles"] for t in c["topics"]}
        assert shown == {"Busy", "Quiet", "Sparse"}
        assert [c["id"] for c in seen["articles"]][:3] == ["a0", "a1", "a2"]
        assert {"quiet", "sparse"} <= {c["title"].split()[-1] for c in seen["articles"][:3]}

    def test_a_duplicate_uri_across_topics_keeps_both_topics(self, loop, monkeypatch):
        seen = {}

        def capture(payload):
            seen["articles"] = payload["candidate_articles"]
            return {"articles": [], "incidents": [], "emerging_topics": []}

        shared = article("shared", align=0.9)
        facade = FakeFacade({"A": [dict(shared)], "B": [dict(shared)]})
        install_stubs(monkeypatch, curate=capture)
        compose(FakeDB(facade), ["A", "B"], run_detection=False)

        assert len(seen["articles"]) == 1
        assert set(seen["articles"][0]["topics"]) == {"A", "B"}


# --------------------------------------------------------------------------
# Validation, fallback, backfill
# --------------------------------------------------------------------------

class TestSelectionHandling:
    def _corpus(self, n=12):
        return {"T": [article(f"a{i}", align=0.9 - i * 0.01, days_ago=i * 0.1) for i in range(n)]}

    def test_a_failed_curator_falls_back_to_the_relevance_ranking(self, loop, monkeypatch):
        facade = FakeFacade(self._corpus())
        install_stubs(monkeypatch, curate=None)
        _, final = compose(FakeDB(facade), ["T"], run_detection=False)
        assert final["fallback"] is True
        assert len(facade.staged_articles) == svc.TARGET_ARTICLES
        assert [a["uri"] for a in facade.staged_articles] == [f"a{i}" for i in range(8)]

    def test_malformed_json_produces_the_same_result_as_a_failed_call(self, loop, monkeypatch):
        facade_a = FakeFacade(self._corpus())
        install_stubs(monkeypatch, curate=None)
        compose(FakeDB(facade_a), ["T"], run_detection=False)

        facade_b = FakeFacade(self._corpus())
        install_stubs(monkeypatch, curate=lambda p: None)
        compose(FakeDB(facade_b), ["T"], run_detection=False)

        assert ([a["uri"] for a in facade_a.staged_articles]
                == [a["uri"] for a in facade_b.staged_articles])

    def test_unknown_and_duplicate_ids_are_rejected_and_backfilled(self, loop, monkeypatch):
        picks = {"articles": [{"id": "a1", "reason": "real"},
                              {"id": "a1", "reason": "same again"},
                              {"id": "nope", "reason": "invented"}],
                 "incidents": [], "emerging_topics": []}
        facade = FakeFacade(self._corpus())
        install_stubs(monkeypatch, curate=lambda p: picks)
        _, final = compose(FakeDB(facade), ["T"], run_detection=False)

        uris = [a["uri"] for a in facade.staged_articles]
        assert uris[0] == "a1"
        assert len(uris) == svc.TARGET_ARTICLES
        assert len(set(uris)) == len(uris)
        assert final["backfill_count"] == 7

    def test_three_valid_picks_are_topped_up_with_the_best_remaining(self, loop, monkeypatch):
        picks = {"articles": [{"id": i, "reason": "r"} for i in ("a5", "a6", "a7")],
                 "incidents": [], "emerging_topics": []}
        facade = FakeFacade(self._corpus())
        install_stubs(monkeypatch, curate=lambda p: picks)
        compose(FakeDB(facade), ["T"], run_detection=False)

        uris = [a["uri"] for a in facade.staged_articles]
        assert uris[:3] == ["a5", "a6", "a7"]
        assert uris[3:] == ["a0", "a1", "a2", "a3", "a4"]

    def test_the_curator_cannot_exceed_the_target(self, loop, monkeypatch):
        picks = {"articles": [{"id": f"a{i}", "reason": "r"} for i in range(12)],
                 "incidents": [], "emerging_topics": []}
        facade = FakeFacade(self._corpus())
        install_stubs(monkeypatch, curate=lambda p: picks)
        compose(FakeDB(facade), ["T"], run_detection=False)
        assert len(facade.staged_articles) == svc.TARGET_ARTICLES

    def test_incidents_are_capped_at_their_target_too(self, loop, monkeypatch):
        incidents = [{"name": f"inc{i}", "significance": "high", "article_uris": []}
                     for i in range(20)]
        picks = {"articles": [], "incidents": [{"id": f"i{i}", "reason": "r"} for i in range(20)],
                 "emerging_topics": []}
        facade = FakeFacade(self._corpus())
        install_stubs(monkeypatch, curate=lambda p: picks, incidents=incidents)
        compose(FakeDB(facade), ["T"], run_detection=False)
        assert len(facade.staged_incidents) == svc.TARGET_INCIDENTS

    def test_an_article_sourced_by_a_selected_incident_is_replaced_not_just_dropped(
            self, loop, monkeypatch):
        incidents = [{"name": "inc", "significance": "high", "article_uris": ["a0", "a1"]}]
        picks = {"articles": [{"id": "a0", "reason": "r"}, {"id": "a1", "reason": "r"},
                              {"id": "a2", "reason": "r"}],
                 "incidents": [{"id": "i0", "reason": "r"}], "emerging_topics": []}
        facade = FakeFacade(self._corpus())
        install_stubs(monkeypatch, curate=lambda p: picks, incidents=incidents)
        compose(FakeDB(facade), ["T"], run_detection=False)

        uris = [a["uri"] for a in facade.staged_articles]
        assert "a0" not in uris and "a1" not in uris
        assert len(uris) == svc.TARGET_ARTICLES

    def test_an_empty_curator_response_over_a_full_pool_falls_back(self, loop, monkeypatch):
        """Returning no articles when there were candidates is a failed call,
        not an editorial verdict — it used to produce an empty briefing."""
        facade = FakeFacade(self._corpus())
        install_stubs(monkeypatch,
                      curate=lambda p: {"articles": [], "incidents": [], "emerging_topics": []})
        _, final = compose(FakeDB(facade), ["T"], run_detection=False)
        assert final["fallback"] is True
        assert len(facade.staged_articles) == svc.TARGET_ARTICLES

    def test_it_stops_below_target_when_the_pool_is_genuinely_small(self, loop, monkeypatch):
        facade = FakeFacade(self._corpus(n=3))
        install_stubs(monkeypatch, curate=None)
        compose(FakeDB(facade), ["T"], run_detection=False)
        assert len(facade.staged_articles) == 3

    def test_repeated_runs_produce_identical_selections(self, loop, monkeypatch):
        picks = {"articles": [{"id": "a4", "reason": "r"}], "incidents": [], "emerging_topics": []}
        runs = []
        for _ in range(2):
            facade = FakeFacade(self._corpus())
            install_stubs(monkeypatch, curate=lambda p: picks)
            compose(FakeDB(facade), ["T"], run_detection=False)
            runs.append([a["uri"] for a in facade.staged_articles])
        assert runs[0] == runs[1]

    def test_staged_articles_keep_the_fields_the_briefing_renders(self, loop, monkeypatch):
        facade = FakeFacade(self._corpus(n=1))
        install_stubs(monkeypatch,
                      curate=lambda p: {"articles": [{"id": "a0", "reason": "why it matters"}],
                                        "incidents": [], "emerging_topics": []})
        compose(FakeDB(facade), ["T"], run_detection=False)

        staged = facade.staged_articles[0]
        assert staged["uri"] == "a0"
        assert staged["title"] and staged["source"] and staged["publication_date"]
        assert staged["topic"] == "T" and staged["matched_topics"] == ["T"]
        assert staged["topic_alignment_score"] == pytest.approx(0.9)
        assert staged["prerank_score"] > 0
        assert staged["analysis"]["key_insight"] == "why it matters"


# --------------------------------------------------------------------------
# Failure handling
# --------------------------------------------------------------------------

class TestFailureHandling:
    def test_a_failure_after_the_draft_is_created_does_not_leave_an_empty_draft(
            self, loop, monkeypatch):
        facade = FakeFacade({"T": [article("a")]})
        install_stubs(monkeypatch, curate=None)

        def explode(*a, **kw):
            raise RuntimeError("gather exploded")
        monkeypatch.setattr(svc, "_gather_candidate_articles", explode)

        _, final = compose(FakeDB(facade), ["T"], run_detection=False)
        assert final["stage"] == "error"
        assert facade.deleted == [4242]

    def test_the_browser_does_not_see_the_raw_exception(self, loop, monkeypatch):
        facade = FakeFacade({"T": [article("a")]})
        install_stubs(monkeypatch, curate=None)
        monkeypatch.setattr(svc, "_gather_candidate_articles",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("secret internals")))
        _, final = compose(FakeDB(facade), ["T"], run_detection=False)
        assert "secret internals" not in final["message"]

    def test_the_non_streaming_wrapper_raises_rather_than_returning_success(
            self, loop, monkeypatch):
        facade = FakeFacade({"T": [article("a")]})
        install_stubs(monkeypatch, curate=None)
        monkeypatch.setattr(svc, "_gather_candidate_articles",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("nope")))
        with pytest.raises(RuntimeError):
            loop.run_until_complete(
                svc.compose_daily_briefing(FakeDB(facade), "tester", ["T"], run_detection=False))

    def test_streaming_and_non_streaming_select_the_same_articles(self, loop, monkeypatch):
        picks = {"articles": [{"id": "a2", "reason": "r"}], "incidents": [], "emerging_topics": []}
        corpus = {"T": [article(f"a{i}", align=0.9 - i * 0.01) for i in range(10)]}

        facade_stream = FakeFacade(corpus)
        install_stubs(monkeypatch, curate=lambda p: picks)
        compose(FakeDB(facade_stream), ["T"], run_detection=False)

        facade_direct = FakeFacade(corpus)
        install_stubs(monkeypatch, curate=lambda p: picks)
        loop.run_until_complete(
            svc.compose_daily_briefing(FakeDB(facade_direct), "tester", ["T"], run_detection=False))

        assert ([a["uri"] for a in facade_stream.staged_articles]
                == [a["uri"] for a in facade_direct.staged_articles])
