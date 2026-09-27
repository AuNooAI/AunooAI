"""Collection-side fixes from the aisocnews.com checks of 25 Sep 2026.

No database: each is a rule that failed quietly on live data.
"""

from __future__ import annotations

from app.collectors import xpoz_collector
from app.utils.title_translation import looks_english_text


def test_styled_english_is_english():
    """257 LinkedIn posts in 𝐛𝐨𝐥𝐝 letters were sent for translation, and
    came back with the vendor's name cut off the headline."""
    assert looks_english_text("Today, we are introducing 𝐂𝐃/𝐂𝐑: "
                              "𝐂𝐨𝐧𝐭𝐢𝐧𝐮𝐨𝐮𝐬 𝐃𝐞𝐭𝐞𝐜𝐭𝐢𝐨𝐧 for the SOC")
    assert not looks_english_text("Rusya Siber Savaşı İçin Üniversitelerde "
                                  "Nasıl Eğitim Veriyor")


def test_translation_keeps_the_vendor_prefix(monkeypatch):
    """The model dropped "Torq:" from "Torq: #FalCon2026, done."; the prefix
    now stays out of the call and goes back on afterwards."""
    from app.services import market_collect as mc
    from app.utils import title_translation as tt

    def fake(record, ai_model=None):
        record["original_summary"] = record["summary"]
        record["summary"] = "Our CTO spoke at CYBERFIRST'26."
        record["original_title"] = record["title"]
        record["title"] = "Our CTO spoke at CYBERFIRST'26."
        return True

    monkeypatch.setattr(tt, "english_fields", fake)
    written = {}

    class Conn:
        def execute(self, _sql, params):
            written.update(params)

    mc._translate_landed(Conn(), "u", "SOCNova: CTO'muz CYBERFIRST'26 "
                         "Etkinliği kapsamında konuştu",
                         "CTO'muz CYBERFIRST'26 Etkinliği kapsamında konuştu")
    assert written["title"].startswith("SOCNova: Our CTO")
    assert written["otitle"].startswith("SOCNova: CTO'muz")


def test_english_posts_are_not_sent_for_translation(monkeypatch):
    from app.services import market_collect as mc
    from app.utils import title_translation as tt

    called = []
    monkeypatch.setattr(tt, "english_fields",
                        lambda *a, **k: called.append(1) or True)
    mc._translate_landed(object(), "u", "Torq: #FalCon2026, done.",
                         "#FalCon2026, done. Thanks to everyone who came by "
                         "and saw the team.")
    assert not called


def test_reddit_can_have_its_own_timeout(monkeypatch):
    monkeypatch.setenv("XPOZ_PLATFORM_TIMEOUT", "25")
    monkeypatch.setenv("XPOZ_REDDIT_TIMEOUT", "45")
    assert xpoz_collector._platform_timeout("reddit") == 45.0
    assert xpoz_collector._platform_timeout("twitter") == 25.0


def test_only_a_start_failure_is_retried():
    class OperationFailedError(Exception):
        pass

    assert xpoz_collector._is_start_failure(OperationFailedError(
        "Operation  failed: Failed to start operation"))
    assert not xpoz_collector._is_start_failure(OperationFailedError("quota"))
    assert not xpoz_collector._is_start_failure(ValueError(
        "Failed to start operation"))


def test_the_writing_check_asks_one_question_per_field():
    from app.services import market_post_review as mpr

    q = mpr._check_questions({"kind": "customer", "headline": "H", "summary": "S",
                              "customer": {"name": "Acme"}})
    assert set(q) == {"is_news", "kind", "headline", "summary", "customer",
                      "actor", "summary_on_event"}
    assert set(q["headline"]["criteria"]) == {"supports", "contradicts", "says_nothing"}
    assert set(q["kind"]["criteria"]) == set(mpr.KIND_CRITERIA)
    # No writing and no customer: only the reading is checked.
    assert set(mpr._check_questions({"kind": "launch"})) == {"is_news", "kind"}
    assert mpr._written("  null ", 200) is None
    assert mpr._written('"Torq launches Auto Triage"', 200) == "Torq launches Auto Triage"


def test_no_jev_means_no_check(monkeypatch):
    from app.services import market_post_review as mpr

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert mpr.check_one("post", {"kind": "launch", "headline": "H"}) is None
    assert not mpr.passes(None, "headline")


def test_a_social_post_is_hidden_only_when_jev_turned_it_away():
    from app.services import market_post_review as mpr

    assert mpr.social_passes({"review_check": None})
    assert mpr.social_passes({"review_check": {"social": {"on_topic": 0.9, "substance": 0.8}}})
    assert not mpr.social_passes({"review_check": {"social": {"on_topic": 0.1, "substance": 0.9}}})
    assert not mpr.social_passes({"review_check": {"social": {"on_topic": 0.9, "substance": 0.2}}})
    q = mpr._social_questions("AI in the SOC", ["AI SOC"])
    assert set(q) == {"on_topic", "substance", "self_promotion"}
    assert not mpr.social_passes({"review_check": {"social": {
        "on_topic": 0.9, "substance": 0.9, "self_promotion": 0.8}}})


def test_the_checker_is_told_who_published_the_post_and_checks_roles():
    from app.services import market_post_review as mpr

    q = mpr._check_questions({"kind": "customer", "headline": "H", "summary": "S",
                              "customer": {"name": "Acme"}})
    assert {"actor", "summary_on_event"} <= set(q)
    assert "publisher" in q["actor"]["instructions"]
    assert "publisher" in q["customer"]["instructions"]
    # A headline that failed the actor check is not shown.
    check = {"headline": {"verdict": "supports", "p_supports": 0.95}, "actor": 0.2}
    assert not mpr.passes(check, "headline")
    check = {"summary": {"verdict": "supports", "p_supports": 0.95}, "summary_on_event": 0.3}
    assert not mpr.passes(check, "summary")
    assert not mpr.passes({"headline": {"verdict": "supports", "p_supports": 0.95},
                           "exact": ["the headline gives 47, which the post does not state"]},
                          "headline")


def test_a_company_promoting_itself_is_hidden_from_social():
    from app.services import market_post_review as mpr

    assert not mpr.social_passes({"review_check": {"social": {
        "on_topic": 0.9, "substance": 0.8, "self_promotion": 0.9}}})
