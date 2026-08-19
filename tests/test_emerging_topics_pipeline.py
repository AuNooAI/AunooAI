"""Emerging-topics pipeline: run lifecycle, scoping, ordering, and scoring.

These cover the defects the 2026-08-19 hardening pass fixed. They run without a
database: the pieces that talk to Postgres are stubbed, and what is asserted is
the behaviour around them — which run state is written, what is persisted
together, what survives validation, and in what order.

The SQL-level guarantees (scope isolation in the queries, novelty de-duplication,
the migration round trip) live in tests/test_emerging_topics_sql.py, which needs
a database and skips without one.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.emerging_topics.article_validator import (
    ArticleValidator,
    ValidationResult,
)
from app.services.emerging_topics.date_utils import (
    parse_publication_timestamp,
    publication_ts_sql,
)
from app.services.emerging_topics import notification_filters as nf
from app.services.emerging_topics import sentinels
from app.services.emerging_topics.run_lock import normalize_topic_filter, scope_key
from app.services.emerging_topics.theme_proposer import ProposedTheme, ProposalResult
from app.services.emerging_topics.theme_validator import ThemeValidator
from app.services.emerging_topics.trend_scorer import TrendScorer


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------

class FakeLock:
    """Stands in for the advisory lock; records acquire/release."""

    def __init__(self):
        self.acquired = False
        self.released = False

    def acquire(self):
        self.acquired = True
        return self

    def release(self):
        self.released = True


class FakeRunStore:
    """Records what the service does to detection_runs and topic rows."""

    def __init__(self):
        self.runs = {}
        self.next_run_id = 1
        self.saved_topics = []
        self.saved_history = []
        self.missed_runs_calls = []

    def create_run(self, topic_filter, config, model):
        run_id = self.next_run_id
        self.next_run_id += 1
        self.runs[run_id] = {"status": "running", "topic_filter": topic_filter}
        return run_id

    def statuses(self):
        return [r["status"] for r in self.runs.values()]


def build_service(store, *, themes=None, sampled=5, analysis=None,
                  trend=None, save_error_on=None, propose_error=None,
                  historical=False):
    """An EmergingTopicsService with every database and model call stubbed."""
    from app.services.emerging_topics.emerging_topics_service import (
        EmergingTopicsService,
        EmergingTopicsConfig,
    )
    from app.services.emerging_topics.deep_analyzer import DeepAnalysis
    from app.services.emerging_topics.trend_scorer import TrendScore

    service = EmergingTopicsService(config=EmergingTopicsConfig(min_articles_for_theme=1))

    async def fake_propose(topic_filter=None, days_back=7, max_sample=250, **kw):
        if propose_error:
            raise propose_error
        return ProposalResult(
            themes=list(themes or []),
            sampled_uris=[f"uri-{i}" for i in range(sampled)],
        )

    async def fake_assign(themes, **kwargs):
        return themes

    async def fake_analyze(**kwargs):
        return analysis or DeepAnalysis()

    service.theme_proposer.propose_themes = fake_propose
    service.theme_proposer.assign_articles_to_themes = fake_assign
    service.deep_analyzer.analyze = fake_analyze
    service.trend_scorer.calculate = lambda uris, days_back=7: (trend or TrendScore())
    service.theme_validator.validate = lambda t: _immediate(list(t))
    service._get_default_org_profile = lambda: None
    service._fetch_articles_for_validation = lambda uris: []
    service._check_auto_retirement = lambda ids, tf: 0
    service._create_detection_run = store.create_run

    async def fake_historical(**kwargs):
        return historical

    service._check_historical_coverage = fake_historical

    def fake_persist(run_id, topics, topic_filter, articles_sampled, duration):
        for index, topic in enumerate(topics, start=1):
            if save_error_on is not None and index == save_error_on:
                raise RuntimeError("simulated save failure")
            topic.id = 100 + index
            topic.topic_filter = topic_filter
            store.saved_topics.append(topic)
            store.saved_history.append((topic.id, run_id))
        store.missed_runs_calls.append((run_id, topic_filter))
        store.runs[run_id]["status"] = "completed"
        store.runs[run_id]["topics_detected"] = len(topics)
        store.runs[run_id]["articles_sampled"] = articles_sampled

    service._persist_run_results = fake_persist

    def fake_fail(run_id, message, duration):
        store.runs[run_id]["status"] = "failed"
        store.runs[run_id]["error_message"] = message

    service._fail_detection_run = fake_fail
    return service


async def _immediate(value):
    return value


def collect(service, **kwargs):
    """Drive the streaming generator to completion and return its events."""
    async def run():
        events = []
        async for event in service.run_detection_streaming(
            run_lock=FakeLock(), **kwargs
        ):
            events.append(event)
        return events

    return asyncio.run(run())


def a_theme(label="Theme", uris=None, entities=None):
    return ProposedTheme(
        theme_label=label,
        theme_description=f"{label} description",
        search_query=label,
        key_entities=entities or ["Acme"],
        why_emerging="it is new",
        article_uris=list(uris or ["a", "b", "c"]),
        article_distances=[0.1, 0.2, 0.3][: len(uris or ["a", "b", "c"])],
    )


# ---------------------------------------------------------------------------
# 1. Run lifecycle
# ---------------------------------------------------------------------------

def test_no_proposed_themes_completes_the_run_with_zero_topics():
    store = FakeRunStore()
    service = build_service(store, themes=[], sampled=42)

    events = collect(service)

    assert store.statuses() == ["completed"]
    complete = [e for e in events if e["event"] == "complete"]
    assert len(complete) == 1
    assert complete[0]["total_emerging_topics"] == 0
    assert not [e for e in events if e["event"] == "error"]


def test_sample_size_reported_is_the_real_sample_not_the_ceiling():
    store = FakeRunStore()
    service = build_service(store, themes=[], sampled=37)

    events = collect(service)
    complete = [e for e in events if e["event"] == "complete"][0]

    # The configured ceiling is 250; only 37 articles existed.
    assert complete["articles_sampled"] == 37
    assert complete["articles_analyzed"] == 37
    assert store.runs[1]["articles_sampled"] == 37


def test_encoder_failure_fails_the_run_and_emits_no_success():
    store = FakeRunStore()
    service = build_service(
        store, propose_error=RuntimeError("DeBERTa encoder service unreachable")
    )

    events = collect(service)

    assert store.statuses() == ["failed"]
    assert "encoder" in store.runs[1]["error_message"]
    assert not [e for e in events if e["event"] == "complete"]
    errors = [e for e in events if e["event"] == "error"]
    assert len(errors) == 1
    assert errors[0]["status"] == "failed"


def test_failure_saving_the_second_topic_leaves_no_successful_run():
    store = FakeRunStore()
    service = build_service(
        store,
        themes=[a_theme("First"), a_theme("Second")],
        save_error_on=2,
    )

    events = collect(service)

    assert store.statuses() == ["failed"]
    assert not [e for e in events if e["event"] == "complete"]
    # The real _persist_run_results runs in one transaction; the double records
    # the first topic, and the run is still reported as failed.
    assert store.runs[1].get("topics_detected") is None


def test_every_exit_path_leaves_no_run_in_running():
    for kwargs in (
        {"themes": []},
        {"themes": [a_theme()]},
        {"propose_error": RuntimeError("boom")},
        {"themes": [a_theme(), a_theme("Other")], "save_error_on": 1},
    ):
        store = FakeRunStore()
        service = build_service(store, **kwargs)
        collect(service)
        assert "running" not in store.statuses(), kwargs


def test_client_disconnect_fails_the_run_and_frees_the_scope():
    """Closing the generator mid-stream must not leave a run at 'running'.

    An async generator that awaits while handling GeneratorExit raises "async
    generator ignored GeneratorExit", so the lock release has to be synchronous
    — exactly the case where holding the scope forever would hurt most.
    """
    store = FakeRunStore()
    service = build_service(store, themes=[a_theme()])
    lock = FakeLock()

    async def run():
        agen = service.run_detection_streaming(run_lock=lock)
        await agen.__anext__()   # first progress event
        await agen.aclose()      # client hangs up

    asyncio.run(run())

    assert store.statuses() == ["failed"]
    assert "cancelled" in store.runs[1]["error_message"].lower()


def test_a_service_owned_lock_is_freed_on_disconnect():
    store = FakeRunStore()
    service = build_service(store, themes=[a_theme()])
    own_lock = FakeLock()

    import app.services.emerging_topics.emerging_topics_service as svc_module
    original = svc_module.DetectionRunLock
    svc_module.DetectionRunLock = lambda topic_filter=None: own_lock
    try:
        async def run():
            agen = service.run_detection_streaming()
            await agen.__anext__()
            await agen.aclose()

        asyncio.run(run())
    finally:
        svc_module.DetectionRunLock = original

    assert own_lock.acquired and own_lock.released


def test_non_streaming_entry_point_raises_instead_of_returning_empty():
    from app.services.emerging_topics.emerging_topics_service import DetectionFailed

    store = FakeRunStore()
    service = build_service(store, propose_error=RuntimeError("database is down"))

    with pytest.raises(DetectionFailed):
        asyncio.run(service.run_detection(run_lock=FakeLock()))


def test_lock_is_released_on_failure():
    store = FakeRunStore()
    service = build_service(store, propose_error=RuntimeError("boom"))
    lock = FakeLock()

    async def run():
        async for _ in service.run_detection_streaming(run_lock=lock):
            pass

    asyncio.run(run())
    # The route owns a passed-in lock, so the service leaves it alone; a lock
    # the service takes itself is released in its own finally.
    assert lock.released is False

    store2 = FakeRunStore()
    service2 = build_service(store2, propose_error=RuntimeError("boom"))
    own_lock = FakeLock()
    service2_lock_holder = []

    import app.services.emerging_topics.emerging_topics_service as svc_module
    original = svc_module.DetectionRunLock

    def fake_lock_factory(topic_filter=None):
        service2_lock_holder.append(own_lock)
        return own_lock

    svc_module.DetectionRunLock = fake_lock_factory
    try:
        async def run2():
            async for _ in service2.run_detection_streaming():
                pass
        asyncio.run(run2())
    finally:
        svc_module.DetectionRunLock = original

    assert own_lock.acquired and own_lock.released


# ---------------------------------------------------------------------------
# 2. Lock scoping
# ---------------------------------------------------------------------------

def test_lock_scope_separates_filters_and_treats_null_as_its_own_scope():
    assert scope_key("climate") == scope_key("Climate")   # case-insensitive
    assert scope_key("climate") != scope_key("semiconductors")
    assert scope_key(None) != scope_key("climate")
    assert scope_key(None) == scope_key("")               # blank means global
    assert scope_key(None) == scope_key("   ")


def test_normalize_topic_filter_collapses_blanks_to_the_global_scope():
    assert normalize_topic_filter(None) is None
    assert normalize_topic_filter("") is None
    assert normalize_topic_filter("  ") is None
    assert normalize_topic_filter(" climate ") == "climate"


# ---------------------------------------------------------------------------
# 3. Article validation preserves everything past the cost cap
# ---------------------------------------------------------------------------

class StubModel:
    def __init__(self, payload):
        self.payload = payload

    async def generate(self, prompt, max_tokens=None):
        return self.payload


def run_validator(payload, articles, ordered_uris, min_confidence=0.7):
    validator = ArticleValidator(ai_model_getter=lambda name: StubModel(payload))
    return asyncio.run(validator.validate_theme_articles(
        theme_label="T",
        theme_description="d",
        key_entities=[],
        articles=articles,
        min_confidence=min_confidence,
        ordered_uris=ordered_uris,
    ))


def test_articles_past_the_validation_cap_are_kept():
    ordered = [f"uri-{i}" for i in range(30)]
    articles = [{"uri": u, "title": u, "summary": "s"} for u in ordered[:15]]
    payload = "[" + ",".join(
        f'{{"uri": "{u}", "relevant": true, "confidence": 0.9}}' for u in ordered[:15]
    ) + "]"

    kept = run_validator(payload, articles, ordered)

    assert kept == ordered, "positions 16-30 were never judged and must survive"


def test_rejected_uris_are_removed_without_disturbing_the_others():
    ordered = [f"uri-{i}" for i in range(20)]
    articles = [{"uri": u, "title": u, "summary": "s"} for u in ordered[:15]]
    verdicts = []
    for i, u in enumerate(ordered[:15]):
        relevant = "false" if i in (2, 7) else "true"
        verdicts.append(f'{{"uri": "{u}", "relevant": {relevant}, "confidence": 0.9}}')
    payload = "[" + ",".join(verdicts) + "]"

    kept = run_validator(payload, articles, ordered)

    assert "uri-2" not in kept and "uri-7" not in kept
    expected = [u for u in ordered if u not in ("uri-2", "uri-7")]
    assert kept == expected


def test_a_low_confidence_positive_verdict_still_rejects():
    ordered = ["uri-0", "uri-1"]
    articles = [{"uri": u, "title": u, "summary": "s"} for u in ordered]
    payload = (
        '[{"uri": "uri-0", "relevant": true, "confidence": 0.2},'
        ' {"uri": "uri-1", "relevant": true, "confidence": 0.95}]'
    )

    assert run_validator(payload, articles, ordered) == ["uri-1"]


def test_validation_failure_keeps_the_whole_theme():
    class BrokenModel:
        async def generate(self, prompt, max_tokens=None):
            raise RuntimeError("model down")

    validator = ArticleValidator(ai_model_getter=lambda name: BrokenModel())
    ordered = ["a", "b", "c"]
    kept = asyncio.run(validator.validate_theme_articles(
        theme_label="T", theme_description="d", key_entities=[],
        articles=[{"uri": u} for u in ordered], ordered_uris=ordered,
    ))
    assert kept == ordered


# ---------------------------------------------------------------------------
# 4. Stable merging and the post-merge minimum
# ---------------------------------------------------------------------------

def test_merge_preserves_the_primary_ranking_and_appends_the_rest():
    validator = ThemeValidator(min_articles=1)
    primary = a_theme("Primary", uris=["p1", "p2", "p3", "p4"])
    primary.article_distances = [0.1, 0.2, 0.3, 0.4]
    secondary = a_theme("Secondary", uris=["p2", "s1"], entities=["Beta"])
    secondary.article_distances = [0.9, 0.5]

    merged = validator.merge_themes(primary, secondary)

    assert merged.article_uris == ["p1", "p2", "p3", "p4", "s1"]
    # p2's distance comes from the primary theme, whose ranking wins.
    assert merged.article_distances == [0.1, 0.2, 0.3, 0.4, 0.5]
    assert merged.key_entities[:2] == ["Acme", "Beta"]


def test_merging_is_deterministic_across_runs():
    orderings = set()
    for _ in range(15):
        validator = ThemeValidator(min_articles=1)
        primary = a_theme("Primary", uris=[f"p{i}" for i in range(12)])
        primary.article_distances = [i / 100 for i in range(12)]
        secondary = a_theme("Secondary", uris=[f"s{i}" for i in range(12)])
        secondary.article_distances = [i / 100 for i in range(12)]
        merged = validator.merge_themes(primary, secondary)
        orderings.add(tuple(merged.article_uris))
    assert len(orderings) == 1, "set()-based dedup used to reshuffle every run"


def test_theme_below_the_minimum_after_validation_is_dropped():
    validator = ThemeValidator(min_articles=3)
    validator.calculate_coherence = lambda uris: 0.1

    keep = a_theme("Keeps", uris=["a", "b", "c"])
    drop = a_theme("Drops", uris=["x"])

    surviving = validator.validate_and_merge([keep, drop])

    assert [t.theme_label for t in surviving] == ["Keeps"]


# ---------------------------------------------------------------------------
# 5. Dates, velocity, and the SQL guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("2026-08-19", datetime(2026, 8, 19, tzinfo=timezone.utc)),
    ("2026-08-19T14:30:00", datetime(2026, 8, 19, 14, 30, tzinfo=timezone.utc)),
    ("2026-08-19T14:30:00Z", datetime(2026, 8, 19, 14, 30, tzinfo=timezone.utc)),
    ("2026-08-19 14:30:00", datetime(2026, 8, 19, 14, 30, tzinfo=timezone.utc)),
    ("2026-08-19T16:30:00+02:00", datetime(2026, 8, 19, 14, 30, tzinfo=timezone.utc)),
])
def test_publication_timestamps_keep_their_time_and_timezone(value, expected):
    parsed = parse_publication_timestamp(value)
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.astimezone(timezone.utc) == expected


@pytest.mark.parametrize("value", [None, "", "   ", "not a date", "N/A", "0000"])
def test_unreadable_dates_return_none_rather_than_raising(value):
    assert parse_publication_timestamp(value) is None


def test_publication_ts_sql_guards_the_cast():
    expression = publication_ts_sql("a.publication_date")
    assert "CASE" in expression
    assert "::timestamp" not in expression, "a blind cast aborts on one bad row"
    assert "to_timestamp" in expression


def test_velocity_counts_use_the_hour_within_a_one_day_window():
    scorer = TrendScorer()
    now = datetime.now(timezone.utc)
    # One article in the first half of a 1-day window, four in the second. Both
    # halves are the same calendar day, so the old date-only parse put all five
    # at midnight and counted 5/0.
    articles = (
        [{"publication_date": (now - timedelta(hours=20)).isoformat()}]
        + [{"publication_date": (now - timedelta(hours=2)).isoformat()}] * 4
    )

    score, label, first, second = scorer.calculate_velocity_score(articles, days_back=1)

    assert (first, second) == (1, 4)
    assert label == "accelerating"


def test_velocity_over_a_multi_day_window():
    scorer = TrendScorer()
    now = datetime.now(timezone.utc)
    articles = (
        [{"publication_date": (now - timedelta(days=6)).isoformat()}] * 4
        + [{"publication_date": (now - timedelta(days=1)).isoformat()}] * 1
    )

    _, label, first, second = scorer.calculate_velocity_score(articles, days_back=7)

    assert (first, second) == (4, 1)
    assert label == "decelerating"


# ---------------------------------------------------------------------------
# 6. Sentinels and confidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "Not mentioned", "not mentioned", "NOT MENTIONED", "Not mentioned.",
    "unknown", "None", "n/a", "", "   ", "Not specified",
])
def test_placeholder_strings_are_recognised(value):
    assert sentinels.is_sentinel(value)


def test_placeholder_only_analysis_adds_no_confidence():
    from app.services.emerging_topics.emerging_topics_service import (
        EmergingTopic,
        EmergingTopicsService,
        EmergingTopicsConfig,
    )

    service = EmergingTopicsService(config=EmergingTopicsConfig())
    empty = EmergingTopic(
        actors=sentinels.clean_list_dict({
            "companies": ["Not mentioned"], "people": ["Unknown"], "organizations": [],
        }),
        events=sentinels.clean_events({"trigger_event": "Not mentioned", "timeline": []}),
    )
    substantive = EmergingTopic(
        actors=sentinels.clean_list_dict({"companies": ["ASML"], "people": []}),
        events=sentinels.clean_events({"trigger_event": "Export licence revoked"}),
    )

    assert service._calculate_confidence_v2(empty) == pytest.approx(0.5)
    assert service._calculate_confidence_v2(substantive) == pytest.approx(0.6)


def test_confidence_is_capped_at_one():
    from app.services.emerging_topics.emerging_topics_service import (
        EmergingTopic,
        EmergingTopicsService,
        EmergingTopicsConfig,
    )

    service = EmergingTopicsService(config=EmergingTopicsConfig())
    topic = EmergingTopic(
        composite_score=95,
        article_count=50,
        actors={"companies": ["ASML"]},
        events={"trigger_event": "Something happened"},
    )
    assert service._calculate_confidence_v2(topic) == 1.0


def test_mixed_placeholder_and_real_values_keep_only_the_real_ones():
    cleaned = sentinels.clean_list(["ASML", "Not mentioned", "", "Nvidia", "unknown"])
    assert cleaned == ["ASML", "Nvidia"]


def test_urgency_outside_the_allowed_values_falls_back_to_medium():
    assert sentinels.clean_synthesis({"urgency": "catastrophic"})["urgency"] == "medium"
    assert sentinels.clean_synthesis({"urgency": "HIGH"})["urgency"] == "high"


def test_topic_creation_strips_placeholders_before_storage():
    from app.services.emerging_topics.emerging_topics_service import (
        EmergingTopicsService, EmergingTopicsConfig,
    )
    from app.services.emerging_topics.deep_analyzer import (
        DeepAnalysis, Actors, Events, Synthesis,
    )
    from app.services.emerging_topics.trend_scorer import TrendScore

    service = EmergingTopicsService(config=EmergingTopicsConfig())
    analysis = DeepAnalysis(
        actors=Actors(companies=["Not mentioned"], people=["Jane Roe"]),
        events=Events(trigger_event="Not mentioned", timeline=["unknown", "A ruling"]),
        synthesis=Synthesis(key_takeaway="Not mentioned", urgency="high"),
        model_used="test-model",
    )

    topic = service._create_topic_from_theme(
        theme=a_theme(), analysis=analysis, trend=TrendScore(),
        detection_date=date(2026, 8, 19), topic_filter="climate",
    )

    assert topic.actors["companies"] == []
    assert topic.actors["people"] == ["Jane Roe"]
    assert topic.events["trigger_event"] == ""
    assert topic.events["timeline"] == ["A ruling"]
    assert topic.synthesis["key_takeaway"] == ""
    assert topic.synthesis["model_used"] == "test-model"
    assert topic.topic_filter == "climate"


def test_topic_dict_exposes_the_scope():
    from app.services.emerging_topics.emerging_topics_service import EmergingTopic

    assert EmergingTopic(topic_filter="climate").to_dict()["topic_filter"] == "climate"
    assert EmergingTopic().to_dict()["topic_filter"] is None


# ---------------------------------------------------------------------------
# 7. Notification semantics
# ---------------------------------------------------------------------------

def test_default_filters_select_a_newly_proposed_v2_topic():
    topic = {"detection_type": "llm_proposed", "velocity": "stable",
             "confidence_score": 0.8}
    selected = nf.select_topics_for_notification([topic], nf.DEFAULT_FILTERS, 0.7)
    assert selected == [topic]


def test_the_old_default_selected_nothing_the_pipeline_writes():
    topic = {"detection_type": "llm_proposed", "velocity": "stable"}
    # The shipped default was ["accelerating", "new_cluster"]; under the v2
    # vocabulary it maps to something that does match.
    assert nf.normalize_filters(["accelerating", "new_cluster"]) == [
        "accelerating", "llm_proposed",
    ]
    assert nf.topic_matches_filters(topic, ["accelerating", "new_cluster"])
    # ... and the literal comparison it used to do matches nothing.
    assert topic["detection_type"] not in ("accelerating", "new_cluster")


def test_acceleration_is_matched_against_velocity_not_detection_type():
    accelerating = {"detection_type": "ongoing_topic", "velocity": "accelerating"}
    stable = {"detection_type": "ongoing_topic", "velocity": "stable"}

    assert nf.topic_matches_filters(accelerating, ["accelerating"])
    assert not nf.topic_matches_filters(stable, ["accelerating"])


def test_legacy_values_map_predictably():
    assert nf.normalize_filters(["new_cluster"]) == ["llm_proposed"]
    assert nf.normalize_filters(["proto_cluster"]) == ["llm_proposed"]
    assert nf.normalize_filters(["splitting"]) == list(nf.DEFAULT_FILTERS)
    assert nf.normalize_filters([]) == list(nf.DEFAULT_FILTERS)
    assert nf.normalize_filters(None) == list(nf.DEFAULT_FILTERS)


def test_unknown_filters_are_rejected_on_submission():
    with pytest.raises(ValueError):
        nf.validate_filters(["llm_proposed", "banana"])
    assert nf.validate_filters(["new_cluster"]) == ["llm_proposed"]


def test_confidence_floor_applies():
    topic = {"detection_type": "llm_proposed", "confidence_score": 0.5}
    assert nf.select_topics_for_notification([topic], ["llm_proposed"], 0.7) == []
    assert nf.select_topics_for_notification([topic], ["llm_proposed"], 0.4) == [topic]
