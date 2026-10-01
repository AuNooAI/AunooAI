"""Query expressions: parse the operator's text, compile it per provider.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work package 9.
"""
from __future__ import annotations

from app.collectors.query_expression import (
    And, Not, Or, Term, compile_for, parse_expression,
    STATUS_EXACT, STATUS_UNSUPPORTED,
)


def test_exact_phrase_remains_a_phrase():
    c = compile_for("newsdata", parse_expression('"gum disease" OR Parodontitis'))
    assert c.status == STATUS_EXACT
    assert c.query == '"gum disease" OR Parodontitis'


def test_three_alternative_brands_survive():
    c = compile_for("newsdata", parse_expression("Oviva OR HelloBetter OR zanadio"))
    assert c.query == "Oviva OR HelloBetter OR zanadio"
    assert len(parse_expression("Oviva OR HelloBetter OR zanadio").terms()) == 3


def test_commas_and_pipes_are_alternatives_and_plus_is_and():
    assert compile_for("newsdata", parse_expression("a, b | c")).query == "a OR b OR c"
    assert compile_for("newsdata", parse_expression("a + b")).query == "a AND b"


def test_exclusion_is_rendered_as_a_not_b():
    c = compile_for("newsdata", parse_expression("wiley -recall"))
    assert c.query == "wiley NOT recall"
    c = compile_for("newsdata", parse_expression('(a OR b) AND "c d" NOT e'))
    assert c.query == '(a OR b) AND "c d" NOT e'


def test_nested_exclusion_fails_explicitly_for_newsdata():
    c = compile_for("newsdata", parse_expression("a OR (b NOT c)"))
    assert c.status == STATUS_UNSUPPORTED
    assert c.query is None
    assert "exclusion" in (c.reason or "")


def test_exclusion_without_positive_term_is_unsupported():
    c = compile_for("newsdata", parse_expression("NOT recall"))
    assert c.status == STATUS_UNSUPPORTED


def test_unicode_terms_are_intact():
    c = compile_for("newsdata", parse_expression("歯周病 AND Käse OR サンスター"))
    assert "歯周病" in c.query and "Käse" in c.query and "サンスター" in c.query
    assert c.status == STATUS_EXACT


def test_curly_quotes_are_phrases():
    e = parse_expression("“GUM toothpaste” OR Sunstar")
    assert isinstance(e.root, Or)
    assert e.root.children[0] == Term("GUM toothpaste", phrase=True)


def test_empty_input_is_empty_expression():
    for text in ("", "   ", None, "AND OR", "()"):
        e = parse_expression(text)
        assert e.empty, text
        c = compile_for("newsdata", e)
        assert c.query is None and c.status == STATUS_EXACT


def test_long_query_is_refused_rather_than_cut():
    text = " OR ".join(f"brand{i}" for i in range(120))
    c = compile_for("newsdata", parse_expression(text))
    assert c.status == STATUS_UNSUPPORTED
    assert "512" in c.reason


def test_tree_shape_and_precedence():
    e = parse_expression("a b OR c")
    assert isinstance(e.root, Or)
    assert isinstance(e.root.children[0], And)
    assert e.root.children[1] == Term("c")
    e = parse_expression("a NOT b")
    assert isinstance(e.root, And)
    assert isinstance(e.root.children[1], Not)
    assert [t.text for t in e.excluded_terms()] == ["b"]


def test_never_substitutes_a_generic_query():
    for text in ("", "the of", "!!!"):
        c = compile_for("newsdata", parse_expression(text))
        assert c.query not in ("news", "AI")
