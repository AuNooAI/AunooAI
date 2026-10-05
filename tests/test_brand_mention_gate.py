"""brand_mention_gate: real cases from the oviva site, 1 Oct 2026."""
import pytest

from app.services import brand_mention_gate as g

OVIVA = g.build_brand(
    "Oviva", ["Oviva", "Oviva AG", "Oviva app", "Oviva NHS"], [],
    {"mention_context": ["app", "NHS", "weight", "Abnehm*", "Unternehmen", "CEO",
                         "Gesundheit*", "digital*", "DiGA", "Ernährung*"],
     "exclude_context": ["antibiot*", "osteomyel*", "orthop*", "ortho-ID", "ortho ID",
                         "bone infection*", "OVIVA_OVIVA"]})
WW = g.build_brand("WeightWatchers", ["WeightWatchers", "Weight Watchers"], [],
                   {"non_press_domains": ["ww-recipes.net", "skinnytaste.com"]})


@pytest.mark.parametrize("text", [
    "was referred to Oviva, an NHS partner delivering weight-management programmes",
    "leitende Ernährungsberaterin bei der Abnehm-App „Oviva”.",
    "Kai Eberhardt (CEO und Co-Founder Oviva) zum Thema Künstliche Intelligenz",
])
def test_press_mentions_count(text):
    assert g.judge(OVIVA, text)["verdict"] == "named"


def test_mention_without_brand_context_is_weak():
    text = "Uncle Fred Oviva says he hopes the preservation will mean younger generations"
    assert g.judge(OVIVA, text)["verdict"] == "weak"


@pytest.mark.parametrize("text", [
    "Agree, although I think even with OVIVA and bone infection practice generally",
    "Another game changer in ortho ID from the group that brought you OVIVA",
    "@OVIVA_OVIVA Congratulations, OVIVA-san!!",
])
def test_same_name_subjects_are_excluded(text):
    assert g.judge(OVIVA, text)["verdict"] == "excluded"


def test_context_word_must_be_whole_word():
    # "happens" contains "app"; it must not count as brand context.
    assert g.judge(OVIVA, "whatever happens to Oviva in the novel")["verdict"] == "weak"


def test_lowercase_multiword_name_is_not_the_brand():
    assert g.judge(WW, "especially for weight watchers McDonald's wants")["verdict"] == "not_named"
    assert g.judge(OVIVA, "This oviva app that prescribed the HA to me")["verdict"] == "named"


def test_not_named():
    assert g.judge(OVIVA, "a story about lentils")["verdict"] == "not_named"


def test_non_press_domain_by_url_and_subdomain():
    assert g.judge(WW, "Weight Watchers chicken", "https://www.ww-recipes.net/x/")["verdict"] == "non_press"
    assert g.judge(WW, "", "https://blog.skinnytaste.com/y")["verdict"] == "non_press"
    assert g.judge(WW, "Weight Watchers shares fall", "https://www.reuters.com/a")["verdict"] == "named"


def test_apply_floor_and_zeroing(monkeypatch):
    monkeypatch.setattr(g, "brand_for_topic", lambda t, conn=None: {
        "Brand Monitoring Oviva": OVIVA, "Brand Monitoring WeightWatchers": WW}.get(t))
    monkeypatch.setenv("BW_BRAND_MENTION_FLOOR", "0.5")
    r = {"relevance_score": 0.1, "topic_alignment_score": 0.1}
    g.apply(r, "Brand Monitoring Oviva", {"title": "Eggs", "content": "Ernährungsberaterin bei der Abnehm-App Oviva"})
    assert r["topic_alignment_score"] == 0.5 and r["_brand_gate"] == "mention_floor"

    r = {"relevance_score": 0.8, "topic_alignment_score": 0.8}
    g.apply(r, "Brand Monitoring Oviva", {"title": "", "summary": "unlike OVIVA, this ortho-ID trial"})
    assert r["topic_alignment_score"] == 0.0 and r["_brand_gate"] == "excluded"

    r = {"relevance_score": 0.9, "topic_alignment_score": 0.9}
    g.apply(r, "Brand Monitoring WeightWatchers", {"uri": "https://ww-recipes.net/a", "title": "Weight Watchers soup"})
    assert r["topic_alignment_score"] == 0.0 and r["_brand_gate"] == "non_press"

    # A snippet that stops before the mention: the stored page decides.
    monkeypatch.setattr(g, "_stored_page", lambda uri: "Diätassistentin und Ernährungsberaterin bei Oviva. Das Unternehmen")
    r = {"relevance_score": 0.1, "topic_alignment_score": 0.1}
    g.apply(r, "Brand Monitoring Oviva", {"uri": "https://x/a", "title": "Yo-yo effect", "summary": "after the jab"})
    assert r["topic_alignment_score"] == 0.5 and r["_brand_gate"] == "mention_floor"
    monkeypatch.setattr(g, "_stored_page", lambda uri: "")

    # Off without the floor: a low score stays low.
    monkeypatch.delenv("BW_BRAND_MENTION_FLOOR")
    r = {"relevance_score": 0.1, "topic_alignment_score": 0.1}
    g.apply(r, "Brand Monitoring Oviva", {"content": "the Oviva app on the NHS"})
    assert r["topic_alignment_score"] == 0.1

    # A brand with no mention_context is never lifted (common-word names).
    monkeypatch.setenv("BW_BRAND_MENTION_FLOOR", "0.5")
    plain = g.build_brand("Second Nature", ["Second Nature"], [], {})
    monkeypatch.setattr(g, "brand_for_topic", lambda t, conn=None: plain)
    r = {"relevance_score": 0.1, "topic_alignment_score": 0.1}
    g.apply(r, "Brand Monitoring Second Nature", {"content": "drills you until it's second nature"})
    assert r["topic_alignment_score"] == 0.1

    # Not a brand topic: untouched.
    r = {"relevance_score": 0.2, "topic_alignment_score": 0.2}
    g.apply(r, "Quantum Computing", {"content": "the Oviva app on the NHS"})
    assert r == {"relevance_score": 0.2, "topic_alignment_score": 0.2}


def test_kept_mentions_sql_widens_the_name_filter():
    sql, params = g.kept_mentions_sql("AND (LOWER(a.title) LIKE :b0)", {"b0": "%oviva%"}, "Oviva")
    assert sql == ("AND ((LOWER(a.title) LIKE :b0) OR (a.topic = :_bmg_topic"
                   " AND a.overall_match_explanation LIKE :_bmg_mark))")
    assert params == {"b0": "%oviva%", "_bmg_topic": "Brand Monitoring Oviva",
                      "_bmg_mark": g.KEPT_MARK + "Oviva%"}
    assert g.kept_mentions_sql("", {}, "Oviva") == ("", {})


def test_kept_mention_evidence_parses_the_explanation():
    expl = g.KEPT_MARK + 'Oviva (subject score 0.10): "referred to Oviva, an NHS partner"'

    class _Conn:
        def execute(self, *_a, **_k):
            class _R:
                def fetchall(self_inner):
                    return [("u1", expl), ("u2", "Hybrid scoring: something else")]
            return _R()

    assert g.kept_mention_evidence(_Conn(), ["u1", "u2"]) == {
        "u1": {"brand": "Oviva", "snippet": "referred to Oviva, an NHS partner"}}
    assert g.kept_mention_evidence(_Conn(), []) == {}
