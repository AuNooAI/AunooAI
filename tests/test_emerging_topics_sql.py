"""Emerging-topics behaviour that only a real database can demonstrate.

Scope isolation, the detect/miss counters, novelty de-duplication, bounded and
source-diverse sampling, date-window scoping, and the 1536d backup/restore round
trip all live in SQL. Asserting them against stubs would only prove the stubs
agree with themselves.

Everything runs inside a throwaway schema (``et_test_sandbox``) created on the
tenant's own database and dropped afterwards. The tenant's real tables are never
read or written: ``search_path`` points at the sandbox for the whole session.

Skips cleanly when there is no reachable PostgreSQL.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import text  # noqa: E402

SCHEMA = "et_test_sandbox"


def _engine():
    from app.config.settings import db_settings
    from sqlalchemy import create_engine

    return create_engine(db_settings.get_sync_database_url(), poolclass=None)


@pytest.fixture(scope="module")
def db():
    """A connection whose search_path is a private, disposable schema."""
    try:
        engine = _engine()
        conn = engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"No PostgreSQL available: {exc}")

    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.commit()
    except Exception as exc:  # pragma: no cover
        conn.close()
        pytest.skip(f"Cannot create a sandbox schema: {exc}")

    conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
    _create_tables(conn)
    conn.commit()

    yield conn

    try:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.commit()
    finally:
        conn.close()


SANDBOX_TABLES = (
    "articles",
    "article_novelty_scores",
    "emerging_topics",
    "detection_runs",
    "topic_history",
)


def _create_tables(conn):
    """Clone the tenant's real table shapes into the sandbox.

    ``LIKE ... INCLUDING ALL`` copies columns, types, defaults, and indexes but
    no data, so the tests exercise the same column set the production queries
    write to. Hand-written stand-ins drift from the real schema and turn a
    genuine SQL bug into a passing test.
    """
    for table in SANDBOX_TABLES:
        exists = conn.execute(
            text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}
        ).scalar()
        if not exists:
            pytest.skip(f"public.{table} is missing; cannot clone a sandbox")
        conn.execute(text(
            f"CREATE TABLE {SCHEMA}.{table} "
            f"(LIKE public.{table} INCLUDING ALL)"
        ))


@pytest.fixture(autouse=True)
def clean(db):
    db.rollback()
    db.execute(text(
        f"TRUNCATE {', '.join(SANDBOX_TABLES)} RESTART IDENTITY"
    ))
    db.commit()
    yield


def service_on(db):
    """An EmergingTopicsService whose connections point at the sandbox."""
    from app.services.emerging_topics.emerging_topics_service import (
        EmergingTopicsService, EmergingTopicsConfig,
    )

    class Passthrough:
        """Hands out the shared sandbox connection and ignores close()."""
        def __init__(self, conn):
            self._conn = conn

        def execute(self, *a, **kw):
            return self._conn.execute(*a, **kw)

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

        def close(self):
            pass

    service = EmergingTopicsService(config=EmergingTopicsConfig())
    service._get_connection = lambda: Passthrough(db)
    return service


def add_topic(db, label, topic_filter, **overrides):
    values = {
        "label": label,
        "filter": topic_filter,
        "status": overrides.get("status", "active"),
        "detection_date": overrides.get("detection_date", date.today()),
        "last": overrides.get("last_detection_date", date.today()),
        "consecutive": overrides.get("consecutive_detections", 1),
        "missed": overrides.get("missed_runs", 0),
    }
    return db.execute(text("""
        INSERT INTO emerging_topics
            (topic_label, topic_filter, detection_type, status, detection_date,
             first_detection_date, last_detection_date,
             detection_count, consecutive_detections, missed_runs)
        VALUES (:label, :filter, 'llm_proposed', :status, :detection_date,
                :detection_date, :last, 1, :consecutive, :missed)
        RETURNING id
    """), values).scalar()


def counters(db, topic_id):
    row = db.execute(text("""
        SELECT consecutive_detections, missed_runs, status
        FROM emerging_topics WHERE id = :id
    """), {"id": topic_id}).fetchone()
    return {"consecutive": row[0], "missed": row[1], "status": row[2]}


# ---------------------------------------------------------------------------
# Scope isolation
# ---------------------------------------------------------------------------

def test_same_label_in_two_scopes_stays_two_topics(db):
    from app.services.emerging_topics.emerging_topics_service import EmergingTopic

    service = service_on(db)
    topic = EmergingTopic(topic_label="AI Chip Export Controls",
                          detection_date=date.today())

    first = service._save_emerging_topic(db, topic, "semiconductors")
    second = service._save_emerging_topic(db, topic, "trade_policy")
    db.commit()

    assert first != second
    rows = db.execute(text(
        "SELECT topic_filter FROM emerging_topics ORDER BY topic_filter"
    )).fetchall()
    assert [r[0] for r in rows] == ["semiconductors", "trade_policy"]


def test_a_named_scope_never_matches_the_global_scope(db):
    from app.services.emerging_topics.emerging_topics_service import EmergingTopic

    service = service_on(db)
    topic = EmergingTopic(topic_label="Same Label", detection_date=date.today())

    global_id = service._save_emerging_topic(db, topic, None)
    scoped_id = service._save_emerging_topic(db, topic, "climate")
    # A second global save finds the first one rather than making a third.
    again = service._save_emerging_topic(db, topic, None)
    db.commit()

    assert global_id != scoped_id
    assert again == global_id
    assert db.execute(text("SELECT COUNT(*) FROM emerging_topics")).scalar() == 2


def test_missed_runs_only_touch_the_run_s_own_scope(db):
    service = service_on(db)
    climate = add_topic(db, "Climate topic", "climate")
    chips = add_topic(db, "Chip topic", "semiconductors")
    everything = add_topic(db, "Global topic", None)
    db.commit()

    service._apply_missed_runs(db, [], "climate")
    db.commit()

    assert counters(db, climate)["missed"] == 1
    assert counters(db, chips)["missed"] == 0
    assert counters(db, everything)["missed"] == 0


def test_detect_detect_miss_detect_counter_sequence(db):
    from app.services.emerging_topics.emerging_topics_service import EmergingTopic

    service = service_on(db)
    topic = EmergingTopic(topic_label="Recurring Theme", detection_date=date.today())

    topic_id = service._save_emerging_topic(db, topic, "climate")
    db.commit()
    assert counters(db, topic_id) == {"consecutive": 1, "missed": 0, "status": "active"}

    service._save_emerging_topic(db, topic, "climate")
    db.commit()
    assert counters(db, topic_id) == {"consecutive": 2, "missed": 0, "status": "active"}

    service._apply_missed_runs(db, [], "climate")
    db.commit()
    assert counters(db, topic_id) == {"consecutive": 0, "missed": 1, "status": "active"}

    service._save_emerging_topic(db, topic, "climate")
    db.commit()
    assert counters(db, topic_id) == {"consecutive": 1, "missed": 0, "status": "active"}


def test_a_detected_topic_is_not_counted_as_missed(db):
    service = service_on(db)
    seen = add_topic(db, "Seen", "climate")
    unseen = add_topic(db, "Unseen", "climate")
    db.commit()

    service._apply_missed_runs(db, [seen], "climate")
    db.commit()

    assert counters(db, seen)["missed"] == 0
    assert counters(db, unseen)["missed"] == 1


# ---------------------------------------------------------------------------
# Retirement
# ---------------------------------------------------------------------------

def test_retirement_is_scoped_and_counts_only_completed_runs(db):
    service = service_on(db)
    long_ago = date.today() - timedelta(days=30)

    stale_climate = add_topic(db, "Stale climate", "climate",
                              last_detection_date=long_ago)
    stale_chips = add_topic(db, "Stale chips", "semiconductors",
                            last_detection_date=long_ago)

    # Eight completed climate runs since, plus failed ones that must not count.
    for _ in range(8):
        db.execute(text("""
            INSERT INTO detection_runs (run_date, topic_filter, status)
            VALUES (NOW(), 'climate', 'completed')
        """))
    for _ in range(20):
        db.execute(text("""
            INSERT INTO detection_runs (run_date, topic_filter, status)
            VALUES (NOW(), 'semiconductors', 'failed')
        """))
    db.commit()

    retired = service._check_auto_retirement([], "climate")
    db.commit()

    assert retired == 1
    assert counters(db, stale_climate)["status"] == "retired"
    assert counters(db, stale_chips)["status"] == "active"


def test_failed_runs_alone_never_retire_a_topic(db):
    service = service_on(db)
    stale = add_topic(db, "Stale", "climate",
                      last_detection_date=date.today() - timedelta(days=30))
    for _ in range(20):
        db.execute(text("""
            INSERT INTO detection_runs (run_date, topic_filter, status)
            VALUES (NOW(), 'climate', 'failed')
        """))
    db.commit()

    assert service._check_auto_retirement([], "climate") == 0
    assert counters(db, stale)["status"] == "active"


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def _add_novelty(db, uri, calc_date, score):
    """One novelty row. The real table requires every component score."""
    db.execute(text("""
        INSERT INTO article_novelty_scores
            (article_uri, calculation_date, knn_distance_score, density_score,
             centroid_distance_score, composite_novelty_score)
        VALUES (:uri, :calc_date, :score, :score, :score, :score)
    """), {"uri": uri, "calc_date": calc_date, "score": score})


def seed_articles(db, spec, days_ago=1):
    """spec: {source: count}. Novelty descends with insertion order."""
    stamp = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    n = 0
    for source, count in spec.items():
        for i in range(count):
            uri = f"{source}-{i}"
            db.execute(text("""
                INSERT INTO articles (uri, title, summary, news_source,
                                      publication_date, topic)
                VALUES (:uri, :title, :summary, :source, :pub, 'climate')
            """), {
                "uri": uri, "title": f"{source} story {i}",
                "summary": "x" * 80, "source": source, "pub": stamp,
            })
            _add_novelty(db, uri, date.today(), 100 - n)
            n += 1
    db.commit()


def proposer_on(db):
    from app.services.emerging_topics.theme_proposer import ThemeProposer

    class Passthrough:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, *a, **kw):
            return self._conn.execute(*a, **kw)

        def close(self):
            pass

    proposer = ThemeProposer()
    proposer._get_connection = lambda: Passthrough(db)
    return proposer


def test_sample_is_bounded_and_source_diverse(db):
    # One wire dominates by volume and by novelty.
    seed_articles(db, {"wire": 200, "trade": 10, "local": 5})
    proposer = proposer_on(db)

    sample = proposer._fetch_sample_articles(
        topic_filter="climate", days_back=7, max_articles=20
    )

    assert len(sample) == 20
    sources = {row["news_source"] for row in sample}
    assert sources == {"wire", "trade", "local"}, (
        "every available source must be represented before one repeats"
    )
    counts = {s: sum(1 for r in sample if r["news_source"] == s) for s in sources}
    assert counts["wire"] < 20, "one source must not consume the whole sample"


def test_sample_is_deterministic(db):
    seed_articles(db, {"wire": 30, "trade": 30})
    proposer = proposer_on(db)

    first = proposer._fetch_sample_articles("climate", 7, 15)
    second = proposer._fetch_sample_articles("climate", 7, 15)

    assert [r["uri"] for r in first] == [r["uri"] for r in second]


def test_sample_applies_the_topic_filter_and_date_window(db):
    seed_articles(db, {"wire": 5}, days_ago=1)
    db.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, publication_date, topic)
        VALUES ('old', 't', :s, 'wire', :pub, 'climate'),
               ('other-topic', 't', :s, 'wire', :recent, 'markets')
    """), {
        "s": "y" * 80,
        "pub": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
        "recent": datetime.now(timezone.utc).isoformat(),
    })
    db.commit()

    uris = {r["uri"] for r in proposer_on(db)._fetch_sample_articles("climate", 7, 50)}

    assert "old" not in uris, "outside the date window"
    assert "other-topic" not in uris, "outside the topic filter"
    assert len(uris) == 5


def test_malformed_publication_dates_do_not_break_the_sample(db):
    seed_articles(db, {"wire": 3})
    db.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, publication_date, topic)
        VALUES ('bad-1', 't', :s, 'wire', 'not a date', 'climate'),
               ('bad-2', 't', :s, 'wire', '', 'climate'),
               ('bad-3', 't', :s, 'wire', NULL, 'climate'),
               ('bad-4', 't', :s, 'wire', '2026-13-45', 'climate')
    """), {"s": "z" * 80})
    db.commit()

    # A blind ::timestamp cast would abort the whole statement here.
    sample = proposer_on(db)._fetch_sample_articles("climate", 7, 50)

    assert {r["uri"] for r in sample} == {"wire-0", "wire-1", "wire-2"}


def test_multiple_novelty_rows_do_not_duplicate_an_article(db):
    seed_articles(db, {"wire": 2})
    for offset in (1, 2, 3):
        _add_novelty(db, "wire-0", date.today() - timedelta(days=offset), 10 * offset)
    db.commit()

    sample = proposer_on(db)._fetch_sample_articles("climate", 7, 50)

    uris = [r["uri"] for r in sample]
    assert uris.count("wire-0") == 1
    # The newest calculation wins.
    score = next(r["novelty_score"] for r in sample if r["uri"] == "wire-0")
    assert score == 100


def test_high_novelty_listing_returns_each_article_once(db):
    """A re-scored article used to fill the list with copies of itself."""
    from app.services.emerging_topics.novelty_scorer import NoveltyScorer

    seed_articles(db, {"wire": 3})
    for offset in (1, 2, 3, 4, 5):
        _add_novelty(db, "wire-0", date.today() - timedelta(days=offset), 95)
    db.commit()

    class Passthrough:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, *a, **kw):
            return self._conn.execute(*a, **kw)

        def close(self):
            pass

    scorer = NoveltyScorer()
    scorer._get_connection = lambda: Passthrough(db)

    articles = scorer.get_high_novelty_articles(
        threshold=0, days_back=30, topic_filter="climate", limit=50
    )

    uris = [a["article_uri"] for a in articles]
    assert len(uris) == len(set(uris)), f"duplicated articles: {uris}"
    assert set(uris) == {"wire-0", "wire-1", "wire-2"}
    # The newest scoring run wins the tie.
    wire_0 = next(a for a in articles if a["article_uri"] == "wire-0")
    assert wire_0["calculation_date"] == date.today()


def test_trend_scorer_counts_an_article_once_despite_novelty_history(db):
    from app.services.emerging_topics.trend_scorer import TrendScorer

    seed_articles(db, {"wire": 1, "trade": 1})
    for offset in (1, 2, 3, 4):
        _add_novelty(db, "wire-0", date.today() - timedelta(days=offset), 50)
    db.commit()

    class Passthrough:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, *a, **kw):
            return self._conn.execute(*a, **kw)

        def close(self):
            pass

    scorer = TrendScorer()
    scorer._get_connection = lambda: Passthrough(db)

    result = scorer.calculate(["wire-0", "trade-0"], days_back=7)

    assert result.article_count == 2, "five novelty rows must not become five articles"
    assert result.source_count == 2


# ---------------------------------------------------------------------------
# Historical coverage
# ---------------------------------------------------------------------------

def _vector(seed, dim=768):
    """A unit-ish vector that is close to itself and far from other seeds."""
    values = [0.0] * dim
    values[seed % dim] = 1.0
    return "[" + ",".join(str(v) for v in values) + "]"


# ---------------------------------------------------------------------------
# Historical coverage: gated off, and honest about it
# ---------------------------------------------------------------------------

def test_historical_coverage_is_unknown_without_an_e5_index(db, monkeypatch):
    """The sandbox has no article_embeddings_ml, which is the normal case.

    The DeBERTa rule this replaced answered "ongoing" for everything, including
    invented themes. Absent a calibrated index the only truthful answer is that
    we do not know.
    """
    from app.services.emerging_topics import historical_backend as hb
    from app.services.emerging_topics.theme_proposer import ProposedTheme
    import asyncio

    monkeypatch.setenv("EMERGING_TOPICS_HISTORICAL_MODE", "shadow")
    hb.reset_probe_cache()
    service = service_on(db)

    theme = ProposedTheme("T", "d", "q", [], "")
    theme.article_uris = ["a", "b", "c"]

    status, shadow = asyncio.run(service._check_historical_coverage(
        theme=theme, days_back=7, topic_filter="climate",
    ))

    assert status == hb.UNKNOWN
    assert shadow is None
    hb.reset_probe_cache()


def test_the_status_round_trips_through_the_database(db):
    """It has to be queryable, or "observable" is just a word."""
    from app.services.emerging_topics.emerging_topics_service import EmergingTopic

    service = service_on(db)
    topic = EmergingTopic(
        topic_label="Gated Theme",
        detection_date=date.today(),
        historical_coverage_status="unknown",
        historical_shadow={"backend": "e5", "would_be": "ongoing"},
    )

    topic_id = service._save_emerging_topic(db, topic, "climate")
    db.commit()

    row = db.execute(text("""
        SELECT historical_coverage_status, historical_shadow, detection_type
        FROM emerging_topics WHERE id = :id
    """), {"id": topic_id}).fetchone()

    assert row[0] == "unknown"
    assert row[1]["would_be"] == "ongoing", "the shadow verdict must be queryable"
    assert row[2] == "llm_proposed", "unknown must not mark a topic ongoing"
