"""DatabaseQueryFacade against a real PostgreSQL, in a throwaway schema.

The facade is 5,000 statements of SQL that every reader and most writers go
through, and until 11 Oct 2026 the suite exercised 12% of it. The bugs that
hurt here are SQL bugs (a reader that forgets the readable-articles rule, a
JSON column written as text), so stubbing the connection would miss them.

Every test module gets its own schema named ``qf_<hex>``. The tables it needs
are cloned empty from ``public`` with ``LIKE ... INCLUDING ALL`` (indexes and
defaults copied, foreign keys not), a dedicated engine puts that schema first
on ``search_path``, and the schema is dropped at the end. Nothing in
``public`` is read or written: a facade method that reaches a table this
module did not clone fails loudly, because the clone is what the search path
finds first and ``public`` only backs it up for lookup tables.

Skips when the database is not reachable.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta

import pytest

TOPIC = "Topic A"                       # not a press-release topic
PR_TOPIC = "Market Monitoring SOC Automation"  # configured Market Monitoring topic: shows press releases
CONFIG_TOPIC = "AI and Machine Learning"  # exists in app/config/config.json (upsert_article checks)

TABLES = (
    "articles", "raw_articles",
    "auspex_chats", "auspex_messages", "auspex_prompts",
    "auspex_search_routing", "auspex_tool_usage", "auspex_research_sessions",
    "user_preferences", "desk_briefings", "organizational_profiles",
)


class _Db:
    """The slice of app.database.Database the facade touches."""
    db_type = "postgresql"

    def __init__(self, engine):
        self.engine = engine

    def _temp_get_connection(self, max_retries=3):
        return self.engine.connect()


@pytest.fixture(scope="module")
def sandbox():
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool
        from app.config.settings import db_settings
        if db_settings.DB_TYPE != "postgresql":
            pytest.skip("facade tests need PostgreSQL")
        url = db_settings.get_sync_database_url()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no database settings: {e}")

    schema = f"qf_{uuid.uuid4().hex[:8]}"
    try:
        admin = create_engine(url, poolclass=NullPool)
        with admin.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            for t in TABLES:
                conn.execute(text(f"CREATE TABLE {schema}.{t} (LIKE public.{t} INCLUDING ALL)"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no sandbox: {e}")

    engine = create_engine(url, poolclass=NullPool,
                           connect_args={"options": f"-c search_path={schema},public"})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.fixture
def facade(sandbox):
    from app.database_query_facade import DatabaseQueryFacade
    return DatabaseQueryFacade(_Db(sandbox), logging.getLogger("test_query_facade"))


def _exec(engine, sql, **params):
    from sqlalchemy import text
    with engine.begin() as conn:
        return conn.execute(text(sql), params)


def _rows(engine, sql, **params):
    from sqlalchemy import text
    with engine.begin() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings()]


# ── Readable-articles rule, as every reader applies it ───────────────────────

_YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

# uri -> (overrides, readable?)  One row per branch of the rule in
# app/services/article_visibility.py, all in TOPIC unless said otherwise.
MATRIX = {
    "r-approved":        (dict(ingest_status="approved", topic_alignment_score=0.9), True),
    "r-unscored":        (dict(ingest_status=None, topic_alignment_score=None), True),
    "x-low-score":       (dict(ingest_status="filtered_relevance", topic_alignment_score=0.1), False),
    "x-failed":          (dict(ingest_status="relevance_check_failed", topic_alignment_score=None), False),
    "x-decided-no":      (dict(ingest_status="approved", topic_alignment_score=0.95,
                               relevance_accepted_applied=False), False),
    "r-decided-yes":     (dict(ingest_status="approved", topic_alignment_score=0.1,
                               relevance_accepted_applied=True), True),
    "x-under-threshold": (dict(ingest_status="approved", topic_alignment_score=0.5,
                               relevance_threshold_applied=0.6), False),
    "r-over-floor":      (dict(ingest_status="approved", topic_alignment_score=0.5,
                               relevance_threshold_applied=None), True),
    "x-press-release":   (dict(ingest_status="approved", topic_alignment_score=0.9,
                               source_type="press_release"), False),
    "x-copy-of-readable": (dict(ingest_status="approved", topic_alignment_score=0.9,
                                duplicate_of="r-approved"), False),
    "r-copy-of-reject":  (dict(ingest_status="approved", topic_alignment_score=0.9,
                               duplicate_of="x-low-score"), True),
}
READABLE = {u for u, (_, ok) in MATRIX.items() if ok}


def _article(uri, **over):
    row = dict(
        uri=uri, title=f"Title {uri}", summary=f"Summary for {uri}", topic=TOPIC,
        category="Policy", sentiment="Neutral", future_signal="Weak Signal",
        time_to_impact="Short-Term", news_source="example.org", bias="center",
        publication_date=_YESTERDAY, submission_date=_YESTERDAY, analyzed=True,
        tags="a,b", ingest_status=None, topic_alignment_score=None,
        relevance_threshold_applied=None, relevance_accepted_applied=None,
        source_type="news", duplicate_of=None,
    )
    row.update(over)
    return row


_INSERT = """INSERT INTO articles (uri, title, summary, topic, category, sentiment, future_signal,
    time_to_impact, news_source, bias, publication_date, submission_date, analyzed, tags,
    ingest_status, topic_alignment_score, relevance_threshold_applied, relevance_accepted_applied,
    source_type, duplicate_of)
VALUES (:uri, :title, :summary, :topic, :category, :sentiment, :future_signal, :time_to_impact,
    :news_source, :bias, :publication_date, :submission_date, :analyzed, :tags, :ingest_status,
    :topic_alignment_score, :relevance_threshold_applied, :relevance_accepted_applied,
    :source_type, :duplicate_of)
ON CONFLICT (uri) DO NOTHING"""


@pytest.fixture(scope="module")
def visibility_rows(sandbox):
    for uri, (over, _) in MATRIX.items():
        _exec(sandbox, _INSERT, **_article(uri, **over))
    # A press release in a topic that shows them, and one in the plain topic
    # whose readability the matrix already covers.
    _exec(sandbox, _INSERT, **_article("pr-in-market-topic", topic=PR_TOPIC,
                                       ingest_status="approved", topic_alignment_score=0.9,
                                       source_type="press_release"))
    return READABLE


def _uris(rows):
    return {r["uri"] for r in rows}


def test_search_articles_applies_the_readable_rule(facade, visibility_rows):
    rows, total = facade.search_articles(topic=TOPIC, per_page=50)
    assert _uris(rows) == visibility_rows
    assert total == len(visibility_rows)


def test_search_articles_can_be_told_to_show_the_rejects(facade, visibility_rows):
    rows, total = facade.search_articles(topic=TOPIC, per_page=50, readable_only=False)
    assert _uris(rows) == set(MATRIX)
    assert total == len(MATRIX)


def test_search_articles_keyword_filter_searches_title_and_summary(facade, visibility_rows):
    rows, total = facade.search_articles(topic=TOPIC, keyword="r-decided-yes", per_page=50)
    assert _uris(rows) == {"r-decided-yes"} and total == 1


def test_search_articles_normalises_blank_category_and_sentiment(facade, visibility_rows):
    _exec(facade.db.engine, _INSERT, **_article("r-blank", category="", sentiment=None,
                                                ingest_status="approved", topic_alignment_score=0.9))
    rows, _ = facade.search_articles(topic=TOPIC, keyword="r-blank", per_page=5)
    assert rows[0]["category"] == "Uncategorized" and rows[0]["sentiment"] == "Unknown"
    _exec(facade.db.engine, "DELETE FROM articles WHERE uri = 'r-blank'")


def test_search_articles_paginates(facade, visibility_rows):
    page1, total = facade.search_articles(topic=TOPIC, page=1, per_page=2)
    page2, _ = facade.search_articles(topic=TOPIC, page=2, per_page=2)
    assert len(page1) == 2 and len(page2) == 2
    assert not (_uris(page1) & _uris(page2))
    assert total == len(visibility_rows)


def test_recent_articles_by_topic_applies_the_readable_rule(facade, visibility_rows):
    rows = facade.get_recent_articles_by_topic(TOPIC, limit=50)
    assert _uris(rows) == visibility_rows
    # tags come back as a list, blanks normalised
    assert all(isinstance(r["tags"], list) for r in rows)


def test_recent_articles_cross_topic_includes_the_market_press_release(facade, visibility_rows):
    rows = facade.get_recent_articles_by_topic(None, limit=50)
    assert "pr-in-market-topic" in _uris(rows)
    assert "x-press-release" not in _uris(rows)


def test_recent_articles_date_window_is_honoured(facade, visibility_rows):
    far = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    rows = facade.get_recent_articles_by_topic(TOPIC, limit=50, start_date=far,
                                               end_date=(datetime.now() - timedelta(days=300)).strftime("%Y-%m-%d"))
    assert rows == []


def test_articles_by_topic_applies_the_readable_rule(facade, visibility_rows):
    rows = facade.get_articles_by_topic(TOPIC, limit=50)
    assert _uris(rows) == visibility_rows
    assert "raw_markdown" in dict(rows[0])


def test_bias_reader_applies_the_readable_rule(facade, visibility_rows):
    rows = facade.get_articles_with_bias_data(TOPIC, limit=50, days_back=30)
    assert _uris(rows) == visibility_rows


def test_future_signal_reader_applies_the_readable_rule(facade, visibility_rows):
    rows = facade.get_articles_with_future_signals(TOPIC, limit=50, days_back=30)
    assert _uris(rows) == visibility_rows


@pytest.mark.parametrize("mode", ["deterministic", "balanced"])
def test_report_corpus_reader_applies_the_readable_rule(facade, visibility_rows, mode):
    rows = facade.get_articles_with_dynamic_limit(
        mode, TOPIC, datetime.now() - timedelta(days=7), datetime.now(), optimal_sample_size=50)
    assert _uris(rows) == visibility_rows


def test_news_feed_readers_agree_with_each_other_and_the_rule(facade, visibility_rows):
    rows = facade.get_news_feed_articles_for_date_range("all", [], 100, topic=TOPIC, limit=100)
    count = facade.get_news_feed_articles_count_for_date_range("all", [], topic=TOPIC)
    chrono = facade.get_news_feed_articles_chronological(None, None, topic=TOPIC, limit=100)
    chrono_count = facade.get_news_feed_articles_chronological_count(None, None, topic=TOPIC)
    assert _uris(rows) == visibility_rows
    assert count == len(visibility_rows)
    assert _uris(chrono) == visibility_rows
    assert chrono_count == len(visibility_rows)


def test_topic_counts_count_every_row_not_only_the_readable_ones(facade, visibility_rows):
    counts = facade.get_topics_with_article_counts()
    assert counts[TOPIC]["article_count"] == len(MATRIX)
    assert counts[PR_TOPIC]["article_count"] == 1


# ── upsert_article ───────────────────────────────────────────────────────────

def test_upsert_inserts_then_updates_without_emptying_other_columns(facade):
    uri = "https://example.org/news/upsert-1"
    out = facade.upsert_article({"uri": uri, "title": "First", "summary": "S1", "topic": CONFIG_TOPIC,
                                 "news_source": "example.org", "tags": ["x", "y"],
                                 "publication_date": _YESTERDAY, "sentiment": "Positive"})
    assert out == {"success": True, "uri": uri}
    row = _rows(facade.db.engine, "SELECT * FROM articles WHERE uri = :u", u=uri)[0]
    assert row["tags"] == "x,y" and row["sentiment"] == "Positive"
    assert row["url_key"] and row["source_type"] == "news"

    facade.upsert_article({"uri": uri, "title": "Second", "topic": CONFIG_TOPIC})
    row = _rows(facade.db.engine, "SELECT * FROM articles WHERE uri = :u", u=uri)[0]
    assert row["title"] == "Second"
    assert row["summary"] == "S1" and row["sentiment"] == "Positive"
    assert _rows(facade.db.engine, "SELECT count(*) AS n FROM articles WHERE uri = :u", u=uri)[0]["n"] == 1


def test_upsert_refuses_a_topic_that_is_not_configured(facade):
    with pytest.raises(ValueError):
        facade.upsert_article({"uri": "https://example.org/x", "title": "T", "topic": "No Such Topic"})


def test_upsert_requires_a_uri(facade):
    with pytest.raises(ValueError):
        facade.upsert_article({"title": "T", "topic": CONFIG_TOPIC})


def test_upsert_ignores_columns_that_are_not_article_fields(facade):
    uri = "https://example.org/news/upsert-2"
    facade.upsert_article({"uri": uri, "title": "T", "topic": CONFIG_TOPIC, "not_a_column": 1})
    assert _rows(facade.db.engine, "SELECT title FROM articles WHERE uri = :u", u=uri)[0]["title"] == "T"


# ── Auspex chats, messages, prompts ──────────────────────────────────────────

def test_chat_round_trip(facade):
    chat_id = facade.create_auspex_chat(TOPIC, title="A chat", user_id=None, profile_id=None,
                                        metadata={"created_at": "now", "profile_id": None})
    chat = facade.get_auspex_chat(chat_id)
    assert chat["topic"] == TOPIC and chat["title"] == "A chat"
    assert chat["metadata"] == {"created_at": "now", "profile_id": None}

    facade.add_auspex_message(chat_id, "system", "sys", metadata={"prompt_name": "default"})
    facade.add_auspex_message(chat_id, "user", "hello")
    facade.add_auspex_message(chat_id, "assistant", "hi", model_used="m", tokens_used=12,
                              metadata={"used_tools": False})
    msgs = facade.get_auspex_messages(chat_id)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
    assert msgs[0]["metadata"] == {"prompt_name": "default"}
    assert msgs[1]["metadata"] is None
    assert msgs[2]["model_used"] == "m" and msgs[2]["tokens_used"] == 12

    chats = facade.get_auspex_chats(topic=TOPIC)
    mine = [c for c in chats if c["id"] == chat_id][0]
    assert mine["message_count"] == 3
    assert facade.get_auspex_chats(topic="Other") == []

    assert facade.update_auspex_chat_metadata(chat_id, {"last_compaction": {"n": 1}})
    assert facade.get_auspex_chat(chat_id)["metadata"] == {
        "created_at": "now", "profile_id": None, "last_compaction": {"n": 1}}

    assert facade.update_auspex_chat_profile(chat_id, 7)
    assert facade.get_auspex_chat(chat_id)["profile_id"] == 7

    assert facade.delete_auspex_chat(chat_id)
    assert facade.get_auspex_chat(chat_id) is None


def test_missing_chat_reads_as_none_and_empty(facade):
    assert facade.get_auspex_chat(987654321) is None
    assert facade.get_auspex_messages(987654321) == []


def test_prompt_round_trip(facade):
    name = f"p-{uuid.uuid4().hex[:6]}"
    pid = facade.create_auspex_prompt(name, "Title", "Content", description="d", user_created="oliver")
    assert isinstance(pid, int)
    p = facade.get_auspex_prompt(name)
    assert (p["title"], p["content"], p["description"], p["user_created"]) == ("Title", "Content", "d", "oliver")
    assert p["is_default"] is False

    assert facade.update_auspex_prompt(name, content="New")
    p = facade.get_auspex_prompt(name)
    assert p["content"] == "New" and p["title"] == "Title"

    assert name in {x["name"] for x in facade.get_all_auspex_prompts()}
    assert facade.delete_auspex_prompt(name)
    assert facade.get_auspex_prompt(name) is None


def test_duplicate_prompt_name_is_refused(facade):
    name = f"p-{uuid.uuid4().hex[:6]}"
    facade.create_auspex_prompt(name, "T", "C")
    with pytest.raises(Exception):
        facade.create_auspex_prompt(name, "T2", "C2")
    assert facade.get_auspex_prompt(name)["title"] == "T"


# ── User preferences ─────────────────────────────────────────────────────────

def test_user_preference_set_get_overwrite(facade):
    assert facade.get_user_preference("u1", "k") is None
    assert facade.set_user_preference("u1", "k", {"a": 1})
    assert facade.get_user_preference("u1", "k") == {"a": 1}
    assert facade.set_user_preference("u1", "k", {"a": 2, "b": [1]})
    assert facade.get_user_preference("u1", "k") == {"a": 2, "b": [1]}
    assert facade.get_user_preference("u2", "k") is None


# ── Desk briefings ───────────────────────────────────────────────────────────

def test_desk_briefing_lifecycle(facade):
    bid = facade.create_desk_briefing("Morning", "oliver", description="d", topic=TOPIC)
    b = facade.get_desk_briefing_by_id(bid, "oliver")
    assert b["name"] == "Morning" and b["status"] == "draft"
    assert b["articles"] == [] and b["articles_count"] == 0
    assert facade.get_desk_briefing_by_id(bid, "someone-else") is None

    assert facade.add_article_to_desk_briefing(bid, "oliver", {"uri": "u1", "title": "One"})
    assert facade.add_article_to_desk_briefing(bid, "oliver", {"uri": "u2", "title": "Two"})
    assert facade.add_article_to_desk_briefing(bid, "oliver", {"uri": "u1", "title": "One again"})
    b = facade.get_desk_briefing_by_id(bid, "oliver")
    assert [a["uri"] for a in b["articles"]] == ["u1", "u2"] and b["articles_count"] == 2

    assert facade.remove_article_from_desk_briefing(bid, "oliver", "u1")
    assert not facade.remove_article_from_desk_briefing(bid, "oliver", "u1")
    assert facade.get_desk_briefing_by_id(bid, "oliver")["articles_count"] == 1

    assert facade.add_incident_to_desk_briefing(bid, "oliver", {"name": "Outage"})
    assert facade.add_incident_to_desk_briefing(bid, "oliver", {"name": "Outage"})
    assert facade.add_emerging_topic_to_desk_briefing(bid, "oliver", {"name": "Topic X"})
    b = facade.get_desk_briefing_by_id(bid, "oliver")
    assert b["incidents_count"] == 1 and b["emerging_topics_count"] == 1

    assert facade.remove_incident_from_desk_briefing(bid, "oliver", "Outage")
    assert facade.remove_emerging_topic_from_desk_briefing(bid, "oliver", "Topic X")
    b = facade.get_desk_briefing_by_id(bid, "oliver")
    assert b["incidents_count"] == 0 and b["emerging_topics_count"] == 0

    assert facade.update_desk_briefing(bid, "oliver", name="Evening")
    assert not facade.update_desk_briefing(bid, "someone-else", name="Hijack")
    assert facade.get_desk_briefing_by_id(bid, "oliver")["name"] == "Evening"

    assert bid in {x["id"] for x in facade.get_desk_briefings_for_user("oliver")}
    assert facade.delete_desk_briefing(bid, "oliver")
    assert facade.get_desk_briefing_by_id(bid, "oliver") is None


def test_finalized_briefing_refuses_changes(facade):
    bid = facade.create_desk_briefing("Final", "oliver")
    _exec(facade.db.engine, "UPDATE desk_briefings SET status = 'finalized' WHERE id = :i", i=bid)
    assert not facade.add_article_to_desk_briefing(bid, "oliver", {"uri": "u"})
    assert not facade.add_incident_to_desk_briefing(bid, "oliver", {"name": "n"})
    assert not facade.remove_article_from_desk_briefing(bid, "oliver", "u")


# ── Research sessions, tool usage, routing log ───────────────────────────────

def test_research_session_round_trip(facade):
    assert facade.create_research_session({"username": "u", "query": "q"}) is None  # topic missing
    sid = facade.create_research_session({"username": "u", "query": "q", "topic": TOPIC})
    s = facade.get_research_session(sid)
    assert s["status"] == "pending" and s["username"] == "u" and s["topic"] == TOPIC

    assert facade.update_research_session(sid, {"status": "done", "report": "text", "ignored": "x"})
    s = facade.get_research_session(sid)
    assert s["status"] == "done" and s["report"] == "text"
    assert not facade.update_research_session(sid, {"ignored": "x"})
    assert facade.get_research_session(999999999) is None
    assert sid in {x["id"] for x in facade.get_research_sessions_by_user("u")}


def test_tool_usage_and_routing_logs(facade):
    assert facade.log_tool_usage({}) is None
    tid = facade.log_tool_usage({"tool_name": "trend", "chat_id": None, "execution_ms": 12})
    assert isinstance(tid, int)
    row = _rows(facade.db.engine, "SELECT * FROM auspex_tool_usage WHERE id = :i", i=tid)[0]
    assert row["tool_name"] == "trend" and row["execution_ms"] == 12

    assert facade.log_search_routing({"query": "q"}) is None
    rid = facade.log_search_routing({"query": "q", "recommended_source": "vector",
                                     "actual_source": "sql", "confidence": 0.7})
    row = _rows(facade.db.engine, "SELECT * FROM auspex_search_routing WHERE id = :i", i=rid)[0]
    assert row["recommended_source"] == "vector" and row["confidence"] == 0.7


def test_json_columns_round_trip_as_objects(facade):
    sid = facade.create_research_session({"username": "u", "query": "q", "topic": TOPIC,
                                          "objectives": {"o": 1}, "metadata": {"m": 2}})
    facade.update_research_session(sid, {"findings": {"f": [1, 2]}})
    s = facade.get_research_session(sid)
    assert s["objectives"] == {"o": 1} and s["metadata"] == {"m": 2} and s["findings"] == {"f": [1, 2]}

    tid = facade.log_tool_usage({"tool_name": "trend", "parameters": {"p": 1}, "result_summary": {"n": 3}})
    row = _rows(facade.db.engine, "SELECT * FROM auspex_tool_usage WHERE id = :i", i=tid)[0]
    assert row["parameters"] == {"p": 1} and row["result_summary"] == {"n": 3}

    rid = facade.log_search_routing({"query": "q", "recommended_source": "v", "actual_source": "s",
                                     "signals": {"temporal": True}})
    row = _rows(facade.db.engine, "SELECT * FROM auspex_search_routing WHERE id = :i", i=rid)[0]
    assert row["signals"] == {"temporal": True}


# ── Organisational profiles ──────────────────────────────────────────────────

def test_default_profile_lookup(facade):
    assert facade.get_default_organisational_profile() is None
    _exec(facade.db.engine,
          "INSERT INTO organizational_profiles (name, industry, is_default, key_concerns) "
          "VALUES ('Acme', 'Widgets', true, :kc)", kc=json.dumps(["cost"]))
    p = facade.get_default_organisational_profile()
    assert p["name"] == "Acme" and json.loads(p["key_concerns"]) == ["cost"]
    assert facade.get_organisational_profile(p["id"])["industry"] == "Widgets"
    assert facade.get_organisational_profile(999999999) is None


# ── Pure helpers: dot-paths into the brief payload ───────────────────────────

def test_split_path_parses_keys_and_indexes():
    from app.database_query_facade import DatabaseQueryFacade as F
    assert F._split_path("") == []
    assert F._split_path("a") == [("key", "a")]
    assert F._split_path("themes[2].body") == [("key", "themes"), ("idx", 2), ("key", "body")]
    assert F._split_path("a.b[0][1].c") == [("key", "a"), ("key", "b"), ("idx", 0), ("idx", 1), ("key", "c")]
    with pytest.raises(ValueError):
        F._split_path("a[1")


def test_path_to_jsonb_array_and_walk():
    from app.database_query_facade import DatabaseQueryFacade as F
    assert F._path_to_jsonb_array("themes[2].body") == ["themes", "2", "body"]
    doc = {"themes": [{"body": "x"}, {"body": "y"}], "n": 1}
    assert F._walk_path(doc, "themes[1].body") == "y"
    assert F._walk_path(doc, "themes[5].body") is None
    assert F._walk_path(doc, "n.z") is None
    assert F._walk_path(doc, "") == doc


# ── The rollback helpers ─────────────────────────────────────────────────────

def test_helpers_return_values_and_raise_on_bad_sql(facade):
    from sqlalchemy import text
    assert facade._scalar_with_rollback(text("SELECT 41 + 1")) == 42
    assert facade._fetchone_with_rollback(text("SELECT 1 AS a, 2 AS b"), mappings=True)["b"] == 2
    assert [r[0] for r in facade._fetchall_with_rollback(text("SELECT generate_series(1, 3)"))] == [1, 2, 3]
    with pytest.raises(Exception):
        facade._execute_with_rollback(text("SELECT * FROM no_such_table_here"))
    # the connection that failed does not poison the next call
    assert facade._scalar_with_rollback(text("SELECT 1")) == 1
