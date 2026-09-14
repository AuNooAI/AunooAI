"""Guardrails on the Market Monitor briefing's inline citation resolver.

The case that motivated this file: the model wrote "[A5, A11]" — two facts
supporting one sentence, which is how anybody cites two things — and the
resolver deleted the whole bracket. The single-ID pattern didn't match it,
so the stray-bracket pattern swept it up as junk. Three brackets went that
way in the 2026-08-17 SOC automation weekly, taking eight valid IDs and
their References entries with them, and the reader saw a sentence with no
evidence behind it.

The resolver still has to throw away an invented ID and a descriptive
bracket like "[headcount data]", so widening it far enough to keep a real
group without also letting junk through is the thing worth pinning down.
"""

import pytest

from app.services.market_briefing import resolve_citations


def _facts(*cite_ids):
    """A citation index holding exactly the IDs named."""
    return {"citation_index": {
        cid: {"vendor": f"Vendor {cid}", "title": f"Title {cid}",
              "uri": f"https://example.test/{cid}"}
        for cid in cite_ids
    }}


def test_a_grouped_citation_keeps_every_id_and_both_references():
    content = "Two vendors shipped agentic triage [A5, A11]."
    out, refs, dropped = resolve_citations(content, _facts("A5", "A11"))

    assert "[A5, A11]" in out
    assert [r["cite_id"] for r in refs] == ["A5", "A11"]
    assert dropped == []


def test_a_single_citation_is_untouched():
    out, refs, dropped = resolve_citations("One fact [A1].", _facts("A1"))

    assert "[A1]" in out
    assert [r["cite_id"] for r in refs] == ["A1"]
    assert dropped == []


def test_a_group_mixing_real_and_invented_ids_keeps_the_real_half():
    out, refs, dropped = resolve_citations("Claim [A2, A998].", _facts("A2"))

    assert "[A2]" in out
    assert "A998" not in out
    assert [r["cite_id"] for r in refs] == ["A2"]
    assert len(dropped) == 1


def test_a_group_of_only_invented_ids_loses_the_bracket():
    out, _, dropped = resolve_citations("Claim [A998, A999].", _facts("A1"))

    assert "[" not in out
    assert len(dropped) == 2


def test_a_descriptive_bracket_is_still_stripped():
    out, refs, dropped = resolve_citations(
        "Hiring rose [headcount data].", _facts("A1"))

    assert "headcount data" not in out
    assert refs == []
    assert len(dropped) == 1


def test_a_stripped_bracket_does_not_leave_a_space_before_the_period():
    out, _, _ = resolve_citations("Hiring rose [headcount data].", _facts("A1"))

    assert "rose." in out


@pytest.mark.parametrize("detail_source", ["invented", "descriptive"])
def test_every_lint_entry_carries_the_check_key_the_ui_renders(detail_source):
    """MarketBriefingsView renders "{l.check}: {l.detail}".

    These entries used to be built with a "kind" key while every other lint
    producer used "check", so the label came out undefined and the reader got
    a bare leading colon: ": dropped non-citation bracket [A5, A11]".
    """
    content = ("Claim [A999]." if detail_source == "invented"
               else "Claim [headcount data].")
    _, _, dropped = resolve_citations(content, _facts("A1"))

    assert dropped
    for entry in dropped:
        assert entry["check"] == "citation"
        assert entry["detail"]


def test_references_list_one_entry_per_id_even_when_grouped():
    content = "First [A5, A11]. Second [A11]. Third [A5]."
    out, refs, _ = resolve_citations(content, _facts("A5", "A11"))

    assert [r["cite_id"] for r in refs] == ["A5", "A11"]
    assert out.count("[A5] ") == 1
    assert out.count("[A11] ") == 1


# --- Citation placement -----------------------------------------------------
#
# Kimi copies the fact list's layout, where every line starts with its ID, and
# opens sentences with the citation: "[A2] Arambh Labs launched…". The prompt
# now shows the right and wrong form; move_leading_citations is the safety
# net for the lines it still gets wrong.

from app.services.market_briefing import move_leading_citations


def test_a_citation_opening_a_line_moves_to_the_end_of_its_sentence():
    assert (move_leading_citations("[A2] Arambh Labs launched Armor Detect.")
            == "Arambh Labs launched Armor Detect. [A2]")


def test_two_leading_citations_both_move():
    assert (move_leading_citations("[A5] [A11] Andesite partnered with Booz Allen.")
            == "Andesite partnered with Booz Allen. [A5] [A11]")


def test_a_grouped_leading_citation_moves_as_separate_brackets():
    assert (move_leading_citations("[A5, A11] Andesite partnered with Booz Allen.")
            == "Andesite partnered with Booz Allen. [A5] [A11]")


def test_a_bullet_keeps_its_marker():
    assert (move_leading_citations("- [A9] Intezer announced an integration.")
            == "- Intezer announced an integration. [A9]")


def test_only_the_first_sentence_on_the_line_gets_the_moved_citation():
    assert (move_leading_citations("[A2] First claim. Second, uncited.")
            == "First claim. [A2] Second, uncited.")


def test_a_sentence_ending_in_a_quote_keeps_the_quote_before_the_citation():
    assert (move_leading_citations('[A16] Wraithwatch got access to "Mythos."')
            == 'Wraithwatch got access to "Mythos." [A16]')


def test_a_heading_with_no_full_stop_is_left_alone():
    line = "### [A1] Product launches"
    assert move_leading_citations(line) == line


def test_a_citation_after_a_full_stop_mid_paragraph_is_not_moved():
    """"X. [A3] Y." is the correct form — A3 cites X — so it must stay."""
    text = "Five partnerships were announced. [A5] Andesite partnered with Booz Allen."
    assert move_leading_citations(text) == text


def test_a_correctly_placed_trailing_citation_is_untouched():
    text = "Arambh Labs launched Armor Detect. [A2]"
    assert move_leading_citations(text) == text


def test_the_resolver_applies_the_move_before_resolving():
    out, refs, dropped = resolve_citations(
        "[A2] Arambh Labs launched Armor Detect.\n[A999] Invented.",
        _facts("A2"))

    assert out.startswith("Arambh Labs launched Armor Detect. [A2]\nInvented.")
    assert [r["cite_id"] for r in refs] == ["A2"]
    assert len(dropped) == 1
