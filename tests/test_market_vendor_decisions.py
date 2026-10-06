"""Brand decisions for Market Monitor vendor links
(docs/BRAND_RELEVANCE_MARKET_VENDORS.md).

The rule: with MARKET_VENDOR_DECISIONS on, the market's name match decides
each (article, vendor) pair with the brand decision and writes the vendor link
only when the decision is earned; every decision is stored; the article enters
the market corpus whatever the outcome. With the flag off nothing changes.

Write-path tests run against the real schema inside a transaction that is
always rolled back, on constructed ``test.invalid`` articles, as
tests/test_market_corpus_names.py does. The judge is a stub: no model call.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.services import brand_decision as bd
from app.services import brand_profile as bp
from app.services import market_corpus as mcorp
from app.services import market_vendor_decisions as mvd


class _Judge:
    def __init__(self, label=None, fail=False):
        self.label, self.fail, self.calls = label, fail, []
        self.route = "stub"

    def __call__(self, profile, article, mention, quality):
        self.calls.append((profile.display_name, article.get("uri"), mention.status))
        if self.fail:
            raise bd.JudgeUnavailable("stub judge down")
        return self.label, "stub reason", "stub-model"


@pytest.fixture()
def conn():
    from app.database import get_database_instance
    c = get_database_instance()._temp_get_connection()
    if not c.execute(text("SELECT to_regclass('brand_article_decisions') IS NOT NULL")).scalar():
        c.close()
        pytest.skip("bm_001 not applied on this database")
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture()
def market(conn):
    row = conn.execute(text("SELECT id FROM bw_markets ORDER BY id LIMIT 1")).scalar()
    if row is None:
        pytest.skip("no market in this database")
    return int(row)


@pytest.fixture()
def flag_on(monkeypatch):
    monkeypatch.setenv("MARKET_VENDOR_DECISIONS", "1")
    from app.services import brand_ingest_hooks
    monkeypatch.setattr(brand_ingest_hooks, "_reserve_judge_call", lambda: True)


def _set_judge(monkeypatch, judge):
    monkeypatch.setattr(mvd.bd, "configured_judges", lambda: (judge,))


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _land(conn, uri, title, summary):
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, submission_date, publication_date, news_source, topic)
        VALUES (:uri, :title, :summary, :now, :now, 'test.invalid', 'constructed for a test')
        ON CONFLICT (uri) DO NOTHING
    """), {"uri": uri, "title": title, "summary": summary, "now": _now()})


def _vendor_named_in_title(conn, market):
    """A tracked vendor whose first reviewed name the brand profile accepts as
    a headline mention without extra context, with that name."""
    vendors = mcorp.vendor_name_terms(conn, market)
    profiles = mvd.profiles_by_id(conn, [v["brand_id"] for v in vendors])
    q = mcorp.market_qualifier(conn, market) or "security"
    for v in vendors:
        p = profiles.get(v["brand_id"])
        if p is None:
            continue
        term = v["terms"][0]
        art = {"uri": "https://test.invalid/x", "title": f"{term} raises a round",
               "summary": f"{term} announced funding for its {q} platform."}
        if bp.detect_mention(p, art).status == "title" and not bp.exclusion(p, art):
            return v, term, q
    pytest.skip("no vendor whose name the profile accepts in a headline")


def _links(conn, uri, brand_id):
    return conn.execute(text("SELECT classification_method FROM bw_article_categories "
                             "WHERE article_uri = :u AND brand_id = :b"), {"u": uri, "b": brand_id}).fetchall()


def _decision(conn, uri, brand_id):
    return mvd.stored(conn, uri, brand_id)


def _in_corpus(conn, market, uri):
    return conn.execute(text("SELECT 1 FROM bw_market_articles WHERE market_id = :m AND article_uri = :u"),
                        {"m": market, "u": uri}).scalar() == 1


# ---------------------------------------------------------------------------
# Flag off: exactly today's behaviour
# ---------------------------------------------------------------------------

def test_flag_off_links_as_before_and_stores_no_decision(conn, market, monkeypatch):
    monkeypatch.delenv("MARKET_VENDOR_DECISIONS", raising=False)
    v, term, q = _vendor_named_in_title(conn, market)
    uri = "https://test.invalid/mvd/off"
    _land(conn, uri, f"{term} raises a round", f"{term} announced funding for its {q} platform.")
    out = mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    assert len(_links(conn, uri, v["brand_id"])) == 1
    assert _decision(conn, uri, v["brand_id"]) is None
    assert out["vendor_decisions"] is None


# ---------------------------------------------------------------------------
# Flag on: the rule table
# ---------------------------------------------------------------------------

def test_earned_decision_writes_the_link_and_is_stored_as_linked(conn, market, flag_on, monkeypatch):
    judge = _Judge("subject")
    _set_judge(monkeypatch, judge)
    v, term, q = _vendor_named_in_title(conn, market)
    uri = "https://test.invalid/mvd/earned"
    _land(conn, uri, f"{term} raises a round", f"{term} announced funding for its {q} platform.")
    mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    assert [m for (m,) in _links(conn, uri, v["brand_id"])] == [mcorp.NAME_MATCH_METHOD]
    row = _decision(conn, uri, v["brand_id"])
    assert row["outcome"] == "decided" and row["brand_relation"] == "subject" and row["linked"] is True
    assert _in_corpus(conn, market, uri)
    assert judge.calls


def test_a_settled_pair_is_not_judged_again_on_the_next_scan(conn, market, flag_on, monkeypatch):
    judge = _Judge("subject")
    _set_judge(monkeypatch, judge)
    v, term, q = _vendor_named_in_title(conn, market)
    uri = "https://test.invalid/mvd/settled"
    _land(conn, uri, f"{term} raises a round", f"{term} announced funding for its {q} platform.")
    mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    n = len([c for c in judge.calls if c[1] == uri])
    mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    assert len([c for c in judge.calls if c[1] == uri]) == n == 1
    assert len(_links(conn, uri, v["brand_id"])) == 1


def test_passing_mention_is_stored_but_not_linked_and_stays_in_the_corpus(conn, market, flag_on, monkeypatch):
    _set_judge(monkeypatch, _Judge("passing"))
    v, term, q = _vendor_named_in_title(conn, market)
    uri = "https://test.invalid/mvd/passing"
    _land(conn, uri, f"Ten {q} tools compared",
          f"A long roundup of the {q} market that lists {term} among many others in passing.")
    out = mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    if _decision(conn, uri, v["brand_id"]) is None:
        pytest.skip("the name match did not fire on the constructed body mention")
    assert _links(conn, uri, v["brand_id"]) == []
    row = _decision(conn, uri, v["brand_id"])
    assert row["outcome"] == "decided" and row["brand_relation"] == "passing" and row["linked"] is False
    assert _in_corpus(conn, market, uri)
    assert out["not_earned"] >= 1


def test_unavailable_judgment_writes_no_link_and_the_retry_links_it(conn, market, flag_on, monkeypatch):
    _set_judge(monkeypatch, _Judge(fail=True))
    v, term, q = _vendor_named_in_title(conn, market)
    uri = "https://test.invalid/mvd/retry"
    _land(conn, uri, f"Inside the {q} market",
          f"Analysts say {term} is changing how teams buy {q} tools, with new contracts this quarter.")
    mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    row = _decision(conn, uri, v["brand_id"])
    if row is None:
        pytest.skip("the name match did not fire on the constructed body mention")
    assert row["outcome"] == "unavailable" and _links(conn, uri, v["brand_id"]) == []
    assert json.loads(json.dumps(row["last_failure"]))["attempts"] == 1

    out = mvd.retry_unavailable(conn, 500, judges=(_Judge("notable"),))
    assert out["linked"] >= 1
    row = _decision(conn, uri, v["brand_id"])
    assert row["outcome"] == "decided" and row["brand_relation"] == "notable" and row["linked"] is True
    assert len(_links(conn, uri, v["brand_id"])) == 1


def test_retry_stops_at_the_attempt_cap(conn, market, flag_on, monkeypatch):
    monkeypatch.setenv("BRAND_RETRY_MAX_ATTEMPTS", "2")
    _set_judge(monkeypatch, _Judge(fail=True))
    v, term, q = _vendor_named_in_title(conn, market)
    uri = "https://test.invalid/mvd/cap"
    _land(conn, uri, f"Inside the {q} market",
          f"Analysts say {term} is changing how teams buy {q} tools, with new contracts this quarter.")
    mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    if _decision(conn, uri, v["brand_id"]) is None:
        pytest.skip("the name match did not fire on the constructed body mention")
    mvd.retry_unavailable(conn, 500, judges=(_Judge(fail=True),))
    assert json.loads(json.dumps(_decision(conn, uri, v["brand_id"])["last_failure"]))["attempts"] == 2
    picked = [r for r in conn.execute(text(
        "SELECT article_uri FROM brand_article_decisions WHERE outcome='unavailable' "
        "AND COALESCE((last_failure->>'attempts')::int,0) < 2")).fetchall() if r[0] == uri]
    assert picked == []


# ---------------------------------------------------------------------------
# Profiles, reuse, readers
# ---------------------------------------------------------------------------

def test_disabled_vendors_still_get_a_profile(conn):
    row = conn.execute(text("SELECT id FROM bw_brands WHERE NOT enabled ORDER BY id LIMIT 1")).scalar()
    if row is None:
        pytest.skip("no disabled brand in this database")
    assert int(row) in mvd.profiles_by_id(conn, [int(row)])


def test_a_vendor_without_a_brand_row_defers():
    d = mvd.decide(None, None, {"uri": "https://test.invalid/x", "title": "x"})
    assert d.outcome == "deferred"


def test_reuse_finds_a_decision_in_either_store(conn, market, flag_on):
    v, term, q = _vendor_named_in_title(conn, market)
    uri = "https://test.invalid/mvd/reuse"
    d = bd.Decision("decided", "subject", "independent", provenance="model", reason="r",
                    evidence={"profile_version": "p"}, judge_version="key-abc")
    mvd.save(conn, uri, v["brand_id"], market, d, linked=True)
    hit = mvd.reuse_lookup(conn, uri)("key-abc")
    assert hit is not None and hit.brand_relation == "subject"
    assert mvd.reuse_lookup(conn, uri)("other-key") is None


def test_coverage_split_counts_market_decisions_once_per_article(conn, market):
    from app.services.brand_coverage import coverage_split
    v, term, q = _vendor_named_in_title(conn, market)
    name = conn.execute(text("SELECT display_name FROM bw_brands WHERE id = :b"), {"b": v["brand_id"]}).scalar()
    uri = "https://test.invalid/mvd/split"
    _land(conn, uri, f"{term} raises a round", "body")
    before = coverage_split(conn, name, days=30)["counts"].get("passing", 0)
    mvd.save(conn, uri, v["brand_id"], market,
             bd.Decision("decided", "passing", "independent", evidence={"profile_version": "p"}), linked=False)
    after = coverage_split(conn, name, days=30)["counts"].get("passing", 0)
    assert after == before + 1


def test_comparisons_wait_for_the_switch_on_date(conn, market):
    from app.services import market_analysis as ma
    started = ma.collection_started(conn, market)
    later = datetime.now(timezone.utc) - timedelta(days=1)
    conn.execute(text("UPDATE bw_markets SET config = COALESCE(config::jsonb, '{}'::jsonb) || "
                      "jsonb_build_object('vendor_decisions_since', CAST(:s AS text)) WHERE id = :m"),
                 {"s": later.isoformat(), "m": market})
    base = ma.comparison_baseline(conn, market)
    assert base is not None and abs((base - later).total_seconds()) < 1
    assert not ma.period_comparison(conn, market, days=30)["comparable"]
    if started is not None:
        assert base >= started


def test_uipath_generic_product_names_need_uipath_nearby():
    row = {"id": 1, "name": "uipath", "display_name": "UiPath", "brand_keywords": ["UiPath"],
           "product_keywords": ["Test Suite", "Test Manager", "Test Cloud"],
           "config": {"ambiguous_aliases": ["Test Suite", "Test Manager", "Test Cloud"],
                      "mention_context": ["UiPath"]}}
    p = bp.build_profile(row)
    dev = {"uri": "https://test.invalid/dev", "title": "Automating Wi-Fi setup testing on the ESP32",
           "summary": "We run the rig nightly as part of our test suite and a test manager reviews failures."}
    press = {"uri": "https://test.invalid/press", "title": "UiPath Test Suite adds agentic testing",
             "summary": "UiPath said Test Suite now runs autonomous agents."}
    assert not bp.detect_mention(p, dev).verified
    assert bp.detect_mention(p, press).status == "title"


def test_social_posts_keep_todays_rule(conn, market, flag_on, monkeypatch):
    judge = _Judge("passing")
    _set_judge(monkeypatch, judge)
    v, term, q = _vendor_named_in_title(conn, market)
    uri = "https://test.invalid/mvd/social"
    _land(conn, uri, f"{term} raises a round", f"{term} announced funding for its {q} platform.")
    conn.execute(text("UPDATE articles SET social_meta = '{\"platform\": \"bluesky\"}' WHERE uri = :u"), {"u": uri})
    mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    assert len(_links(conn, uri, v["brand_id"])) == 1
    assert _decision(conn, uri, v["brand_id"]) is None
    assert not [c for c in judge.calls if c[1] == uri]
