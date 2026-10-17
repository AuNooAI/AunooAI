"""Link provenance across the duplicate merge and the link judge
(17 Oct 2026): nothing is dropped silently, every candidate gets a
decision, and the audit names what is missing."""
from app.services.wiley_event_extraction import (
    inherit_links, links_to_decide, resolve_links, audit_merged_links, _normalize_scenario_relevance,
    events_for_scenario, near_duplicate_pairs)

NOW = "2026-10-17T14:00:00+00:00"


def _active(scenario, direction, **kw):
    return {"scenario": scenario, "direction": direction, "judged": True, "p": kw.pop("p", 0.8), **kw}


def test_merge_carries_links_as_candidates_and_records_twins():
    surv = [_active("Revenue Concentration Risk", "confirms", rationale="settlement")]
    merged = [(2664, [_active("Revenue Concentration Risk", "counters", rationale="new revenue")]),
              (2665, [_active("Revenue Concentration Risk", "confirms")]),
              (2666, [{"scenario": "Other", "direction": "counters", "rejected": True, "rejected_reason": "x"}])]
    out = inherit_links(surv, merged, NOW)
    assert out[0]["also_from"] == [2665]
    cands = [x for x in out if x.get("candidate")]
    assert len(cands) == 1 and cands[0]["inherited_from"] == 2664 and cands[0]["direction"] == "counters"
    # A candidate is not evidence until decided.
    assert _normalize_scenario_relevance(out) == [{"scenario": "Revenue Concentration Risk", "direction": "confirms"}]


def test_decide_covers_proposals_candidates_and_previous_links_not_locked():
    old = [_active("A", "confirms", rationale="kept last run"),
           {"scenario": "B", "direction": "counters", "candidate": True, "inherited_from": 7},
           {"scenario": "C", "direction": "confirms", "locked": True},
           {"scenario": "D", "direction": "counters", "rejected": True, "rejected_reason": "no"}]
    todo = links_to_decide(old, [{"scenario": "A", "direction": "confirms", "p": 0.9, "judged": True},
                                 {"scenario": "C", "direction": "counters", "p": 0.9, "judged": True}])
    keys = {(x["scenario"], x["origin"]) for x in todo}
    assert keys == {("A", "proposal"), ("B", "candidate")}


def test_resolve_records_keep_reject_and_unresolved():
    old = [{"scenario": "B", "direction": "counters", "candidate": True, "inherited_from": 7, "rationale": "twin"},
           {"scenario": "E", "direction": "counters", "candidate": True, "inherited_from": 8}]
    decided = links_to_decide(old, [{"scenario": "A", "direction": "confirms", "p": 0.9, "judged": True}])
    verdicts = {("a", "confirms"): {"keep": True, "rationale": "bears on the claim"},
                ("b", "counters"): {"keep": False, "rationale": "adjacent sector"}}
    out, st = resolve_links(old, decided, verdicts, now=NOW, decided_by="link judge")
    assert st == {"kept": 1, "rejected": 1, "unresolved": 1, "superseded": 0}
    a = next(x for x in out if x["scenario"] == "A")
    assert a["judged"] and a["decided_by"] == "link judge" and a["decided_at"] == NOW
    b = next(x for x in out if x["scenario"] == "B")
    assert b["rejected"] and b["rejected_reason"] == "adjacent sector" and b["inherited_from"] == 7
    e = next(x for x in out if x["scenario"] == "E")
    assert e["candidate"] and e["inherited_from"] == 8
    assert _normalize_scenario_relevance(out) == [{"scenario": "A", "direction": "confirms"}]


def test_conflicting_directions_one_active_and_the_other_superseded():
    old = [_active("R", "confirms", p=0.7), {"scenario": "R", "direction": "counters", "candidate": True,
                                             "inherited_from": 9, "p": 0.6}]
    decided = links_to_decide(old, [])
    verdicts = {("r", "confirms"): {"keep": True, "rationale": "yes"}, ("r", "counters"): {"keep": True, "rationale": "also"}}
    out, st = resolve_links(old, decided, verdicts, now=NOW, decided_by="link judge")
    active = _normalize_scenario_relevance(out)
    assert active == [{"scenario": "R", "direction": "confirms"}] and st["superseded"] == 1
    sup = next(x for x in out if x.get("rejected"))
    assert "superseded" in sup["rejected_reason"] and sup["inherited_from"] == 9


def test_repeated_run_is_stable():
    old = [_active("A", "confirms"), {"scenario": "B", "direction": "counters", "candidate": True, "inherited_from": 7}]
    verdicts = {("a", "confirms"): {"keep": True, "rationale": "yes"}, ("b", "counters"): {"keep": False, "rationale": "no"}}
    out1, _ = resolve_links(old, links_to_decide(old, []), verdicts, now=NOW, decided_by="link judge")
    out2, st2 = resolve_links(out1, links_to_decide(out1, []), {("a", "confirms"): {"keep": True, "rationale": "yes"}},
                              now=NOW, decided_by="link judge")
    assert _normalize_scenario_relevance(out1) == _normalize_scenario_relevance(out2)
    assert [x for x in out2 if x.get("rejected")] == [x for x in out1 if x.get("rejected")]
    assert st2["rejected"] == 0


def test_audit_names_lost_undecided_and_redirected_links():
    rows = [
        {"id": 1, "merged_into": None, "scenario_relevance": [_active("S1", "confirms"),
                                                             {"scenario": "S2", "direction": "counters", "rejected": True,
                                                              "rejected_reason": "adjacent", "inherited_from": 2}]},
        {"id": 2, "merged_into": 1, "scenario_relevance": [_active("S1", "confirms"), _active("S2", "counters")]},
        {"id": 3, "merged_into": 1, "scenario_relevance": [_active("S3", "counters")]},
        {"id": 4, "merged_into": None, "scenario_relevance": [{"scenario": "S4", "direction": "counters", "candidate": True,
                                                              "inherited_from": 5}]},
        {"id": 5, "merged_into": 4, "scenario_relevance": [_active("S4", "counters")]},
        {"id": 6, "merged_into": 5, "scenario_relevance": [_active("S6", "counters")]},
        {"id": 7, "merged_into": 1, "scenario_relevance": [_active("S1", "counters")]},
    ]
    off = audit_merged_links(rows)
    problems = {(o["merged_id"], o["scenario"]): o["problem"] for o in off}
    assert problems == {(3, "S3"): "link never carried to the survivor",
                        (5, "S4"): "undecided candidate on the survivor",
                        (6, "S6"): "link never carried to the survivor",
                        (7, "S1"): "direction changed on the survivor with no recorded decision"}


def test_events_for_scenario_ignores_rejected_and_candidates():
    evs = [{"scenario_relevance": [{"scenario": "S", "direction": "counters", "rejected": True, "rejected_reason": "x"}]},
           {"scenario_relevance": [{"scenario": "S", "direction": "counters", "candidate": True}]},
           {"scenario_relevance": [_active("S", "counters")]}]
    conf, ctr = events_for_scenario(evs, "S")
    assert len(conf) == 0 and len(ctr) == 1


def test_candidate_on_locked_scenario_is_rejected_by_the_lock():
    old = [{"scenario": "P", "direction": "counters", "locked": True, "rationale": "dropped on 23 September"},
           {"scenario": "P", "direction": "confirms", "candidate": True, "inherited_from": 2855}]
    out, st = resolve_links(old, links_to_decide(old, []), {}, now=NOW, decided_by="link judge")
    rej = [x for x in out if x.get("rejected")]
    assert len(rej) == 1 and rej[0]["rejected_by"] == "analyst lock" and rej[0]["inherited_from"] == 2855
    assert _normalize_scenario_relevance(out) == [{"scenario": "P", "direction": "counters"}]
    assert not audit_merged_links([{"id": 1, "merged_into": None, "scenario_relevance": out},
                                   {"id": 2855, "merged_into": 1, "scenario_relevance": [_active("P", "confirms")]}])


def test_missing_survivor_only_matters_when_links_would_be_lost():
    assert audit_merged_links([{"id": 9, "merged_into": 999, "scenario_relevance": []}]) == []
    assert audit_merged_links([{"id": 9, "merged_into": 999, "scenario_relevance": [_active("S", "confirms")]}])[0]["problem"] == "survivor row missing"


def test_rejected_link_is_not_relitigated_by_a_later_inherit_or_run():
    surv = [{"scenario": "K", "direction": "counters", "rejected": True, "rejected_reason": "adjacent", "inherited_from": 3}]
    out = inherit_links(surv, [(3, [_active("K", "counters")])], NOW)
    assert out == surv  # no candidate added, no also_from on a rejection
    old = surv + [{"scenario": "K", "direction": "counters", "candidate": True, "inherited_from": 3}]
    assert links_to_decide(old, []) == []
    out2, st = resolve_links(old, links_to_decide(old, []), {}, now=NOW, decided_by="link judge")
    assert [x for x in out2 if x.get("rejected")] == surv and not any(x.get("candidate") for x in out2)


def test_duplicate_detector_proposes_pairs_and_never_drops_rows():
    rows = [{"id": 1, "topic": "Q", "confidence": 0.9, "actor": "IBM", "subject": "Stage C of DARPA Quantum Benchmarking Initiative",
             "event_date": "2026-10-08", "magnitude_value": None},
            {"id": 2, "topic": "Q", "confidence": 0.8, "actor": "Diraq", "subject": "Stage C of DARPA Quantum Benchmarking Initiative",
             "event_date": "2026-10-07", "magnitude_value": None},
            {"id": 3, "topic": "Q", "confidence": 0.7, "actor": "IonQ", "subject": "trapped-ion memory", "event_date": "2026-09-01",
             "magnitude_value": None}]
    pairs = near_duplicate_pairs(rows)
    assert [(p["a"], p["b"]) for p in pairs] == [(1, 2)]  # proposed, not decided
    assert len(rows) == 3  # the detector drops nothing
