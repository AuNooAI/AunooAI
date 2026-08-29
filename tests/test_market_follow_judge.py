"""A followed account's post that matched no phrase goes to the judge: it
lands pending under the market's topic, the review pass lists it as
``@handle``, noise leaves it off the market and marked, commentary attaches
it as a watchlist row. Needs Postgres; skips without it."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("DB_TYPE", "postgresql").lower() != "postgresql",
    reason="the market queries are Postgres")

URI_NOISE = "https://x.com/test_follow/status/900000000000000001"
URI_KEEP = "https://x.com/test_follow/status/900000000000000002"


@pytest.fixture()
def conn():
    from sqlalchemy import text

    from app.database import get_database_instance
    try:
        c = get_database_instance()._temp_get_connection()
    except Exception as exc:  # noqa: BLE001 — no DB reachable, not a code failure
        pytest.skip(f"no database available: {exc}")
    try:
        yield c
    finally:
        c.rollback()
        c.execute(text("DELETE FROM bw_market_articles WHERE article_uri IN (:a, :b)"),
                  {"a": URI_NOISE, "b": URI_KEEP})
        c.execute(text("DELETE FROM articles WHERE uri IN (:a, :b)"), {"a": URI_NOISE, "b": URI_KEEP})
        c.commit()
        c.close()


def test_pending_followed_posts_are_judged_and_attached_or_marked(conn):
    from sqlalchemy import text

    from app.services import market_post_review as mpr
    from app.services.market_collect import land_article

    row = conn.execute(text("""
        SELECT id, config->'collection'->>'topic_name' FROM bw_markets
         WHERE config->'collection'->>'topic_name' IS NOT NULL ORDER BY id LIMIT 1""")).fetchone()
    if row is None:
        pytest.skip("no market with a collection topic")
    market_id, topic = int(row[0]), row[1]
    for uri, body in ((URI_NOISE, "lol same"), (URI_KEEP, "Detection content is a product, not a project.")):
        land_article(conn, uri=uri, title=f"@test_follow: {body}", summary=body,
                     news_source="xpoz:twitter", published_at="2026-08-28T10:00:00.000000Z",
                     topic=topic, category="", bias_source="",
                     social_meta={"platform": "twitter", "author": "test_follow",
                                  "followed": True, "pending_review": True})
    conn.commit()

    cands = {c["uri"]: c for c in mpr.followed_candidates(conn, market_id, limit=50)}
    assert URI_NOISE in cands and URI_KEEP in cands
    assert cands[URI_KEEP]["vendor"] == "@test_follow" and cands[URI_KEEP]["followed"] is True
    # The general candidate list carries them too, after the vendor posts.
    assert URI_KEEP in {c["uri"] for c in mpr.candidates(conn, market_id, limit=5000)}

    n = mpr.store(conn, market_id, [
        {"uri": URI_NOISE, "verdict": "noise", "kind": "other", "reason": "a reply", "customer": None,
         "followed": True},
        {"uri": URI_KEEP, "verdict": "commentary", "kind": "opinion", "reason": "an argument",
         "customer": None, "followed": True},
    ], "test-model")
    conn.commit()
    assert n == 2
    attached = {r[0]: r for r in conn.execute(text("""
        SELECT article_uri, method, origin, review_verdict FROM bw_market_articles
         WHERE market_id = :m AND article_uri IN (:a, :b)"""),
        {"m": market_id, "a": URI_NOISE, "b": URI_KEEP}).fetchall()}
    assert URI_NOISE not in attached
    assert attached[URI_KEEP][1:] == ("watchlist", "follow", "commentary")
    flags = {r[0]: r[1] for r in conn.execute(text(
        "SELECT uri, social_meta FROM articles WHERE uri IN (:a, :b)"),
        {"a": URI_NOISE, "b": URI_KEEP}).fetchall()}
    assert flags[URI_NOISE]["follow_verdict"] == "noise" and "pending_review" not in flags[URI_NOISE]
    assert flags[URI_KEEP]["follow_verdict"] == "commentary"
    # Judged once: neither is a candidate again.
    assert not {c["uri"] for c in mpr.followed_candidates(conn, market_id, limit=50)} & {URI_NOISE, URI_KEEP}
