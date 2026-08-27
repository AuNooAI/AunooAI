"""The findings-first layer: developments, observation states, findings.

Every test here runs on constructed rows and no database, because each rule
under test is one that would fail silently on live data — a paused vendor
counted as "monitored, nothing changed", four posts about one acquisition
counted as four acquisitions, a job-seeker's post counted as a market event.
The database-backed render tests in ``test_market_report_copy`` check that
the real report still carries the structure; these check the rules.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import market_assessment as ma

NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


def _vendor(name="Radiant Security", brand_id=7):
    return {"brand_id": brand_id, "vendor": name}


def _candidate(kind, title, *, date="2026-08-19", vendors=None, summary="",
               voice="independent", source_type="news", key=None, uri=None,
               seed=True, social=False):
    uri = uri or f"https://example.test/{abs(hash(title))}"
    return {
        "key": f"corpus:{uri}", "event_type": kind, "date": date,
        "vendors": vendors if vendors is not None else [_vendor()],
        "headline": title, "summary": summary, "seed": seed,
        "evidence": [{"uri": uri, "title": title, "source": source_type,
                      "voice": voice, "social": social,
                      "source_type": source_type,
                      "key": key or f"{voice}:{uri}"}],
    }


# ---------------------------------------------------------------------------
# Event deduplication
# ---------------------------------------------------------------------------

def test_four_records_of_one_acquisition_become_one_development():
    """Four posts about Cribl acquiring Radiant are one event with four
    evidence records, not four developments."""
    release = _candidate(
        "acquisition", "Cribl Advances AI-Powered Security Operations with "
        "New AI SOC Acquisition",
        summary="Cribl acquired technology assets from Radiant Security to "
                "add AI-driven triage and investigation capabilities.",
        key="domain:globenewswire.com")
    tweet = _candidate(
        "acquisition", "Cribl buys Radiant Security's AI SOC tech in second "
        "security deal of 2026", date="2026-08-19", seed=False, social=True,
        source_type="social", key="social:x:duncanriley")
    reddit = _candidate(
        "acquisition", "Cribl acquires AI SOC technology assets from Radiant "
        "Security.", date="2026-08-19", seed=False, social=True,
        source_type="social", key="social:reddit:camilian")
    unattributed = _candidate(
        "acquisition", "Cribl advances with AI SOC technology acquisition",
        date="2026-08-23", vendors=[], seed=False, social=True,
        source_type="social", key="social:bluesky:shepherd")
    devs = ma.dedupe([release, tweet, reddit, unattributed])
    assert len(devs) == 1
    assert len(devs[0]["evidence"]) == 4
    finished = ma.finish(devs[0])
    assert finished["source_count"] == 4
    assert finished["provenance"] == "multiple_independent_sources"
    # The event's date is the earliest record, not a repost days later.
    assert finished["date"] == "2026-08-19"


def test_two_launches_by_one_vendor_in_one_week_stay_separate():
    a = _candidate("product_launch", "Introducing Imperum Agent Studio.",
                   vendors=[_vendor("Imperum", 3)], date="2026-08-21",
                   summary="Agent Studio lets analysts compose agents.",
                   voice="owned", source_type="vendor")
    b = _candidate("product_launch", "Introducing Imperum-CybersecurityLLM v1.0.",
                   vendors=[_vendor("Imperum", 3)], date="2026-08-24",
                   summary="A language model trained on security data.",
                   voice="owned", source_type="vendor")
    assert len(ma.dedupe([a, b])) == 2


def test_records_about_different_vendors_never_merge():
    a = _candidate("product_launch", "Meet Armor Detect, our detection "
                   "engineering agent", vendors=[_vendor("Arambh Labs", 1)])
    b = _candidate("product_launch", "Introducing our detection engineering "
                   "agent", vendors=[_vendor("Imperum", 2)])
    assert len(ma.dedupe([a, b])) == 2


def test_an_unattributed_post_cannot_seed_a_development():
    """A tweet naming nobody we track attaches to an event or is dropped."""
    only = _candidate("acquisition", "Some company acquires another company",
                      vendors=[], seed=False, social=True)
    assert ma.dedupe([only]) == []


# ---------------------------------------------------------------------------
# Noise filtering and classification
# ---------------------------------------------------------------------------

def _record(title, *, article_class="discussion", summary="", vendors=None,
            review_verdict=None, review_kind=None):
    return {"uri": "https://x.test/1", "title": title, "summary": summary,
            "article_class": article_class,
            "vendors": vendors if vendors is not None else [_vendor()],
            "review_verdict": review_verdict, "review_kind": review_kind,
            "news_source": "xpoz:twitter", "social_meta": {}}


def test_a_job_seeker_post_mentioning_soc_is_not_a_development():
    assert ma.classify_record(_record(
        "SOC Analyst / Cybersecurity grad looking for opportunities "
        "(Rabat or remote). Recently deployed a home lab.",
        article_class="news")) is None
    assert ma.classify_record(_record(
        "[FOR HIRE] SOC monitoring services, $15/h, fast turnaround. "
        "Launching my freelance practice.", article_class="news")) is None


def test_a_training_completion_post_is_not_a_development():
    assert ma.classify_record(_record(
        "I just completed SOC L1 Alert Triage room on TryHackMe! Partnering "
        "with my mentor on the next one.", article_class="news")) is None


def test_a_market_size_report_is_not_a_development():
    assert ma.classify_record(_record(
        "SOC Automation Market Size to reach $9.4B by 2031, CAGR 14%. "
        "Leading vendors launch new platforms.", article_class="news")) is None


def test_a_reviewed_vendor_launch_post_is_a_development():
    rec = _record("Radiant Security: Introducing Citations, the newest "
                  "addition to the Radiant platform!", article_class="social",
                  review_verdict="signal", review_kind="launch")
    assert ma.classify_record(rec) in ("product_launch", "product_expansion")


def test_a_vendor_post_the_review_called_noise_is_not_a_development():
    rec = _record("Radiant Security: Introducing our new booth at RSA!",
                  article_class="social", review_verdict="noise",
                  review_kind="event")
    assert ma.classify_record(rec) is None


def test_practitioner_social_never_seeds_a_development():
    rec = _record("Cribl acquires Radiant Security's AI SOC tech",
                  article_class="discussion")
    assert ma.classify_record(rec) is None
    # ...but the same words classify for attachment as evidence.
    assert ma.classify_text(rec["title"]) == "acquisition"


def test_a_web_page_needs_the_headline_to_say_so():
    """A vendor's explainer mentions launching and deploying in its body and
    is neither. Only ownership and money events are read from the body."""
    explainer = _record("What is Agentic Security? Everything You Should Know",
                        article_class="vendor",
                        summary="Vendors launch agents that deploy across the "
                                "SOC and partner with SIEMs.")
    assert ma.classify_record(explainer) is None
    raise_page = _record("Our story", article_class="vendor",
                         summary="Last year we raised $30M in a Series A led "
                                 "by Accel.")
    assert ma.classify_record(raise_page) == "funding"


def test_a_launch_by_an_untracked_company_is_not_a_vendor_move():
    rec = _record("Palo Alto Networks launches a new SOC platform",
                  article_class="news", vendors=[])
    assert ma.classify_record(rec) is None


def test_a_junior_welcome_post_is_not_an_executive_appointment():
    junior = _record("Twine Security: Welcome to the team, Helgo!",
                     article_class="social", review_verdict="signal",
                     review_kind="hiring")
    assert ma.classify_record(junior) is None
    senior = _record("Twine Security: We are thrilled to welcome Jarrod as "
                     "our new Vice President of Sales", article_class="social",
                     review_verdict="signal", review_kind="hiring")
    assert ma.classify_record(senior) == "executive_appointment"


def test_a_headline_that_is_not_one_falls_back_to_the_body():
    """The same rule the Findings tab applies, so the two agree."""
    head = ma.headline_of({
        "title": "Kamal Shah: Prophet Security’s Post",
        "summary": "What do you do when a zero day lands? Prophet AI builds "
                   "a hunt.",
        "vendors": [_vendor("Prophet Security")]})
    assert head == "What do you do when a zero day lands?"
    # The vendor prefix comes off, and so does a web page's site suffix.
    assert ma.headline_of({"title": "Crogl: Crogl ships a connector",
                           "vendors": [_vendor("Crogl")]}) == "Crogl ships a connector"
    assert ma.headline_of({"title": "Prophet Raises $30M | Prophet Security",
                           "vendors": [_vendor("Prophet Security")]}) \
        == "Prophet Raises $30M"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def test_a_vendor_announcement_with_no_independent_source_is_vendor_only():
    dev = ma.finish(ma.dedupe([_candidate(
        "product_launch", "Introducing Citations", voice="owned",
        source_type="vendor", key="owned:linkedin:7")])[0])
    assert dev["provenance"] == "vendor_source_only"
    assert dev["provenance_label"] == "Vendor source only"


def test_a_vendor_announcement_plus_one_outside_report_is_independently_reported():
    own = _candidate("partnership", "We've partnered with Anthropic",
                     voice="owned", source_type="vendor", key="owned:linkedin:7",
                     summary="Closed access to Mythos for our detection work.")
    press = _candidate("partnership", "Radiant partners with Anthropic on "
                       "Mythos access", key="domain:securityweek.com",
                       summary="Radiant Security has partnered with Anthropic.")
    dev = ma.finish(ma.dedupe([own, press])[0])
    assert dev["provenance"] == "independently_reported"
    assert dev["provenance_label"] == "Also reported independently"


def test_three_records_from_one_publisher_are_one_source():
    rows = [_candidate("acquisition", f"Cribl acquires Radiant, take {i}",
                       key="domain:onepublisher.com",
                       summary="Cribl acquired Radiant Security's assets.")
            for i in range(3)]
    assert ma.provenance_of([r["evidence"][0] for r in rows]) == \
        "independently_reported"


def test_provenance_never_claims_verification():
    for label in ma.PROVENANCE_LABELS.values():
        assert "verified" not in label.lower()
        assert "confirmed" not in label.lower()
        assert "corroborated" not in label.lower()


# ---------------------------------------------------------------------------
# Observation states
# ---------------------------------------------------------------------------

def _policy(source, *, success_ago_days=1, failures=0, eligible=True,
            enabled=True, cadence=86400, attempted=True):
    last = NOW - timedelta(days=success_ago_days) if success_ago_days is not None else None
    return {"source": source, "enabled": enabled, "eligible": eligible,
            "ineligible_reason": None if eligible else "no identifier",
            "cadence_seconds": cadence,
            "last_attempt_at": (last or NOW) if attempted else None,
            "last_success_at": last, "consecutive_failures": failures}


REQUIRED = ("linkedin_company_post", "vendor_web")


def _state(vendor, policies, has_change=False):
    return ma.observation_state_for(
        vendor, {p["source"]: p for p in policies}, required=REQUIRED,
        now=NOW, days=30, has_change=has_change)[0]


def test_a_paused_vendor_with_nothing_collected_is_paused_not_quiet():
    state = _state({"collection_enabled": False}, [])
    assert state == "paused"
    assert state != "monitored_no_material_change"


def test_a_vendor_whose_required_source_failed_is_not_quiet():
    state = _state({"collection_enabled": True}, [
        _policy("linkedin_company_post"),
        _policy("vendor_web", failures=2)])
    assert state == "incomplete_coverage"


def test_a_vendor_whose_required_source_was_never_collected_is_not_quiet():
    state = _state({"collection_enabled": True}, [
        _policy("linkedin_company_post"),
        _policy("vendor_web", success_ago_days=None)])
    assert state == "incomplete_coverage"


def test_a_vendor_missing_a_required_source_entirely_is_not_quiet():
    state = _state({"collection_enabled": True}, [
        _policy("linkedin_company_post")])
    assert state == "incomplete_coverage"


def test_a_vendor_read_before_the_period_is_not_quiet():
    state = _state({"collection_enabled": True}, [
        _policy("linkedin_company_post", success_ago_days=45),
        _policy("vendor_web")])
    assert state == "incomplete_coverage"


def test_a_fully_read_vendor_with_no_development_is_quiet():
    state = _state({"collection_enabled": True}, [
        _policy("linkedin_company_post"), _policy("vendor_web")])
    assert state == "monitored_no_material_change"


def test_a_vendor_with_a_development_is_a_material_change_whatever_its_sources():
    state = _state({"collection_enabled": True}, [
        _policy("vendor_web", failures=3)], has_change=True)
    assert state == "material_change"


def test_a_vendor_nothing_has_ever_tried_to_read_is_not_yet_collected():
    state = _state({"collection_enabled": True}, [
        _policy("linkedin_company_post", success_ago_days=None, attempted=False)])
    assert state == "not_yet_collected"


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

def _dev(kind, vendor, *, provenance="vendor_source_only", n=1):
    return {"event_id": f"{kind}:{vendor}:{n}", "event_type": kind,
            "event_type_label": ma.EVENT_TYPES[kind], "date": "2026-08-19",
            "vendors": [{"brand_id": hash(vendor) % 1000, "vendor": vendor}],
            "headline": f"{vendor} {kind} {n}", "provenance": provenance,
            "provenance_label": ma.PROVENANCE_LABELS[provenance],
            "independent_source_count": 0 if provenance == "vendor_source_only" else 1,
            "source_count": 1, "importance": "medium"}


def _collection(successful, eligible):
    return {"coverage": {"successful": successful, "eligible": eligible}}


def _inputs(devs, *, post_share=1.0, hiring=None):
    return {"days": 30, "developments": devs,
            "distribution": ma.distribution(devs),
            "observation": {"counts": {"monitored_no_material_change": 10,
                                       "incomplete_coverage": 2}},
            "hiring": hiring or {}, "registry_total": 40,
            "post_collection": _collection(int(40 * post_share), 40),
            "jobs_collection": _collection(30, 40)}


def test_no_market_comparison_is_made_below_the_coverage_threshold():
    """Twenty launches against two customers is a fact about our collection
    when we only read a third of the vendors' channels. The template that
    compares them across the market must stay silent."""
    devs = ([_dev("product_launch", f"V{i}", n=i) for i in range(6)]
            + [_dev("customer", "V1")])
    thin = ma.candidate_findings(_inputs(devs, post_share=0.3))
    assert not any(f["id"] == "product_vs_customer" for f in thin)
    # The observed-mix finding that replaces it says what it counts.
    assert any(f["id"] == "dominant_kind" for f in thin)
    full = ma.candidate_findings(_inputs(devs, post_share=0.9))
    assert any(f["id"] == "product_vs_customer" for f in full)


def test_hiring_concentration_needs_enough_roles_and_vendors():
    thin = {"openings": 6, "by_vendor": [
        {"vendor": "A", "openings": 5}, {"vendor": "B", "openings": 1}]}
    assert not any(f["id"] == "hiring_concentration"
                   for f in ma.candidate_findings(_inputs([], hiring=thin)))
    enough = {"openings": 40, "by_vendor": [
        {"vendor": "A", "openings": 24}, {"vendor": "B", "openings": 10},
        {"vendor": "C", "openings": 6}]}
    hits = [f for f in ma.candidate_findings(_inputs([], hiring=enough))
            if f["id"] == "hiring_concentration"]
    assert hits and "of 40 vendors" in hits[0]["coverage"]
    assert "24" in hits[0]["body"] and "A" in hits[0]["body"]


def test_absence_of_funding_is_never_a_finding():
    devs = [_dev("product_launch", f"V{i}", n=i) for i in range(6)]
    for f in ma.candidate_findings(_inputs(devs)):
        assert "no funding" not in f["headline"].lower()
        assert "no funding" not in f["body"].lower()


def test_an_acquisition_is_always_a_finding_and_cites_its_development():
    acq = _dev("acquisition", "Radiant Security",
               provenance="multiple_independent_sources")
    out = ma.candidate_findings(_inputs([acq]))
    hit = next(f for f in out if f["id"] == "consolidation")
    assert acq["event_id"] in hit["developments"]
    # Full coverage: nothing to qualify, so no line. Thin coverage: one.
    assert hit["coverage"] == ""
    thin = ma.candidate_findings(_inputs([acq], post_share=0.5))
    assert "not the whole registry" in next(
        f for f in thin if f["id"] == "consolidation")["coverage"]


def test_findings_stay_between_zero_and_six_and_carry_coverage():
    devs = ([_dev("product_launch", f"V{i}", n=i) for i in range(8)]
            + [_dev("customer", "V1"), _dev("funding", "V2"),
               _dev("acquisition", "V3")])
    out = ma.candidate_findings(_inputs(devs))
    assert 3 <= len(out) <= ma.MAX_FINDINGS
    for f in out:
        assert f["headline"] and f["body"]
        assert f["basis"] == "observed"
    # Complete coverage carries no caveat; partial coverage names itself.
    assert all(not f["coverage"] for f in out if f["id"] in ("consolidation", "capital"))
    thin = ma.candidate_findings(_inputs(devs, post_share=0.6))
    assert any("whose announcements could be read" in f["coverage"] for f in thin)


BANNED = ("rapidly evolving", "gaining momentum", "strong traction",
          "increasingly competitive", "dynamic market", "proves")


def test_findings_and_synthesis_use_no_unsupported_phrases():
    devs = ([_dev("product_launch", f"V{i}", n=i) for i in range(8)]
            + [_dev("customer", "V1"), _dev("funding", "V2"),
               _dev("acquisition", "V3")])
    inputs = _inputs(devs, hiring={"openings": 40, "by_vendor": [
        {"vendor": "A", "openings": 24}, {"vendor": "B", "openings": 10}]})
    inputs["formation"] = {"coverage": {"measured": 38},
                           "founded_by_year": [{"year": 2019, "vendors": 8},
                                               {"year": 2024, "vendors": 30}]}
    inputs["now"] = NOW
    text_value = " ".join(
        f["headline"] + " " + f["body"] for f in ma.candidate_findings(inputs))
    text_value += " ".join(p["text"] for p in ma.market_synthesis(inputs))
    for phrase in BANNED:
        assert phrase not in text_value.lower(), phrase


def test_synthesis_only_calls_the_cohort_young_when_the_years_say_so():
    base = {"distribution": {}, "registry_total": 40, "now": NOW}
    young = ma.market_synthesis({**base, "formation": {
        "coverage": {"measured": 38},
        "founded_by_year": [{"year": 2019, "vendors": 8},
                            {"year": 2024, "vendors": 30}]}})
    assert young and "young" in young[0]["text"]
    assert "30 of the 38" in young[0]["text"] and "2023" in young[0]["text"]
    old = ma.market_synthesis({**base, "formation": {
        "coverage": {"measured": 38},
        "founded_by_year": [{"year": 2012, "vendors": 30},
                            {"year": 2024, "vendors": 8}]}})
    assert old and "established" in old[0]["text"]
    # Founding year known for a third of the registry: no cohort claim.
    thin = ma.market_synthesis({**base, "formation": {
        "coverage": {"measured": 12},
        "founded_by_year": [{"year": 2024, "vendors": 12}]}})
    assert not thin


# ---------------------------------------------------------------------------
# The renderer boundary
# ---------------------------------------------------------------------------

def test_the_renderer_makes_no_materiality_decisions():
    """``market_report_html`` receives developments and findings; it must
    not carry the keyword rules, the merge rule or the provenance rule."""
    from app.services import market_report_html as html

    for name in ("_material_kind", "_MATERIAL_PATTERNS", "_merge_same_story",
                 "_corroboration", "_spam_re"):
        assert not hasattr(html, name), name


def test_the_renderer_renders_structured_developments_as_given():
    from app.services.market_report_html import (_render_developments,
                                                 _render_moved_table)

    dev = ma.finish(ma.dedupe([_candidate(
        "customer", "Crogl announces US Air Force deployment",
        vendors=[_vendor("Crogl", 9)], voice="owned", source_type="vendor",
        key="owned:linkedin:9", social=True)])[0])
    dev["rank"] = 1
    table = _render_moved_table([dev])
    assert "Crogl" in table and "Customer evidence" in table
    assert "Vendor source only" in table
    assert "Evidence beyond product availability" in table
    listing = _render_developments([dev])
    assert "Vendor source only" in listing
    assert "1 observed source" in listing


def test_the_renderer_labels_independent_reporting_as_given():
    from app.services.market_report_html import _render_developments

    own = _candidate("partnership", "We've partnered with Anthropic",
                     voice="owned", source_type="vendor", key="owned:linkedin:7",
                     summary="Closed access to Mythos for our detection work.")
    press = _candidate("partnership", "Radiant partners with Anthropic on "
                       "Mythos access", key="domain:securityweek.com",
                       summary="Radiant Security has partnered with Anthropic.")
    dev = ma.finish(ma.dedupe([own, press])[0])
    dev["rank"] = 1
    assert "Also reported independently" in _render_developments([dev])
