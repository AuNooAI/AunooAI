"""brand_decision_store: stored-state rules (pure) and the save SQL against a
real PostgreSQL in a throwaway schema (tables cloned empty with LIKE ...
INCLUDING ALL, foreign keys not copied). Skips when the database is not
reachable or the schema cannot be made."""

import asyncio
import json
import os
import uuid

import pytest

from app.services import brand_decision as bd
from app.services import brand_decision_store as st

TOPIC = "Brand Monitoring Colgate-Palmolive"


# ── Stored-state rules ──────────────────────────────────────────────────────

def _r(**kw):
    base = {"brand_relation": None, "relevance_status": None, "source_relation": None,
            "judge_version": None, "evidence": None, "article_status": None, "article_topic": TOPIC}
    base.update(kw)
    return base


@pytest.mark.parametrize("rows,state", [
    ([], "no_row"),
    ([_r()], "undecided"),
    ([_r(relevance_status="relevance_check_failed")], "undecided"),
    ([_r(relevance_status="deferred")], "undecided"),
    ([_r(relevance_status="approved")], "legacy"),
    ([_r(relevance_status="filtered_relevance")], "legacy"),
    ([_r(article_status="approved")], "legacy"),                      # site without per-group verdicts
    ([_r(article_status="approved", article_topic="Other topic")], "undecided"),
    ([_r(brand_relation="notable", relevance_status="approved", article_status="approved")], "label_done"),
    ([_r(brand_relation="other", relevance_status="filtered_relevance", article_status="filtered_relevance")], "label_done"),
    ([_r(brand_relation="notable", relevance_status="quality_failed")], "label_done"),
    ([_r(brand_relation="notable", relevance_status="enrichment_failed", article_status="enrichment_failed")], "label_retry"),
    ([_r(brand_relation="great", relevance_status="approved")], "invalid"),
    ([_r(relevance_status="approved"), _r(brand_relation="subject", relevance_status="approved", article_status="approved")], "label_done"),
])
def test_classify_stored(rows, state):
    assert st.classify_stored(rows, TOPIC)[0] == state


def test_invalid_label_is_never_read_as_a_score():
    assert st.decision_from_row({"brand_relation": "0.9"}) is None


# ── SQL against PostgreSQL ──────────────────────────────────────────────────

class _Adb:
    """The slice of AsyncDatabase the store uses, on one asyncpg connection
    whose search_path starts at the sandbox schema."""
    db_type = "postgresql"

    def __init__(self, conn):
        self.conn = conn

    def _convert_query_params(self, query, params):
        for i in range(1, query.count("?") + 1):
            query = query.replace("?", f"${i}", 1)
        return query, params

    class _Ctx:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn

        async def __aexit__(self, *a):
            return False

    def get_connection(self):
        return self._Ctx(self.conn)

    async def fetch_all(self, q, params=()):
        q, p = self._convert_query_params(q, params)
        return [dict(r) for r in await self.conn.fetch(q, *p)]

    async def execute_single_update(self, q, params=()):
        q, p = self._convert_query_params(q, params)
        return int((await self.conn.execute(q, *p)).split()[-1])


@pytest.fixture
def sandbox():
    try:
        import asyncpg
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    except ImportError:
        pytest.skip("asyncpg or dotenv missing")
    schema = f"brtest_{uuid.uuid4().hex[:8]}"
    loop = asyncio.new_event_loop()

    async def setup():
        conn = await asyncpg.connect(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "5432")),
                                     user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
                                     database=os.getenv("DB_NAME"),
                                     server_settings={"search_path": f"{schema},public"})
        await conn.execute(f"CREATE SCHEMA {schema}")
        for t in ("articles", "keyword_groups", "keyword_article_matches"):
            await conn.execute(f"CREATE TABLE {schema}.{t} (LIKE public.{t} INCLUDING ALL)")
        return conn
    try:
        conn = loop.run_until_complete(setup())
    except Exception as e:  # noqa: BLE001
        loop.close()
        pytest.skip(f"no sandbox: {e}")
    yield loop, _Adb(conn), conn
    loop.run_until_complete(conn.execute(f"DROP SCHEMA {schema} CASCADE"))
    loop.run_until_complete(conn.close())
    loop.close()


def _seed(loop, conn, uri, topic=TOPIC, article_status=None, article_topic=TOPIC, match_status=None, label=None):
    async def go():
        gid = await conn.fetchval(
            "INSERT INTO keyword_groups (name, topic, source, is_active) VALUES ($1, $2, 'news', true) RETURNING id",
            f"g-{uuid.uuid4().hex[:6]}", topic)
        await conn.execute("INSERT INTO articles (uri, title, topic, ingest_status) VALUES ($1, 'T', $2, $3)",
                           uri, article_topic, article_status)
        await conn.execute("INSERT INTO keyword_article_matches (article_uri, keyword_ids, group_id, relevance_status, brand_relation) "
                           "VALUES ($1, '1', $2, $3, $4)", uri, gid, match_status, label)
        return gid
    return loop.run_until_complete(go())


def _dec(label="notable", src="independent", outcome="decided", failure=None):
    return bd.Decision(outcome, label if outcome == "decided" else None, src, "model", "CFO quoted",
                       {"alias": "Colgate", "field": "title", "quality": "summary"}, route="llm:fake",
                       resolved_model="fake-1", judge_version="bk1:abc", failure=failure)


def _row(loop, conn, uri):
    return loop.run_until_complete(conn.fetchrow(
        "SELECT m.brand_relation, m.source_relation, m.relevance_status, m.topic_alignment_score, "
        "m.decision_evidence, m.last_failure, m.judge_version, a.ingest_status, a.topic_alignment_score AS a_score "
        "FROM keyword_article_matches m JOIN articles a ON a.uri = m.article_uri WHERE m.article_uri = $1", uri))


def test_rejection_saves_article_and_match_together(sandbox):
    loop, adb, conn = sandbox
    _seed(loop, conn, "u1")
    d = _dec("passing")
    assert loop.run_until_complete(st.save_rejection(adb, {"uri": "u1", "title": "T"}, TOPIC, d)) == "saved"
    r = _row(loop, conn, "u1")
    assert (r["brand_relation"], r["relevance_status"], r["ingest_status"]) == ("passing", "filtered_relevance", "filtered_relevance")
    assert r["topic_alignment_score"] == 0.2
    ev = json.loads(r["decision_evidence"])
    assert ev["provenance"] == "model" and ev["alias"] == "Colgate" and ev["rubric"] == bd.RUBRIC_VERSION


def test_unavailable_records_failure_and_no_verdict(sandbox):
    loop, adb, conn = sandbox
    _seed(loop, conn, "u2")
    d = _dec(outcome="unavailable", failure="llm:fake: timeout")
    loop.run_until_complete(st.save_rejection(adb, {"uri": "u2", "title": "T"}, TOPIC, d))
    r = _row(loop, conn, "u2")
    assert r["brand_relation"] is None and r["relevance_status"] == "relevance_check_failed"
    assert r["ingest_status"] == "relevance_check_failed" and "timeout" in json.loads(r["last_failure"])["reason"]


def test_failed_repeat_keeps_the_previous_valid_verdict(sandbox):
    loop, adb, conn = sandbox
    _seed(loop, conn, "u3", article_status="approved", match_status="approved", label="subject")
    d = _dec(outcome="unavailable", failure="jev: 529")
    loop.run_until_complete(st.save_rejection(adb, {"uri": "u3", "title": "T"}, TOPIC, d))
    r = _row(loop, conn, "u3")
    assert (r["brand_relation"], r["relevance_status"]) == ("subject", "approved")
    assert json.loads(r["last_failure"])["reason"] == "jev: 529"


def test_existing_label_is_not_overwritten_and_rollback_is_whole(sandbox):
    loop, adb, conn = sandbox
    _seed(loop, conn, "u4", article_status="approved", match_status="approved", label="subject")
    out = loop.run_until_complete(st.save_rejection(adb, {"uri": "u4", "title": "T"}, TOPIC, _dec("other")))
    assert out == "concurrent"
    r = _row(loop, conn, "u4")
    assert (r["brand_relation"], r["ingest_status"]) == ("subject", "approved")  # article write rolled back too


def test_missing_match_row_is_a_failed_save(sandbox):
    loop, adb, conn = sandbox
    loop.run_until_complete(conn.execute("INSERT INTO articles (uri, title, topic) VALUES ('u5', 'T', $1)", TOPIC))
    with pytest.raises(st.SaveFailed):
        loop.run_until_complete(st.save_rejection(adb, {"uri": "u5", "title": "T"}, TOPIC, _dec("other")))
    assert loop.run_until_complete(conn.fetchval("SELECT ingest_status FROM articles WHERE uri='u5'")) is None


def test_admitted_save_needs_both_rows(sandbox):
    loop, adb, conn = sandbox
    _seed(loop, conn, "u6")
    q = ("UPDATE articles SET ingest_status = ?, analyzed = true WHERE uri = ?", ("approved", "u6"))
    assert loop.run_until_complete(st.save_admitted(adb, q, "u6", TOPIC, _dec("subject"))) == "saved"
    r = _row(loop, conn, "u6")
    assert (r["brand_relation"], r["relevance_status"], r["ingest_status"]) == ("subject", "approved", "approved")
    gone = ("UPDATE articles SET ingest_status = ? WHERE uri = ?", ("approved", "nope"))
    _seed(loop, conn, "u7")
    with pytest.raises(st.SaveFailed):
        loop.run_until_complete(st.save_admitted(adb, gone, "u7", TOPIC, _dec("subject")))
    assert _row(loop, conn, "u7")["brand_relation"] is None  # match write rolled back


def test_one_uri_two_brands_keep_separate_decisions(sandbox):
    loop, adb, conn = sandbox
    other = "Brand Monitoring Lion Corporation"
    _seed(loop, conn, "u8")
    async def second_group():
        gid = await conn.fetchval("INSERT INTO keyword_groups (name, topic, source, is_active) VALUES ('g-lion', $1, 'news', true) RETURNING id", other)
        await conn.execute("INSERT INTO keyword_article_matches (article_uri, keyword_ids, group_id) VALUES ('u8', '2', $1)", gid)
    loop.run_until_complete(second_group())
    loop.run_until_complete(st.save_rejection(adb, {"uri": "u8", "title": "T"}, TOPIC, _dec("subject", src="owned")))
    loop.run_until_complete(st.save_label_with_status(adb, "u8", other, _dec("subject", src="independent"), "approved"))
    rows = loop.run_until_complete(conn.fetch(
        "SELECT g.topic, m.brand_relation, m.source_relation FROM keyword_article_matches m JOIN keyword_groups g ON g.id=m.group_id "
        "WHERE m.article_uri='u8' ORDER BY g.topic"))
    assert [(r["topic"], r["source_relation"]) for r in rows] == [(TOPIC, "owned"), (other, "independent")]


def test_label_with_status_keeps_article_untouched(sandbox):
    loop, adb, conn = sandbox
    _seed(loop, conn, "u9", article_status=None)
    loop.run_until_complete(st.save_label_with_status(adb, "u9", TOPIC, _dec("notable"), "quality_failed"))
    r = _row(loop, conn, "u9")
    assert (r["brand_relation"], r["relevance_status"], r["ingest_status"]) == ("notable", "quality_failed", None)
    assert loop.run_until_complete(st.stored_state(adb, "u9", TOPIC))[0] == "label_done"
