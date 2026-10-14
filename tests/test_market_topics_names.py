"""Subject names carry no trend words (copy rules in test_market_report_copy).

On 14 Oct 2026 the model named a subject "Prophet Security funding and
momentum"; the headlines said Prophet raised money from Amex Ventures and
Citi Ventures, and "funding and momentum" is banned report copy.
"""
import pytest

from app.services import market_topics as mt


@pytest.mark.parametrize("raw,clean", [
    ("Prophet Security funding and momentum", "Prophet Security funding"),
    ("Prophet Security Funding And Momentum", "Prophet Security Funding"),
    ("Torq gaining momentum with agentic SOC", "Torq with agentic SOC"),
    ("Dropzone AI strong traction in enterprises", "Dropzone AI in enterprises"),
    ("Cribl, momentum and the data pipeline market", "Cribl and the data pipeline market"),
    # A name, not a trend word.
    ("Momentum Cyber M&A report", "Momentum Cyber M&A report"),
    ("RSA Conference 2026 launches", "RSA Conference 2026 launches"),
    # Too little would be left: the name stands.
    ("Momentum", "Momentum"),
])
def test_tidy_name(raw, clean):
    assert mt.tidy_name(raw) == clean


def test_parsed_subjects_are_tidied():
    raw = '{"subjects": [{"name": "Prophet Security funding and momentum", "summary": "s", "members": [1, 2, 3]}]}'
    assert mt._parse_subjects(raw, 5)[0]["name"] == "Prophet Security funding"


def test_the_prompt_rules_out_trend_words():
    prompt = mt._grouping_prompt({"items": [], "window_days": 30}, "AI in the SOC")
    assert "momentum" in prompt and "traction" in prompt
