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


def test_a_product_named_in_both_headlines_is_one_event():
    """The vendor's post says "introduce Intezer Workflows"; the publisher
    says "adds automated response workflows". One shared name, in both
    headlines, and a nine-word summary on the publisher's side: one event,
    a launch, with the story as its outside source."""
    intezer = [_vendor("Intezer", 9)]
    post = _candidate(
        "product_launch", "That is why we are thrilled to introduce Intezer Workflows!",
        vendors=intezer, voice="vendor", source_type="linkedin",
        summary="With Intezer Workflows the escalation logic no longer lives in a "
                "separate playbook system with its own skillset. Whoever decides "
                "the verdict reads the forensic evidence in plain language.")
    story = _candidate(
        "product_expansion", "Intezer adds automated response workflows to AI SOC",
        vendors=intezer, key="domain:securitybrief.in",
        summary="Intezer has introduced automated remediation capabilities within "
                "its AI SOC platform, enabling security teams to streamline threat "
                "response without switching between tools and improving detection "
                "of lower-severity threats.")
    devs = ma.dedupe([story, post], stop=set())
    assert len(devs) == 1
    assert {e["uri"] for e in devs[0]["evidence"]} == {post["evidence"][0]["uri"], story["evidence"][0]["uri"]}


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
    assert dev["provenance_label"] == "Vendor sources only"


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


def _mixed(n_independent, n_total):
    """Launches, ``n_independent`` of them reported by somebody outside."""
    return [_dev("product_launch", f"V{i}", n=i,
                 provenance=("independently_reported" if i < n_independent
                             else "vendor_source_only"))
            for i in range(n_total)]


def test_no_market_comparison_is_made_below_the_coverage_threshold():
    """Twenty launches against two customers is a fact about our collection
    when we only read a third of the vendors' channels. The template that
    compares them across the market must stay silent.

    Three of the seven developments here are independently reported, which
    clears MIN_INDEPENDENT_SHARE, so vendor coverage is the only gate the
    assertions are testing.
    """
    devs = _mixed(3, 6) + [_dev("customer", "V1")]
    thin = ma.candidate_findings(_inputs(devs, post_share=0.3))
    assert not any(f["id"] == "product_vs_customer" for f in thin)
    # The observed-mix finding that replaces it says what it counts.
    assert any(f["id"] == "dominant_kind" for f in thin)
    full = ma.candidate_findings(_inputs(devs, post_share=0.9))
    assert any(f["id"] == "product_vs_customer" for f in full)


def test_nothing_characterises_the_market_when_only_vendors_were_read():
    """Vendors post launches far more than customer wins, so a corpus built
    only from vendor channels produces that ratio whatever the market is
    doing, and produces "the only source is the vendor" every period because
    no other answer is reachable. Neither finding may run on that corpus, and
    nor may the observed-mix finding that would otherwise stand in.
    """
    named = {**_dev("customer", "V1"),
             "attributes": {"customer": {"named": True, "name": "Acme Bank"}}}
    devs = _mixed(0, 6) + [named]
    out = ma.candidate_findings(_inputs(devs, post_share=0.9))
    ids = {f["id"] for f in out}
    assert "product_vs_customer" not in ids
    assert "dominant_kind" not in ids
    assert "corroboration" not in ids
    # Named developments are still reported; it is the market-wide claim
    # about them that is withheld.
    assert "adoption" in ids


def test_the_market_findings_return_once_outside_sources_are_read():
    """The gate is about our reading, not a permanent silence. Give the same
    developments outside sourcing and both findings come back."""
    devs = _mixed(3, 6) + [_dev("customer", "V1")]
    ids = {f["id"] for f in ma.candidate_findings(_inputs(devs, post_share=0.9))}
    assert "product_vs_customer" in ids
    assert "corroboration" in ids


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
    assert young and "Most of the market is new" in young[0]["text"]
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
    assert "Vendor sources only" in table
    assert "The vendor does not name the customer" in table
    listing = _render_developments([dev])
    assert "Vendor sources only" in listing
    assert "1 source" in listing


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


# ---------------------------------------------------------------------------
# The headline names the vendor
# ---------------------------------------------------------------------------

def test_a_headline_that_never_names_the_vendor_gets_it_prefixed():
    """A vendor's case-study post names the customer, not itself; the card
    headline read as the customer's announcement (DXC/7ai, 5 Sep 2026)."""
    dev = ma.finish(ma.dedupe([_candidate(
        "customer",
        "DXC went from proving the model on its own operations to delivering "
        "it to customers worldwide through DXC Agentic SOC.",
        vendors=[_vendor("7ai", 112)], voice="vendor")])[0])
    assert dev["headline"].startswith("7ai: DXC went from")


def test_a_headline_already_naming_the_vendor_is_left_alone():
    dev = ma.finish(ma.dedupe([_candidate(
        "funding", "Radiant Security raises $40M Series B")])[0])
    assert dev["headline"] == "Radiant Security raises $40M Series B"


def test_the_vendor_name_matches_case_insensitively_and_possessively():
    dev = ma.finish(ma.dedupe([_candidate(
        "customer", "Inside 7AI's rollout at a global insurer",
        vendors=[_vendor("7ai", 112)], voice="vendor")])[0])
    assert not dev["headline"].startswith("7ai:")


def test_any_of_a_multivendor_devs_names_satisfies_the_rule():
    dev = ma.finish(ma.dedupe([_candidate(
        "partnership", "Torq and Defy Security partner on deployment",
        vendors=[_vendor("7ai", 112), _vendor("Torq", 49826)],
        voice="vendor")])[0])
    assert dev["headline"] == "Torq and Defy Security partner on deployment"


# ---------------------------------------------------------------------------
# The summary excerpt skips marketing drumroll
# ---------------------------------------------------------------------------

def test_the_summary_excerpt_drops_hooks_fragments_and_drumroll():
    """The 7ai case-study post opened on a rhetorical question, a three-word
    fragment and 'The real story is what came next.' — none carries a fact."""
    dev = ma.finish(ma.dedupe([_candidate(
        "customer", "Case study: DXC Technology",
        summary=("What does agentic security look like at global scale? "
                 "Ask DXC Technology. Across 25 delivery centers, DXC put "
                 "7AI's agents into worldwide production in eight weeks. "
                 "The real story is what came next. Analysts became threat "
                 "hunters and incident-response leads."),
        vendors=[_vendor("7ai", 112)], voice="vendor")])[0])
    assert dev["summary"] == (
        "Across 25 delivery centers, DXC put 7AI's agents into worldwide "
        "production in eight weeks. Analysts became threat hunters and "
        "incident-response leads.")


def test_a_plain_summary_passes_through_unchanged():
    text = ("Torq raised $70M in Series C funding led by Insight Partners. "
            "The round values the company above $1B.")
    assert ma.plain_summary(text) == text


def test_a_sentence_with_a_promotional_tell_is_dropped():
    text = ("The company shipped single sign-on for all plans. "
            "This game-changing capability revolutionizes enterprise access.")
    assert ma.plain_summary(text) == "The company shipped single sign-on for all plans."


def test_consumer_promotion_is_noise():
    """A Bluesky post selling a "Fun-Pass" reached the public Social panel by
    matching a vendor's name inside its discount code (16 Sep 2026). Two
    gates now stop it; this is the one that reads the words."""
    from app.services.market_assessment import is_noise

    assert is_noise("One scan. One Fun-Pass. Use code: 7AI-N5AI to unlock "
                    "the latest drop. Link in bio to tap in.")
    assert is_noise("Huge giveaway, DM me for the promo code")


def test_a_question_about_your_own_career_is_noise():
    from app.services.market_assessment import is_noise, record_is_noise

    assert is_noise("Help please. I recently graduated in cybersecurity and "
                    "I have two government job offers.")
    # The subreddit carries it where the wording does not.
    assert record_is_noise({
        "title": "20yo in cybersecurity — which path could lead to a "
                 "location-independent career?",
        "summary": "I'm 20 and from Brazil.",
        "social_meta": {"platform": "reddit", "subreddit": "SecurityCareerAdvice"}})


def test_a_practitioner_asking_how_to_evaluate_tools_is_not_noise():
    """The career rules are the shapes of a question about one's own job. A
    practitioner asking the panel's own question must survive them."""
    from app.services.market_assessment import is_noise, record_is_noise

    real = ("What's the best way to evaluate AI SOC solutions in 2026? Our "
            "alert backlog and investigation times have both crept up, and "
            "we're weighing three vendors. Any advice welcome.")
    assert not is_noise(real)
    assert not record_is_noise({"title": real, "summary": "",
                                "social_meta": {"subreddit": "AskNetsec"}})
    assert not record_is_noise({
        "title": "Wrote a 3-part SOC Analyst series (Triage, Hunting, "
                 "Detection Engineering)", "summary": "",
        "social_meta": {"subreddit": "learnwithcodelivly"}})


def test_a_feed_robot_restating_headlines_is_noise():
    from app.services.market_assessment import is_noise

    assert is_noise('The latest update for #Corelight includes "The '
                    'defensible AI-SOC: Redefining SOC modernization"')


def test_share_price_chatter_is_noise():
    from app.services.market_assessment import is_noise

    assert is_noise("AI Security Stocks - Cybersecurity stocks to help "
                    "improve AI security. $FTNT $PANW")
    assert not is_noise("7ai raised $130M, the largest cybersecurity "
                        "Series A on record")


def test_a_sales_approach_is_noise():
    from app.services.market_assessment import is_noise

    assert is_noise("Fragmented security tools impact visibility. Message us "
                    "to talk about how Copilot agents unify alerts.")
    assert is_noise("Book a demo to see the agentic SOC in action")
    assert not is_noise("We swapped our SIEM for a streaming pipeline and "
                        "alert volume fell by half")


def test_two_tickers_is_share_price_talk_and_one_is_a_tag():
    """A stock-tracking account tags a vendor's announcement with the
    vendor's ticker, and that announcement is still a development. Two
    different tickers in one post is somebody comparing shares."""
    from app.services.market_assessment import is_noise

    assert is_noise("$CSCO Cisco is bringing Splunk AI on-prem through a new "
                    "AI POD with $NVDA accelerated computing")
    # One ticker, repeated because the title is prepended to the body.
    tagged = ("CrowdStrike Unveils the Next Evolution of the Agentic SOC | "
              "$CRWD CrowdStrike Unveils the Next Evolution of the Agentic "
              "SOC. Only CrowdStrike can investigate every domain | $CRWD")
    assert not is_noise(tagged)


def test_research_counts_as_a_development_only_where_the_market_asks():
    """Off unless asked for, because the two markets measured want opposite
    answers. On a health market a published study is the news; on AI-SOC it is
    mostly content marketing, and counting it added 35 developments to a
    93-development month while pushing outside sourcing down.
    """
    assert ma.includes_research({"id": 1}) is False
    assert ma.includes_research({"id": 1, "config": {}}) is False
    assert ma.includes_research(
        {"id": 1, "config": {"developments": {"include_research": False}}}) is False
    assert ma.includes_research(
        {"id": 1, "config": {"developments": {"include_research": True}}}) is True


def test_the_flag_is_read_from_config_stored_as_text():
    """bw_markets.config comes back as a string through some drivers, and a
    flag that silently reads False there would be a switch that does nothing.
    """
    assert ma.includes_research(
        {"id": 1, "config": '{"developments": {"include_research": true}}'}) is True
    assert ma.includes_research({"id": 1, "config": "not json"}) is False


def test_a_research_finding_never_outranks_a_funding_round():
    """The canonical list is ordered by importance and `importance_of` reads
    position, so where research sits in it is behaviour, not presentation."""
    assert ma.EVENT_TYPES["research"] == "Research finding"
    assert ma._TYPE_RANK["research"] > ma._TYPE_RANK["funding"]
    assert ma._TYPE_RANK["research"] > ma._TYPE_RANK["acquisition"]
    assert ma.importance_of("research", "vendor_source_only") == "low"
    assert ma.importance_of("research", "multiple_independent_sources") == "low"


# ---------------------------------------------------------------------------
# aisocnews data-quality review, 24 Sep 2026: each case is a real item that
# was wrong on the page.
# ---------------------------------------------------------------------------

def _post(title, summary="", *, vendor="Simbian", brand_id=5, date="2026-09-02"):
    return _candidate("product_launch", title, date=date, summary=summary,
                      vendors=[_vendor(vendor, brand_id)], voice="owned",
                      source_type="vendor", key=f"owned:linkedin:{brand_id}")


def _tweet(title, n, *, date="2026-09-08", kind="product_launch"):
    return _candidate(kind, title, date=date, vendors=[], seed=False, social=True,
                      source_type="social", key=f"social:x:account{n}")


def test_tweets_about_other_companies_do_not_attach_to_a_vendor_post():
    """Simbian's post collected fifteen sources: the Zscaler, Proofpoint and
    CrowdStrike launches, each attaching on words the last one added."""
    post = _post("As frontier models get better on offense, their defensive "
                 "growth doesn't keep pace.",
                 "Frontier models from Anthropic and OpenAI change the SOC.")
    tweets = [
        _tweet("Zscaler launches Agentic SOC with AI agents from Anthropic and OpenAI", 1),
        _tweet("Proofpoint launches AI SOC Analyst Agent with OpenAI models", 2),
        _tweet("CrowdStrike unveils Charlotte AI Agentic SOC with frontier models", 3),
    ]
    devs = ma.dedupe([post] + tweets, stop=set())
    assert len(devs) == 1 and len(devs[0]["evidence"]) == 1
    assert ma.finish(devs[0])["provenance"] == "vendor_source_only"


def test_a_partner_named_in_a_report_is_not_the_vendor():
    """A SailPoint release about CrowdStrike is not coverage of Artemis
    presenting with CrowdStrike."""
    post = _candidate("partnership", "Presenting alongside CrowdStrike at their own "
                      "event is a milestone for Artemis and for our partnership.",
                      date="2026-09-01", vendors=[_vendor("Artemis Security", 6)],
                      voice="owned", source_type="vendor")
    other = _tweet("SailPoint Announces Integration with CrowdStrike Falcon Next-Gen SIEM",
                   4, date="2026-09-01", kind="partnership")
    devs = ma.dedupe([post, other], stop=set())
    assert len(devs[0]["evidence"]) == 1


def test_a_three_letter_customer_name_merges_two_posts_about_it():
    a = _candidate("customer", "DXC went from proving the model on its own operations "
                   "to delivering it to customers worldwide.", date="2026-08-31",
                   vendors=[_vendor("7ai", 8)], voice="owned", source_type="vendor",
                   summary="Across 25 delivery centers DXC put agents into production.")
    b = _candidate("customer", "Before bringing agentic security to customers, DXC "
                   "Technology ran it across its own global security operations.",
                   date="2026-09-09", vendors=[_vendor("7ai", 8)], voice="owned",
                   source_type="vendor", summary="Ask DXC how it went.")
    assert len(ma.dedupe([a, b], stop=set())) == 1


def test_one_release_on_blog_and_linkedin_is_one_launch():
    blog = _post("Bricklayer Introduces MCP Support", vendor="Bricklayer AI",
                 brand_id=9, date="2026-09-09",
                 summary="Bricklayer AI announces support for Model Context Protocol.")
    post = _post("Today we're announcing MCP support in Bricklayer.", vendor="Bricklayer AI",
                 brand_id=9, date="2026-09-09",
                 summary="MCP has quickly become the standard for connecting AI systems.")
    assert len(ma.dedupe([blog, post], stop=set())) == 1


def test_a_product_named_in_both_headlines_merges_across_three_weeks():
    first = _post("we just launched Morpheus 2, the new and improved version of our "
                  "agentic SOC platform.", vendor="D3 Security", brand_id=10,
                  date="2026-08-28")
    later = _post("We've launched some exciting new improvements with Morpheus 2, which "
                  "include graded evidence.", vendor="D3 Security", brand_id=10,
                  date="2026-09-17")
    assert len(ma.dedupe([first, later], stop=set())) == 1


def test_two_products_sharing_a_first_word_stay_apart():
    a = _post("Introducing Virtus Sentinel", "AI Detection, Enforcement and Response "
              "across agents and tools.", vendor="Imperum", brand_id=3, date="2026-09-17")
    b = _post("Imperum Virtus Cerebrum is now live!", "Virtus Cerebrum reasons across "
              "agents and tools.", vendor="Imperum", brand_id=3, date="2026-09-07")
    assert len(ma.dedupe([a, b], stop=set())) == 2


def test_a_name_with_a_turkish_suffix_is_the_same_name():
    assert "PARS" in ma._tokens("Bugün SOCNova’nın Agentic Katmanı: PARS’ı duyuruyoruz.")


def test_a_short_name_prefix_is_not_doubled():
    rec = {"title": "Mate: Mate is joining the XAA Ecosystem!",
           "vendors": [{"vendor": "Mate Security"}]}
    headline = ma.headline_of(rec)
    assert headline == "Mate is joining the XAA Ecosystem!"
    assert ma._named_headline(headline, rec["vendors"]) == headline


def test_a_hook_headline_gives_way_to_the_sentence_naming_the_product():
    got = ma.announcing_headline(
        "A coverage map tells you a rule exists.",
        "A coverage map tells you a rule exists. It doesn't tell you the log source "
        "behind it died in March. Armor Detect runs that audit every day, then fixes "
        "what it finds.", "product_launch", [{"vendor": "Arambh Labs"}])
    assert got.startswith("Armor Detect runs that audit")
    kept = "This week we unified Detection and Response into a single Agents workspace."
    assert ma.announcing_headline(kept, kept + " More.", "product_expansion",
                                  [{"vendor": "Cotool"}]) == kept


def test_deal_highlights_are_in_our_words():
    acq = {"event_type": "acquisition", "date": "2026-09-18",
           "vendors": [{"vendor": "Wirespeed"}],
           "headline": "Wirespeed: Coalition, Inc. acquired us for our ability to stop "
                       "cyber threats in milliseconds.", "summary": ""}
    said = ma._deal_sentence(acq)
    assert said == "Coalition, Inc. acquired Wirespeed on 18 September."
    fund = {"event_type": "funding", "date": "2026-09-16", "why_it_matters": "",
            "vendors": [{"vendor": "StrikeReady"}], "summary": "",
            "headline": "StrikeReady is excited to share our new investment round led by "
                        "the venture capital arm of Aramco, Wa'ed Ventures."}
    assert ma._deal_sentence(fund) == ("StrikeReady raised a new round led by the venture "
                                       "capital arm of Aramco, Wa'ed Ventures on 16 September.")


def test_headlines_that_are_not_market_events():
    for title in ("The 10 Best Tines Alternatives in 2026: Agentic SOC Platforms Compared",
                  "Within 35 seconds, we shut down two malicious LOTL executions.",
                  "We'll take the number 1 spot on HackerOne's US leaderboard.",
                  "Introducing the Certified AI SOC Analyst (CASA) program by Intezer."):
        assert ma._NOT_EVENT.search(title), title
    assert ma.classify_text("How Prophet AI Protects High-Exposure Partner Environments",
                            title="How Prophet AI Protects High-Exposure Partner "
                                  "Environments") is None
    assert ma.classify_text("RedCarbon is now an Armis Technology Partner!",
                            title="RedCarbon is now an Armis Technology Partner!") == "partnership"


def test_chip_news_paid_lists_and_junior_hires_are_noise():
    assert ma.is_noise("$MASK completes pre-silicon emulation of custom Edge AI SoC")
    assert ma.is_noise("SOC Automation Tool List 2026 includes Legion Security")
    assert ma.is_noise("Jamal joins our team as a CSOC Tier 1 Analyst")
    assert not ma.is_noise("Strike48 announces an agentic SOC appliance for air-gapped sites")


def test_styled_letters_read_as_plain_text():
    assert ma.plain_letters("𝐁𝐅𝐒𝐈 teams") == "BFSI teams"
    assert ma.plain_letters("iSteps™ show") == "iSteps show"


def test_hiring_readings_are_counted_apart_from_developments():
    devs = [ma.finish(ma.prepare_candidate(c, set())) for c in (
        _post("Launch one", date="2026-09-01", vendor="A", brand_id=1),
        _post("Launch two", date="2026-09-02", vendor="B", brand_id=2),
        {**_post("12 open roles", vendor="A", brand_id=1),
         "event_type": "significant_hiring"})]
    dist = ma.distribution(devs)
    assert dist["total"] == 2 and dist["signals"] == 1


def test_vendors_tied_for_third_are_all_named():
    rows = [{"vendor": v, "n": n} for v, n in
            (("7ai", 4), ("Anvilogic", 4), ("D3 Security", 4), ("Mate Security", 4),
             ("Artemis", 3))]
    assert [r["vendor"] for r in ma.top_vendors(rows)] == [
        "7ai", "Anvilogic", "D3 Security", "Mate Security"]


def test_a_funding_total_is_not_the_round():
    dev = {"event_type": "funding", "vendors": [{"vendor": "StrikeReady"}],
           "headline": "StrikeReady is excited to share our new investment round.",
           "summary": "This brings our total funding raised to $29M with Hitachi."}
    assert ma.why_it_matters(dev) == "$29M raised in total, the vendor says."


# ---------------------------------------------------------------------------
# Round two of the aisocnews.com data-quality fixes (25 Sep 2026)
# ---------------------------------------------------------------------------

def _dedupe(*cands):
    return ma.dedupe([dict(c) for c in cands])


def test_two_vendor_launches_a_week_apart_need_the_same_product_to_merge():
    """Mars Security's detection engine and its Playbooks merged on "Real"."""
    engine = _post("A new Mars invasion: automatic, intel-based, Real-Time "
                   "detection engineering.",
                   "Mars turns CTI into Real-Time detections for every SIEM.",
                   vendor="Mars Security", brand_id=159, date="2026-09-08")
    playbooks = _post("PRODUCT UPDATE: Introducing MARS Playbooks",
                      "Five Real playbooks that turn CTI into detections.",
                      vendor="Mars Security", brand_id=159, date="2026-09-16")
    assert len(_dedupe(engine, playbooks)) == 2


def test_a_follow_up_post_two_days_later_is_the_same_launch():
    """Huntbase opened its Hub on 22 Sep and posted about it again on the
    24th, sharing twelve subject words but few names."""
    body = ("threat research hunts built from current public research, each "
            "reviewed by a person, runnable against your environment, "
            "queries covering techniques across windows linux macos cloud")
    first = _post("Today we opened the Huntbase Hub: 149 hunts built from "
                  "current public research", body,
                  vendor="Huntbase", brand_id=301, date="2026-09-22")
    second = _post("Until this week, running a Huntbase hunt meant asking us "
                   "for access.", "Two days later there are 162. " + body,
                   vendor="Huntbase", brand_id=301, date="2026-09-24")
    assert len(_dedupe(first, second)) == 1


def test_partnerships_with_different_partners_stay_apart():
    """AquilaI's Virus Rescuers and Ampcus Cyber partnerships, one event."""
    one = _candidate("partnership", "At Aquila I, we are thrilled to kick off "
                     "a strategic partnership with Virus Rescuers at GISEC",
                     summary="Aquila I and Virus Rescuers will serve the "
                     "Middle East.", date="2026-09-24",
                     vendors=[_vendor("AquilaI", 40)], voice="owned")
    two = _candidate("partnership", "At GISEC GLOBAL 2026, Aquila I and "
                     "Ampcus Cyber announced a strategic MSSP partnership",
                     summary="Aquila I and Ampcus Cyber at GISEC.",
                     date="2026-09-22", vendors=[_vendor("AquilaI", 40)],
                     voice="owned")
    assert len(_dedupe(one, two)) == 2


def test_a_wire_release_is_the_vendors_own_voice():
    row = {"uri": "https://www.prnewswire.com/news-releases/x.html",
           "title": "BlueVoyant launches agentic SOC", "article_class": "news",
           "news_source": "PR Newswire", "vendors": [_vendor("BlueVoyant", 3)]}
    ev = ma._evidence_from_record(row)
    assert ev["voice"] == "owned" and ev["key"] == "owned:wire:prnewswire.com"
    assert ma.provenance_of([ev]) == "vendor_source_only"
    menafn = ma._evidence_from_record({**row, "uri": "https://menafn.com/1"})
    assert menafn["voice"] == "owned"


def test_an_event_day_is_the_utc_day():
    """Wirespeed posted at 22:02 UTC on 17 Sep; Berlin time made it the 18th."""
    from datetime import date as _date
    berlin = timezone(timedelta(hours=2))
    stamp = datetime(2026, 9, 18, 0, 2, tzinfo=berlin)
    assert ma._parse_day(stamp) == _date(2026, 9, 17)
    assert ma._parse_day("2026-09-18 00:02:00+02:00") == _date(2026, 9, 17)
    assert ma._parse_day("2026-09-17") == _date(2026, 9, 17)


def test_platform_headlines_reach_the_wider_market():
    for title, company in (
            ("Splunk is expanding its Agentic SOC Workforce with a set of new "
             "purpose-built skills", "Splunk"),
            ("🔐 Cisco &amp; NVIDIA bring Splunk AI to on-premises "
             "environments — launching Cisco AI POD for Splunk", "Cisco"),
            ("Cisco expanded Splunk AI with on-premises NVIDIA hardware "
             "support", "Cisco"),
            ("Exciting news: Cisco announces intent to acquire WideField "
             "Security Inc", "Cisco")):
        row = {"uri": f"https://x.test/{abs(hash(title))}", "title": title,
               "summary": "", "published": "2026-09-17T10:00:00Z"}
        cand = ma._wider_candidate(row, {"uri": row["uri"]})
        # Not read yet: it waits for the strip's review, named for it.
        assert cand and cand["unchecked"] and cand["company"] == company, title


def _passed_wider(headline, summary=""):
    return {"wider": {"passed": True, "headline": headline, "summary": summary}}


def test_the_wider_strip_shows_only_what_its_review_passed():
    title = ("🔐 Cisco &amp; NVIDIA bring Splunk AI to on-premises environments "
             "— launching Cisco AI POD for Splunk")
    row = {"uri": "https://x.test/cisco", "title": title, "summary": "",
           "published": "2026-09-17T10:00:00Z"}
    ok = ma._wider_candidate({**row, "review_check": _passed_wider(
        "Cisco brings Splunk AI to on-premises NVIDIA hardware")}, {"uri": row["uri"]})
    assert ok["headline"] == "Cisco brings Splunk AI to on-premises NVIDIA hardware"
    assert ok["vendors"][0]["vendor"] == "Cisco"
    failed = {"wider": {"passed": False, "headline": None}}
    assert ma._wider_candidate({**row, "review_check": failed}, {"uri": row["uri"]}) is None
    # A leading hashtag is not part of the company's name.
    tagged = {**row, "title": "#Cybersecurity KDDI Expands Agentic SOC Services "
                              "Across US and EMEA"}
    assert ma._wider_candidate(tagged, {"uri": row["uri"]})["company"] == "KDDI"


def test_a_customer_that_avoided_an_attack_is_not_a_customer_win():
    assert ma._NOT_EVENT.search(
        "Wirespeed ⚡️: We helped another Coalition policyholder avoid a "
        "cyber attack!")


def test_a_download_count_is_not_a_launch():
    assert ma._NOT_EVENT.search("Imperum: Virtus passes 6K+ downloads")


def test_chip_soc_posts_are_noise():
    assert ma.is_noise("$MASK - 3 E Network: Hardware Emulation for Custom "
                       "Edge AI SoC")


def test_partner_in_a_sentence_is_not_a_senior_title():
    assert not ma._SENIOR.search(
        "Paige Roderick joins as Lead, Field Marketing, focused on customer "
        "and partner experiences")
    assert ma._SENIOR.search("joins as Managing Partner")


def test_a_hook_headline_falls_back_to_the_review_reading():
    assert ma.announcing_headline(
        "Someone relaxes a WAF rule during an incident.",
        "Someone relaxes a WAF rule during an incident. Nobody reverts it.",
        "product_launch", [_vendor("Tuskira", 9)],
        reason="Vector autonomous red team agent shipped",
    ) == "Vector autonomous red team agent shipped"


def test_a_vendor_blog_about_another_companys_deal_is_not_the_vendors():
    d3 = {"vendors": [_vendor("D3 Security", 11)]}
    assert not ma.speaks_for_vendor(
        "Cribl Just Acquired Radiant Security’s AI SOC Technology. Here’s What "
        "It Means", d3)
    assert ma.speaks_for_vendor("We've been acquired by Coalition",
                                {"vendors": [_vendor("Wirespeed", 12)]})


def test_an_unnamed_customer_count_is_not_listed_as_a_customer():
    dev = {"event_type": "customer", "vendors": [_vendor("Spectrum Security", 8)],
           "headline": "SEP2 runs 24/7 MDR across 70+ customers",
           "summary": "SEP2 runs 24/7 MDR across 70+ customers.",
           "attributes": {}}
    assert not ma._customer_listable(dev)


def test_a_longer_company_page_name_is_stripped_but_a_sentence_is_not():
    crogl = {"title": "Crogl, Inc.: Your SOC depends on a system no security "
             "vendor supports.", "vendors": [_vendor("Crogl", 21)]}
    assert ma.headline_of(crogl).startswith("Your SOC depends")
    mate = {"title": "Mate Announce Gamebooks: the Control Flow for Agentic "
            "Investigations.", "vendors": [_vendor("Mate Security", 22)]}
    assert ma.headline_of(mate).startswith("Mate Announce Gamebooks")


# ---------------------------------------------------------------------------
# The review writes the headline; Jev checks it (26 Sep 2026)
# ---------------------------------------------------------------------------

def _check(headline="supports", summary="supports", p=0.95):
    return {"headline": {"verdict": headline, "p_supports": p},
            "summary": {"verdict": summary, "p_supports": p}}


def test_a_checked_headline_is_used_and_an_unsupported_one_is_not():
    row = {"review_headline": "Legion Security joins OpenAI's Daybreak Blue programme",
           "review_summary": "It gains early access to Astra.",
           "review_check": _check()}
    assert ma.checked_writing(row) == (row["review_headline"], row["review_summary"])
    # Conifers: "finds 47% of detections need attention", which the post does
    # not say.
    assert ma.checked_writing({**row, "review_check": _check(
        headline="says_nothing", p=0.11)})[0] is None
    # No check at all is not a pass.
    assert ma.checked_writing({**row, "review_check": None}) == (None, None)
    # A low probability of support is not a pass even when it is the choice.
    assert ma.checked_writing({**row, "review_check": _check(p=0.4)})[0] is None


def test_the_review_headline_leads_a_vendor_post():
    row = {"uri": "https://www.linkedin.com/posts/legion_1", "title":
           "Legion Security: We're proud to share that we have been accepted "
           "into OpenAI Daybreak Blue", "summary": "We're proud to share…",
           "article_class": "social", "review_verdict": "signal",
           "review_kind": "partnership", "vendors": [_vendor("Legion Security", 30)],
           "published": "2026-09-25T09:00:00Z",
           "review_headline": "Legion Security joins OpenAI's Daybreak Blue programme",
           "review_summary": "It gains early access to Astra.",
           "review_check": _check(), "social_meta": {}}
    dev = ma.finish(ma.dedupe([{
        "key": "corpus:x", "event_type": "partnership", "date": "2026-09-25",
        "vendors": row["vendors"], "headline": ma.checked_writing(row)[0],
        "dek": ma.checked_writing(row)[1], "summary": row["summary"],
        "evidence": [ma._evidence_from_record(row)], "seed": True,
        "headline_rank": 2}])[0])
    assert dev["headline"].startswith("Legion Security joins")
    assert dev["dek"] == "It gains early access to Astra."


def test_a_credential_or_an_open_letter_is_not_an_event():
    for headline in ("UiPath launches Agentic Automation Builder Professional "
                     "Certification",
                     "Cotool signs OpenAI open letter on cyber defense collective action",
                     "Mate Security named early supporter of OpenAI's Call for "
                     "Collective Action on Cyber Defense"):
        assert ma._NOT_EVENT.search(headline), headline
    assert not ma._NOT_EVENT.search("UiPath launches Delegate, an enterprise productivity agent")


def test_a_vendor_post_with_no_tracked_vendor_is_not_a_development():
    """Avo Automation left panaya's market on 22 Sep; its posts kept a review."""
    post = _record("Avo Automation: Church & Dwight reduced regression testing effort",
                   article_class="social", vendors=[], review_verdict="signal",
                   review_kind="customer")
    assert ma.classify_record(post) is None


# ---------------------------------------------------------------------------
# Data-quality round three (26 Sep 2026)
# ---------------------------------------------------------------------------

def test_a_word_in_passing_does_not_drop_a_reviewed_announcement():
    """Merlin Cyber and Torq's partnership post mentioned the booth."""
    post = {**_record("Torq: Merlin Cyber and Torq are partnering on federal AI SOC",
                      article_class="social", vendors=[_vendor("Torq", 50)],
                      review_verdict="signal", review_kind="partnership",
                      summary="Find us at booth 12 to see it."),
            "review_headline": "Merlin Cyber partners with Torq for federal AI SOC",
            "review_check": _check()}
    assert ma.classify_record(post) == "partnership"


def test_a_government_award_is_a_customer_not_a_round():
    assert ma._refine_funding("funding", "Method Security wins $30M STRATFI award "
                              "from U.S. Space Force") == "customer"
    assert ma._refine_funding("funding", "StrikeReady raises funding led by "
                              "Wa'ed Ventures") == "funding"


def test_led_by_stops_at_the_end_of_the_headline():
    dev = {"event_type": "funding", "vendors": [_vendor("StrikeReady", 51)],
           "headline": "StrikeReady raises funding led by Wa'ed Ventures",
           "summary": "StrikeReady is excited to share our new investment round "
                      "led by the venture capital arm of Aramco.",
           "date": "2026-09-16"}
    assert ma._deal_sentence(dev) == ("StrikeReady raised a new round led by "
                                      "Wa'ed Ventures on 16 September.")


def test_a_marketplace_listing_is_not_an_event():
    assert ma._NOT_EVENT.search("Daylight Security launches on Google Cloud Marketplace")
    assert ma._NOT_EVENT.search("Anvilogic listed in Snowflake, Databricks and AWS marketplaces")
    assert not ma._NOT_EVENT.search("Anvilogic becomes Snowflake Connected App")


def test_one_named_customer_told_twice_three_weeks_apart_is_one_item():
    reading = {"customer": {"named": True, "name": "SEP2"}}
    first = {**_post("SEP2 runs 24/7 MDR for 70+ customers", vendor="Spectrum Security",
                     brand_id=52, date="2026-09-03"), "event_type": "customer",
             "attributes": reading}
    again = {**_post("Every detection team has a list of coverage it cannot reach",
                     vendor="Spectrum Security", brand_id=52, date="2026-09-25"),
             "event_type": "customer", "attributes": reading}
    assert len(ma.dedupe([first, again])) == 1


def test_a_companys_own_site_is_not_independent_in_the_wider_strip():
    row = {"uri": "https://atos.net/en/2026/press-release/atos-gch",
           "title": "Atos partners with GCH to open a new AI-driven SOC in the UAE",
           "summary": "", "published": "2026-09-17T10:00:00Z",
           "review_check": _passed_wider("Atos partners with GCH to open an AI SOC in the UAE")}
    cand = ma._wider_candidate(row, {"uri": row["uri"], "voice": "independent",
                                     "key": "domain:atos.net"})
    assert cand and cand["evidence"][0]["voice"] == "owned"


def test_a_look_back_post_does_not_date_the_event():
    assert ma._LOOKS_BACK.search("Sevii: Looking back at an outstanding CrowdStrike "
                                 "Fal.Con 2026 in Las Vegas")
    assert ma._LOOKS_BACK.search("That's a wrap on AiStrike India week.")
    assert not ma._LOOKS_BACK.search("Sevii launches Sevii AI Security module")


def test_strikethrough_marks_are_dropped():
    assert ma.plain_letters("W̶e̶e̶k̶s̶ of work") == "Weeks of work"


def test_a_case_studys_co_author_is_not_the_customer():
    text_value = ("We worked with Anthropic on a case study covering what Kai does "
                  "inside a real enterprise environment.")
    reading = ma.reading_from_review({"name": "Anthropic", "stage": "unclear"},
                                     text_value=text_value)
    assert reading["named"] is False
    assert ma.reading_from_review({"name": "Virgin Money", "stage": "in_use"},
                                  text_value="Virgin Money runs Legion.")["named"]


# ---------------------------------------------------------------------------
# Round four: generate, validate, correct (26 Sep 2026)
# ---------------------------------------------------------------------------

def test_a_newsletter_is_not_an_event_whatever_the_review_says():
    post = {**_record("Tuskira: Tuskira Threat Brief: Week of September 21, 2026",
                      article_class="social", vendors=[_vendor("Tuskira", 60)],
                      review_verdict="signal", review_kind="launch"),
            "review_headline": "Tuskira launches autonomous red teaming",
            "review_check": _check()}
    assert ma.classify_record(post) is None


def test_a_preview_or_an_advisor_is_not_an_event():
    assert ma._NOT_EVENT.search("D3 Security to unveil Morpheus 2 on September 16")
    assert ma._NOT_EVENT.search("Sevii appoints Tammi Hayes as advisor")
    assert not ma._NOT_EVENT.search("D3 Security launches Morpheus 2")


def test_founding_leaders_and_team_leads_are_senior():
    assert ma._SENIOR.search("Mate Security hires Kirra Rice as Founding Channel Leader")
    # A team lead is not an executive.
    assert not ma._SENIOR.search("AiStrike hires Bhuvanesh Prabhakaran to lead SOC team")
    assert not ma._SENIOR.search("Acme hires Jo Smith as SOC team leader")
    assert ma._SENIOR.search("Acme hires Jo Smith to lead sales in EMEA")
    assert not ma._SENIOR.search("Legion Security hires Paige Roderick as Lead, Field Marketing")


def test_a_short_vendor_name_at_the_start_is_not_doubled():
    assert ma._named_headline("Kai hires Thomas N. as VP of Product Marketing",
                              [_vendor("Kai Security", 61)]).startswith("Kai hires")


def test_many_tied_vendors_are_described_by_their_threshold():
    rows = [{"vendor": f"V{i}", "n": 2} for i in range(9)]
    top = ma.top_vendors(rows)
    assert len(top) == 9


def test_the_vendor_note_in_brackets_is_not_shown():
    dev = ma.finish(ma.prepare_candidate(
        _post("Strike48 launches on-prem appliance", vendor="Strike48 (A Devo company)",
              brand_id=62), set()))
    assert dev["vendors"][0]["vendor"] == "Strike48"


def test_objections_cover_kind_news_customer_and_text():
    from app.services import market_post_review as mpr

    item = {"verdict": "signal", "kind": "customer", "headline": "H", "summary": None,
            "customer": {"name": "Help Net Security"}}
    check = {"kind": {"choice": "other", "p_drafted": 0.05},
             "is_news": 0.2, "customer": 0.1,
             "headline": {"verdict": "supports", "p_supports": 0.64}}
    found = " ".join(mpr.objections(item, check))
    assert "kind" in found and "new development" in found
    assert "Help Net Security" in found and "headline" in found
    # Two kinds that never reach the page are not worth a correction.
    assert not mpr.objections({"verdict": "signal", "kind": "award"},
                              {"kind": {"choice": "other", "p_drafted": 0.1}})


def test_what_the_checker_still_disputes_is_held_back():
    from app.services import market_post_review as mpr

    v = {"verdict": "signal", "kind": "customer", "headline": "H", "summary": "S",
         "customer": {"name": "Help Net Security"},
         "check": {"kind": {"choice": "other", "p_drafted": 0.05}, "is_news": 0.2}}
    mpr._hold_what_is_unconfirmed(v)
    assert v["verdict"] == "commentary" and v["check"]["held"]


def test_a_contract_read_as_an_award_is_still_a_customer():
    post = {**_record("Method Security: Bringing cyber resilience to Space.",
                      article_class="social", vendors=[_vendor("Method Security", 63)],
                      review_verdict="signal", review_kind="award"),
            "review_headline": "Method Security wins $30M STRATFI award from U.S. Space Force",
            "review_check": _check()}
    assert ma.classify_record(post) == "customer"


def test_awardable_on_a_marketplace_is_a_listing_not_a_contract():
    h = "BlueDome by AiStrike becomes Awardable on Tradewinds Solutions Marketplace"
    assert ma._NOT_EVENT.search(h)
    assert not ma._CONTRACT.search(h)


def test_the_customer_line_only_adds_what_the_headline_does_not_say():
    def dev(reading):
        return {"event_type": "customer", "vendors": [_vendor("Opnova", 64)],
                "headline": "Live Oak Bank uses Opnova for identity governance",
                "summary": "", "attributes": {"customer": {**reading, "source": "review"}}}
    in_use = {"named": True, "name": "Live Oak Bank", "voice": "in the vendor's words",
              "stage": "described in use"}
    assert ma.customer_sentence(dev(in_use)) == ""
    assert ma.customer_sentence(dev({**in_use, "stage": "evaluating it rather than running it"})) \
        == "Live Oak Bank is evaluating the product, not yet running it."
    assert ma.customer_sentence(dev({**in_use, "voice": "in the customer's own words"})) \
        == "Someone from Live Oak Bank is quoted in the post."
    assert ma.customer_sentence(dev({"named": False, "name": None,
                                     "voice": "in the vendor's words",
                                     "stage": "described as a customer"})) \
        == "The vendor does not name the customer."


def test_a_highlight_source_line_reads_like_the_rest_of_the_page():
    dev = {"headline": "Coalition acquires Wirespeed", "date": "2026-09-17",
           "provenance_label": "Vendor sources only"}
    assert ma._evidence_line(dev) == "Coalition acquires Wirespeed (Vendor sources only, 17 Sep 2026)"


def test_a_vendor_name_takes_the_registered_spelling():
    assert ma._vendor_spelling("Vigilbase launches Vigilbase Platform",
                               [_vendor("VigilBase", 70)]) == "VigilBase launches VigilBase Platform"


def test_only_confident_items_are_featured_or_quoted():
    assert ma.prominent_ok({"review_confidence": None})
    assert ma.prominent_ok({"review_confidence": 0.9})
    assert not ma.prominent_ok({"review_confidence": 0.64})
    assert ma.review_confidence({"kind": {"p_drafted": 0.95},
                                 "headline": {"p_supports": 0.64}}) == 0.64


def test_a_usage_milestone_is_not_a_launch_whatever_the_headline_says():
    # Imperum's 11 Sep post thanks readers for 6K+ downloads of a model it
    # released on 24 Aug. Sonnet 5 rewrote it as "Imperum releases …", so
    # the guard reads the post, not the headline.
    milestone = ("Imperum: A big thank you to the cybersecurity community! In less "
                 "than 3 weeks since launch, Imperum-CybersecurityLLM v1.0 has "
                 "passed 6K+ downloads")
    assert ma.milestone_post("product_launch", milestone)
    assert not ma.milestone_post("partnership", milestone)
    assert not ma.milestone_post("product_launch", "Imperum: Introducing "
                                 "Imperum-CybersecurityLLM v1.0. Free to download.")
    assert not ma.milestone_post("product_launch", "Acme: We're excited to launch "
                                 "Acme Triage 2.0, already used by 5,000 users in beta.")
    assert ma.milestone_post("product_expansion", "Acme: Our agent just hit 10K "
                             "stars on GitHub. Thank you!")
    record = {"article_class": "vendor", "review_verdict": "signal",
              "review_kind": "launch", "vendors": [{"brand_id": 1, "vendor": "Imperum"}],
              "title": milestone, "summary": "",
              "review_headline": "Imperum releases Imperum-CybersecurityLLM v1.0",
              "review_check": {"headline": {"verdict": "supports", "p_supports": 0.95}}}
    assert ma.classify_record(record) is None


def test_the_page_shows_only_checked_quoted_or_counted_words():
    assert ma.shown_on_page({"headline_source": "checked", "review_confidence": 0.9})
    assert ma.shown_on_page({"headline_source": "publisher", "review_confidence": None})
    assert ma.shown_on_page({"headline_source": "data"})
    assert not ma.shown_on_page({"headline_source": "rule"})
    # The checks unsure what it is: left out rather than guessed.
    assert not ma.shown_on_page({"headline_source": "checked", "review_confidence": 0.39})


def test_an_item_is_credited_only_to_a_company_its_sources_say_did_it():
    dev = {"event_type": "product_launch", "headline": "Synthesized launches UiPath integration",
           "headline_uri": "https://news/synth", "headline_rank": 0,
           "vendors": [{"brand_id": 5, "vendor": "UiPath"}, {"brand_id": 6, "vendor": "SmartBear"}],
           "evidence": [{"uri": "https://news/synth"}, {"uri": "https://uipath.com/blog"}],
           "head_options": [
               {"uri": "https://news/synth", "headline": "Synthesized launches UiPath integration",
                "headline_source": "publisher", "headline_rank": 0},
               {"uri": "https://uipath.com/blog", "headline": "UiPath launches Integration Service",
                "headline_source": "checked", "headline_rank": 2}]}
    # Not checked yet: every pair waits.
    kept, todo, rejected = ma._credited(dev, {})
    assert not kept and len(todo) == 4 and not rejected
    actors = {"https://news/synth": {"5": 0.26, "6": 0.1},
              "https://uipath.com/blog": {"5": 0.98, "6": 0.05}}
    kept, todo, rejected = ma._credited(dev, actors)
    assert [v["vendor"] for v in kept] == ["UiPath"] and not todo and rejected
    # The headline's own source does not confirm UiPath: take one that does.
    fixed = ma._confirmed_headline({**dev, "vendors": kept}, actors)
    assert fixed["headline"] == "UiPath launches Integration Service"
    assert fixed["headline_uri"] == "https://uipath.com/blog"


def test_a_vendor_is_named_by_the_names_it_goes_by():
    # "P&G Oral-B" is written "Oral-B" in the press.
    dev = {"vendors": [{"brand_id": 5, "vendor": "P&G Oral-B", "aliases": ["Oral-B"]}]}
    assert ma._names_vendor_of({"title": "Oral-B iO Series 2 launched in India"}, dev)
    assert not ma._names_vendor_of({"title": "Oral-B iO Series 2 launched in India"},
                                   {"vendors": [{"brand_id": 5, "vendor": "P&G Oral-B"}]})


def test_confidence_travels_with_the_headline_shown():
    opt = ma._head_option({"headline": "Nebulock releases GATES Method",
                           "headline_uri": "https://a", "review_confidence": 0.99,
                           "headline_rank": 2})
    assert opt["review_confidence"] == 0.99
    dev = {"headline": "weak", "headline_uri": "https://b", "review_confidence": 0.48,
           "vendors": [{"brand_id": 1, "vendor": "Nebulock"}],
           "head_options": [opt, {"uri": "https://b", "headline": "weak",
                                  "headline_rank": 3, "review_confidence": 0.48}]}
    swapped = ma._confirmed_headline(dev, {"https://a": {"1": 0.9}, "https://b": {"1": 0.1}})
    assert swapped["headline_uri"] == "https://a" and swapped["review_confidence"] == 0.99
