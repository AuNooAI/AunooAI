"""Briefing review: the judge's "date" findings are handled without the writer.

The reviewer kept flagging sentences for dating an event by the day it was
reported, and the writer kept failing to fix them (wileytest, 25 Sep 2026:
14 warnings, then 7, 3 and 16 across three writer rounds). These tests hold
the two deterministic rules that replaced that loop, replayed on the
sentences that briefing actually shipped with.
"""

from app.services import daily_report_service as svc


def _finding(claim, check="date", fix="", evidence="Article 6", severity="warning", text="x"):
    return {"target": "summary", "severity": severity, "finding": text, "evidence": evidence,
            "suggested_fix": fix, "claim_text": claim, "check": check, "source": "judge"}


# The seven warnings desk briefing 166 finalized with, verbatim.
ALREADY_ATTRIBUTED = [
    "The Boston Globe reported on September 23, 2026, that the White House reversed a proposed directive that would have established a commission with authority to block National Institutes of Health research grants, preserving existing grant approval processes.",
    "Separately, reports on September 24, 2026, stated that the White House asked OpenAI and Anthropic not to share new AI models with the UK's AI Safety Institute until US authorities complete their own reviews, with Anthropic agreeing to the request.",
    "The Boston Globe reported on September 23, 2026, that the White House reversed a proposed directive that would have created a commission to block NIH grants (Article 6), while NPR published on September 24, 2026, an analysis with six graphics showing that NIH funding disruptions under the Trump administration have led to lab closures and scientist job losses (Article 1).",
]
NO_DATE_STATED = [
    "OpenEvidence raised $250 million at a $15 billion valuation (up from $12 billion in January) and may be open to acquisition, according to sources cited by Business Insider (Article 7, Incident 3).",
    "The Information reported, citing PitchBook data, that AI coding assistant TypeSafe is in talks to raise over $1 billion at a valuation exceeding $10 billion, one week after announcing a $40 million seed round at a $200 million valuation—a 50x valuation increase in seven days.",
]
BARE_EVENT_DATE = (
    "OpenEvidence raised $250 million at a $15 billion valuation and may be open to acquisition according to Business Insider, "
    "while Edison Scientific announced on September 24 a partnership with Springer Nature to integrate research content into its Kosmos platform."
)


def test_date_findings_on_attributed_or_undated_sentences_are_dropped():
    findings = [_finding(c) for c in ALREADY_ATTRIBUTED + NO_DATE_STATED] + [_finding(BARE_EVENT_DATE)]
    kept = svc._drop_attributed_date_findings(findings)
    assert [f["claim_text"] for f in kept] == [BARE_EVENT_DATE]


def test_non_date_findings_pass_through_untouched():
    f = _finding(ALREADY_ATTRIBUTED[0], check="actor", severity="error")
    assert svc._drop_attributed_date_findings([f]) == [f]


def test_bare_event_date_gets_as_reported_on():
    out = svc._date_fix_sentence(BARE_EVENT_DATE)
    assert "announced, as reported on September 24, a partnership" in out
    assert out.count("as reported on") == 1
    # Idempotent: the sentence is attributed now.
    assert svc._date_fix_sentence(out) == out


def test_sentence_final_and_leading_dates():
    assert svc._date_fix_sentence("The White House reversed the directive on September 23, 2026.") == \
        "The White House reversed the directive, as reported on September 23, 2026."
    assert svc._date_fix_sentence("On 2026-09-23 the White House reversed the directive.") == \
        "As reported on 2026-09-23 the White House reversed the directive."


def test_attributed_sentences_are_left_alone():
    for s in ALREADY_ATTRIBUTED:
        assert svc._date_fix_sentence(s) == s


def test_apply_date_fixes_edits_only_the_quoted_sentence():
    draft = {
        "briefing_summary": "Untouched opener. " + BARE_EVENT_DATE + " Untouched closer on September 30.",
        "themes": [{"theme_name": "T", "description": "Theme text announced on September 24 too.", "strategic_implication": "So what."}],
        "priority_actions": [{"action": "Do X.", "rationale": "Because."}],
    }
    fixed, n = svc._apply_date_fixes(draft, [_finding(BARE_EVENT_DATE)])
    assert n == 1
    assert fixed["briefing_summary"].startswith("Untouched opener. ")
    assert fixed["briefing_summary"].endswith(" Untouched closer on September 30.")
    assert "announced, as reported on September 24, a partnership" in fixed["briefing_summary"]
    assert fixed["themes"][0]["description"] == draft["themes"][0]["description"]
    assert BARE_EVENT_DATE in draft["briefing_summary"], "input must not be mutated"


def test_apply_date_fixes_tolerates_quote_drift_and_skips_unsourced_dates():
    draft = {"briefing_summary": "Edison Scientific announced on September 24 a partnership — big one.", "themes": [], "priority_actions": []}
    drifted = "Edison  Scientific announced on September 24 a partnership - big one."
    fixed, n = svc._apply_date_fixes(draft, [_finding(drifted)])
    assert n == 1 and "as reported on September 24" in fixed["briefing_summary"]
    # A date no source states at all is not rescued by attribution.
    _, n = svc._apply_date_fixes(draft, [_finding(draft["briefing_summary"], evidence="no source")])
    assert n == 0


def test_fix_that_says_wording_is_acceptable_is_not_a_finding():
    raw = [
        {"target": "summary", "severity": "warning", "check": "date", "claim_text": "x",
         "finding": "Incident 1 states this was 'reported 2026-09-24', not that the request occurred on that date.",
         "suggested_fix": "The current wording is acceptable as it says 'reports on September 24 stated', which correctly identifies this as the reporting date rather than the event date."},
        {"target": "summary", "severity": "warning", "check": "date", "claim_text": "y",
         "finding": "The January valuation is correctly sourced. The theme should clarify this is the reporting date.",
         "suggested_fix": "Write 'raised $250 million at a $15 billion valuation as reported on September 24' to clarify timing."},
    ]
    kept = svc._sanitize_review_findings(raw)
    assert [f["claim_text"] for f in kept] == ["y"]


def test_writer_rounds_ignore_date_fix_rounds():
    rounds = [{"round": 1, "kind": "date_fix"}, {"round": 2}, {"round": 3, "kind": "date_fix"}]
    assert svc._writer_rounds(rounds) == 1


# --- The writer splices, it does not rewrite ---------------------------------

DRAFT = {
    "briefing_summary": "Opener stays. The Register reported that an academic publisher was compromised by LAPSUS$. Closer stays.",
    "themes": [{"theme_name": "T", "description": "Enveda raised $311 million. Untouched second sentence.", "strategic_implication": "So what."}],
    "priority_actions": [{"action": "Do X.", "rationale": "Because."}],
}


def test_replacement_changes_only_the_quoted_sentence():
    reps = [{"claim_text": "The Register reported that an academic publisher was compromised by LAPSUS$.",
             "replacement": "The Register reported that Elsevier was compromised by LAPSUS$."}]
    out, n = svc._apply_replacements(DRAFT, reps)
    assert n == 1
    assert out["briefing_summary"] == "Opener stays. The Register reported that Elsevier was compromised by LAPSUS$. Closer stays."
    assert out["themes"] == DRAFT["themes"] and out["priority_actions"] == DRAFT["priority_actions"]
    assert "academic publisher" in DRAFT["briefing_summary"], "input must not be mutated"


def test_empty_replacement_deletes_the_sentence():
    out, n = svc._apply_replacements(DRAFT, [{"claim_text": "Enveda raised $311 million.", "replacement": ""}])
    assert n == 1
    assert out["themes"][0]["description"] == "Untouched second sentence."


def test_replacements_skip_no_ops_unmatched_and_oversized():
    reps = [
        {"claim_text": "Enveda raised $311 million.", "replacement": "Enveda raised $311 million."},   # no-op
        {"claim_text": "This sentence is not in the draft.", "replacement": "Whatever."},               # unmatched
        {"claim_text": "Do X.", "replacement": "Do X. " + "And a whole new field of prose. " * 20},     # oversized
        "not a dict",
    ]
    out, n = svc._apply_replacements(DRAFT, reps)
    assert n == 0 and out == DRAFT


def test_repair_prompt_asks_for_replacements_not_a_rewrite():
    assert '"replacements"' in svc.REPAIR_PROMPT
    assert "briefing_summary" not in svc.REPAIR_PROMPT
    assert "never flag it for its date" in svc.DEFAULT_REVIEWER_PROMPT
