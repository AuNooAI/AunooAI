"""Vendor-name attribution in the corpus scan.

The rule under test: an article that names a vendor is linked to that vendor,
once, and a name that could be an ordinary word is only believed when the
market's own language sits beside it or the page is the vendor's own.

The pure parts (which names a vendor answers to, what "distinctive" means,
what a hit is) run with no database. The write path runs against the real
schema inside a transaction that is always rolled back, using a constructed
article on a ``test.invalid`` URI, so nothing it does survives the test.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services import market_corpus as mcorp


# ---------------------------------------------------------------------------
# Which names a vendor answers to
# ---------------------------------------------------------------------------

def test_bracketed_note_is_not_part_of_the_name():
    assert mcorp._strip_parenthetical("Variance (was Intrinsic)") == "Variance"
    assert mcorp._strip_parenthetical("Strike48 (A Devo company)") == "Strike48"
    assert mcorp._strip_parenthetical("Crogl") == "Crogl"


class _Conn:
    """Just enough of a connection to feed vendor_name_terms one result set."""

    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_a, **_k):
        rows = self._rows

        class _R:
            def fetchall(self_inner):
                return rows
        return _R()


def test_reviewed_keywords_are_used_as_written_and_name_is_only_a_fallback():
    conn = _Conn([
        # id, display_name, brand_keywords, product_keywords, config
        (1, "Cantina", ["Cantina security"], [], {}),
        (2, "Variance (was Intrinsic)",
         ["Variance security", "Intrinsic security"], [], {}),
        (3, "Crogl", None, None, {"news_keyword_excludes": ["Crogl Ltd"]}),
        (4, "Dropzone AI", ["Dropzone AI"], ["Dropzone AI", "dropzone ai"],
         {}),
    ])
    out = {v["vendor"]: v for v in mcorp.vendor_name_terms(conn, 2)}
    # A reviewed keyword replaces the bare name, it does not sit beside it.
    assert out["Cantina"]["terms"] == ["Cantina security"]
    assert "Cantina" not in out["Cantina"]["terms"]
    assert out["Variance (was Intrinsic)"]["terms"] == [
        "Variance security", "Intrinsic security"]
    # No keyword at all: the display name, and only then.
    assert out["Crogl"]["terms"] == ["Crogl"]
    assert out["Crogl"]["excludes"] == ["Crogl Ltd"]
    # Case-duplicates collapse to one term.
    assert out["Dropzone AI"]["terms"] == ["Dropzone AI"]


# ---------------------------------------------------------------------------
# What counts as a hit
# ---------------------------------------------------------------------------

def _v(brand_id, name, terms, excludes=()):
    return {"brand_id": brand_id, "vendor": name, "terms": list(terms),
            "excludes": list(excludes)}


def test_a_name_inside_another_word_is_not_a_hit():
    vendors = [_v(1, "Nua", ["Nua"]), _v(2, "Mave", ["Mave"])]
    assert mcorp._vendor_hits("the annual report is manual work", vendors) == []
    hits = mcorp._vendor_hits("Nua raised a seed round", vendors)
    assert [(v["vendor"], t) for v, t in hits] == [("Nua", "Nua")]


def test_names_that_start_or_end_in_a_non_word_character_still_match():
    vendors = [_v(1, "7ai", ["7ai"]), _v(2, "Secure.com", ["Secure.com"])]
    hits = mcorp._vendor_hits("Thanks to 7AI's team; Secure.com joined too",
                              vendors)
    assert sorted(v["vendor"] for v, _ in hits) == ["7ai", "Secure.com"]


def test_one_vendor_is_one_hit_however_many_of_its_names_appear():
    vendors = [_v(1, "Variance", ["Variance security", "Intrinsic security"])]
    hits = mcorp._vendor_hits(
        "Variance security, formerly Intrinsic security, ships", vendors)
    assert len(hits) == 1


def test_a_per_vendor_exclude_phrase_vetoes_the_article_for_that_vendor():
    vendors = [_v(1, "Crogl", ["Crogl"], excludes=["Crogl Ltd"]),
               _v(2, "Intezer", ["Intezer"])]
    hits = mcorp._vendor_hits("Crogl Ltd and Intezer both hire", vendors)
    assert [v["vendor"] for v, _ in hits] == ["Intezer"]


# ---------------------------------------------------------------------------
# When a name needs company
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("term,expected", [
    ("7ai", True), ("Secure.com", True), ("Strike48", True),
    ("SOC Jedi.ai", True),
    ("Joon", False), ("Andesite", False), ("Alpha Level", False),
    ("Prophet Security", False), ("", False),
])
def test_a_token_with_a_digit_or_a_dot_cannot_be_a_dictionary_word(term, expected):
    assert mcorp._distinctive(term) is expected


# ---------------------------------------------------------------------------
# The write path, rolled back
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn():
    from app.database import get_database_instance

    c = get_database_instance()._temp_get_connection()
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture()
def market(conn):
    row = conn.execute(text(
        "SELECT id FROM bw_markets ORDER BY id LIMIT 1")).scalar()
    if row is None:
        pytest.skip("no market in this database")
    return int(row)


def _a_vendor(conn, market_id):
    """A tracked vendor and the first name it answers to."""
    vendors = mcorp.vendor_name_terms(conn, market_id)
    if not vendors:
        pytest.skip("no vendors with a name")
    return vendors[0]


def _land(conn, uri, title, summary):
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, submission_date,
                              publication_date, news_source, topic)
        VALUES (:uri, :title, :summary, :now, :now, 'test.invalid',
                'constructed for a test')
        ON CONFLICT (uri) DO NOTHING
    """), {"uri": uri, "title": title, "summary": summary,
           "now": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")})


def _links(conn, uri, brand_id):
    return conn.execute(text("""
        SELECT classification_method FROM bw_article_categories
         WHERE article_uri = :u AND brand_id = :b
    """), {"u": uri, "b": brand_id}).fetchall()


def test_an_article_naming_a_vendor_is_linked_once_and_enters_the_corpus(conn, market):
    vendor = _a_vendor(conn, market)
    term = vendor["terms"][0]
    qualifier = mcorp.market_qualifier(conn, market) or "security"
    uri = "https://test.invalid/names/one"
    _land(conn, uri, f"{term} raises a round",
          f"{term} announced funding to expand its {qualifier} platform.")

    first = mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    assert first["matched"] >= 1
    links = _links(conn, uri, vendor["brand_id"])
    assert len(links) == 1
    assert links[0][0] == mcorp.NAME_MATCH_METHOD
    method = conn.execute(text("""
        SELECT method FROM bw_market_articles
         WHERE market_id = :m AND article_uri = :u
    """), {"m": market, "u": uri}).scalar()
    assert method == mcorp.NAME_MATCH_CORPUS_METHOD

    # MM-10: naming the vendor again, or running again, is still one link.
    second = mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    assert len(_links(conn, uri, vendor["brand_id"])) == 1
    assert second["attributed"] == 0 or second["attributed"] < first["attributed"]


def test_an_article_already_linked_by_another_method_is_not_linked_twice(conn, market):
    vendor = _a_vendor(conn, market)
    term = vendor["terms"][0]
    qualifier = mcorp.market_qualifier(conn, market) or "security"
    uri = "https://test.invalid/names/prior"
    _land(conn, uri, f"{term} in the news", f"A {qualifier} story about {term}.")
    conn.execute(text("""
        INSERT INTO bw_article_categories
            (article_uri, brand_id, category, classification_method, confidence)
        VALUES (:u, :b, 'Product & Innovation', 'llm_semantic', 0.9)
    """), {"u": uri, "b": vendor["brand_id"]})

    mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    links = _links(conn, uri, vendor["brand_id"])
    assert [m for (m,) in links] == ["llm_semantic"]


def test_a_bare_word_name_without_the_markets_language_is_not_linked(conn, market):
    """The K-drama case. A vendor whose only name is an ordinary word is not
    credited with an article that never comes near the market's subject."""
    contexts = mcorp.context_patterns(conn, market)
    if not contexts:
        pytest.skip("market has no qualifier or phrases to require")
    # A name like "Artemis Security" carries the market's word inside it and
    # qualifies itself. The case here is the name that does not.
    vendors = [v for v in mcorp.vendor_name_terms(conn, market)
               if not any(mcorp._distinctive(t) for t in v["terms"])
               and not any(p.search(v["terms"][0]) for p in contexts)]
    if not vendors:
        pytest.skip("every vendor's name is distinctive or self-qualifying")
    vendor = vendors[0]
    term = vendor["terms"][0]
    uri = "https://test.invalid/names/drama"
    body = f"{term} stars in the second season of the drama, airing Friday."
    assert not any(p.search(body) for p in contexts), \
        "fixture accidentally contains the market's language"
    _land(conn, uri, f"{term} joins the cast", body)

    out = mcorp.attribute_vendors(conn, market, days=1, limit=5000)
    assert _links(conn, uri, vendor["brand_id"]) == []
    assert any(r["uri"] == uri for r in out["rejected"])


def test_dry_run_writes_nothing(conn, market):
    vendor = _a_vendor(conn, market)
    term = vendor["terms"][0]
    qualifier = mcorp.market_qualifier(conn, market) or "security"
    uri = "https://test.invalid/names/dry"
    _land(conn, uri, f"{term} ships", f"{term} released a {qualifier} feature.")
    out = mcorp.attribute_vendors(conn, market, days=1, limit=5000, dry_run=True)
    assert out["dry_run"] is True
    assert _links(conn, uri, vendor["brand_id"]) == []


def test_scan_reports_the_name_pass_under_the_same_dry_run(conn, market):
    out = mcorp.scan(conn, market, days=1, limit=200, dry_run=True)
    assert "vendor_names" in out
    assert out["vendor_names"]["dry_run"] is True
    for key in ("vendors", "scanned", "matched", "attributed",
                "already_linked", "without_context", "rejected"):
        assert key in out["vendor_names"]


# ---------------------------------------------------------------------------
# A change needs an earlier period we were collecting in
# ---------------------------------------------------------------------------

def test_a_period_before_collection_began_is_not_comparable(conn, market):
    """A market created last week has no "previous 30 days". The counts are
    still returned — they are counts of dated records — but the payload says
    they cannot be read as a change, and since when."""
    from datetime import datetime, timedelta, timezone

    from app.services import market_analysis as man
    from app.services import market_publish as mp

    started = man.collection_started(conn, market)
    assert started is not None and started.tzinfo is not None
    pc = man.period_comparison(conn, market, days=30)
    expect = (datetime.now(timezone.utc) - timedelta(days=60)) >= started
    assert pc["comparable"] is expect
    assert pc["collection_started"] == started.isoformat()
    assert pc["comparable_from"] == (started + timedelta(days=60)).date().isoformat()

    m = dict(conn.execute(text("SELECT * FROM bw_markets WHERE id = :m"),
                          {"m": market}).mappings().one())
    movers = mp.market_movers(conn, m, days=30)
    coverage_rows = [x for x in movers["movers"]
                     if x["metric"] == "Written about by others"]
    blocked = [u for u in movers["unavailable"]
               if u["metric"] == "Written about by others"]
    if pc["comparable"]:
        assert not blocked
    else:
        assert not coverage_rows
        assert blocked and "no earlier period" in blocked[0]["reason"]
