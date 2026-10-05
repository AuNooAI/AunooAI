"""Exact checks on what the review writes (26 Sep 2026): every figure and
every name in a headline or summary must be in the post."""

from app.services.review_exact_checks import exact_objections


def test_a_figure_the_post_does_not_state_is_caught():
    post = ("Nearly three quarters of CISOs surveyed don't expect AI to shrink "
            "their teams, and over 80 percent said it will create demand.")
    found = exact_objections(None, "73% of CISOs don't expect AI to shrink teams.", post)
    assert found and "73" in found[0]


def test_a_figure_written_another_way_is_not_an_objection():
    post = "Method is proud to announce a $30M STRATFI award."
    assert exact_objections("Method Security wins $30 million award", None, post,
                            ["Method Security"]) == []


def test_a_name_the_post_does_not_mention_is_caught():
    post = "Mate is joining the XAA Ecosystem with more than 50 AI leaders."
    found = exact_objections("Mate joins Okta's XAA Ecosystem", None, post, ["Mate"])
    assert found and "Okta" in found[0]


def test_ordinary_words_and_hyphenated_names_are_not_objections():
    post = "CrowdStrike leads Project QuiltWorks, and Artemis Security has joined it."
    assert exact_objections("Artemis Security joins QuiltWorks",
                            "Enables a CrowdStrike-led coalition.", post,
                            ["Artemis Security"]) == []
