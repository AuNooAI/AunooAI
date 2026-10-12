"""The firehose keyword compiler.

Groups, phrases and exclusions become the flat OR chain of multi-word terms
the firehose API accepts (8 a request, words in a term ANDed). Fixtures are
the live keywords on bugfixing on 11 Oct 2026.
"""

from __future__ import annotations

from app.collectors.newsfirehose_collector import NewsFirehoseCollector
from app.collectors.query_expression import (
    STATUS_EXACT,
    STATUS_EXPANDED,
    STATUS_UNSUPPORTED,
    compile_newsfirehose_terms,
    parse_expression,
)

KW_190 = ('("president" | "prime minister" | "foreign minister" | "defense minister") '
          '+ (warning | condemnation | visit | summit | ceasefire | mediation | sanctions)')
KW_195 = '(Venezuela | Guyana | Essequibo) + (dispute | referendum | arbitration | "ICJ")'
TOO_BIG = "(" + " | ".join(f"a{i}" for i in range(9)) + ") + (" + " | ".join(f"b{i}" for i in range(8)) + ")"


def terms(q):
    return compile_newsfirehose_terms(parse_expression(q))


def test_keyword_87_is_a_bare_term_and_a_phrase_matched_as_words():
    t = terms('(AI | "artificial intelligence")')
    assert t.terms == ["AI", "artificial intelligence"]
    assert t.status == STATUS_EXPANDED
    assert t.dropped == ['phrase "artificial intelligence" matched as words']


def test_keyword_190_groups_joined_with_plus_become_the_cross_product():
    t = terms(KW_190)
    assert len(t.terms) == 4 * 7 and t.status == STATUS_EXPANDED
    assert t.terms[0] == "president warning" and t.terms[-1] == "defense minister sanctions"
    chunks, why, shape = NewsFirehoseCollector._query_chunks(KW_190)
    assert why is None and len(chunks) == 4
    assert all(len(ch.split(" OR ")) <= 8 for ch in chunks)
    assert chunks[0].startswith("president warning OR president condemnation OR president visit")
    assert shape["query_terms"] == 28 and shape["query_shape"] == STATUS_EXPANDED


def test_keyword_195_is_twelve_terms_in_two_requests():
    t = terms(KW_195)
    assert len(t.terms) == 12 and t.terms[:4] == [
        "Venezuela dispute", "Venezuela referendum", "Venezuela arbitration", "Venezuela ICJ"]
    chunks, why, _ = NewsFirehoseCollector._query_chunks(KW_195)
    assert why is None and len(chunks) == 2


def test_a_flat_list_of_and_terms_is_exact_and_unchanged():
    t = terms("AI startup | AI investment | venture funding AI")
    assert t.terms == ["AI startup", "AI investment", "venture funding AI"]
    assert t.status == STATUS_EXACT and t.dropped == []


def test_uppercase_or_chain_matches_the_old_chunking():
    q = " OR ".join(f"term{i}" for i in range(20))
    chunks, why, _ = NewsFirehoseCollector._query_chunks(q)
    assert why is None and len(chunks) == 3
    assert chunks[0] == " OR ".join(f"term{i}" for i in range(8)) and chunks[2] == "term16 OR term17 OR term18 OR term19"


def test_exclusion_is_dropped_and_reported():
    t = terms("coup -sport")
    assert t.terms == ["coup"] and t.dropped == ["NOT sport"] and t.status == STATUS_EXPANDED


def test_only_an_exclusion_is_unsupported():
    t = terms("-sport")
    assert t.status == STATUS_UNSUPPORTED and not t.ok


def test_product_over_the_cap_is_refused_not_cut():
    t = terms(TOO_BIG)
    assert t.status == STATUS_UNSUPPORTED and "72 terms" in t.reason
    chunks, why, _ = NewsFirehoseCollector._query_chunks(TOO_BIG)
    assert chunks is None and "72 terms" in why


def test_tsquery_operator_characters_are_removed_from_words():
    t = terms("John Wiley & Sons | Taylor:Francis")
    assert t.terms == ["John Wiley Sons", "Taylor Francis"]


def test_lone_quoted_phrase_keeps_its_quotes():
    chunks, why, shape = NewsFirehoseCollector._query_chunks('"Atlantis Press"')
    assert chunks == ['"Atlantis Press"'] and why is None and shape == {"query_shape": "phrase"}


def test_empty_keyword_sends_nothing():
    assert NewsFirehoseCollector._query_chunks("   ") == ([], None, {})
