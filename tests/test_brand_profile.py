"""brand_profile: one effective profile per brand, topic resolution, and the
deterministic checks (mention, ownership, exclusions, evidence quality).
Cases are taken from the 2026-10-06 Sunstar and Oviva reviews. No database."""

import pytest

from app.services import brand_profile as bp


def _row(id_, display, kw=(), products=(), **cfg):
    return {"id": id_, "name": display.lower().replace(" ", "-"), "display_name": display,
            "brand_keywords": list(kw), "product_keywords": list(products), "config": cfg, "enabled": True}


LION = _row(2, "Lion Corporation", kw=["Lion Corp", "ライオン株式会社", "LION"],
            products=["クリニカ", "Clinica", "システマ", "Systema", "ブリリアントモア", "NONIO"],
            original_names=["ライオン", "ライオン歯科材"], ambiguous_aliases=["LION", "Lion"],
            exclude_context=["Lionsgate", "sea lion", "シーライオン"], owned_domains=["lion.co.jp"])
COLGATE = _row(5, "Colgate-Palmolive", kw=["Colgate"], products=["Colgate Total", "elmex", "meridol"],
               exclude_context=["university", "Raiders", "football", "basketball", "lacrosse", "Hail Mary"],
               owned_domains=["colgate.com", "colgatepalmolive.com"])
WW = _row(9, "WeightWatchers", kw=["Weight Watchers", "WW International"],
          non_press_domains=["ww-recipes.net"], owned_domains=["weightwatchers.com", "ww.com"])
OVIVA = _row(1, "Oviva", kw=["Oviva AG"], mention_context=["app", "NHS", "Adipositas", "weight", "diabetes", "digital"],
             exclude_context=["antibiot*", "osteomyel*", "bone and joint"], owned_domains=["oviva.com"])


def _p(row):
    return bp.build_profile(row)


# ── Mentions ────────────────────────────────────────────────────────────────

def test_japanese_product_in_headline_is_a_title_mention():
    m = bp.detect_mention(_p(LION), {"title": "【上戸彩】LION「クリニカ」新CM出演！"})
    assert m.status == "title" and m.alias == "クリニカ"


def test_japanese_company_name_matches_inside_a_longer_word():
    m = bp.detect_mention(_p(LION), {"title": "ライオン歯科材、プロフェッショナルケア用PMTCペースト「Brilliant PMTC」などを歯科医院に向けて発売"})
    assert m.status == "title"


def test_short_ambiguous_alias_alone_is_weak_not_verified():
    m = bp.detect_mention(_p(LION), {"title": "LION wins again", "summary": "The football club LION wins the cup."})
    assert m.status == "weak" and not m.verified


def test_same_name_collision_in_headline():
    m = bp.detect_mention(_p(COLGATE), {"title": "Harvard football outsmarts Colgate on Hail Mary attempt"})
    assert m.status == "same_name" and not m.verified


def test_real_colgate_headline_is_verified():
    m = bp.detect_mention(_p(COLGATE), {"title": "Colgate-Palmolive explores sale of three personal care brands in $1 bn deal"})
    assert m.status == "title" and m.alias in ("Colgate-Palmolive", "Colgate")


def test_lowercase_multiword_name_is_the_phrase_not_the_company():
    m = bp.detect_mention(_p(WW), {"title": "McDonald's menu tips", "summary": "A guide for weight watchers on a budget."})
    assert m.status == "none"
    m2 = bp.detect_mention(_p(WW), {"title": "Weight Watchers files for bankruptcy"})
    assert m2.status == "title"


def test_body_mention_with_required_context():
    art = {"title": "What comes after the weight loss injection?",
           "summary": "Dietitian at Oviva, the digital weight programme used by the NHS, explains."}
    assert bp.detect_mention(_p(OVIVA), art).status == "body"


def test_context_required_and_missing_is_weak():
    art = {"title": "Museum notes", "summary": "Uncle Fred Oviva donated the clock in 1921."}
    assert bp.detect_mention(_p(OVIVA), art).status == "weak"


def test_exclude_beside_mention_is_same_name_and_both_is_ambiguous():
    trial = {"title": "OVIVA trial: oral antibiotics for bone and joint infection", "summary": "Results of OVIVA."}
    assert bp.detect_mention(_p(OVIVA), trial).status == "same_name"
    both = {"title": "Oviva", "summary": "Oviva app on the NHS; also the OVIVA antibiotics trial."}
    assert bp.detect_mention(_p(OVIVA), both).status == "ambiguous"


def test_collision_phrase_from_news_keyword_excludes():
    row = _row(7, "Wiley", kw=["John Wiley & Sons"], news_keyword_excludes=["Wiley College", "Wiley University"])
    m = bp.detect_mention(_p(row), {"title": "Wiley College wins accreditation"})
    assert m.status == "same_name"


def test_full_width_latin_normalises():
    m = bp.detect_mention(_p(COLGATE), {"title": "Ｃｏｌｇａｔｅ results beat estimates"})
    assert m.status == "title"


def test_nothing_named():
    assert bp.detect_mention(_p(LION), {"title": "Toothpaste market grows 4%"}).status == "none"


def test_extract_keeps_original_casing():
    m = bp.detect_mention(_p(COLGATE), {"title": "x", "summary": "Analysts at Barclays met Colgate-Palmolive management."})
    assert "Colgate-Palmolive" in m.extract


# ── Ownership ───────────────────────────────────────────────────────────────

def test_owned_domain_with_boundary():
    p = _p(OVIVA)
    assert bp.source_relation(p, {"uri": "https://oviva.com/uk/blog/tuna"})[0] == "owned"
    assert bp.source_relation(p, {"uri": "https://www.oviva.com/x"})[0] == "owned"
    assert bp.source_relation(p, {"uri": "https://blog.oviva.com/x"})[0] == "owned"
    assert bp.source_relation(p, {"uri": "https://notoviva.com/x"})[0] == "independent"
    assert bp.source_relation(p, {"uri": "https://oviva.com.evil.net/x"})[0] == "independent"


def test_one_uri_owned_for_a_independent_for_b():
    art = {"uri": "https://www.colgate.com/en-us/news/launch"}
    assert bp.source_relation(_p(COLGATE), art)[0] == "owned"
    assert bp.source_relation(_p(LION), art)[0] == "independent"


def test_legacy_owned_tag_only_counts_for_its_own_brand():
    art = {"uri": "https://smartbear.com/blog/x", "bias_source": "owned:smartbear.com"}
    sb = _p(_row(30, "SmartBear", owned_domains=["smartbear.com"]))
    assert bp.source_relation(sb, art)[0] == "owned"
    assert bp.source_relation(_p(COLGATE), art)[0] == "independent"


def test_no_host_is_unknown():
    assert bp.source_relation(_p(COLGATE), {"uri": "", "news_source": "Reuters"})[0] == "unknown"


def test_registry_domains_join_the_profile():
    p = bp.build_profile(COLGATE, registry_domains=["colgate.co.uk"])
    assert bp.source_relation(p, {"uri": "https://colgate.co.uk/x"})[0] == "owned"


# ── Exclusions ──────────────────────────────────────────────────────────────

def test_fan_recipe_site_is_non_press():
    kind, _ = bp.exclusion(_p(WW), {"uri": "https://ww-recipes.net/fish-pie", "title": "Weight Watchers Fish Pie recipe"})
    assert kind == "non_press"


def test_valuation_pages_are_excluded_and_reporting_is_not():
    for t in ("CL DCF Analysis: Intrinsic Value $44 vs Price $88", "CL Looks 8.5% Undervalued on GF Value™"):
        assert bp.exclusion(_p(COLGATE), {"uri": "https://www.gurufocus.com/x", "title": t})[0] == "valuation_page"
    for t in ("Colgate-Palmolive Declares Regular Quarterly Dividend",
              "Colgate-Palmolive explores sale of three personal care brands",
              "Here's Why WeightWatchers (WW) Rose in Q4"):
        assert bp.exclusion(_p(COLGATE), {"uri": "https://www.reuters.com/x", "title": t}) is None


def test_deal_listing_is_excluded():
    ex = bp.exclusion(_p(COLGATE), {"uri": "https://slickdeals.net/f/1", "title": "4-Pk 5.1-Oz Colgate Total Active Prevention Whitening Gel Toothpaste"})
    assert ex is not None and ex[0] == "deal_listing"


# ── Resolution and versioning ───────────────────────────────────────────────

def test_resolves_both_topic_naming_forms():
    rows = [LION, COLGATE]
    assert bp.resolve(rows, "Brand Monitoring Lion Corporation").profile.brand_id == 2
    assert bp.resolve(rows, "Colgate-Palmolive - Brand Watch").profile.brand_id == 5


def test_duplicate_profiles_defer_with_a_visible_error():
    dup = _row(99, "Lion Corporation")
    r = bp.resolve([LION, dup], "Brand Monitoring Lion Corporation")
    assert r.profile is None and r.brand_topic and "2 enabled brands" in r.error


def test_group_pin_wins_over_name():
    pinned = _row(50, "Lion Corporation JP", group_ids=[14])
    r = bp.resolve([LION, pinned], "Brand Monitoring Lion Corporation", group_id=14)
    assert r.profile.brand_id == 50


def test_theme_topic_is_not_a_brand_topic():
    r = bp.resolve([LION], "Oral Health & Whole-Body Health - Japan")
    assert r.profile is None and not r.brand_topic and r.error is None


def test_profile_version_changes_with_rules_not_with_order():
    a = bp.build_profile(_row(5, "Colgate-Palmolive", kw=["Colgate", "CL"]))
    b = bp.build_profile(_row(5, "Colgate-Palmolive", kw=["CL", "Colgate"]))
    c = bp.build_profile(_row(5, "Colgate-Palmolive", kw=["Colgate"]))
    assert a.version == b.version != c.version


def test_collection_terms_skip_short_and_ambiguous_aliases():
    terms = _p(LION).collection_terms()
    assert "LION" not in terms and "Lion" not in terms
    assert "ライオン株式会社" in terms and "Clinica" in terms


# ── Evidence quality ────────────────────────────────────────────────────────

@pytest.mark.parametrize("art,q", [
    ({"title": "T", "content": "body text"}, "full"),
    ({"title": "T", "summary": "a summary"}, "summary"),
    ({"title": "Colgate-Palmolive seeks to divest", "summary": "Colgate-Palmolive seeks to divest"}, "title_only"),
    ({"title": "T"}, "title_only"),
])
def test_evidence_quality(art, q):
    assert bp.evidence_quality(art) == q
