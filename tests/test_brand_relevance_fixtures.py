"""Reported cases from 2026-10-06, captured read-only from the sunstar and oviva
databases (tests/fixtures/brand_relevance/captured_2026-10-06.json), run
through the brand decision with the sites' real profiles plus the reviewed
additions in eval/brand_relevance/profiles/. The judge is a fake that always
answers "passing", the worst case, so only what rules decide is asserted:
headlines, collisions, exclusions, ownership and where no judge is called."""
import importlib.util
import json
import os

import pytest

from app.services import brand_decision as bd
from app.services import brand_profile as bp

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
CAPTURE = json.load(open(os.path.join(HERE, "fixtures", "brand_relevance", "captured_2026-10-06.json")))


def _apply_mod():
    spec = importlib.util.spec_from_file_location("bpa", os.path.join(ROOT, "scripts", "brand_profile_apply.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _profiles(site, with_additions=True):
    rows = {r["display_name"]: dict(r) for r in CAPTURE["brands"][site]}
    if with_additions:
        add = json.load(open(os.path.join(ROOT, "eval", "brand_relevance", "profiles", f"{site}.json")))
        mod = _apply_mod()
        for name, spec in add["brands"].items():
            if name not in rows:
                continue
            for col, (new, _) in mod.plan_for(rows[name], spec).items():
                rows[name][col] = new
    return list(rows.values())


def _passing():
    calls = []

    def j(profile, article, mention, quality):
        calls.append(article.get("uri"))
        return "passing", "fake judge", "fake"
    j.route = "llm:fake"
    j.calls = calls
    return j


def _decide(site, row, topic_relevant=True, with_additions=True):
    res = bp.resolve(_profiles(site, with_additions), row["topic"])
    judge = _passing()
    d = bd.decide(res, row, judges=(judge,), topic_scorer=lambda a: topic_relevant)
    return d, judge


def _rows(case):
    rows = CAPTURE["cases"][case]["rows"]
    if not rows:
        pytest.skip(f"no captured rows for {case}")
    return CAPTURE["cases"][case]["site"], rows


def test_lion_japanese_items_are_recognised_with_the_profile_filled_in():
    """Headline mentions are coverage by rule; body mentions reach the judge
    (with the fake judge they come back 'passing', so only the mention is
    asserted for those)."""
    site, rows = _rows("lion_japanese_coverage")
    for r in rows:
        d, judge = _decide(site, r)
        m = d.evidence.get("mention")
        assert m in ("title", "body"), (r["title"], m)
        if m == "title":
            assert d.earned, (r["title"], d.brand_relation)
        else:
            assert judge.calls, r["title"]


def test_lion_clinica_advert_misses_with_todays_profile():
    """The reason the profile step exists: today's Lion row lists only
    'Clinica toothpaste', so the Japanese advert is not a verified mention."""
    site, rows = _rows("lion_japanese_coverage")
    ad = [r for r in rows if "クリニカ" in (r["original_title"] or "") + (r["title"] or "")]
    if not ad:
        pytest.skip("advert not captured")
    d, judge = _decide(site, ad[0], with_additions=False)
    assert d.evidence.get("mention") not in ("title", "body") and judge.calls == []


def test_colgate_company_headlines_are_coverage_even_when_judged_passing():
    """Independent outlets: earned. The company's own investor site: owned,
    as the spec requires for the brand's own content (the dividend notice
    appears twice, once on investor.colgatepalmolive.com, once on Business Wire)."""
    site, rows = _rows("colgate_company_news")
    for r in rows:
        d, judge = _decide(site, r)
        if d.evidence.get("mention") == "body":
            assert judge.calls, r["title"]   # headline does not name it: the judge decides
            continue
        assert d.brand_relation in ("subject", "notable"), (r["title"], d.brand_relation)
        if "colgatepalmolive.com" in r["uri"]:
            assert d.source_relation == "owned" and not d.earned
        else:
            assert d.earned, (r["uri"], d.source_relation)


def test_colgate_university_sport_is_not_coverage_and_needs_no_model():
    site, rows = _rows("colgate_university_collision")
    for r in rows:
        d, judge = _decide(site, r)
        assert d.brand_relation == "other" and d.provenance == "rule" and judge.calls == [], (r["title"], d.evidence)


@pytest.mark.parametrize("case,kind", [("colgate_deal_listing", "deal_listing"),
                                       ("colgate_valuation_page", "valuation_page"),
                                       ("ww_fan_recipes", "non_press")])
def test_excluded_pages_are_not_coverage(case, kind):
    site, rows = _rows(case)
    for r in rows:
        d, judge = _decide(site, r)
        assert (d.brand_relation, d.provenance, d.evidence.get("exclusion")) == ("other", "rule", kind), r["title"]
        assert judge.calls == []


def test_haleon_japanese_product_headline_is_coverage():
    site, rows = _rows("haleon_japan_product")
    for r in rows:
        d, _ = _decide(site, r)
        assert d.earned, (r["title"], d.evidence)


def test_phantom_matches_never_reach_the_brand_judge():
    site, rows = _rows("japan_phantom_match")
    for r in rows:
        d, judge = _decide(site, r, topic_relevant=False)
        assert judge.calls == [] and not d.earned and d.provenance in ("topic_scorer", "rule"), r["title"]


def test_ww_company_news_is_earned():
    site, rows = _rows("ww_company_news")
    for r in rows:
        d, _ = _decide(site, r)
        assert d.earned, (r["title"], d.evidence)


def test_oviva_own_pages_are_owned_never_earned():
    site, rows = _rows("oviva_owned_content")
    for r in rows:
        d, _ = _decide(site, r)
        assert d.source_relation == "owned" and not d.earned, r["uri"]


def test_oviva_sector_stories_are_sector_not_earned():
    site, rows = _rows("oviva_sector_story")
    for r in rows:
        d, judge = _decide(site, r)
        if d.evidence.get("mention") in ("title", "body"):
            continue  # names Oviva in its text after all; the judge decides
        assert d.brand_relation == "sector" and not d.earned and judge.calls == [], r["title"]


def test_same_name_entities_are_rejected_by_rule_without_a_model():
    """The SunStar Philippines newspaper and Colgate University (colgate.edu):
    rule decisions, no judge call (6 Oct rejection probe)."""
    site, rows = _rows("sunstar_same_name_rejections")
    for r in rows:
        d, judge = _decide(site, r)
        assert d.brand_relation == "other" and d.provenance == "rule" and judge.calls == [], (r["title"], d.evidence)
