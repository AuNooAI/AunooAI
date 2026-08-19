"""The briefing's article resolver must not silently rebind a pick.

The resolver exists because the model garbles long, near-identical URIs. It
matches on a short corpus id first, then the uri, then the title. Each of those
fallbacks can itself go wrong, and getting it wrong means the briefing's
headline, summary and executive takeaway are attached to a different article's
URL — a worse failure than the missing article the resolver was added to fix.
"""

from unittest.mock import Mock


def _svc():
    from app.services.news_feed_service import NewsFeedService

    return NewsFeedService.__new__(NewsFeedService)


CORPUS = [
    {"uri": "https://example.com/a0", "title": "First story about quantum computing"},
    {"uri": "https://example.com/a1", "title": "Second story about fusion energy"},
    {"uri": "https://example.com/a2", "title": "Third story about chip export rules"},
]


def test_a_wrong_id_that_contradicts_a_good_uri_does_not_rebind_the_pick():
    """An id is two characters, so "a0" for "a2" is the same class of slip the
    resolver defends against. Taking the id on trust would move the write-up
    onto another article."""
    svc = _svc()
    selected = [{
        "id": "a0",                                   # wrong
        "uri": "https://example.com/a2",              # right
        "title": "Third story about chip export rules",
    }]

    resolved, unresolved = svc._resolve_selected_articles(selected, CORPUS)

    assert len(resolved) == 1
    assert resolved[0]["uri"] == "https://example.com/a2", (
        "the title corroborates the uri, so the uri must win"
    )


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
    """The conflict check must not undo the fix: a garbled uri with a good id
    is the original failure and still has to resolve."""
    svc = _svc()
    selected = [{"id": "a1", "uri": "https://example.com/nope", "title": "whatever"}]

    resolved, _ = svc._resolve_selected_articles(selected, CORPUS)

    assert [a["uri"] for a in resolved] == ["https://example.com/a1"]


def test_two_picks_cannot_resolve_to_the_same_article():
    """Two garbled picks can land on one corpus article — one by id, one by
    title. Keeping both puts the same story in the briefing twice under two
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
    """Syndicated wire copy runs under several publishers with one headline.
    Matching on it would attach the analysis to whichever copy came first."""
    svc = _svc()
    corpus = [
        {"uri": "https://reuters.example/x", "title": "Chip export rules tighten"},
        {"uri": "https://apnews.example/y", "title": "Chip export rules tighten"},
    ]
    selected = [{"uri": "https://nowhere.example/z", "title": "Chip export rules tighten"}]

    resolved, unresolved = svc._resolve_selected_articles(selected, corpus)

    assert resolved == [], "an ambiguous title must not identify an article"
    assert len(unresolved) == 1


def test_a_unique_title_still_rescues_a_garbled_uri():
    """The original production failure: right article, right title, wrong uri.

    The prompt makes the model append "(Source, date, author)" to the headline,
    so the match is on the shared prefix. It needs at least
    TITLE_MATCH_MIN_CHARS of normalised text, which real headlines comfortably
    exceed — this one is deliberately as long as the ones that failed in
    production.
    """
    from app.services.news_feed_service import NewsFeedService

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
    assert len(svc._normalize_title_for_match(corpus[0]["title"])) >= \
        NewsFeedService.TITLE_MATCH_MIN_CHARS

    resolved, _ = svc._resolve_selected_articles(selected, corpus)

    assert [a["uri"] for a in resolved] == ["https://example.com/real"]


def test_a_suffixed_title_can_still_settle_an_id_uri_conflict():
    """The wileytest briefing of 2026-08-19, reduced.

    The model copied the right URI and the right headline but the wrong ID
    line. The conflict check asked the title to break the tie, and the title
    the model returns always carries a "(Source, date, author)" suffix — so an
    exact-match-only lookup found nothing and the pick was dropped. Four picks
    went that way in one run and the briefing came back with five articles.
    """
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
        "id": "a46",                                            # wrong
        "uri": "https://www.techmeme.com/260818/p24#a260818p24",  # right
        "title": ("Harvey announces Harvey Tenet, its first in-house, proprietary model "
                  "for legal work, trained on mock disputes and case files "
                  "(Business Insider, 2026-08-18, Melia Robinson)"),
    }]

    resolved, unresolved = svc._resolve_selected_articles(selected, corpus)

    assert unresolved == []
    assert [a["uri"] for a in resolved] == ["https://www.techmeme.com/260818/p24#a260818p24"]
