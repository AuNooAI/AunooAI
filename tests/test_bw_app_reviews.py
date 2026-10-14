"""App store reviews for Brand Watcher (docs/APP_STORE_REVIEWS_SPEC.md).

Pure mapping tests first, then the fetch, landing, cap and alert checks
against PostgreSQL in a throwaway schema. Bright Data is never called: every
test passes a fake scrape function.
"""
import asyncio
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services import bw_app_reviews as ar

PLAY = {"store": "google_play", "app_id": "com.example.app", "country": "GB", "language": "en"}
APPLE = {"store": "app_store", "app_id": "123456", "country": "gb", "language": ""}


def _play_rec(rid, rating, day, text="The reminders are useful and the coach answers quickly.", **kw):
    rec = {"review_id": rid, "reviewer_name": "Jane Example", "review_date": f"{day}T10:00:00.000Z",
           "review_rating": rating, "review": text, "found_helpful": 3,
           "app_rating": 4.41, "app_number_of_reviews": 30673, "app_downloads": 413668,
           "app_title": "Example", "app_country": "GB", "app_developer": "Google Commerce Ltd"}
    rec.update(kw)
    return rec


def _apple_rec(rid, rating, day, reply=None):
    return {"review_id": rid, "reviewer_name": "Jane Example", "review_title": "Handy",
            "review_date": f"{day}T10:00:00Z", "review_rating": rating,
            "review": "Simple to log meals.", "developer_response": reply,
            "app_latest_version": "5.2.0"}


# ---------------------------------------------------------------------------
# Pure
# ---------------------------------------------------------------------------

def test_play_review_maps_to_article_row_without_reviewer_name():
    row = ar.map_review(_play_rec("abc-1", 2, "2026-10-01"), PLAY, "Example")
    assert row["url"] == "https://play.google.com/store/apps/details?id=com.example.app&reviewId=abc-1"
    assert row["title"].startswith("Google Play review (2/5): The reminders")
    assert row["sentiment"] == "Negative"
    assert row["published_at"] == "2026-10-01"
    assert row["social_meta"]["rating"] == 2
    assert "Jane" not in json.dumps(row)
    assert "Google Commerce" not in json.dumps(row)


def test_apple_reply_is_added_to_summary():
    row = ar.map_review(_apple_rec("r1", 5, "2026-10-02", reply="Thanks, glad it helps."), APPLE, "Example")
    assert row["summary"].endswith("Example replied: Thanks, glad it helps.")
    assert row["social_meta"]["has_developer_reply"] is True
    assert row["url"] == "https://apps.apple.com/gb/app/id123456#review-r1"
    assert row["sentiment"] == "Positive"


def test_error_and_idless_records_are_dropped():
    assert ar.map_review({"error": "bad url"}, PLAY, "X") is None
    assert ar.map_review({"review": "no id"}, PLAY, "X") is None


def test_targets_validate_and_normalise():
    cfg = {"app_store_targets": [
        {"store": "google_play", "app_id": "com.a", "country": "GB"},
        {"store": "app_store", "app_id": "id42", "country": "de"},
        {"store": "app_store", "app_id": "not-a-number", "country": "de"},
        {"store": "google_play", "app_id": "", "country": "GB"},
    ]}
    assert [t["app_id"] for t in ar.targets_for(cfg, "google_play")] == ["com.a"]
    assert [t["app_id"] for t in ar.targets_for(cfg, "app_store")] == ["42"]


def test_app_figures():
    f = ar.app_figures([_play_rec("1", 4, "2026-10-01")], PLAY)
    assert (f["rating"], f["review_count"], f["downloads"]) == (4.41, 30673, 413668)
    g = ar.app_figures([_apple_rec("1", 4, "2026-10-01", reply="x"), _apple_rec("2", 1, "2026-10-01")], APPLE)
    assert g["rating"] is None and g["data"]["reply_share"] == 0.5
    assert ar.app_figures([{"error": "x"}], PLAY) is None


def test_play_payload_windows_by_date():
    p = ar._payload(PLAY, datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert p["start_date"] == "2026-10-01" and p["num_of_reviews"] == ar.MAX_REVIEWS_PER_CALL
    assert p["language"] == "en" and p["country"] == "GB"
    assert ar._payload(APPLE, datetime(2026, 10, 1)) == {"url": "https://apps.apple.com/gb/app/id123456"}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    try:
        from dotenv import load_dotenv
        from sqlalchemy import create_engine, text
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
        schema = f"apptest_{uuid.uuid4().hex[:8]}"
        url = (f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST', 'localhost')}:"
               f"{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}")
        eng = create_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
        conn = eng.connect()
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        for t in ("articles", "bw_brands", "bw_article_categories", "bw_app_snapshots",
                  "bw_app_review_calls", "bw_article_risks"):
            conn.execute(text(f"CREATE TABLE {schema}.{t} (LIKE public.{t} INCLUDING ALL)"))
        conn.execute(text(
            "INSERT INTO bw_brands (id, name, display_name, enabled, brand_keywords, config) "
            "VALUES (1, 'Example', 'Example', true, '[]', CAST(:c AS jsonb))"),
            {"c": json.dumps({"extra_sources": ["google_play"],
                              "app_review_author_role": "patient",
                              "app_store_targets": [
                                  {"store": "google_play", "app_id": "com.example.app", "country": "GB"},
                                  {"store": "google_play", "app_id": "com.example.other", "country": "DE"}]})})
        conn.commit()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no sandbox: {e}")
    yield conn, text
    conn.rollback()
    conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    conn.commit()
    conn.close()


def _cfg(conn, text):
    raw = conn.execute(text("SELECT config FROM bw_brands WHERE id = 1")).scalar()
    return raw if isinstance(raw, dict) else json.loads(raw)


BRAND = {"id": 1, "display_name": "Example", "brand_keywords": "[]"}


def _today(offset=0):
    return (date.today() - timedelta(days=offset)).isoformat()


def test_poll_lands_once_sets_role_snapshot_and_cursor(db, monkeypatch):
    conn, text = db
    from app.services import bw_official_sources as bos

    async def fake(store, payload):
        if "other" in payload["url"]:
            return []
        return [_play_rec("n1", 1, _today(1)), _play_rec("n2", 5, _today(2)),
                _play_rec("old", 3, _today(90))]
    monkeypatch.setattr(ar, "_scrape", fake)

    async def no_risk(*a, **k):
        return 0
    monkeypatch.setattr(bos, "_risk_pass", no_risk)

    now = datetime.now(timezone.utc)
    summary = {"polled": 0, "new_articles": 0, "risk_flagged": 0, "errors": 0}
    cfg = _cfg(conn, text)
    ran = asyncio.run(bos._poll_app_reviews(conn, BRAND, cfg, {}, "google_play", now, False, [10], summary))
    assert ran and summary["new_articles"] == 2 and summary["errors"] == 0  # the 90-day-old one dropped

    rows = conn.execute(text("SELECT news_source, author_role, social_meta->>'rating', row_to_json(articles)::text FROM articles ORDER BY uri")).fetchall()
    assert {r[0] for r in rows} == {"Google Play"}
    assert {r[1] for r in rows} == {"patient"}
    assert not any("Jane" in r[3] for r in rows)  # no reviewer name anywhere in the stored row
    assert conn.execute(text("SELECT COUNT(*) FROM bw_article_categories WHERE brand_id = 1")).scalar() == 2
    snap = conn.execute(text("SELECT rating, review_count FROM bw_app_snapshots")).fetchall()
    assert [(float(s[0]), s[1]) for s in snap] == [(4.41, 30673)]  # the empty target writes none
    assert conn.execute(text("SELECT COUNT(*), SUM(records) FROM bw_app_review_calls")).fetchone() == (2, 3)
    assert (_cfg(conn, text)["source_state"]["google_play"]["last_polled_at"]) == now.isoformat()

    # Same reviews again: nothing new lands.
    summary2 = {"polled": 0, "new_articles": 0, "risk_flagged": 0, "errors": 0}
    asyncio.run(bos._poll_app_reviews(conn, BRAND, cfg, {}, "google_play", now, True, [10], summary2))
    assert summary2["new_articles"] == 0


def test_failed_target_keeps_cursor_and_others_run(db, monkeypatch):
    conn, text = db
    from app.services import bw_official_sources as bos

    async def fake(store, payload):
        if "other" in payload["url"]:
            raise RuntimeError("HTTP 500")
        return [_play_rec("n1", 4, _today(1))]
    monkeypatch.setattr(ar, "_scrape", fake)

    async def no_risk(*a, **k):
        return 0
    monkeypatch.setattr(bos, "_risk_pass", no_risk)

    summary = {"polled": 0, "new_articles": 0, "risk_flagged": 0, "errors": 0}
    asyncio.run(bos._poll_app_reviews(conn, BRAND, _cfg(conn, text), {}, "google_play",
                                      datetime.now(timezone.utc), False, [10], summary))
    assert summary["new_articles"] == 1 and summary["errors"] == 1
    assert "source_state" not in _cfg(conn, text)
    assert conn.execute(text("SELECT ok, error FROM bw_app_review_calls WHERE NOT ok")).fetchone()[1] == "HTTP 500"


def test_monthly_cap_stops_calls(db, monkeypatch):
    conn, text = db
    calls = []

    async def fake(store, payload):
        calls.append(payload["url"])
        return []
    monkeypatch.setenv("BW_APP_REVIEWS_MONTHLY_RECORDS", "60")
    conn.execute(text("INSERT INTO bw_app_review_calls (brand_id, store, app_id, country, records, ok) "
                      "VALUES (1, 'google_play', 'x', 'GB', 20, true)"))
    rows, complete = asyncio.run(ar.fetch_app_reviews(
        conn, BRAND, _cfg(conn, text), "google_play", datetime.now(timezone.utc) - timedelta(days=1), scrape=fake))
    assert calls == [] and complete is False


def test_rating_drop(db):
    conn, text = db
    for offset, rating in ((20, 4.41), (12, 4.35), (2, 4.30)):
        ar.save_snapshot(conn, 1, PLAY, {"rating": rating, "review_count": 1, "downloads": 1}, _today(offset))
    drops = ar.rating_drops(conn, 1, 0.1, 35, 7)
    assert len(drops) == 1 and drops[0]["rating_old"] == 4.41 and drops[0]["rating_new"] == 4.30
    assert ar.rating_drops(conn, 1, 0.2, 35, 7) == []
    # The same fall inside three days is too quick to call.
    conn.execute(text("DELETE FROM bw_app_snapshots"))
    ar.save_snapshot(conn, 1, PLAY, {"rating": 4.41}, _today(3))
    ar.save_snapshot(conn, 1, PLAY, {"rating": 4.30}, _today(0))
    assert ar.rating_drops(conn, 1, 0.1, 35, 7) == []


def _land_review(conn, text, uri, day, stars):
    conn.execute(text("INSERT INTO articles (uri, title, news_source, publication_date, social_meta) "
                      "VALUES (:u, 't', 'Google Play', :d, CAST(:m AS jsonb))"),
                 {"u": uri, "d": day, "m": json.dumps({"rating": stars})})
    conn.execute(text("INSERT INTO bw_article_categories (article_uri, brand_id, category, classification_method, confidence, relevance_score) "
                      "VALUES (:u, 1, 'Brand Sentiment & Perception', 'official', 1, 1)"), {"u": uri})


def test_negative_counts(db):
    conn, text = db
    for i in range(6):
        _land_review(conn, text, f"recent{i}", _today(1), 1)
    _land_review(conn, text, "recent-good", _today(1), 5)
    for i in range(16):  # 2 a week over the 8 weeks before
        _land_review(conn, text, f"old{i}", _today(10 + i * 3), 2)
    recent, weekly = ar.negative_counts(conn, 1, 8)
    assert recent == 6 and weekly == 2.0


def test_app_reviews_classify_as_community_voices():
    from app.services.social_sources import classify_source
    assert classify_source("Google Play", "official:play.google.com") == ("google_play", "community")
    assert classify_source("App Store", "official:apps.apple.com") == ("app_store", "community")


def test_app_store_polls_weekly_and_google_play_daily(monkeypatch):
    from app.services import bw_official_sources as bos
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    state = {"app_store": {"last_polled_at": "2026-10-16T00:00:00+00:00"},
             "google_play": {"last_polled_at": "2026-10-16T00:00:00+00:00"}}
    assert bos._due_since(state, "app_store", now, interval=bos._app_poll_interval("app_store")) is None
    assert bos._due_since(state, "google_play", now, interval=bos._app_poll_interval("google_play")) is not None
    monkeypatch.setenv("BW_APP_STORE_POLL_DAYS", "3")
    assert bos._due_since(state, "app_store", now, interval=bos._app_poll_interval("app_store")) is not None


def test_a_progress_note_is_waited_for_not_counted_as_a_review(monkeypatch):
    calls = []

    class _Client:
        def __init__(self, key):
            pass

        async def scrape_sync(self, dataset, payload):
            return [{"snapshot_id": "sd_x", "message": "Your request is still in progress"}]

        async def snapshot_status(self, sid):
            calls.append("status")
            return {"status": "running" if len(calls) < 2 else "ready"}

        async def fetch_snapshot(self, sid):
            return [_apple_rec("r1", 4, "2026-10-01")]

    import app.services.brightdata_linkedin as bl
    monkeypatch.setattr(bl, "LinkedInDatasetClient", _Client)
    monkeypatch.setattr(bl, "api_key", lambda: "k")
    monkeypatch.setattr(ar, "SNAPSHOT_POLL_SECONDS", 0)
    out = asyncio.run(ar._scrape("app_store", {"url": "u"}))
    assert [r["review_id"] for r in out] == ["r1"] and calls == ["status", "status"]


def test_a_snapshot_that_never_finishes_is_a_failure(monkeypatch):
    class _Client:
        def __init__(self, key):
            pass

        async def scrape_sync(self, dataset, payload):
            return [{"snapshot_id": "sd_y", "message": "still in progress"}]

        async def snapshot_status(self, sid):
            return {"status": "running"}

    import app.services.brightdata_linkedin as bl
    monkeypatch.setattr(bl, "LinkedInDatasetClient", _Client)
    monkeypatch.setattr(bl, "api_key", lambda: "k")
    monkeypatch.setattr(ar, "SNAPSHOT_POLL_SECONDS", 0)
    monkeypatch.setattr(ar, "SNAPSHOT_WAIT_SECONDS", 0)
    with pytest.raises(RuntimeError, match="not ready"):
        asyncio.run(ar._scrape("app_store", {"url": "u"}))
