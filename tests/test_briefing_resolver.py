"""The briefing's article resolver must not silently rebind a pick.

The resolver exists because the model garbles long, near-identical URIs. It
matches on the short corpus id the model is asked to return. Until October
2026 a uri or a title could overrule or rescue a pick; twelve briefings in a
week then logged "Selected article disagrees with itself" and the title
heuristic settled them. Work package 31 of
docs/COLLECTOR_DATA_QUALITY_SPEC.md ends that: the id is the pick, an
echoed uri or title that names another article rejects the pick, and a
title alone never resolves anything. Getting a pick wrong attaches the
headline, summary and executive takeaway to a different article's URL,
which is worse than a missing article.
"""


def _svc():
    from app.services.news_feed_service import NewsFeedService

    return NewsFeedService.__new__(NewsFeedService)


CORPUS = [
    {"uri": "https://example.com/a0", "title": "First story about quantum computing"},
    {"uri": "https://example.com/a1", "title": "Second story about fusion energy"},
    {"uri": "https://example.com/a2", "title": "Third story about chip export rules"},
]


def test_a_wrong_id_that_contradicts_a_good_uri_rejects_the_pick():
    """An id is two characters, so "a0" for "a2" is the kind of slip the
    resolver defends against. Neither side is trusted over the other: the
    pick is rejected and the caller asks again."""
    svc = _svc()
    selected = [{
        "id": "a0",
        "uri": "https://example.com/a2",
        "title": "Third story about chip export rules",
    }]

    resolved, unresolved = svc._resolve_selected_articles(selected, CORPUS)

    assert resolved == []
    assert unresolved[0]["_unresolved_reason"] == "selection_mismatch"


def test_an_unresolvable_conflict_drops_the_pick_rather_than_guessing():
    svc = _svc()
    selected = [{
        "id": "a0",
        "uri": "https://example.com/a2",
        "title": "A headline matching neither",
    }]

    resolved, unresolved = svc._resolve_selected_articles(selected, CORPUS)

    assert resolved == []
    assert len(unresolved) == 1


def test_an_id_alone_still_resolves():
    """A garbled uri with a good id is the original failure and still has to
    resolve: a uri that names nothing in the corpus is not a contradiction."""
    svc = _svc()
    selected = [{"id": "a1", "uri": "https://example.com/nope", "title": "whatever"}]

    resolved, _ = svc._resolve_selected_articles(selected, CORPUS)

    assert [a["uri"] for a in resolved] == ["https://example.com/a1"]


def test_two_picks_cannot_resolve_to_the_same_article():
    """Two picks can land on one corpus article, one by id and one by uri.
    Keeping both puts the same story in the briefing twice under two
    different write-ups."""
    svc = _svc()
    selected = [
        {"id": "a1", "title": "Second story about fusion energy"},
        {"uri": "https://example.com/a1", "title": "Second story about fusion energy"},
    ]

    resolved, unresolved = svc._resolve_selected_articles(selected, CORPUS)

    assert len(resolved) == 1
    assert len(unresolved) == 1


def test_a_title_shared_by_two_articles_is_not_used_as_an_identifier():
    """Syndicated wire copy runs under several publishers with one headline."""
    svc = _svc()
    corpus = [
        {"uri": "https://reuters.example/x", "title": "Chip export rules tighten"},
        {"uri": "https://apnews.example/y", "title": "Chip export rules tighten"},
    ]
    selected = [{"uri": "https://nowhere.example/z", "title": "Chip export rules tighten"}]

    resolved, unresolved = svc._resolve_selected_articles(selected, corpus)

    assert resolved == [], "an ambiguous title must not identify an article"
    assert len(unresolved) == 1


def test_a_unique_title_does_not_rescue_a_garbled_uri():
    """Right article, right title, wrong uri, no id: before work package 31
    the title rescued this pick. It no longer does, because the same rule
    attached write-ups to the wrong outlet when titles were shared. The
    caller asks the model again with the id instead."""
    svc = _svc()
    corpus = [{
        "uri": "https://example.com/real",
        "title": "Pornhub's parent company Aylo will pay $120M to settle two class actions",
    }]
    selected = [{
        "uri": "https://example.com/garbled",
        "title": ("Pornhub's parent company Aylo will pay $120M to settle two class "
                  "actions (Techmeme, 2026-08-17, Samantha Cole/404 Media)"),
    }]

    resolved, unresolved = svc._resolve_selected_articles(selected, corpus)

    assert resolved == []
    assert unresolved[0]["_unresolved_reason"] == "no_match"


def test_a_suffixed_title_does_not_settle_an_id_uri_conflict():
    """The wileytest briefing of 2026-08-19, reduced: right URI, right
    headline, wrong ID line. The title used to break the tie. Now the id and
    uri disagree, so the pick is a selection_mismatch and the caller retries
    once; the title's "(Source, date, author)" suffix plays no part."""
    svc = _svc()
    corpus = [
        {"uri": f"https://filler.example/{i}", "title": f"Filler headline number {i} about nothing at all"}
        for i in range(24)
    ]
    corpus.append({
        "uri": "https://www.techmeme.com/260818/p24#a260818p24",
        "title": ("Harvey announces Harvey Tenet, its first in-house, proprietary model "
                  "for legal work, trained on mock disputes and case files"),
    })
    corpus += [
        {"uri": f"https://other.example/{i}", "title": f"Another unrelated headline number {i} entirely"}
        for i in range(25, 47)
    ]
    assert corpus[46]["uri"] == "https://other.example/46"

    selected = [{
        "id": "a46",
        "uri": "https://www.techmeme.com/260818/p24#a260818p24",
        "title": ("Harvey announces Harvey Tenet, its first in-house, proprietary model "
                  "for legal work, trained on mock disputes and case files "
                  "(Business Insider, 2026-08-18, Melia Robinson)"),
    }]

    resolved, unresolved = svc._resolve_selected_articles(selected, corpus)

    assert resolved == []
    assert unresolved[0]["_unresolved_reason"] == "selection_mismatch"


def test_the_prefix_title_check_still_flags_a_mismatch_with_a_suffixed_title():
    """The title check uses the shared prefix, so a suffixed title that names
    another corpus article is still caught as a mismatch."""
    svc = _svc()
    corpus = [
        {"uri": "https://a.example/1", "title": "A long enough headline about one subject for the check"},
        {"uri": "https://a.example/2", "title": "Another long enough headline about a second subject here"},
    ]
    selected = [{"id": "a0", "title": corpus[1]["title"] + " (Reuters, 2026-10-01, Someone)"}]

    resolved, unresolved = svc._resolve_selected_articles(selected, corpus)

    assert resolved == []
    assert unresolved[0]["_unresolved_reason"] == "selection_mismatch"
