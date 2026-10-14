"""Health side effects in app reviews reach the risk check (14 Oct 2026).

An Oviva Google Play review said the staff's suggestions "would make me
physically sick". No risk vocabulary matched, so it was never screened, and
no risk type covered a person reporting harm to their own health.
"""
import asyncio

import pytest

from app.services import brand_screening as bs
from app.services import bw_official_sources as bos


@pytest.mark.parametrize("text,hit", [
    ("the things they were suggesting would make me physically sick", True),
    ("Constant nausea since week 2 of the injections", True),
    ("ended up in A&E with pancreatitis", True),
    ("Crashes every 10s whenever I log a meal", False),
    ("Lost 6kg in 8 weeks, the coach is lovely", False),
])
def test_health_vocabulary(text, hit):
    assert bool(bs.HEALTH_TRIGGER_RE.search(text)) is hit


def test_health_is_a_risk_type_and_the_fallback_is_conservative():
    assert "adverse_health_effect" in bs.RISK_TYPES
    assert bs.PROMPT_VERSION.startswith("v2.2")
    assert [f["risk_type"] for f in bs.keyword_risk_fallback("they would make me physically sick")] == ["adverse_health_effect"]
    assert bs.keyword_risk_fallback("I felt sick of the notifications") == []


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *a, **k):
        return _Rows(self.rows)


def _run(monkeypatch, health):
    seen, stored = [], []

    async def fake_llm(title, summary, brand):
        seen.append(summary)
        return [{"risk_type": "adverse_health_effect", "severity": "medium", "confidence": 0.7,
                 "justification": "x"}]
    monkeypatch.setattr(bs, "llm_detect_risks", fake_llm)
    monkeypatch.setattr(bs, "store_article_risks", lambda conn, uri, bid, risks, m: stored.append(uri))
    monkeypatch.setattr(bs, "record_verdict", lambda *a, **k: None)
    rows = [("u1", "Google Play review (1/5)", "made me physically sick"),
            ("u2", "Google Play review (2/5)", "too many notifications")]
    flagged = asyncio.run(bos._risk_pass(_Conn(rows), {"id": 1, "display_name": "Oviva"},
                                         ["u1", "u2"], [10], health=health))
    return flagged, seen, stored


def test_app_reviews_reach_the_model_on_health_words(monkeypatch):
    flagged, seen, stored = _run(monkeypatch, health=True)
    assert flagged == 1 and seen == ["made me physically sick"] and stored == ["u1"]


def test_other_official_sources_keep_the_old_gate(monkeypatch):
    flagged, seen, stored = _run(monkeypatch, health=False)
    assert flagged == 0 and seen == []


def test_rule_recipients_are_added_without_duplicates():
    from app.services.brand_alert_service import _recipients_for
    cfg = {"email_recipients": ["a@x.com", "b@x.com"],
           "rules": {"health_side_effect": {"recipients": ["safety@client.com", "A@x.com"]}}}
    assert _recipients_for(cfg, "health_side_effect") == ["a@x.com", "b@x.com", "safety@client.com"]
    assert _recipients_for(cfg, "neg_social_spike") == ["a@x.com", "b@x.com"]
